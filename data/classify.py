#!/usr/bin/env python3
"""Sahne CSV'lerinden her ham videoyu ceki yapisina gore siniflandirir.

  surekli  : cok az kesme, uzun ortalama cekim -> tek CCTV kaydi, oldugu gibi kullanilir
  derleme  : orta sayida kesme, 8sn+ ortalama  -> her kesme ayri bir olay, BOLUNUR
  montaj   : yogun kesme, kisa ortalama        -> muzik/kurgu montaji, bolmek anlamsiz
"""
import csv, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def scenes(csv_path):
    rows = list(csv.reader(csv_path.open()))
    # PySceneDetect: 1. satir toplam ozet, 2. satir baslik, sonrasi sahneler
    hdr = next((i for i, r in enumerate(rows) if r and r[0] == "Scene Number"), 1)
    body = [r for r in rows[hdr + 1:] if r and r[0].isdigit()]
    return [float(r[9]) for r in body]  # Length (seconds)


def duration(f):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(f)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


out = []
for f in sorted((ROOT / "raw").rglob("*.mp4")):
    b = f.stem
    c = ROOT / "scenes" / f"{b}-scenes.csv"
    dur = duration(f)
    lens = scenes(c) if c.exists() else []
    n = len(lens) or 1
    avg = (sum(lens) / n) if lens else dur
    # 5sn+ suren sahneler: bir olayi tasiyabilecek uzunlukta olanlar
    usable = [l for l in lens if l >= 5]
    if n <= 2 or avg >= 45:
        kind = "surekli"
    elif avg < 4.5:
        kind = "montaj"
    else:
        kind = "derleme"
    out.append({"dosya": str(f.relative_to(ROOT)), "ad": b, "kategori": f.parent.name,
                "sure": round(dur, 1), "sahne": n, "ort_sahne": round(avg, 1),
                "kullanilabilir_kesit": len(usable), "tip": kind})

(ROOT / "shots.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
w = max(len(r["ad"]) for r in out)
print(f"{'DOSYA':<{w}} {'TIP':<9} {'SURE':>7} {'SAHNE':>6} {'ORT':>6} {'5sn+':>5}")
for r in sorted(out, key=lambda r: (r["tip"], -r["sahne"])):
    print(f"{r['ad']:<{w}} {r['tip']:<9} {r['sure']:>7.0f} {r['sahne']:>6} "
          f"{r['ort_sahne']:>6.1f} {r['kullanilabilir_kesit']:>5}")
print()
for k in ("derleme", "montaj", "surekli"):
    print(f"{k}: {sum(1 for r in out if r['tip'] == k)}")
