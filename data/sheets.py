#!/usr/bin/env python3
"""Tek bir video icin 4x2 kontak sayfasi uretir — bir kesiti yakindan incelemek icin.
Toplu etiketleme index-sheets.py ile yapilir; bu betik tek tek bakmak icindir.

Kareler ffmpeg'in hizli seek'i ile alinir (fps filtresi tum videoyu decode ederdi),
dosseme PIL ile yapilir (bu ffmpeg derlemesinde tile/drawtext yok).

Kullanim: ./sheets.py <video.mp4> [<video.mp4> ...]   ya da argumansiz: tum kesitler
"""
import subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "thumbs"
OUT.mkdir(exist_ok=True)
CELL, COLS, ROWS = (400, 225), 4, 2


def dur(f):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(f)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def sheet(f):
    out = OUT / f"{f.stem}.jpg"
    if out.exists():
        return out, True
    d = dur(f)
    n = COLS * ROWS
    tmpdir = ROOT / ".th"
    tmpdir.mkdir(exist_ok=True)
    tiles = []
    for i in range(n):
        t = tmpdir / f"{f.stem}-{i}.png"
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{d * (i + 0.5) / n:.2f}",
             "-i", str(f), "-frames:v", "1", "-vf",
             f"scale={CELL[0]}:{CELL[1]}:force_original_aspect_ratio=decrease,"
             f"pad={CELL[0]}:{CELL[1]}:(ow-iw)/2:(oh-ih)/2:black", str(t)],
            capture_output=True)
        if t.exists():
            tiles.append(Image.open(t).convert("RGB"))
    if not tiles:
        return out, False
    sh = Image.new("RGB", (COLS * CELL[0], ROWS * CELL[1]), (0, 0, 0))
    for i, im in enumerate(tiles):
        sh.paste(im, ((i % COLS) * CELL[0], (i // COLS) * CELL[1]))
    sh.save(out, quality=85)
    for i in range(n):
        (tmpdir / f"{f.stem}-{i}.png").unlink(missing_ok=True)
    return out, True


targets = [Path(a) for a in sys.argv[1:]] or \
          [f for f in sorted((ROOT / "clips").rglob("*.mp4")) if "_elenen" not in f.parts]
print(f"{len(targets)} dosya")
with ThreadPoolExecutor(max_workers=6) as ex:
    bad = sum(0 if ok else 1 for _, ok in ex.map(sheet, targets))
print(f"tamam ({bad} hata)")
