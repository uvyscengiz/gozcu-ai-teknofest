# Mikro-ajan mimarisi yeniden tasarımı — uygulama planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PDF'in mikro-ajan önerisini koda indirmek — protokole dayalı bir
Karar & Aksiyon ajanı eklemek, risk analistini derecelendirmeye daraltmak ve
ajan adlarını mimari dokümanla eşitlemek.

**Architecture:** Zincire `risk_analyst → action_planner → supervisor` durağı
giriyor. Planlayıcı, epizodun `event_class` + `zone_id` alanlarıyla
deterministik süzülmüş aday protokoller arasından seçim yapıyor; modelin
uydurduğu değil, tesisin yazılı prosedürü plana giriyor. Model susarsa
protokolün adımları birebir plana düşüyor — yani `actions` anahtarı artık
model başarısına bağlı değil.

**Tech Stack:** Python 3.12 · pydantic v2 · SQLite (`:memory:`) · pytest ·
EVREN gateway (`gozcu/gateway.py`) · uv

**Spec:** [2026-08-27-mikro-ajan-yeniden-tasarimi-design.md](../specs/2026-08-27-mikro-ajan-yeniden-tasarimi-design.md)

## Global Constraints

- **Kod İngilizce, insana görünen metin Türkçe.** Sınıf/fonksiyon/alan/JSON
  anahtarı/tool adı/SQL tablo adı İngilizce; promptlar, operatör mesajları,
  docstring'ler ve enum *değerleri* Türkçe.
- **Risk seviyeleri birebir:** `"Düşük" | "Orta" | "Yüksek" | "Kritik"`.
- **Olay sınıfları birebir:** `"sıkışma" | "düşme" | "çarpma" | "yangın" |
  "kimyasal sızıntı" | "ekipman arızası" | "yetkisiz giriş" | "rutin" | "diğer"`.
- **Prompt bir enum sayıyorsa değerleri şemadakiyle birebir aynı olmalı.**
  Ayrıştıklarında sistem sessizce ölür.
- **Çıktı sözleşmesi:** `summary` · `events` · `risk` · `actions` her koşuda
  üretilir; genişletilmiş katmanlar çökse bile.
- **Model kimlikleri yalnız `gozcu/config.py`'da.**
- **TDD:** önce test, kırmızı olduğunu gör, sonra minimum kod.
- **Doğrulama komutu:** `uv run pytest tests/ -v`

## Dosya haritası

| Dosya | Sorumluluk | Görev |
|---|---|---|
| `gozcu/models.py` | Paylaşılan sözleşme — `AgentName`, `EventClass`, `Episode`, `Protocol`, `ActionPlan`, `RiskAssessment`, `Detail` | 1,2,3,4,6 |
| `gozcu/agents/synthesizer.py` → `anomaly_analyst.py` | Pencere → epizot; olay sınıfı ve bölge | 1,2 |
| `gozcu/agents/router.py` → `orchestrator.py` | Dikkat mekanizması | 1 |
| `gozcu/fixtures/protocols.json` | Tesisin yazılı prosedürleri (yeni) | 3 |
| `gozcu/fixtures/loader.py` | `load_protocols`, `match_protocols` | 3 |
| `gozcu/agents/action_planner.py` | **Yeni ajan** — protokol seçici | 4 |
| `gozcu/store.py` | `action_plan` tablosu, `save_action_plan`, `action_plans` | 4 |
| `gozcu/agents/risk.py` | Yalnız derecelendirme | 6 |
| `gozcu/agents/supervisor.py` | Planı yükseltme mesajına taşır | 5 |
| `gozcu/run.py`, `gozcu/loop.py` | Planlayıcıyı zincire bağlar | 5 |
| `gozcu/report.py`, `gozcu/ui/feed.py` | `actions` artık plandan türer | 6 |
| `gozcu/agents/reporter.py` | Kök neden raporu protokolü anar | 7 |
| `gozcu/ui/web/js/trace.js`, `ui/feed.py`, `ui/view.py`, `ui/web/css/styles.css` | Yeni ad ve yeni durak | 1,5 |
| `benchmark/kpi.py` | `_BUCKET_BY_TARGET` anahtarları | 1 |

---

## Task 1: Yeniden adlandırma (davranış değişmiyor)

**Files:**
- Modify: `gozcu/models.py:39` — `AgentName`
- Rename: `gozcu/agents/router.py` → `gozcu/agents/orchestrator.py`
- Rename: `gozcu/agents/synthesizer.py` → `gozcu/agents/anomaly_analyst.py`
- Modify: `gozcu/loop.py`, `gozcu/run.py`, `gozcu/agents/supervisor.py`
- Modify: `benchmark/kpi.py:60-63`, `gozcu/ui/feed.py:58`, `gozcu/ui/view.py:342-346`
- Modify: `gozcu/ui/web/js/trace.js:48`, `gozcu/ui/web/css/styles.css`
- Test: `tests/test_models.py` (yeni dosya değilse mevcut), `tests/test_kpi.py`

**Interfaces:**
- Produces: `AgentName = Literal["perception", "orchestrator", "interpreter",
  "anomaly_analyst", "risk_analyst", "supervisor", "reporter"]`;
  `gozcu.agents.orchestrator.route(...)`, `gozcu.agents.anomaly_analyst.synthesize(...)`
  — imza değişmiyor, yalnız modül ve ajan adı değişiyor.

- [ ] **Step 1: Yeni adları isteyen testi yaz**

`tests/test_agent_names.py` (yeni dosya):

```python
"""Ajan adları mimari dokümanla eşit olmalı (spec §4)."""
import pytest
from pydantic import ValidationError

from gozcu.models import Handoff


def _handoff(source: str, target: str) -> Handoff:
    return Handoff(ts=1.0, source_agent=source, target_agent=target,
                   reason="test", confidence=0.5, payload_ref="x:1")


def test_new_names_accepted():
    assert _handoff("orchestrator", "interpreter").source_agent == "orchestrator"
    assert _handoff("anomaly_analyst", "risk_analyst").source_agent == "anomaly_analyst"


@pytest.mark.parametrize("stale", ["router", "synthesizer"])
def test_stale_names_rejected(stale):
    """Eski ad kabul edilirse iki sözlük yan yana yaşar ve ayrışır."""
    with pytest.raises(ValidationError):
        _handoff(stale, "supervisor")
```

- [ ] **Step 2: Testi koş, kırmızı olduğunu gör**

Run: `uv run pytest tests/test_agent_names.py -v`
Expected: FAIL — `test_new_names_accepted` `ValidationError` atıyor
(`"orchestrator"` henüz geçerli değil), `test_stale_names_rejected` geçiyor
(ters yönde).

- [ ] **Step 3: `AgentName`'i güncelle**

`gozcu/models.py:39`:

```python
AgentName = Literal["perception", "orchestrator", "interpreter",
                    "anomaly_analyst", "risk_analyst", "supervisor",
                    "reporter"]
```

- [ ] **Step 4: Modülleri git ile yeniden adlandır**

```bash
git mv gozcu/agents/router.py gozcu/agents/orchestrator.py
git mv gozcu/agents/synthesizer.py gozcu/agents/anomaly_analyst.py
git mv tests/test_router.py tests/test_orchestrator.py
git mv tests/test_synthesizer.py tests/test_anomaly_analyst.py
```

- [ ] **Step 5: İçerideki her referansı düzelt**

Sırayla — her biri ayrı bir tür referans, toplu `sed` hepsini yakalamaz:

1. `from gozcu.agents.router import` → `from gozcu.agents.orchestrator import`
   (aynısı synthesizer için) — `gozcu/loop.py`, `gozcu/run.py`,
   `gozcu/agents/supervisor.py`, `tests/`.
2. `Handoff(... source_agent="synthesizer" ...)` →
   `source_agent="anomaly_analyst"` — `gozcu/agents/anomaly_analyst.py`
   (dosya sonu), `gozcu/loop.py:841`.
3. `self._handoff("synthesizer", ...)` → `"anomaly_analyst"` — `gozcu/loop.py:841`.
4. `TARGET` sözlüğü `gozcu/loop.py` — hedef ajan adları.
5. `gozcu/ui/feed.py:58` emoji eşlemesi: `"synthesizer": "🧩"` →
   `"anomaly_analyst": "🧩"`; `router` anahtarı varsa `orchestrator`.
6. `gozcu/ui/web/js/trace.js:48`:

```javascript
const CHAIN_STAGES = ["perception", "orchestrator", "interpreter",
                      "anomaly_analyst", "risk_analyst", "supervisor"];
```

- [ ] **Step 6: KPI kova adlarını KORUYARAK eşleme sözlüğünü güncelle**

`benchmark/kpi.py:60-63` — yalnız **anahtarlar** değişir, kova adları
(`closed_at_router`, `to_synthesizer`) **aynı kalır**, ki `bench/kpi.json`
temeli karşılaştırılabilir kalsın:

```python
#: Orkestratör kararının hedef ajanı -> kova adı.
#:
#: Kova adları AJAN ADLARINDAN BAĞIMSIZ ve bilerek eski: `bench/kpi.json`
#: içindeki ölçüm temeli bu anahtarlarla kaydedildi. `router → orchestrator`
#: yeniden adlandırması (spec §4) sözlüğün anahtarlarını değiştirir, kova
#: adlarını DEĞİL — yoksa 26 Ağustos taban ölçümü karşılaştırılamaz olur.
_BUCKET_BY_TARGET = {"perception": "closed_at_router",
                     "interpreter": "to_interpreter",
                     "anomaly_analyst": "to_synthesizer",
                     "supervisor": "escalated"}
```

`DECISION_BUCKETS`, `gozcu/ui/view.py:342` `DECISION_BUCKET_LABELS` ve
`styles.css` `[data-bucket="to_synthesizer"]` seçicileri **dokunulmadan
kalır**. Türkçe etiketler ("yönlendiricide kapandı", "sentezleyiciye gitti")
Görev 8'de yeni rol adlarına çevrilir; kova anahtarları hiç değişmez.

- [ ] **Step 7: Kova adlarının değişmediğini kilitleyen testi ekle**

`tests/test_kpi.py` sonuna:

```python
def test_bucket_names_survive_agent_rename():
    """Kova adları ajan adlarından bağımsız (spec §4).

    Ayrışmazlarsa `bench/kpi.json` içindeki taban ölçüm okunamaz hâle gelir.
    """
    from benchmark.kpi import DECISION_BUCKETS, _BUCKET_BY_TARGET
    assert "closed_at_router" in DECISION_BUCKETS
    assert "to_synthesizer" in DECISION_BUCKETS
    assert _BUCKET_BY_TARGET["anomaly_analyst"] == "to_synthesizer"
    assert "synthesizer" not in _BUCKET_BY_TARGET
```

- [ ] **Step 8: Bütün testleri koş**

Run: `uv run pytest tests/ -v`
Expected: PASS — hepsi. Bu görev davranış değiştirmiyor; kırmızı kalan bir
test kaçırılmış bir referanstır.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor(agents): router→orchestrator, synthesizer→anomaly_analyst

Mimari doküman ile kod aynı adları kullanıyor (spec §4). Davranış
değişmedi. KPI kova adları bilerek eski kaldı: bench/kpi.json içindeki
taban ölçüm o anahtarlarla kayıtlı."
```

---

## Task 2: Epizot olay sınıfı ve bölge taşısın

**Files:**
- Modify: `gozcu/models.py` — `EventClass`, `Episode.event_class`, `Episode.zone_id`
- Modify: `gozcu/agents/anomaly_analyst.py` — `_SynthesisResponse`, `SYSTEM_PROMPT`, `_parse`, `synthesize`
- Test: `tests/test_anomaly_analyst.py`

**Interfaces:**
- Consumes: Görev 1'in `anomaly_analyst` modülü.
- Produces: `EventClass` Literal; `Episode.event_class: EventClass` (varsayılan
  `"diğer"`), `Episode.zone_id: str | None`. Görev 3 ve 4 bu iki alanla süzüyor.

- [ ] **Step 1: Başarısız testi yaz**

`tests/test_anomaly_analyst.py` sonuna:

```python
def test_episode_carries_event_class_and_zone(store):
    """Sentez epizoda tipli olay sınıfı ve bölge yazar (spec §2b)."""
    payload = json.dumps({
        "phase": "development",
        "summary_tr": "İstif aracı raf ayağına çarptı, malzeme devrildi.",
        "participants": ["IST-04", "PRS-001"],
        "preliminary_risk": "Yüksek",
        "event_class": "çarpma",
        "zone_id": "line_b",
    })
    episode = synthesize(_gw(payload), store, _window(), None, "open_episode")
    assert episode.event_class == "çarpma"
    assert episode.zone_id == "line_b"


def test_unknown_event_class_falls_back_to_diger(store):
    """Uydurulmuş sınıf hiçbir protokolle eşleşmez; sessiz boş plan yerine
    açıkça `"diğer"` (spec §2b)."""
    payload = json.dumps({
        "phase": "development", "summary_tr": "Bir şey oldu.",
        "participants": [], "preliminary_risk": "Orta",
        "event_class": "uzaylı istilası", "zone_id": "line_b",
    })
    episode = synthesize(_gw(payload), store, _window(), None, "open_episode")
    assert episode.event_class == "diğer"


def test_system_prompt_lists_event_classes_verbatim():
    """CLAUDE.md: prompt bir enum sayıyorsa değerleri şemadakiyle birebir."""
    from typing import get_args
    from gozcu.agents.anomaly_analyst import SYSTEM_PROMPT
    from gozcu.models import EventClass
    for value in get_args(EventClass):
        assert f'"{value}"' in SYSTEM_PROMPT, f"prompt {value} saymıyor"


def test_fallback_does_not_overwrite_model_event_class(store):
    """Yedek yanıt, modelin biçtiği sınıfı EZMEZ — `summary_tr` ile aynı kural."""
    good = json.dumps({"phase": "onset", "summary_tr": "Çarpma oldu.",
                       "participants": [], "preliminary_risk": "Yüksek",
                       "event_class": "çarpma", "zone_id": "line_b"})
    synthesize(_gw(good), store, _window(), None, "open_episode")
    episode = synthesize(_gw("bu JSON değil"), store, _window(ts=10.0), None,
                         "update_episode")
    assert episode.event_class == "çarpma"
    assert episode.zone_id == "line_b"
```

`_gw` ve `_window` yardımcıları dosyada zaten var; yoksa mevcut testlerdeki
desenden kopyalanır.

- [ ] **Step 2: Testleri koş, kırmızı olduğunu gör**

Run: `uv run pytest tests/test_anomaly_analyst.py -k "event_class or zone" -v`
Expected: FAIL — `AttributeError: 'Episode' object has no attribute 'event_class'`
ve `ImportError: cannot import name 'EventClass'`.

- [ ] **Step 3: Sözleşmeyi genişlet**

`gozcu/models.py`, `RiskLevel` satırının hemen altına:

```python
#: Olayın türü. **Türkçe** çünkü operatör ekranında ve raporda görünüyor
#: (CLAUDE.md). `"rutin"` bilerek geçerli bir değer: anomali analistinin
#: "burada bir şey yok" diyebilmesi gerekiyor — PDF #3'ün istediği ayrım bu.
#: `"diğer"` uydurulmuş sınıfların düştüğü yer.
EventClass = Literal["sıkışma", "düşme", "çarpma", "yangın",
                     "kimyasal sızıntı", "ekipman arızası",
                     "yetkisiz giriş", "rutin", "diğer"]
```

`Episode` sınıfına, `summary_source` alanının hemen üstüne:

```python
    #: Olayın türü — protokol süzgecinin anahtarı (bkz. `fixtures.match_protocols`).
    #: Serbest metinden okunamaz: `summary_tr` "raf ayağına çarptı" derken
    #: hangi prosedürün geçerli olduğunu bir dize eşlemesi bilemez.
    event_class: EventClass = "diğer"
    #: `facility.json`'daki `zone_id`, birebir. `None` = analist bölgeyi
    #: seçemedi. Saha aracı parametreleri bundan sonra bu alana dayanıyor;
    #: önceden modelin uydurduğu serbest bölge adını `resolve_zone` aracın
    #: İÇİNDE çözmeye çalışıyordu.
    zone_id: str | None = None
```

- [ ] **Step 4: Analistin şemasını ve prompt'unu genişlet**

`gozcu/agents/anomaly_analyst.py`, `_SynthesisResponse`:

```python
    phase: str
    summary_tr: str = Field(max_length=MAX_SUMMARY)
    participants: list[str] = Field(default_factory=list)
    preliminary_risk: RiskLevel
    #: `phase` ile aynı gerekçe: `EventClass` olsaydı modelin uydurduğu bir
    #: sınıf bütün kaydı doğrulama hatasına düşürürdü. `_parse` çekiyor.
    event_class: str = "diğer"
    zone_id: str | None = None
```

`SYSTEM_PROMPT`'un sonuna — değerler `get_args`'tan türetiliyor, elle
kopyalanmıyor (CLAUDE.md kuralı `_describe_tool` deseniyle korunuyor):

```python
from typing import get_args

from gozcu.models import EventClass

_EVENT_CLASS_LINE = ", ".join(f'"{v}"' for v in get_args(EventClass))

SYSTEM_PROMPT = _SYSTEM_TEMPLATE + f"""

`event_class` alanına TAM OLARAK şu değerlerden birini yaz: {_EVENT_CLASS_LINE}.
Olağan üretim akışı için "rutin", hiçbiri uymuyorsa "diğer" kullan.
`zone_id` alanına olayın geçtiği bölgenin kimliğini yaz — TAM OLARAK şu
değerlerden biri: "line_b", "line_b_shipping", "line_c", "warehouse", "yard".
Bölgeyi seçemiyorsan null bırak; uydurma."""
```

> `_SYSTEM_TEMPLATE` bugünkü `SYSTEM_PROMPT` sabitinin yeniden adlandırılmış
> hâli — mevcut metin olduğu gibi kalıyor, üstüne bu blok ekleniyor.
> Bölge kimliklerini prompt'a yazmadan önce `gozcu/fixtures/facility.json`
> içindeki `zones[].zone_id` değerlerini **oku ve birebir kopyala** —
> yukarıdaki liste o dosyadan alındı ama tek doğruluk kaynağı dosyanın
> kendisi. (Görev 3'ün `test_zone_ids_match_facility` testi protokolleri
> kilitliyor, prompt'u değil.)

- [ ] **Step 5: `_parse` bilinmeyen sınıfı çeksin**

`gozcu/agents/anomaly_analyst.py`, `_parse` içinde `phase` çekmesinin yanına:

```python
    if parsed.phase not in PHASES:
        parsed.phase = FALLBACK_PHASE
    if parsed.event_class not in get_args(EventClass):
        parsed.event_class = "diğer"
    return parsed
```

- [ ] **Step 6: `synthesize` alanları yazsın ve yedek onları ezmesin**

Yeni epizot dalı:

```python
        episode = Episode(start_ts=window[0].ts, end_ts=end_ts,
                          phase=synthesis.phase,
                          summary_tr=synthesis.summary_tr,
                          participants=synthesis.participants,
                          preliminary_risk=synthesis.preliminary_risk,
                          event_class=synthesis.event_class,
                          zone_id=synthesis.zone_id,
                          state="open", beats=beats,
                          summary_source=synthesis.summary_source)
```

Kaynaşma dalı — `fields` sözlüğüne iki alan, **ve** yedek koruma listesine:

```python
        fields = {"end_ts": end_ts, "summary_tr": synthesis.summary_tr,
                  "participants": synthesis.participants,
                  "preliminary_risk": synthesis.preliminary_risk,
                  "event_class": synthesis.event_class,
                  "zone_id": synthesis.zone_id,
                  "beats": _merge_beats(open_episode.beats, beats),
                  "summary_source": synthesis.summary_source,
                  "phase": "outcome" if closing else synthesis.phase}
        if (synthesis.summary_source == "fallback"
                and open_episode.summary_source == "model"):
            for key in ("summary_tr", "summary_source", "participants",
                        "preliminary_risk", "event_class", "zone_id"):
                fields.pop(key, None)
```

> `event_class`/`zone_id` koruma listesine ŞART: yedek yanıt onları
> varsayılandan (`"diğer"`, `None`) doldurur, yani ezmek son penceresi
> arızalanan bir olayın protokol eşleşmesini sessizce yok eder.

`store.update_episode`'un bu iki alanı kabul ettiğini doğrula
(`gozcu/store.py:196`); imza `**fields` almıyorsa alan adlarını oraya ekle.

- [ ] **Step 7: Testleri koş**

Run: `uv run pytest tests/test_anomaly_analyst.py -v`
Expected: PASS — dördü de.

- [ ] **Step 8: Bütün testleri koş**

Run: `uv run pytest tests/ -v`
Expected: PASS. `Episode` alan kazandı ama ikisinin de varsayılanı var, yani
mevcut testlerin `Episode(...)` çağrıları bozulmaz.

- [ ] **Step 9: Commit**

```bash
git add gozcu/models.py gozcu/agents/anomaly_analyst.py tests/test_anomaly_analyst.py
git commit -m "feat(anomaly_analyst): epizot olay sınıfı ve bölge taşısın

PDF #3'ün 'rutin akış ile kaza anını ayırır' cümlesi serbest metinden
tipli bir alana taşındı. Protokol süzgecinin (Görev 3) anahtarı bu.
Yedek yanıt modelin biçtiği sınıfı ezmiyor — summary_tr ile aynı kural."
```

---

## Task 3: Protokol sözleşmesi, fixture ve süzgeç

**Files:**
- Modify: `gozcu/models.py` — `ProtocolStep`, `Protocol`
- Create: `gozcu/fixtures/protocols.json`
- Modify: `gozcu/fixtures/loader.py` — `load_protocols()`, `match_protocols()`
- Test: `tests/test_protocols.py` (yeni)

**Interfaces:**
- Consumes: Görev 2'nin `EventClass`, `Episode.event_class`, `Episode.zone_id`.
- Produces:
  - `gozcu.models.Protocol`, `gozcu.models.ProtocolStep`
  - `gozcu.fixtures.loader.load_protocols() -> list[Protocol]`
  - `gozcu.fixtures.loader.match_protocols(event_class: EventClass,
    zone_id: str | None, risk_level: RiskLevel) -> list[Protocol]`
    — `min_risk` eşiğini geçen, bölgesi uyan protokoller; boş liste geçerli
    bir sonuç. Görev 4 bunu çağırıyor.

- [ ] **Step 1: Başarısız testi yaz**

`tests/test_protocols.py` (yeni dosya):

```python
"""Protokol fixture'ı ve deterministik süzgeç (spec §2c, §2e)."""
import json
from pathlib import Path

from gozcu.fixtures.loader import (FIXTURE_DIR, load_fixture, load_protocols,
                                   match_protocols)
from gozcu.tools.registry import TOOLS


def test_protocols_load_and_validate():
    protocols = load_protocols()
    assert 4 <= len(protocols) <= 6, "spec §2c: dört ila altı protokol"
    assert len({p.protocol_id for p in protocols}) == len(protocols)


def test_every_step_binds_a_real_tool():
    """Uydurulmuş araç adı taşıyan protokol, yedek yolunu sessizce bozardı."""
    for protocol in load_protocols():
        assert protocol.steps, f"{protocol.protocol_id} adımsız"
        for step in protocol.steps:
            assert step.tool_name in TOOLS, \
                f"{protocol.protocol_id}: bilinmeyen araç {step.tool_name}"


def test_zone_ids_match_facility():
    """Protokolün bölgesi tesiste yoksa hiçbir olayla eşleşmez."""
    known = {z["zone_id"] for z in load_fixture("facility")["zones"]}
    for protocol in load_protocols():
        for zone_id in protocol.zone_ids:
            assert zone_id in known, f"{protocol.protocol_id}: {zone_id} yok"


def test_match_filters_by_event_class():
    matched = match_protocols("çarpma", "line_b", "Yüksek")
    assert matched
    assert all(p.event_class == "çarpma" for p in matched)


def test_match_filters_by_zone():
    """Bölgesi listelenmiş protokol başka bölgede eşleşmez."""
    scoped = [p for p in load_protocols() if p.zone_ids]
    assert scoped, "en az bir bölgeye bağlı protokol olmalı"
    protocol = scoped[0]
    matched = match_protocols(protocol.event_class, "yard", "Kritik")
    assert protocol.protocol_id not in {p.protocol_id for p in matched} \
        or "yard" in protocol.zone_ids


def test_match_respects_min_risk():
    """`min_risk` altındaki bir olay protokolü tetiklemez."""
    high = match_protocols("çarpma", "line_b", "Kritik")
    low = match_protocols("çarpma", "line_b", "Düşük")
    assert len(low) <= len(high)


def test_empty_zone_ids_means_whole_facility():
    facility_wide = [p for p in load_protocols() if not p.zone_ids]
    for protocol in facility_wide:
        matched = match_protocols(protocol.event_class, "yard", "Kritik")
        assert protocol.protocol_id in {p.protocol_id for p in matched}


def test_unknown_event_class_matches_nothing():
    assert match_protocols("diğer", "line_b", "Kritik") == [] \
        or all(p.event_class == "diğer" for p in match_protocols("diğer", "line_b", "Kritik"))
```

- [ ] **Step 2: Testleri koş, kırmızı olduğunu gör**

Run: `uv run pytest tests/test_protocols.py -v`
Expected: FAIL — `ImportError: cannot import name 'load_protocols'`.

- [ ] **Step 3: Sözleşmeyi ekle**

`gozcu/models.py`, `ProposedAction`'ın hemen üstüne:

```python
class ProtocolStep(Base):
    """Bir prosedür adımı — açıklaması insana, aracı sisteme."""

    order: int
    description_tr: str = Field(max_length=200)
    #: `tools.registry.TOOLS` içinden, birebir. Uydurma ad fixture testinde
    #: yakalanıyor: yedek yolu (spec §2f) adımları DOĞRUDAN plana yazdığı
    #: için burada bir yazım hatası sessizce boş bir müdahaleye dönerdi.
    tool_name: str
    params: dict = Field(default_factory=dict)


class Protocol(Base):
    """Tesisin yazılı prosedürü.

    Planlayıcının bunu UYDURMAMASI tasarımın özü: aday protokoller
    deterministik süzülüp prompt'a yazılıyor, model yalnız aralarından
    seçiyor. `preventable` bu sayede modelin kanaati olmaktan çıkıp
    "prosedür vardı ve uygulanmadı" tespitine dönüşüyor.
    """

    protocol_id: str                    # "PRT-B-CARPMA"
    title_tr: str = Field(max_length=120)
    event_class: EventClass
    #: Boş = bütün tesis. Doluysa yalnız sayılan bölgelerde geçerli.
    zone_ids: list[str] = Field(default_factory=list)
    #: Bu seviyeden İTİBAREN geçerli — altındaki olaylarda tetiklenmez.
    min_risk: RiskLevel
    steps: list[ProtocolStep] = Field(default_factory=list)
```

- [ ] **Step 4: Fixture'ı yaz**

`gozcu/fixtures/protocols.json` — beş protokol. Bölge kimlikleri
`facility.json`'dan, araç adları `tools/registry.py::TOOLS`'tan:

```json
{
  "protocols": [
    {
      "protocol_id": "PRT-B-CARPMA",
      "title_tr": "B-Hattı istif aracı çarpması",
      "event_class": "çarpma",
      "zone_ids": ["line_b", "line_b_shipping"],
      "min_risk": "Orta",
      "steps": [
        {"order": 1, "description_tr": "B hattını durdur",
         "tool_name": "halt_production_line",
         "params": {"line_id": "B", "rationale": "İstif aracı çarpması"}},
        {"order": 2, "description_tr": "Revir-2'yi olay yerine çağır",
         "tool_name": "dispatch_medical",
         "params": {"location": "line_b", "urgency": "critical"}},
        {"order": 3, "description_tr": "Vardiya amirine telsizle bildir",
         "tool_name": "radio_call",
         "params": {"unit": "vardiya_amiri",
                    "message": "B-Hattında istif aracı çarpması"}},
        {"order": 4, "description_tr": "İSG olay kaydı aç",
         "tool_name": "open_safety_incident",
         "params": {"classification": "çarpma"}}
      ]
    },
    {
      "protocol_id": "PRT-GENEL-SIKISMA",
      "title_tr": "Ekipman-personel sıkışması",
      "event_class": "sıkışma",
      "zone_ids": [],
      "min_risk": "Orta",
      "steps": [
        {"order": 1, "description_tr": "Bölgedeki hattı derhal durdur",
         "tool_name": "halt_production_line",
         "params": {"rationale": "Personel sıkışması"}},
        {"order": 2, "description_tr": "Sağlık ekibini acil çağır",
         "tool_name": "dispatch_medical", "params": {"urgency": "critical"}},
        {"order": 3, "description_tr": "İSG olay kaydı aç",
         "tool_name": "open_safety_incident",
         "params": {"classification": "sıkışma"}}
      ]
    },
    {
      "protocol_id": "PRT-GENEL-DUSME",
      "title_tr": "Yüksekten veya seviyeden düşme",
      "event_class": "düşme",
      "zone_ids": [],
      "min_risk": "Orta",
      "steps": [
        {"order": 1, "description_tr": "Sağlık ekibini çağır",
         "tool_name": "dispatch_medical", "params": {"urgency": "critical"}},
        {"order": 2, "description_tr": "Alanı çevrele ve uyarı ver",
         "tool_name": "site_alarm", "params": {"level": "warning"}},
        {"order": 3, "description_tr": "İSG olay kaydı aç",
         "tool_name": "open_safety_incident",
         "params": {"classification": "düşme"}}
      ]
    },
    {
      "protocol_id": "PRT-GENEL-YANGIN",
      "title_tr": "Yangın veya duman",
      "event_class": "yangın",
      "zone_ids": [],
      "min_risk": "Yüksek",
      "steps": [
        {"order": 1, "description_tr": "Tesis alarmını en yüksek seviyede çal",
         "tool_name": "site_alarm", "params": {"level": "critical"}},
        {"order": 2, "description_tr": "Bölgedeki hattı durdur",
         "tool_name": "halt_production_line",
         "params": {"rationale": "Yangın alarmı"}},
        {"order": 3, "description_tr": "İtfaiye ekibini telsizle çağır",
         "tool_name": "radio_call",
         "params": {"unit": "itfaiye", "message": "Yangın ihbarı"}}
      ]
    },
    {
      "protocol_id": "PRT-GENEL-EKIPMAN",
      "title_tr": "Ekipman arızası — bakım gecikmeli",
      "event_class": "ekipman arızası",
      "zone_ids": [],
      "min_risk": "Orta",
      "steps": [
        {"order": 1, "description_tr": "Ekipmanın bakım geçmişini doğrula",
         "tool_name": "query_equipment_history", "params": {}},
        {"order": 2, "description_tr": "Bakım ekibine telsizle bildir",
         "tool_name": "radio_call",
         "params": {"unit": "bakim", "message": "Arızalı ekipman bildirimi"}}
      ]
    }
  ]
}
```

> `params` bilerek EKSİK yerlerde (`line_id`, `location`, `equipment_id`):
> planlayıcı bunları epizodun `zone_id`'si ve katılımcılarıyla dolduruyor
> (Görev 4). Yedek yolunda ise adım olduğu gibi geçiyor ve aracın kendi
> `resolve_zone` savunması devreye giriyor.

- [ ] **Step 5: Yükleyici ve süzgeci yaz**

`gozcu/fixtures/loader.py` sonuna:

```python
from gozcu.models import EventClass, Protocol, RiskLevel

#: Risk seviyesinin sıralaması — `min_risk` eşiği bununla karşılaştırılıyor.
#: `report.ORDER`'ın ikizi değil: orası çıktı sözleşmesinin en yüksek riskini
#: seçiyor, burası bir eşik testi yapıyor ve ikisi ayrı sebeplerle değişebilir.
_RISK_ORDER: tuple[RiskLevel, ...] = ("Düşük", "Orta", "Yüksek", "Kritik")


def load_protocols() -> list[Protocol]:
    """`protocols.json`'ı doğrulanmış `Protocol` listesine çevirir."""
    raw = load_fixture("protocols")["protocols"]
    return [Protocol(**item) for item in raw]


def match_protocols(event_class: EventClass, zone_id: str | None,
                    risk_level: RiskLevel) -> list[Protocol]:
    """Olaya uyan protokoller — **deterministik**, model karışmıyor.

    Üç süzgeç birlikte uygulanıyor:

    1. `event_class` birebir eşleşmeli. Uydurulmuş bir sınıf (`"diğer"`e
       düşürülmüş olan) hiçbir prosedürle eşleşmez ve bu doğru: yanlış
       prosedürü uygulamak, prosedürsüz kalmaktan kötüdür.
    2. `zone_ids` boşsa protokol bütün tesiste geçerli; doluysa olayın
       bölgesi listede olmalı. Bölge bilinmiyorsa (`zone_id is None`)
       yalnız tesis geneli protokoller eşleşir — bölgeye özgü bir prosedürü
       bilinmeyen bir bölgeye uygulamak varsayım üretmek olurdu.
    3. Olayın riski `min_risk`'in ALTINDAysa protokol tetiklenmez.

    Boş liste geçerli bir sonuç: çağıran (`action_planner`) onu
    `plan_source="empty"` ile kaydediyor, uydurulmuş bir plana düşmüyor.
    """
    threshold = _RISK_ORDER.index(risk_level)
    return [p for p in load_protocols()
            if p.event_class == event_class
            and (not p.zone_ids or (zone_id is not None
                                    and zone_id in p.zone_ids))
            and threshold >= _RISK_ORDER.index(p.min_risk)]
```

- [ ] **Step 6: Testleri koş**

Run: `uv run pytest tests/test_protocols.py -v`
Expected: PASS — sekizi de.

- [ ] **Step 7: Bütün testleri koş**

Run: `uv run pytest tests/ -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add gozcu/models.py gozcu/fixtures/protocols.json gozcu/fixtures/loader.py tests/test_protocols.py
git commit -m "feat(fixtures): tesisin yazılı prosedürleri ve deterministik süzgeç

Beş protokol, her adımı gerçek bir saha aracına bağlı. match_protocols
olay sınıfı + bölge + risk eşiğiyle süzüyor; model süzgece karışmıyor,
yalnız süzülmüş adaylar arasından seçiyor (spec §2c, §2e)."
```

---

## Task 4: `action_planner` ajanı

**Files:**
- Modify: `gozcu/models.py` — `AgentName` (+`action_planner`), `ActionPlan`
- Modify: `gozcu/store.py` — `action_plan` tablosu, `save_action_plan`, `action_plans`
- Create: `gozcu/agents/action_planner.py`
- Test: `tests/test_action_planner.py` (yeni)

**Interfaces:**
- Consumes: Görev 3'ün `match_protocols`, Görev 2'nin `Episode.event_class` /
  `zone_id`, mevcut `RiskAssessment`.
- Produces:
  - `gozcu.models.ActionPlan`
  - `Store.save_action_plan(plan: ActionPlan) -> int`
  - `Store.action_plans() -> list[ActionPlan]`
  - `gozcu.agents.action_planner.plan_actions(gw, store, episode: Episode,
    assessment: RiskAssessment) -> ActionPlan`
    — kaydeder, `risk_analyst → action_planner` ve
    `action_planner → supervisor` devirlerini deftere yazar, planı döndürür.
    Görev 5, 6, 7 bunu çağırıyor.

- [ ] **Step 1: Başarısız testleri yaz**

`tests/test_action_planner.py` (yeni dosya):

```python
"""Karar & Aksiyon ajanı — protokol seçici (spec §2)."""
import json

import pytest

from gozcu.agents.action_planner import plan_actions
from gozcu.models import Episode, RiskAssessment
from gozcu.store import Store
from gozcu.tools.registry import TOOLS


@pytest.fixture
def store():
    return Store()


def _gw(content: str, degraded: bool = False):
    """Tek yanıtlık sahte ağ geçidi — `tests/test_risk.py` deseni."""
    class _Response:
        def __init__(self):
            self.content = content
            self.degraded = degraded
            self.tool_calls = []
    class _GW:
        def ask(self, *args, **kwargs):
            return _Response()
    return _GW()


def _episode(store, event_class="çarpma", zone_id="line_b") -> Episode:
    episode = Episode(start_ts=0.0, end_ts=10.0, phase="outcome",
                      summary_tr="İstif aracı raf ayağına çarptı.",
                      participants=["IST-04", "PRS-001"],
                      preliminary_risk="Yüksek", state="closed",
                      event_class=event_class, zone_id=zone_id)
    episode.id = store.create_episode(episode)
    return episode


def _assessment(store, episode, level="Yüksek") -> RiskAssessment:
    assessment = RiskAssessment(episode_id=episode.id, ts=10.0, level=level,
                                rationale_tr="Ağır yaralanma riski.",
                                preventable=True)
    assessment.id = store.save_risk(assessment)
    return assessment


def test_plan_binds_actions_to_selected_protocol(store):
    episode = _episode(store)
    assessment = _assessment(store, episode)
    payload = json.dumps({
        "protocol_id": "PRT-B-CARPMA",
        "rationale_tr": "B-Hattı çarpma prosedürü geçerli.",
        "proposed_actions": [
            {"description_tr": "B hattını durdur",
             "tool_name": "halt_production_line",
             "params": {"line_id": "B", "rationale": "çarpma"}},
            {"description_tr": "Sağlık ekibini çağır",
             "tool_name": "dispatch_medical",
             "params": {"location": "line_b", "urgency": "critical"}},
        ]})
    plan = plan_actions(_gw(payload), store, episode, assessment)
    assert plan.protocol_id == "PRT-B-CARPMA"
    assert plan.plan_source == "model"
    assert [a.tool_name for a in plan.proposed_actions] == [
        "halt_production_line", "dispatch_medical"]


def test_unreadable_response_falls_back_to_protocol_steps(store):
    """Model susarsa protokolün adımları BİREBİR plana yazılır (spec §2f)."""
    episode = _episode(store)
    assessment = _assessment(store, episode)
    plan = plan_actions(_gw("bu JSON değil"), store, episode, assessment)
    assert plan.plan_source == "protocol_fallback"
    assert plan.protocol_id == "PRT-B-CARPMA"
    assert plan.proposed_actions, "yedek boş plan üretmemeli"
    assert all(a.tool_name in TOOLS for a in plan.proposed_actions)


def test_no_matching_protocol_yields_empty_plan(store):
    """Eşleşen protokol yoksa plan BOŞ — uydurulmuş bir plan değil."""
    episode = _episode(store, event_class="rutin", zone_id="yard")
    assessment = _assessment(store, episode, level="Düşük")
    plan = plan_actions(_gw("bu JSON değil"), store, episode, assessment)
    assert plan.plan_source == "empty"
    assert plan.proposed_actions == []
    assert plan.protocol_id is None
    assert plan.rationale_tr, "sebep yazılmalı"


def test_invented_tool_name_is_dropped(store):
    episode = _episode(store)
    assessment = _assessment(store, episode)
    payload = json.dumps({
        "protocol_id": "PRT-B-CARPMA", "rationale_tr": "gerekçe",
        "proposed_actions": [
            {"description_tr": "helikopter çağır",
             "tool_name": "dispatch_helicopter", "params": {}},
            {"description_tr": "Sağlık ekibini çağır",
             "tool_name": "dispatch_medical", "params": {}},
        ]})
    plan = plan_actions(_gw(payload), store, episode, assessment)
    assert [a.tool_name for a in plan.proposed_actions] == ["dispatch_medical"]


def test_invented_protocol_id_is_rejected(store):
    """Model aday listesinde OLMAYAN bir protokol uydurursa reddedilir."""
    episode = _episode(store)
    assessment = _assessment(store, episode)
    payload = json.dumps({
        "protocol_id": "PRT-UYDURMA", "rationale_tr": "gerekçe",
        "proposed_actions": [{"description_tr": "Sağlık ekibini çağır",
                              "tool_name": "dispatch_medical", "params": {}}]})
    plan = plan_actions(_gw(payload), store, episode, assessment)
    assert plan.protocol_id is None


def test_planner_is_offered_only_read_tools(store, monkeypatch):
    """Yazma araçları bu ajana KAPALI (spec §2e)."""
    from gozcu.agents import action_planner as module
    seen = {}

    class _GW:
        def ask(self, tier, messages, **kwargs):
            seen["tools"] = kwargs.get("tools", [])
            class _R:
                content = "bu JSON değil"
                degraded = False
                tool_calls = []
            return _R()

    episode = _episode(store)
    plan_actions(_GW(), store, episode, _assessment(store, episode))
    offered = {s["function"]["name"] for s in seen["tools"]}
    assert offered <= {"query_shift_personnel", "query_equipment_history"}


def test_plan_is_persisted_and_handed_off(store):
    episode = _episode(store)
    assessment = _assessment(store, episode)
    plan_actions(_gw("bu JSON değil"), store, episode, assessment)
    assert len(store.action_plans()) == 1
    targets = [(h.source_agent, h.target_agent) for h in store.handoffs()]
    assert ("risk_analyst", "action_planner") in targets
    assert ("action_planner", "supervisor") in targets


def test_plan_timestamp_follows_video_clock(store):
    """Plan videonun anına yazılır, duvar saatine değil."""
    episode = _episode(store)
    assessment = _assessment(store, episode)
    plan = plan_actions(_gw("bu JSON değil"), store, episode, assessment)
    assert plan.ts == episode.end_ts
```

- [ ] **Step 2: Testleri koş, kırmızı olduğunu gör**

Run: `uv run pytest tests/test_action_planner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gozcu.agents.action_planner'`.

- [ ] **Step 3: Sözleşmeyi ekle**

`gozcu/models.py` — `AgentName`'e yeni durak:

```python
AgentName = Literal["perception", "orchestrator", "interpreter",
                    "anomaly_analyst", "risk_analyst", "action_planner",
                    "supervisor", "reporter"]
```

`RiskAssessment`'ın hemen altına:

```python
class ActionPlan(Base):
    """Karar & Aksiyon ajanının çıktısı.

    `RiskAssessment` içinde DEĞİL, ayrı bir kayıt: spec'in kuralı "hiçbir şey
    bir ajan sınırını serbest metin olarak geçmez, her devir tipli bir
    kayıttır" — bir ajanın başka bir ajanın kaydına yazması tipler tutsa bile
    bu kuralı bozar ve trace panelinde iki ajanın işi tek satırda görünür.
    """

    id: int | None = None
    #: Videonun saati, duvarın değil (bkz. `RiskAssessment.ts`).
    ts: float = 0.0
    episode_id: int
    risk_assessment_id: int
    #: Uygulanan prosedür; `None` = eşleşen protokol yoktu ya da model
    #: aday listesinde olmayan bir kimlik uydurdu.
    protocol_id: str | None = None
    rationale_tr: str = Field(max_length=800)
    proposed_actions: list[ProposedAction] = Field(default_factory=list)
    #: `"model"` planı model kurdu · `"protocol_fallback"` model okunamadı,
    #: protokolün adımları birebir yazıldı · `"empty"` eşleşen protokol yok.
    #: Metne bakarak ayırt edilemez ve ayırt edilmezse kök neden raporu
    #: deterministik bir yedeği modelin kararı gibi anlatır.
    plan_source: Literal["model", "protocol_fallback", "empty"] = "model"
```

- [ ] **Step 4: Depoyu genişlet**

`gozcu/store.py`, `SCHEMA` içine (`action` satırının altına):

```sql
CREATE TABLE IF NOT EXISTS action_plan (id INTEGER PRIMARY KEY, payload TEXT);
```

`save_risk`'in hemen altına:

```python
    def save_action_plan(self, plan: ActionPlan) -> int:
        return self._insert("action_plan", plan)

    def action_plans(self) -> list[ActionPlan]:
        return self._read("action_plan", ActionPlan)
```

`ActionPlan`'ı `gozcu/store.py`'nin import satırına ekle.

- [ ] **Step 5: Ajanı yaz**

`gozcu/agents/action_planner.py` (yeni dosya):

```python
"""Karar & Aksiyon ajanı — riske karşı protokole dayalı müdahale planı.

Bu ajanın var oluş sebebi, risk analistinden bir alanı devralmak değil:
planı **tesisin yazılı prosedürüne** bağlamak. Aday protokoller deterministik
süzülüp prompt'a yazılıyor (`fixtures.match_protocols`), model yalnız
aralarından seçiyor. İki sonucu var:

- `preventable` modelin kanaati olmaktan çıkıyor: "PRT-B-CARPMA prosedürü
  vardı ve uygulanmadı" denebilir hâle geliyor (kök neden raporu, Görev 7).
- Deterministik bir yedek doğuyor: model susarsa protokolün adımları birebir
  plana yazılıyor. Çıktı sözleşmesinin `actions` anahtarı artık model
  başarısına bağlı değil.

**Yazma araçları bu ajana kapalı.** Müdahale araçlarını yalnız Nöbetçi'nin
onay kapısı çağırır; planlayıcı öneri üretir, tetiklemez.
"""
import json

from pydantic import BaseModel, ConfigDict, Field

from gozcu.agents.interpreter import _sanitize_text
from gozcu.agents.risk import _describe_tool
from gozcu.fixtures.loader import match_protocols
from gozcu.models import (ActionPlan, Episode, Handoff, ProposedAction,
                          RiskAssessment)
from gozcu.tools.registry import TOOL_SCHEMAS, TOOLS

MAX_RATIONALE = 800
MAX_ACTION_DESCRIPTION = 200
PLANNER_MAX_TOKENS = 4096

#: Planlayıcıya sunulan araçlar — yalnız okuma. `risk.READ_TOOL_SCHEMAS`'ın
#: ikizi değil: analist arşive de bakıyor, planlayıcı yalnız parametre
#: dolduruyor. İkisi ayrı sebeplerle değişebilir.
PLANNER_READ_TOOLS = ("query_shift_personnel", "query_equipment_history")
PLANNER_TOOL_SCHEMAS = [s for s in TOOL_SCHEMAS
                        if s["function"]["name"] in PLANNER_READ_TOOLS]

NO_PROTOCOL_RATIONALE = ("Bu olay sınıfı ve bölge için tanımlı bir prosedür "
                         "bulunmadı; müdahale önerisi üretilmedi.")
FALLBACK_RATIONALE = ("Plan katmanı okunabilir yanıt vermedi; {title} "
                      "prosedürünün adımları doğrudan uygulandı.")

SYSTEM_PROMPT = """Sen bir fabrikanın İSG müdahale protokolü uzmanısın.

Sana bir olay, o olayın risk değerlendirmesi ve tesiste TANIMLI prosedürler
veriliyor. Görevin: geçerli prosedürü seçmek ve adımlarını olayın somut
verileriyle (bölge, ekipman, personel) doldurulmuş müdahale önerilerine
çevirmek.

KURALLAR:
- `protocol_id` alanına SADECE sana verilen aday prosedürlerden birinin
  kimliğini yaz. Hiçbiri uymuyorsa null yaz. Prosedür UYDURMA.
- Her öneriyi SADECE aşağıdaki araçlardan birine bağla. Araç adını ve
  parametre değerlerini burada yazdığı gibi, birebir kullan:
{tools}
- Parametreleri olayın verilerinden doldur. Bilmiyorsan aracı çağırıp öğren;
  uydurma.
- Sadece JSON döndür."""


class _PlanResponse(BaseModel):
    """Modelden beklenen şekil.

    `ActionPlan`'dan ayrı: onun `id`, `episode_id`, `risk_assessment_id` ve
    `plan_source` alanları var ve katı şema modunda her alan `required`
    oluyor — model kendi veritabanı kimliğini uydurmak zorunda kalırdı.
    """

    model_config = ConfigDict(extra="forbid")

    protocol_id: str | None = None
    rationale_tr: str = Field(max_length=MAX_RATIONALE)
    proposed_actions: list[ProposedAction] = Field(default_factory=list)


def _describe_protocol(protocol) -> str:
    """Bir protokolü prompt satırlarına çevirir."""
    lines = [f"- {protocol.protocol_id}: {protocol.title_tr} "
             f"(en az {protocol.min_risk} risk)"]
    for step in sorted(protocol.steps, key=lambda s: s.order):
        lines.append(f"    {step.order}. {step.description_tr} "
                     f"→ {step.tool_name} {json.dumps(step.params, ensure_ascii=False)}")
    return "\n".join(lines)


def _prompt(episode: Episode, assessment: RiskAssessment,
            candidates: list) -> str:
    participants = ", ".join(episode.participants) or "(bilinmiyor)"
    catalogue = "\n".join(_describe_protocol(p) for p in candidates)
    return "\n".join([
        f"OLAY: {episode.summary_tr}",
        f"OLAY SINIFI: {episode.event_class}",
        f"BÖLGE: {episode.zone_id or '(bilinmiyor)'}",
        f"KATILIMCILAR (ekipman/personel kimlikleri): {participants}",
        f"RİSK: {assessment.level} — {assessment.rationale_tr}",
        f"ÖNLENEBİLİR: {'evet' if assessment.preventable else 'hayır'}",
        f"\nADAY PROSEDÜRLER:\n{catalogue}",
    ])


def _parse(content: str) -> _PlanResponse | None:
    """Ham çıktıyı doğrulanmış yanıta çevirir; olmazsa `None`."""
    try:
        data = json.loads(content)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    rationale = data.get("rationale_tr")
    if isinstance(rationale, str):
        data["rationale_tr"] = _sanitize_text(rationale, MAX_RATIONALE)
    actions = data.get("proposed_actions")
    if isinstance(actions, list):
        data["proposed_actions"] = [_sanitize_action(a) for a in actions]

    try:
        return _PlanResponse(**data)
    except Exception:  # noqa: BLE001 — bozuk çıktı bir koşuyu düşürmemeli
        return None


def _sanitize_action(action):
    """Öneri açıklamasını sınıra çeker (risk.py'deki ikizinin aynısı:
    tek uzun bir öneri bütün planı doğrulama hatasına düşürmemeli)."""
    if not isinstance(action, dict):
        return action
    description = action.get("description_tr")
    if not isinstance(description, str):
        return action
    return {**action,
            "description_tr": _sanitize_text(description,
                                             MAX_ACTION_DESCRIPTION)}


def _from_protocol(protocol) -> list[ProposedAction]:
    """Protokol adımlarını BİREBİR önerilere çevirir — deterministik yedek."""
    return [ProposedAction(description_tr=step.description_tr,
                           tool_name=step.tool_name, params=dict(step.params))
            for step in sorted(protocol.steps, key=lambda s: s.order)
            if step.tool_name in TOOLS]


def plan_actions(gw, store, episode: Episode,
                 assessment: RiskAssessment) -> ActionPlan:
    """Epizoda karşı müdahale planı üretir, kaydeder ve devreder.

    Akış: protokolleri süz → aday yoksa boş plan → modele sor → okunamazsa
    protokol adımlarına düş → süz, kaydet, devret.
    """
    # Videonun "şimdi"si — `start_ts` uzun bir olayda saati olayın başında
    # dondurur (risk.py'deki aynı kural).
    now = episode.end_ts or episode.start_ts

    candidates = match_protocols(episode.event_class, episode.zone_id,
                                 assessment.level)

    if not candidates:
        return _save(store, ActionPlan(
            episode_id=episode.id, risk_assessment_id=assessment.id, ts=now,
            protocol_id=None, rationale_tr=NO_PROTOCOL_RATIONALE,
            proposed_actions=[], plan_source="empty"))

    response = gw.ask("main", [
        {"role": "system",
         "content": SYSTEM_PROMPT.format(
             tools="\n".join(_describe_tool(s) for s in TOOL_SCHEMAS))},
        {"role": "user", "content": _prompt(episode, assessment, candidates)},
    ], schema=_PlanResponse, tools=PLANNER_TOOL_SCHEMAS,
        max_tokens=PLANNER_MAX_TOKENS)

    parsed = None if response.degraded else _parse(response.content or "")

    if parsed is None:
        protocol = candidates[0]
        return _save(store, ActionPlan(
            episode_id=episode.id, risk_assessment_id=assessment.id, ts=now,
            protocol_id=protocol.protocol_id,
            rationale_tr=FALLBACK_RATIONALE.format(title=protocol.title_tr),
            proposed_actions=_from_protocol(protocol),
            plan_source="protocol_fallback"))

    # Uydurulmuş protokol kimliği reddedilir: aday listesinde olmayan bir
    # kimlik raporda "prosedür uygulandı" diye görünürdü.
    known = {p.protocol_id for p in candidates}
    protocol_id = parsed.protocol_id if parsed.protocol_id in known else None

    # Uydurulmuş araç adları düşürülür, Nöbetçi'ye asla iletilmez.
    actions = [a for a in parsed.proposed_actions if a.tool_name in TOOLS]

    return _save(store, ActionPlan(
        episode_id=episode.id, risk_assessment_id=assessment.id, ts=now,
        protocol_id=protocol_id, rationale_tr=parsed.rationale_tr,
        proposed_actions=actions, plan_source="model"))


def _save(store, plan: ActionPlan) -> ActionPlan:
    """Planı kaydeder ve iki devri deftere yazar.

    İKİ devir, çünkü planlayıcı zincirin bir DURAĞI: gelen kenar
    (risk analistinden) ve giden kenar (Nöbetçi'ye) ayrı ayrı görünmezse
    trace paneli yeni ajanı zincirin dışında, kopuk bir kutu olarak çizer.
    """
    plan.id = store.save_action_plan(plan)
    store.save_handoff(Handoff(
        ts=plan.ts, source_agent="risk_analyst", target_agent="action_planner",
        reason=f"plan isteniyor: episode {plan.episode_id}", confidence=0.9,
        payload_ref=f"risk:{plan.risk_assessment_id}"))
    store.save_handoff(Handoff(
        ts=plan.ts, source_agent="action_planner", target_agent="supervisor",
        reason=f"plan: {plan.protocol_id or '(prosedür yok)'} "
               f"— {len(plan.proposed_actions)} öneri",
        confidence=0.85, payload_ref=f"plan:{plan.id}"))
    return plan
```

- [ ] **Step 6: Testleri koş**

Run: `uv run pytest tests/test_action_planner.py -v`
Expected: PASS — sekizi de.

- [ ] **Step 7: Bütün testleri koş**

Run: `uv run pytest tests/ -v`
Expected: PASS. Bu görev hiçbir mevcut çağrı yolunu değiştirmedi; planlayıcı
henüz zincire bağlı değil (Görev 5).

- [ ] **Step 8: Commit**

```bash
git add gozcu/models.py gozcu/store.py gozcu/agents/action_planner.py tests/test_action_planner.py
git commit -m "feat(action_planner): protokole dayalı Karar & Aksiyon ajanı

PDF #5. Aday protokoller deterministik süzülüp prompt'a yazılıyor; model
uydurmuyor, seçiyor. Model okunamazsa protokol adımları birebir plana
düşüyor — actions anahtarı artık model başarısına bağlı değil (spec §2)."
```

---

## Task 5: Planlayıcıyı zincire bağla

**Files:**
- Modify: `gozcu/run.py` — `assess_risk` çağrılarının üçü
- Modify: `gozcu/agents/supervisor.py` — `escalate` mesajı, `_internal_tool`, `_apply_correction`
- Modify: `gozcu/ui/web/js/trace.js:48`, `gozcu/ui/feed.py:58`
- Test: `tests/test_run.py`, `tests/test_supervisor.py`

**Interfaces:**
- Consumes: Görev 4'ün `plan_actions(gw, store, episode, assessment) -> ActionPlan`.
- Produces: `gozcu.agents.supervisor.Supervisor` yükseltme mesajı artık planın
  `protocol_id`, `title_tr` ve önerilerini taşıyor. Görev 7 raporu bu plandan
  okuyor.

> **Bu görev planlayıcıyı dekoratif olmaktan çıkarır.** Nöbetçi bugün
> `proposed_actions`'ı HİÇ okumuyor — `escalate` mesajı yalnız `risk.level` ve
> `risk.rationale_tr` taşıyor, araç seçimini süpervizör kendi yapıyor. Plan
> mesaja girmezse yeni ajan yalnız raporu ve besleme panelini besler, karar
> veren ajanı etkilemez.

- [ ] **Step 1: Başarısız testi yaz**

`tests/test_supervisor.py` sonuna:

```python
def test_escalation_message_carries_the_plan(store, monkeypatch):
    """Plan yükseltme mesajına girmezse planlayıcı dekoratif kalır (spec §5)."""
    from gozcu.models import ActionPlan, ProposedAction

    episode = _episode(store)
    risk = _risk(episode)
    plan = ActionPlan(episode_id=episode.id, risk_assessment_id=1, ts=10.0,
                      protocol_id="PRT-B-CARPMA",
                      rationale_tr="B-Hattı çarpma prosedürü geçerli.",
                      proposed_actions=[
                          ProposedAction(description_tr="B hattını durdur",
                                         tool_name="halt_production_line",
                                         params={"line_id": "B"})],
                      plan_source="model")
    plan.id = store.save_action_plan(plan)

    monkeypatch.setattr("gozcu.agents.supervisor.assess_risk",
                        lambda *a, **k: risk)
    monkeypatch.setattr("gozcu.agents.supervisor.plan_actions",
                        lambda *a, **k: plan)

    supervisor = Supervisor(_gw("Anlaşıldı."), store)
    supervisor.escalate(episode)

    system_turns = [m["content"] for m in supervisor.history
                    if m["role"] == "user" and "[SİSTEM]" in m["content"]]
    assert system_turns
    message = system_turns[-1]
    assert "PRT-B-CARPMA" in message
    assert "B hattını durdur" in message


def test_escalation_without_plan_still_speaks(store, monkeypatch):
    """Boş plan yükseltmeyi düşürmez — çıktı sözleşmesi her hâlükârda."""
    from gozcu.models import ActionPlan

    episode = _episode(store)
    risk = _risk(episode)
    plan = ActionPlan(episode_id=episode.id, risk_assessment_id=1, ts=10.0,
                      protocol_id=None, rationale_tr="prosedür yok",
                      proposed_actions=[], plan_source="empty")
    monkeypatch.setattr("gozcu.agents.supervisor.assess_risk",
                        lambda *a, **k: risk)
    monkeypatch.setattr("gozcu.agents.supervisor.plan_actions",
                        lambda *a, **k: plan)
    supervisor = Supervisor(_gw("Anlaşıldı."), store)
    assert supervisor.escalate(episode)
```

`tests/test_run.py` sonuna:

```python
def _fake_assess_returning(calls, level="Kritik"):
    """`assess_risk` ikizi — ama değerlendirmeyi DÖNDÜRÜR.

    Mevcut `_fake_assess_that_escalates` yalnız depoya yazıp `None`
    döndürüyor; `run.py` artık dönen değeri planlayıcıya verdiği için o ikiz
    `plan_actions(..., None)` çağrısına yol açar. Yeni ikiz aynı işi yapıp
    kaydı geri veriyor.
    """
    def _assess(gw, store, episode):
        calls.append(episode.id)
        assessment = RiskAssessment(
            episode_id=episode.id,
            ts=episode.end_ts if episode.end_ts is not None else episode.start_ts,
            level=level, rationale_tr="İstif aracı devrilmiş, kişi yerde.",
            preventable=True)
        assessment.id = store.save_risk(assessment)
        return assessment
    return _assess


def test_every_assessment_is_followed_by_a_plan(monkeypatch):
    """Süpürme bir epizodu değerlendirdiyse planlayıcı da koşmalı.

    Bağlanmazsa yeni ajan yalnız süpervizör yolunda çalışır ve koşu sonunda
    yeniden değerlendirilen epizotlar plansız kalır — `actions` anahtarı da
    onlarla birlikte boşalır.
    """
    store = Store(":memory:")
    episode = _seed_episode(store, end_ts=99.0)
    store.save_risk(RiskAssessment(episode_id=episode.id, ts=19.0,
                                   level="Yüksek",
                                   rationale_tr="Araç sallanıyor.",
                                   preventable=True))
    assessed: list[int] = []
    planned: list[int] = []
    monkeypatch.setattr(run_module, "assess_risk",
                        _fake_assess_returning(assessed))
    monkeypatch.setattr(run_module, "plan_actions",
                        lambda gw, st, ep, a: planned.append(ep.id))

    _sweep_stale_risk(gw=None, store=store, fresh=[episode])

    assert assessed == [episode.id]
    assert planned == [episode.id], "değerlendirildi ama plan üretilmedi"


def test_the_plan_receives_the_assessment_that_was_just_made(monkeypatch):
    """Planlayıcıya geçen kayıt, o an üretilen değerlendirmenin ta kendisi
    olmalı — bayat bir kayıt geçerse plan yanlış seviyeye göre kurulur."""
    store = Store(":memory:")
    episode = _seed_episode(store, end_ts=30.0)
    seen: list[str] = []
    monkeypatch.setattr(run_module, "assess_risk",
                        _fake_assess_returning([], level="Kritik"))
    monkeypatch.setattr(run_module, "plan_actions",
                        lambda gw, st, ep, a: seen.append(a.level))

    _sweep_stale_risk(gw=None, store=store, fresh=[episode])

    assert seen == ["Kritik"]
```

- [ ] **Step 2: Testleri koş, kırmızı olduğunu gör**

Run: `uv run pytest tests/test_supervisor.py -k plan tests/test_run.py -k plan -v`
Expected: FAIL — `AttributeError: module 'gozcu.agents.supervisor' has no
attribute 'plan_actions'`.

- [ ] **Step 3: Nöbetçiyi planla besle**

`gozcu/agents/supervisor.py` — import:

```python
from gozcu.agents.action_planner import plan_actions
```

`escalate` içinde, `risk = assess_risk(...)` satırının hemen altına:

```python
            risk = assess_risk(self.gw, self.store, episode)
            plan = plan_actions(self.gw, self.store, episode, risk)
        else:
            plan = self._latest_plan(episode)
```

Yeni yardımcı, `_latest_risk`'in hemen altına:

```python
    def _latest_plan(self, episode: Episode):
        """Epizodun depodaki SON planı; yoksa None."""
        rows = [p for p in self.store.action_plans()
                if p.episode_id == episode.id]
        return rows[-1] if rows else None
```

Mesaj kurulumu — `PLAN_LINE` sabiti dosya başına:

```python
#: Planın yükseltme mesajındaki satırı. Nöbetçi araç kataloğunu zaten
#: görüyor; bu satır ona hangi prosedürün geçerli olduğunu söylüyor ki
#: seçimi kendi sezgisi değil tesisin kuralı belirlesin.
PLAN_LINE = ("Geçerli prosedür: {protocol}. Önerilen müdahale: {actions}. "
             "Bu öneriyi operatöre sun ve onay iste.")
NO_PLAN_LINE = ("Bu olay için tanımlı bir prosedür yok; müdahaleyi kendi "
                "değerlendirmenle öner.")


def plan_line(plan) -> str:
    """Planı tek satırlık talimata çevirir."""
    if plan is None or not plan.proposed_actions:
        return NO_PLAN_LINE
    actions = " · ".join(a.description_tr for a in plan.proposed_actions)
    return PLAN_LINE.format(protocol=plan.protocol_id or "(kayıtsız)",
                            actions=actions)
```

`escalate`'in `self.history.append({...})` bloğunda `Gerekçe:` satırından
sonra:

```python
                       f"Gerekçe: {risk.rationale_tr}\n"
                       f"{plan_line(plan)}\n{note}\n"
                       f"{UPDATE_INSTRUCTION if update else ESCALATION_INSTRUCTION}"})
```

- [ ] **Step 4: Süpervizörün diğer iki çağrı yerini bağla**

`_apply_correction` — düzeltme sonrası yeni değerlendirme yeni plan doğurur:

```python
        refreshed = self._episode(episode.id)
        risk = assess_risk(self.gw, self.store, refreshed)
        plan_actions(self.gw, self.store, refreshed, risk)
        return {"state": "recorded", "new_summary": refreshed.summary_tr,
                "new_risk": risk.level}
```

`_internal_tool`'un `REQUEST_RISK_ASSESSMENT` dalı:

```python
            assessment = assess_risk(self.gw, self.store, episode)
            plan = plan_actions(self.gw, self.store, episode, assessment)
            return {**assessment.model_dump(),
                    "plan": plan.model_dump()}
```

- [ ] **Step 5: `run.py`'yi bağla**

`gozcu/run.py` — import ve üç çağrı yeri (`:219`, `:293`, `:297`
civarındaki `assess_risk(gw, store, episode)` satırları):

```python
from gozcu.agents.action_planner import plan_actions
```

Her `assessment = assess_risk(gw, store, episode)` satırının hemen altına:

```python
    plan_actions(gw, store, episode, assessment)
```

> Çağrılar bugün dönüş değerini atmıyor (`assess_risk(gw, store, episode)`);
> `assessment = ` ile yakalayıp planlayıcıya vermek gerekiyor.
>
> **Bu, mevcut test ikizlerini kırar.** `tests/test_run.py`'deki
> `_fake_assess_that_escalates` depoya yazıp `None` döndürüyor; dönüş değeri
> artık kullanıldığı için o ikiz `plan_actions(..., None)` üretir. Step 1'deki
> `_fake_assess_returning` onun yerine geçer ve `_fake_assess_that_escalates`
> kullanan üç test (`test_a_stale_early_assessment_is_reassessed_once_at_the_end`,
> `test_an_assessment_as_fresh_as_the_episodes_end_is_not_reassessed`,
> `test_an_episode_with_no_assessment_at_all_still_gets_one`) yeni ikize
> çevrilir. `assess_risk`'i `unittest.mock.patch` ile yamalayan
> `tests/test_supervisor.py` ve `tests/test_kpi.py` testleri de
> `plan_actions`'ı yamalamak zorunda — yamalanmazsa gerçek planlayıcı sahte
> ağ geçidine gider.

- [ ] **Step 6: Arayüzü yeni durakla güncelle**

`gozcu/ui/web/js/trace.js:48`:

```javascript
const CHAIN_STAGES = ["perception", "orchestrator", "interpreter",
                      "anomaly_analyst", "risk_analyst", "action_planner",
                      "supervisor"];
```

`gozcu/ui/feed.py:58` emoji eşlemesine: `"action_planner": "📋",`

- [ ] **Step 7: Testleri koş**

Run: `uv run pytest tests/test_supervisor.py tests/test_run.py -v`
Expected: PASS.

- [ ] **Step 8: Bütün testleri koş**

Run: `uv run pytest tests/ -v`
Expected: PASS. `assess_risk`'i yamalayan mevcut testler artık `plan_actions`'ı
da yamalamak zorunda — kırmızı kalan her test bu yüzdendir ve yamayı eklemek
doğru düzeltmedir (davranış gerçekten değişti).

- [ ] **Step 9: Commit**

```bash
git add gozcu/run.py gozcu/agents/supervisor.py gozcu/ui/web/js/trace.js gozcu/ui/feed.py tests/
git commit -m "feat(supervisor): plan yükseltme mesajına girsin

Nöbetçi proposed_actions'ı hiç okumuyordu — araç seçimini kendi
sezgisiyle yapıyordu. Plan mesaja girmeden planlayıcı dekoratif kalırdı
(spec §5). Trace paneli yeni durağı gösteriyor."
```

---

## Task 6: Risk analistini derecelendirmeye daralt

**Files:**
- Modify: `gozcu/models.py` — `RiskAssessment.proposed_actions` kaldır, `Detail.action_plans` ekle
- Modify: `gozcu/agents/risk.py` — `_RiskResponse`, `SYSTEM_PROMPT`, `assess_risk`
- Modify: `gozcu/report.py:186-190` — `actions` plandan türesin
- Modify: `gozcu/ui/feed.py:470-480` — besleme plandan okusun
- Test: `tests/test_risk.py`, `tests/test_report.py`, `tests/test_feed.py`

**Interfaces:**
- Consumes: Görev 4'ün `Store.action_plans()`.
- Produces: `RiskAssessment` artık `proposed_actions` taşımıyor;
  `Detail.action_plans: list[ActionPlan]`; `PipelineOutput.actions`
  `store.action_plans()` üzerinden türüyor.

- [ ] **Step 1: Başarısız testleri yaz**

`tests/test_risk.py` sonuna:

```python
def test_assessment_no_longer_carries_actions():
    """İki ajanın işi tek kayıtta durmamalı (spec §2d)."""
    import pytest
    from pydantic import ValidationError
    from gozcu.models import RiskAssessment
    with pytest.raises(ValidationError):
        RiskAssessment(episode_id=1, ts=1.0, level="Yüksek",
                       rationale_tr="x", preventable=True,
                       proposed_actions=[])


def test_risk_prompt_no_longer_lists_intervention_tools():
    """Katalog planlayıcıya taşındı; analistte kalırsa iki ajan aynı işi yapar."""
    from gozcu.agents.risk import SYSTEM_PROMPT
    assert "halt_production_line" not in SYSTEM_PROMPT
    assert "dispatch_medical" not in SYSTEM_PROMPT


def test_risk_levels_still_verbatim_in_prompt():
    """Daraltma sırasında enum/prompt eşleşmesine DOKUNULMAZ (CLAUDE.md)."""
    from typing import get_args
    from gozcu.agents.risk import SYSTEM_PROMPT
    from gozcu.models import RiskLevel
    for value in get_args(RiskLevel):
        assert f'"{value}"' in SYSTEM_PROMPT or value in SYSTEM_PROMPT
```

`tests/test_report.py` sonuna:

```python
def test_actions_derive_from_action_plans(store):
    """`actions` planlardan türer, değerlendirmelerden değil (spec §2f)."""
    from gozcu.models import ActionPlan, ProposedAction
    episode = _episode(store)
    plan = ActionPlan(episode_id=episode.id, risk_assessment_id=1, ts=5.0,
                      protocol_id="PRT-B-CARPMA", rationale_tr="gerekçe",
                      proposed_actions=[
                          ProposedAction(description_tr="B hattını durdur",
                                         tool_name="halt_production_line")],
                      plan_source="model")
    store.save_action_plan(plan)
    output = build_output(store, summary="özet", perception=None)
    assert "B hattını durdur" in output.actions
    assert output.detail.action_plans


def test_four_keys_survive_empty_plan(store):
    """Plan boşken bile dört anahtar üretilir (CLAUDE.md çıktı sözleşmesi)."""
    output = build_output(store, summary="özet", perception=None)
    assert output.summary and output.risk
    assert output.events == [] or output.events is not None
    assert output.actions == []
```

> `build_output` / `_episode` adları `tests/test_report.py`'deki mevcut
> yardımcılardan; imza uyuşmuyorsa oradaki desen kullanılır.

- [ ] **Step 2: Testleri koş, kırmızı olduğunu gör**

Run: `uv run pytest tests/test_risk.py -k "no_longer or verbatim" tests/test_report.py -k "action_plans or four_keys" -v`
Expected: FAIL — `RiskAssessment` hâlâ `proposed_actions` kabul ediyor;
`Detail.action_plans` yok.

- [ ] **Step 3: Sözleşmeyi daralt**

`gozcu/models.py` — `RiskAssessment`'tan alanı çıkar:

```python
class RiskAssessment(Base):
    id: int | None = None
    episode_id: int
    ts: float = 0.0
    level: RiskLevel
    rationale_tr: str = Field(max_length=800)
    preventable: bool
    # `proposed_actions` KALDIRILDI → `ActionPlan` (spec §3). Müdahale
    # önerisi ayrı bir ajanın işi ve ayrı bir kayıtta durur.
```

`Detail`'e yeni alan:

```python
class Detail(Base):
    episodes: list[Episode] = Field(default_factory=list)
    risk_assessments: list[RiskAssessment] = Field(default_factory=list)
    action_plans: list[ActionPlan] = Field(default_factory=list)
    handoff_chain: list[Handoff] = Field(default_factory=list)
    action_ledger: list[ActionRecord] = Field(default_factory=list)
    root_cause_report: dict | None = None
```

- [ ] **Step 4: Analisti daralt**

`gozcu/agents/risk.py`:

1. `_RiskResponse`'tan `proposed_actions` alanını sil.
2. `SYSTEM_PROMPT`'tan araç kataloğu bölümünü sil — "Her aksiyon önerisini
   SADECE aşağıdaki araçlardan birine bağla … {tools}" paragrafı ve
   `.format(tools=TOOL_CATALOGUE)` çağrısı. **Okuma araçları kalır:** "ÖNCE
   ARAŞTIR" paragrafı ve `READ_TOOL_SCHEMAS` dokunulmuyor; analist ciddiyeti
   biçmek için bakım gecikmesini bilmeye devam ediyor.
3. `_fallback` ve `_read_assessment`'tan `proposed_actions` referanslarını sil.
4. `assess_risk` sonunda:

```python
    parsed = _read_assessment(response, episode)

    assessment = RiskAssessment(
        episode_id=episode.id, ts=now, level=parsed.level,
        rationale_tr=parsed.rationale_tr, preventable=parsed.preventable)
    assessment.id = store.save_risk(assessment)
```

`store.save_handoff(... "risk_analyst" → "supervisor" ...)` satırı **silinir**:
zincirdeki bir sonraki durak artık planlayıcı ve o deviri `action_planner._save`
yazıyor. İkisi birden kalırsa trace paneli aynı andan iki kenar çizer.

`_sanitize_action` ve `MAX_ACTION_DESCRIPTION` da silinir — ikizleri
`action_planner.py`'de yaşıyor.

- [ ] **Step 5: Okuyucuları plana çevir**

`gozcu/report.py:186-190`:

```python
    actions: list[str] = []
    for plan in store.action_plans():
        for action in plan.proposed_actions:
            if action.tool_name in TOOLS and action.description_tr not in actions:
                actions.append(action.description_tr)
```

ve `Detail(...)` çağrısına `action_plans=store.action_plans(),` eklenir.

`gozcu/ui/feed.py:470-480` — risk satırı artık öneri saymıyor; öneriler kendi
besleme satırını hak ediyor:

```python
        elif entry.source == "risk":
            risk = risks.get(entry.row_id)
            if risk:
                episode = episodes.get(risk.episode_id)
                made = FeedEntry(
                    seq=entry.seq,
                    ts=risk.ts or (episode.event_ts if episode else 0.0),
                    agent="risk_analyst", kind="risk",
                    title=risk.rationale_tr, detail="", risk=risk.level)

        elif entry.source == "action_plan":
            plan = plans.get(entry.row_id)
            if plan:
                proposed = " · ".join(a.description_tr
                                      for a in plan.proposed_actions)
                made = FeedEntry(
                    seq=entry.seq, ts=plan.ts,
                    agent="action_planner", kind="plan",
                    title=(f"prosedür: {plan.protocol_id}"
                           if plan.protocol_id else "tanımlı prosedür yok"),
                    detail=f"öneri: {proposed}" if proposed else "")
```

`plans` sözlüğü, `risks` sözlüğünün kurulduğu yerde
`{p.id: p for p in store.action_plans()}` ile kurulur.

- [ ] **Step 6: Testleri koş**

Run: `uv run pytest tests/test_risk.py tests/test_report.py tests/test_feed.py -v`
Expected: PASS.

- [ ] **Step 7: `test_risk.py`'nin öneri iddialarını taşı**

`tests/test_risk.py` içinde `proposed_actions`'a bakan sekiz iddia
(`:84-91`, `:99`, `:283-291`, `:330`) `tests/test_action_planner.py`'ye
taşınır. **Daraltılmadan** — kaybolan iddia, kaybolan davranıştır. Karşılığı
olmayan bir iddia varsa yeni bir test olarak yazılır.

- [ ] **Step 8: Bütün testleri koş**

Run: `uv run pytest tests/ -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor(risk): analist yalnız derecelendirsin

proposed_actions ActionPlan'e taşındı; araç kataloğu prompt'tan çıktı.
Okuma araçları kalıyor — ciddiyeti biçmek için bakım gecikmesi gerekli.
actions anahtarı artık planlardan türüyor (spec §3)."
```

---

## Task 7: Kök neden raporu protokolü ansın

**Files:**
- Modify: `gozcu/agents/reporter.py` — `_prompt`, `RootCauseReport`
- Test: `tests/test_reporter.py`

**Interfaces:**
- Consumes: Görev 4'ün `Store.action_plans()`, `ActionPlan.protocol_id`.
- Produces: Kök neden raporu prompt'u planları ve uygulanan prosedürü sayıyor.

- [ ] **Step 1: Başarısız testi yaz**

`tests/test_reporter.py` sonuna:

```python
def test_report_prompt_cites_the_protocol(store):
    """'Önlenebilirdi' iddiası bir prosedüre dayanmalı (spec §2a)."""
    from gozcu.agents.reporter import _prompt
    from gozcu.models import ActionPlan, ProposedAction

    episode = _episode(store)
    plan = ActionPlan(episode_id=episode.id, risk_assessment_id=1, ts=5.0,
                      protocol_id="PRT-B-CARPMA",
                      rationale_tr="B-Hattı çarpma prosedürü geçerli.",
                      proposed_actions=[
                          ProposedAction(description_tr="B hattını durdur",
                                         tool_name="halt_production_line")],
                      plan_source="model")
    store.save_action_plan(plan)

    text = _prompt(store)
    assert "PRT-B-CARPMA" in text
    assert "B hattını durdur" in text


def test_report_prompt_survives_empty_plan(store):
    """Plan yokken rapor yine üretilebilmeli."""
    from gozcu.agents.reporter import _prompt
    assert _prompt(store)
```

- [ ] **Step 2: Testleri koş, kırmızı olduğunu gör**

Run: `uv run pytest tests/test_reporter.py -k protocol -v`
Expected: FAIL — `assert "PRT-B-CARPMA" in text` başarısız; rapor planları
bilmiyor.

- [ ] **Step 3: Raporu planla besle**

`gozcu/agents/reporter.py`, `_prompt` içinde — mevcut `_section` deseniyle:

```python
def _plan_line(plan) -> str:
    """Bir planın rapor satırı.

    `plan_source` DAHİL: deterministik bir yedeği modelin kararı gibi
    anlatmak, raporun en çok güvenilmesi gereken cümlesini yalan yapar.
    """
    protocol = plan.protocol_id or "(tanımlı prosedür yok)"
    actions = " · ".join(a.description_tr for a in plan.proposed_actions)
    source = {"model": "plan katmanı kurdu",
              "protocol_fallback": "prosedür adımları doğrudan uygulandı",
              "empty": "öneri üretilmedi"}[plan.plan_source]
    return f"- {mmss(plan.ts)} {protocol} ({source}): {actions or '—'}"
```

`_prompt` gövdesine, risk bölümünün ardına:

```python
    plans = store.action_plans()
    lines += _section("UYGULANAN PROSEDÜRLER",
                      [_plan_line(p) for p in plans]
                      or ["- (prosedür kaydı yok)"])
```

Sistem prompt'una bir cümle — "önlenebilirdi" iddiasının dayanağını
zorunlu kılar:

```
Bir olayın önlenebilir olduğunu söylüyorsan, UYGULANAN PROSEDÜRLER
bölümündeki prosedür kimliğini anarak söyle. Prosedür kaydı yoksa
"önlenebilirdi" deme; hangi prosedürün eksik olduğunu yaz.
```

- [ ] **Step 4: Testleri koş**

Run: `uv run pytest tests/test_reporter.py -v`
Expected: PASS.

- [ ] **Step 5: Bütün testleri koş**

Run: `uv run pytest tests/ -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add gozcu/agents/reporter.py tests/test_reporter.py
git commit -m "feat(reporter): kök neden raporu prosedürü ansın

'Önlenebilirdi' modelin kanaati olmaktan çıkıp 'PRT-X vardı ve
uygulanmadı' tespitine dönüşüyor. plan_source rapora giriyor:
deterministik bir yedeği modelin kararı gibi anlatmak, raporun en çok
güvenilmesi gereken cümlesini yalan yapardı (spec §2a)."
```

---

## Task 8: Belgeleme ve arayüz etiketleri

**Files:**
- Modify: `gozcu/ui/view.py:342-346` — Türkçe kova etiketleri
- Modify: `docs/05-decisions/decision-log.md`
- Modify: `docs/tasks/README.md`
- Modify: `docs/superpowers/specs/2026-08-22-agentic-gozcu-design.md` — üstyazı bandı
- Modify: `CLAUDE.md` — ajan kadrosu satırı

- [ ] **Step 1: Kova etiketlerini yeni rol adlarına çevir**

`gozcu/ui/view.py:342` — **anahtarlar değişmiyor** (Görev 1/Step 6),
yalnız Türkçe etiketler:

```python
DECISION_BUCKET_LABELS: dict[str, str] = {
    "closed_at_router": "orkestratörde kapandı",
    "to_interpreter": "yorumcuya gitti",
    "to_synthesizer": "anomali analistine gitti",
    "escalated": "yükseltildi",
    "degraded": "kesinti (bozulmuş)",
}
```

- [ ] **Step 2: Karar günlüğüne yaz**

`docs/05-decisions/decision-log.md` sonuna, spec §0b'deki beş kararı
gerekçeleriyle ekle: (1) ajan = model çalıştıran aktör, (2) "tamamen yerel"
ifadesinin düzeltilmesi, (3) A2 protokol seçici, (4) yeniden adlandırmanın
kodda yapılması, (5) hızın sonraya bırakılması. Her karara ölçüyü ya da
gerekçeyi yaz — "böyle karar verildi" tek başına kayıt değildir.

- [ ] **Step 3: Görev tablosunu güncelle**

`docs/tasks/README.md` — görev listesine yeni satır:

```markdown
| [22](22-mikro-ajan-yeniden-tasarimi.md) | Mikro-ajan yeniden tasarımı (Karar & Aksiyon ajanı) | 17, 21 | ✅ 27 Ağu |
```

ve **Durum** bölümündeki "Bütün özellik görevleri bitti" cümlesini düzelt.

- [ ] **Step 4: Eski spec'e üstyazı bandı koy**

`docs/superpowers/specs/2026-08-22-agentic-gozcu-design.md`, §3 "Components"
başlığının hemen altına:

```markdown
> **ÜSTYAZILDI (27 Ağustos).** Ajan kadrosu ve adlar
> [2026-08-27-mikro-ajan-yeniden-tasarimi-design.md](2026-08-27-mikro-ajan-yeniden-tasarimi-design.md)
> ile değişti: `router → orchestrator`, `synthesizer → anomaly_analyst`,
> zincire `action_planner` eklendi ve risk analisti derecelendirmeye
> daraldı. Çelişkide yeni doküman geçerlidir.
```

- [ ] **Step 5: `CLAUDE.md`'ye kadro satırı ekle**

"Değişmez kurallar" bölümüne:

```markdown
- **Ajan kadrosu sekiz değil, altı ajan + iki alt sistem.** Mock araç kaydı
  ve benchmark modülü ajan DEĞİL — model çalıştırmıyorlar. Kadro:
  `orchestrator` · `interpreter` · `anomaly_analyst` · `risk_analyst` ·
  `action_planner` · `supervisor` (+ `reporter`, `guard`). Ayrıntı:
  [yeniden tasarım spec'i](docs/superpowers/specs/2026-08-27-mikro-ajan-yeniden-tasarimi-design.md).
```

- [ ] **Step 6: Bütün testleri koş**

Run: `uv run pytest tests/ -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "docs: mikro-ajan yeniden tasarımının kaydı

Karar günlüğü, görev tablosu, eski spec'e üstyazı bandı ve CLAUDE.md'ye
kadro satırı. Arayüzün Türkçe kova etiketleri yeni rol adlarını
kullanıyor; kova ANAHTARLARI kasıtlı olarak eski (KPI temeli)."
```

---

## Kapsam dışı (bu planda YOK)

- **Uzun Süreli Hafıza ajanı (PDF #2).** `memory.py` başka bir oturumda
  yeniden yazılıyor; ayrı bir turda ele alınacak.
- **Mock ve Benchmark'ın ajanlaştırılması.** Spec §0b/1.
- **A3 — düşük riskte özerk yürütme.** Spec §6.
- **`supervisor` yeniden adlandırması.** Spec §4.
- **Gecikme optimizasyonu.** Spec §8/R1 — ölçülür, bu turda çözülmez.
- **PDF dosyasının kendisinin düzeltilmesi** (offline ifadesi, askerler
  örneği, sekiz-ajan çerçevesi). Kod deposunun dışında bir iş.
