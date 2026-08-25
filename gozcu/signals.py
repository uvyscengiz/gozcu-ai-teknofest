"""Kare başına türetilen sinyaller — hangisi kimlik ister, hangisi istemez.

`gozcu.track` artık kimliksiz kutuları da veriyor (`track_id is None`). Bu
modülün işi o iki dünyayı ayırmak:

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
"""

import math
from dataclasses import dataclass, field

from gozcu.track import TrackedObject


@dataclass
class FrameSignals:
    velocities: dict[int, float] = field(default_factory=dict)
    vanished_tracks: list[int] = field(default_factory=list)
    person_count: int = 0
    person_count_delta: int = 0


def _bbox_center(bbox: tuple[int, int, int, int]) -> tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def _by_id(frame_objects: list[TrackedObject]) -> dict[int, TrackedObject]:
    """Yalnız kimliği olan nesnelerin kimlik→nesne eşlemesi.

    Süzgeç sözlük kurulmadan ÖNCE: `None` anahtarlı bir sözlük sessizce
    çakışır, hata vermez ve hayalet hız üretir.
    """
    return {obj.track_id: obj for obj in frame_objects
            if obj.track_id is not None}


def compute_signals(
    tracked_frames: list[list[TrackedObject]],
    frame_timestamps: list[float],
) -> list[FrameSignals]:
    signals: list[FrameSignals] = []
    prev_by_id: dict[int, TrackedObject] = {}
    prev_person_count = 0

    for i, frame_objects in enumerate(tracked_frames):
        current_by_id = _by_id(frame_objects)
        # Kimlikten BAĞIMSIZ: kimliksiz bir insan da karede duran bir insandır.
        person_count = sum(1 for obj in frame_objects
                           if obj.class_name == "person")

        if i == 0:
            signals.append(FrameSignals(person_count=person_count))
            prev_by_id = current_by_id
            prev_person_count = person_count
            continue

        dt = frame_timestamps[i] - frame_timestamps[i - 1]
        velocities: dict[int, float] = {}
        if dt > 0:
            for track_id, obj in current_by_id.items():
                if track_id in prev_by_id:
                    prev_center = _bbox_center(prev_by_id[track_id].bbox)
                    curr_center = _bbox_center(obj.bbox)
                    distance = math.hypot(
                        curr_center[0] - prev_center[0],
                        curr_center[1] - prev_center[1],
                    )
                    velocities[track_id] = distance / dt

        vanished_tracks = [tid for tid in prev_by_id if tid not in current_by_id]

        signals.append(
            FrameSignals(
                velocities=velocities,
                vanished_tracks=vanished_tracks,
                person_count=person_count,
                person_count_delta=person_count - prev_person_count,
            )
        )

        prev_by_id = current_by_id
        prev_person_count = person_count

    return signals
