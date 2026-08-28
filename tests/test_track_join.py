"""Takip artık kutuları ELEYEMEZ — tespit kayıt, kimlik bir JOIN.

25 Ağustos'ta `if box.id is None: continue` kaldırıldı ve sözleşme "tespit
kayıttır, takip yalnız kimlik ekler" oldu. Süzgeç gerçekten kaldırıldı ama
**kayıp oradan gelmiyordu**: Ultralytics'in `model.track()` çağrısı, kare için
en az bir onaylı iz üretirse `results.boxes`'ı iz alt kümesiyle DEĞİŞTİRİYOR.
Kutular bizim döngümüz onları görmeden yok oluyordu.

Ölçüldü (tekstil kazası, 116 kare): takip 41 karede kutu eledi, 0 karede
ekledi; conf 0,03'te yok edilen pay %59'a çıkıyor.

Bu testler o vetonun geri gelemeyeceğini garanti ediyor. Hepsi sahte bir
tespit edici ve sahte bir ilişkilendirici ile koşuyor: gerçek YOLO yok, gerçek
ByteTrack yok — sınanan şey **sözleşme**, kütüphane değil.
"""

import pytest

from gozcu.perception.detect import DetectedObject
from gozcu.perception.track import TrackedObject, attach_track_ids


def _box(label="person", conf=0.5, bbox=(0, 0, 10, 10)):
    return DetectedObject(class_name=label, confidence=conf, bbox=bbox)


class TestAttachTrackIds:
    """Kimlik ekleme: kutu sayısı ASLA değişmez."""

    def test_every_detection_survives_even_with_no_ids(self):
        frames = [[_box(), _box()], [_box()]]
        out = attach_track_ids(frames, associate=lambda boxes, state: [None] * len(boxes))
        assert [len(f) for f in out] == [2, 1]

    def test_ids_are_attached_when_association_succeeds(self):
        frames = [[_box(), _box()]]
        out = attach_track_ids(frames, associate=lambda boxes, state: [7, 9])
        assert [o.track_id for o in out[0]] == [7, 9]

    def test_partial_association_keeps_unmatched_boxes(self):
        """En kritik test: ilişkilendirici bir kutuya kimlik veremezse
        o kutu DÜŞMEZ, `track_id=None` ile geçer."""
        frames = [[_box(), _box(), _box()]]
        out = attach_track_ids(frames, associate=lambda boxes, state: [1, None, 3])
        assert len(out[0]) == 3
        assert [o.track_id for o in out[0]] == [1, None, 3]

    def test_detection_fields_are_preserved(self):
        frames = [[_box(label="forklift", conf=0.31, bbox=(1, 2, 3, 4))]]
        out = attach_track_ids(frames, associate=lambda boxes, state: [5])
        obj = out[0][0]
        assert (obj.class_name, obj.confidence, obj.bbox) == ("forklift", 0.31, (1, 2, 3, 4))
        assert isinstance(obj, TrackedObject)

    def test_associator_returning_too_few_ids_is_refused(self):
        """Sessizce hizalamak kimlikleri YANLIŞ kutulara bağlardı — ve bu
        hatalı hız hesabı olarak, hiçbir uyarı vermeden ortaya çıkardı."""
        frames = [[_box(), _box()]]
        with pytest.raises(ValueError):
            attach_track_ids(frames, associate=lambda boxes, state: [1])

    def test_associator_failure_does_not_drop_the_frame(self):
        """İlişkilendirici patlarsa kare kimliksiz geçer, kaybolmaz.

        Takip katmanının bir arızası tespit kanıtını yok edemez — bu
        modülün varlık sebebi tam olarak bu.
        """
        def explode(boxes, state):
            raise RuntimeError("tracker patladı")

        out = attach_track_ids([[_box(), _box()]], associate=explode)
        assert len(out[0]) == 2
        assert [o.track_id for o in out[0]] == [None, None]

    def test_empty_frames_stay_empty(self):
        out = attach_track_ids([[], [_box()]], associate=lambda b, s: [None] * len(b))
        assert [len(f) for f in out] == [0, 1]

    def test_state_is_threaded_across_frames(self):
        """İlişkilendirici kareler arasında durum taşıyabilmeli, yoksa
        hiçbir kimlik iki kare boyunca aynı kalamaz."""
        seen = []

        def associate(boxes, state):
            seen.append(dict(state))
            state["n"] = state.get("n", 0) + 1
            return [None] * len(boxes)

        attach_track_ids([[_box()], [_box()], [_box()]], associate=associate)
        assert seen == [{}, {"n": 1}, {"n": 2}]


class TestNoVeto:
    """Sözleşmenin kendisi: çıktı kutu sayısı = girdi kutu sayısı."""

    @pytest.mark.parametrize("shape", [[0], [1], [5], [3, 0, 7], [2, 2, 2]])
    def test_box_count_is_invariant(self, shape):
        frames = [[_box() for _ in range(n)] for n in shape]
        for associate in (lambda b, s: [None] * len(b),
                          lambda b, s: list(range(len(b))),
                          lambda b, s: [None if i % 2 else i
                                        for i in range(len(b))]):
            out = attach_track_ids(frames, associate=associate)
            assert [len(f) for f in out] == shape
