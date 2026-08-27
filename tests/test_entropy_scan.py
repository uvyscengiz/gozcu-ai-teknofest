"""Küresel piksel-entropi ön-taraması (bkz. `gozcu/entropy_scan.py`).

Bu dosyanın koruduğu tek cümle: sakin bir videonun ortasına gömülü kısa,
kaotik bir leke (patlama/toz benzeri) aday pencereler arasında ÇIKMALI —
sayaç ya da periyot değil, piksel dağılımının kendisi seçmeli.
"""

import cv2
import numpy as np

from gozcu.entropy_scan import combine_entropy, entropy_of_gray, scan_video


def _quiet_frames(count, size=64, value=120):
    return [np.full((size, size), value, np.uint8) for _ in range(count)]


def _chaotic_frames(count, size=64, seed=0):
    rng = np.random.default_rng(seed)
    return [rng.integers(0, 256, (size, size), dtype=np.uint8)
           for _ in range(count)]


def _write_video(path, frames, fps=10):
    height, width = frames[0].shape[:2]
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                             fps, (width, height), isColor=True)
    for frame in frames:
        writer.write(cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR))
    writer.release()
    return path


# -- entropi ölçümünün kendisi -------------------------------------------

def test_entropy_is_low_for_a_flat_image():
    flat = np.full((80, 80), 120, np.uint8)
    assert entropy_of_gray(flat) == 0.0


def test_entropy_is_high_for_noise():
    rng = np.random.default_rng(0)
    noise = rng.integers(0, 256, (80, 80), dtype=np.uint8)
    # 64 kova, teorik tavan log2(64) = 6 bit; gürültü ona yakın olmalı.
    assert entropy_of_gray(noise) > 5.0


# -- birleşim: mutlak zirveye değil kendi ortalamasına göre ---------------

def test_combine_uses_zscore_not_peak_normalize():
    """Dar aralıklı ama sabit-yüksek bir kanal (gerçek kare entropisi gibi)
    zirveye bölünseydi her örnek 1,0'a yakın kalır, sinyal ölürdü. Z-skorda
    sabit bir kanal sıfıra yakın kalmalı, tek sapan örnek öne çıkmalı."""
    frame_entropy = [5.60, 5.61, 5.59, 5.62, 5.60]  # neredeyse sabit
    diff_entropy = [None, 1.2, 1.3, 1.2, 4.5]        # son örnek sıçrıyor
    combined = combine_entropy(frame_entropy, diff_entropy)
    assert int(np.argmax(combined)) == 4
    # sabit kanalın kendisi hiçbir örneği "1,0'a yakın" göstermemeli
    assert all(c < 2.0 for i, c in enumerate(combined) if i != 4)


# -- uçtan uca: sentetik video --------------------------------------------

def test_scan_finds_the_chaotic_burst(tmp_path):
    fps = 10
    quiet_before = _quiet_frames(50)   # 0-5 s
    burst = _chaotic_frames(20)         # 5-7 s
    quiet_after = _quiet_frames(50)     # 7-12 s
    frames = quiet_before + burst + quiet_after
    path = _write_video(tmp_path / "synthetic.mp4", frames, fps=fps)

    result = scan_video(path, sample_hz=fps, window_s=1.0, z_thresh=1.5,
                        merge_gap_s=0.5, pad_s=0.0)

    burst_start_s, burst_end_s = 50 / fps, 70 / fps
    hit = [w for w in result.candidates
          if w.start_s < burst_end_s and w.end_s > burst_start_s]
    assert hit, (f"patlama aralığı ({burst_start_s}-{burst_end_s}s) "
                f"adaylar arasında yok: {result.candidates}")


def test_scan_returns_empty_for_a_still_video(tmp_path):
    frames = _quiet_frames(30)
    path = _write_video(tmp_path / "still.mp4", frames, fps=10)
    result = scan_video(path, sample_hz=10)
    assert result.candidates == []


def test_scan_is_fast_relative_to_duration(tmp_path):
    frames = _quiet_frames(150)  # 15 s @ 10fps
    path = _write_video(tmp_path / "quiet.mp4", frames, fps=10)
    result = scan_video(path, sample_hz=10)
    assert result.scan_time_s < result.duration_s


def test_scan_on_missing_file_does_not_raise(tmp_path):
    result = scan_video(tmp_path / "yok.mp4")
    assert result.candidates == []
    assert result.sampled == 0
