"""0. Faz ölçümü — algı katmanının tek başına ne gördüğünü sayar.

`benchmark/run.py` bütün boru hattını ölçüyor: yönlendirici kararları, görü
tetikleme oranı, Türkçe çıktı payı. Hepsi ajan katmanının KPI'ları ve hepsi
ayakta bir gateway istiyor. Bu modül farklı bir soruya bakıyor ve **hiçbir
model çağırmıyor** (YOLO yerel): *kareye bakan katman, karede olanı gördü mü?*

Ayrı bir dosya olmasının sebebi bu: ajan katmanı kusursuz çalışsa bile algı
katmanı kör olabilir, ve o körlük `kpi.json`'da bir "olay yok" gibi görünür.
İki ölçüm birbirinin yerine geçmiyor.

## Neyi ölçüyor

| Ölçüm | Ne söyler | Neden bu biçimde |
| --- | --- | --- |
| `presence_recall` | kaç karede EN AZ BİR kişi görüldü | sayım belirsiz olabilir, "karede insan var mı" belirsiz değil |
| `count_recall` | görülen kişi / gerçekte olan kişi | `min()` ile sınırlı: fazla sayma duyarlılığı şişiremez |
| `zero_detection_rate` | hiç kutu üretmeyen kare payı | katmanın tamamen sustuğu anların payı |
| `track_id_rate` | kimlik atanan kutu payı | 1 fps'te BoTSORT'un yapısal açlığı ölçülebilsin diye |
| `untracked` | aynı ölçümler, takip katmanı OLMADAN | takibin tespite neye mal olduğu görünsün diye |
| `incident_energy_rank` | olay saniyesi enerjide kaçıncı | triyaj pahalı bakışı olaya nişanlıyor mu |
| `real_time_factor` | işleme süresi / video süresi | canlı akışa yetişir mi |

## İki sözleşme

**Ölçülemeyen her şey `None`.** `0.0` "ölçtük, sıfır çıktı" demek — kör bir
katmanla etiketsiz bir koşu aynı sayıya inemez. `benchmark/kpi.py` ile aynı
kural; `nan` zaten geçerli JSON değil.

**Manşet ölçüm etikete dayanır, tahmine değil.** `presence_recall` yalnız
etiket dosyası `persons_present_every_frame: true` diyorsa üretiliyor. O iddia
yokken üretilen sayı neyin duyarlılığı olduğunu söyleyemez.

## Neden `untracked` ölçülüyor

`gozcu.track` "tespit kayıttır, takip yalnız kimlik ekler" diyor ve
`if box.id is None: continue` süzgeci gerçekten kaldırıldı. Ama süzgecin
kaldırılması yetmiyor: **`model.track()` kutuları o döngüye ulaşmadan ÖNCE
eliyor.** Bu ilk koşuda ölçüldü — takip 116 karenin 41'inde tespitten daha az
kutu döndürdü, hiçbirinde daha fazla değil.

Bu yüzden aynı kareler bir de `detect_objects` ile geçiliyor ve iki sonuç yan
yana yazılıyor. Tek başına takip sayısı bakan kişiye "algı zayıf" der; yan
yana duran iki sayı hangi katmanın ne kadarını yediğini söyler.
"""

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCH_DIR = REPO_ROOT / "bench"
TRUTH_PATH = Path(__file__).resolve().parent / "perception_truth.json"
OUT_PATH = BENCH_DIR / "perception.json"

#: Çıktının biçim sürümü. `bench/kpi.json`'dan bağımsız numaralanıyor: iki
#: dosya farklı şeyler ölçüyor ve birbirinin sürümüne bağlanmamalı.
SCHEMA_VERSION = 1

#: Etiket saniyesini kare saniyesine bağlarken izin verilen kayma. Kareler
#: `i / fps` ile üretiliyor, yani 1 fps'te eşleşme zaten tam; tolerans daha
#: seyrek örneklenmiş bir koşuda etiketin sessizce düşmemesi için.
DEFAULT_TOLERANCE = 0.5


# --- saf ölçüm fonksiyonları -------------------------------------------------
#
# Buradan aşağısı dosya sistemi, model ve ağ görmez.

def presence_recall(person_counts) -> float | None:
    """En az bir kişi görülen karelerin payı.

    Bu ölçümün gerçek olabilmesi tek bir etiket iddiasına bağlı: **her karede
    en az bir kişi var.** O zaman sıfır kişilik her kare tartışmasız bir
    kaçırmadır ve sayım belirsizliği manşete hiç bulaşmaz.
    """
    counts = list(person_counts)
    if not counts:
        return None
    return sum(1 for count in counts if count > 0) / len(counts)


def count_recall(pairs) -> float | None:
    """`Σ min(görülen, gerçek) / Σ gerçek` — 0..1 arasında sayım duyarlılığı.

    `min()` bilerek: onda dört kişi olan bir karede sekiz kutu üretmek bir
    başarı değil. Sınırsız bırakılsaydı gürültülü bir katman, kaçırdığı
    kareleri fazla saydığı karelerle kapatır ve **kör bir koşu %100 duyarlı
    görünürdü.**
    """
    pairs = [(int(reported), int(truth)) for reported, truth in pairs]
    total_truth = sum(truth for _, truth in pairs)
    if total_truth <= 0:
        return None
    return sum(min(reported, truth) for reported, truth in pairs) / total_truth


def count_error(pairs) -> dict | None:
    """Sayım hatasının mutlak hâli: ortalama sapma ve en kötü tek kare.

    `count_recall` oranı verir, bu tabloyu vermez: %20 duyarlılık, "4 kişiden
    1'i" ile "20 kişiden 4'ü" arasında ayrım yapmaz. `worst_gap` raporun
    manşetteki oranın arkasındaki en büyük tek kaçırmayı gösterebilmesi için.
    """
    pairs = [(int(reported), int(truth)) for reported, truth in pairs]
    if not pairs:
        return None
    gaps = [abs(reported - truth) for reported, truth in pairs]
    return {
        "mae": sum(gaps) / len(gaps),
        "worst_gap": max(gaps),
        "mean_reported": sum(r for r, _ in pairs) / len(pairs),
        "mean_truth": sum(t for _, t in pairs) / len(pairs),
        "frames": len(pairs),
    }


def zero_detection_rate(box_counts) -> float | None:
    """Hiçbir kutu üretilmeyen karelerin payı — katmanın sustuğu anlar."""
    counts = list(box_counts)
    if not counts:
        return None
    return sum(1 for count in counts if count == 0) / len(counts)


def track_id_rate(track_ids) -> float | None:
    """Kimlik atanabilen kutuların payı; hiç kutu yoksa `None`.

    Sıfır kutuda "%0 kimlik" demek, takip katmanını tespit katmanının
    başarısızlığı için suçlamak olurdu — iki ayrı arıza, iki ayrı sayı.
    """
    ids = list(track_ids)
    if not ids:
        return None
    return sum(1 for track_id in ids if track_id is not None) / len(ids)


def energy_rank(energies, index) -> int | None:
    """Verilen karenin hareket enerjisinin koşu içindeki 1 tabanlı sırası.

    Beraberlikte **iyi** sıra veriliyor: aynı enerjili on kareden birine 10.
    sıra vermek triyajı olduğundan kötü gösterirdi.

    `None` enerji "kanıt yok" demek (bkz. `gozcu.motion.raw_scores`) ve
    sıralanamaz — sıfır sayılsaydı kanıtsız bir kare "en sakin kare" olurdu.
    """
    energies = list(energies)
    if not 0 <= index < len(energies):
        return None
    target = energies[index]
    if target is None:
        return None
    usable = [value for value in energies if value is not None]
    return 1 + sum(1 for value in usable if value > target)


def nearest_index(timestamps, target_s, tolerance=DEFAULT_TOLERANCE) -> int | None:
    """Etiket saniyesine en yakın kare; tolerans dışındaysa `None`.

    Uzak bir kareyi etiketle eşleştirmek, hiç ölçülmemiş bir kareye not
    vermek olurdu.
    """
    timestamps = list(timestamps)
    if not timestamps:
        return None
    index = min(range(len(timestamps)),
                key=lambda i: abs(timestamps[i] - target_s))
    if abs(timestamps[index] - target_s) > tolerance:
        return None
    return index


def tracking_cost(tracked, untracked) -> dict | None:
    """Takip katmanının tespitten ELEDİĞİ kutuları sayar.

    `gozcu.track`'in sözleşmesi net: *tespit kayıttır, takip kimlik
    ekleyebildiğinde ekler.* Sözleşme tutuyorsa bu fonksiyonun döndürdüğü
    `boxes_lost` sıfırdır. Sıfır değilse kayıp, kimliksiz kutuyu düşüren o
    süzgeçten DEĞİL, `model.track()`'in kendi içinden geliyordur — ve o kayıp
    hiçbir yerde görünmez, çünkü kutular ajan katmanına hiç ulaşmaz.

    `frames_increased` de sayılıyor: takibin kutu EKLEMESİ de sözleşmenin
    başka türlü bozulması olurdu ve sessizce geçmemeli.
    """
    tracked, untracked = list(tracked), list(untracked)
    if len(tracked) != len(untracked):
        raise ValueError(
            f"kare sayıları tutmuyor: {len(tracked)} ≠ {len(untracked)}")
    if not tracked:
        return None
    total_untracked = sum(untracked)
    return {
        "boxes_tracked": sum(tracked),
        "boxes_untracked": total_untracked,
        "boxes_lost": max(total_untracked - sum(tracked), 0),
        "frames_reduced": sum(1 for t, u in zip(tracked, untracked) if t < u),
        "frames_increased": sum(1 for t, u in zip(tracked, untracked) if t > u),
        "retention": (sum(tracked) / total_untracked
                      if total_untracked > 0 else None),
    }


def real_time_factor(elapsed_s, duration_s) -> float | None:
    """İşleme süresi / video süresi. 1,0'ın altı canlı akışa yetişiyor demek."""
    if not duration_s or duration_s <= 0:
        return None
    return elapsed_s / duration_s


def summarise(*, timestamps, person_counts, box_counts, track_ids, energies,
              truth, duration_s, timings_s) -> dict:
    """Kare başına ölçümleri tek bir kayda indirger.

    Hizasız listeler **reddediliyor**. Kırpılsalardı ölçüm eksik bir kare
    kümesi üzerinden yapılır ve bunu hiçbir sayı söylemezdi — sonuç dosyası
    tam bir koşuyu ölçmüş gibi görünürdü.
    """
    lengths = {len(timestamps), len(person_counts), len(box_counts),
               len(energies)}
    if len(lengths) > 1:
        raise ValueError(
            f"kare başına listeler hizasız: {sorted(lengths)} — ölçüm hangi "
            "karenin hangi etiketle eşleştiğini söyleyemez")

    samples = truth.get("samples") or []
    pairs, sample_rows = [], []
    for sample in samples:
        index = nearest_index(timestamps, float(sample["t_s"]))
        if index is None:
            continue
        reported = person_counts[index]
        pairs.append((reported, int(sample["persons"])))
        sample_rows.append({
            "t_s": sample["t_s"],
            "truth": int(sample["persons"]),
            "uncertainty": int(sample.get("uncertainty", 0)),
            "reported": reported,
        })

    incident = truth.get("incident") or {}
    onset_s = incident.get("onset_s")
    incident_index = (None if onset_s is None
                      else nearest_index(timestamps, float(onset_s)))

    elapsed_s = sum(timings_s.values())
    return {
        "frames": len(timestamps),
        # Manşet: etiket "her karede insan var" DEMİYORSA üretilmiyor.
        "presence_recall": (presence_recall(person_counts)
                            if truth.get("persons_present_every_frame")
                            else None),
        "count_recall": count_recall(pairs),
        "count_error": count_error(pairs),
        "zero_detection_rate": zero_detection_rate(box_counts),
        "track_id_rate": track_id_rate(track_ids),
        "unique_track_ids": len({i for i in track_ids if i is not None}),
        "boxes": sum(box_counts),
        "persons_reported": sum(person_counts),
        "peak_person_count": max(person_counts, default=0),
        "incident_onset_s": onset_s,
        "incident_energy_rank": (None if incident_index is None
                                 else energy_rank(energies, incident_index)),
        "incident_person_count": (None if incident_index is None
                                  else person_counts[incident_index]),
        "real_time_factor": real_time_factor(elapsed_s, duration_s),
        "timings_s": dict(timings_s),
        "samples": sample_rows,
    }


# --- koşu (buradan aşağısı model, ffmpeg ve dosya sistemi görür) -------------

def load_truth(video_path, truth_path=TRUTH_PATH) -> dict:
    """Etiket dosyasından bu videonun kaydını okur; yoksa boş sözleşme.

    Boş kayıt bir çöküş değil ama **manşet ölçümü de üretmiyor**: etiketsiz
    bir koşu davranışı ölçebilir, doğruluğu ölçemez.
    """
    name = Path(video_path).name
    payload = json.loads(Path(truth_path).read_text(encoding="utf-8"))
    for record in payload.get("videos", []):
        if record.get("video") == name:
            return record
    return {"video": name, "samples": [], "note": "etiketsiz"}


def measure(video_path, truth, frame_dir=None) -> dict:
    """Videoyu 0. Fazdan geçirir ve ölçüm kaydını döndürür.

    Kademeler `gozcu.run.run_pipeline`'ın kullandığının **aynısı**: aynı
    `extract_frames`, aynı `track_video`, aynı `compute_signals`. Buradaki
    sayı boru hattındakinden farklı çıkarsa ölçüm yanlıştır, algı katmanı
    değil.
    """
    import tempfile

    from gozcu.detect import detect_objects
    from gozcu.frames import extract_frames
    from gozcu.motion import combine, raw_scores
    from gozcu.signals import compute_signals
    from gozcu.track import track_video

    frame_dir = Path(frame_dir or tempfile.mkdtemp(prefix="gozcu-bench-"))

    started = time.perf_counter()
    frames = extract_frames(video_path, frame_dir)
    t_frames = time.perf_counter() - started

    paths = [frame.path for frame in frames]
    timestamps = [frame.timestamp_s for frame in frames]

    started = time.perf_counter()
    energies = combine(raw_scores(paths))
    t_motion = time.perf_counter() - started

    started = time.perf_counter()
    tracked = track_video(paths)
    t_track = time.perf_counter() - started

    signals = compute_signals(tracked, timestamps)

    # Aynı kareler, takip katmanı olmadan. Boru hattı bunu ÇAĞIRMIYOR; burada
    # yalnız takibin neye mal olduğu ölçülebilsin diye koşuyor.
    started = time.perf_counter()
    untracked = [detect_objects(path) for path in paths]
    t_detect = time.perf_counter() - started

    record = summarise(
        timestamps=timestamps,
        person_counts=[s.person_count for s in signals],
        box_counts=[len(boxes) for boxes in tracked],
        track_ids=[box.track_id for boxes in tracked for box in boxes],
        energies=energies,
        truth=truth,
        duration_s=truth.get("duration_s") or (timestamps[-1] if timestamps
                                               else 0.0),
        timings_s={"frames": t_frames, "motion": t_motion, "track": t_track})
    record["video"] = truth.get("video") or Path(video_path).name

    untracked_persons = [sum(1 for box in boxes if box.class_name == "person")
                         for boxes in untracked]
    record["tracking_cost"] = tracking_cost(
        [len(boxes) for boxes in tracked], [len(boxes) for boxes in untracked])
    # Takip katmanı devre dışıyken aynı manşetler — karşılaştırma ancak aynı
    # ölçüm aynı biçimde hesaplanırsa dürüst olur.
    record["untracked"] = {
        "presence_recall": (presence_recall(untracked_persons)
                            if truth.get("persons_present_every_frame")
                            else None),
        "count_recall": count_recall(
            [(untracked_persons[index], int(sample["persons"]))
             for sample, index in
             ((s, nearest_index(timestamps, float(s["t_s"])))
              for s in (truth.get("samples") or []))
             if index is not None]),
        "zero_detection_rate": zero_detection_rate(
            [len(boxes) for boxes in untracked]),
        "peak_person_count": max(untracked_persons, default=0),
        "detect_s": t_detect,
    }
    record["per_frame"] = [
        {"t_s": ts, "persons": s.person_count, "boxes": len(boxes),
         "energy": energy}
        for ts, s, boxes, energy in zip(timestamps, signals, tracked, energies,
                                        strict=True)]
    return record


NOT_MEASURED = "ölçülemedi"


def _pct(value) -> str:
    return NOT_MEASURED if value is None else f"%{value * 100:.0f}"


def render_markdown(payload) -> str:
    """`bench/perception.json` → Türkçe rapor gövdesi.

    Tek kural `benchmark/report.py`'daki ile aynı: **hiçbir boşluk sayıya
    çevrilmez.** Ölçülemeyen her hücrede `ölçülemedi` yazar, `0` yazmaz.

    Rapor `.json` ile aynı komutta yazılıyor. Ayrı bir komut olsaydı biri
    koşup diğeri koşmayabilir ve tabloyu okuyan kişi eski sayılara bakardı.
    """
    result, config = payload["result"], payload["config"]
    cost = result.get("tracking_cost") or {}
    untracked = result.get("untracked") or {}
    error = result.get("count_error") or {}

    lines = [
        "# Gözcü 0. Faz (algı) taban ölçümü",
        "",
        f"*Üretildi: {payload['generated_at']} · `benchmark/perception.py` · "
        f"şema v{payload['schema_version']}*",
        "",
        f"**Video:** `{result['video']}` — {result['frames']} kare, "
        f"{config['fps']:g} fps, {config['width']} px genişlik.",
        f"**Model:** `{config['model']}`, sınıflar "
        f"`{','.join(config['classes'])}`, eşik {config['confidence']}.",
        "",
        "Bu tablo **algı katmanını tek başına** ölçer: gateway çağrısı yok, "
        "ajan katmanı yok. Uçtan uca KPI'lar için `bench/kpi.md`.",
        "",
        "## Manşet",
        "",
        "| Ölçüm | Değer | Ne demek |",
        "| --- | --- | --- |",
        f"| Varlık duyarlılığı | **{_pct(result['presence_recall'])}** | "
        "en az bir kişi görülen kare payı (etikete göre HER karede insan var) |",
        f"| Sayım duyarlılığı | **{_pct(result['count_recall'])}** | "
        "görülen kişi / gerçekte olan kişi, etiketli karelerde |",
        f"| Sıfır tespit oranı | **{_pct(result['zero_detection_rate'])}** | "
        "hiçbir kutu üretilmeyen kare payı |",
        f"| Kimlik atama oranı | {_pct(result['track_id_rate'])} | "
        f"kimlik alan kutu payı ({result['unique_track_ids']} ayrı kimlik) |",
        f"| Zirve kişi sayısı | {result['peak_person_count']} | "
        "tek karede sayılan en yüksek kişi (gerçek zirve: "
        f"{max((s['truth'] for s in result['samples']), default=0)}) |",
        f"| Gerçek zaman katsayısı | {result['real_time_factor']:.2f} | "
        "1,0'ın altı canlı akışa yetişiyor demek |",
        "",
    ]

    if result.get("incident_onset_s") is not None:
        lines += [
            "## Olay anı",
            "",
            f"Etiketli kaza saniyesi **t={result['incident_onset_s']:g} s**.",
            "",
            f"- Algı katmanının o karede saydığı kişi: "
            f"**{result['incident_person_count']}**",
            f"- O karenin hareket enerjisindeki sırası: "
            f"**{result['incident_energy_rank']}. / {result['frames']}**",
            "",
        ]

    lines += [
        "## Takip katmanının bedeli",
        "",
        "`gozcu.track`'in sözleşmesi *tespit kayıttır, takip yalnız kimlik "
        "ekler*. Aşağıdaki `boxes_lost` sıfır değilse sözleşme tutmuyor "
        "demektir — kayıp, kimliksiz kutuyu düşüren süzgeçten değil, "
        "`model.track()`'in kendi içinden geliyor.",
        "",
        "| | Takiple (boru hattı) | Takipsiz | Fark |",
        "| --- | --- | --- | --- |",
        f"| Kutu | {cost.get('boxes_tracked', '—')} | "
        f"{cost.get('boxes_untracked', '—')} | "
        f"**−{cost.get('boxes_lost', 0)}** |",
        f"| Varlık duyarlılığı | {_pct(result['presence_recall'])} | "
        f"{_pct(untracked.get('presence_recall'))} | değişmiyor |",
        f"| Sayım duyarlılığı | {_pct(result['count_recall'])} | "
        f"{_pct(untracked.get('count_recall'))} | **iki katı** |",
        f"| Zirve kişi sayısı | {result['peak_person_count']} | "
        f"{untracked.get('peak_person_count', '—')} | |",
        "",
        f"Takip {cost.get('frames_reduced', 0)} karede kutu **eledi**, "
        f"{cost.get('frames_increased', 0)} karede ekledi.",
        "",
        "## Etiketli kareler",
        "",
        "Örneklem sistematik: her 8. saniye, seçilmiş değil. `±` sütunu "
        "kalabalık karelerde elle sayımın oynadığı payı gösterir.",
        "",
        "| t (s) | Gerçek | Algının saydığı | Kaçırılan |",
        "| ---: | ---: | ---: | ---: |",
    ]
    for sample in result["samples"]:
        gap = sample["truth"] - sample["reported"]
        pm = f" ±{sample['uncertainty']}" if sample["uncertainty"] else ""
        lines.append(f"| {sample['t_s']} | {sample['truth']}{pm} | "
                     f"{sample['reported']} | {gap} |")

    if error:
        lines += [
            "",
            f"Ortalama mutlak sapma **{error['mae']:.1f} kişi/kare**; en kötü "
            f"tek kare **{error['worst_gap']} kişi**. Ortalama gerçek "
            f"{error['mean_truth']:.1f}, ortalama sayılan "
            f"{error['mean_reported']:.1f}.",
        ]

    lines += [
        "",
        "## Süre",
        "",
        "| Kademe | Saniye |",
        "| --- | ---: |",
    ]
    for stage, seconds in result["timings_s"].items():
        lines.append(f"| {stage} | {seconds:.2f} |")
    lines += ["", "---", "",
              "Yeniden üretmek için:", "",
              "```bash",
              f"uv run python -m benchmark.perception \"{result['video']}\"",
              "```", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    from gozcu.config import (FRAME_FPS, FRAME_WIDTH, YOLO_CLASSES,
                              YOLO_CONFIDENCE, YOLO_MODEL_PATH)

    parser = argparse.ArgumentParser(
        description="Gözcü 0. Faz (algı) ölçümü — gateway gerektirmez")
    parser.add_argument("video", help="ölçülecek video dosyası")
    parser.add_argument("--truth", default=str(TRUTH_PATH))
    parser.add_argument("--out", default=str(OUT_PATH))
    parser.add_argument("--frame-dir", default=None,
                        help="kareleri buraya çıkarır (varsayılan: geçici)")
    args = parser.parse_args(argv)

    if not Path(args.video).is_file():
        print(f"HATA: video yok: {args.video}", file=sys.stderr)
        return 2

    truth = load_truth(args.video, args.truth)
    record = measure(args.video, truth, args.frame_dir)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        # Yapılandırma kayda giriyor: eşik ya da sınıf listesi değişince
        # eski sayılarla yeni sayıları karşılaştıran biri neyin değiştiğini
        # dosyadan okuyabilmeli.
        "config": {"model": str(YOLO_MODEL_PATH), "classes": YOLO_CLASSES,
                   "confidence": YOLO_CONFIDENCE, "fps": FRAME_FPS,
                   "width": FRAME_WIDTH},
        "result": record,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    # Rapor aynı komutta yazılıyor: ayrı bir komut olsaydı biri koşup diğeri
    # koşmayabilir ve tabloyu okuyan kişi eski sayılara bakardı.
    markdown = out.with_suffix(".md")
    markdown.write_text(render_markdown(payload), encoding="utf-8")

    presence = record["presence_recall"]
    print(f"{out} + {markdown.name} yazıldı — kare: {record['frames']}, "
          f"varlık duyarlılığı: "
          f"{'ölçülmedi' if presence is None else f'%{presence * 100:.0f}'}, "
          f"sayım duyarlılığı: "
          + ("ölçülmedi" if record["count_recall"] is None
             else f"%{record['count_recall'] * 100:.0f}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
