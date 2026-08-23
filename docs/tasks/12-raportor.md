# Görev 12 — Raportör ve kök neden raporu (`gozcu/agents/reporter.py`)

**Sahip:** `beyzaalive` · **Gün:** 25 Ağustos · **Süre:** ~2.5 saat
**Bağımlılık:** [01](01-sozlesme.md), [02](02-olay-deposu.md), [03](03-gateway.md)
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

**Türkçe, kısa cümle, saha terminolojisi.** `istif aracı`, `shift amiri`,
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
#   kademe pozisyonel; bu görevde "ana" kullanacaksın
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
from unittest.mock import Mock

from gozcu.agents.reporter import generate_root_cause_report
from gozcu.gateway import Response
from gozcu.models import (ActionRecord, DialogueTurn, Correction, Episode,
                          RiskAssessment)
from gozcu.store import Store

RESPONSE_JSON = ('{"what_happened":"B-Hattı sevkiyat alanında yük düştü.",'
         '"probable_root_cause":"Fren bakımının 4 ay gecikmiş olması.",'
         '"actions_taken":["İSG kaydı açıldı"],'
         '"prevention_recommendations":["Bakım periyodu denetlensin"],'
         '"confidence_limits":"Kamera görüntüsü fren durumunu doğrudan gösteremez."}')


def _gw(content=RESPONSE_JSON, **kw):
    gw = Mock(); gw.ask.return_value = Response(content=content, **kw)
    return gw


def _seeded_store():
    store = Store(":memory:")
    e = Episode(start_ts=12.0, phase="outcome", summary_tr="yük düştü",
               preliminary_risk="Yüksek", state="closed")
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


def _prompt(gw):
    return gw.ask.call_args.args[1][-1]["content"]


def test_report_always_states_its_confidence_limits():
    gw = _gw(); store, _ = _seeded_store()
    r = generate_root_cause_report(gw, store)
    assert r.confidence_limits.strip()


def test_report_uses_the_large_reasoning_tier():
    gw = _gw(); store, _ = _seeded_store()
    generate_root_cause_report(gw, store)
    assert gw.ask.call_args.args[0] == "main"


def test_prompt_includes_the_action_ledger():
    gw = _gw(); store, _ = _seeded_store()
    generate_root_cause_report(gw, store)
    assert "open_safety_incident" in _prompt(gw)


def test_prompt_includes_risk_assessments_and_dialogue():
    gw = _gw(); store, _ = _seeded_store()
    generate_root_cause_report(gw, store)
    prompt_text = _prompt(gw)
    assert "fren gecikmesi" in prompt_text and "ne oldu?" in prompt_text


def test_operator_corrections_reach_the_prompt():
    gw = _gw(); store, e = _seeded_store()
    store.save_correction(Correction(ts=1.0, episode_id=e.id, field="event_type",
                                   old="araç devrildi", new="yük düştü",
                                   rationale="operatör gözlemi"))
    generate_root_cause_report(gw, store)
    prompt_text = _prompt(gw)
    assert "yük düştü" in prompt_text and "araç devrildi" in prompt_text


def test_degraded_tier_returns_a_report_shell_not_an_exception():
    gw = Mock(); gw.ask.return_value = Response(degraded=True)
    store, _ = _seeded_store()
    r = generate_root_cause_report(gw, store)
    assert r.what_happened and r.confidence_limits


def test_empty_store_does_not_crash():
    generate_root_cause_report(_gw(), Store(":memory:"))
```

Beşinci test bu görevin en önemli garantisi: rapora ulaşmayan bir düzeltme,
hiçbir şey yapmamış bir düzeltmedir.

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_reporter.py -v
```
Beklenen: `ModuleNotFoundError: No module named 'gozcu.agents.reporter'`

### 3. `gozcu/agents/reporter.py` yaz

```python
import json

from pydantic import BaseModel, ConfigDict, Field

SYSTEM_PROMPT = """Sen bir savunma sanayi üretim tesisinin olay inceleme raportörüsün.
Sana olay zinciri, risk değerlendirmeleri, operatör düzeltmeleri, alınan
aksiyonlar ve diyalog dökümü verilir. Bir kök neden raporu yaz.

Kurallar:
- Türkçe, kısa cümleler, saha terminolojisi (istif aracı, vardiya amiri)
- Edilgen çatıdan kaçın
- KESİN HÜKÜM VERME. Kamera verisine dayanan kalibre edilmiş tahmin ver.
- Operatör düzeltmesi varsa DÜZELTİLMİŞ hâli esas al
- guven_sinirlari alanında neyi bilemeyeceğini açıkça yaz

Sadece JSON döndür."""


class RootCauseReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    what_happened: str = Field(max_length=800)
    probable_root_cause: str = Field(max_length=600)
    actions_taken: list[str] = Field(default_factory=list)
    prevention_recommendations: list[str] = Field(default_factory=list)
    confidence_limits: str = Field(max_length=400)


def _section(baslik: str, lines: list[str]) -> list[str]:
    return [f"\n{baslik}:", *(lines or ["- (yok)"])]


def _prompt(store) -> str:
    episodes = store.episodes()
    parts: list[str] = []

    parts += _section("OLAY ZİNCİRİ", [
        f"- {e.start_ts:.0f}s [{e.phase}] {e.summary_tr}" for e in episodes])

    parts += _section("RİSK DEĞERLENDİRMELERİ", [
        f"- {r.level}: {r.rationale_tr}" for r in store.risks()])

    corrections = [d for e in episodes if e.id
                   for d in store.corrections(e.id)]
    parts += _section("OPERATÖR DÜZELTMELERİ", [
        f"- {d.field}: '{d.old}' yerine '{d.new}' ({d.rationale})"
        for d in corrections])

    parts += _section("AKSİYON DEFTERİ", [
        f"- {a.tool_name}({a.params}) → {a.result} [{a.approval}]"
        for a in store.actions()])

    parts += _section("DİYALOG", [
        f"- {s.role}: {s.text}" for s in store.dialogue()])

    return "\n".join(parts)


def generate_root_cause_report(gw, store) -> RootCauseReport:
    response = gw.ask("main", [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _prompt(store)},
    ], schema=RootCauseReport)

    if response.degraded:
        return RootCauseReport(
            what_happened="Rapor katmanı yanıt vermiyor; ham olay zinciri kayıtlıdır.",
            probable_root_cause="Belirlenemedi.",
            confidence_limits="Rapor modeline ulaşılamadı.")
    try:
        return RootCauseReport(**json.loads(response.content))
    except Exception:  # noqa: BLE001
        return RootCauseReport(
            what_happened="Rapor üretilemedi; ham olay zinciri kayıtlıdır.",
            probable_root_cause="Belirlenemedi.",
            confidence_limits="Rapor yanıtı okunamadı.")
```

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_reporter.py -v
```
Beklenen: 7 passed

### 5. Commit

```bash
git add gozcu/agents/reporter.py tests/test_reporter.py
git commit -m "feat: root-cause reporter honouring corrections and stating limits"
```

## Doğrulama

```bash
uv run pytest tests/test_reporter.py -v
```
Beklenen: **7 passed**

## Takıldığında

Üveys'e yaz. **Bekleme** — bu sprintte bir saat, toplam kapasitenin yaklaşık %4'ü.
