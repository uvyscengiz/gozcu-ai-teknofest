# Görev 15 — KPI ve benchmark (`benchmark/`)

**Sahip:** `rumeysaoru` · **Gün:** 26 Ağustos sabahı · **Süre:** ~3 saat
**Bağımlılık:** [02](02-olay-deposu.md) — `kpi.py` ve testleri için yeterli.
`benchmark/run.py` ayrıca [17](17-cikti-sozlesmesi.md)'yi bekliyor; **önce `kpi.py`'ı
yaz ve testleri yeşile al**, runner'ı 17 indikten sonra ekle. Bu sırayla hiç
beklemezsin.
**Etiket:** `cold-start`

## Bağlam

### Proje ne?

Gözcü, fabrika kamera kaydını izleyip olayları fark eden ve operatörle Türkçe
konuşan bir karar destek sistemi. TEKNOFEST Yapay Zekâ Dil Ajanları Yarışması,
3. senaryo. Teslim 26 Ağustos 23:59.

### Bu görev neden var?

Şartname iki şey istiyor: *"katılımcılar, geliştirdikleri sistemin başarısını
ölçmek için kendi metriklerini tanımlamalıdır"* ve teslim kalemi olarak
**benchmark kodu**. Ayrıca dokümantasyonda "ölçümleme sonuçları" bölümü zorunlu.

**Ve bir tanesi sunumun manşet sayısı oluyor.** Mimarimizin iddiası şu: her karar
yetecek en ucuz modele düşüyor, kararların büyük çoğunluğu en küçük modelde
kapanıyor. Bu iddianın kanıtı senin üreteceğin **karar dağılımı grafiği**.
4 dakikalık sunumda tek grafik gidiyor ve o bu.

**İyi haber:** metriklerin tamamı depodaki kayıtlardan hesaplanıyor. Model
çağrısı yok, etiketleme neredeyse yok.

## Kurulum

```bash
git clone git@github.com:uvyscengiz/gozcu-ai-teknofest.git
cd gozcu-ai-teknofest
uv sync --extra dev
uv run pytest tests/ -v
```

## Bağımlı olduğun imzalar

```python
# gozcu/store.py — hepsi okuma
Store(db_path)                      # dosya yolu verilebilir, ":memory:" de olur
Store.observations() -> list[Observation]
Store.interpretations() -> list[Interpretation]     # Yorum.model: str, .token: int, .gecikme_ms: int
Store.episodes() -> list[Episode]   # Epizot.baslangic_ts: float
Store.handoffs() -> list[Handoff]     # Devir.kaynak_ajan, .hedef_ajan
Store.corrections(episode_id) -> list[Correction]   # .epizot_id, .eski, .yeni

# gozcu/report.py  (Görev 17)
build_output(store, ozet: str, kok_neden=None) -> PipelineOutput
```

**Ajan adları** (`Handoff.source_agent` / `target_agent` alanlarında görürsün):
`algi`, `yonlendirici`, `yorumlayici`, `sentezleyici`, `risk_analisti`,
`nobetci`, `raportor`.

## Ne yapacaksın

`benchmark/kpi.py` — beş saf fonksiyon:

```python
decision_distribution(store) -> dict[str, float]
vlm_trigger_rate(store) -> float
tokens_by_model(store) -> dict[str, float]
correction_propagation(store) -> float
timestamp_drift(store, truth: list[tuple[float, float]]) -> float
turkish_output_rate(store) -> float
```

`turkish_output_rate` ucuz ama önemli: yarışmanın adı **Türkçe** dil ajanları ve
modelin sessizce İngilizceye kayması en sinsi başarısızlık. Üretilen özet ve
diyalog metinlerinde İngilizce stop-word (`the`, `and`, `is`, `with`) arıyoruz.
Kasıntı Türkçe'yi yakalamaz — onun için 26 Ağustos'taki insan turu var — ama
dilin tamamen kaymasını yakalar.

**`decision_distribution` için kritik uyarı:** `devir` tablosuna sadece yönlendirici
yazmıyor — sentezleyici ve risk analisti de kendi devirlerini yazıyor. Hepsini
sayarsan oranlar 1'e toplanmaz ve manşet sayı sulanır. **Sadece
`source_agent == "router"` olan satırları say.**

`benchmark/run.py` — etiketli her klibi koşturur, klip başına bir SQLite dosyası
üretir, `runs/kpi.json` yazar.
`benchmark/report.py` — onu okuyup `runs/kpi.md` ve karar dağılımı grafiğini üretir.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_kpi.py`

```python
from benchmark.kpi import (correction_propagation, decision_distribution,
                           timestamp_drift, tokens_by_model,
                           turkish_output_rate, vlm_trigger_rate)
from gozcu.models import Handoff, Correction, Episode, Observation, Interpretation
from gozcu.store import Store


def _store(handoffs=(), observation=0, yorum=0):
    s = Store(":memory:")
    for kaynak, hedef in handoffs:
        s.save_handoff(Handoff(ts=0.0, source_agent=kaynak, target_agent=hedef,
                             reason="n", confidence=0.5, payload_ref="r"))
    for i in range(observation):
        s.save_observation(Observation(ts=float(i)))
    for i in range(yorum):
        s.save_interpretation(Interpretation(observation_ts=float(i), description="x", model="vlm",
                             tokens=100, latency_ms=500))
    return s


def test_decision_distribution_sums_to_one():
    s = _store([("router", "perception"), ("router", "perception"),
                ("router", "interpreter"), ("router", "supervisor")])
    d = decision_distribution(s)
    assert abs(sum(d.values()) - 1.0) < 1e-9
    assert d["closed_at_router"] == 0.5


def test_distribution_ignores_handoffs_written_by_other_agents():
    """sentezleyici ve risk_analisti de devir yazıyor; onları saymak manşet
    sayıyı sulandırır."""
    s = _store([("router", "perception"),
                ("synthesizer", "risk_analyst"),
                ("risk_analyst", "supervisor")])
    assert decision_distribution(s)["closed_at_router"] == 1.0


def test_distribution_is_all_zero_on_an_empty_run():
    assert sum(decision_distribution(_store()).values()) == 0.0


def test_vlm_trigger_rate_is_interpretations_over_observations():
    assert vlm_trigger_rate(_store(observation=100, yorum=3)) == 0.03


def test_trigger_rate_is_zero_not_a_crash_on_an_empty_run():
    assert vlm_trigger_rate(_store()) == 0.0


def test_token_totals_are_grouped_by_model():
    assert tokens_by_model(_store(observation=10, yorum=2))["vlm"] == 200.0


def test_correction_propagation_is_one_when_the_summary_was_updated():
    s = Store(":memory:")
    e = Episode(start_ts=0.0, phase="outcome", summary_tr="yük düştü",
               preliminary_risk="Orta")
    e.id = s.create_episode(e)
    s.save_correction(Correction(ts=0.0, episode_id=e.id, field="event_type",
                               old="araç devrildi", new="yük düştü",
                               rationale="g"))
    assert correction_propagation(s) == 1.0


def test_correction_propagation_is_zero_when_the_summary_was_not_updated():
    s = Store(":memory:")
    e = Episode(start_ts=0.0, phase="outcome", summary_tr="araç devrildi",
               preliminary_risk="Orta")
    e.id = s.create_episode(e)
    s.save_correction(Correction(ts=0.0, episode_id=e.id, field="event_type",
                               old="araç devrildi", new="yük düştü",
                               rationale="g"))
    assert correction_propagation(s) == 0.0


def test_turkish_output_rate_is_one_for_clean_turkish():
    s = Store(":memory:")
    s.create_episode(Episode(start_ts=0.0, phase="outcome",
                             summary_tr="İstif aracı devrildi, yerde hareketsiz kişi var.",
                             preliminary_risk="Kritik"))
    assert turkish_output_rate(s) == 1.0


def test_turkish_output_rate_flags_english_leakage():
    s = Store(":memory:")
    s.create_episode(Episode(start_ts=0.0, phase="outcome",
                             summary_tr="The forklift tipped over and a person is down.",
                             preliminary_risk="Kritik"))
    assert turkish_output_rate(s) == 0.0


def test_timestamp_drift_is_the_median_absolute_error():
    s = Store(":memory:")
    for ts in (10.0, 30.0):
        s.create_episode(Episode(start_ts=ts, phase="onset", summary_tr="x",
                           preliminary_risk="Orta"))
    assert timestamp_drift(s, [(12.0, 20.0), (33.0, 40.0)]) == 2.5
```

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_kpi.py -v
```
Beklenen: `ModuleNotFoundError: No module named 'benchmark'`

### 3. `benchmark/kpi.py` yaz

`benchmark/__init__.py` (boş) de gerekiyor.

```python
from collections import defaultdict

EMPTY_DISTRIBUTION = {"closed_at_router": 0.0, "to_interpreter": 0.0,
               "to_synthesizer": 0.0, "escalated": 0.0}


def decision_distribution(store) -> dict[str, float]:
    """Yönlendiricinin kararlarının nereye düştüğü.

    SADECE yönlendiricinin yazdığı devirler sayılır — sentezleyici ve risk
    analisti de devir yazıyor ve onları katmak oranları bozar.
    """
    handoffs = [d for d in store.handoffs() if d.source_agent == "router"]
    if not handoffs:
        return dict(EMPTY_DISTRIBUTION)
    n = len(handoffs)
    counter: dict[str, int] = defaultdict(int)
    for d in handoffs:
        counter[d.target_agent] += 1
    return {
        "closed_at_router": counter["perception"] / n,
        "to_interpreter": counter["interpreter"] / n,
        "to_synthesizer": counter["synthesizer"] / n,
        "escalated": counter["supervisor"] / n,
    }


def vlm_trigger_rate(store) -> float:
    """Karelerin yüzde kaçı görsel modele gitti. Hedef: %5'in altı."""
    observation = len(store.observations())
    return 0.0 if observation == 0 else len(store.interpretations()) / observation


def tokens_by_model(store) -> dict[str, float]:
    toplam: dict[str, float] = defaultdict(float)
    for y in store.interpretations():
        toplam[y.model] += y.tokens
    return dict(toplam)


def correction_propagation(store) -> float:
    """Operatör düzeltmelerinin kaçı epizot özetine yansıdı. Hedef: 1.0."""
    episodes = {e.id: e for e in store.episodes()}
    corrections = [d for eid in episodes for d in store.corrections(eid)]
    if not corrections:
        return 1.0
    yansiyan = sum(1 for d in corrections
                   if d.episode_id in episodes
                   and d.new in episodes[d.episode_id].summary_tr)
    return yansiyan / len(corrections)


def timestamp_drift(store, truth: list[tuple[float, float]]) -> float:
    """Etiketli olay başlangıcı ile en yakın epizot başlangıcı arasındaki
    medyan mutlak fark, saniye."""
    episodes = store.episodes()
    if not episodes or not truth:
        return float("nan")
    sapmalar = sorted(
        min(abs(e.start_ts - baslangic) for e in episodes)
        for start, _end in truth)
    middle = len(sapmalar) // 2
    return (sapmalar[middle] if len(sapmalar) % 2
            else (sapmalar[middle - 1] + sapmalar[middle]) / 2)
```

### 4. `benchmark/ground_truth.csv` — 5 klip yeter

15 değil, **5.** Etiketleme el işi ve zamanı yok. `data/` altındaki kliplerden
beşini seç, olay penceresini gözle işaretle.

```csv
video,has_incident,start_s,end_s,kind
forklift-accident--qOPnf-YRuk8.mp4,1,12.5,19.0,vehicle_tipover
fire-single--lleF2nmlkMY.mp4,1,4.0,22.0,fire
pl1-01--B5xphv6lYkw.mp4,0,,,yok
```

`kind` sözlüğü — sadece bunları kullan:
`vehicle_tipover` · `load_drop` · `fire` · `ppe_violation` · `fall` · `yok`

### 5. `benchmark/run.py` ve `benchmark/report.py`

`run.py` her etiketli klip için: videoyu `run_pipeline` ile koşturur, o klibin
deposunu `runs/<klip>.db` olarak saklar, `kpi.py`'daki beş fonksiyonu çağırır,
`runs/kpi.json` yazar.

`report.py` `runs/kpi.json`'u okur, `runs/kpi.md` üretir ve **decision dağılımı
çubuk grafiğini** `runs/decision-dagilimi.png` olarak kaydeder (matplotlib).
Slayta giden grafik bu.

Bir klip çökerse **koşuyu durdurma** — hatayı `kpi.json`'a yaz ve devam et.
Kısmi sonuç, hiç sonuç olmamasından iyidir.

### 6. Yeşil olduğunu gör

```bash
uv run pytest tests/test_kpi.py -v
```
Beklenen: 11 passed

### 7. Commit

```bash
git add benchmark tests/test_kpi.py
git commit -m "feat: KPI harness for decision distribution, trigger rate and drift"
```

## Doğrulama

```bash
uv run pytest tests/test_kpi.py -v
```
Beklenen: **11 passed**

## Takıldığında

Üveys'e yaz. **Bekleme** — bu sprintte bir saat, toplam kapasitenin yaklaşık %4'ü.
