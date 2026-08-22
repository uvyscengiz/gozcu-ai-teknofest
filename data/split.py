#!/usr/bin/env python3
"""shots.json'da 'derleme' isaretli videolari sahne sinirlarindan kesitlere ayirir.

Her kesit clips/<kategori>/<video>/<video>-k##.mp4 olarak yazilir. 5 saniyeden
kisa sahneler atlanir (gecis/intro kareleri, tek basina bir olay tasimazlar).
Kesme ffmpeg ile kare-hassas yapilir; Apple Silicon donanim kodlayicisi kullanilir.
"""
import csv, json, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MIN_LEN = 5.0

shots = json.loads((ROOT / "shots.json").read_text())
targets = [r for r in shots if r["tip"] == "derleme"]


def scene_rows(name):
    p = ROOT / "scenes" / f"{name}-scenes.csv"
    rows = list(csv.reader(p.open()))
    hdr = next(i for i, r in enumerate(rows) if r and r[0] == "Scene Number")
    return [r for r in rows[hdr + 1:] if r and r[0].isdigit()]


def cut(args):
    src, out, start, length = args
    r = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{start:.3f}", "-i", str(src),
         "-t", f"{length:.3f}", "-c:v", "h264_videotoolbox", "-b:v", "6M",
         "-c:a", "aac", "-movflags", "+faststart", str(out)],
        capture_output=True, text=True)
    return out, r.returncode, r.stderr.strip()[:200]


jobs, skipped = [], 0
for rec in targets:
    src = ROOT / rec["dosya"]
    outdir = ROOT / "clips" / rec["kategori"] / rec["ad"]
    outdir.mkdir(parents=True, exist_ok=True)
    for row in scene_rows(rec["ad"]):
        start, length = float(row[3]), float(row[9])
        if length < MIN_LEN:
            skipped += 1
            continue
        out = outdir / f"{rec['ad']}-k{int(row[0]):02d}.mp4"
        if out.exists():
            continue
        jobs.append((src, out, start, length))

print(f"{len(targets)} derleme -> {len(jobs)} kesit ({skipped} kisa sahne atlandi)")
fails = 0
with ThreadPoolExecutor(max_workers=6) as ex:
    for out, code, err in ex.map(cut, jobs):
        if code != 0:
            fails += 1
            print(f"HATA {out.name}: {err}", file=sys.stderr)
print(f"tamam: {len(jobs) - fails} kesit, {fails} hata")
