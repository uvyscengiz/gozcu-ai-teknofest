"""Algı katmanını ajan katmanının tiplerine bağlayan ince adaptör.

Algı katmanının ürettiği `TrackedObject` / `FrameSignals` dataclass'ları ile
ajanların konuştuğu `Observation` / `Detection` / `Signals` pydantic modelleri
arasındaki çeviri burada yaşıyor: iki dünya birbirinin tipini import etmeden
birbirine bakabiliyor.
"""

import math
from statistics import median

from gozcu.models import Detection, Observation, Signals

#: `build_observations`'ın taban üstü sayılması için gereken MUTLAK kişi
#: sayısı tabanı. Tamamen boş bir sahnede beliren üç kişi, oranı sıfıra
#: çarpsa bile hâlâ bir toplanmadır — üç, bir kalabalığın en küçük hâli.
GATHERING_MIN_PEOPLE = 3

#: Bir kare, koşunun kendi medyan kişi sayısının kaç katını geçerse
#: "toplanma" sayılır. 1.5, k04 ölçümünde tabanı (medyan 4.0) aşırı
#: duyarlı yapmayacak, gerçek yakınsamayı (13-15) yine de yakalayacak
#: şekilde seçildi — bkz. `docs/05-decisions/decision-log.md`.
GATHERING_FACTOR = 1.5

#: `gathering` ile AYNI desen, kaybolan iz sayısı için: eşik koşunun kendi
#: medyanına göreli, sabit bir sayı değil. Ölçüldü (k04): pencere başına
#: 41-121 kaybolma, en kalabalık pencerelerde en yüksek — sebep tespit
#: değil iz parçalanması (0.03 eşikte nesne sayısıyla ölçekleniyor). Sabit
#: "1 kaybolan yeter" eşiği (yönlendiricinin eski K2'si) bu yüzden HER
#: pencerede tetikleniyordu.
VANISHED_FACTOR = 2.0
#: Medyan sıfırsa (çoğu karede hiç kaybolma yoksa) `VANISHED_FACTOR` de
#: sıfır verir ve tek bir kaybolan iz yeniden her şeyi tetikler — taban
#: bunu önlüyor: "olağandışı" için en az iki kaybolan iz gerekir, "bir
#: tane" değil.
MIN_VANISHED_UNUSUAL = 2

#: `person_count_delta`'nın mutlak değeri için aynı fikir. Ölçüldü (k04):
#: pencere başına delta 3-9 HER YERDE — sabit ±2 eşiği (yönlendiricinin
#: eski K4'ü) bu gürültü tabanının içinde kalıyor.
COUNT_DELTA_FACTOR = 1.5
#: Sıfır medyanda tek birimlik bir dalgalanmayı "olağandışı" saymamak için
#: taban.
MIN_COUNT_DELTA_UNUSUAL = 3


def to_observation(frame_ts: float, detections, frame_signals,
                   gathering: bool = False, vanished_unusual: bool = False,
                   count_change_unusual: bool = False) -> Observation:
    """Donuk algı katmanının çıktısını ajan katmanının tipine çevirir.

    `gathering`, `vanished_unusual`, `count_change_unusual` burada
    TÜRETİLMİYOR — parametre olarak geliyor ve olduğu gibi taşınıyor.
    Türetme `build_observations`'ın işi: o koşunun tamamına bakabiliyor, bu
    fonksiyon tek kareye bakıyor ve bir kuralın ne olduğunu bilmiyor.
    Üçünün de varsayılanı `False`: bir çağıran bu parametreleri es geçerse
    sessizce eski hataları tekrar etmez, açıkça "yok" der.

    `confidence` ve `track_id` `getattr` ile okunuyor: `detect_objects`
    takipsiz `DetectedObject` üretiyor, `track_video` ise `track_id` taşıyan
    `TrackedObject`. İkisi de aynı kapıdan geçebilmeli.

    **`track_id` `None` olabilir ve bu bir eksiklik değil.** `track_video`
    kimlik atanamayan kutuları da veriyor (25 Ağustos); `Detection.track_id`
    zaten `int | None` tipli, yani `None` sözleşmeyi bozmadan geçiyor. Burada
    bir süzgeç OLMAMALI: tespiti takip başarısızlığı yüzünden düşürmek bu
    değişiklikle kaldırılan şeyin ta kendisi.
    """
    return Observation(
        ts=frame_ts,
        detections=[
            Detection(label=tracked.class_name,
                      confidence=getattr(tracked, "confidence", 1.0),
                      box=tuple(float(v) for v in tracked.bbox),
                      track_id=getattr(tracked, "track_id", None))
            for tracked in detections],
        signals=Signals(
            velocities=dict(frame_signals.velocities),
            vanished_tracks=list(frame_signals.vanished_tracks),
            interior_vanished_tracks=list(
                getattr(frame_signals, 'interior_vanished_tracks', [])),
            person_count=frame_signals.person_count,
            person_count_delta=frame_signals.person_count_delta,
            gathering=gathering,
            vanished_unusual=vanished_unusual,
            count_change_unusual=count_change_unusual))


def build_observations(timestamps, detections_per_frame,
                       signals_per_frame) -> list[Observation]:
    """Bir koşunun bütün karelerini `Observation`'a çevirir ve `gathering`'i
    koşunun KENDİ tabanına göre türetir.

    Eski kural sabit bir sayıydı (kişi >= 3) ve k04 klibinde (296 kare,
    98,8 s) ölçüldü: karelerin %66'sını "toplanma" işaretliyordu — sahnenin
    kendi tabanı zaten medyan 4, tepesi 19 iken. Sabit bir eşik "bu bir
    fabrika" diyordu, "insanlar toplandı" değil.

    Yeni kural görelidir: `person_count >= max(GATHERING_MIN_PEOPLE,
    ceil(taban * GATHERING_FACTOR))`, taban bu koşunun TÜMÜNDEKİ kişi
    sayısının MEDYANI. Medyan bilerek — ortalama değil: dedektör 0.03
    eşikte çalışıyor ve sivri yanlış pozitifler üretiyor, medyan bunlara
    dayanıklı.

    **Bu tabanın sınırı dürüstçe yazılsın: medyan koşunun TAMAMI bilindiği
    için hesaplanabiliyor — `run()` bütün kareleri baştan çıkarıyor.**
    Gerçek bir canlı yayında böyle bir bütün yok; orada `gozcu.loop`'un
    top-K hareket bütçesinin taşıdığı aynı sınır geçerli olurdu: kayan bir
    pencere (ör. son N karenin medyanı) gerekirdi, çünkü klibin geleceği
    henüz görülmemiştir. Bu tasarım canlı yayına genelleşmiyor ve
    genelleşiyormuş gibi yazılmıyor.

    `vanished_unusual` ve `count_change_unusual` AYNI desenle türetiliyor:
    kaybolan iz sayısının ve kişi-sayısı değişiminin mutlak değerinin
    koşunun kendi medyanına göre belirgin fazlası (bkz. `VANISHED_FACTOR`,
    `COUNT_DELTA_FACTOR`). Yönlendiricinin K2 ve K4'ü artık bu bayraklara
    bakıyor, ham `vanished_tracks` doluluğuna ya da sabit bir `±N`'e değil
    — aynı sınırlama burada da geçerli: taban koşunun TAMAMI bilindiği için
    hesaplanıyor, canlı yayına genelleşmiyor.
    """
    counts = [signals.person_count for signals in signals_per_frame]
    baseline = median(counts) if counts else 0
    threshold = max(GATHERING_MIN_PEOPLE, math.ceil(baseline * GATHERING_FACTOR))

    vanished_counts = [len(signals.vanished_tracks)
                       for signals in signals_per_frame]
    vanished_baseline = median(vanished_counts) if vanished_counts else 0
    vanished_threshold = max(MIN_VANISHED_UNUSUAL,
                             math.ceil(vanished_baseline * VANISHED_FACTOR))

    delta_magnitudes = [abs(signals.person_count_delta)
                        for signals in signals_per_frame]
    delta_baseline = median(delta_magnitudes) if delta_magnitudes else 0
    delta_threshold = max(MIN_COUNT_DELTA_UNUSUAL,
                          math.ceil(delta_baseline * COUNT_DELTA_FACTOR))

    return [
        to_observation(
            ts, detections, signals,
            gathering=signals.person_count >= threshold,
            vanished_unusual=len(signals.vanished_tracks) >= vanished_threshold,
            count_change_unusual=(abs(signals.person_count_delta)
                                  >= delta_threshold))
        for ts, detections, signals in zip(
            timestamps, detections_per_frame, signals_per_frame, strict=True)
    ]
