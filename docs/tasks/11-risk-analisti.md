# Görev 11 — Risk analisti (`gozcu/agents/risk.py`)

> ## ✅ TAMAMLANDI — 23 Ağustos 2026, `dd803fd`
>
> **Risk analisti indi.** `gozcu/agents/risk.py` var; `tests/test_risk.py` 17
> test ile yeşil. Bu dosyayı yeniden uygulama — aşağısı ne yapıldığının kaydı.
>
> **Sonraki göreve başlarken bilmen gerekenler**
> ([kararlar](#tamamlanma-notları-gelecek-görevleri-bağlayan) bölümüne bak):
> **analist artık gerçek bir okuma aracı çağırıyor** — tek model çağrısı değil,
> iki turlu bir araştırma (araçlar sunulur, çağırdıkları `call_tool` üzerinden
> çalıştırılır, sonuçlarla nihai değerlendirme istenir); **yalnızca
> `READ_TOOLS`** — müdahale araçları ne sunuluyor ne yürütülüyor, yalnızca
> `proposed_actions` olarak Görev 14'e öneriliyor; ve **kesme doğrulamadan
> önce** yapılıyor, iç içe `proposed_actions[*].description_tr` dâhil.

**Sahip:** `uvyscengiz` · **Gün:** 25 Ağustos · **Süre:** ~2 saat
**Bağımlılık:** [08](08-hafiza.md), [10](10-saha-araclari.md)

## Bağlam

Olayı alıp riski biçen, gerekçesini yazan ve **ne yapılması gerektiğini söyleyen**
uzman. Üç tasarım kuralı belirleyici:

**Analist gerçekten araştırıyor.** Tek bir model çağrısı, arşiv metninden
kapılan belirsiz bir cümleden fazlasını üretemez: "fren bakımı dört ay
gecikmiş" hiçbir fikstür dosyasında **yazmıyor**, [Görev 09](09-tesis-dunyasi.md)'un
`overdue_maintenance_months` fonksiyonu onu tarihlerden hesaplıyor ve o sayıya
yalnız `query_equipment_history` çağrılırsa ulaşılır. Bu yüzden burada gerçek
bir araç turu var: modele okuma araçları sunuluyor, çağırdıkları çalıştırılıyor,
sonuçlar geri veriliyor ve nihai değerlendirme ikinci turda çıkıyor.

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
search_timeline(gw, store, query: str, top_k: int = 5,
                exclude_id: int | None = None) -> list[Episode]

# gozcu/tools/registry.py
TOOLS: dict[str, Callable]        # geçerli araç adlarının kaynağı
TOOL_SCHEMAS: list[dict]          # OpenAI biçimli araç şemaları
call_tool(store, tool_name: str, params: dict, actor: str = "agent",
          approval: str | None = None, ts: float = 0.0) -> dict

# gozcu/agents/interpreter.py
_sanitize_text(text: str, max_length: int) -> str

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

> **`exclude_id` ZORUNLU (Görev 08).** Sorgu `episode.summary_tr` ile
> atılıyor — yani tam olarak gömülmüş metinle. `exclude_id=episode.id`
> geçilmezse epizot kendi kosinüs eşleşmesini bulur ve arşiv panelinde **kendi
> emsali olarak** en üstte görünür; sahnede görünen bir hata.

> **Doğrulamadan önce temizle (Görev 06).** Şema sertleştirmesi artık
> `Gateway.ask()`'in içinde ve `maxLength` tele hiç çıkmıyor — yani model
> 800 karakterden uzun bir `rationale_tr` döndürebilir. `_RiskResponse(**...)`
> onu doğrudan doğrularsa `ValidationError` atar ve **gerçek bir risk analizi
> geri düşüş kabuğuna çöker**. `rationale_tr`'yi doğrulamadan önce 800'e kes.
> Aynı şey `ProposedAction.description_tr` (200) için de geçerli.

> **Görev 10 indi (`198801e`) — iki sözlük birebir aynı olmak zorunda.**
> `TOOLS` bir **izin listesi**: `ProposedAction.tool_name` şu yedi İngilizce
> addan biri değilse öneri sessizce düşürülür ve Nöbetçi'ye hiç ulaşmaz —
> `radio_call`, `dispatch_medical`, `site_alarm`, `open_safety_incident`,
> `halt_production_line`, `query_shift_personnel`, `query_equipment_history`.
> Aynısı `dispatch_medical`'in `urgency` parametresi için geçerli: şema bunu
> `enum` olarak **tam olarak `"normal"` ve `"critical"`** bildiriyor (tek
> kaynak `field_systems.URGENCY_LEVELS`). Promptun bu değerleri **birebir**
> yazması gerekiyor. Enum dışı bir değer atılmıyor ama güvenli tarafa,
> `critical`'a yükseltilip `unrecognised_urgency` ile deftere düşüyor — yani
> "kritik" yazmak sessizce yavaş dalı seçmiyor, sadece deftere gürültü
> bırakıyor. Prompt kataloğu bu yüzden elle yazılmıyor, `TOOL_SCHEMAS`'tan
> türetiliyor.

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
"""Görev 11 — risk analisti.

Analistin iki iddiası test ediliyor: **gerçekten araştırıyor** (okuma
araçlarını aksiyon defteri üzerinden çağırıyor) ve **her önerisi gerçek bir
araca bağlı**. İkisi de sahte bir cümleyle taklit edilebilir; testler o yüzden
defterin ve modele giden mesajların içine bakıyor.
"""

import json
from unittest.mock import Mock, patch

from gozcu.agents.risk import (DEGRADED_RATIONALE, MAX_ACTION_DESCRIPTION,
                               MAX_RATIONALE, READ_TOOLS, TOOL_CATALOGUE,
                               assess_risk)
from gozcu.gateway import Response
from gozcu.models import Correction, Episode
from gozcu.store import Store
from gozcu.tools import field_systems
from gozcu.tools.registry import TOOLS

RESPONSE_JSON = ('{"level":"Kritik","rationale_tr":"Yerde hareketsiz kişi var ve '
                 'aracın fren bakımı gecikmiş.","preventable":true,'
                 '"proposed_actions":[{"description_tr":"Sağlık ekibini çağır",'
                 '"tool_name":"dispatch_medical",'
                 '"params":{"location":"B-Hattı","urgency":"critical"}}]}')

EPISODE_TS = 192.5


def _ep(store, participants=("IST-04", "PRS-001")):
    e = Episode(start_ts=EPISODE_TS, end_ts=EPISODE_TS + 20, phase="development",
                summary_tr="araç devrildi", participants=list(participants),
                preliminary_risk="Yüksek")
    e.id = store.create_episode(e)
    return e


def _gw(content=RESPONSE_JSON, **kw):
    gw = Mock()
    gw.ask.return_value = Response(content=content, **kw)
    return gw


def _tool_call(name, **params):
    return {"id": f"call_{name}", "type": "function",
            "function": {"name": name, "arguments": json.dumps(params)}}


def _investigating_gw(*calls, final=RESPONSE_JSON):
    """İlk yanıt araç çağırır, ikincisi nihai değerlendirmeyi verir."""
    gw = Mock()
    gw.ask.side_effect = [Response(tool_calls=list(calls)),
                          Response(content=final)]
    return gw


def _messages(gw, index=-1):
    return gw.ask.call_args_list[index].args[1]


def _text(gw, index=-1):
    return "\n".join(str(m.get("content")) for m in _messages(gw, index))


def _archive_patch(episodes=()):
    return patch("gozcu.agents.risk.search_timeline", return_value=list(episodes))


# -- öneriler gerçek araçlara bağlı -----------------------------------------

def test_only_actions_bound_to_registered_tools_reach_the_supervisor():
    """Süzgeç silinirse uydurma araç da geçer — o yüzden liste karışık."""
    invented = json.loads(RESPONSE_JSON)
    invented["proposed_actions"].append(
        {"description_tr": "Helikopter gönder", "tool_name": "send_helicopter",
         "params": {}})
    store = Store(":memory:")
    with _archive_patch():
        r = assess_risk(_gw(json.dumps(invented)), store, _ep(store))
    assert [a.tool_name for a in r.proposed_actions] == ["dispatch_medical"]
    assert all(a.tool_name in TOOLS for a in r.proposed_actions)


def test_invented_tool_names_are_dropped_not_passed_through():
    bad = RESPONSE_JSON.replace("dispatch_medical", "send_helicopter")
    store = Store(":memory:")
    with _archive_patch():
        r = assess_risk(_gw(bad), store, _ep(store))
    assert r.proposed_actions == []


# -- arşiv --------------------------------------------------------------------

def test_analysis_consults_the_archive_and_excludes_the_episode_itself():
    """`exclude_id` düşerse epizot kendi emsali olarak listenin başına çıkar
    (Görev 08). Arşiv metni de gerçekten modele gitmeli."""
    store = Store(":memory:")
    e = _ep(store)
    prior = Episode(start_ts=0.0, phase="outcome",
                    summary_tr="12 Ağustos gecesi aynı istif aracının freni tuttu",
                    preliminary_risk="Orta")
    gw = _gw()
    with _archive_patch([prior]) as search:
        assess_risk(gw, store, e)
    search.assert_called_once()
    assert search.call_args.kwargs["exclude_id"] == e.id
    assert prior.summary_tr in _text(gw)


# -- araştırma: okuma araçları ------------------------------------------------

def test_the_analyst_is_offered_read_tools_only():
    """Analiz bir yan etkiyle hat durduramaz; müdahale Görev 14'ün onay
    akışına ait."""
    store = Store(":memory:")
    gw = _gw()
    with _archive_patch():
        assess_risk(gw, store, _ep(store))
    offered = {s["function"]["name"]
               for s in gw.ask.call_args_list[0].kwargs["tools"]}
    assert offered == set(READ_TOOLS)
    assert "halt_production_line" not in offered
    assert "dispatch_medical" not in offered


def test_the_analyst_reaches_the_overdue_maintenance_figure_through_the_ledger():
    """Dört aylık gecikme hiçbir arşiv cümlesinde yazmıyor —
    `query_equipment_history` çağrılmadan ulaşılamaz."""
    store = Store(":memory:")
    e = _ep(store)
    gw = _investigating_gw(_tool_call("query_equipment_history",
                                      equipment_id="IST-04"))
    with _archive_patch():
        r = assess_risk(gw, store, e)
    record = next(a for a in store.actions()
                  if a.tool_name == "query_equipment_history")
    assert record.result["overdue_maintenance_months"] == 4
    assert record.ts == e.start_ts == EPISODE_TS
    assert record.actor == "agent" and record.approval == "not_required"
    assert "overdue_maintenance_months" in _text(gw)
    assert gw.ask.call_count == 2
    assert r.level == "Kritik"


def test_the_equipment_id_comes_from_the_episode_participants():
    """Model kimliği tahmin etmiyor: epizodun taşıdığı kararlı kimlikler
    modele veriliyor."""
    store = Store(":memory:")
    gw = _gw()
    with _archive_patch():
        assess_risk(gw, store, _ep(store))
    assert "IST-04" in _text(gw) and "PRS-001" in _text(gw)


def test_a_write_tool_call_is_refused_and_never_reaches_the_ledger():
    store = Store(":memory:")
    gw = _investigating_gw(_tool_call("halt_production_line", line_id="B-Hattı",
                                      rationale="devrilme"))
    with _archive_patch():
        r = assess_risk(gw, store, _ep(store))
    assert [a.tool_name for a in store.actions()] == []
    assert "refused" in _text(gw)
    assert r.level == "Kritik"


def test_an_unknown_tool_name_is_refused_instead_of_raising():
    store = Store(":memory:")
    gw = _investigating_gw(_tool_call("send_helicopter"))
    with _archive_patch():
        r = assess_risk(gw, store, _ep(store))
    assert store.actions() == []
    assert r.level == "Kritik"


def test_a_model_that_calls_nothing_still_gets_one_assessment():
    """Araç fazı isteğe bağlı — çağrı yoksa ikinci tur hiç yapılmaz."""
    store = Store(":memory:")
    gw = _gw()
    with _archive_patch():
        r = assess_risk(gw, store, _ep(store))
    assert gw.ask.call_count == 1
    assert r.level == "Kritik"


# -- şema ile promptun tek sözlüğü -------------------------------------------

def test_the_urgency_vocabulary_reaches_the_model_byte_identically():
    """`URGENCY_LEVELS` prompta şemadan türetilerek giriyor; Türkçe bir
    aciliyet değeri `unrecognised_urgency` ile deftere gürültü bırakırdı."""
    store = Store(":memory:")
    gw = _gw()
    with _archive_patch():
        assess_risk(gw, store, _ep(store))
    system_text = _messages(gw)[0]["content"]
    for value in field_systems.URGENCY_LEVELS:
        assert f'"{value}"' in system_text
    assert '"kritik"' not in system_text  # check-tasks: allow-tr
    assert '"acil"' not in system_text  # check-tasks: allow-tr


def test_the_prompt_catalogue_names_every_registered_tool():
    for name in TOOLS:
        assert name in TOOL_CATALOGUE


# -- doğrulamadan önce temizleme ---------------------------------------------

def test_an_overlong_rationale_is_truncated_not_collapsed_into_the_fallback():
    """`maxLength` tele çıkmıyor (Görev 06); ham doğrulama gerçek bir analizi
    kabuğa çevirirdi."""
    payload = json.loads(RESPONSE_JSON)
    payload["rationale_tr"] = "Gerekçe cümlesi. " * 120
    store = Store(":memory:")
    with _archive_patch():
        r = assess_risk(_gw(json.dumps(payload)), store, _ep(store))
    assert len(r.rationale_tr) <= MAX_RATIONALE
    assert r.rationale_tr.startswith("Gerekçe cümlesi.")
    assert r.level == "Kritik"


def test_an_overlong_action_description_is_truncated_too():
    """Kesme iç içe `proposed_actions` içinde de yürümeli; yürümezse tek uzun
    öneri bütün değerlendirmeyi düşürür."""
    payload = json.loads(RESPONSE_JSON)
    payload["proposed_actions"][0]["description_tr"] = "Sağlık ekibini çağır. " * 30
    store = Store(":memory:")
    with _archive_patch():
        r = assess_risk(_gw(json.dumps(payload)), store, _ep(store))
    assert r.proposed_actions, "uzun açıklama öneriyi düşürmemeli"
    assert len(r.proposed_actions[0].description_tr) <= MAX_ACTION_DESCRIPTION
    assert r.level == "Kritik"


# -- operatör düzeltmesi, kalıcılık, bozulma ---------------------------------

def test_operator_corrections_reach_the_prompt():
    store = Store(":memory:")
    e = _ep(store)
    store.save_correction(Correction(ts=1.0, episode_id=e.id, field="event_type",
                                     old="araç devrildi", new="yük düştü",
                                     rationale="operatör gözlemi"))
    gw = _gw()
    with _archive_patch():
        assess_risk(gw, store, e)
    prompt_text = _messages(gw)[-1]["content"]
    assert "yük düştü" in prompt_text and "araç devrildi" in prompt_text


def test_assessment_is_persisted_with_a_handoff_to_the_supervisor():
    store = Store(":memory:")
    with _archive_patch():
        assess_risk(_gw(), store, _ep(store))
    assert len(store.risks()) == 1
    assert store.handoffs()[-1].target_agent == "supervisor"
    assert store.handoffs()[-1].source_agent == "risk_analyst"


def test_degraded_tier_keeps_the_preliminary_risk_instead_of_crashing():
    """Bozulmuş yanıt bir gün geçerli bir gövde taşırsa (bayat önbellek) o
    gövde canlı analiz gibi kaydedilmemeli — `degraded` guard'ı bu yüzden
    açık, `json.loads("")`'ın tesadüfen patlamasına güvenilmiyor."""
    store = Store(":memory:")
    e = _ep(store)
    gw = Mock()
    gw.ask.return_value = Response(content=RESPONSE_JSON, degraded=True)
    with _archive_patch():
        r = assess_risk(gw, store, e)
    assert r.level == e.preliminary_risk
    assert r.proposed_actions == []
    assert r.rationale_tr == DEGRADED_RATIONALE
    assert store.risks()[-1].rationale_tr == DEGRADED_RATIONALE


def test_unreadable_content_is_distinguishable_from_a_dead_tier():
    store = Store(":memory:")
    e = _ep(store)
    with _archive_patch():
        r = assess_risk(_gw("bu JSON değil"), store, e)
    assert r.level == e.preliminary_risk
    assert r.rationale_tr != DEGRADED_RATIONALE
```

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_risk.py -v
```
Beklenen: `ModuleNotFoundError`

### 3. `gozcu/agents/risk.py` yaz

```python
"""Risk analisti — riski biçen, gerekçesini yazan ve **ne yapılacağını**
söyleyen uzman.

Üç tasarım kuralı belirleyici:

**Analist gerçekten araştırıyor.** Tek bir model çağrısı, arşiv metninden
kapılan belirsiz bir cümleden fazlasını üretemez: "fren bakımı dört ay
gecikmiş" hiçbir fikstür dosyasında **yazmıyor**, Görev 09'un
`overdue_maintenance_months` fonksiyonu onu tarihlerden hesaplıyor ve o sayıya
yalnız `query_equipment_history` çağrılırsa ulaşılır. Bu yüzden burada gerçek
bir araç turu var: modele okuma araçları sunuluyor, çağırdıklarını
çalıştırıyoruz, sonuçları geri veriyoruz ve nihai değerlendirme ikinci turda
çıkıyor. Görev 12'nin kök neden raporu bu sayıyı iddia ediyor; ulaşılamayan
bir sayıyı iddia etmek uydurmak olurdu.

**Analist yalnızca OKUYABİLİR.** `READ_TOOLS` dışındaki her çağrı reddediliyor.
Bir analiz yan etkisiyle hat durduramaz ya da sağlık ekibi sevk edemez;
müdahale araçları `proposed_actions` olarak Nöbetçi'ye öneriliyor ve Görev
14'ün onay akışında yürütülüyor. Öneren ile yürüten aynı adım olursa insan
döngüdeki onay tiyatroya döner.

**Her aday aksiyon gerçek bir araca bağlı.** Sistemin çalıştıramayacağı bir
öneri sadece bir cümledir; uydurulmuş araç adı taşıyan öneri sessizce düşer.

Araçlara giden tek kapı `registry.call_tool` — `field_systems` fonksiyonları
doğrudan çağrılabilir ama doğrudan çağrılan araç **aksiyon defterine hiç
düşmez**, ve defter jürinin okuduğu şey.
"""

import json

from pydantic import BaseModel, ConfigDict, Field

from gozcu.agents.interpreter import _sanitize_text
from gozcu.memory import search_timeline
from gozcu.models import (Episode, Handoff, ProposedAction, RiskAssessment,
                          RiskLevel)
from gozcu.tools.registry import TOOL_SCHEMAS, TOOLS, call_tool

# `RiskAssessment.rationale_tr` ve `ProposedAction.description_tr` ile aynı
# sınırlar. Şema sertleştirmesi `maxLength`'i telden söküyor (bkz.
# `gozcu.gateway.strict_schema`), yani model ikisini de aşabilir; kesme
# doğrulamadan ÖNCE Python tarafında yapılıyor.
MAX_RATIONALE = 800
MAX_ACTION_DESCRIPTION = 200

#: Analistin çağırabildiği araçlar — ikisi de okuma. Beş müdahale aracı
#: bilerek dışarıda: bkz. modül docstring'i.
READ_TOOLS = ("query_shift_personnel", "query_equipment_history")

#: Modele araç olarak sunulan şemalar. `TOOL_SCHEMAS`'ın süzülmüş hâli —
#: sunulmayan bir aracı model çağıramaz, çağırırsa da `_run_tool_calls`
#: reddeder (iki katman, çünkü sunulmamak bir garanti değil).
READ_TOOL_SCHEMAS = [s for s in TOOL_SCHEMAS
                     if s["function"]["name"] in READ_TOOLS]

# Yedek gerekçeler. Üçü bilerek farklı: denetim kaydı "kademe sustu",
# "kademe boş yanıt döndü" ve "yanıt okunamadı" ayrımını görebilmeli. Aynı
# metni paylaşsalardı `degraded` guard'ı sessizce ölü koda dönerdi —
# `json.loads("")` zaten patlayıp okunamayan dala düşüyor ve fark hiçbir yerde
# görünmüyordu.
DEGRADED_RATIONALE = "Risk analiz katmanı yanıt vermiyor; ön risk korundu."
EMPTY_RATIONALE = "Risk analiz katmanı boş yanıt döndürdü; ön risk korundu."
UNREADABLE_RATIONALE = "Risk analizi üretilemedi; ön risk korundu."

REFUSAL_REASON = ("Analist yalnızca okuma araçlarını çağırabilir. Müdahale "
                  "araçları öneri olarak Nöbetçi'ye iletilir ve operatör "
                  "onayıyla yürütülür.")


def _describe_tool(schema: dict) -> str:
    """Bir araç şemasını prompt satırlarına çevirir — **şemadan türeterek**.

    Prompt tek başına araç ADLARINI sayarsa parametreler ve enum değerleri
    modele hiç ulaşmaz: `dispatch_medical`'in `urgency` alanı `("normal",
    "critical")` ile sınırlı, ama Türkçe promptla çalışan bir model gayet
    doğal olarak `"kritik"` yazar ve o sevk deftere `unrecognised_urgency`
    bırakır. CLAUDE.md'nin kuralı — prompt bir enum sayıyorsa değerleri
    şemadakiyle birebir aynı olmalı — burada elle kopyalayarak değil,
    **tek kaynaktan okuyarak** tutuluyor; iki sözlüğün ayrışması mümkün değil.
    """
    function = schema["function"]
    lines = [f"- {function['name']}: {function['description']}"]
    properties = function["parameters"]["properties"]
    required = set(function["parameters"].get("required", ()))
    for name, spec in properties.items():
        note = "" if name in required else " (isteğe bağlı)"
        values = spec.get("enum")
        if values:
            note += (" — TAM OLARAK şu değerlerden biri: "
                     + ", ".join(f'"{v}"' for v in values))
        lines.append(f"    {name}{note}")
    return "\n".join(lines)


#: Promptun araç kataloğu. Yedi aracın hepsi burada — analist yalnız ikisini
#: çağırabilir ama BEŞİNİ önerebilir, dolayısıyla parametrelerini bilmek
#: zorunda.
TOOL_CATALOGUE = "\n".join(_describe_tool(s) for s in TOOL_SCHEMAS)

SYSTEM_PROMPT = """Sen bir savunma sanayi üretim tesisinin iş güvenliği uzmanısın.
Sana bir olay ve arşivden gelen benzer geçmiş olaylar verilir.

Görevin:
- Risk seviyesini belirle — tam olarak şu dördünden biri: Düşük, Orta, Yüksek,
  Kritik
- Gerekçeni Türkçe, kısa cümlelerle yaz. Kamera verisine dayan.
- KESİN HÜKÜM VERME. "olası", "muhtemelen", "görüntüye dayanarak" kullan.
- Önlenebilir olup olmadığını söyle
- Operatör düzeltmesi varsa DÜZELTİLMİŞ hâli esas al

ÖNCE ARAŞTIR: sana verilen okuma araçlarını çağırabilirsin. Olaydaki ekipman
ve personel kimlikleri KATILIMCILAR satırında yazıyor; bakım gecikmesi ya da
vardiya bilgisi gerekiyorsa uydurma, aracı çağır. Sonuçlar geldikten sonra
değerlendirmeni yaz.

Her aksiyon önerisini SADECE aşağıdaki araçlardan birine bağla. Araç adını ve
parametre değerlerini burada yazdığı gibi, birebir kullan:
{tools}

Var olmayan bir araç adı uydurma. Değerlendirmeyi yazarken sadece JSON
döndür."""


class _RiskResponse(BaseModel):
    """Modelin döndürdüğü şekil.

    `RiskAssessment`'ten ayrı, çünkü onun `id` ve `episode_id` alanları var ve
    katı şema modunda her alan `required` oluyor — yani model kendi veritabanı
    kimliğini uydurmak zorunda kalırdı.
    """

    model_config = ConfigDict(extra="forbid")

    level: RiskLevel
    rationale_tr: str = Field(max_length=MAX_RATIONALE)
    preventable: bool
    proposed_actions: list[ProposedAction] = Field(default_factory=list)


def _fallback(episode: Episode, rationale_tr: str) -> _RiskResponse:
    """Analiz okunamadığında epizot yine de bir değerlendirme kazanır.

    Ön risk korunuyor: analiz katmanı sustu diye "Düşük" demek, riski
    olmadığı yere düşürmek olurdu.
    """
    return _RiskResponse(level=episode.preliminary_risk,
                         rationale_tr=rationale_tr, preventable=False)


def _sanitize_action(action):
    """Bir `proposed_actions` girdisinin açıklamasını sınıra çeker.

    Üst düzey `rationale_tr` kesilip iç içe açıklama kesilmezse tek uzun bir
    öneri bütün değerlendirmeyi doğrulama hatasına düşürür — ve kaybedilen
    şey öneri değil, analizin tamamı olur.
    """
    if not isinstance(action, dict):
        return action
    description = action.get("description_tr")
    if not isinstance(description, str):
        return action
    return {**action,
            "description_tr": _sanitize_text(description,
                                             MAX_ACTION_DESCRIPTION)}


def _parse(content: str) -> _RiskResponse | None:
    """Modelin ham çıktısını doğrulanmış bir yanıta çevirir; olmazsa `None`.

    İçeriğin iyi biçimli JSON olduğu varsayılmıyor: `ask()` şemalı istek
    tükendiğinde şemasız bir son deneme yapıyor (Görev 03), dolayısıyla düz
    metin de gelebilir.
    """
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
        return _RiskResponse(**data)
    except Exception:  # noqa: BLE001 — bozuk çıktı bir koşuyu düşürmemeli
        return None


def _read_assessment(response, episode: Episode) -> _RiskResponse:
    """Yanıtı değerlendirmeye çevirir; her arıza kendi yedek metnine düşer."""
    if response.degraded:
        return _fallback(episode, DEGRADED_RATIONALE)
    if not (response.content or "").strip():
        return _fallback(episode, EMPTY_RATIONALE)
    parsed = _parse(response.content)
    return parsed if parsed is not None else _fallback(episode,
                                                       UNREADABLE_RATIONALE)


def _tool_calls(response) -> list[dict]:
    """Yanıttaki araç çağrıları — hiç yoksa boş liste.

    Körlemesine indekslenmiyor: bozulmuş yanıt `tool_calls=[]` taşıyor ve
    `ask()` şemasız son denemeden de cevap verebiliyor (Görev 03).
    """
    calls = getattr(response, "tool_calls", None) or []
    return [c for c in calls if isinstance(c, dict)]


def _call_arguments(call: dict) -> tuple[str | None, dict]:
    """`(araç adı, parametreler)`; okunamayan argüman boş sözlüğe düşer."""
    function = call.get("function") or {}
    if not isinstance(function, dict):
        return None, {}
    raw = function.get("arguments")
    if isinstance(raw, dict):
        return function.get("name"), raw
    try:
        parsed = json.loads(raw or "{}")
    except (ValueError, TypeError):
        parsed = {}
    return function.get("name"), parsed if isinstance(parsed, dict) else {}


def _run_tool_calls(store, calls: list[dict], ts: float) -> list[dict]:
    """Okuma araçlarını çalıştırır, sonuçları model mesajlarına çevirir.

    Yürütme `call_tool` üzerinden geçiyor — tek meşru giriş noktası o, ve
    aksiyon defterine yazan da o. `ts` **videonun zamanı**: defterdeki "ajan
    ne zaman araştırdı" sorusunun anlamlı cevabı sunucu saati değil,
    görüntüdeki an.

    Reddedilen çağrı deftere HİÇ düşmüyor: olmamış bir aksiyon defterde
    görünmemeli. Reddin kendisi modele geri söyleniyor ki ikinci turda o
    aracı öneri olarak yazsın.
    """
    messages = []
    for call in calls:
        name, params = _call_arguments(call)
        if name in READ_TOOLS:
            try:
                result = call_tool(store, name, params, ts=ts)
            except Exception as error:  # noqa: BLE001 — bozuk argüman koşuyu düşürmemeli
                result = {"tool_name": name, "failed": True,
                          "error": str(error)}
        else:
            result = {"tool_name": name, "refused": True,
                      "reason": REFUSAL_REASON}
        messages.append({"role": "tool", "tool_call_id": call.get("id", ""),
                         "name": name,
                         "content": json.dumps(result, ensure_ascii=False,
                                               default=str)})
    return messages


def _assistant_turn(response) -> dict:
    """Modelin araç çağıran turu — ikinci istekte geçmişte durmalı, yoksa
    `tool` rolündeki mesajların bağlandığı çağrı ortada kalır."""
    return {"role": "assistant", "content": response.content or None,
            "tool_calls": response.tool_calls}


def _prompt(episode: Episode, history_text: str, correction_text: str) -> str:
    participants = ", ".join(episode.participants) or "(bilinmiyor)"
    lines = [f"OLAY: {episode.summary_tr}",
             f"ÖN RİSK: {episode.preliminary_risk}",
             f"KATILIMCILAR (ekipman/personel kimlikleri): {participants}"]
    if correction_text:
        lines.append(correction_text)
    lines.append(f"\nARŞİV:\n{history_text}")
    return "\n".join(lines)


def assess_risk(gw, store, episode: Episode) -> RiskAssessment:
    """Epizodu değerlendirir, kaydeder ve süpervizöre devreder.

    Akış: arşive bak → modele sor (okuma araçlarıyla) → çağırdığı araçları
    defter üzerinden çalıştır → sonuçlarla ikinci kez sor → süz, kaydet,
    devret.

    Araç turu **isteğe bağlı**: model hiçbir şey çağırmazsa ya da kademe
    bozuksa tek çağrılık değerlendirmeye düşülür. Bir kesinti bir koşuyu
    düşürmemeli (CLAUDE.md çıktı sözleşmesi).
    """
    history = search_timeline(
        gw, store, f"{episode.summary_tr} {' '.join(episode.participants)}",
        exclude_id=episode.id)
    history_text = "\n".join(f"- {e.summary_tr}" for e in history) or "- (kayıt yok)"

    corrections = store.corrections(episode.id) if episode.id else []
    correction_text = "\n".join(
        f"- OPERATÖR DÜZELTMESİ — {c.field}: '{c.old}' yerine '{c.new}'"
        for c in corrections)

    messages = [
        {"role": "system",
         "content": SYSTEM_PROMPT.format(tools=TOOL_CATALOGUE)},
        {"role": "user",
         "content": _prompt(episode, history_text, correction_text)},
    ]

    response = gw.ask("main", messages, schema=_RiskResponse,
                      tools=READ_TOOL_SCHEMAS)

    calls = [] if response.degraded else _tool_calls(response)
    if calls:
        results = _run_tool_calls(store, calls, ts=episode.start_ts)
        messages = [*messages, _assistant_turn(response), *results]
        # İkinci tur araçsız: nihai değerlendirme isteniyor, yeni bir tur
        # değil. Araçlar yine sunulsaydı model sonsuza dek araştırabilirdi.
        response = gw.ask("main", messages, schema=_RiskResponse)

    parsed = _read_assessment(response, episode)

    # Uydurulmuş araç adları düşürülür, süpervizöre asla iletilmez.
    actions = [a for a in parsed.proposed_actions if a.tool_name in TOOLS]

    assessment = RiskAssessment(
        episode_id=episode.id, level=parsed.level,
        rationale_tr=parsed.rationale_tr, preventable=parsed.preventable,
        proposed_actions=actions)
    assessment.id = store.save_risk(assessment)

    store.save_handoff(Handoff(ts=episode.start_ts,
                               source_agent="risk_analyst",
                               target_agent="supervisor",
                               reason=f"risk: {parsed.level}", confidence=0.85,
                               payload_ref=f"risk:{assessment.id}"))
    return assessment
```

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_risk.py -v
```
Beklenen: 17 passed

### 5. Commit

```bash
git add gozcu/agents/risk.py tests/test_risk.py
git commit -m "feat: risk analyst with real read-tool investigation"
```

## Doğrulama

```bash
uv run pytest tests/test_risk.py -v
```
Beklenen: **17 passed**

## Tamamlanma notları (gelecek görevleri bağlayan)

- **Analist SALT OKUR ve bu iki katmanda zorlanıyor.** Modele yalnızca
  `READ_TOOLS` şemaları sunuluyor (`READ_TOOL_SCHEMAS`), AYRICA sunulmamış her
  araç çağrısı yürütme anında reddediliyor (`_run_tool_calls`). İkisi birden
  var, çünkü bir aracın sunulmamış olması modelin onu istemeyeceğinin garantisi
  değil.
- **Salt okur olması neden önemli:** analist müdahale araçlarına ulaşabilseydi
  hattı durdurmak ve sağlık ekibi sevk etmek bir *analizin* yan etkisi olurdu ve
  [Görev 14](14-nobetci.md)'ün operatör onayı tamamen atlanırdı — kapıyı
  yenerek değil, kapıya hiç girmeyerek.
- **`proposed_actions` ÖNERİDİR.** Her müdahale aracının yürütülmesi ve onay
  kapısı [Görev 14](14-nobetci.md)'e ait. Analist hiçbirini çalıştırmaz.
- **Araç sonuçları `call_tool` üzerinden alınıyor**, `field_systems.*` doğrudan
  çağrılarak değil — doğrudan çağrılan araç aksiyon defterine hiç düşmez. `ts`
  olarak `episode.start_ts` geçiliyor, böylece defterde araştırma **videonun
  zamanında** görünüyor.
- **Ekipman kimlikleri `episode.participants`'tan geliyor** (örn.
  `["IST-04", "PRS-001"]`), modelin tahmininden değil; prompt onları
  KATILIMCILAR satırında veriyor.
- **Promptun araç kataloğu `TOOL_SCHEMAS`'tan üretiliyor** (`_describe_tool`),
  böylece `urgency` gibi enum değerleri (`normal` / `critical`) şemadan
  ayrışamıyor. Bu listeyi elle yazma.
- **Doğrulamadan ÖNCE temizle:** `rationale_tr` (800) VE her bir iç içe
  `proposed_actions[*].description_tr` (200). `maxLength` artık tele
  çıkmadığı için taşma beklenen durumdur; korumasız bir `ValidationError`
  gerçek bir değerlendirmeyi yedek kabuğa çevirir.
- **Üç ayrı yedek gerekçe** — `DEGRADED_RATIONALE` (kademe sustu),
  `EMPTY_RATIONALE` (boş yanıt), `UNREADABLE_RATIONALE` (okunamayan yanıt).
  Bilerek farklılar: denetim kaydı üç arızayı birbirinden ayırabilmeli.
- **`search_timeline(..., exclude_id=episode.id)` zorunlu** ve artık bir testle
  gerçekten doğrulanıyor (`exclude_id` çağrı argümanları üzerinden kontrol
  ediliyor).
