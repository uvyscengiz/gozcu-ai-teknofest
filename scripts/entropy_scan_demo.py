"""Piksel-entropi taramasının hızını ve bulduğu adayları göstermek için
küçük bir komut satırı aracı — testin kendisi değil, testin gözle görülür
kanıtı.

Kullanım:
    uv run python scripts/entropy_scan_demo.py <video_yolu>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gozcu.entropy_scan import scan_video


def main() -> None:
    if len(sys.argv) < 2:
        print("kullanım: entropy_scan_demo.py <video_yolu>")
        raise SystemExit(1)

    result = scan_video(sys.argv[1])

    print(f"video süresi     : {result.duration_s:.1f} s")
    print(f"örneklenen kare  : {result.sampled}")
    if result.scan_time_s > 0:
        print(f"tarama süresi    : {result.scan_time_s:.2f} s "
             f"({result.duration_s / result.scan_time_s:.0f}x gerçek zaman)")
    print(f"aday pencere     : {len(result.candidates)}")
    print()
    for window in result.candidates:
        print(f"  [{window.start_s:8.1f}s - {window.end_s:8.1f}s]  "
             f"z={window.score:.2f}")
    if not result.candidates:
        print("  (aday yok — video baştan sona görsel olarak durgun/tekdüze)")


if __name__ == "__main__":
    main()
