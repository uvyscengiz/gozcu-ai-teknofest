"""`benchmark/results/kpi.json` → `benchmark/results/kpi.md` ve karar dağılımı grafiği.

Rapor tek bir kuralla yazılıyor: **hiçbir boşluk sayıya çevrilmez.** Ölçülemeyen
bir KPI tabloda `ölçülemedi` yazar, `0` yazmaz; bozulmuş bir koşunun başında
uyarı bandı durur. 4 dakikalık sunuma giden tek grafik buradan çıkıyor ve o
grafiğin yanında koşunun durumu da gitmeli — okuyan kişi sayıların bir şey
ifade edip etmediğini bilmeden bakmasın.

```bash
uv run python -m benchmark.run
uv run python -m benchmark.report
```
"""

import argparse
import json
import sys
from pathlib import Path

from benchmark.kpi import DECISION_BUCKETS, DEGRADED, MEASURED, UNMEASURED
from benchmark.run import BENCH_DIR, KPI_PATH

MARKDOWN_PATH = BENCH_DIR / "kpi.md"
CHART_PATH = BENCH_DIR / "decision-distribution.png"

NOT_MEASURED_TEXT = "ölçülemedi"

STATUS_BANNER = {
    MEASURED: "**Durum: ÖLÇÜLDÜ.** Kararların büyük çoğunluğu gerçek model "
              "kararı; aşağıdaki sayılar okunabilir.",
    DEGRADED: "**Durum: BOZULMUŞ KOŞU.** Devirlerin kayda değer bir kısmı "
              "kademe kesintisinden geldi (`degraded` payı). Bu tablo "
              "sistemin başarısını değil, kesintinin boyutunu gösterir.",
    UNMEASURED: "**Durum: ÖLÇÜLEMEDİ.** Yönlendirici hiç karar vermemiş; "
                "ortada ölçülecek bir koşu yok.",
}

BUCKET_LABELS = {
    "closed_at_router": "Yönlendiricide kapandı",
    "to_interpreter": "Yorumlayıcıya",
    "to_synthesizer": "Sentezleyiciye",
    "escalated": "Yükseltildi",
    "degraded": "Kesinti (ölçüm dışı)",
}

#: (anahtar, başlık, hedef) — sıra rapordaki sıra.
SCALAR_KPIS = (
    ("vlm_trigger_rate", "Görü tetikleme oranı", "%5'in altı"),
    ("timestamp_drift_s", "Zaman sapması (medyan, sn)", "düşük"),
    ("turkish_output_rate", "Türkçe kalma oranı", "1.0"),
    ("correction_propagation", "Düzeltme yayılımı", "1.0"),
    ("proactivity_rate", "Proaktivite oranı", "yüksek"),
)

WINDOW_OUTCOME_LABELS = {
    "routed": "Yönlendirici gördü",
    "forced": "Periyodik örneklem",
    "skipped": "Atlandı",
    "deferred": "Telafi kuyruğu",
}


def _number(value, digits: int = 3) -> str:
    return NOT_MEASURED_TEXT if value is None else f"{value:.{digits}f}"


def _tokens(table: dict | None) -> str:
    if not table:
        return NOT_MEASURED_TEXT
    return ", ".join(f"{model}: {int(total)}"
                     for model, total in sorted(table.items()))


def render_markdown(payload: dict) -> str:
    """KPI gövdesini Türkçe rapora çevirir; şekli `benchmark/results/kpi.schema.json`."""
    aggregate = payload["aggregate"]
    kpis = aggregate["kpis"]
    counts = aggregate["clips"]
    truth = payload.get("ground_truth", {})

    lines = ["# Gözcü — ölçüm sonuçları", ""]
    lines.append(STATUS_BANNER.get(aggregate["status"], aggregate["status"]))
    lines += ["", f"Üretim: {payload.get('generated_at', '-')} · şema sürümü "
                  f"{payload.get('schema_version', '-')}", ""]
    lines += [f"Klipler: {counts['total']} toplam · {counts['measured']} "
              f"ölçüldü · {counts['degraded']} bozuk · "
              f"{counts['unmeasured']} ölçülemedi · {counts['error']} hata",
              ""]
    if truth:
        lines += [f"Etiketler: {truth.get('labelled', 0)} işaretli pencere · "
                  f"{truth.get('unlabelled', 0)} olaylı ama etiketsiz · "
                  f"{truth.get('no_incident', 0)} negatif örnek. Etiketsiz "
                  "klipler zaman sapmasına girmez.", ""]

    lines += ["## Karar dağılımı", "",
              "Ortalamaya yalnız `measured` klipler girer; bozulmuş klip "
              "manşet sayıyı sulandırır.", "",
              "| Kova | Pay |", "| --- | --- |"]
    distribution = kpis.get("decision_distribution")
    for bucket in DECISION_BUCKETS:
        share = None if not distribution else distribution.get(bucket)
        lines.append(f"| {BUCKET_LABELS[bucket]} | {_number(share)} |")

    lines += ["", "## KPI özeti", "", "| KPI | Değer | Hedef |",
              "| --- | --- | --- |"]
    for key, label, target in SCALAR_KPIS:
        lines.append(f"| {label} | {_number(kpis.get(key))} | {target} |")
    lines.append(f"| Görü kademesi token'ları | {_tokens(kpis.get('vision_tokens'))} "
                 "| — |")
    lines += ["",
              "> Token muhasebesi **yalnız görü kademesini** kapsıyor: `tokens` "
              "sistemde bir tek `Interpretation` kaydında kalıcı hâle geliyor. "
              "Koşu geneli bir maliyet tablosu bu veriden üretilemez.", ""]

    # --- Gecikme ve kaynak kullanımı ------------------------------------------
    lines += ["## Gecikme ve kaynak kullanımı", "",
              "| Ölçüm | Değer |", "| --- | --- |"]
    lines.append(f"| Toplam boru hattı süresi "
                 f"| {_number(aggregate.get('total_pipeline_s'), 1)} sn |")
    lines.append(f"| Ortalama boru hattı süresi "
                 f"| {_number(aggregate.get('mean_pipeline_s'), 1)} sn |")
    peak_mb = aggregate.get("peak_memory_mb")
    lines.append("| Zirve bellek kullanımı "
                 f"| {NOT_MEASURED_TEXT if peak_mb is None else f'{peak_mb:.1f} MB'} |")

    gateway = kpis.get("gateway_latency")
    if gateway:
        lines.append(f"| Görü çağrısı gecikmesi (toplam) "
                     f"| {_number(gateway.get('total_ms'), 0)} ms |")
        lines.append(f"| Görü çağrısı gecikmesi (ortalama) "
                     f"| {_number(gateway.get('mean_ms'), 1)} ms |")
        lines.append(f"| Görü çağrısı gecikmesi (p50) "
                     f"| {_number(gateway.get('p50_ms'), 0)} ms |")
        lines.append(f"| Görü çağrısı gecikmesi (p95) "
                     f"| {_number(gateway.get('p95_ms'), 0)} ms |")
    lines.append("")

    # --- Özet kalitesi --------------------------------------------------------
    summary_quality = aggregate.get("summary_quality")
    if summary_quality:
        lines += ["## Özet kalitesi (LLM-as-judge)", "",
                  "| Boyut | Ortalama (1–5) |", "| --- | --- |"]
        # Aggregate yalnız mean ve count taşıyor; klip bazlı ayrıntı
        # varsa detaylandırılabilir ama burada koşu ortalaması yeterli.
        lines.append(f"| **Genel ortalama** | {_number(summary_quality.get('mean'))} |")
        lines.append(f"| Klip sayısı | {summary_quality.get('count', 0)} |")
        lines.append("")

    # --- Pencere dağılımı -----------------------------------------------------
    window_dist = kpis.get("window_outcome_distribution")
    if window_dist:
        lines += ["## Pencere dağılımı", "",
                  "| Sonuç | Pay |", "| --- | --- |"]
        for key, label in WINDOW_OUTCOME_LABELS.items():
            lines.append(f"| {label} | {_number(window_dist.get(key))} |")
        lines.append("")

    # --- Klip başına ----------------------------------------------------------
    lines += ["## Klip başına", "",
              "| Klip | Durum | En ucuz kademe | Görü tetikleme | Sapma (sn) "
              "| Türkçe | Süre (sn) | Risk | Hata |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for clip in payload.get("clips", []):
        clip_kpis = clip.get("kpis") or {}
        clip_distribution = clip_kpis.get("decision_distribution") or {}
        duration = clip.get("pipeline_duration_s")
        risk_acc = clip_kpis.get("risk_accuracy")
        if risk_acc and risk_acc.get("exact_match") is not None:
            risk_cell = "✓" if risk_acc["exact_match"] else (
                f"✗ ({risk_acc.get('predicted', '?')})")
        else:
            risk_cell = "—"
        lines.append(
            f"| {Path(clip['video']).name} | {clip.get('status', '-')} "
            f"| {_number(clip_distribution.get('closed_at_router'))} "
            f"| {_number(clip_kpis.get('vlm_trigger_rate'))} "
            f"| {_number(clip_kpis.get('timestamp_drift_s'), 2)} "
            f"| {_number(clip_kpis.get('turkish_output_rate'))} "
            f"| {_number(duration, 1) if duration is not None else '—'} "
            f"| {risk_cell} "
            f"| {clip.get('error') or '—'} |")
    return "\n".join(lines) + "\n"


def write_chart(payload: dict, path: Path = CHART_PATH) -> Path | None:
    """Karar dağılımı çubuk grafiği; dağılım ölçülemediyse grafik yok.

    Sunuma giden tek grafik bu. Kesinti payı ayrı bir çubuk olarak duruyor:
    bozulmuş bir koşunun grafiği "mükemmel filtreleme" gibi görünmemeli.
    """
    distribution = payload["aggregate"]["kpis"].get("decision_distribution")
    if not distribution:
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = [BUCKET_LABELS[b] for b in DECISION_BUCKETS]
    values = [distribution.get(b, 0.0) for b in DECISION_BUCKETS]
    colors = ["#2f6f4e"] * (len(DECISION_BUCKETS) - 1) + ["#a33"]

    figure, axes = plt.subplots(figsize=(8, 4.5))
    axes.bar(labels, values, color=colors)
    axes.set_ylim(0, 1)
    axes.set_ylabel("Kararların payı")
    axes.set_title("Yönlendirici kararları nerede kapandı")
    for index, value in enumerate(values):
        axes.text(index, value + 0.02, f"{value:.0%}", ha="center")
    figure.autofmt_xdate(rotation=20)
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=150)
    plt.close(figure)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gözcü ölçüm raporu")
    parser.add_argument("--kpi", default=str(KPI_PATH))
    parser.add_argument("--markdown", default=str(MARKDOWN_PATH))
    parser.add_argument("--chart", default=str(CHART_PATH))
    args = parser.parse_args(argv)

    source = Path(args.kpi)
    if not source.is_file():
        print(f"HATA: {source} yok — önce `python -m benchmark.run` koşun.",
              file=sys.stderr)
        return 2

    payload = json.loads(source.read_text(encoding="utf-8"))
    markdown = Path(args.markdown)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(payload), encoding="utf-8")
    chart = write_chart(payload, Path(args.chart))
    print(f"{markdown} yazıldı"
          + (f", {chart} yazıldı" if chart else "; karar dağılımı "
             "ölçülemediği için grafik üretilmedi"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
