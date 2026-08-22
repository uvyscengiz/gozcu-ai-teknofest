#!/usr/bin/env python3
"""Her derleme icin tek bir indeks tabakasi uretir: kesit basina 1 temsili kare,
uzerine kesit numarasi ve suresi yazilir. Etiketleme bu tabakalara bakilarak yapilir.

Kareler ffmpeg ile cikarilir, etiketleme ve dosseme PIL ile yapilir
(Homebrew ffmpeg derlemesinde drawtext filtresi yok)."""
import json, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
TMP = ROOT / ".idx"
OUT = ROOT / "index-sheets"
TMP.mkdir(exist_ok=True); OUT.mkdir(exist_ok=True)
CELL = (480, 270)
FONT = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 26)


def dur(f):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(f)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def frame(args):
    f, tmp = args
    d = dur(f)
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{d/2:.2f}", "-i", str(f),
         "-frames:v", "1", "-vf",
         f"scale={CELL[0]}:{CELL[1]}:force_original_aspect_ratio=decrease,"
         f"pad={CELL[0]}:{CELL[1]}:(ow-iw)/2:(oh-ih)/2:black",
         str(tmp)], capture_output=True)
    if not tmp.exists():
        return None
    label = f.stem.split("-k")[-1] if "-k" in f.stem else f.stem[:22]
    im = Image.open(tmp).convert("RGB")
    dr = ImageDraw.Draw(im)
    text = f"{label}  {int(d)}s"
    box = dr.textbbox((10, 8), text, font=FONT)
    dr.rectangle([box[0] - 6, box[1] - 4, box[2] + 6, box[3] + 4], fill=(0, 0, 0))
    dr.text((10, 8), text, font=FONT, fill=(255, 220, 60))
    return im


groups = {}
for f in sorted((ROOT / "clips").rglob("*.mp4")):
    groups.setdefault(f.parent.name, []).append(f)
solo = [r for r in json.loads((ROOT / "shots.json").read_text())
        if r["tip"] in ("surekli", "montaj")]
groups["_bolunmemis-kaynaklar"] = [ROOT / r["dosya"] for r in solo]

for name, files in groups.items():
    out = OUT / f"{name}.jpg"
    pairs = [(f, TMP / f"{name}-{i:03d}.png") for i, f in enumerate(files)]
    with ThreadPoolExecutor(max_workers=6) as ex:
        tiles = [t for t in ex.map(frame, pairs) if t is not None]
    if not tiles:
        print(f"{name}: kare cikarilamadi", file=sys.stderr)
        continue
    cols = 4 if len(tiles) > 6 else min(len(tiles), 3)
    rows = -(-len(tiles) // cols)
    pad = 4
    sheet = Image.new("RGB", (cols * (CELL[0] + pad) + pad,
                              rows * (CELL[1] + pad) + pad), (32, 32, 32))
    for i, t in enumerate(tiles):
        sheet.paste(t, (pad + (i % cols) * (CELL[0] + pad),
                        pad + (i // cols) * (CELL[1] + pad)))
    sheet.save(out, quality=88)
    for _, p in pairs:
        p.unlink(missing_ok=True)
    print(f"{out.name}: {len(tiles)} kesit ({cols}x{rows})")
