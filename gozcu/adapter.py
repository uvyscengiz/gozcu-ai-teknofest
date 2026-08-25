"""Algı katmanını ajan katmanının tiplerine bağlayan ince adaptör.

Algı katmanının ürettiği `TrackedObject` / `FrameSignals` dataclass'ları ile
ajanların konuştuğu `Observation` / `Detection` / `Signals` pydantic modelleri
arasındaki çeviri burada yaşıyor: iki dünya birbirinin tipini import etmeden
birbirine bakabiliyor.
"""

from gozcu.models import Detection, Observation, Signals

#: Kaç kişi bir "toplanma" sayılır. Üç, bir kalabalığın en küçük hâli — iki
#: kişi bir sohbet, üç kişi bir olayın etrafı.
GATHERING_THRESHOLD = 3


def to_observation(frame_ts: float, detections, frame_signals) -> Observation:
    """Donuk algı katmanının çıktısını ajan katmanının tipine çevirir.

    `gathering` `signals.py`'da hesaplanmıyor — burada kişi sayısından
    türetiliyor. Eşiği aşan kişi sayısı `gathering` sayılıyor; bu bir
    heuristik ve yönlendiriciye sadece bir sinyal olarak gidiyor, karar
    olarak değil.

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
            gathering=frame_signals.person_count >= GATHERING_THRESHOLD))
