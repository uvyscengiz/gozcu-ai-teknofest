#!/usr/bin/env python
"""
Aday YOLO(E) sinif/esik kombinasyonlarini gercek kliplerde olcer.

gozcu/config.py'deki mevcut olcum kulturunu takip eder: her klip icin
kac karede tespit var, hangi sinif ne siklikta yakalaniyor, yanlis
pozitif riski nedir -- hepsi tek tabloda.

Kullanim (proje kok dizininde):

  uv run python scripts/measure_yolo_classes.py ^
    --video "C:\yollar\yangin_klip.mp4=yangin (olay)" ^
    --video "C:\yollar\bos_hat.mp4=bos hat (kontrol)" ^
    --classes "person,forklift,truck,vehicle,fire,smoke,explosion,fallen person,collapsed shelf" ^
    --confidence 0.10,0.20,0.30 ^
    --annotate

PowerShell'de uzun satirlari `^` ile degil `` ` `` (backtick) ile bol,
ya da tek satirda yaz -- asagida tek satirlik ornek de var.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

# Proje kokunden calistirilacagi icin gozcu paketi dogrudan import edilebilir.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gozcu.frames import extract_frames  # noqa: E402
from gozcu.config import YOLO_MODEL_PATH, FRAME_FPS, FRAME_WIDTH  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--video",
        action="append",
        required=True,
        dest="videos",
        metavar="PATH=ETIKET",
        help="Video yolu ve etiketi, '=' ile ayrilmis. Birden fazla kez verilebilir. "
             "Kontrol klipleri icin etikete '(kontrol)' yaz -- rapor bunlari ayirir.",
    )
    p.add_argument(
        "--classes",
        required=True,
        help="Virgulle ayrilmis aday sinif listesi, orn: 'person,fire,smoke,collapsed shelf'",
    )
    p.add_argument(
        "--confidence",
        default="0.20",
        help="Virgulle ayrilmis esik degerleri, orn: '0.10,0.20,0.30' (varsayilan: 0.20)",
    )
    p.add_argument("--fps", type=float, default=None, help=f"Kare cikartma fps (varsayilan: config FRAME_FPS={FRAME_FPS})")
    p.add_argument("--width", type=int, default=None, help=f"Kare genisligi (varsayilan: config FRAME_WIDTH={FRAME_WIDTH})")
    p.add_argument(
        "--annotate",
        action="store_true",
        help="Her video/esik icin tespit iceren ilk birkac kareyi kutu cizili olarak "
             "'yolo_review/' klasorune kaydet (gozle kontrol icin).",
    )
    p.add_argument(
        "--annotate-max",
        type=int,
        default=5,
        help="Video basina kaydedilecek maksimum ornek kare (varsayilan: 5)",
    )
    p.add_argument("--keep-frames", action="store_true", help="Cikartilan kareleri isten sonra silme (varsayilan: siler)")
    return p.parse_args()


def parse_video_arg(raw: str) -> tuple[Path, str]:
    if "=" not in raw:
        raise SystemExit(f"--video icin 'YOL=ETIKET' formati bekleniyor, alinan: {raw!r}")
    path_str, label = raw.rsplit("=", 1)
    path = Path(path_str.strip('"'))
    if not path.exists():
        raise SystemExit(f"Video bulunamadi: {path}")
    return path, label.strip()


def main() -> None:
    args = parse_args()
    videos = [parse_video_arg(v) for v in args.videos]
    classes = [c.strip() for c in args.classes.split(",") if c.strip()]
    confidences = [float(c.strip()) for c in args.confidence.split(",") if c.strip()]

    from ultralytics import YOLO  # gec import: --help hizli calissin

    print(f"Model: {YOLO_MODEL_PATH}")
    print(f"Aday siniflar: {classes}")
    print(f"Esikler: {confidences}")
    print()

    model = YOLO(YOLO_MODEL_PATH)
    model.set_classes(classes)

    review_dir = Path("yolo_review")
    if args.annotate:
        review_dir.mkdir(exist_ok=True)

    rows = []  # (video_etiket, esik, toplam_kare, kare_ile_tespit, sinif_sayaci)

    for video_path, label in videos:
        tmp_dir = Path(tempfile.mkdtemp(prefix="gozcu_measure_"))
        print(f"[{label}] kareler cikartiliyor: {video_path.name} ...")
        frames = extract_frames(video_path, tmp_dir, fps=args.fps, width=args.width)
        print(f"[{label}] {len(frames)} kare cikartildi.")

        for conf in confidences:
            frames_with_detection = 0
            class_counter: Counter[str] = Counter()
            saved = 0

            for frame in frames:
                results = model.predict(source=str(frame.path), verbose=False, conf=conf)
                result = results[0]
                boxes = result.boxes
                if len(boxes) > 0:
                    frames_with_detection += 1
                    for box in boxes:
                        class_id = int(box.cls.item())
                        class_counter[result.names[class_id]] += 1

                    if args.annotate and saved < args.annotate_max:
                        safe_label = "".join(c if c.isalnum() else "_" for c in label)
                        out_path = review_dir / f"{video_path.stem}__{safe_label}__conf{conf}__f{frame.index:04d}.jpg"
                        annotated = result.plot()
                        import cv2  # local import, sadece --annotate ile gerekli
                        cv2.imwrite(str(out_path), annotated)
                        saved += 1

            rows.append((label, video_path.name, conf, len(frames), frames_with_detection, dict(class_counter)))

        if not args.keep_frames:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    print()
    print("=" * 100)
    print(f"{'Klip':30} {'Esik':>6} {'Kare/Tespit':>14}  Sinif dagilimi")
    print("=" * 100)
    for label, fname, conf, total, hit, class_counter in rows:
        ratio = f"{hit}/{total}"
        dist = ", ".join(f"{k}:{v}" for k, v in sorted(class_counter.items(), key=lambda kv: -kv[1])) or "(tespit yok)"
        print(f"{label[:30]:30} {conf:>6.2f} {ratio:>14}  {dist}")
    print("=" * 100)

    if args.annotate:
        print(f"\nGozle kontrol icin ornek kareler: {review_dir.resolve()}")


if __name__ == "__main__":
    main()
