"""Algı katmanı — takip **zenginleştirir**, süzmez.

Bu dosyanın koruduğu tek cümle: *tespit kayıttır.* BoTSORT 1 fps'te kimlik
atayamıyor (ölçüldü: raf çökmesi klibinde 6 kutu, 0 kimlik) ve eski kod
kimliksiz kutuyu atıyordu — yani takip katmanının başarısızlığı tespit
katmanının kanıtını siliyordu.

Yeni sözleşme iki parçalı ve ikisi de burada sınanıyor:

- `track_video` **bütün** kutuları veriyor; kimlik varsa iliştiriyor.
- `compute_signals` kimlik isteyen hesapları (hız, kaybolan iz) kimliği
  olanlarla sınırlıyor, kimlik istemeyeni (kişi sayısı) sınırlamıyor.

Ve iki sessiz tuzak: `None` anahtarlı sözlük çakışması (hayalet hız) ile
`kaybolan=[None]`'ın yönlendiricinin özetine sızması.
"""

from unittest.mock import patch

from gozcu.adapter import to_observation
from gozcu.signals import FrameSignals, compute_signals
from gozcu.track import TrackedObject, track_video


# -- YOLO ikizi ---------------------------------------------------------------

class _Scalar:
    """`box.cls` / `box.conf` / `box.id`'nin `.item()` arayüzü."""

    def __init__(self, value):
        self._value = value

    def item(self):
        return self._value


class _Row:
    """`box.xyxy[0]`'ın `.tolist()` arayüzü."""

    def __init__(self, values):
        self._values = list(values)

    def tolist(self):
        return list(self._values)


class _Box:
    def __init__(self, class_id=0, confidence=0.5, xyxy=(0, 0, 10, 10),
                 track_id=None):
        self.cls = _Scalar(class_id)
        self.conf = _Scalar(confidence)
        self.xyxy = [_Row(xyxy)]
        self.id = None if track_id is None else _Scalar(track_id)


class _Result:
    def __init__(self, boxes):
        self.boxes = boxes
        self.names = {0: "person", 1: "forklift"}


class _FakeYOLO:
    """`model.track()` her karede sıradaki kutu listesini döndürür."""

    def __init__(self, frames):
        self._frames = list(frames)
        self.calls = 0

    def __call__(self, *args, **kwargs):
        return self

    def set_classes(self, names):
        self.names = names

    def track(self, *args, **kwargs):
        boxes = self._frames[self.calls]
        self.calls += 1
        return [_Result(boxes)]


def _run_track(frames_of_boxes):
    model = _FakeYOLO(frames_of_boxes)
    with (patch("gozcu.track.YOLO", model),
          patch("gozcu.track.cv2.imread", return_value=object())):
        return track_video([f"frame_{i}.jpg"
                            for i in range(len(frames_of_boxes))])


# -- takip süzgeç değil -------------------------------------------------------

def test_a_box_without_a_track_id_survives_tracking():
    """Eski kod `if box.id is None: continue` diyordu ve ölçülen sonuç şuydu:
    6 kutu bulundu, 0'ı ajan katmanına ulaştı."""
    tracked = _run_track([[_Box(class_id=1, confidence=0.31, xyxy=(1, 2, 3, 4),
                                track_id=None)]])
    assert len(tracked[0]) == 1
    only = tracked[0][0]
    assert only.track_id is None
    assert only.class_name == "forklift"
    assert only.bbox == (1, 2, 3, 4)


def test_tracking_still_attaches_the_id_when_it_has_one():
    """Zenginleştirme kaybolmuyor: kimlik varsa taşınıyor."""
    tracked = _run_track([[_Box(track_id=7)]])
    assert tracked[0][0].track_id == 7


def test_tracked_and_untracked_boxes_come_back_from_the_same_frame():
    tracked = _run_track([[_Box(track_id=3), _Box(track_id=None)]])
    assert [obj.track_id for obj in tracked[0]] == [3, None]


def test_the_untracked_box_reaches_the_agent_layer_through_the_adapter():
    """`models.Detection.track_id` zaten `int | None`; adaptör süzmemeli."""
    observation = to_observation(
        1.0,
        [TrackedObject(class_name="person", confidence=0.4, bbox=(0, 0, 4, 4),
                       track_id=None)],
        FrameSignals(person_count=1))
    assert len(observation.detections) == 1
    assert observation.detections[0].track_id is None


# -- kimlik isteyen / istemeyen hesaplar --------------------------------------

def _person(track_id=None, bbox=(0, 0, 10, 10)):
    return TrackedObject(class_name="person", confidence=0.5, bbox=bbox,
                         track_id=track_id)


def test_person_count_counts_people_without_a_track_id():
    """Kişi sayısı kimlik istemiyor: kimliksiz bir insan da karede durur."""
    signals = compute_signals([[_person(), _person()]], [0.0])
    assert signals[0].person_count == 2


def test_person_count_delta_follows_untracked_people_too():
    signals = compute_signals([[_person()], [_person(), _person()]],
                              [0.0, 1.0])
    assert [s.person_count for s in signals] == [1, 2]
    assert signals[1].person_count_delta == 1


def test_velocities_ignore_objects_without_a_track_id():
    """Hız "aynı nesne iki karede nerede" sorusudur; kimliksiz kutuyla
    cevaplanamaz."""
    signals = compute_signals(
        [[_person(bbox=(0, 0, 10, 10))], [_person(bbox=(100, 0, 110, 10))]],
        [0.0, 1.0])
    assert signals[1].velocities == {}


def test_two_untracked_objects_in_one_frame_do_not_collide_into_one_entry():
    """`{obj.track_id: obj}` naif hâliyle `None` anahtarlarını ÇAKIŞTIRIR.

    Çakışma sessiz: karedeki bütün kimliksiz nesneler tek girdiye iner ve
    iki kare arasında **farklı fiziksel nesneler** arasında hayalet bir hız
    hesaplanır. Burada iki kimliksiz nesne yer değiştiriyor; süzgeç
    kalkarsa `velocities[None]` belirir.
    """
    frames = [[_person(bbox=(0, 0, 10, 10)), _person(bbox=(500, 0, 510, 10))],
              [_person(bbox=(500, 0, 510, 10)), _person(bbox=(0, 0, 10, 10))]]
    signals = compute_signals(frames, [0.0, 1.0])
    assert signals[1].velocities == {}
    assert None not in signals[1].velocities
    assert signals[1].person_count == 2


def test_vanished_tracks_never_contain_none():
    """`kaybolan=[None]` yönlendiricinin özetine düşer ve model olmayan bir
    izin kaybolduğunu okur."""
    frames = [[_person(track_id=None), _person(track_id=4)],
              [_person(track_id=4)]]
    signals = compute_signals(frames, [0.0, 1.0])
    assert signals[1].vanished_tracks == []
    assert None not in signals[1].vanished_tracks


def test_a_real_track_still_vanishes_when_it_leaves_the_frame():
    """Süzgeç kaybolan iz tespitini öldürmüyor — sadece `None`'ı dışarıda
    tutuyor."""
    signals = compute_signals([[_person(track_id=9)], [_person(track_id=None)]],
                              [0.0, 1.0])
    assert signals[1].vanished_tracks == [9]


def test_a_tracked_object_still_gets_its_velocity():
    signals = compute_signals(
        [[_person(track_id=2, bbox=(0, 0, 10, 10))],
         [_person(track_id=2, bbox=(0, 8, 10, 18))]],
        [0.0, 2.0])
    assert signals[1].velocities == {2: 4.0}
