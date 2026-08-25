"""Kimlik ilişkilendiricisinin testleri.

İlişkilendirici **kimlik üretir, kutu üretmez ve kutu elemez.** Bu ayrım
`gozcu/track.py`'ın sözleşmesi; buradaki testler ilişkilendiricinin o
sözleşmeyi kendi içinde de bozmadığını sınıyor.

Neden Ultralytics'in ByteTrack'i değil: tespit artık kayıt olduğu için
ByteTrack'in asıl değeri olan "düşük güvenli kutuyu kurtarma" makinesi bize
bir şey katmıyor — biz zaten hiçbir kutuyu düşürmüyoruz. Geriye yalnız kimlik
eşleştirmesi kalıyor ve onu kütüphanenin sürümden sürüme değişen iç
API'sine bağlamak (`BYTETracker.update` bu sürümde `Boxes` tipi istiyor,
`__init__` `frame_rate` almıyor) kırılgan bir bağımlılık olurdu.
"""

import pytest

from gozcu.associate import iou, iou_associator
from gozcu.detect import DetectedObject


def _box(bbox, label="person", conf=0.5):
    return DetectedObject(class_name=label, confidence=conf, bbox=bbox)


class TestIou:
    def test_identical_boxes(self):
        assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0

    def test_disjoint_boxes(self):
        assert iou((0, 0, 10, 10), (100, 100, 110, 110)) == 0.0

    def test_half_overlap(self):
        # 10x10 ve 10x10, yarısı örtüşüyor -> 50 / 150
        assert iou((0, 0, 10, 10), (5, 0, 15, 10)) == pytest.approx(1 / 3)

    def test_zero_area_box_does_not_divide_by_zero(self):
        assert iou((5, 5, 5, 5), (0, 0, 10, 10)) == 0.0


class TestAssociator:
    def test_every_box_gets_an_id(self):
        """Kimliksiz kutu bir eksiklik değil ama gereksiz de: eşleşmeyen
        kutu YENİ bir iz başlatır."""
        associate = iou_associator()
        ids = associate([_box((0, 0, 10, 10)), _box((50, 50, 60, 60))], {})
        assert ids == [1, 2]

    def test_same_box_keeps_its_id_across_frames(self):
        associate, state = iou_associator(), {}
        first = associate([_box((0, 0, 10, 10))], state)
        second = associate([_box((1, 0, 11, 10))], state)
        assert first == second == [1]

    def test_a_jump_too_far_starts_a_new_track(self):
        associate, state = iou_associator(), {}
        associate([_box((0, 0, 10, 10))], state)
        moved = associate([_box((500, 500, 510, 510))], state)
        assert moved == [2]

    def test_ids_never_collide_within_a_frame(self):
        associate = iou_associator()
        ids = associate([_box((0, 0, 10, 10)), _box((1, 1, 11, 11)),
                         _box((2, 2, 12, 12))], {})
        assert len(set(ids)) == 3

    def test_classes_do_not_cross_match(self):
        """Aynı yerdeki bir forklift, bir insanın kimliğini devralmamalı."""
        associate, state = iou_associator(), {}
        associate([_box((0, 0, 10, 10), label="person")], state)
        other = associate([_box((0, 0, 10, 10), label="forklift")], state)
        assert other == [2]

    def test_a_track_survives_a_short_gap(self):
        associate, state = iou_associator(buffer_frames=3), {}
        associate([_box((0, 0, 10, 10))], state)
        associate([], state)                       # kaybolan kare
        back = associate([_box((0, 0, 10, 10))], state)
        assert back == [1]

    def test_a_track_expires_after_the_buffer(self):
        associate, state = iou_associator(buffer_frames=1), {}
        associate([_box((0, 0, 10, 10))], state)
        associate([], state)
        associate([], state)
        back = associate([_box((0, 0, 10, 10))], state)
        assert back == [2]

    def test_greedy_match_prefers_the_better_overlap(self):
        """İki iz bir kutuya adaysa, kutu daha çok örtüşene gitmeli."""
        associate, state = iou_associator(), {}
        associate([_box((0, 0, 10, 10)), _box((20, 0, 30, 10))], state)
        ids = associate([_box((19, 0, 29, 10))], state)
        assert ids == [2]

    def test_returns_one_id_per_box_always(self):
        associate, state = iou_associator(), {}
        for boxes in ([], [_box((0, 0, 5, 5))],
                      [_box((0, 0, 5, 5)), _box((9, 9, 14, 14))]):
            assert len(associate(boxes, state)) == len(boxes)

    def test_empty_frame_returns_empty(self):
        assert iou_associator()([], {}) == []

    def test_state_is_not_shared_between_associators(self):
        a, b = iou_associator(), iou_associator()
        assert a([_box((0, 0, 10, 10))], {}) == [1]
        assert b([_box((0, 0, 10, 10))], {}) == [1]
