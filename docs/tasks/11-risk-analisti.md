# Görev 11 — Risk analisti (`gozcu/agents/risk.py`)

**Sahip:** `uvyscengiz` · **Gün:** 25 Ağustos · **Süre:** ~2 saat
**Bağımlılık:** [08](08-hafiza.md), [10](10-saha-araclari.md)

## Bağlam

Olayı alıp riski biçen, gerekçesini yazan ve **ne yapılması gerektiğini söyleyen**
uzman. İki tasarım kuralı belirleyici:

**Her aday aksiyon gerçek bir araca bağlanmak zorunda.** Sistemin
çalıştıramayacağı bir öneri sadece bir cümledir — ve cümleler tam olarak saha
araçlarının var olma sebebini boşa çıkarır. Model olmayan bir araç adı
uydurursa o öneri **sessizce düşürülür**, Nöbetçi'ye hiç ulaşmaz.

**Kesin hüküm vermez.** Kamera verisine dayanan bir sistem, bir kazanın sebebine
hükmedemez; kalibre edilmiş bir tahmin verir. Prompt bunu zorluyor, rapor da
(Görev 12) aynı çizgiyi sürdürüyor.

Analiz, karar vermeden önce **arşive bakıyor** — bu ekipmanın geçmişi var mı,
benzer bir olay olmuş mu. Hafıza katmanının mimari süs değil, muhakemenin
girdisi olduğu yer burası.

## Kurulum

```bash
uv sync --extra dev
uv run pytest tests/test_memory.py tests/test_tools.py -v
```

## Bağımlı olduğun imzalar

```python
# gozcu/memory.py
search_timeline(gw, store, query: str, top_k: int = 5) -> list[Episode]

# gozcu/tools/registry.py
TOOLS: dict[str, Callable]        # geçerli araç adlarının kaynağı

# gozcu/gateway.py
Gateway.ask(tier, messages, schema=None, tools=None) -> Response

# gozcu/store.py
Store.save_risk(r: RiskAssessment) -> int
Store.corrections(episode_id: int) -> list[Correction]
Store.save_handoff(d: Handoff) -> int

# gozcu/models.py
ProposedAction(description_tr, tool_name, params)
RiskAssessment(id, episode_id, level, rationale_tr, preventable, proposed_actions)
```

> **Doğrulamadan önce temizle (Görev 06).** Şema sertleştirmesi artık
> `Gateway.ask()`'in içinde ve `maxLength` tele hiç çıkmıyor — yani model
> 800 karakterden uzun bir `rationale_tr` döndürebilir. `_RiskResponse(**...)`
> onu doğrudan doğrularsa `ValidationError` atar ve **gerçek bir risk analizi
> geri düşüş kabuğuna çöker**. `rationale_tr`'yi doğrulamadan önce 800'e kes.
> Aynı şey `ProposedAction.description_tr` (200) için de geçerli.

**Bozulmuş yanıt guard'ı (Görev 03).** `gw.ask()` kesintide istisna atmıyor;
`content=""`, `tool_calls=[]` olan `degraded=True` bir `Response` dönüyor.
Bozulmuş yanıt hiçbir şeye ayrışmaz — hem JSON ayrıştırma hem de
`tool_calls[0]` erişimi korunmalı. `except GatewayError` bunu yakalamaz.

## Ne yapacaksın

```python
assess_risk(gw, store, episode: Episode) -> RiskAssessment
```

**Şema notu:** modele `RiskAssessment`'yi doğrudan verme — `id` ve
`episode_id` alanları var ve katı şema modunda modeli bunları uydurmaya zorlar.
Ayrı bir `_RiskResponse` yanıt modeli tanımla.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_risk.py`

```python
from unittest.mock import Mock, patch

from gozcu.agents.risk import assess_risk
from gozcu.gateway import Response
from gozcu.models import Correction, Episode
from gozcu.store import Store

RESPONSE_JSON = ('{"level":"Kritik","rationale_tr":"Yerde hareketsiz kişi var ve '
         'aracın fren bakımı gecikmiş.","preventable":true,'
         '"proposed_actions":[{"description_tr":"Sağlık ekibini çağır",'
         '"tool_name":"dispatch_medical",'
         '"params":{"location":"B-Hattı","urgency":"critical"}}]}')


def _ep(store):
    e = Episode(start_ts=0.0, phase="development", summary_tr="araç devrildi",
               preliminary_risk="Yüksek")
    e.id = store.create_episode(e)
    return e


def _gw(content=RESPONSE_JSON, **kw):
    gw = Mock(); gw.ask.return_value = Response(content=content, **kw)
    return gw


def test_candidate_actions_map_to_real_registered_tools():
    from gozcu.tools.registry import TOOLS
    store = Store(":memory:")
    with patch("gozcu.agents.risk.search_timeline", return_value=[]):
        r = assess_risk(_gw(), store, _ep(store))
    assert r.proposed_actions
    assert all(a.tool_name in TOOLS for a in r.proposed_actions)


def test_invented_tool_names_are_dropped_not_passed_through():
    bad = RESPONSE_JSON.replace("dispatch_medical", "helikopter_gonder")
    store = Store(":memory:")
    with patch("gozcu.agents.risk.search_timeline", return_value=[]):
        r = assess_risk(_gw(bad), store, _ep(store))
    assert r.proposed_actions == []


def test_analysis_consults_the_archive_before_deciding():
    store = Store(":memory:")
    with patch("gozcu.agents.risk.search_timeline",
               return_value=[]) as ara:
        assess_risk(_gw(), store, _ep(store))
    ara.assert_called_once()


def test_operator_corrections_reach_the_prompt():
    store = Store(":memory:")
    e = _ep(store)
    store.save_correction(Correction(ts=1.0, episode_id=e.id, field="event_type",
                                   old="araç devrildi", new="yük düştü",
                                   rationale="operatör gözlemi"))
    gw = _gw()
    with patch("gozcu.agents.risk.search_timeline", return_value=[]):
        assess_risk(gw, store, e)
    prompt_text = gw.ask.call_args.args[1][-1]["content"]
    assert "yük düştü" in prompt_text and "araç devrildi" in prompt_text


def test_assessment_is_persisted_with_a_handoff_to_the_supervisor():
    store = Store(":memory:")
    with patch("gozcu.agents.risk.search_timeline", return_value=[]):
        assess_risk(_gw(), store, _ep(store))
    assert len(store.risks()) == 1
    assert store.handoffs()[-1].target_agent == "supervisor"


def test_degraded_tier_keeps_the_preliminary_risk_instead_of_crashing():
    store = Store(":memory:")
    e = _ep(store)
    gw = Mock(); gw.ask.return_value = Response(degraded=True)
    with patch("gozcu.agents.risk.search_timeline", return_value=[]):
        r = assess_risk(gw, store, e)
    assert r.level == e.preliminary_risk and r.proposed_actions == []
```

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_risk.py -v
```
Beklenen: `ModuleNotFoundError`

### 3. `gozcu/agents/risk.py` yaz

```python
import json

from pydantic import BaseModel, ConfigDict, Field

from gozcu.memory import search_timeline
from gozcu.models import (ProposedAction, Handoff, Episode, RiskAssessment,
                          RiskLevel)
from gozcu.tools.registry import TOOLS

SYSTEM_PROMPT = """Sen bir savunma sanayi üretim tesisinin iş güvenliği uzmanısın.
Sana bir olay ve arşivden gelen benzer geçmiş olaylar verilir.

Görevin:
- Risk seviyesini belirle: Düşük, Orta, Yüksek, Kritik
- Gerekçeni Türkçe, kısa cümlelerle yaz. Kamera verisine dayan.
- KESİN HÜKÜM VERME. "olası", "muhtemelen", "görüntüye dayanarak" kullan.
- Önlenebilir olup olmadığını söyle
- Operatör düzeltmesi varsa DÜZELTİLMİŞ hâli esas al
- Her aksiyon önerisini SADECE şu araçlardan birine bağla:
{araclar}

Var olmayan bir araç adı uydurma. Sadece JSON döndür."""


class _RiskResponse(BaseModel):
    """Modelin döndürdüğü şekil. RiskDegerlendirme'den ayrı, çünkü onun
    id/epizot_id alanları var ve katı şema modunda model onları uydurmaya
    zorlanır."""
    model_config = ConfigDict(extra="forbid")
    level: RiskLevel
    rationale_tr: str = Field(max_length=800)
    preventable: bool
    proposed_actions: list[ProposedAction] = Field(default_factory=list)


def assess_risk(gw, store, episode: Episode) -> RiskAssessment:
    history = search_timeline(
        gw, store, f"{episode.summary_tr} {' '.join(episode.participants)}")
    history_text = "\n".join(f"- {e.summary_tr}" for e in history) or "- (kayıt yok)"

    corrections = store.corrections(episode.id) if episode.id else []
    correction_text = "\n".join(
        f"- OPERATÖR DÜZELTMESİ — {d.field}: '{d.old}' yerine '{d.new}'"
        for d in corrections)

    response = gw.ask("main", [
        {"role": "system",
         "content": SYSTEM_PROMPT.format(tools="\n".join(f"- {a}" for a in TOOLS))},
        {"role": "user",
         "content": f"OLAY: {episode.summary_tr}\nÖN RİSK: {episode.preliminary_risk}\n"
                    f"{correction_text}\n\nARŞİV:\n{history_text}"},
    ], schema=_RiskResponse)

    if response.degraded:
        parsed = _RiskResponse(level=episode.preliminary_risk,
                            rationale_tr="Risk analiz katmanı yanıt vermiyor; "
                                       "ön risk korundu.",
                            preventable=False)
    else:
        try:
            parsed = _RiskResponse(**json.loads(response.content))
        except Exception:  # noqa: BLE001
            parsed = _RiskResponse(level=episode.preliminary_risk,
                                rationale_tr="Risk analizi üretilemedi; "
                                           "ön risk korundu.",
                                preventable=False)

    # Uydurulmuş araç adları düşürülür, süpervizöre asla iletilmez.
    actions = [a for a in parsed.proposed_actions if a.tool_name in TOOLS]

    degerlendirme = RiskAssessment(
        episode_id=episode.id, level=parsed.level,
        rationale_tr=parsed.rationale_tr, preventable=parsed.preventable,
        proposed_actions=actions)
    degerlendirme.id = store.save_risk(degerlendirme)

    store.save_handoff(Handoff(ts=episode.start_ts,
                             source_agent="risk_analyst", target_agent="supervisor",
                             reason=f"risk: {parsed.level}", confidence=0.85,
                             payload_ref=f"risk:{degerlendirme.id}"))
    return degerlendirme
```

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_risk.py -v
```
Beklenen: 6 passed

### 5. Commit

```bash
git add gozcu/agents/risk.py tests/test_risk.py
git commit -m "feat: risk analyst grounding every recommendation in a real tool"
```

## Doğrulama

```bash
uv run pytest tests/test_risk.py -v
```
Beklenen: **6 passed**
