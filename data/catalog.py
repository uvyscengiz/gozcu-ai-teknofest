#!/usr/bin/env python3
"""shots.json + labels.tsv + ffprobe'u birlestirip catalog.md / catalog.json uretir."""
import csv, json, subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# amac notlari video ID'ye gore eslesir: ayni slot'ta birden cok URL olabiliyor
AMAC = {}
for line in (ROOT / "sources.tsv").read_text().splitlines():
    p = line.split("\t")
    if len(p) != 4:
        continue
    url = p[2]
    vid = url.rstrip("/").split("/")[-1].split("?")[0]
    AMAC[vid] = p[3]

LAB = {}
for line in (ROOT / "labels.tsv").read_text().splitlines():
    if line.startswith("#") or not line.strip():
        continue
    p = line.split("\t")
    LAB[p[0]] = {"verdict": p[1], "etiket": p[2], "not": p[3] if len(p) > 3 else ""}

SHOTS = {r["ad"]: r for r in json.loads((ROOT / "shots.json").read_text())}


def probe(f):
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json",
                        "-show_format", "-show_streams", str(f)],
                       capture_output=True, text=True)
    if r.returncode:
        return f, {}
    d = json.loads(r.stdout)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), {})
    return f, {"sure": round(float(d["format"].get("duration", 0)), 1),
               "mb": round(int(d["format"].get("size", 0)) / 1048576, 1),
               "en": v.get("width"), "boy": v.get("height")}


# _elenen/ ayiklanan kesitlerin arsivi; katalogda ayri bolumde labels.tsv'den listelenir
files = sorted((ROOT / "raw").rglob("*.mp4")) + \
        [f for f in sorted((ROOT / "clips").rglob("*.mp4")) if "_elenen" not in f.parts]
with ThreadPoolExecutor(max_workers=8) as ex:
    meta = dict(ex.map(probe, files))

rows = []
for f in files:
    rel = str(f.relative_to(ROOT))
    kaynak = f.stem.split("-k")[0] if "/clips/" in f"/{rel}" else f.stem
    lab = LAB.get(rel, {})
    rows.append({
        "yol": rel,
        "tur": "kaynak" if rel.startswith("raw/") else "kesit",
        "kategori": f.relative_to(ROOT).parts[1],
        "kaynak": kaynak,
        "tip": SHOTS.get(f.stem, {}).get("tip", ""),
        "verdict": lab.get("verdict", "kullan"),
        "etiket": lab.get("etiket", ""),
        "not": lab.get("not", "") or SHOTS.get(f.stem, {}).get("duzeltme", ""),
        "amac": AMAC.get(kaynak.split("--")[-1], ""),
        **meta.get(f, {}),
    })

(ROOT / "catalog.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))


def mmss(s):
    s = int(s or 0)
    return f"{s // 60}:{s % 60:02d}"


kaynak = [r for r in rows if r["tur"] == "kaynak"]
kesit = [r for r in rows if r["tur"] == "kesit"]
kullan = kesit
ele = [{"kaynak": Path(k).name.split("-k")[0], "yol": k, **v}
       for k, v in LAB.items() if v["verdict"] == "ele"]

L = ["# Test Video Korpusu — Katalog", "",
     f"{len(kaynak)} kaynak video + {len(kesit) + len(ele)} kesit "
     f"({len(kesit)} kullanilabilir, {len(ele)} elenip `clips/_elenen/` altina alindi). "
     "`catalog.py` uretir, elle duzenlenmez — etiketler `labels.tsv`'de.", ""]

L += ["## Kaynak videolar", "",
      "| Kategori | Dosya | Süre | Çöz. | Boyut | Çekim tipi | Amaç |", "|---|---|---|---|---|---|---|"]
for r in sorted(kaynak, key=lambda r: (r["kategori"], r["yol"])):
    L.append(f"| {r['kategori']} | `{Path(r['yol']).name}` | {mmss(r.get('sure'))} | "
             f"{r.get('boy')}p | {r.get('mb')} MB | {r['tip']} | {r['amac']} |")

L += ["", "## Kesitler — kullanilabilir", "",
      "| Kategori | Kaynak | Kesit | Süre | Etiket |", "|---|---|---|---|---|"]
for r in sorted(kullan, key=lambda r: r["yol"]):
    L.append(f"| {r['kategori']} | {r['kaynak']} | `{Path(r['yol']).name.split('-k')[-1][:2]}` | "
             f"{mmss(r.get('sure'))} | {r['etiket']} |")

L += ["", "## Kesitler — elendi", "",
      "| Kaynak | Kesit | Sebep |", "|---|---|---|"]
for r in sorted(ele, key=lambda r: r["yol"]):
    L.append(f"| {r['kaynak']} | `{Path(r['yol']).name.split('-k')[-1][:2]}` | "
             f"{r['etiket']}{' — ' + r['not'] if r['not'] else ''} |")

(ROOT / "catalog.md").write_text("\n".join(L) + "\n")
print(f"{len(kaynak)} kaynak, {len(kullan)} kullanilabilir kesit, {len(ele)} elenen -> catalog.md")
tot = sum(r.get("sure", 0) for r in kaynak)
print(f"toplam kaynak suresi: {tot/60:.0f} dk")
