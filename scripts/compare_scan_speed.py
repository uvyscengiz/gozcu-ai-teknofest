"""`gozcu.motion` (var olan triyaj) ile `gozcu.entropy_scan` (yeni ön-tarama)
AYNI ŞEY DEĞİL — biri diğerinin "daha hızlı versiyonu" değil, ikisi
pipeline'ın FARKLI noktalarında çalışıyor. Bu script farkı sayılarla
gösteriyor: `motion.py`'nin sinyali kendisi ucuz (~2 ms/kare) ama o kareler
zaten ffmpeg + YOLO ile üretilmiş OLMAK ZORUNDA — asıl bedel oradadır.
`entropy_scan.py` o bedeli hiç ödemeden, ham videodan seyrek örnekleyerek
çalışıyor.

Kullanım:
    uv run python scripts/compare_scan_speed.py <video_yolu>
"""

import sys
import time
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gozcu.frames import extract_frames
from gozcu.track import track_video
from gozcu.motion import build_motion_for
from gozcu.entropy_scan import scan_video


def main() -> None:
    if len(sys.argv) < 2:
        print("kullanım: compare_scan_speed.py <video_yolu>")
        raise SystemExit(1)

    video_path = sys.argv[1]

    print("=" * 70)
    print("ESKİ YOL: ffmpeg kare çıkarma -> YOLO tespit -> motion.py triyajı")
    print("=" * 70)

    t0 = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="cmp-frames-") as out_dir:
        frames = extract_frames(video_path, out_dir)
        t1 = time.monotonic()
        print(f"  1) ffmpeg kare çıkarma   : {t1 - t0:6.2f} s  "
             f"({len(frames)} kare, {(t1 - t0) / max(len(frames), 1) * 1000:.1f} ms/kare)")

        tracked = track_video([f.path for f in frames])
        t2 = time.monotonic()
        n_det = sum(len(t) for t in tracked)
        print(f"  2) YOLO tespit + takip   : {t2 - t1:6.2f} s  "
             f"({(t2 - t1) / max(len(frames), 1) * 1000:.1f} ms/kare, {n_det} tespit)")

        motion_for = build_motion_for(
            [f.timestamp_s for f in frames], [f.path for f in frames])
        t3 = time.monotonic()
        print(f"  3) motion.py triyajı     : {t3 - t2:6.2f} s  "
             f"({(t3 - t2) / max(len(frames), 1) * 1000:.1f} ms/kare)")

    old_total = t3 - t0
    print(f"  ESKİ YOL TOPLAM (VLM/LLM çağrıları HARİÇ): {old_total:.2f} s")

    print()
    print("=" * 70)
    print("YENİ YOL: entropy_scan.py (ffmpeg yok, YOLO yok)")
    print("=" * 70)

    t4 = time.monotonic()
    result = scan_video(video_path)
    t5 = time.monotonic()
    new_total = t5 - t4
    print(f"  entropy_scan.scan_video  : {new_total:6.2f} s  "
         f"({result.sampled} örnek kare, {len(result.candidates)} aday pencere)")

    print()
    print("=" * 70)
    print("KARŞILAŞTIRMA")
    print("=" * 70)
    print(f"  video süresi              : {result.duration_s:.1f} s")
    print(f"  eski yol (çıkarma+YOLO+triyaj) : {old_total:8.2f} s")
    print(f"  yeni yol (entropy_scan)        : {new_total:8.2f} s")
    if new_total > 0:
        print(f"  hızlanma                       : {old_total / new_total:8.1f}x")
    print()
    print("  1 saatlik videoya doğrusal ölçekleyince (kabaca):")
    scale = 3600.0 / max(result.duration_s, 1e-6)
    print(f"    eski yol  ~ {old_total * scale / 60:6.1f} dk")
    print(f"    yeni yol  ~ {new_total * scale:6.1f} s")


if __name__ == "__main__":
    main()
