# Görev 17 — Çıktı sözleşmesi ve entegrasyon (`gozcu/report.py`, `gozcu/run.py`)

**Sahip:** `uvyscengiz` · **Gün:** 26 Ağustos sabahı · **Süre:** ~3 saat
**Bağımlılık:** hepsi
**Puanın %35'i tek bir dosyada — projedeki en yüksek getirili teslim**

## Bağlam

Şartnamenin puanladığı senaryo şu: video yüklenir, sistem **zaman damgalı olay
listesi, genel özet, risk değerlendirmesi ve aksiyon önerileri** üretir.
Verdikleri örnek JSON'un anahtarları `summary`, `events`, `risk`, `actions`.

**Bu dört anahtar, diğer her şey çökse bile üretilmek zorunda.** Jüri çıktımızı
kendi örnekleriyle karşılaştıracak; aynı anahtarları görmeli. Bozulmuş bir koşu
bile geçerli, notlandırılabilir bir sonuç döndürmeli.

Eklediğimiz her şey — fazlı epizotlar, devir defteri, risk gerekçeleri, aksiyon
defteri, kök neden raporu — o sözleşmenin **yanında**, `detail` anahtarı
altında duruyor. Yerine değil.

İkinci kural: `actions[]` metinleri Risk Analisti'nin **gerçekten bir araca
eşlediği** adaylardan türetiliyor. İnsanın okuduğu liste ile makinenin aksiyon
defteri birbirinden ayrışamaz.

## Kurulum

```bash
uv sync --extra dev
uv run pytest tests/ -v      # her şey yeşil olmalı
```

## Ne yapacaksın

Üç parça.

### A. `gozcu/report.py` — sözleşme derleyicisi

```python
build_output(store, summary: str, root_cause=None) -> PipelineOutput
```

### B. `gozcu/adapter.py` — donuk algı katmanını modellere bağlar

Mevcut `signals.py` `FrameSignals(velocities, vanished_tracks, person_count,
person_count_delta)` üretiyor; bizim `Sinyaller` tipimizin bir de `toplanma`
alanı var ve **algı katmanı onu hesaplamıyor.** Burada türetiyoruz.

```python
to_observation(frame_ts, detections, frame_signals) -> Observation
GATHERING_THRESHOLD = 3
```

### C. `gozcu/run.py` — uçtan uca akış

`run_pipeline(video_path)` artık: kare çıkar → `Observation` üret → `DecisionLoop`
kur → koştur → `build_output` döndür.

> **Görev 05 bağlama uyarısı (iki tuzak).**
> 1. `run()` `Episode` değil **`LoopEvent(episode, late)`** yield ediyor —
>    `event.episode` okunacak, `event.late` ise operatöre giden metni
>    değiştirmeli: geç telafi edilmiş bir epizot duyurulur ama canlı kriz gibi
>    sunulmaz.
> 2. **`is_degraded` mutlaka geçilecek:** `is_degraded=lambda: gw.is_degraded("vlm")`.
>    Varsayılan `lambda: False` ile `deferred` hiç dolmaz, `catch_up()` ölü kod
>    olur ve kesinti telafisi demosu sessizce hiçbir şey yapmaz. Çıplak
>    `gw.is_degraded` de olmaz: "herhangi bir kademe" demek ve `rerank`'ın
>    beklenen 400'ü her pencereyi sonsuza dek erteletir.
> 3. `synthesize` döngüye üç argümanlı geçiyor `(window, interpretation,
>    decision)`; Görev 07'nin gerçek imzası `synthesize(gw, store, window,
>    interpretation, decision, on_close=None)` — aradaki farkı bir `lambda`
>    kapatıyor.

**Genişletilmiş yolun tamamı `try` içinde.** Çöktüğünde bile dört anahtarlı
geçerli bir `PipelineOutput` dönmeli, `detail=None` ile.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_report.py`

```python
from gozcu.adapter import to_observation
from gozcu.models import (ProposedAction, ActionRecord, Episode, RiskAssessment)
from gozcu.report import build_output
from gozcu.store import Store


class _FS:
    def __init__(self, **kw):
        self.velocities = kw.get("velocities", {})
        self.vanished_tracks = kw.get("vanished_tracks", [])
        self.person_count = kw.get("person_count", 0)
        self.person_count_delta = kw.get("person_count_delta", 0)


def test_four_keys_exist_even_with_a_completely_empty_run():
    c = build_output(Store(":memory:"), summary="Kayda değer olay yok.")
    d = c.model_dump(exclude_none=True)
    assert {"summary", "events", "risk", "actions"} <= set(d)
    assert d["risk"] == "Düşük"


def test_events_use_mmss_and_come_from_episodes():
    store = Store(":memory:")
    store.create_episode(Episode(start_ts=15.0, phase="onset",
                           summary_tr="İstif aracı devrildi", preliminary_risk="Yüksek"))
    c = build_output(store, summary="ö")
    assert c.events[0].time == "00:15"
    assert c.events[0].event == "İstif aracı devrildi"


def test_overall_risk_is_the_highest_assessed_level():
    store = Store(":memory:")
    for level in ("Düşük", "Kritik", "Orta"):
        store.save_risk(RiskAssessment(episode_id=1, level=level,
                                            rationale_tr="g", preventable=True))
    assert build_output(store, summary="ö").risk == "Kritik"


def test_risk_falls_back_to_episode_preliminary_when_no_assessment_exists():
    store = Store(":memory:")
    store.create_episode(Episode(start_ts=0.0, phase="development", summary_tr="x",
                           preliminary_risk="Yüksek"))
    assert build_output(store, summary="ö").risk == "Yüksek"


def test_actions_are_rendered_from_tool_backed_candidates_only():
    store = Store(":memory:")
    store.save_risk(RiskAssessment(
        episode_id=1, level="Kritik", rationale_tr="g", preventable=True,
        proposed_actions=[ProposedAction(description_tr="Sağlık ekibini çağır",
                                     tool_name="dispatch_medical")]))
    assert build_output(store, summary="ö").actions == ["Sağlık ekibini çağır"]


def test_duplicate_actions_are_not_repeated():
    store = Store(":memory:")
    for _ in range(3):
        store.save_risk(RiskAssessment(
            episode_id=1, level="Orta", rationale_tr="g", preventable=True,
            proposed_actions=[ProposedAction(description_tr="Alanı güvenlik altına al",
                                         tool_name="site_alarm")]))
    assert build_output(store, summary="ö").actions == [
        "Alanı güvenlik altına al"]


def test_detail_block_is_attached_but_never_replaces_the_four_keys():
    store = Store(":memory:")
    store.save_action(ActionRecord(ts=1.0, tool_name="site_alarm",
                                      params={}, result={}, actor="agent",
                                      approval="not_required"))
    c = build_output(store, summary="ö")
    assert c.detail is not None and len(c.detail.action_ledger) == 1
    assert c.summary == "ö"


def test_adapter_derives_gathering_from_person_count():
    g = to_observation(1.0, [], _FS(person_count=3))
    assert g.signals.gathering is True
    assert to_observation(1.0, [], _FS(person_count=2)).signals.gathering is False


def test_adapter_keeps_the_person_count_delta():
    g = to_observation(1.0, [], _FS(person_count=4, person_count_delta=2))
    assert g.signals.person_count_delta == 2


def test_adapter_maps_velocities_and_vanished_tracks():
    g = to_observation(2.0, [], _FS(velocities={7: 3.1}, vanished_tracks=[9]))
    assert g.signals.velocities == {7: 3.1}
    assert g.signals.vanished_tracks == [9]
    assert g.ts == 2.0
```

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_report.py -v
```
Beklenen: `ModuleNotFoundError`

### 3. `gozcu/adapter.py` yaz

```python
from gozcu.models import Observation, Signals, Detection

GATHERING_THRESHOLD = 3


def to_observation(frame_ts: float, detections, frame_signals) -> Observation:
    """Donuk algı katmanının çıktısını ajan katmanının tipine çevirir.

    `gathering` signals.py'da hesaplanmıyor — burada kişi sayısından
    türetiliyor. Eşiği aşan kişi sayısı 'toplanma' sayılıyor; bu bir
    heuristik ve yönlendiriciye sadece bir sinyal olarak gidiyor, karar
    olarak değil.
    """
    return Observation(
        ts=frame_ts,
        detections=[Detection(label=t.class_name, confidence=getattr(t, "confidence", 1.0),
                          box=tuple(float(v) for v in t.bbox),
                          track_id=getattr(t, "track_id", None))
                   for t in detections],
        signals=Signals(
            velocities=dict(frame_signals.velocities),
            vanished_tracks=list(frame_signals.vanished_tracks),
            person_count=frame_signals.person_count,
            person_count_delta=frame_signals.person_count_delta,
            gathering=frame_signals.person_count >= GATHERING_THRESHOLD))
```

### 4. `gozcu/report.py` yaz

```python
from gozcu.agents.router import mmss
from gozcu.models import Detail, EventSummary, PipelineOutput, RiskLevel

ORDER: list[RiskLevel] = ["Düşük", "Orta", "Yüksek", "Kritik"]


def build_output(store, summary: str, root_cause=None) -> PipelineOutput:
    """Şartnamenin dört anahtarını üretir; her şey detail altında yanına
    eklenir, yerine değil."""
    episodes = store.episodes()
    risks = store.risks()

    events = [EventSummary(time=mmss(e.start_ts), event=e.summary_tr[:200])
              for e in episodes]

    seviyeler = [r.level for r in risks] or [e.preliminary_risk for e in episodes]
    risk = max(seviyeler, key=ORDER.index) if seviyeler else "Düşük"

    # Sadece araca bağlanmış adaylardan; böylece insanın okuduğu liste ile
    # makinenin aksiyon defteri birbirinden ayrışamaz.
    actions: list[str] = []
    for r in risks:
        for a in r.proposed_actions:
            if a.description_tr not in actions:
                actions.append(a.description_tr)

    return PipelineOutput(
        summary=summary, events=events, risk=risk, actions=actions,
        detail=Detail(
            episodes=episodes,
            risk_assessments=risks,
            handoff_chain=store.handoffs(),
            action_ledger=store.actions(),
            root_cause_report=root_cause.model_dump() if root_cause else None))
```

### 5. `gozcu/run.py` yeniden yaz

```python
def run_pipeline(video_path, store=None, gw=None, nobetci=None):
    """Uçtan uca akış. Genişletilmiş katman çökse bile dört anahtarlı geçerli
    bir çıktı döner — bozulmuş bir koşu da notlandırılabilir olmalı."""
    frames = extract_frames(video_path, output_dir)
    tracked = track_video([f.path for f in frames])
    signals = compute_signals(tracked, [f.timestamp_s for f in frames])

    observations = [to_observation(f.timestamp_s, t, s)
                 for f, t, s in zip(frames, tracked, signals, strict=True)]
    for g in observations:
        store.save_observation(g)

    summary = "Kayda değer olay tespit edilmedi."
    root_cause = None
    try:
        loop = DecisionLoop(store,
                             route=lambda p: route(
                                 gw, p, store.open_episode() is not None),
                             interpret=lambda p: interpret(
                                 gw, store, p, _frame_for(frames)),
                             synthesize=lambda p, y, k: synthesize(
                                 gw, store, p, y, k,
                                 on_close=lambda e: embed_episode(gw, store, e)),
                             # Çıplak gw.is_degraded değil: sadece görü kademesi.
                             is_degraded=lambda: gw.is_degraded("vlm"))
        for event in loop.run(observations):
            if nobetci is not None:
                message = nobetci.escalate(event.episode)
                if event.late:
                    # Kesinti telafisinden geldi: duyur, ama canlı kriz gibi değil.
                    message = f"[Telafi — kesinti sırasında atlanmıştı] {message}"
        if store.episodes():
            root_cause = generate_root_cause_report(gw, store)
            summary = root_cause.what_happened
    except Exception:  # noqa: BLE001 — bozulmuş koşu da geçerli çıktı vermeli
        return build_output(store, summary=summary), output_dir

    return build_output(store, summary=summary, root_cause=root_cause), output_dir
```

`_frame_for(frames)` Görev 04'ün beklediği kapanış. Tanımı:

```python
def _frame_for(frames):
    """Bir ts alıp o ana en yakın karenin dosya yolunu döndüren kapanış."""
    ordered = sorted(frames, key=lambda f: f.timestamp_s)

    def pick(ts: float):
        if not ordered:
            return None
        return min(ordered, key=lambda f: abs(f.timestamp_s - ts)).path

    return pick
```

`app.py` üç satırlık giriş noktası olarak kalsın:

```python
from gozcu.ui.console import baslat

if __name__ == "__main__":
    baslat()
```

### 6. Yeşil olduğunu gör

```bash
uv run pytest tests/ -v
```
Beklenen: hepsi yeşil.

### 7. Uçtan uca dene

```bash
uv run python app.py
```

Bir klip yükle. Dört anahtarlı JSON çıkmalı.

### 8. Commit

```bash
git add gozcu/report.py gozcu/adapter.py gozcu/run.py app.py tests/test_report.py
git commit -m "feat: şartname output contract with detail block and safe fallback"
```

## Doğrulama

```bash
uv run pytest tests/test_report.py -v && uv run pytest tests/ -q
```
Beklenen: **10 passed** ve tüm suite yeşil.
