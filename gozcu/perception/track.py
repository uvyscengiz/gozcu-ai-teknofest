"""Takip katmanı — tespiti **zenginleştirir**, süzmez.

## Birinci düzeltme (25 Ağustos): kaldırılan süzgeç

Buradaki kural şuydu: `if box.id is None: continue`. BoTSORT bir kimlik
atayamadıysa kutu hiç var olmamış sayılıyordu. Ölçüldü (raf çökmesi klibi,
23 kare): YOLO 6 kutu buldu, BoTSORT 0 kimlik verdi, ajan katmanına 0 tespit
ulaştı. Süzgeç kaldırıldı ve sözleşme tersine çevrildi: **tespit kayıttır,
takip kimlik ekleyebildiğinde ekler.**

## İkinci düzeltme (25 Ağustos): kaldırılan VETO

Süzgeci kaldırmak **yetmedi**, çünkü kayıp oradan gelmiyordu. Ultralytics'in
`model.track()` çağrısı, kare için en az bir onaylı iz üretirse
`results.boxes`'ı **iz alt kümesiyle değiştiriyor**; sıfır iz üretirse ham
tespitler dokunulmadan geçiyor. Yani kutular bizim döngümüz onları hiç
görmeden yok oluyordu ve `botsort.yaml`'daki hiçbir eşik bunu değiştirmiyor —
bu bir ayar değil, bir postprocess semantiği.

Ölçüldü (tekstil fabrikası kazası, 116 kare, `benchmark/perception.py`):

    conf    takipsiz kutu   takipten sonra   yok edilen
    0,20         266             159            %40
    0,05         770             334            %57
    0,03        1150             469            %59

Takip **41 karede kutu eledi, 0 karede ekledi.** Ve eşik düştükçe kötüleşti:
`YOLO_CONFIDENCE` 0,20'den 0,03'e indiğinde bu katman baskın kayıp hâline
geldi (sayım duyarlılığı takiple %31, takipsiz %83,4).

Bu yüzden `model.track()` artık **hiç çağrılmıyor**. Akış:

1. `detect_objects()` her kareyi tek başına geçiyor — **kayıt budur**,
2. `attach_track_ids()` ilişkilendiriciyi çağırıp kimlikleri **iliştiriyor**,
3. kimlik atanamayan kutu `track_id=None` ile **yine de geçiyor**.

İlişkilendirici `gozcu.associate` — kare başına açgözlü IoU eşleştirmesi.
Ultralytics'in ByteTrack'i denendi ve geri alındı: onu değerli kılan şey
düşük güvenli kutuları **kurtarması**, ama biz artık hiçbir kutuyu
düşürmediğimiz için kurtarılacak bir şey yok; geriye yalnız sürümden sürüme
oynayan bir iç API kalıyordu (ayrıntı: `gozcu/associate.py`).

## Kimlik ne işe yarıyor

Yalnız iki hesap kimlik istiyor (`gozcu.signals`): `velocities` ve
`vanished_tracks`. `person_count` ve `gathering` kimlikten bağımsız. Yani
kimlik bir **açıklama**, kayıt değil — ve açıklamayı üreten katmanın kaydı
veto etme yetkisi olamaz.
"""

from dataclasses import dataclass
from pathlib import Path

from gozcu.perception.detect import DetectedObject, detect_objects

__all__ = ["FrameTracker", "TrackedObject", "attach_track_ids", "track_video"]


@dataclass
class TrackedObject(DetectedObject):
    #: Takip kimliği — **isteğe bağlı**. `None` "bu kutu yok" demek değil,
    #: "bu kutuya kimlik atanamadı" demek. `models.Detection.track_id` zaten
    #: `int | None` olduğu için veri sözleşmesi değişmiyor.
    track_id: int | None = None


class FrameTracker:
    """Kare kare tespit + takip — `track_video`'nun artımlı karşılığı.

    Her `process` çağrısı bir kareyi tespit edip IoU kimliği iliştiriyor;
    durum kareler arasında taşınıyor. `run_pipeline`'ın akış algısı bunu
    kullanıyor: her kare sonucu hemen depoya yazılıyor ve SSE'ye bump
    ediliyor — toplu `track_video` yerine.
    """

    def __init__(self):
        self._associate = _default_associator()
        self._state: dict = {}

    def process(self, frame_path) -> list[TrackedObject]:
        detected = detect_objects(frame_path)
        try:
            ids = list(self._associate(detected, self._state))
        except ValueError:
            raise
        except Exception:      # noqa: BLE001 — takip arızası kaydı silemez
            ids = [None] * len(detected)
        if len(ids) != len(detected):
            raise ValueError(
                f"ilişkilendirici {len(detected)} kutuya {len(ids)} kimlik "
                "döndürdü; hizasız cevap kimlikleri yanlış kutulara bağlar")
        return [
            TrackedObject(class_name=box.class_name, confidence=box.confidence,
                          bbox=box.bbox, track_id=track_id)
            for box, track_id in zip(detected, ids, strict=True)]


def attach_track_ids(detected_frames, associate) -> list[list[TrackedObject]]:
    """Kimlikleri kutulara iliştirir; **kutu sayısını asla değiştirmez.**

    `associate(boxes, state) -> list[int | None]` kare başına bir kez
    çağrılıyor ve kutularla **aynı uzunlukta** bir kimlik listesi döndürmeli.
    `state` kareler arasında taşınan bir sözlük: ilişkilendirici kendi iz
    defterini orada tutuyor.

    Üç garanti:

    - **Eleme yok.** Çıktıdaki kutu sayısı girdideki ile birebir aynı.
    - **Hizasız cevap reddediliyor.** Kısa bir kimlik listesini sessizce
      doldurmak kimlikleri YANLIŞ kutulara bağlardı ve bu, hatalı bir hız
      hesabı olarak hiçbir uyarı vermeden ortaya çıkardı.
    - **İlişkilendiricinin çöküşü kareyi düşürmez.** Patlarsa o kare
      kimliksiz geçiyor. Takip katmanının arızası tespit kanıtını yok
      edemez — bu modülün varlık sebebi tam olarak bu.
    """
    state: dict = {}
    out: list[list[TrackedObject]] = []
    for boxes in detected_frames:
        try:
            ids = list(associate(boxes, state))
        except ValueError:
            raise
        except Exception:      # noqa: BLE001 — takip arızası kaydı silemez
            ids = [None] * len(boxes)
        if len(ids) != len(boxes):
            raise ValueError(
                f"ilişkilendirici {len(boxes)} kutuya {len(ids)} kimlik "
                "döndürdü; hizasız cevap kimlikleri yanlış kutulara bağlar")
        out.append([
            TrackedObject(class_name=box.class_name, confidence=box.confidence,
                          bbox=box.bbox, track_id=track_id)
            for box, track_id in zip(boxes, ids, strict=True)])
    return out


def _default_associator():
    """Boru hattının kimlik üreticisi — bkz. `gozcu.associate`.

    Ultralytics'in ByteTrack'i denendi ve **geri alındı**: bu sürümde
    `BYTETracker.__init__` `frame_rate` almıyor, `update()` de
    dilimlenebilir bir `Boxes` istiyor. İkisi de sessizce `except`'e düşüp
    bütün kimlikleri `None` yaptı ve bunu ancak `track_id_rate` ölçümü
    yakaladı. Tespit artık kayıt olduğu için ByteTrack'in asıl değeri
    (düşük güvenli kutuyu kurtarma) zaten bize gereksizdi.
    """
    from gozcu.memory.associate import iou_associator

    return iou_associator()


def track_video(frame_paths: list[str | Path]) -> list[list[TrackedObject]]:
    """Kareleri tespit edip kimlik iliştirir; **her kutu geçer.**

    `model.track()` bilerek çağrılmıyor — bkz. modül docstring'i. Tespit
    `gozcu.detect.detect_objects` ile yapılıyor, yani boru hattı ile ölçüm
    aynı kapıdan geçiyor ve ikisi ayrışamıyor.
    """
    detected = [detect_objects(path) for path in frame_paths]
    return attach_track_ids(detected, _default_associator())
