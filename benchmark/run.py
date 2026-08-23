"""Benchmark koşucusu — etiketli klipleri koşturup `bench/kpi.json` yazar.

## Ön koşullar (hepsi gerçek, hiçbiri opsiyonel değil)

`benchmark/kpi.py` fikstürsüz ve gateway'siz çalışır; **koşu öyle değil.**
Bu script'in ihtiyaç duyduğu üç şey var ve üçü de bir klasörden okunamaz:

1. **Video dosyaları.** `data/clips/` `.gitignore`'da — taze bir klonda
   video yoktur. İndirme betikleri `data/` altında, gerçek dizin
   `data/labels.tsv`.
2. **Ayakta bir gateway.** Yönlendirici, görü ve ana kademeler gerçek model
   çağrısı yapar. Kademe yoksa her karar `confidence=0.0` ile kesintiye
   düşer; sayılar üretilir ama hiçbir şey ölçmez.
3. **Görev 17'nin `run_pipeline`'ı.** Depodaki `gozcu/run.py` hâlâ 1. Aşama
   PoC'si (`run_pipeline(video_path, output_dir)`); Görev 17 onu
   `run_pipeline(video_path, store=..., gw=...)` olarak yeniden yazıyor.
   Eski imzayla koşarsak depo boş kalır.

Bu yüzden `preflight()` eksik ön koşulda **yüksek sesle durur**. Alternatifi
şu olurdu: her KPI `null`, her dağılım boş, tertemiz bir `kpi.json` — yani
ölçüm gibi görünen bir hiç. Bu görevin bütün mesele ettiği şey tam olarak o
tabloyu üretmemek.

## Koşu

```bash
uv run --env-file .env python -m benchmark.run
uv run python -m benchmark.report
```

Bir klip çökerse koşu **durmaz**: hata o klibin kaydına yazılır ve sıradakine
geçilir. Kısmi sonuç, hiç sonuç olmamasından iyidir — ama kısmi olduğu
`clips` sayacında görünür.
"""

import argparse
import inspect
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from benchmark import kpi
from benchmark.ground_truth import (DEFAULT_PATH, Clip, GroundTruthError,
                                    load_ground_truth, windows)

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

#: Benchmark çıktılarının yeri. `runs/` DEĞİL: orası `.gitignore`'da ve
#: ultralytics'in kendi çıktıları için kullanılıyor — teslim edilecek ölçüm
#: sonuçları versiyonlanan bir dizinde durmalı.
BENCH_DIR = REPO_ROOT / "bench"
KPI_PATH = BENCH_DIR / "kpi.json"
STORE_DIR = BENCH_DIR / "stores"

#: `bench/kpi.json`'un biçim sürümü; şema `bench/kpi.schema.json`.
SCHEMA_VERSION = 1


class PrerequisiteError(RuntimeError):
    """Ön koşul eksik — sıfırlarla dolu sahte bir tablo üretmek yerine durulur."""


def missing_videos(clips: list[Clip], data_dir: Path = DATA_DIR) -> list[str]:
    return [clip.video for clip in clips
            if not (data_dir / clip.video).is_file()]


def pipeline_is_rewritten(run_pipeline) -> bool:
    """Görev 17'nin imzası mı, 1. Aşama PoC'si mi.

    Ayırt edici alan `store`: PoC `(video_path, output_dir)` alıyor ve depoya
    hiçbir şey yazmıyor — onunla koşulan bir benchmark her KPI'ı `null`
    okurdu ve bunu bir bulgu sanardık.
    """
    try:
        parameters = inspect.signature(run_pipeline).parameters
    except (TypeError, ValueError):
        return False
    return "store" in parameters


def preflight(clips: list[Clip], *, data_dir: Path = DATA_DIR,
              run_pipeline=None, gateway_probe=None) -> None:
    """Eksik her ön koşulu tek seferde, Türkçe ve adıyla bildirir.

    Hepsi birden raporlanıyor: teker teker düşen bir kontrol zinciri, koşuyu
    başlatmak isteyen kişiyi üç ayrı denemeye zorlar.
    """
    problems: list[str] = []
    if not clips:
        problems.append("etiket dosyasında hiç klip yok")

    absent = missing_videos(clips, data_dir)
    if absent:
        problems.append(
            f"{len(absent)} klip dosyası yok (data/clips/ .gitignore'da; "
            f"indirme betikleri data/ altında): " + ", ".join(absent[:3])
            + (" …" if len(absent) > 3 else ""))

    if run_pipeline is None or not pipeline_is_rewritten(run_pipeline):
        problems.append(
            "gozcu.run.run_pipeline hâlâ 1. Aşama PoC imzasında; benchmark "
            "Görev 17'nin store alan sürümünü bekliyor")

    if gateway_probe is not None and not gateway_probe():
        problems.append("gateway yanıt vermiyor: kademeler ayağa kalkmadan "
                        "koşulan benchmark yalnız kesinti ölçer")

    if problems:
        raise PrerequisiteError(
            "Benchmark ön koşulları eksik:\n- " + "\n- ".join(problems))


def _gateway_probe() -> bool:
    """Yönlendirici kademesine tek bir ucuz istek; kesinti varsa `False`.

    Ağ yalnız burada var — testler kendi sondalarını geçiriyor.
    """
    from gozcu.gateway import Gateway

    response = Gateway().ask(
        "router", [{"role": "user", "content": "hazır mısın"}],
        max_tokens=1, _retries=1)
    return not response.degraded


def run_clip(clip: Clip, *, run_pipeline, store_factory,
             data_dir: Path = DATA_DIR) -> dict:
    """Tek klibi koşturur ve KPI kaydını döndürür; çöküş kayda yazılır.

    Arşiv tohumlaması varsa kimlikler koşudan ÖNCE alınıyor: `load_history`
    ile gelen epizotlar tespit değil, onları sapma hesabına katmak sahte bir
    isabet üretir.
    """
    record = {"video": clip.video, "error": None, "status": kpi.UNMEASURED,
              "kpis": {key: None for key in kpi.KPI_KEYS}}
    try:
        store = store_factory(clip)
        seeded = {episode.id for episode in store.episodes()}
        run_pipeline(str(data_dir / clip.video), store=store)
        epoch_scale = kpi.epoch_scale_episodes(store)
        if epoch_scale:
            raise RuntimeError(
                f"{len(epoch_scale)} epizot epoch ölçeğinde bir start_ts "
                "taşıyor; zaman damgaları video saniyesi olmalı")
        record.update(kpi.collect(store,
                                  windows([clip]),
                                  seeded_episode_ids=seeded))
    except Exception as error:  # noqa: BLE001 — bir klip koşuyu durdurmamalı
        record["error"] = f"{type(error).__name__}: {error}"
    return record


def _store_factory(clip: Clip):
    """Klip başına bir SQLite dosyası.

    Depo dosyası koşu bitmeden okunmuyor: `Store`'un WAL pragma'sı ve
    `close()`'u yok, yazan süreçle aynı anda okumak gerçek bir çekişme.
    """
    from gozcu.store import Store

    STORE_DIR.mkdir(parents=True, exist_ok=True)
    path = STORE_DIR / (Path(clip.video).stem + ".db")
    path.unlink(missing_ok=True)
    return Store(path)


def benchmark(clips: list[Clip], *, run_pipeline, store_factory=_store_factory,
              data_dir: Path = DATA_DIR) -> dict:
    """Bütün klipleri koşturur ve `bench/kpi.json` gövdesini üretir."""
    records = [run_clip(clip, run_pipeline=run_pipeline,
                        store_factory=store_factory, data_dir=data_dir)
               for clip in clips]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "ground_truth": {
            "clips": len(clips),
            "labelled": sum(1 for c in clips if c.labelled),
            "unlabelled": sum(1 for c in clips if c.unlabelled),
            "no_incident": sum(1 for c in clips if not c.has_incident),
        },
        "clips": records,
        "aggregate": kpi.aggregate(records),
    }


def write_payload(payload: dict, path: Path = KPI_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gözcü benchmark koşucusu")
    parser.add_argument("--ground-truth", default=str(DEFAULT_PATH))
    parser.add_argument("--data-dir", default=str(DATA_DIR))
    parser.add_argument("--out", default=str(KPI_PATH))
    parser.add_argument("--skip-gateway-probe", action="store_true",
                        help="gateway sondasını atlar; sayılar kesinti ölçer")
    args = parser.parse_args(argv)

    try:
        clips = load_ground_truth(args.ground_truth)
    except GroundTruthError as error:
        print(f"HATA: {error}", file=sys.stderr)
        return 2

    from gozcu.run import run_pipeline

    try:
        preflight(clips, data_dir=Path(args.data_dir),
                  run_pipeline=run_pipeline,
                  gateway_probe=None if args.skip_gateway_probe
                  else _gateway_probe)
    except PrerequisiteError as error:
        print(f"HATA: {error}", file=sys.stderr)
        return 2

    payload = benchmark(clips, run_pipeline=run_pipeline,
                        data_dir=Path(args.data_dir))
    path = write_payload(payload, Path(args.out))
    aggregate = payload["aggregate"]
    print(f"{path} yazıldı — durum: {aggregate['status']}, "
          f"klipler: {aggregate['clips']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
