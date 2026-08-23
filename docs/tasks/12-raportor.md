# Görev 12 — Raportör ve kök neden raporu (`gozcu/agents/reporter.py`)

> ## ✅ TAMAMLANDI — 23 Ağustos 2026, `a8cf363`
>
> **Raportör indi.** `gozcu/agents/reporter.py` var; `tests/test_reporter.py` 22
> test ile yeşil. Bu dosyayı yeniden uygulama — aşağısı ne yapıldığının kaydı.
>
> **Sonraki göreve başlarken bilmen gerekenler**
> ([kararlar](#tamamlanma-notları-gelecek-görevleri-bağlayan) bölümüne bak):
> **promptun alan listesi ŞEMADAN TÜRETİLİYOR** — elle yazılan liste bir kez
> ayrıştı (`guven_sinirlari` ↔ `confidence_limits`) ve gerçek alan sessizce boş
> kaldı; **rapordaki her rakam, tarih ve kimlik aksiyon defterine dayanmak
> zorunda** — dayanağı yoksa rapor "kayıtlarda bu veri yok" yazar, tahmin etmez;
> ve **üç ayrı arıza metni** var (kademe sustu / boş yanıt / okunamayan yanıt),
> çünkü operatör de denetim kaydı da üçünü birbirinden ayırabilmeli.

**Sahip:** `beyzaalive` · **Gün:** 25 Ağustos · **Süre:** ~2.5 saat
**Bağımlılık:** [01](01-sozlesme.md), [02](02-olay-deposu.md), [03](03-gateway.md), [10](10-saha-araclari.md), [11](11-risk-analisti.md)
**Etiket:** `cold-start`

## Bağlam

### Proje ne?

Gözcü, fabrika kamera kaydını izleyip olayları fark eden ve operatörle Türkçe
konuşan bir karar destek sistemi. TEKNOFEST Yapay Zekâ Dil Ajanları Yarışması,
3. senaryo. Teslim 26 Ağustos 23:59.

### Bu görev neden var?

Olay kapandığında sistemin yazdığı **kök neden raporu.** Demo'nun kapanış anı
bu. Elindeki malzeme zaten depoda birikmiş durumda: olay zinciri, risk
değerlendirmeleri, operatörün yaptığı düzeltmeler, çağrılan saha sistemleri,
diyalog dökümü. Senin işin bunları tek bir Türkçe rapora dönüştürmek.

Üç kural raporu belirliyor:

**Operatör düzeltmesi kazanır.** Operatör "araç devrilmedi, yük düştü" dediyse
rapor da yük düştü der. Düzeltme raporu etkilemiyorsa, düzeltme hiçbir şey
yapmamış demektir — ve bu, puanın %20'sini taşıyan diyalog kaleminin çöktüğü yer.

**Kesin hüküm yok.** Kamera bir kazanın sebebine hükmedemez. Rapor "muhtemel kök
neden" der ve `confidence_limits` alanında **neyi bilemeyeceğini açıkça yazar.**
Bu bir zayıflık değil; şartnamenin *açıklanabilirlik* beklentisinin karşılığı.

**Türkçe, kısa cümle, saha terminolojisi.** `istif aracı`, `vardiya amiri`,
`yerde hareketsiz kişi`. Edilgen çatıdan kaçın.

## Kurulum

```bash
git clone git@github.com:uvyscengiz/gozcu-ai-teknofest.git
cd gozcu-ai-teknofest
uv sync --extra dev
uv run pytest tests/ -v
```

Gateway erişimin olmasa da bu görev biter — bütün testler mock kullanıyor.

## Bağımlı olduğun imzalar

```python
# gozcu/gateway.py
Gateway.ask(tier, messages, schema=None, tools=None) -> Response
#   kademe pozisyonel; bu görevde "main" kullanacaksın
Response(content: str, tool_calls: list, model: str, latency_ms: int,
      tokens: int, degraded: bool)

# gozcu/store.py — hepsi okuma
Store.episodes() -> list[Episode]
Store.risks() -> list[RiskAssessment]
Store.corrections(episode_id: int) -> list[Correction]
Store.actions() -> list[ActionRecord]
Store.dialogue() -> list[DialogueTurn]

# gozcu/models.py — alanları
Episode(id, start_ts, end_ts, phase, summary_tr, participants, preliminary_risk, state)
RiskAssessment(id, episode_id, level, rationale_tr, preventable, proposed_actions)
Correction(id, ts, episode_id, field, old, new, rationale)
ActionRecord(id, ts, tool_name, params, result, actor, approval)
DialogueTurn(id, ts, role, text)
```

**Bozulmuş yanıt guard'ı (Görev 03).** `main` kademesi de artık kesintide istisna
atmıyor, **bozuluyor**: `content=""`, `degraded=True`. Rapor kabuğu dalı bu
yüzden ölü kod değil, canlı yol — bozulmuş bir koşudan da şartnamenin dört
anahtarı (`summary` · `events` · `risk` · `actions`) çıkmalı. JSON ayrıştırmayı
boş içeriğe karşı koru; `except GatewayError` bir kesintiyi yakalamaz.

**Şema sertleştirmesi (Görev 03/04).** Şema sertleştirmesi **gateway'in içinde**. `Gateway.ask()`'e düz bir pydantic
modeli ver; `strict_schema()`'i kimse elle çağırmıyor. Sonucu: `maxLength`,
`minimum`/`maximum` ve `pattern` artık tele hiç çıkmıyor — yani **her ajan
doğrulamadan ÖNCE kendi değerlerini temizlemek zorunda**. Ayrıca `ask()` şemalı
istek tükendiğinde şemasız bir son deneme yapıyor, dolayısıyla dönen içerik iyi
biçimli JSON olmayabilir; ayrıştırıcılar bunu varsaymamalı.

Burada somut karşılığı: `RootCauseReport`'un uzunluk sınırları — `what_happened`
(800), `probable_root_cause` (600), `confidence_limits` (400) — modele hiç
gitmiyor. `RootCauseReport(**…)` çağrılmadan **önce** üçü de kendi sınırına
kesilecek. Kesilmezse uzun bir rapor doğrulama hatasına düşer ve mock'larla
yeşil olan kod sahada hep kabuk rapor üretir.

> **Görev 11 indi (`dd803fd`) — "4 ay gecikmiş fren bakımı" artık ULAŞILABİLİR
> ve DEFTERE DÜŞÜYOR.** Risk analisti değerlendirmeyi yazmadan önce
> `query_equipment_history` aracını `call_tool` üzerinden çağırıyor; araç
> `overdue_maintenance_months` alanını fikstürdeki bakım tarihlerinden
> **türeterek** döndürüyor ([Görev 09](09-tesis-dunyasi.md)) ve çağrı
> `detail.action_ledger`'a epizodun **video zamanıyla** yazılıyor. Aşağıdaki
> testte `probable_root_cause` içinde geçen `4` bir model çıktısı taklidi —
> sayının kaynağı o değil. Rapor bu sayıyı `store.actions()` içindeki
> `query_equipment_history` kaydına **dayandırmalı** (istersen defter satırına
> atıf vererek); hiçbir şeyin üretmediği bir sayıyı iddia etmek uydurmaktır.

## Ne yapacaksın

```python
class RootCauseReport(BaseModel):
    what_happened: str
    probable_root_cause: str
    actions_taken: list[str]
    prevention_recommendations: list[str]
    confidence_limits: str
```

Ve tek bir fonksiyon: `generate_root_cause_report(gw, store) -> RootCauseReport`

Depodaki her şeyi tek bir isteme topla, `gw.ask("main", ...)` ile rapor ürettir.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_reporter.py`

```python
"""Görev 12 — raportör ve kök neden raporu.

Rapor projenin **insana dönük** çıktısı: bir operatör onu okuyup bir iş
kazasının sebebi hakkında hüküm kuracak. Bu yüzden testler metnin varlığına
değil, üç garantisine bakıyor:

- **Prompt şemadan türüyor.** Promptun saydığı her alan modelde gerçekten
  var; elle yazılmış bir alan listesi ayrışır.
- **Her sayı kanıta dayanıyor.** Türetilmiş `overdue_maintenance_months`
  rakamı aksiyon defterinden prompta ulaşıyor; ulaşmıyorsa rapordaki sayı
  uydurmadır.
- **Arızalar birbirinden ayırt ediliyor.** Bozulmuş kademe, boş yanıt ve
  okunamayan yanıt üç farklı metin üretir — aynı kabuğu paylaşsalardı
  guard'lar sessizce ölü koda dönerdi.
"""

import json
import re
from unittest.mock import Mock

from gozcu.agents.reporter import (DEGRADED_REASON, EMPTY_REASON,
                                   GROUNDING_RULE, MAX_CONFIDENCE_LIMITS,
                                   MAX_ROOT_CAUSE, MAX_WHAT_HAPPENED,
                                   MISSING_CONFIDENCE_LIMITS, SECTIONS,
                                   SYSTEM_PROMPT, UNREADABLE_REASON,
                                   RootCauseReport,
                                   generate_root_cause_report)
from gozcu.gateway import Response
from gozcu.models import (ActionRecord, Correction, Detail, DialogueTurn,
                          Episode, RiskAssessment)
from gozcu.store import Store
from gozcu.tools.registry import call_tool

RESPONSE_JSON = ('{"what_happened":"B-Hattı sevkiyat alanında yük düştü.",'
                 '"probable_root_cause":"Fren bakımının 4 ay gecikmiş olması.",'
                 '"actions_taken":["İSG kaydı açıldı"],'
                 '"prevention_recommendations":["Bakım periyodu denetlensin"],'
                 '"confidence_limits":"Kamera görüntüsü fren durumunu doğrudan gösteremez."}')

#: Epizodun özeti düzeltmenin yeni değerinden bilerek FARKLI. Aynı olsalardı
#: "düzeltme prompta ulaştı" testi düzeltme silinse bile yeşil kalırdı —
#: metni epizot özeti zaten taşıyordu.
EPISODE_SUMMARY = "B-Hattı sevkiyat alanında bir olay gelişti"


def _gw(content=RESPONSE_JSON, **kw):
    gw = Mock()
    gw.ask.return_value = Response(content=content, **kw)
    return gw


def _seeded_store():
    store = Store(":memory:")
    e = Episode(start_ts=12.0, phase="outcome", summary_tr=EPISODE_SUMMARY,
                participants=["IST-04"], preliminary_risk="Yüksek",
                state="closed")
    e.id = store.create_episode(e)
    store.save_risk(RiskAssessment(episode_id=e.id, level="Yüksek",
                                   rationale_tr="fren gecikmesi",
                                   preventable=True))
    store.save_action(ActionRecord(ts=1.0, tool_name="open_safety_incident",
                                   params={}, result={"record_no": "x"},
                                   actor="agent", approval="not_required"))
    store.save_dialogue(DialogueTurn(ts=1.0, role="operator",
                                     text="ne oldu?"))
    return store, e


def _messages(gw):
    return gw.ask.call_args.args[1]


def _prompt_text(gw):
    return _messages(gw)[-1]["content"]


def _line_starting(text, prefix):
    return next(l for l in text.splitlines() if l.startswith(prefix))


# -- kademe ve şema ---------------------------------------------------------

def test_report_uses_the_large_reasoning_tier():
    gw = _gw()
    store, _ = _seeded_store()
    generate_root_cause_report(gw, store)
    assert gw.ask.call_args.args[0] == "main"
    assert gw.ask.call_args.kwargs["schema"] is RootCauseReport


# -- prompt şemadan türüyor (Kural 1) ---------------------------------------

_SNAKE_CASE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+")


def test_prompt_names_no_field_that_the_model_lacks():
    """Promptun andığı her alan adı `RootCauseReport`'ta gerçekten var.

    Prompt bir zamanlar `guven_sinirlari` diyordu; şemadaki ad
    `confidence_limits`. Model var olmayan bir anahtarı doldurur, o anahtar
    atılır ve gerçek alan boş kalırdı — CLAUDE.md'nin "bir kez ayrıştılar ve
    sistem sessizce öldü" dediği arıza.
    """
    named = set(_SNAKE_CASE.findall(SYSTEM_PROMPT))
    assert named, "prompt hiçbir alan adı saymıyor — katalog düşmüş olabilir"
    assert named <= set(RootCauseReport.model_fields)


def test_prompt_field_catalogue_covers_every_model_field():
    """Katalog şemadan türetiliyor; bir alan eklenince prompt kendiliğinden
    büyümeli."""
    assert set(_SNAKE_CASE.findall(SYSTEM_PROMPT)) == set(
        RootCauseReport.model_fields)


def test_prompt_states_the_length_limits_the_wire_no_longer_carries():
    """`maxLength` şema sertleştirmesinde sökülüyor; sınırı modele prompt
    söylüyor."""
    for limit in (MAX_WHAT_HAPPENED, MAX_ROOT_CAUSE, MAX_CONFIDENCE_LIMITS):
        assert str(limit) in SYSTEM_PROMPT


# -- her sayı kanıta dayanıyor (Kural 2) ------------------------------------

def test_prompt_forbids_unevidenced_figures():
    assert GROUNDING_RULE in SYSTEM_PROMPT
    for header in SECTIONS:
        assert header in SYSTEM_PROMPT


def test_derived_maintenance_figure_reaches_the_prompt_from_the_ledger():
    """"4 ay gecikmiş fren bakımı" rakamının TEK kaynağı defter.

    Sayı hiçbir fikstür dosyasında yazmıyor; `query_equipment_history` onu
    bakım vadelerinden türetiyor ve çağrı `call_tool` üzerinden deftere
    düşüyor. Defter prompta girmezse rapordaki sayı dayanaksız kalır.
    """
    gw = _gw()
    store, e = _seeded_store()
    result = call_tool(store, "query_equipment_history",
                       {"equipment_id": "IST-04"}, ts=e.start_ts)
    assert result["overdue_maintenance_months"] == 4

    generate_root_cause_report(gw, store)
    ledger = _prompt_text(gw)
    assert "overdue_maintenance_months" in ledger
    assert '"overdue_maintenance_months": 4' in ledger


def test_prompt_includes_the_action_ledger():
    gw = _gw()
    store, _ = _seeded_store()
    generate_root_cause_report(gw, store)
    prompt = _prompt_text(gw)
    assert "open_safety_incident" in prompt
    assert "record_no" in prompt and "not_required" in prompt


def test_prompt_includes_risk_assessments_and_dialogue():
    gw = _gw()
    store, _ = _seeded_store()
    generate_root_cause_report(gw, store)
    prompt = _prompt_text(gw)
    assert "fren gecikmesi" in prompt and "ne oldu?" in prompt
    assert "Yüksek" in prompt


def test_every_section_appears_even_when_it_is_empty():
    gw = _gw()
    generate_root_cause_report(gw, Store(":memory:"))
    prompt = _prompt_text(gw)
    for header in SECTIONS:
        assert f"{header}:" in prompt
    assert prompt.count("- (yok)") == len(SECTIONS)


# -- operatör düzeltmesi kazanır --------------------------------------------

def _store_with_correction():
    store, e = _seeded_store()
    store.save_correction(Correction(ts=1.0, episode_id=e.id,
                                     field="event_type", old="araç devrildi",
                                     new="yük düştü",
                                     rationale="operatör gözlemi"))
    return store, e


def test_operator_corrections_reach_the_prompt():
    gw = _gw()
    store, _ = _store_with_correction()
    generate_root_cause_report(gw, store)
    prompt = _prompt_text(gw)
    # Epizot özeti düzeltmenin yeni değerini TAŞIMIYOR: iki iddia da ayrı ayrı
    # anlamlı.
    assert EPISODE_SUMMARY in prompt
    assert "yük düştü" not in EPISODE_SUMMARY
    assert "yük düştü" in prompt and "araç devrildi" in prompt
    assert "operatör gözlemi" in prompt


def test_the_corrected_value_supersedes_the_original():
    """Rapora ulaşmayan bir düzeltme hiçbir şey yapmamış bir düzeltmedir —
    ama prompta ikisini yan yana koymak da yetmez: modelin HANGİSİNİN geçerli
    olduğunu görmesi gerek."""
    gw = _gw()
    store, _ = _store_with_correction()
    generate_root_cause_report(gw, store)
    line = _line_starting(_prompt_text(gw), "- event_type:")
    assert "GEÇERLİ DEĞER 'yük düştü'" in line
    assert "'araç devrildi'" in line and "GEÇERSİZ" in line
    assert line.index("yük düştü") < line.index("araç devrildi")


# -- doğrulamadan ÖNCE kesme (Kural 3) --------------------------------------

def _overlong(field, filler):
    """Geçerli raporun tek bir alanını sınırın üstüne taşıran yanıt."""
    payload = json.loads(RESPONSE_JSON)
    payload[field] = filler
    return json.dumps(payload, ensure_ascii=False)


def test_overlong_fields_are_truncated_instead_of_collapsing_the_report():
    """Şema sertleştirmesi `maxLength`'i telden söküyor; taşma BEKLENEN yol.

    Ham hâliyle pydantic'e verilseydi doğrulama patlar ve GERÇEK bir rapor
    kabuğa düşerdi — mock'larla yeşil, sahada hep kabuk.
    """
    long_text = "Sevkiyat alanında yük düştü ve istif aracı durdu. " * 30
    gw = _gw(_overlong("what_happened", long_text))
    store, _ = _seeded_store()
    r = generate_root_cause_report(gw, store)
    assert len(r.what_happened) <= MAX_WHAT_HAPPENED
    assert r.what_happened.startswith("Sevkiyat alanında yük düştü")
    for reason in (DEGRADED_REASON, EMPTY_REASON, UNREADABLE_REASON):
        assert reason not in r.what_happened
    # Taşmayan alanlar gerçek rapordan geliyor, kabuktan değil.
    assert "4 ay" in r.probable_root_cause


def test_every_length_limited_field_is_truncated():
    store, _ = _seeded_store()
    for field, limit in (("what_happened", MAX_WHAT_HAPPENED),
                         ("probable_root_cause", MAX_ROOT_CAUSE),
                         ("confidence_limits", MAX_CONFIDENCE_LIMITS)):
        gw = _gw(_overlong(field, "Kanıta dayanan uzun bir cümle. " * 40))
        r = generate_root_cause_report(gw, store)
        assert len(getattr(r, field)) <= limit
        assert getattr(r, field).startswith("Kanıta dayanan")


# -- üç ayrı arıza, üç ayrı metin (Kural 4) ---------------------------------

def test_degraded_tier_returns_a_report_shell_not_an_exception():
    """Yanıt GEÇERLİ JSON taşıyor: kabuk yalnızca `degraded` kontrolünden
    çıkabilir. İçerik boş olsaydı test guard silinince de yeşil kalırdı."""
    gw = Mock()
    gw.ask.return_value = Response(content=RESPONSE_JSON, degraded=True)
    store, _ = _seeded_store()
    r = generate_root_cause_report(gw, store)
    assert DEGRADED_REASON in r.what_happened
    assert r.confidence_limits.strip()
    assert "4 ay" not in r.probable_root_cause


def test_empty_content_is_reported_as_its_own_fault():
    gw = _gw(content="   ")
    store, _ = _seeded_store()
    r = generate_root_cause_report(gw, store)
    assert EMPTY_REASON in r.what_happened


def test_unreadable_content_is_reported_as_its_own_fault():
    gw = _gw(content="Rapor: yük düştü, sebebi fren.")
    store, _ = _seeded_store()
    r = generate_root_cause_report(gw, store)
    assert UNREADABLE_REASON in r.what_happened


def test_the_three_fallback_texts_are_distinct():
    assert len({DEGRADED_REASON, EMPTY_REASON, UNREADABLE_REASON}) == 3


# -- rapor her hâlükârda sınırlarını yazar ----------------------------------

def test_report_always_states_its_confidence_limits():
    """Model alanı boş bırakırsa rapor yine de neyi bilemediğini söyler.

    "Kesin hüküm yok" bu tek alanda duruyor; boş bir `confidence_limits`
    pydantic'ten sessizce geçer ve rapor kendini mutlak bir hüküm gibi
    sunardı.
    """
    gw = _gw(RESPONSE_JSON.replace(
        '"Kamera görüntüsü fren durumunu doğrudan gösteremez."', '""'))
    store, _ = _seeded_store()
    r = generate_root_cause_report(gw, store)
    assert r.confidence_limits.strip()
    assert r.confidence_limits == MISSING_CONFIDENCE_LIMITS
    # Gerçek rapor kabuğa düşmedi; sadece eksik alan tamamlandı.
    assert "4 ay" in r.probable_root_cause


def test_the_models_own_confidence_limits_survive():
    gw = _gw()
    store, _ = _seeded_store()
    r = generate_root_cause_report(gw, store)
    assert r.confidence_limits.startswith("Kamera görüntüsü")


# -- teslim şekli (Kural 7) -------------------------------------------------

def test_empty_store_returns_a_full_report_shape():
    r = generate_root_cause_report(_gw(), Store(":memory:"))
    assert isinstance(r, RootCauseReport)
    assert set(r.model_dump()) == {"what_happened", "probable_root_cause",
                                   "actions_taken",
                                   "prevention_recommendations",
                                   "confidence_limits"}
    assert r.what_happened.strip() and r.confidence_limits.strip()
    assert isinstance(r.actions_taken, list)


def test_report_is_deliverable_under_detail_root_cause_report():
    """Görev 17 raporu `detail.root_cause_report` altında düz `dict` olarak
    teslim ediyor."""
    gw = _gw()
    store, _ = _seeded_store()
    r = generate_root_cause_report(gw, store)
    detail = Detail(root_cause_report=r.model_dump())
    assert detail.root_cause_report["what_happened"] == r.what_happened


def test_report_is_returned_not_persisted():
    gw = _gw()
    store, _ = _seeded_store()
    before = (len(store.episodes()), len(store.risks()), len(store.actions()),
              len(store.handoffs()), len(store.dialogue()))
    generate_root_cause_report(gw, store)
    after = (len(store.episodes()), len(store.risks()), len(store.actions()),
             len(store.handoffs()), len(store.dialogue()))
    assert before == after
```

`test_the_corrected_value_supersedes_the_original` bu görevin en önemli
garantisi: rapora ulaşmayan bir düzeltme, hiçbir şey yapmamış bir
düzeltmedir — ve düzeltmeyi prompta koymak da yetmez, promptun HANGİ değerin
geçerli olduğunu söylemesi gerekir.

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_reporter.py -v
```
Beklenen: `ModuleNotFoundError: No module named 'gozcu.agents.reporter'`

### 3. `gozcu/agents/reporter.py` yaz

```python
"""Raportör — olay kapandığında bir **insanın** okuyacağı kök neden raporu.

Demo'nun kapanış anı bu. Malzeme zaten depoda: olay zinciri, risk
değerlendirmeleri, operatörün yaptığı düzeltmeler, çağrılan saha sistemleri ve
diyalog dökümü. Buradaki iş onları tek bir Türkçe rapora dönüştürmek.

**Bu rapor nereye gidiyor.** `generate_root_cause_report()` bir
`RootCauseReport` döndürür ve **hiçbir şey kaydetmez** — deposu yok, çağıran
onu istediği gibi kullanır. Görev 17'nin boru hattı iki şey yapıyor:

- `what_happened` şartnamenin dört anahtarından biri olan **`summary`** hâline
  gelir. Yani bu alan bir iç metin değil, jürinin okuduğu ilk cümledir.
- Raporun tamamı `detail.root_cause_report` altında **düz bir `dict`** olarak
  teslim edilir: `Detail.root_cause_report` `dict | None` tipli, dolayısıyla
  çağıran `.model_dump()` uygular. Model nesnesi oraya doğrudan konmaz.

Raporu belirleyen dört kural:

**Operatör düzeltmesi kazanır.** Operatör "araç devrilmedi, yük düştü" dediyse
rapor da yük düştü der. Düzeltme bölümü eski değeri GEÇERSİZ diye işaretliyor;
ikisini yan yana koyup hangisinin geçerli olduğunu söylememek modele seçim
bırakmak olurdu. Rapora ulaşmayan bir düzeltme hiçbir şey yapmamış bir
düzeltmedir — ve orası puanın %20'sini taşıyan diyalog kalemi.

**Her sayı kanıta dayanır.** Raporun iddia ettiği "4 ay gecikmiş fren bakımı"
hiçbir fikstür dosyasında yazmıyor: `query_equipment_history` onu bakım
vadeleriyle senaryo tarihinden **türetiyor** ve çağrı aksiyon defterine
videonun zamanıyla düşüyor (Görev 09/11). Defter prompta olduğu gibi giriyor
ve `GROUNDING_RULE` modele sayıların kaynağını yazdırıyor. Bu kural olmadan
model aynı sayıyı arşiv metnindeki bulanık "gecikmiş bakım" ifadesinden
uydurabilir — ve raporu defterle karşılaştıran bir jüri dayanaksız bir iddia
bulur.

**Kesin hüküm yok.** Kamera bir kazanın sebebine hükmedemez. Rapor "muhtemel
kök neden" der ve `confidence_limits` alanında neyi bilemeyeceğini açıkça
yazar. Model o alanı boş bırakırsa `MISSING_CONFIDENCE_LIMITS` devreye girer:
boş bir sınırlar alanı pydantic'ten sessizce geçer ve rapor kendini mutlak bir
hüküm gibi sunardı.

**Promptun alan listesi şemadan türer.** Prompt bir zamanlar
`guven_sinirlari` diyordu; şemadaki ad `confidence_limits`. Model var olmayan
bir anahtarı doldurur, o anahtar atılır ve gerçek alan boş kalırdı. Elle
yazılan liste ayrışır, türetilen liste ayrışamaz.
"""

import json

from pydantic import BaseModel, ConfigDict, Field

from gozcu.agents.interpreter import _sanitize_text
from gozcu.agents.router import mmss

# `RootCauseReport` alan sınırları. Şema sertleştirmesi `maxLength`'i telden
# söküyor (bkz. `gozcu.gateway.strict_schema`), yani model üçünü de aşabilir;
# kesme doğrulamadan ÖNCE Python tarafında yapılıyor. Sınırın modele ulaşan
# tek kopyası promptun alan kataloğu.
MAX_WHAT_HAPPENED = 800
MAX_ROOT_CAUSE = 600
MAX_CONFIDENCE_LIMITS = 400

#: Promptun bölüm başlıkları. Sistem mesajı da kullanıcı mesajı da BURADAN
#: okuyor: kural metni "AKSİYON DEFTERİ'ne bak" derken başlık başka bir şey
#: yazıyorsa model neye bakacağını bilemez.
SECTION_EPISODES = "OLAY ZİNCİRİ"
SECTION_RISKS = "RİSK DEĞERLENDİRMELERİ"
SECTION_CORRECTIONS = "OPERATÖR DÜZELTMELERİ"
SECTION_LEDGER = "AKSİYON DEFTERİ"
SECTION_DIALOGUE = "DİYALOG"
SECTIONS = (SECTION_EPISODES, SECTION_RISKS, SECTION_CORRECTIONS,
            SECTION_LEDGER, SECTION_DIALOGUE)

EMPTY_SECTION = "- (yok)"

# Yedek metinler. Üçü bilerek farklı: operatörün okuduğu şey de denetim kaydı
# da "kademe sustu", "kademe boş yanıt döndü" ve "yanıt okunamadı" ayrımını
# görebilmeli — üçü farklı arızalar ve farklı müdahale gerektiriyor. Aynı
# kabuğu paylaşsalardı `degraded` guard'ı sessizce ölü koda dönerdi:
# `json.loads("")` zaten patlayıp okunamayan dala düşüyor ve fark hiçbir yerde
# görünmüyordu.
DEGRADED_REASON = "Rapor katmanı yanıt vermiyor"
EMPTY_REASON = "Rapor katmanı boş yanıt döndürdü"
UNREADABLE_REASON = "Rapor yanıtı okunamadı"

#: Model `confidence_limits`'i boş bırakırsa rapor yine de neyi bilemediğini
#: söyler. "Kesin hüküm yok" kuralının tek somut karşılığı bu alan.
MISSING_CONFIDENCE_LIMITS = (
    "Rapor kendi sınırlarını yazmadı. Bu rapor yalnızca kamera görüntüsüne, "
    "aksiyon defterine ve operatör beyanına dayanır; görüntünün dışında kalan "
    "hiçbir nedeni doğrulayamaz ve kesin hüküm taşımaz.")

#: Sayıların kaynağını zorunlu kılan kural. `gozcu.agents.risk` aynı ilkeyi
#: analiz tarafında uyguluyor ("uydurma, aracı çağır"); rapor tarafında
#: karşılığı bu: araç zaten çağrıldı, sonucu defterde — rapor oradan alacak.
GROUNDING_RULE = (
    f"HER SAYIYI, TARİHİ VE KİMLİĞİ KANITA DAYANDIR. Rapordaki her rakam, her "
    f"tarih ve her ekipman/personel kimliği sana verilen bölümlerden birinde "
    f"geçmek zorunda — özellikle {SECTION_LEDGER} bölümündeki araç "
    f"sonuçlarında. Bir sayıyı kullanırken hangi kayıttan aldığını cümle "
    f"içinde belirt. Dayanağı olmayan bir sayıyı TAHMİN ETME, YUVARLAMA ve "
    f"arşiv metninden ÇIKARIM YAPMA; onun yerine 'kayıtlarda bu veri yok' "
    f"yaz.")


class RootCauseReport(BaseModel):
    """Raporun sözleşmesi.

    Alan açıklamaları burada duruyor çünkü promptun alan kataloğu **bu
    şemadan** üretiliyor: açıklamayı değiştirmek promptu da değiştirir, ikisi
    ayrışamaz.
    """

    model_config = ConfigDict(extra="forbid")

    what_happened: str = Field(
        max_length=MAX_WHAT_HAPPENED,
        description="Ne oldu, nerede, kim vardı. Kayda dayanan kısa cümleler. "
                    "Bu metin operatörün okuduğu olay özetidir.")
    probable_root_cause: str = Field(
        max_length=MAX_ROOT_CAUSE,
        description="MUHTEMEL kök neden ve dayandığı kanıt. Kesin hüküm verme.")
    actions_taken: list[str] = Field(
        default_factory=list,
        description="Olay sırasında GERÇEKTEN yürütülen aksiyonlar; sadece "
                    "aksiyon defterinde görünenler. Her madde tek cümle.")
    prevention_recommendations: list[str] = Field(
        default_factory=list,
        description="Tekrarını önleyecek somut öneriler. Her madde tek cümle.")
    confidence_limits: str = Field(
        max_length=MAX_CONFIDENCE_LIMITS,
        description="Bu raporun NEYİ BİLEMEDİĞİ. Kamera verisinin göremediği "
                    "ve kayıtların cevaplamadığı şeyleri açıkça yaz.")


_SCHEMA = RootCauseReport.model_json_schema()

#: Şemadaki JSON tiplerinin Türkçe karşılıkları — prompt satırı için.
_TYPE_NAMES = {"string": "metin", "array": "metin listesi",
               "integer": "tam sayı", "number": "sayı",
               "boolean": "evet/hayır"}


def _describe_field(name: str, spec: dict, required: bool) -> str:
    """Bir şema alanını prompt satırına çevirir — **şemadan türeterek**.

    Elle yazılmış bir alan listesi şemadan ayrışır; bu liste ayrışamaz. Sınır
    (`maxLength`) de buradan geliyor: `strict_schema()` onu telden söktüğü
    için modelin sınırı öğrenebileceği tek yer prompt metni.
    """
    notes = [_TYPE_NAMES.get(spec.get("type"), "metin")]
    limit = spec.get("maxLength")
    if limit:
        notes.append(f"en fazla {limit} karakter")
    if not required:
        notes.append("boş bırakılabilir")
    return f"- {name} ({', '.join(notes)}): {spec['description']}"


#: Promptun alan kataloğu. `RootCauseReport`'a bir alan eklendiği an prompt da
#: onu saymaya başlar.
FIELD_CATALOGUE = "\n".join(
    _describe_field(name, spec, name in set(_SCHEMA.get("required", ())))
    for name, spec in _SCHEMA["properties"].items())

_SYSTEM_TEMPLATE = """Sen bir savunma sanayi üretim tesisinin olay inceleme raportörüsün.
Sana kapanmış bir olayın tam kaydı verilir: {sections}. Bu kayda dayanarak bir
kök neden raporu yaz. Raporu bir vardiya amiri okuyacak.

Kurallar:
- Türkçe yaz. Kısa cümleler, saha terminolojisi: istif aracı, vardiya amiri,
  yerde hareketsiz kişi.
- Edilgen çatıdan kaçın. "Yük düştü" de; "yükün düşmüş olduğu görülmektedir"
  deme.
- KESİN HÜKÜM VERME. Kamera bir kazanın sebebine hükmedemez. "Olası",
  "muhtemelen", "görüntüye dayanarak" kullan.
- Operatör düzeltmesi varsa DÜZELTİLMİŞ hâli esas al. {corrections} bölümünde
  hangi değerin geçerli olduğu yazıyor; GEÇERSİZ işaretli eski değeri rapora
  taşıma.
- {grounding}

Raporun alanları — tam olarak bu adlarla doldur, başka anahtar ekleme:
{fields}

Sadece JSON döndür."""

SYSTEM_PROMPT = _SYSTEM_TEMPLATE.format(sections=", ".join(SECTIONS),
                                        corrections=SECTION_CORRECTIONS,
                                        grounding=GROUNDING_RULE,
                                        fields=FIELD_CATALOGUE)

#: Kesilecek alanlar ve sınırları — **şemadan** okunuyor, elle sayılmıyor.
#: Uzunluk sınırlı bir alan eklendiğinde kesme kendiliğinden onu da kapsar.
LENGTH_LIMITS = {name: spec["maxLength"]
                 for name, spec in _SCHEMA["properties"].items()
                 if "maxLength" in spec}


def _dump(payload: dict) -> str:
    """Defter satırlarındaki sözlükleri okunur JSON'a çevirir.

    `ensure_ascii=False`: Türkçe karakterler kaçış dizisine dönerse modelin
    okuduğu kanıt metni bozulur.
    """
    return json.dumps(payload, ensure_ascii=False, default=str)


def _section(title: str, lines: list[str]) -> list[str]:
    """Bir bölüm başlığı ve satırları; satır yoksa açıkça '(yok)'.

    Boş bölüm atlanmıyor: atlanan bölüm modele "bu kayıt hiç tutulmadı" ile
    "bu olayda böyle bir kayıt yok" arasındaki farkı kaybettirir.
    """
    return [f"\n{title}:", *(lines or [EMPTY_SECTION])]


def _correction_line(correction) -> str:
    """Düzeltmeyi, hangi değerin geçerli olduğunu SÖYLEYEREK yazar.

    Eski ve yeni değeri yan yana koyup ikisini eşit sunmak modele seçim
    bırakır. Rapor operatörün düzelttiği değeri kullanmak zorunda.
    """
    return (f"- {correction.field}: GEÇERLİ DEĞER '{correction.new}' — "
            f"operatör düzeltti; eski değer '{correction.old}' GEÇERSİZ "
            f"({correction.rationale})")


def _prompt(store) -> str:
    """Depodaki her şeyi tek bir kanıt dosyasına toplar.

    Aksiyon defteri sonuçları BUDANMADAN giriyor: `query_equipment_history`
    çağrısının türetilmiş `overdue_maintenance_months` alanı raporun kök neden
    iddiasının tek dayanağı ve bir kısaltma onu düşürebilir.
    """
    episodes = store.episodes()
    parts: list[str] = []

    parts += _section(SECTION_EPISODES, [
        f"- {mmss(e.start_ts)} [{e.phase}] {e.summary_tr}" for e in episodes])

    parts += _section(SECTION_RISKS, [
        f"- {r.level}: {r.rationale_tr}" for r in store.risks()])

    corrections = [c for e in episodes if e.id
                   for c in store.corrections(e.id)]
    parts += _section(SECTION_CORRECTIONS,
                      [_correction_line(c) for c in corrections])

    parts += _section(SECTION_LEDGER, [
        f"- {mmss(a.ts)} {a.tool_name}({_dump(a.params)}) → "
        f"{_dump(a.result)} [{a.approval}]" for a in store.actions()])

    parts += _section(SECTION_DIALOGUE, [
        f"- {mmss(t.ts)} {t.role}: {t.text}" for t in store.dialogue()])

    return "\n".join(parts)


def _fallback(reason: str) -> RootCauseReport:
    """Arıza hâlinde bile şartnamenin dört anahtarı üretilebilsin diye kabuk.

    Kabuk bir bulgu gibi okunmamalı: `confidence_limits` bunun bir arıza kaydı
    olduğunu açıkça söylüyor, yoksa "Belirlenemedi" cümlesi bir inceleme
    sonucu sanılır.
    """
    return RootCauseReport(
        what_happened=f"{reason}; olay zinciri, risk değerlendirmeleri ve "
                      f"aksiyon defteri depoda kayıtlıdır.",
        probable_root_cause="Belirlenemedi — rapor katmanı bir değerlendirme "
                            "üretmedi.",
        confidence_limits=f"{reason}. Bu metin bir bulgu değil, bir arıza "
                          f"kaydıdır: kök neden hiç incelenmemiştir.")


def _parse(content: str) -> RootCauseReport | None:
    """Modelin ham çıktısını doğrulanmış bir rapora çevirir; olmazsa `None`.

    İçeriğin iyi biçimli JSON olduğu varsayılmıyor: `ask()` şemalı istek
    tükendiğinde şemasız bir son deneme yapıyor (Görev 03), dolayısıyla düz
    metin de gelebilir.

    Kesme doğrulamadan ÖNCE: şemada `maxLength` olmadığı için taşma beklenen
    yoldur ve ham hâliyle pydantic'e verilen GERÇEK bir rapor kabuğa çökerdi —
    mock'larla yeşil, sahada hep kabuk.
    """
    try:
        data = json.loads(content)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    for name, limit in LENGTH_LIMITS.items():
        value = data.get(name)
        if isinstance(value, str):
            data[name] = _sanitize_text(value, limit)

    limits = data.get("confidence_limits")
    if not isinstance(limits, str) or not limits.strip():
        data["confidence_limits"] = MISSING_CONFIDENCE_LIMITS

    try:
        return RootCauseReport(**data)
    except Exception:  # noqa: BLE001 — bozuk çıktı bir koşuyu düşürmemeli
        return None


def generate_root_cause_report(gw, store) -> RootCauseReport:
    """Depodaki kaydı tek bir Türkçe kök neden raporuna dönüştürür.

    Rapor **döndürülür, kaydedilmez**: çağıran onu `detail.root_cause_report`
    altına `.model_dump()` ile koyar ve `what_happened`'i şartnamenin
    `summary` anahtarı olarak kullanır (Görev 17).

    Üç arıza dalı da açık ve üçü ayrı metin üretiyor. `degraded` kontrolü
    olmadan bozulmuş ama gövdeli bir yanıt (ör. önbellekten dönen bayat rapor)
    canlı bulgu gibi okunur; boş içerik kontrolü olmadan ise `json.loads("")`
    tesadüfen patladığı için "okunamadı" diye raporlanırdı — kademe aslında
    hiçbir şey söylememişken.
    """
    response = gw.ask("main", [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _prompt(store)},
    ], schema=RootCauseReport)

    if response.degraded:
        return _fallback(DEGRADED_REASON)
    if not (response.content or "").strip():
        return _fallback(EMPTY_REASON)

    parsed = _parse(response.content)
    return parsed if parsed is not None else _fallback(UNREADABLE_REASON)
```

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_reporter.py -v
```
Beklenen: 22 passed

### 5. Commit

```bash
git add gozcu/agents/reporter.py tests/test_reporter.py
git commit -m "feat: root-cause reporter grounded in the action ledger"
```

## Doğrulama

```bash
uv run pytest tests/test_reporter.py -v
```
Beklenen: **22 passed**

## Takıldığında

Üveys'e yaz. **Bekleme** — bu sprintte bir saat, toplam kapasitenin yaklaşık %4'ü.

## Tamamlanma notları (gelecek görevleri bağlayan)

- **Promptun alan kataloğu DA kesme haritası DA `RootCauseReport.model_json_schema()`'den
  türetiliyor** (`FIELD_CATALOGUE`, `LENGTH_LIMITS`). Elle yazılan bir liste
  şemadan ayrışır: bu dosya bir zamanlar promptta `guven_sinirlari` derken
  modeldeki alan `confidence_limits`'ti — model var olmayan anahtarı doldurur, o
  anahtar atılır ve gerçek alan boş kalırdı. Şimdi uzunluk sınırlı yeni bir alan
  eklendiğinde prompt onu kendiliğinden sayar ve kesme kendiliğinden kapsar.
  **İkisini de elle yazma.**
- **Rapordaki her rakam, tarih ve kimlik verilen deftere/değerlendirmelere
  dayanmak zorunda** (`GROUNDING_RULE`); kanıt yoksa rapor "kayıtlarda bu veri
  yok" der, tahmin etmez. Bu kural olmadan model "4 ay" rakamını arşiv
  metnindeki bulanık "gecikmiş bakım" ifadesinden uydurabilir ve sonuç,
  [Görev 09](09-tesis-dunyasi.md)'un tarihlerden **türettiği** deftere düşmüş
  değerden ayırt edilemez.
- **Üç ayrı yedek metin** — `DEGRADED_REASON` (kademe sustu), `EMPTY_REASON`
  (boş yanıt), `UNREADABLE_REASON` (okunamayan yanıt). `gozcu/agents/risk.py` ve
  `synthesizer.py` ile aynı gelenek: operatör de denetim kaydı da üç arızayı
  birbirinden ayırabilmeli. Aynı kabuğu paylaşsalardı `degraded` guard'ı sessizce
  ölü koda dönerdi.
- **Doğrulamadan ÖNCE kes:** `what_happened` 800, `probable_root_cause` 600,
  `confidence_limits` 400. `maxLength` şema sertleştirmesinde telden söküldüğü
  için taşma **beklenen** yoldur; korumasız bir `ValidationError` gerçek bir
  raporu kabuğa çevirir — mock'larla yeşil, sahada hep kabuk.
- **Teslim şekli [Görev 17](17-cikti-sozlesmesi.md)'de:** `what_happened`
  şartnamenin `summary` anahtarı olur; raporun tamamı `detail.root_cause_report`
  altına **düz bir `dict`** olarak gider — `Detail.root_cause_report` `dict | None`
  tipli, dolayısıyla çağıran `.model_dump()` uygular. Rapor **döndürülür,
  kaydedilmez**: hiçbir şey onu depoya yazmaz.
- **Defterdeki araç sonuçları BUDANMADAN prompta giriyor** — bilerek. Budama,
  raporun atıf vermesi gereken türetilmiş rakamı (`overdue_maintenance_months`)
  düşürebilir. [Görev 17](17-cikti-sozlesmesi.md) bağlam baskısına girerse bütçe
  orada ayarlanmalı, raportörde değil.
- **Bölüm başlıkları paylaşılan sabitler** (`SECTIONS`); kural metni de prompt
  gövdesi de aynı sabitlerden okuyor, böylece dayanak kuralı var olmayan bir
  bölümü işaret edemiyor.
