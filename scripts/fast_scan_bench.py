"""`run_pipeline(..., fast_scan=True)` gerçekten ne kadar kazandırıyor —
kare çıkarma + YOLO adımlarını, tüm video ile yalnız aday pencereler
arasında ölçerek karşılaştırır. LLM/VLM çağrısı YAPMAZ (ağa çıkmaz, ücretsiz
ve hızlı çalışır) — kıyaslanan şey algı katmanı (`extract_frames` + YOLO),
zaten videonun uzunluğuyla doğrusal büyüyen ve `motion.py`'nin bedelsiz
triyajından ÖNCE gelen kısım.

Kullanım:
    uv run python scripts/fast_scan_bench.py <video_yolu>
"""

import sys
import time
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gozcu.entropy_scan import scan_video
from gozcu.frames import extract_frames, extract_frames_for_windows
from gozcu.track import track_video


def _run(label, extract_fn):
    with tempfile.TemporaryDirectory(prefix="fastscan-bench-") as out_dir:
        t0 = time.monotonic()
        frames = extract_fn(out_dir)
        t1 = time.monotonic()
        tracked = track_video([f.path for f in frames])
        t2 = time.monotonic()
    n_det = sum(len(t) for t in tracked)
    print(f"{label}")
    print(f"  kare        : {len(frames)}")
    print(f"  çıkarma     : {t1 - t0:6.2f} s")
    print(f"  YOLO tespit : {t2 - t1:6.2f} s  ({n_det} tespit)")
    print(f"  TOPLAM      : {t2 - t0:6.2f} s")
    return t2 - t0, len(frames)


def main() -> None:
    if len(sys.argv) < 2:
        print("kullanım: fast_scan_bench.py <video_yolu>")
        raise SystemExit(1)
    video_path = sys.argv[1]

    scan = scan_video(video_path)
    print(f"entropi ön-taraması: {scan.scan_time_s:.2f} s, "
         f"{len(scan.candidates)} aday pencere "
         f"(video {scan.duration_s:.1f} s)")
    for w in scan.candidates:
        print(f"    [{w.start_s:7.1f}s - {w.end_s:7.1f}s]  z={w.score:.2f}")
    print()

    old_total, old_frames = _run(
        "ESKİ (fast_scan=False, tüm video)",
        lambda out_dir: extract_frames(video_path, out_dir))
    print()

    windows = [(w.start_s, w.end_s) for w in scan.candidates]
    new_total, new_frames = _run(
        "YENİ (fast_scan=True, yalnız aday pencereler)",
        lambda out_dir: extract_frames_for_windows(video_path, out_dir, windows))

    print()
    print("=" * 60)
    print(f"kare azalması : {old_frames} -> {new_frames} "
         f"(%{100 * (1 - new_frames / max(old_frames, 1)):.0f} daha az)")
    if new_total > 0:
        print(f"hızlanma      : {old_total / new_total:.1f}x "
             f"(+ {scan.scan_time_s:.2f}s ön-tarama dahil)")


if __name__ == "__main__":
    main()
