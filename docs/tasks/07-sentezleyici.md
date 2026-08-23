# Görev 07 — Sentezleyici: kareler → epizot (`gozcu/agents/synthesizer.py`)

**Sahip:** `uvyscengiz` · **Gün:** 24 Ağustos · **Süre:** ~2.5 saat
**Bağımlılık:** [01](01-sozlesme.md), [02](02-olay-deposu.md), [03](03-gateway.md), [06](06-yonlendirici.md)

## Bağlam

Şartname açıkça şunu istiyor: *"yalnızca kare bazlı analiz etmekle sınırlı
kalmamalı; sahne bütünlüğünü, zamansal ilişkileri ve olay akışını
anlayabilmelidir"* ve *"olayların başlangıç, gelişim ve sonuç süreçlerini ayırt
edebilmeli."*

**Kare bağımsızlığı tam olarak burada kırılıyor.** Dağınık gözlemler ve görsel
yorumlar tek bir `Episode` kaydına dönüşüyor: hangi fazda, kimler var, Türkçe
özeti ne, ön riski ne.

### Epizot yaşam döngüsü — bu görevin en kritik kısmı

Yönlendirici üç farklı epizot kararı verebiliyor ve **üçü de farklı davranmalı:**

| Karar | Ne yapılır |
|---|---|
| `open_episode` | Yeni epizot açılır |
| `update_episode` | **Açık epizota kaynaşır** — `update_episode` ile bitiş zamanı, faz ve özet güncellenir. Yeni epizot AÇILMAZ |
| `close_episode` | Açık epizot `state="closed"`, `end_ts` set edilir, ve **gömme geri çağrısı** tetiklenir |

Üçü de yeni epizot açarsa tek bir forklift kazası N kopya epizota bölünür,
`events[]` çıktısında aynı olay tekrar tekrar görünür ve kare bağımsızlığını
pencere seviyesinde geri getirmiş oluruz. Bu, düzeltilmesi en pahalı hatalardan
biri — testler onu yakalıyor.

Gömme geri çağrısı opsiyonel (`on_close=None`): Görev 08 hafızayı yazana kadar bu
görev tek başına tamamlanabilsin diye.

## Kurulum

```bash
uv sync --extra dev
uv run pytest tests/test_router.py tests/test_store.py -v
```

## Bağımlı olduğun imzalar

```python
# gozcu/agents/router.py
mmss(ts: float) -> str

# gozcu/gateway.py
Gateway.ask(tier, messages, schema=None, tools=None) -> Response
Response(content, tool_calls, model, latency_ms, tokens, degraded)

# gozcu/store.py
Store.create_episode(e: Episode) -> int
Store.update_episode(episode_id: int, **fields) -> None
Store.open_episode() -> Episode | None
Store.save_handoff(d: Handoff) -> int

# gozcu/models.py
Episode(id, start_ts, end_ts, phase, summary_tr, participants, preliminary_risk, state)
Interpretation(id, observation_ts, description, notable_event, model, latency_ms, tokens)
```

**Bozulmuş yanıt guard'ı (Görev 03).** `fast` kademesi kesintide istisna atmıyor;
`content=""` olan `degraded=True` bir `Response` dönüyor. Bozulmuş yanıt hiçbir
şeye ayrışmaz — JSON ayrıştırma boş içeriğe karşı korunmalı.
`except GatewayError` bunu yakalamaz.

## Ne yapacaksın

```python
synthesize(gw, store, window, interpretation, decision, on_close=None) -> Episode | None
```

`decision` ∈ `{"open_episode", "update_episode", "close_episode"}`.
`on_close` verilirse ve karar `close_episode` ise `on_close(episode)` çağrılır.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_synthesizer.py`

```python
from unittest.mock import Mock

from gozcu.agents.synthesizer import synthesize
from gozcu.gateway import Response
from gozcu.models import Episode, Observation, Signals, Interpretation
from gozcu.store import Store

RESPONSE_JSON = ('{"phase":"development","summary_tr":"İstif aracı devrildi, yerde hareketsiz '
         'kişi var.","participants":["istif aracı","personnel"],'
         '"preliminary_risk":"Kritik"}')


def _gw():
    gw = Mock(); gw.ask.return_value = Response(content=RESPONSE_JSON)
    return gw


def _win(bas=0, adet=10):
    return [Observation(ts=float(bas + t), signals=Signals(person_count=1))
            for t in range(adet)]


def test_open_merges_a_window_into_one_episode():
    store = Store(":memory:")
    interpretation = Interpretation(observation_ts=3.0, description="araç yan yattı", model="m")
    e = synthesize(_gw(), store, _win(), interpretation, "open_episode")
    assert e.start_ts == 0.0 and e.end_ts == 9.0
    assert e.preliminary_risk == "Kritik" and e.phase == "development"
    assert len(store.episodes()) == 1


def test_update_extends_the_open_episode_instead_of_opening_a_new_one():
    store = Store(":memory:")
    synthesize(_gw(), store, _win(0), None, "open_episode")
    synthesize(_gw(), store, _win(10), None, "update_episode")
    assert len(store.episodes()) == 1
    assert store.episodes()[0].end_ts == 19.0


def test_close_closes_the_open_episode_and_does_not_open_a_new_one():
    store = Store(":memory:")
    synthesize(_gw(), store, _win(0), None, "open_episode")
    synthesize(_gw(), store, _win(10), None, "close_episode")
    assert len(store.episodes()) == 1
    e = store.episodes()[0]
    assert e.state == "closed" and e.end_ts == 19.0
    assert store.open_episode() is None


def test_close_triggers_the_embedding_callback():
    store, embedded = Store(":memory:"), []
    synthesize(_gw(), store, _win(0), None, "open_episode", on_close=embedded.append)
    assert embedded == []
    synthesize(_gw(), store, _win(10), None, "close_episode",
             on_close=embedded.append)
    assert len(embedded) == 1 and embedded[0].state == "closed"


def test_update_without_an_open_episode_opens_one():
    store = Store(":memory:")
    e = synthesize(_gw(), store, _win(), None, "update_episode")
    assert e is not None and len(store.episodes()) == 1


def test_synthesize_uses_the_fast_tier_not_the_large_one():
    gw = _gw()
    synthesize(gw, Store(":memory:"), _win(), None, "open_episode")
    assert gw.ask.call_args.args[0] == "fast"


def test_degraded_fast_tier_still_produces_an_episode():
    gw = Mock(); gw.ask.return_value = Response(degraded=True)
    store = Store(":memory:")
    e = synthesize(gw, store, _win(), None, "open_episode")
    assert e is not None and len(store.episodes()) == 1


def test_synthesize_records_a_handoff_to_the_risk_analyst():
    store = Store(":memory:")
    synthesize(_gw(), store, _win(), None, "open_episode")
    assert store.handoffs()[-1].source_agent == "synthesizer"
    assert store.handoffs()[-1].target_agent == "risk_analyst"
```

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_synthesizer.py -v
```
Beklenen: `ModuleNotFoundError`

### 3. `gozcu/agents/synthesizer.py` yaz

```python
import json

from pydantic import BaseModel, ConfigDict, Field

from gozcu.agents.router import mmss
from gozcu.models import Handoff, Episode, Observation, RiskLevel, Interpretation

SYSTEM_PROMPT = """Sen bir fabrika kontrol odasının kâtibisin. Sana bir zaman
aralığındaki gözlemler ve görsel yorumlar verilir. Bunları TEK BİR OLAY
halinde birleştir.

Kurallar:
- Olayın hangi fazda olduğunu belirt — tam olarak bu değerlerden biri:
  onset (başlangıç), development (gelişim), outcome (sonuç)
- Özet Türkçe, kısa cümlelerle, saha terminolojisiyle yazılır
- Görmediğin bir şeyi yazma. Emin değilsen "olası" de.
- Ön riski şu dördünden biri olarak ver: Düşük, Orta, Yüksek, Kritik

Sadece JSON döndür."""

PHASES = ("onset", "development", "outcome")


class _SynthesisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phase: str
    summary_tr: str = Field(max_length=600)
    participants: list[str] = Field(default_factory=list)
    preliminary_risk: RiskLevel


def _synthesise(gw, window: list[Observation], interpretation: Interpretation | None,
                   onceki: Episode | None) -> _SynthesisResponse:
    lines = [f"{mmss(g.ts)} kişi={g.signals.person_count} "
                f"hızlar={g.signals.velocities or '-'}" for g in window]
    if interpretation is not None:
        lines.append(f"{mmss(interpretation.observation_ts)} GÖRSEL: {interpretation.description}")
    if onceki is not None:
        lines.insert(0, f"DEVAM EDEN OLAY: {onceki.summary_tr}")

    response = gw.ask("fast", [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(lines)},
    ], schema=_SynthesisResponse)

    if response.degraded:
        return _SynthesisResponse(phase="development",
                       summary_tr="Sentez katmanı yanıt vermiyor; "
                               "ham gözlemler kayıtlı.",
                       preliminary_risk="Orta")
    try:
        s = _SynthesisResponse(**json.loads(response.content))
    except Exception:  # noqa: BLE001
        return _SynthesisResponse(phase="development",
                       summary_tr="Sentez üretilemedi; ham gözlemler kayıtlı.",
                       preliminary_risk="Orta")
    if s.phase not in PHASES:
        s.phase = "development"
    return s


def synthesize(gw, store, window: list[Observation], interpretation: Interpretation | None,
             decision: str, on_close=None) -> Episode | None:
    """Gözlem penceresini bir Epizot'a dönüştürür.

    decision == "open_episode"       -> yeni epizot
    decision == "update_episode" -> açık epizota kaynaşır
    decision == "close_episode"    -> açık epizodu kapatır ve on_close(episode) çağırır
    """
    if not window:
        return None

    open_ep = store.open_episode() if decision != "open_episode" else None
    s = _synthesise(gw, window, interpretation, open_ep)
    end = window[-1].ts

    if open_ep is None:
        episode = Episode(start_ts=window[0].ts, end_ts=end,
                        phase="outcome" if decision == "close_episode" else s.phase,
                        summary_tr=s.summary_tr, participants=s.participants,
                        preliminary_risk=s.preliminary_risk,
                        state="closed" if decision == "close_episode" else "open")
        episode.id = store.create_episode(episode)
    else:
        fields = {"end_ts": end, "summary_tr": s.summary_tr,
                   "participants": s.participants, "preliminary_risk": s.preliminary_risk,
                   "phase": "outcome" if decision == "close_episode" else s.phase}
        if decision == "close_episode":
            fields["state"] = "closed"
        store.update_episode(open_ep.id, **fields)
        episode = next(e for e in store.episodes() if e.id == open_ep.id)

    store.save_handoff(Handoff(ts=episode.start_ts,
                             source_agent="synthesizer",
                             target_agent="risk_analyst",
                             reason=f"{decision} → episode {episode.id}",
                             confidence=0.8,
                             payload_ref=f"episode:{episode.id}"))

    if decision == "close_episode" and on_close is not None:
        on_close(episode)

    return episode
```

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_synthesizer.py -v
```
Beklenen: 8 passed

### 5. Commit

```bash
git add gozcu/agents/synthesizer.py tests/test_synthesizer.py
git commit -m "feat: synthesizer with full episode lifecycle (open/update/close)"
```

## Doğrulama

```bash
uv run pytest tests/test_synthesizer.py -v
```
Beklenen: **8 passed**

## Takvim kaydıysa

Bu görev, 24 Ağustos gecikirse **entegrasyondan önce kesilecek** olan görevdir.
Kesilirse yerine sinyallerden şablon epizot üret (`f"{kisi} kişi, {hiz} hız"`) —
kaba olur ama uçtan uca akış ayakta kalır. Bir arada çalışmayan altı modül,
kaba epizotlu çalışan bir sistemden kötüdür.
