# Görev 15 — KPI ve benchmark (`benchmark/`)

> ## ✅ TAMAMLANDI — 24 Ağustos 2026, `b08fce8`
>
> **KPI takımı ve benchmark koşucusu indi.** `benchmark/kpi.py`,
> `benchmark/ground_truth.py`, `benchmark/run.py`, `benchmark/report.py` var;
> `tests/test_kpi.py` ile `tests/test_benchmark.py` birlikte 58 test ile yeşil.
> Bu dosyayı yeniden uygulama — aşağısı ne yapıldığının kaydı.
>
> **Sonraki göreve başlarken bilmen gerekenler**
> ([kararlar](#tamamlanma-notları-gelecek-görevleri-bağlayan) bölümüne bak):
> **bozulmuş koşular manşetten AYRI raporlanıyor** — `decision_distribution`'ın
> beşinci kovası `degraded` ve her KPI kaydı koşu seviyesinde bir `status`
> taşıyor, çünkü aksi hâlde tamamen çökmüş bir koşu "kararların %100'ü en ucuz
> kademede kapandı" diye okunuyordu; **artefaktlar `bench/` altında** —
> versiyonlanan bir dizin, `runs/` değil, orası `.gitignore`'da ve
> ultralytics'in; ve **`tokens_by_model` artık `vision_tokens`** — `tokens`
> sistemde yalnız `Interpretation`'da kalıcı hâle geldiği için koşu geneli bir
> maliyet iddiası veriye dayanmıyor.

**Bağımlılık:** [02](02-olay-deposu.md) — `kpi.py` ve testleri için yeterli.
`benchmark/run.py` ayrıca [17](17-cikti-sozlesmesi.md)'yi bekliyor; **önce `kpi.py`'ı
yaz ve testleri yeşile al**, runner'ı 17 indikten sonra ekle. Bu sırayla hiç
beklemezsin.


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

### Depodan devraldığın iki tuzak (Görev 02)

- **`Store._read` `ORDER BY id` ile okuyor — ekleme sırası, `ts` sırası değil.**
  Kronolojik sıra varsayan her KPI ve zaman çizelgesi sıralamayı `ts` üzerinden
  kendisi yapmalı.
- **`Store`'un `close()`'u ve WAL pragma'sı yok**, bağlantı da
  `check_same_thread=False` ile açılıyor. Dosya tabanlı bir `Store`'u başka bir
  süreç yazarken okursan çekişme gerçek — klip koşusu bitmeden o dosyadan KPI
  hesaplama.

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
Store.interpretations() -> list[Interpretation]     # Interpretation.model: str, .tokens: int, .latency_ms: int
Store.episodes() -> list[Episode]   # Episode.start_ts: float
Store.handoffs() -> list[Handoff]     # Handoff.source_agent, .target_agent
Store.corrections(episode_id) -> list[Correction]   # .episode_id, .old, .new
Store.dialogue() -> list[DialogueTurn]      # .role: "supervisor" | "operator" | "system"
Store.risks() -> list[RiskAssessment]       # .rationale_tr: str
Store.db                            # ham sqlite3 bağlantısı

# gozcu/report.py  (Görev 17)
build_output(store, summary: str, root_cause=None) -> PipelineOutput
```

**Ajan adları** (`Handoff.source_agent` / `target_agent` alanlarında görürsün):
`perception`, `router`, `interpreter`, `synthesizer`, `risk_analyst`,
`supervisor`, `reporter`.

> **Görev 14 indi (`463a74c`) — `correction_propagation` ARTIK ÖLÇÜLEBİLİR.**
> Süpervizörün promptu bir zamanlar modele `gozlem_duzelt` adını öğretirken şema
> `correct_observation` tanımlıyordu: model var olmayan aracı çağırıyor, düzeltme
> hiç kaydedilmiyor ve bu KPI **yapısal olarak** sıfır okuyordu — ölçtüğü şey
> asla gerçekleşemezdi. Katalog artık şemadan türetiliyor; düzeltme kaydediliyor,
> epizot özeti güncelleniyor ve risk yeniden koşuyor. Sıfır bir okuma bundan
> sonra gerçek bir bulgudur, ölçüm arızası değil.
>
> **Diyalog sayan bir KPI `[denetim]` satırlarını ayıklamalı.** Denetim hükmü
> `store.dialogue()`'a `role="system"` ve `[denetim]` önekli bir satır olarak
> düşüyor (yalnız hüküm `safe` değilken). Bunlar model üretimi operatör metni
> değil; `turkish_output_rate` gibi üretilen metni tartan bir ölçüm ya da düz bir
> tur sayımı onları operatör diyaloğu sanarsa payda şişer.


## Ne yapacaksın

`benchmark/kpi.py` — depodan okuyan saf fonksiyonlar. Teslim edilen imzalar:

```python
decision_distribution(store) -> dict[str, float] | None
run_status(store) -> str
vlm_trigger_rate(store) -> float | None
vision_tokens(store) -> dict[str, float] | None
correction_propagation(store) -> float | None
turkish_output_rate(store) -> float | None
timestamp_drift(store, truth, seeded_episode_ids=()) -> float | None
collect(store, truth=(), seeded_episode_ids=()) -> dict
aggregate(clips) -> dict
```

`turkish_output_rate` ucuz ama önemli: yarışmanın adı **Türkçe** dil ajanları ve
modelin sessizce İngilizceye kayması en sinsi başarısızlık. Üretilen özet ve
diyalog metinlerinde İngilizce stop-word (`the`, `and`, `is`, `with`) arıyoruz.
Kasıntı Türkçe'yi yakalamaz — onun için 26 Ağustos'taki insan turu var — ama
dilin tamamen kaymasını yakalar. Arama **kelime belirteci** üzerinden yapılıyor:
alt dizeye bakan bir ölçüm `risk` içinde `is`, `hasarlı` içinde `has` görür ve
tertemiz Türkçe bir raporu "İngilizce" diye damgalar.

**`decision_distribution` için kritik uyarı:** `handoff` tablosuna sadece
yönlendirici yazmıyor — sentezleyici ve risk analisti de kendi devirlerini
yazıyor. Hepsini sayarsan oranlar 1'e toplanmaz ve manşet sayı sulanır. **Sadece
`source_agent == "router"` olan satırları say**, ve `DecisionLoop.catch_up()`'ın
`reason="telafi"` ile yazdığı telafi devrini ayıkla: o bir yönlendirici kararı
değil, döngünün kendi kaydı.

**İkinci kritik uyarı — kesinti dördüncü kovaya sığmaz.** Yönlendirici kademesi
kesintiye girdiğinde `route()` `decision="ignore"`, `confidence=0.0` döndürüyor
ve `DecisionLoop` tanımadığı kararı `TARGET.get(..., "perception")` ile
`closed_at_router`'a yazıyor. Bu hâliyle **tamamen çökmüş bir koşu, mümkün olan
en gurur verici grafiği** üretirdi. Bu yüzden beşinci bir kova var: `degraded`.

`benchmark/ground_truth.py` + `benchmark/ground_truth.csv` — etiketli klip
listesi; olay penceresi olan, olayı olup penceresi henüz işaretlenmemiş ve
olaysız klipleri birbirinden ayırır.
`benchmark/run.py` — etiketli her klibi koşturur, klip başına bir SQLite dosyası
üretir, `bench/kpi.json` yazar.
`benchmark/report.py` — onu okuyup `bench/kpi.md` ve karar dağılımı grafiğini
(`bench/decision-distribution.png`) üretir.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_kpi.py`

```python
"""Görev 15 — KPI takımı.

Bu dosya ölçümü ölçüyor. Buradaki yanlış bir sayı çökme değil, **sonuç gibi
görünen bir yalan** olurdu; testler bu yüzden üç şeyi kilitliyor:

**Bozulmuş koşu manşetten ayrılır.** Yönlendirici kesintide `confidence=0.0`
ile `ignore`'a düşüyor ve `TARGET.get(..., "perception")` de aynı kovaya
oturuyor — yani tamamen çökmüş bir koşu "kararların %100'ü en ucuz kademede
kapandı" diye okunabilirdi. `degraded` payı ayrı bir kova ve koşunun bir
durumu var.

**Boş koşu için tek sözleşme var: `None`.** Ölçülemeyen KPI JSON'da `null`
oluyor; `0.0` "ölçtük, sıfır çıktı" demek ve ikisi karıştırılamaz.

**Türkçe ölçümü alt dizeye bakmaz.** `risk` içinde `is`, `ise` içinde `is`
geçiyor; kelime sınırı olmadan her Türkçe metin İngilizce sanılırdı.
"""

import json
from unittest.mock import Mock, patch

import pytest

from benchmark.kpi import (DEGRADED, EPOCH_THRESHOLD_S, MEASURED, UNMEASURED,
                           aggregate, collect, correction_propagation,
                           decision_distribution, epoch_scale_episodes,
                           run_status, timestamp_drift, turkish_output_rate,
                           vision_tokens, vlm_trigger_rate)
from gozcu.agents.supervisor import (AUDIT_PREFIX, CORRECT_OBSERVATION,
                                     DEGRADED_REPLY, Supervisor)
from gozcu.config import MODELS
from gozcu.fixtures.loader import load_history
from gozcu.gateway import Response
from gozcu.guard import CLEAN_NOTE, Screening
from gozcu.loop import DecisionLoop
from gozcu.models import (DialogueTurn, Episode, Handoff, Interpretation,
                          Observation, RiskAssessment, RouterDecision,
                          Signals)
from gozcu.store import Store

VLM_MODEL = MODELS["vlm"]


def _store(handoffs=(), observation=0, interpretation=0):
    """`handoffs`: (source, target, confidence) üçlüleri."""
    store = Store(":memory:")
    for source, target, confidence in handoffs:
        store.save_handoff(Handoff(ts=0.0, source_agent=source,
                                   target_agent=target, reason="n",
                                   confidence=confidence, payload_ref="r"))
    for i in range(observation):
        store.save_observation(Observation(ts=float(i)))
    for i in range(interpretation):
        store.save_interpretation(Interpretation(
            observation_ts=float(i), description="x", model=VLM_MODEL,
            tokens=100, latency_ms=500))
    return store


def _episode(store, summary="istif aracı devrildi", start_ts=0.0,
             risk="Orta"):
    episode = Episode(start_ts=start_ts, phase="outcome", summary_tr=summary,
                      preliminary_risk=risk)
    episode.id = store.create_episode(episode)
    return episode


# --- karar dağılımı --------------------------------------------------------

def test_decision_distribution_sums_to_one():
    store = _store([("router", "perception", 0.8), ("router", "perception", 0.7),
                    ("router", "interpreter", 0.6),
                    ("router", "supervisor", 0.9)])
    distribution = decision_distribution(store)
    assert abs(sum(distribution.values()) - 1.0) < 1e-9
    assert distribution["closed_at_router"] == 0.5


def test_distribution_ignores_handoffs_written_by_other_agents():
    """Sentezleyici ve risk analisti de devir yazıyor; onları saymak manşet
    sayıyı sulandırır."""
    store = _store([("router", "perception", 0.8),
                    ("synthesizer", "risk_analyst", 0.5),
                    ("risk_analyst", "supervisor", 0.5)])
    assert decision_distribution(store)["closed_at_router"] == 1.0


def test_a_fully_degraded_run_is_not_reported_as_perfect_filtering():
    """Kesintide yönlendirici `ignore`/`confidence=0.0`'a düşüyor ve hedef
    `perception` oluyor. Bu koşu 'her karar en ucuz kademede kapandı' diye
    okunursa, tamamen çökmüş bir sistem en gurur verici grafiği üretir."""
    store = _store([("router", "perception", 0.0),
                    ("router", "perception", 0.0)])
    distribution = decision_distribution(store)
    assert distribution["degraded"] == 1.0
    assert distribution["closed_at_router"] == 0.0
    assert run_status(store) == DEGRADED


def test_a_healthy_run_is_reported_as_measured():
    store = _store([("router", "perception", 0.8),
                    ("router", "interpreter", 0.7)])
    assert run_status(store) == MEASURED
    assert decision_distribution(store)["degraded"] == 0.0


def test_catch_up_handoffs_do_not_inflate_the_synthesizer_share():
    """`DecisionLoop._handoff` telafi devrini de `source_agent="router"` diye
    yazıyor. Gerçek döngü üzerinden koşuluyor: kaynağı taklit eden bir test
    bu sızıntıyı göremezdi."""
    store = Store(":memory:")
    degraded = {"on": True}
    observations = [Observation(ts=float(i), signals=Signals(person_count=1))
                    for i in range(3)]
    loop = DecisionLoop(
        store,
        route=lambda window: RouterDecision(decision="inspect",
                                            rationale="bakılsın",
                                            confidence=0.8),
        interpret=lambda window: None,
        synthesize=lambda window, interpretation, decision: None,
        is_degraded=lambda: degraded["on"])
    list(loop.run(observations))
    degraded["on"] = False
    list(loop.catch_up())

    assert [h.reason for h in store.handoffs()].count("telafi") == 1
    distribution = decision_distribution(store)
    assert distribution["to_interpreter"] == 1.0
    assert distribution["to_synthesizer"] == 0.0


def test_distribution_is_not_measured_on_an_empty_run():
    assert decision_distribution(_store()) is None
    assert run_status(_store()) == UNMEASURED


# --- görü tetikleme --------------------------------------------------------

def test_vlm_trigger_rate_is_interpretations_over_observations():
    assert vlm_trigger_rate(_store(observation=100, interpretation=3)) == 0.03


def test_trigger_rate_is_not_measured_on_an_empty_run():
    assert vlm_trigger_rate(_store()) is None


# --- token muhasebesi ------------------------------------------------------

def test_vision_tokens_are_grouped_by_the_recorded_model_id():
    """Anahtar `Interpretation.model`'in gerçekten taşıdığı şey — kademe
    takma adı değil, gateway'in döndürdüğü model kimliği."""
    assert vision_tokens(_store(observation=10,
                                interpretation=2))[VLM_MODEL] == 200.0


def test_vision_tokens_are_not_measured_when_nothing_was_interpreted():
    assert vision_tokens(_store(observation=10)) is None


# --- düzeltme yayılımı -----------------------------------------------------

def _corrected_store(episode_id: int) -> Store:
    """Gerçek süpervizörü bir `correct_observation` çağrısıyla koşturur.

    Elle kurulmuş bir depo bu KPI'ı hiç ölçmezdi: ölçülen şey tam olarak
    `Supervisor._apply_correction`'ın düzeltmeyi nereye yaydığı.
    """
    gateway = Mock()
    stream = iter([
        Response(tool_calls=[{"id": "c1", "type": "function", "function": {
            "name": CORRECT_OBSERVATION,
            "arguments": json.dumps({"episode_id": episode_id,
                                     "field": "event_type",
                                     "old": "araç devrildi",
                                     "new": "yük düştü",
                                     "rationale": "operatör gözlemi"})}}]),
        Response(content="Anlaşıldı, kaydı güncelledim."),
    ])
    gateway.ask.side_effect = lambda *args, **kwargs: next(stream)

    store = Store(":memory:")
    episode = _episode(store, "araç devrildi")
    risk = RiskAssessment(episode_id=episode.id, level="Orta",
                          rationale_tr="gerekçe", preventable=True)
    with patch("gozcu.agents.supervisor.assess_risk", return_value=risk), \
         patch("gozcu.agents.supervisor.screen_text",
               side_effect=lambda gw, text, critical=False:
               Screening(text, "safe", CLEAN_NOTE)):
        Supervisor(gateway, store).talk("araç devrilmedi, yük düştü")
    return store


def test_correction_propagation_is_one_when_the_supervisor_lands_it():
    assert correction_propagation(_corrected_store(episode_id=1)) == 1.0


def test_correction_propagation_is_zero_when_the_episode_does_not_exist():
    """Model var olmayan bir epizot kimliği uydurduğunda düzeltme deftere
    düşüyor ama hiçbir yere yayılmıyor — ölçüm bunu görmeli."""
    assert correction_propagation(_corrected_store(episode_id=999)) == 0.0


def test_correction_propagation_is_not_applicable_without_corrections():
    """Hiç düzeltme yoksa 1.0 okumak, operatörle hiç konuşmamış bir koşuya
    tam not vermek olurdu."""
    store = Store(":memory:")
    _episode(store)
    assert correction_propagation(store) is None


# --- Türkçe oranı ----------------------------------------------------------

def test_turkish_output_rate_is_one_for_clean_turkish():
    store = Store(":memory:")
    _episode(store, "İstif aracı devrildi, yerde hareketsiz kişi var.")
    assert turkish_output_rate(store) == 1.0


def test_turkish_output_rate_flags_english_leakage():
    store = Store(":memory:")
    _episode(store, "The forklift tipped over and a person is down.")
    assert turkish_output_rate(store) == 0.0


def test_turkish_words_that_embed_english_stopwords_are_not_flagged():
    """`risk` içinde `is`, `ise` içinde `is`, `iş` içinde `is` yok ama alt
    dize araması üçünü de yakalardı. `"İ".lower()` de iki kod noktası üretir."""
    store = Store(":memory:")
    _episode(store, "İSG riski yüksek; hasarlı istif aracı iş "
                   "durdurulmadan çekilsin.")
    _episode(store, "İŞ GÜVENLİĞİ İHLALİ TESPİT EDİLDİ")
    assert turkish_output_rate(store) == 1.0


def test_turkish_words_colliding_with_english_stopwords_are_not_flagged():
    """`not`, `at`, `on`, `in` gerçek Türkçe kelimeler — stop-word listesinde
    olmamaları bilinçli bir seçim ve test bunu kilitliyor."""
    store = Store(":memory:")
    _episode(store, "Not: on numaralı at arabası hattın içinde bekliyor.")
    assert turkish_output_rate(store) == 1.0


def test_system_rows_are_not_counted_as_model_output():
    """`[denetim]` hükümleri ve elle yazılmış arıza metinleri model üretimi
    değil; paydaya girerlerse oran şişer ya da sulanır."""
    store = Store(":memory:")
    store.save_dialogue(DialogueTurn(ts=0.0, role="supervisor",
                                     text="Hat durduruldu, ekip yolda."))
    store.save_dialogue(DialogueTurn(
        ts=0.0, role="system",
        text=f"{AUDIT_PREFIX} the verdict is unsafe and the text was blocked"))
    store.save_dialogue(DialogueTurn(ts=0.0, role="system",
                                     text=DEGRADED_REPLY))
    store.save_dialogue(DialogueTurn(ts=0.0, role="operator",
                                     text="what happened over there"))
    assert turkish_output_rate(store) == 1.0


def test_turkish_rate_covers_summaries_dialogue_and_risk_rationales():
    store = Store(":memory:")
    episode = _episode(store, "Yük düştü, kimse yaralanmadı.")
    store.save_dialogue(DialogueTurn(ts=0.0, role="supervisor",
                                     text="Yük düştü, ekip bölgede."))
    store.save_risk(RiskAssessment(
        episode_id=episode.id, level="Orta",
        rationale_tr="The load fell because the mast was overloaded.",
        preventable=True))
    assert turkish_output_rate(store) == pytest.approx(2 / 3)


def test_turkish_rate_is_not_measured_without_generated_text():
    assert turkish_output_rate(Store(":memory:")) is None


# --- zaman sapması ---------------------------------------------------------

def test_timestamp_drift_is_the_median_absolute_error():
    store = Store(":memory:")
    for ts in (10.0, 30.0):
        _episode(store, start_ts=ts)
    assert timestamp_drift(store, [(12.0, 20.0), (33.0, 40.0)]) == 2.5


def test_archive_episodes_are_not_counted_as_detections():
    """`load_history` arşiv olaylarını epizot olarak tohumluyor. Onlar tespit
    değil; sayılırlarsa sapma sahte biçimde küçülür."""
    store = Store(":memory:")
    archived = _episode(store, "arşiv olayı", start_ts=0.0)
    _episode(store, "canlı olay", start_ts=10.0)
    assert timestamp_drift(store, [(2.0, 8.0)]) == 2.0
    assert timestamp_drift(store, [(2.0, 8.0)],
                           seeded_episode_ids={archived.id}) == 8.0


def test_drift_is_not_measured_without_labelled_windows():
    store = Store(":memory:")
    _episode(store, start_ts=10.0)
    assert timestamp_drift(store, []) is None
    assert timestamp_drift(Store(":memory:"), [(1.0, 2.0)]) is None


# --- arşiv zaman birimi ----------------------------------------------------

def test_no_episode_in_the_store_carries_an_epoch_timestamp():
    """`Episode.start_ts` video saniyesi. Arşiv fikstürleri bir zamanlar aynı
    sütunda epoch saniyesi taşıyordu ve `mmss()` onları `99:59`'a yapıştırıp
    makul görünen yanlış bir saat basıyordu."""
    gateway = Mock()
    gateway.embed.return_value = [0.1, 0.2]
    store = Store(":memory:")
    load_history(gateway, store)

    assert store.episodes(), "arşiv boş yüklendi"
    assert all(e.start_ts < EPOCH_THRESHOLD_S for e in store.episodes())
    assert all((e.end_ts or 0.0) < EPOCH_THRESHOLD_S for e in store.episodes())
    assert epoch_scale_episodes(store) == []


def test_epoch_scale_episodes_names_the_offender():
    store = Store(":memory:")
    offender = _episode(store, "epoch damgalı olay", start_ts=1786567260.0)
    assert [e.id for e in epoch_scale_episodes(store)] == [offender.id]


# --- toplama ---------------------------------------------------------------

KPI_KEYS = {"decision_distribution", "vlm_trigger_rate", "vision_tokens",
            "correction_propagation", "timestamp_drift_s",
            "turkish_output_rate"}


def test_collect_reports_every_kpi_and_the_run_status():
    store = _store([("router", "perception", 0.8)], observation=10,
                   interpretation=1)
    record = collect(store)
    assert record["status"] == MEASURED
    assert set(record["kpis"]) == KPI_KEYS


def test_aggregate_averages_only_measured_clips():
    """Bozulmuş klip ortalamaya girerse manşet sayı sulanır."""
    measured = collect(_store([("router", "perception", 0.8),
                               ("router", "interpreter", 0.8)],
                              observation=10, interpretation=1))
    broken = collect(_store([("router", "perception", 0.0)] * 4))
    summary = aggregate([{"video": "a", "error": None, **measured},
                         {"video": "b", "error": None, **broken}])
    assert summary["clips"] == {"total": 2, "measured": 1, "degraded": 1,
                                "unmeasured": 0, "error": 0}
    assert summary["status"] == DEGRADED
    assert summary["kpis"]["decision_distribution"]["closed_at_router"] == 0.5
    assert summary["kpis"]["vlm_trigger_rate"] == 0.1


def test_aggregate_is_unmeasured_when_no_clip_could_be_measured():
    summary = aggregate([{"video": "a", "error": "video yok",
                          "status": UNMEASURED, "kpis": {}}])
    assert summary["status"] == UNMEASURED
    assert summary["kpis"]["decision_distribution"] is None
    assert set(summary["kpis"]) == KPI_KEYS
```

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_kpi.py -v
```
Beklenen: `ModuleNotFoundError: No module named 'benchmark'`

### 3. `benchmark/kpi.py` yaz

`benchmark/__init__.py` (boş) de gerekiyor.

```python
"""Ölçüm katmanı — depodaki kayıtlardan hesaplanan saf fonksiyonlar.

Bu modül fikstür, gateway, dosya sistemi ve ağ görmez: girdisi bir `Store`,
çıktısı sayılardır. Sunumun manşet grafiği (`decision_distribution`) buradan
çıkıyor, dolayısıyla buradaki yanlış bir sayı bir çökme değil — **sonuç gibi
görünen bir yalan** olurdu. Üç tasarım kararı bunu engellemek için var:

**Bozulmuş koşu manşetten ayrılır.** Yönlendirici kademesi kesintiye
girdiğinde `route()` `decision="ignore"`, `confidence=0.0` döndürüyor;
`DecisionLoop` de tanımadığı kararı `TARGET.get(..., "perception")` ile aynı
hedefe yazıyor. İkisi de `closed_at_router` kovasına düşerdi ve **tamamen
çökmüş bir koşu, mümkün olan en gurur verici grafiği** üretirdi. Bu yüzden
`confidence == 0.0` devirleri ayrı bir `degraded` payına gidiyor ve koşunun
bir durumu var (`run_status`).

**Boş koşu için tek sözleşme: `None`.** Ölçülemeyen her KPI `None` döner ve
JSON'da `null` olur. `0.0` "ölçtük, sıfır çıktı" demek; `1.0` ise hiç
operatör düzeltmesi olmayan bir koşuya tam not vermek olurdu. `nan` zaten
geçerli JSON değil.

**Ölçüm, ölçebildiğini söyler.** `vision_tokens` yalnız görü kademesinin
token'larını sayabiliyor çünkü `tokens` sistemde tek bir yerde
(`Interpretation`) kalıcı hâle geliyor; koşu geneli maliyet iddiası veriye
dayanmaz ve bu yüzden üretilmiyor.
"""

import re
import unicodedata
from collections import defaultdict
from statistics import median

#: Koşu durumları. `measured` = sayılar bir şey ifade ediyor; `degraded` =
#: kararların kayda değer bir kısmı kesintiden geldi, grafik okunmamalı;
#: `unmeasured` = yönlendirici hiç karar vermemiş, ölçülecek bir şey yok.
MEASURED = "measured"
DEGRADED = "degraded"
UNMEASURED = "unmeasured"

#: Koşuyu `degraded` sayan eşik: devirlerin beşte birinden fazlası kesinti
#: kaynaklıysa manşet sayı okunamaz. Tek bir bozuk JSON bütün koşuyu
#: damgalamasın diye sıfır değil.
DEGRADED_RUN_THRESHOLD = 0.2

#: `DecisionLoop.catch_up()`'ın telafi devrine yazdığı gerekçe. `_handoff`
#: her deviri `source_agent="router"` diye yazıyor, yani telafi devirleri
#: yönlendiricinin gerçek kararlarından **yalnız** bu gerekçeyle ayrılabiliyor
#: (bkz. `router_handoffs`).
CATCH_UP_REASON = "telafi"

#: Video saniyesi ile epoch saniyesi arasındaki sınır. `Episode.start_ts`
#: videonun kaçıncı saniyesi demek; 1e9 (2001) üstü bir değer o sütuna epoch
#: damgası yazıldığının kanıtıdır. `mmss()` böyle bir değeri `99:59`'a
#: yapıştırır ve rapor makul görünen yanlış bir saat basar.
EPOCH_THRESHOLD_S = 1e9

DECISION_BUCKETS = ("closed_at_router", "to_interpreter", "to_synthesizer",
                    "escalated", "degraded")

#: Yönlendirici kararının hedef ajanı -> kova adı.
_BUCKET_BY_TARGET = {"perception": "closed_at_router",
                     "interpreter": "to_interpreter",
                     "synthesizer": "to_synthesizer",
                     "supervisor": "escalated"}


# --- devirler --------------------------------------------------------------

def router_handoffs(store) -> list:
    """Yönlendiricinin **kendi kararları**; telafi devirleri hariç.

    İki ayıklama var ve ikisi de manşet sayıyı korur:

    1. Sentezleyici ve risk analisti de `handoff` tablosuna yazıyor. Hepsini
       saymak oranları 1'e toplamaz.
    2. `DecisionLoop.catch_up()` kesinti telafisinde `source_agent="router"`,
       `target_agent="synthesizer"` bir devir yazıyor — yönlendiricinin
       verdiği bir karar değil, döngünün kendi kaydı. Sayılırsa
       `to_synthesizer` payı şişer.

    **Sınırı açıkça söylemek gerekir:** telafi devri yalnız `reason` alanıyla
    ayırt edilebiliyor (`loop.py` kaynağı sabit yazıyor ve bu görev ona
    dokunmuyor). Gerekçe modelden gelen bir metin olduğu için, yönlendirici
    bir gün gerekçesini tam olarak `"telafi"` yazar ve hedefi sentezleyici
    olursa o karar da ayıklanır. Üçlü eşleşme (kaynak + hedef + gerekçe) bu
    olasılığı küçültüyor; sıfırlamıyor.
    """
    return [h for h in store.handoffs()
            if h.source_agent == "router"
            and not (h.target_agent == "synthesizer"
                     and h.reason == CATCH_UP_REASON)]


def decision_distribution(store) -> dict[str, float] | None:
    """Yönlendiricinin kararlarının nereye düştüğü; beş pay 1'e toplanır.

    Dördü gerçek kararlar, beşincisi (`degraded`) kesintiden gelen
    devirlerdir. Beşi de **aynı paydaya** (toplam yönlendirici devri) bölünür:
    böylece tamamen çökmüş bir koşuda `degraded` payı 1.0 okur ve grafiğe
    bakan kişi "mükemmel filtreleme" değil, "bu koşu ölçülemedi" görür.

    Hiç yönlendirici devri yoksa `None` — ölçülecek karar yok.

    `confidence == 0.0` kesintinin işareti olarak kullanılıyor: `route()`'un
    `_fallback`'i bunu bilerek sıfır veriyor. Gerçekten sıfır güvenle
    dönen bir model kararı da bu kovaya düşer; kaydedilen tek ayırt edici
    alan bu.
    """
    handoffs = router_handoffs(store)
    if not handoffs:
        return None

    total = len(handoffs)
    counter: dict[str, int] = defaultdict(int)
    for handoff in handoffs:
        if handoff.confidence == 0.0:
            counter["degraded"] += 1
            continue
        bucket = _BUCKET_BY_TARGET.get(handoff.target_agent)
        if bucket is not None:
            counter[bucket] += 1
    return {bucket: counter[bucket] / total for bucket in DECISION_BUCKETS}


def run_status(store) -> str:
    """Koşunun sayıları okunabilir mi: `measured` / `degraded` / `unmeasured`.

    Rapor ve konsol bunu tek bakışta göstermek için okuyor. Bir KPI tablosu,
    okuyanına o tablodaki sayıların bir anlam taşıyıp taşımadığını
    söylemeden yayınlanamaz.
    """
    distribution = decision_distribution(store)
    if distribution is None:
        return UNMEASURED
    return (DEGRADED if distribution["degraded"] > DEGRADED_RUN_THRESHOLD
            else MEASURED)


# --- görü kademesi ---------------------------------------------------------

def vlm_trigger_rate(store) -> float | None:
    """Gözlemlerin yüzde kaçı görsel modele gitti. Hedef: %5'in altı.

    Hiç gözlem yoksa `None`: sıfır gözlemde oran tanımsızdır, sıfır değil.
    """
    observations = len(store.observations())
    if observations == 0:
        return None
    return len(store.interpretations()) / observations


def vision_tokens(store) -> dict[str, float] | None:
    """**Yalnız görü kademesinin** token'ları, kaydedilen model kimliği başına.

    Adı bilerek `tokens_by_model` değil. Sistemde `tokens` tek bir yerde
    kalıcı hâle geliyor — `Interpretation` — yani yönlendirici, ana model,
    denetim, gömme ve yeniden sıralama kademelerinin token'ları hiçbir yerde
    yazmıyor. "Model başına token" adı taşıyan bir çıktı koşu geneli bir
    maliyet tablosu vaat ederdi; veri bunu desteklemiyor ve desteklemeyen bir
    maliyet iddiası yayınlanmaz.

    Anahtar `Interpretation.model`'in gerçekten taşıdığı değer: gateway'in
    döndürdüğü model kimliği (`gozcu.config.MODELS["vlm"]`), kademe takma adı
    değil.
    """
    interpretations = store.interpretations()
    if not interpretations:
        return None
    totals: dict[str, float] = defaultdict(float)
    for interpretation in interpretations:
        totals[interpretation.model] += interpretation.tokens
    return dict(totals)


# --- operatör düzeltmeleri -------------------------------------------------

def _all_corrections(store) -> list:
    """Depodaki bütün düzeltmeler.

    `Store.corrections()` epizot kimliği istiyor, yani var olmayan bir
    epizoda yazılmış düzeltme onunla hiç görünmez — oysa ölçmek istediğimiz
    arıza tam olarak o. Kimlik listesi bu yüzden doğrudan tablodan okunuyor;
    satırların çözümü yine `Store` üzerinden yapılıyor.
    """
    ids = [row[0] for row in
           store.db.execute("SELECT DISTINCT episode_id FROM correction")]
    return [c for episode_id in ids for c in store.corrections(episode_id)]


def correction_propagation(store) -> float | None:
    """Operatör düzeltmelerinin kaçı **gerçek bir epizoda** oturdu. Hedef: 1.0.

    Ne ölçtüğü konusunda dürüst olmak gerekiyor. `Supervisor._apply_correction`
    özette `replace(old, new)` yapıyor ve bu boşa çıktığında düzeltmeyi
    `"(operatör düzeltmesi: …)"` diye **ekliyor** — yani epizot bulunduğu
    sürece yeni metin özette her hâlükârda bulunur. Dolayısıyla "yeni metin
    özette mi" sorusu tek başına asla başarısız olamaz; ölçüm 1.0'da çakılı
    kalırdı.

    Gerçekten başarısız olabilen şey şu: modelin verdiği `episode_id` var
    olmayan bir epizodu gösterdiğinde düzeltme deftere yazılır, `warning` ile
    döner ve **hiçbir yere yayılmaz** — özet güncellenmez, risk yeniden
    koşmaz. Bu KPI onu sayıyor: düzeltmenin kimliği gerçek bir epizoda
    çözülüyor mu ve o epizodun özeti düzeltilmiş metni taşıyor mu.

    Ölçemediği: `Correction` doğrulamasında düşen çağrılar. Onlar deftere hiç
    yazılmadığı için paydada görünmezler; o arıza `_apply_correction`'ın
    döndürdüğü hata metninde ve diyalog dökümünde aranır.

    Hiç düzeltme yoksa `None`. Operatörle hiç konuşulmamış bir koşuya 1.0
    vermek, yapılmamış bir işi tam puanla ödüllendirmek olurdu.
    """
    corrections = _all_corrections(store)
    if not corrections:
        return None
    episodes = {e.id: e for e in store.episodes()}
    landed = sum(1 for correction in corrections
                 if correction.episode_id in episodes
                 and correction.new in episodes[correction.episode_id].summary_tr)
    return landed / len(corrections)


# --- Türkçe kalma oranı ----------------------------------------------------

#: İngilizce stop-word listesi. Yalnız işlev kelimeleri; içerik kelimeleri
#: (`forklift`, `report`) Türkçe metinde de teknik terim olarak geçebiliyor.
#:
#: Türkçede gerçek kelime olan İngilizce stop-word'ler listeden BİLEREK
#: çıkarıldı: `not` (bilgi notu), `at` (hayvan), `on` (sayı), `an` (zaman
#: birimi), `in` (mağara), `it` (hayvan), `her` (nicelik), `as` (asmak),
#: `a` (ünlem). Bunları saymak Türkçe metni İngilizce sanmaya yol açardı.
ENGLISH_STOPWORDS = frozenset({
    "the", "and", "is", "are", "was", "were", "be", "been", "being",
    "with", "without", "that", "this", "these", "those", "from", "for",
    "have", "has", "had", "will", "would", "should", "could", "there",
    "they", "them", "their", "which", "what", "when", "where", "who",
    "because", "about", "into", "onto", "over", "under", "after", "before",
    "your", "you", "our", "his", "she", "he", "we", "of", "to", "or",
    "but", "if", "then", "than", "also", "while", "during", "between",
})

#: Bir metni "İngilizceye kaymış" saymak için gereken **farklı** stop-word
#: sayısı. Tek eşleşme rastlantı olabilir: Türkçe `is` (kurum) kelimesi
#: `"İs"` biçiminde yazıldığında birleştirici nokta atıldıktan sonra
#: İngilizce `is`'e denk düşer. İki farklı işlev kelimesi ise dilin
#: kaydığının kanıtıdır.
MIN_STOPWORD_HITS = 2

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
_COMBINING_DOT = "\u0307"


def _fold(word: str) -> str:
    """Kelimeyi karşılaştırılabilir hâle getirir.

    `"İ".casefold()` **iki** kod noktası üretir (`i` + U+0307); ham
    karşılaştırma büyük harfli Türkçe metinde hiçbir şeyi eşleştiremez ve
    ölçüm sessizce kör kalırdı. Birleştirici nokta bu yüzden ayrıştırılıp
    atılıyor.
    """
    folded = unicodedata.normalize("NFD", word.casefold())
    return folded.replace(_COMBINING_DOT, "")


def looks_english(text: str) -> bool:
    """Metin İngilizceye kaymış mı.

    Kural: metin **kelime sınırlarıyla** ayrıştırılır ve en az
    `MIN_STOPWORD_HITS` farklı İngilizce stop-word içeriyorsa kaymış sayılır.

    Alt dize araması bilerek kullanılmıyor: `risk` içinde `is`, `hasarlı`
    içinde `has`, `istif` içinde `is` geçiyor. Alt dizeye bakan bir ölçüm
    tertemiz Türkçe bir raporu "İngilizce" diye damgalar — ve o damga
    yarışmanın adı Türkçe olan bir kategoride en pahalı yanlış ölçümdür.
    """
    hits = {token for token in map(_fold, _WORD.findall(text))
            if token in ENGLISH_STOPWORDS}
    return len(hits) >= MIN_STOPWORD_HITS


def generated_texts(store) -> list[str]:
    """Ölçüme giren korpus: **modelin ürettiği, insana görünen** metinler.

    Üç kaynak: süpervizörün diyalog satırları (`role == "supervisor"`),
    epizot özetleri (`summary_tr`) ve risk gerekçeleri (`rationale_tr`).

    `role == "system"` satırları korpusun dışında ve bu bir ayrıntı değil:
    o rolde iki farklı şey yatıyor ve **ikisi de model üretimi değil** —
    `AUDIT_PREFIX` önekli denetim hükümleri ve elle yazılmış Türkçe arıza
    metinleri (`DEGRADED_REPLY` gibi). Arıza metinleri her zaman Türkçe
    olduğu için oranı yapay olarak yukarı çeker, denetim hükümleri ise
    payda şişirir. `role == "operator"` da haliyle dışarıda: operatörün ne
    yazdığı sistemin dil performansı değildir.
    """
    texts = [turn.text for turn in store.dialogue()
             if turn.role == "supervisor"]
    texts += [episode.summary_tr for episode in store.episodes()]
    texts += [risk.rationale_tr for risk in store.risks()]
    return [text for text in texts if text and text.strip()]


def turkish_output_rate(store) -> float | None:
    """Üretilen operatör metninin ne kadarı Türkçe kaldı. Hedef: 1.0.

    Yarışmanın adı **Türkçe** dil ajanları ve modelin sessizce İngilizceye
    kayması en sinsi başarısızlık: sistem çalışmaya devam eder, çıktılar
    makul görünür, teslim değersizleşir. Kasıntı Türkçe'yi yakalamaz — onun
    için insan turu var — ama dilin tamamen kaymasını yakalar.

    Korpus `generated_texts()`'te tanımlı. Hiç üretilmiş metin yoksa `None`.
    """
    texts = generated_texts(store)
    if not texts:
        return None
    return sum(1 for text in texts if not looks_english(text)) / len(texts)


# --- zaman doğruluğu -------------------------------------------------------

def epoch_scale_episodes(store) -> list:
    """`start_ts`'i epoch ölçeğinde olan epizotlar — boş olmalı.

    `Episode.start_ts` **video saniyesi**. Arşiv fikstürleri bir zamanlar aynı
    sütuna epoch saniyesi (`1786567260.0`) yazıyordu; `mmss()` onu `99:59`'a
    yapıştırıyor ve rapor ile konsol makul görünen yanlış bir saat basıyordu.
    Olayın takvim tarihi fikstürün `occurred_at` / `date` alanlarında yaşıyor,
    epizot satırında değil.
    """
    return [e for e in store.episodes()
            if e.start_ts >= EPOCH_THRESHOLD_S
            or (e.end_ts or 0.0) >= EPOCH_THRESHOLD_S]


def detections(store, seeded_episode_ids=()) -> list:
    """Bu koşuda **tespit edilmiş** epizotlar.

    Arşiv olayları (`load_history`) da epizot satırı olarak duruyor ve hiçbir
    alanları onları canlı tespitten ayırmıyor. Ayırt eden tek güvenilir bilgi
    çağıranda: koşu başlamadan önce depoda hangi epizotların olduğu. Benchmark
    koşucusu tohumlamadan hemen sonra kimlikleri alıp buraya veriyor.
    """
    seeded = set(seeded_episode_ids)
    return [e for e in store.episodes() if e.id not in seeded]


def timestamp_drift(store, truth: list[tuple[float, float]],
                    seeded_episode_ids=()) -> float | None:
    """Etiketli olay başlangıcı ile en yakın epizot başlangıcı arasındaki
    medyan mutlak fark, saniye.

    `truth` yalnızca **gerçekten olay içeren** pencerelerden oluşmalı;
    `benchmark.ground_truth.load_ground_truth()` `has_incident=0` satırlarını
    ve penceresi henüz işaretlenmemiş satırları zaten ayıklıyor (boş bir
    `start_s` alanında `float("")` istisna atar).

    Etiketli pencere yoksa ya da hiç tespit yoksa `None` döner: sıfır sapma
    "mükemmel isabet" demek olurdu ve hiçbir şey tespit etmemiş bir koşu böyle
    okunamaz.
    """
    episodes = detections(store, seeded_episode_ids)
    if not episodes or not truth:
        return None
    drifts = [min(abs(episode.start_ts - start) for episode in episodes)
              for start, _end in truth]
    return float(median(drifts))


# --- klip ve koşu özeti ----------------------------------------------------

def collect(store, truth: list[tuple[float, float]] = (),
            seeded_episode_ids=()) -> dict:
    """Tek bir klip için bütün KPI'lar ve koşunun durumu.

    Dönen sözlük `bench/kpi.schema.json`'daki `clip` kaydının gövdesi;
    `video` ve `error` alanlarını koşucu ekliyor.
    """
    return {
        "status": run_status(store),
        "kpis": {
            "decision_distribution": decision_distribution(store),
            "vlm_trigger_rate": vlm_trigger_rate(store),
            "vision_tokens": vision_tokens(store),
            "correction_propagation": correction_propagation(store),
            "timestamp_drift_s": timestamp_drift(store, list(truth),
                                                 seeded_episode_ids),
            "turkish_output_rate": turkish_output_rate(store),
        },
    }


KPI_KEYS = ("decision_distribution", "vlm_trigger_rate", "vision_tokens",
            "correction_propagation", "timestamp_drift_s",
            "turkish_output_rate")

_SCALAR_KPIS = ("vlm_trigger_rate", "correction_propagation",
                "timestamp_drift_s", "turkish_output_rate")


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def aggregate(clips: list[dict]) -> dict:
    """Klip kayıtlarını koşu özetine indirger.

    **Ortalamalara yalnız `measured` klipler girer.** Bozulmuş bir klibin
    dağılımı büyük ölçüde `degraded` payından ibaret; onu ortalamaya katmak
    manşet sayıyı sulandırır ve kesintiyi başarı gibi gösterir. Bozulmuş ve
    çöken klipler kaybolmuyor — `clips` sayacında adıyla duruyorlar.
    """
    counts = {"total": len(clips), "measured": 0, "degraded": 0,
              "unmeasured": 0, "error": 0}
    measured: list[dict] = []
    for clip in clips:
        if clip.get("error"):
            counts["error"] += 1
            continue
        status = clip.get("status", UNMEASURED)
        counts[status] = counts.get(status, 0) + 1
        if status == MEASURED:
            measured.append(clip.get("kpis") or {})

    kpis: dict = {key: None for key in KPI_KEYS}
    for key in _SCALAR_KPIS:
        kpis[key] = _mean([k[key] for k in measured if k.get(key) is not None])

    distributions = [k["decision_distribution"] for k in measured
                     if k.get("decision_distribution")]
    if distributions:
        kpis["decision_distribution"] = {
            bucket: sum(d[bucket] for d in distributions) / len(distributions)
            for bucket in DECISION_BUCKETS}

    token_tables = [k["vision_tokens"] for k in measured
                    if k.get("vision_tokens")]
    if token_tables:
        totals: dict[str, float] = defaultdict(float)
        for table in token_tables:
            for model, tokens in table.items():
                totals[model] += tokens
        kpis["vision_tokens"] = dict(totals)

    if counts["measured"] == 0 and counts["degraded"] == 0:
        status = UNMEASURED
    elif (counts["measured"] == 0 or counts["degraded"] or counts["error"]
          or counts["unmeasured"]):
        status = DEGRADED
    else:
        status = MEASURED
    return {"status": status, "clips": counts, "kpis": kpis}
```

### 4. `benchmark/ground_truth.py` ve `benchmark/ground_truth.csv`

Beş klip yeter — 15 değil. Etiketleme el işi ve zamanı yok. Yükleyicinin
sözleşmesi:

```python
Clip(video, has_incident, window, kind)     # .labelled, .unlabelled
load_ground_truth(path=DEFAULT_PATH) -> list[Clip]
windows(clips) -> list[tuple[float, float]]     # yalnız işaretli pencereler
GroundTruthError                                # bozuk satırda yüksek sesle durur
```

`kind` sözlüğü — sadece bunlar:
`vehicle_tipover` · `load_drop` · `fire` · `ppe_violation` · `fall` · `yok`

Teslim edilen dosya (pencereler **bilerek boş**: onları videoyu izleyen bir
insan koyar, buraya tahmin yazılmaz):

```csv
# Gözcü benchmark etiketleri — yollar data/ dizinine görelidir.
#
# start_s / end_s BOŞ ise o klibin olay penceresi HENÜZ İŞARETLENMEDİ.
# Pencereyi videoyu izleyen bir insan koyar; buraya tahmin yazılmaz.
# İşaretsiz satırlar zaman sapması ölçümüne girmez ve koşu raporunda
# "etiketsiz" olarak sayılır — sıfır sapma diye okunmazlar.
#
# kind sözlüğü: vehicle_tipover | load_drop | fire | ppe_violation | fall | yok
video,has_incident,start_s,end_s,kind
clips/forklift/forklift-compilation--N9bG-sOU6LE/forklift-compilation--N9bG-sOU6LE-k03.mp4,1,,,load_drop
clips/forklift/forklift-compilation--N9bG-sOU6LE/forklift-compilation--N9bG-sOU6LE-k05.mp4,1,,,vehicle_tipover
clips/forklift/forklift-compilation--N9bG-sOU6LE/forklift-compilation--N9bG-sOU6LE-k09.mp4,1,,,load_drop
clips/yangin/fire-single--lleF2nmlkMY/fire-single--lleF2nmlkMY-k01.mp4,1,,,fire
clips/yangin/fire-single--lleF2nmlkMY/fire-single--lleF2nmlkMY-k03.mp4,0,,,yok
```

### 5. `benchmark/run.py`, `benchmark/report.py` ve `tests/test_benchmark.py`

`run.py` her etiketli klip için: videoyu `run_pipeline` ile koşturur, o klibin
deposunu `bench/stores/<klip>.db` olarak saklar, `kpi.collect()` çağırır ve
`bench/kpi.json` yazar. `report.py` onu okuyup `bench/kpi.md` ile
`bench/decision-distribution.png` üretir. Slayta giden grafik bu.

```python
# benchmark/run.py
preflight(clips, *, data_dir, run_pipeline, gateway_probe) -> None   # PrerequisiteError
pipeline_is_rewritten(run_pipeline) -> bool
run_clip(clip, *, run_pipeline, store_factory, data_dir) -> dict
benchmark(clips, *, run_pipeline, store_factory, data_dir) -> dict
write_payload(payload, path=KPI_PATH) -> Path

# benchmark/report.py
render_markdown(payload) -> str
write_chart(payload, path=CHART_PATH) -> Path | None
```

Bir klip çökerse **koşuyu durdurma** — hatayı o klibin kaydına yaz ve devam et.
Kısmi sonuç, hiç sonuç olmamasından iyidir; ama kısmi olduğu `clips` sayacında
görünür.

Buna karşılık **eksik ön koşulda hiç başlama.** Video dosyaları, ayakta bir
gateway ve Görev 17'nin `store` alan `run_pipeline`'ı olmadan üretilen şey
sıfırlarla dolu tertemiz bir `kpi.json` olurdu — çökme değil, ölçüm gibi görünen
bir hiç. `preflight()` eksik olan her şeyi tek seferde, Türkçe ve adıyla
bildirip çıkış kodu 2 ile durur.

```python
"""Görev 15 — benchmark koşucusu, etiket dosyası ve rapor.

`kpi.py` fikstürsüz ve gateway'sizdi; **koşu değil.** Bu dosyanın koruduğu şey
tek bir cümle: eksik ön koşulda benchmark sıfırlarla dolu bir tablo
üretmemeli. Sıfırlarla dolu bir `kpi.json` çökme değil, ölçüm gibi görünen bir
hiçtir — ve jüriye giden dosya odur.
"""

import json

import pytest

from benchmark import kpi, report, run
from benchmark.ground_truth import (DEFAULT_PATH, Clip, GroundTruthError,
                                    load_ground_truth, windows)
from gozcu.models import Episode, Handoff, Observation
from gozcu.store import Store

HEADER = "video,has_incident,start_s,end_s,kind\n"


def _csv(tmp_path, body: str):
    path = tmp_path / "gt.csv"
    path.write_text(HEADER + body, encoding="utf-8")
    return path


# --- etiket dosyası --------------------------------------------------------

def test_the_shipped_ground_truth_file_parses():
    clips = load_ground_truth(DEFAULT_PATH)
    assert len(clips) == 5
    assert sum(1 for c in clips if c.has_incident) == 4
    assert all(c.window is None or c.window[1] > c.window[0] for c in clips)


def test_a_negative_example_is_kept_but_never_measured(tmp_path):
    """`has_incident=0` satırında `start_s` boş; `float("")` istisna atardı ve
    bu satır sapma hesabına hiç girmemeli."""
    clips = load_ground_truth(_csv(tmp_path, "clips/a.mp4,0,,,yok\n"))
    assert clips[0].has_incident is False
    assert clips[0].window is None
    assert windows(clips) == []


def test_an_incident_without_a_marked_window_is_reported_not_guessed(tmp_path):
    """Pencere el işi. İşaretlenmemiş satır ölçüme girmez ama kaybolmaz."""
    clips = load_ground_truth(_csv(tmp_path, "clips/a.mp4,1,,,fire\n"))
    assert clips[0].unlabelled is True
    assert windows(clips) == []


def test_a_marked_window_reaches_the_drift_measurement(tmp_path):
    clips = load_ground_truth(_csv(tmp_path, "clips/a.mp4,1,12.5,19,fire\n"))
    assert windows(clips) == [(12.5, 19.0)]


@pytest.mark.parametrize("row, fragment", [
    ("clips/a.mp4,1,1,2,patlama\n", "bilinmeyen kind"),
    ("clips/a.mp4,1,1,2,yok\n", "has_incident=1"),
    ("clips/a.mp4,0,,,fire\n", "has_incident=0"),
    ("clips/a.mp4,1,abc,2,fire\n", "start_s sayı değil"),
    ("clips/a.mp4,1,5,5,fire\n", "büyük olmalı"),
    (",1,1,2,fire\n", "video yolu boş"),
    ("clips/a.mp4,2,1,2,fire\n", "has_incident 0 ya da 1"),
])
def test_a_broken_label_row_stops_the_run_loudly(tmp_path, row, fragment):
    with pytest.raises(GroundTruthError, match=fragment):
        load_ground_truth(_csv(tmp_path, row))


def test_comments_and_blank_lines_are_skipped(tmp_path):
    path = tmp_path / "gt.csv"
    path.write_text("# yorum\n\n" + HEADER + "clips/a.mp4,0,,,yok\n",
                    encoding="utf-8")
    assert len(load_ground_truth(path)) == 1


def test_a_missing_label_file_is_an_error_not_an_empty_run(tmp_path):
    with pytest.raises(GroundTruthError, match="etiket dosyası yok"):
        load_ground_truth(tmp_path / "yok.csv")


# --- ön koşullar -----------------------------------------------------------

def _rewritten_pipeline(video_path, store=None, gw=None):
    return None


def test_preflight_rejects_the_stage_one_pipeline():
    """Depodaki `gozcu.run.run_pipeline` hâlâ PoC imzasında ve depoya hiçbir
    şey yazmıyor; onunla koşulan benchmark her KPI'ı `null` okurdu."""
    from gozcu.run import run_pipeline

    assert run.pipeline_is_rewritten(run_pipeline) is False
    assert run.pipeline_is_rewritten(_rewritten_pipeline) is True


def test_preflight_names_every_missing_prerequisite_at_once(tmp_path):
    clip = Clip(video="clips/yok.mp4", has_incident=True, window=(1.0, 2.0),
                kind="fire")
    with pytest.raises(run.PrerequisiteError) as error:
        run.preflight([clip], data_dir=tmp_path, run_pipeline=None,
                      gateway_probe=lambda: False)
    message = str(error.value)
    assert "klip dosyası yok" in message
    assert "run_pipeline" in message
    assert "gateway" in message


def test_preflight_passes_when_everything_is_in_place(tmp_path):
    (tmp_path / "clips").mkdir()
    (tmp_path / "clips" / "a.mp4").write_bytes(b"0")
    clip = Clip(video="clips/a.mp4", has_incident=True, window=(1.0, 2.0),
                kind="fire")
    run.preflight([clip], data_dir=tmp_path,
                  run_pipeline=_rewritten_pipeline, gateway_probe=lambda: True)


def test_preflight_refuses_an_empty_label_set(tmp_path):
    with pytest.raises(run.PrerequisiteError, match="hiç klip yok"):
        run.preflight([], data_dir=tmp_path, run_pipeline=_rewritten_pipeline)


# --- klip koşusu -----------------------------------------------------------

def _clip(window=(12.0, 19.0)):
    return Clip(video="clips/a.mp4", has_incident=True, window=window,
                kind="fire")


def _seeded_store(_clip_unused=None):
    """Arşiv tohumlanmış bir depo — `load_history`'nin bıraktığı hâl."""
    store = Store(":memory:")
    archived = Episode(start_ts=0.0, phase="outcome", summary_tr="arşiv olayı",
                       preliminary_risk="Orta", state="closed")
    archived.id = store.create_episode(archived)
    return store


def _pipeline_writing(store_ref):
    def run_pipeline(video_path, store=None, gw=None):
        store_ref.append(store)
        store.save_observation(Observation(ts=0.0))
        store.save_handoff(Handoff(ts=0.0, source_agent="router",
                                   target_agent="perception", reason="sakin",
                                   confidence=0.8, payload_ref="w@0"))
        episode = Episode(start_ts=14.0, phase="onset",
                          summary_tr="Yük düştü, ekip bölgede.",
                          preliminary_risk="Yüksek")
        store.create_episode(episode)
    return run_pipeline


def test_a_clip_run_measures_the_live_episode_not_the_archive():
    written: list = []
    record = run.run_clip(_clip(), run_pipeline=_pipeline_writing(written),
                          store_factory=_seeded_store)
    assert record["error"] is None
    assert record["status"] == kpi.MEASURED
    # Arşiv epizodu 0.0'da duruyor; sayılsaydı sapma 12.0 okunurdu.
    assert record["kpis"]["timestamp_drift_s"] == 2.0


def test_a_crashing_clip_is_recorded_and_the_run_continues():
    def exploding(video_path, store=None):
        raise RuntimeError("video okunamadı")

    record = run.run_clip(_clip(), run_pipeline=exploding,
                          store_factory=_seeded_store)
    assert "video okunamadı" in record["error"]
    assert record["status"] == kpi.UNMEASURED
    assert set(record["kpis"]) == set(kpi.KPI_KEYS)


def test_an_epoch_timestamp_in_the_store_fails_the_clip_instead_of_reporting():
    """Epoch damgalı bir epizot `mmss()` altında `99:59` okunur — makul
    görünen yanlış bir saat. Ölçüm bunu sonuç diye yayınlamaz."""
    def bad_pipeline(video_path, store=None):
        store.create_episode(Episode(start_ts=1786567260.0, phase="outcome",
                                     summary_tr="x", preliminary_risk="Orta"))

    record = run.run_clip(_clip(), run_pipeline=bad_pipeline,
                          store_factory=_seeded_store)
    assert "epoch" in record["error"]


def test_the_payload_carries_the_clip_records_and_the_aggregate():
    written: list = []
    payload = run.benchmark([_clip()], run_pipeline=_pipeline_writing(written),
                            store_factory=_seeded_store)
    assert payload["schema_version"] == run.SCHEMA_VERSION
    assert payload["ground_truth"] == {"clips": 1, "labelled": 1,
                                       "unlabelled": 0, "no_incident": 0}
    assert payload["aggregate"]["status"] == kpi.MEASURED


# --- şema ------------------------------------------------------------------

def _schema() -> dict:
    return json.loads((run.BENCH_DIR / "kpi.schema.json")
                      .read_text(encoding="utf-8"))


def test_the_schema_names_exactly_the_kpis_the_code_produces():
    """Şema ile kod ayrışırsa rapor sessizce yanlış anahtarı okur; bu proje
    o ayrışmayı beş kez yaşadı."""
    schema = _schema()
    assert set(schema["definitions"]["kpis"]["properties"]) == set(kpi.KPI_KEYS)
    assert (set(schema["definitions"]["distribution"]["properties"])
            == set(kpi.DECISION_BUCKETS))


def test_a_generated_payload_validates_against_the_committed_schema():
    jsonschema = pytest.importorskip("jsonschema")
    written: list = []
    payload = run.benchmark([_clip()], run_pipeline=_pipeline_writing(written),
                            store_factory=_seeded_store)
    jsonschema.validate(json.loads(json.dumps(payload)), _schema())


def test_a_failed_payload_also_validates():
    jsonschema = pytest.importorskip("jsonschema")

    def exploding(video_path, store=None):
        raise RuntimeError("video yok")

    payload = run.benchmark([_clip(window=None)], run_pipeline=exploding,
                            store_factory=_seeded_store)
    jsonschema.validate(json.loads(json.dumps(payload)), _schema())


def test_the_payload_is_written_as_readable_utf8(tmp_path):
    written: list = []
    payload = run.benchmark([_clip()], run_pipeline=_pipeline_writing(written),
                            store_factory=_seeded_store)
    path = run.write_payload(payload, tmp_path / "kpi.json")
    assert json.loads(path.read_text(encoding="utf-8")) == payload


# --- rapor -----------------------------------------------------------------

def _payload(status, distribution, **kpis):
    body = {key: None for key in kpi.KPI_KEYS}
    body["decision_distribution"] = distribution
    body.update(kpis)
    return {"schema_version": 1, "generated_at": "2026-08-24T09:00:00+00:00",
            "ground_truth": {"clips": 1, "labelled": 0, "unlabelled": 1,
                             "no_incident": 0},
            "clips": [{"video": "clips/a.mp4", "status": status,
                       "error": None, "kpis": body}],
            "aggregate": {"status": status,
                          "clips": {"total": 1, "measured": 0, "degraded": 1,
                                    "unmeasured": 0, "error": 0},
                          "kpis": body}}


def test_the_report_says_not_measured_instead_of_zero():
    markdown = report.render_markdown(_payload(kpi.UNMEASURED, None))
    assert report.NOT_MEASURED_TEXT in markdown
    assert "ÖLÇÜLEMEDİ" in markdown


def test_the_report_banners_a_degraded_run():
    distribution = {"closed_at_router": 0.1, "to_interpreter": 0.0,
                    "to_synthesizer": 0.0, "escalated": 0.0, "degraded": 0.9}
    markdown = report.render_markdown(_payload(kpi.DEGRADED, distribution))
    assert "BOZULMUŞ KOŞU" in markdown
    assert "0.900" in markdown


def test_the_report_states_that_tokens_cover_the_vision_tier_only():
    markdown = report.render_markdown(_payload(kpi.MEASURED, None))
    assert "yalnız görü kademesini" in markdown


def test_no_chart_is_drawn_when_the_distribution_was_not_measured(tmp_path):
    assert report.write_chart(_payload(kpi.UNMEASURED, None),
                              tmp_path / "c.png") is None


def test_the_chart_is_written_when_the_distribution_exists(tmp_path):
    pytest.importorskip("matplotlib")
    distribution = {"closed_at_router": 0.7, "to_interpreter": 0.2,
                    "to_synthesizer": 0.05, "escalated": 0.05,
                    "degraded": 0.0}
    path = report.write_chart(_payload(kpi.MEASURED, distribution),
                              tmp_path / "c.png")
    assert path.is_file() and path.stat().st_size > 0
```

### 6. Yeşil olduğunu gör

```bash
uv run pytest tests/test_kpi.py tests/test_benchmark.py -q
```
Beklenen: 58 passed

### 7. Commit

```bash
git add benchmark bench tests/test_kpi.py tests/test_benchmark.py
git commit -m "feat: KPI suite that distinguishes measured runs from degraded ones"
```

## Doğrulama

```bash
uv run pytest tests/test_kpi.py tests/test_benchmark.py -q
uv run python scripts/check-tasks.py
```
Beklenen: **58 passed**

## Takıldığında

Üveys'e yaz. **Bekleme** — bu sprintte bir saat, toplam kapasitenin yaklaşık %4'ü.

## Tamamlanma notları (gelecek görevleri bağlayan)

- **`Episode.start_ts` HER YERDE video saniyesi.** Arşiv fikstürleri aynı sütunda
  epoch damgası taşıyordu (`1786567260.0`) ve `mmss()` onu kendi tavanına,
  `99:59`'a yapıştırıyordu: rapor ve konsol arşiv olaylarını makul görünen
  yanlış bir saatle basıyordu. Arşiv epizotları artık `start_ts=0.0` ile geliyor,
  olayın süresi `end_ts`'te duruyor, takvim anı ise `occurred_at` / `date`
  alanlarında yaşıyor — epizot satırında değil.
  `epoch_scale_episodes(store)` ihlali adıyla döndürüyor ve `run_clip` böyle bir
  klibi ölçmek yerine hataya düşürüyor.
- **`decision_distribution` BEŞ kovalı.** Dört yönlendirme sonucunun yanında
  `degraded` var: `confidence == 0.0` taşıyan devirler, yani `route()`'un kesinti
  yedeğinin bıraktığı işaret. Bu kova olmadan tamamen çökmüş bir koşu "mükemmel
  ucuz filtreleme" diye okunuyordu, çünkü her arıza da `closed_at_router`'a
  düşüyordu. Beş pay aynı paydaya bölünür ve 1'e toplanır.
- **Her KPI yükü koşu seviyesinde bir `status` taşıyor:** `measured` /
  `degraded` / `unmeasured`. `aggregate()` ortalamalara **yalnız `measured`
  klipleri** katıyor; bozulmuş ve çöken klipler kaybolmuyor, `clips` sayacında
  adıyla duruyorlar.
- **Boş koşu sözleşmesi her yerde `None`** (JSON'da `null`). Önceki taslakta üç
  gelenek yan yana yaşıyordu — `0.0`, `1.0` ve `nan`; `0.0` "ölçtük, sıfır
  çıktı" demek, `1.0` hiç düzeltme almamış bir koşuya tam not vermek olurdu ve
  `nan` zaten geçerli JSON değil.
- **`turkish_output_rate` yalnız `role == "supervisor"` diyalog satırlarını
  okuyor.** `role == "system"` satırlarında iki şey yatıyor ve ikisi de model
  üretimi değil: `AUDIT_PREFIX` önekli denetim hükümleri ve elle yazılmış Türkçe
  arıza metinleri. Tespit **kelime belirteci** üzerinden yapılıyor, alt dize
  araması değil: Türkçe `risk`, `iş`, `İSG` birer ASCII tuzağı ve `"İ".lower()`
  iki kod noktası üretir.
- **`tokens_by_model` artık `vision_tokens`.** `tokens` sistemde tek bir yerde
  kalıcı hâle geliyor — `Interpretation` — dolayısıyla koşu geneli bir maliyet
  iddiası veriye dayanmaz ve üretilmiyor. Anahtar, kaydedilen model kimliği.
- **`vision_tokens` 25 Ağustos'tan beri VİDEO pencerelerini sayıyor**
  (`886342a`): görü kademesine giden şey artık üç kare değil, pencere başına
  tek bir mp4 klibi. Canlı ölçülen tek pencere **~8.000 token** ve bunun ezici
  çoğunluğu video kodlamasından geliyor — yani koşu başına toplam, kare
  döneminin varsayımından **çok daha büyük**. Sayı sıçradı diye bir gerileme
  arama; ölçülen şey değişti. Pencere sayısı sabit kaldığı için
  `vlm_trigger_rate` bundan etkilenmiyor.
- **`correction_propagation` hiç düzeltme yoksa `None` döner**, ve gerçek ayırt
  edicisi var olmayan bir epizodu gösteren düzeltmedir. Süpervizörün
  ekleme-yedeği ("(operatör düzeltmesi: …)") yüzünden "yeni metin özette mi"
  sorusu, epizot çözüldüğü anda asla başarısız olamıyor.
- **Benchmark artefaktları VERSİYONLANAN `bench/` dizininde**, sözleşmeleri
  `bench/kpi.schema.json` ile birlikte commit'li. `runs/` `.gitignore`'da ve
  zaten ultralytics'in çıktıları için kullanılıyor; `bench/` altında dışarıda
  kalan tek şey klip başına SQLite deposu (`bench/stores/`).
- **`benchmark/run.py` Görev 17 inene kadar KOŞMAYI REDDEDİYOR** — çıkış kodu 2,
  Türkçe mesaj. Beklediği şey `Store` alan bir `run_pipeline`. Bu bilerek böyle:
  eksik bir ön koşul, ölçülmüş bir sıfır yığınıyla karıştırılamamalı.
- **`benchmark/ground_truth.csv` olay pencereleri İŞARETSİZ geliyor.**
  Etiketleme el işi; bir insan klipleri işaretleyene kadar `timestamp_drift_s`
  `null` okur. Hiçbir sayı uydurulmadı.
