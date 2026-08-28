"""Açıklamalı algı videosu — depoda ne varsa onu çizer, yeni ölçüm yapmaz."""

import subprocess

import numpy as np
import pytest

from gozcu.output.annotate import AnnotateError, annotate_run
from gozcu.core.models import Detection, Observation, Signals, WindowRecord
from gozcu.core.store import Store

FPS = 3.0

pytestmark = pytest.mark.skipif(
    subprocess.run(["which", "ffmpeg"], capture_output=True).returncode != 0,
    reason="ffmpeg yok")


def _frames(tmp_path, count=6):
    import cv2

    tmp_path.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        image = np.full((120, 200, 3), 40, dtype=np.uint8)
        cv2.imwrite(str(tmp_path / f"frame_{index:04d}.jpg"), image)
    return tmp_path


def _store_with(count=6):
    store = Store(":memory:")
    for index in range(count):
        store.save_observation(Observation(
            ts=index / FPS, signals=Signals(person_count=2),
            detections=[Detection(label="person", confidence=0.91,
                                  box=(10.0, 40.0, 60.0, 110.0), track_id=3),
                        Detection(label="forklift", confidence=0.77,
                                  box=(80.0, 30.0, 180.0, 110.0))]))
    store.save_window(WindowRecord(ts=0.0, end_ts=count / FPS, index=1,
                                   total=1, frames=count, person_peak=2,
                                   detections=count * 2,
                                   labels=["forklift", "person"],
                                   floor_passed=True, outcome="routed"))
    return store


def test_it_writes_a_playable_video_from_the_stored_observations(tmp_path):
    frames = _frames(tmp_path / "kareler")
    out = tmp_path / "acikla.mp4"
    result = annotate_run(frames, _store_with(), out, fps=FPS)
    assert result == out and out.exists() and out.stat().st_size > 0


def test_the_boxes_come_from_the_store_not_from_a_fresh_model_call(tmp_path):
    """Tanı aracı ikinci bir gerçeklik üretmemeli: çizilen şey koşunun
    GERÇEKTEN kaydettiği şey olmak zorunda."""
    import cv2

    from gozcu.output.annotate import _draw

    store = _store_with(1)
    image = np.full((120, 200, 3), 40, dtype=np.uint8)
    before = image.copy()
    drawn = _draw(image, store.observations()[0], store.window_records()[0],
                  1, 1)
    assert not np.array_equal(drawn, before), "hiçbir şey çizilmedi"
    assert cv2.imwrite(str(tmp_path / "x.jpg"), drawn)


def test_a_window_that_no_layer_looked_at_says_so_on_the_frame(tmp_path):
    """"Bakılmadı" ile "bakıldı, bir şey yoktu" karede de ayrı görünmeli."""
    from gozcu.output.annotate import OUTCOME_LABELS, _window_for

    store = Store(":memory:")
    store.save_window(WindowRecord(ts=0.0, end_ts=9.0, index=1, total=2,
                                   frames=3, floor_passed=False,
                                   outcome="skipped"))
    record = _window_for(4.0, store.window_records())
    assert record is not None and record.outcome == "skipped"
    assert OUTCOME_LABELS["skipped"] != OUTCOME_LABELS["routed"]


def test_the_last_frame_of_a_window_still_belongs_to_it():
    """Aralık kapalı: dışarıda bırakılırsa her pencerenin son karesi
    başlıksız kalır."""
    from gozcu.output.annotate import _window_for

    store = Store(":memory:")
    store.save_window(WindowRecord(ts=0.0, end_ts=9.0, index=1, total=1,
                                   frames=3, floor_passed=True,
                                   outcome="routed"))
    records = store.window_records()
    assert _window_for(9.0, records) is not None
    assert _window_for(9.5, records) is None


def test_no_frames_is_reported_not_silently_empty(tmp_path):
    """Sessizce boş bir dosya bırakmak, "algı hiçbir şey görmedi" ile
    "çizim üretilemedi"yi aynı şeye çevirirdi."""
    empty = tmp_path / "bos"
    empty.mkdir()
    with pytest.raises(AnnotateError):
        annotate_run(empty, Store(":memory:"), tmp_path / "x.mp4", fps=FPS)


def test_a_frame_with_no_observation_is_still_written(tmp_path):
    """Gözlemi olmayan kare atlanmıyor: atlanırsa video sessizce kısalır ve
    zaman çizelgesi kayar."""
    frames = _frames(tmp_path / "kareler", count=6)
    store = _store_with(3)               # yalnız ilk üç karenin gözlemi var
    out = annotate_run(frames, store, tmp_path / "y.mp4", fps=FPS)
    assert out.exists() and out.stat().st_size > 0
