"""Kare başına türetilen sinyaller — hangisi kimlik ister, hangisi istemez.

`gozcu.track` kimliksiz kutuları da veriyor (`track_id is None`). Bu modülün
işi o iki dünyayı ayırmak:

- **Kimlik istemeyen** hesap: `person_count` / `person_count_delta`. Bir insan
  kimliği atanamadı diye kareden silinmez; sayılır.
- **Kimlik isteyen** hesaplar: `velocities` ve `vanished_tracks`. İkisi de
  "aynı nesne iki karede nerede" sorusuna dayanıyor ve bu soru kimliksiz bir
  kutuyla cevaplanamaz.

İki tuzak burada bilerek kapatılıyor:

1. `{obj.track_id: obj for obj in frame_objects}` — `None` anahtarları
   ÇAKIŞIR. Karedeki bütün kimliksiz nesneler tek bir girdiye iner ve iki
   kare arasında **farklı fiziksel nesneler** arasında hayalet bir hız
   hesaplanır. Süzgeç sözlük kurulmadan önce uygulanıyor.
2. `vanished_tracks` içine `None` sızarsa yönlendiricinin özetine
   `kaybolan=[None]` diye düşer ve model olmayan bir izin kaybolduğunu okur.
   `prev_by_id` yalnız kimliklilerden kurulduğu için `None` oraya hiç
   giremiyor.

## Kaybolma artık ısrar istiyor (25 Ağustos, kare hızı yükseldiğinde)

Eskiden kural şuydu: *önceki karede vardı, bu karede yok → kayboldu.* 1
fps'te bu makul bir tanımdı. `FRAME_FPS` 1'den 5'e çıkınca aynı tanım **200
ms'lik bir kesintiyi kaybolma sayıyor** ve yönlendiricinin pencere özeti
sahte kaybolmalarla doluyor — `loop.py`'ın taban kontrolü de onları gerçek
kanıt sanıyor.

Eşik bu yüzden **saniye cinsinden** (`vanish_after_s`), kare cinsinden değil.
Kare sayısına sabitlenseydi kare hızı her değiştiğinde eşiğin anlamı sessizce
değişirdi. Ve bir iz **bir kez** bildiriliyor: her karede yeniden "kayboldu"
demek, tek bir olayı pencere boyunca çoğaltmak olurdu.

## `interior_vanished_tracks` HESAPLANIYOR ama HENÜZ KULLANILMIYOR

Fikir sağlamdı: "makineye kapılan işçi" sinyal olarak *hızlanan ve sonra
kadraj kenarına değmeden kaybolan bir iz*. Kadrajı terk eden insan gitmiştir;
kadraj ortasında kaybolan insan bir şeyin içine girmiştir.

**Ölçüldü ve çalışmadı.** Tekstil kazası klibinde (347 kare, 3 fps):

    min_established_s   içeri kaybolma   saniye başına
          1,0                381              3,30
          2,0                315              2,73
          3,0                268              2,32
          5,0                189              1,64
          8,0                128              1,11

Hiçbir eşikte sinyal gürültünün üstüne çıkmıyor; kaza penceresi (t=47–55)
toplamın içinde ayırt edilemiyor. **Sebep tespit değil, iz parçalanması:**
~25 gerçek kişi için 500'den fazla kimlik üretiliyor ve her parçalanma bir
"kayboldu" gibi görünüyor. `gozcu.associate`'in açgözlü IoU eşleştirmesi bu
görüntüde (sürekli birbirini kapatan insanlar, 0,03 eşiğinin ürettiği
marjinal kutular) yetmiyor.

Bu yüzden alan **üretiliyor ama hiçbir karara bağlanmıyor**: ne
`loop.passes_floor`'a, ne yorumlayıcının prompt'una giriyor. Saniyede iki
kez "bir insan makineye kapıldı" diyen bir sinyal, bir güvenlik sisteminde
sessiz kalmaktan kötüdür.

Önce iz kalitesi düzelmeli (daha güçlü ilişkilendirme, ya da kimlik
gerektirmeyen bir formülasyon). O zaman bu alan hazır bekliyor olacak.

## Hız birimi: piksel/saniye SAHNEYE göre yalan söylüyor (26 Ağustos)

`velocities` bboks merkezleri arasındaki öklid mesafesini `dt`'ye bölüyordu —
birim piksel/saniye. Ölçüldü (k04, 98.8 sn, 10 pencere, 896x434 kare): genel
medyan 7 px/s, p90 32 px/s, tepe 541 px/s. Yönlendiricinin promptu "1.0 üstü
yürüyüşten hızlı" diyordu — iki basamak kaçık, yani K3 HER pencerede
tetikleniyordu.

Piksel bir sahne birimi değil, bir ÇÖZÜNÜRLÜK birimi: aynı yürüyüş 4K'da
1920x1080'e göre iki kat daha fazla piksel/s üretir, sahnede hiçbir şey
değişmeden. Kare GENİŞLİĞİ başına normalize etmek bunu çözüyor — "saniyede
kendi kare genişliğinin kaçta kaçı" sahne ve çözünürlükten bağımsız bir
sayı. Aynı k04 verisi normalize edilince: genel medyan 0.008, p90 0.036,
tepe 0.604 — ve pencere başına tepe değerler (0.238, 0.157, 0.100, 0.604,
0.293, 0.218, 0.149, 0.082, 0.193, 0.115) ARTIK ayırt edici: en yüksek ikisi
(0.604, 0.293) forkliftin çarptığı ve devrildiği pencereler.

`frame_size` verilmezse eski piksel/saniye davranışına düşülüyor — bir
ölçek UYDURMAK piksel kadar yanlış olurdu, o yüzden bu fallback yalnız
`frame_size` gerçekten bilinmediğinde devrede. Her tüketici retune edildi:
`gozcu.loop.FLOOR_VELOCITY` ve `gozcu.agents.orchestrator`'ın K3 eşiği — ikisi de
bu yeni birimde, gerekçeleri kendi dosyalarında.
"""

import math
from dataclasses import dataclass, field

from gozcu.perception.track import TrackedObject

__all__ = ["DEFAULT_VANISH_AFTER_S", "EDGE_MARGIN_PX", "MIN_ESTABLISHED_S",
           "FrameSignals", "SignalComputer", "compute_signals"]

#: Bir izin "yerleşmiş" sayılması için kaç saniye görülmüş olması gerektiği.
#:
#: Bu eşik OLMADAN `interior_vanished_tracks` kullanılamaz — ölçüldü: 347
#: karelik koşuda 614 içeri kaybolma, yani kare başına ~2. Sebep tespit
#: değil **iz parçalanması**: ~25 kişi için 500'den fazla kimlik üretiliyor
#: ve her parçalanma bir "kayboldu" gibi görünüyor.
#:
#: Yerleşme şartı bunu süzüyor: bir karede parlayıp sönen bir kutu iz
#: sayılmıyor, dolayısıyla kaybolamıyor da.
MIN_ESTABLISHED_S = 1.0

#: Bir kutunun "kenara değiyor" sayılması için kadraj sınırına olan en büyük
#: uzaklık. Sıfır olsaydı bir piksellik tespit gürültüsü, kadrajı terk eden
#: bir insanı "içeride kayboldu" diye okurdu — yani bir kaza uydururdu.
EDGE_MARGIN_PX = 24

#: Bir izin kaybolmuş sayılması için geçmesi gereken süre. 1,0 saniye: 1
#: fps'te eski davranışla birebir aynı (bir kare yokluk), 5 fps'te beş kare
#: ısrar istiyor. Kare hızından bağımsız olması **şart** — bu sayı bir
#: fiziksel süre, bir çıkarım penceresi değil.
DEFAULT_VANISH_AFTER_S = 1.0


@dataclass
class FrameSignals:
    velocities: dict[int, float] = field(default_factory=dict)
    vanished_tracks: list[int] = field(default_factory=list)
    person_count: int = 0
    person_count_delta: int = 0
    #: Kenara DEĞMEDEN kaybolan izler — `vanished_tracks`'in alt kümesi.
    #: Kadrajı terk eden bir insan sadece gitmiştir; kadrajın ortasında
    #: kaybolan bir insan bir şeyin İÇİNE girmiştir. Kaza sinyali bu.
    interior_vanished_tracks: list[int] = field(default_factory=list)


def _bbox_center(bbox: tuple[int, int, int, int]) -> tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def _touches_edge(bbox, frame_size, margin: int = EDGE_MARGIN_PX) -> bool:
    """Kutu kadrajın kenarına değiyor mu."""
    width, height = frame_size
    x1, y1, x2, y2 = bbox
    return (x1 <= margin or y1 <= margin
            or x2 >= width - margin or y2 >= height - margin)


def _by_id(frame_objects: list[TrackedObject]) -> dict[int, TrackedObject]:
    """Yalnız kimliği olan nesnelerin kimlik→nesne eşlemesi.

    Süzgeç sözlük kurulmadan ÖNCE: `None` anahtarlı bir sözlük sessizce
    çakışır, hata vermez ve hayalet hız üretir.
    """
    return {obj.track_id: obj for obj in frame_objects
            if obj.track_id is not None}


class SignalComputer:
    """Kare kare sinyal hesabı — `compute_signals`'ın artımlı karşılığı.

    Her `process` çağrısı tek bir karenin sinyalini üretiyor; durum kareler
    arasında taşınıyor. `run_pipeline`'ın akış algısı bunu kullanıyor.
    """

    def __init__(self, *, frame_size=None,
                 vanish_after_s=DEFAULT_VANISH_AFTER_S,
                 min_established_s=MIN_ESTABLISHED_S):
        self.frame_size = frame_size
        self.vanish_after_s = vanish_after_s
        self.min_established_s = min_established_s
        self._prev_by_id: dict[int, TrackedObject] = {}
        self._prev_person_count = 0
        self._prev_ts: float | None = None
        self._last_seen: dict[int, float] = {}
        self._last_bbox: dict[int, tuple] = {}
        self._first_seen: dict[int, float] = {}
        self._last_speed: dict[int, float] = {}
        self._reported_vanished: set[int] = set()

    def process(self, frame_objects: list[TrackedObject],
                timestamp_s: float) -> FrameSignals:
        current_by_id = _by_id(frame_objects)
        now = timestamp_s
        person_count = sum(1 for obj in frame_objects
                           if obj.class_name == "person")

        for track_id, obj in current_by_id.items():
            self._first_seen.setdefault(track_id, now)
            self._last_seen[track_id] = now
            self._last_bbox[track_id] = obj.bbox
            self._reported_vanished.discard(track_id)

        if self._prev_ts is None:
            self._prev_by_id = current_by_id
            self._prev_person_count = person_count
            self._prev_ts = now
            return FrameSignals(person_count=person_count)

        dt = now - self._prev_ts
        velocities: dict[int, float] = {}
        frame_width = self.frame_size[0] if self.frame_size is not None else None
        if dt > 0:
            for track_id, obj in current_by_id.items():
                if track_id in self._prev_by_id:
                    prev_center = _bbox_center(self._prev_by_id[track_id].bbox)
                    curr_center = _bbox_center(obj.bbox)
                    distance = math.hypot(
                        curr_center[0] - prev_center[0],
                        curr_center[1] - prev_center[1])
                    speed = distance / dt
                    if frame_width:
                        speed = speed / frame_width
                    velocities[track_id] = speed
                    self._last_speed[track_id] = speed

        vanished_tracks, interior_vanished = [], []
        for track_id, seen_at in self._last_seen.items():
            if track_id in current_by_id or track_id in self._reported_vanished:
                continue
            if now - seen_at >= self.vanish_after_s:
                vanished_tracks.append(track_id)
                self._reported_vanished.add(track_id)
                established = (seen_at - self._first_seen.get(track_id, seen_at)
                               >= self.min_established_s)
                if (self.frame_size is not None
                        and established
                        and track_id in self._last_bbox
                        and not _touches_edge(self._last_bbox[track_id],
                                              self.frame_size)):
                    interior_vanished.append(track_id)

        result = FrameSignals(
            velocities=velocities,
            vanished_tracks=vanished_tracks,
            interior_vanished_tracks=interior_vanished,
            person_count=person_count,
            person_count_delta=person_count - self._prev_person_count)

        self._prev_by_id = current_by_id
        self._prev_person_count = person_count
        self._prev_ts = now
        return result


def compute_signals(
    tracked_frames: list[list[TrackedObject]],
    frame_timestamps: list[float],
    vanish_after_s: float = DEFAULT_VANISH_AFTER_S,
    frame_size: tuple[int, int] | None = None,
    min_established_s: float = MIN_ESTABLISHED_S,
) -> list[FrameSignals]:
    """`frame_size` verilmezse `interior_vanished_tracks` üretilmiyor.

    Kadraj boyutu bilinmeden kenar da bilinemez ve tahmin etmek buradaki en
    tehlikeli şey olurdu: kadrajı terk eden her insan "içeride kayboldu"
    diye okunur, yani sistem **olmayan bir kaza uydurur.** Sıradan
    `vanished_tracks` boyuttan bağımsız ve üretilmeye devam ediyor.

    `velocities`'in birimi de `frame_size`'a bağlı. Verilirse hız **kare
    genişliği/saniye** — sahne ve çözünürlükten bağımsız, ölçüldü ve
    ayırt edici (bkz. modül başı notu). Verilmezse ESKİ piksel/saniye
    davranışına düşülüyor: bir ölçek uydurmak (`frame_size` yokken rastgele
    bir genişlik varsaymak) piksel birimiyle aynı yalanı başka bir sayıyla
    tekrar etmek olurdu.
    """
    signals: list[FrameSignals] = []
    prev_by_id: dict[int, TrackedObject] = {}
    prev_person_count = 0
    #: kimlik → en son görüldüğü zaman damgası. Kaybolma buradan hesaplanıyor,
    #: "önceki karede var mıydı"dan değil.
    last_seen: dict[int, float] = {}
    #: kimlik → en son görüldüğü kutu. İçeri kaybolma kararı bu kutuya
    #: bakıyor: iz kaybolduğunda EN SON nerede duruyordu.
    last_bbox: dict[int, tuple] = {}
    #: kimlik → ilk görüldüğü zaman. "Yerleşmiş iz" buradan hesaplanıyor.
    first_seen: dict[int, float] = {}
    #: kimlik → kaybolmadan önceki son hız. İçeri kaybolmanın ikinci şartı.
    last_speed: dict[int, float] = {}
    reported_vanished: set[int] = set()

    for i, frame_objects in enumerate(tracked_frames):
        current_by_id = _by_id(frame_objects)
        now = frame_timestamps[i]
        # Kimlikten BAĞIMSIZ: kimliksiz bir insan da karede duran bir insandır.
        person_count = sum(1 for obj in frame_objects
                           if obj.class_name == "person")

        for track_id, obj in current_by_id.items():
            first_seen.setdefault(track_id, now)
            last_seen[track_id] = now
            last_bbox[track_id] = obj.bbox
            # Geri dönen bir iz yeniden kaybolabilmeli.
            reported_vanished.discard(track_id)

        if i == 0:
            signals.append(FrameSignals(person_count=person_count))
            prev_by_id = current_by_id
            prev_person_count = person_count
            continue

        dt = now - frame_timestamps[i - 1]
        velocities: dict[int, float] = {}
        # `frame_size` varsa hız kare GENİŞLİĞİ'ne bölünüyor: piksel/saniye
        # sahneye göre yalan söylüyor (bkz. modül başı notu), genişlik
        # başına oran sahne ve çözünürlükten bağımsız.
        frame_width = frame_size[0] if frame_size is not None else None
        if dt > 0:
            for track_id, obj in current_by_id.items():
                if track_id in prev_by_id:
                    prev_center = _bbox_center(prev_by_id[track_id].bbox)
                    curr_center = _bbox_center(obj.bbox)
                    distance = math.hypot(
                        curr_center[0] - prev_center[0],
                        curr_center[1] - prev_center[1],
                    )
                    speed = distance / dt
                    if frame_width:
                        speed = speed / frame_width
                    velocities[track_id] = speed
                    last_speed[track_id] = speed

        # Eşiği YENİ aşan izler. `>` değil `>=` değil — kesin olarak aşan,
        # ve yalnız bir kez.
        vanished_tracks, interior_vanished = [], []
        for track_id, seen_at in last_seen.items():
            if track_id in current_by_id or track_id in reported_vanished:
                continue
            if now - seen_at >= vanish_after_s:
                vanished_tracks.append(track_id)
                reported_vanished.add(track_id)
                # İçeri kaybolma ÜÇ şartın birleşimi. Tek başına "kenara
                # değmeden kayboldu" kullanılamaz: ölçüldü, 347 karede 614
                # olay üretiyor ve sinyal değil gürültü oluyor.
                # İzin GÖRÜLDÜĞÜ süre — `now`'a kadar geçen süre değil.
                # `now` kaybolmanın bildirildiği an ve o zaten en az
                # `vanish_after_s` sonrası; oradan ölçmek tek karelik bir izi
                # bile "yerleşmiş" sayardı (ölçüldü: süzgeç hiçbir şey
                # süzmedi, 614 olay 614 kaldı).
                established = (seen_at - first_seen.get(track_id, seen_at)
                               >= min_established_s)
                if (frame_size is not None
                        and established
                        and track_id in last_bbox
                        and not _touches_edge(last_bbox[track_id], frame_size)):
                    interior_vanished.append(track_id)

        signals.append(
            FrameSignals(
                velocities=velocities,
                vanished_tracks=vanished_tracks,
                interior_vanished_tracks=interior_vanished,
                person_count=person_count,
                person_count_delta=person_count - prev_person_count,
            )
        )

        prev_by_id = current_by_id
        prev_person_count = person_count

    return signals
