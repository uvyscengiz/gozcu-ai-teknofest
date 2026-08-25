"""Kimlik ilişkilendirmesi — kutuya iz kimliği bağlar, kutuya dokunmaz.

`gozcu.track` artık `model.track()` çağırmıyor (sebebi orada yazılı: o çağrı
kutuları eliyordu). Geriye kimlikleri kimin üreteceği sorusu kaldı ve cevap
Ultralytics'in ByteTrack'i **değil**. İki sebep:

1. **ByteTrack'in asıl değeri bize gereksiz.** Onu değerli kılan şey ikinci
   aşaması: düşük güvenli kutuları mevcut izlere bağlayıp **kurtarması**.
   Ama biz artık hiçbir kutuyu düşürmüyoruz — kurtarılacak bir şey yok.
   Geriye yalnız kimlik eşleştirmesi kalıyor.
2. **İç API'si sürümden sürüme oynuyor.** Bu sürümde `BYTETracker.__init__`
   `frame_rate` almıyor ve `update()` `IterableSimpleNamespace` değil
   dilimlenebilir bir `Boxes` istiyor. Ölçüm koşusunda bu, sessizce
   `except`'e düşüp **bütün kimlikleri `None` yaptı** ve fark edilmesi bir
   ölçüm turu aldı. Kırılgan bir bağımlılığı, 40 satırlık ve tam test edilmiş
   bir eşleştiriciyle değiştirmek burada doğru takas.

## Ne yapıyor

Kare başına açgözlü IoU eşleştirmesi: her kutu, aynı sınıftan ve en çok
örtüşen ize bağlanıyor; eşleşmeyen kutu **yeni bir iz başlatıyor**;
eşleşmeyen iz `buffer_frames` kadar bekletiliyor, sonra düşüyor.

**Her kutu bir kimlik alır.** Kimliksiz bırakmak bir seçenekti ama gereksiz:
kimlik artık kaydı veto etmiyor, yalnız açıklıyor. Gürültülü bir izin
zararı `gozcu.signals`'ta soruluyor ("bu iz kaç kare boyunca görüldü"),
burada değil — kimlik üretmek ile kimliğe güvenmek ayrı işler.
"""

from collections.abc import Callable

__all__ = ["DEFAULT_IOU", "iou", "iou_associator"]

#: Eşleştirme tabanı. 0,3 gevşek görünüyor ama kasıtlı: 1 fps'te bir insan
#: iki kare arasında kendi genişliği kadar yol alabiliyor ve sıkı bir eşik
#: her adımda yeni kimlik üretirdi. Kare hızı yükseldikçe (bkz. `FRAME_FPS`)
#: bu taban fazlasıyla güvenli kalıyor.
DEFAULT_IOU = 0.3


def iou(a, b) -> float:
    """İki kutunun kesişim/birleşim oranı; alansız kutuda 0,0."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(ix2 - ix1, 0) * max(iy2 - iy1, 0)
    if inter <= 0:
        return 0.0
    area_a = max(ax2 - ax1, 0) * max(ay2 - ay1, 0)
    area_b = max(bx2 - bx1, 0) * max(by2 - by1, 0)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def iou_associator(iou_threshold: float = DEFAULT_IOU,
                   buffer_frames: int | None = None) -> Callable:
    """`associate(boxes, state) -> list[int | None]` kapanışı üretir.

    `buffer_frames` bir izin kaç kare görünmeden hayatta kalacağı. `None`
    ise `FRAME_FPS`'ten türetiliyor: **üç saniyelik** bir tampon. Kare
    sayısına sabitlenseydi kare hızı değiştiğinde tamponun anlamı sessizce
    değişirdi (1 fps'te 30 kare 30 saniye, 5 fps'te 6 saniye).
    """
    if buffer_frames is None:
        from gozcu.config import FRAME_FPS
        buffer_frames = max(int(round(3.0 * FRAME_FPS)), 1)

    def associate(boxes, state) -> list[int | None]:
        tracks = state.setdefault("tracks", {})
        if not boxes:
            _age(tracks, buffer_frames)
            return []

        # Açgözlü: bütün (kutu, iz) çiftlerini örtüşmeye göre sırala, en iyiden
        # başlayarak her ikisi de boştaysa bağla. Macar algoritması daha
        # "doğru" olurdu; bu ölçekte (kare başına <60 kutu) farkı ölçülemez
        # ve okunabilirlik kazanıyor.
        pairs = []
        for box_index, box in enumerate(boxes):
            for track_id, track in tracks.items():
                if track["class_name"] != box.class_name:
                    continue          # forklift bir insanın kimliğini almaz
                overlap = iou(box.bbox, track["bbox"])
                if overlap >= iou_threshold:
                    pairs.append((overlap, box_index, track_id))
        pairs.sort(key=lambda item: -item[0])

        ids: list[int | None] = [None] * len(boxes)
        claimed: set[int] = set()
        for _, box_index, track_id in pairs:
            if ids[box_index] is None and track_id not in claimed:
                ids[box_index] = track_id
                claimed.add(track_id)

        for box_index, box in enumerate(boxes):
            if ids[box_index] is None:
                state["next_id"] = state.get("next_id", 0) + 1
                ids[box_index] = state["next_id"]
            tracks[ids[box_index]] = {"bbox": box.bbox,
                                      "class_name": box.class_name,
                                      "missed": 0,
                                      "hits": tracks.get(ids[box_index], {})
                                      .get("hits", 0) + 1}

        _age(tracks, buffer_frames, seen=set(ids))
        return ids

    return associate


def _age(tracks: dict, buffer_frames: int, seen: set | None = None) -> None:
    """Bu karede görülmeyen izleri yaşlandırır; tamponu aşanı düşürür."""
    seen = seen or set()
    for track_id in list(tracks):
        if track_id in seen:
            continue
        tracks[track_id]["missed"] += 1
        if tracks[track_id]["missed"] > buffer_frames:
            del tracks[track_id]
