# Görev 07 — Sentezleyici: kareler → epizot (`gozcu/agents/synthesizer.py`)

> ## ✅ TAMAMLANDI — 23 Ağustos 2026, `b2d8f08`
>
> **Sentezleyici indi.** `gozcu/agents/synthesizer.py` var,
> `tests/test_synthesizer.py` 26 test fonksiyonu / 30 durum ile yeşil. Bu
> dosyayı yeniden uygulama — aşağısı ne yapıldığının kaydı.
>
> **Sonraki göreve başlarken bilmen gerekenler**
> ([kararlar](#tamamlanma-notları-gelecek-görevleri-bağlayan) bölümüne bak):
> `close_episode` açık epizot yokken **hiçbir şey yapmıyor** — ne epizot, ne
> devir teslim, ne geri çağrı, ne de model çağrısı; **özet doğrulamadan önce
> kesiliyor** (600 karakter, çünkü `maxLength` artık tele çıkmıyor); ve
> bozulmuş / boş / okunamayan yanıt için **üç ayrı** geri düşüş metni var.

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
| `close_episode` | Açık epizot `state="closed"`, `end_ts` set edilir, ve **gömme geri çağrısı** tetiklenir. **Açık epizot yoksa hiçbir şey yapılmaz** — epizot da devir de geri çağrı da yok |

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

**`Interpretation.observation_ts` pencerenin ORTA zaman damgası (Görev 04).**
`window[0].ts` değil — adaptör pencereden üç kare (ilk / orta / son) alıyor ve
kaydı ortanın anına yazıyor. Yorumu pencereye geri eşleyen her kod ilkini
varsayarsa yanlıştır; epizodun `start_ts`'i ayrı bir şey ve o `window[0].ts`
olmaya devam ediyor.

**Şema sertleştirmesi (Görev 03/04).** Şema sertleştirmesi **gateway'in içinde**. `Gateway.ask()`'e düz bir pydantic
modeli ver; `strict_schema()`'i kimse elle çağırmıyor. Sonucu: `maxLength`,
`minimum`/`maximum` ve `pattern` artık tele hiç çıkmıyor — yani **her ajan
doğrulamadan ÖNCE kendi değerlerini temizlemek zorunda**. Ayrıca `ask()` şemalı
istek tükendiğinde şemasız bir son deneme yapıyor, dolayısıyla dönen içerik iyi
biçimli JSON olmayabilir; ayrıştırıcılar bunu varsaymamalı.

Burada somut karşılığı: `_SynthesisResponse.summary_tr`'nin 600 karakterlik
sınırı modele hiç gitmiyor. `_SynthesisResponse(**…)` çağrılmadan **önce**
`summary_tr` 600'e kesilecek — kesilmezse modelin uzun bir özeti doğrulama
hatasına düşer ve gerçek bir epizot sentezi kabuğa çöker.

## Ne yapacaksın

```python
synthesize(gw, store, window, interpretation, decision, on_close=None) -> Episode | None
```

`decision` ∈ `{"open_episode", "update_episode", "close_episode"}`.
`on_close` verilirse ve karar `close_episode` ise `on_close(episode)` çağrılır.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_synthesizer.py`

```python
"""Sentezleyicinin testleri — dağınık pencereler tek bir epizota dönüşüyor mu.

Sahte gateway bilerek `Mock()` değil: bu depoda yedi kusur şekilsiz bir
`Mock()` collaborator'ın arkasında saklandı. `_FakeGateway` hangi kademeye,
hangi mesajlarla ve hangi şemayla gidildiğini kaydeder ve gerçek bir
`Response` döndürür — böylece "modele ne gitti" sorusu test edilebilir bir
soru oluyor.
"""

import json

import pytest

from gozcu.agents.router import mmss
from gozcu.agents.synthesizer import (DEGRADED_SUMMARY, EMPTY_SUMMARY, PHASES,
                                      SYSTEM_PROMPT, UNREADABLE_SUMMARY,
                                      _SynthesisResponse, synthesize)
from gozcu.gateway import Response
from gozcu.models import Interpretation, Observation, Signals
from gozcu.store import Store

RESPONSE_JSON = json.dumps({
    "phase": "development",
    "summary_tr": "İstif aracı devrildi, yerde hareketsiz kişi var.",
    "participants": ["istif aracı", "personnel"],
    "preliminary_risk": "Kritik"}, ensure_ascii=False)


class _FakeGateway:
    """Şekilli sahte: `Gateway.ask` imzasını birebir taşır ve kaydeder."""

    def __init__(self, response: Response | None = None) -> None:
        self.response = response if response is not None else Response(
            content=RESPONSE_JSON, model="fast-test")
        self.calls: list[dict] = []

    def ask(self, tier, messages, schema=None, tools=None,
            max_tokens=None, temperature=None) -> Response:
        self.calls.append({"tier": tier, "messages": messages,
                           "schema": schema, "tools": tools,
                           "max_tokens": max_tokens,
                           "temperature": temperature})
        return self.response

    @property
    def last(self) -> dict:
        assert self.calls, "gateway hiç çağrılmadı"
        return self.calls[-1]

    @property
    def user_content(self) -> str:
        return self.last["messages"][-1]["content"]


class _Embedder:
    """Görev 08'in gömme geri çağrısının şekli: epizodu alır, kaydeder.

    Şekilsiz bir `list.append` stub'ı geri çağrının epizodu gerçekten aldığını
    kanıtlamıyordu; bu sahte, teslim edilen epizodun kimliğini ve durumunu
    tutuyor.
    """

    def __init__(self) -> None:
        self.seen: list[tuple[int, str, str]] = []

    def __call__(self, episode) -> None:
        self.seen.append((episode.id, episode.state, episode.summary_tr))


def _window(start: float = 0.0, count: int = 10) -> list[Observation]:
    return [Observation(ts=float(start + t), signals=Signals(person_count=1))
            for t in range(count)]


def _gateway() -> _FakeGateway:
    return _FakeGateway()


# --- epizot yaşam döngüsü -------------------------------------------------

def test_open_merges_a_window_into_one_episode():
    store = Store(":memory:")
    interpretation = Interpretation(observation_ts=3.0,
                                    description="araç yan yattı", model="m")
    episode = synthesize(_gateway(), store, _window(), interpretation,
                         "open_episode")
    assert episode.start_ts == 0.0 and episode.end_ts == 9.0
    assert episode.preliminary_risk == "Kritik"
    assert episode.phase == "development"
    assert episode.participants == ["istif aracı", "personnel"]
    assert len(store.episodes()) == 1


def test_update_extends_the_open_episode_instead_of_opening_a_new_one():
    store = Store(":memory:")
    synthesize(_gateway(), store, _window(0), None, "open_episode")
    synthesize(_gateway(), store, _window(10), None, "update_episode")
    assert len(store.episodes()) == 1
    assert store.episodes()[0].end_ts == 19.0
    assert store.episodes()[0].start_ts == 0.0


def test_close_closes_the_open_episode_and_does_not_open_a_new_one():
    store = Store(":memory:")
    synthesize(_gateway(), store, _window(0), None, "open_episode")
    synthesize(_gateway(), store, _window(10), None, "close_episode")
    assert len(store.episodes()) == 1
    episode = store.episodes()[0]
    assert episode.state == "closed" and episode.end_ts == 19.0
    assert episode.phase == "outcome"
    assert store.open_episode() is None


def test_update_without_an_open_episode_opens_one():
    """Yönlendirici açık epizot yokken de `update_episode` diyebiliyor
    (Görev 06 notu) ve döngü boş depoda bunu düzeltmiyor — kaynaşacak bir şey
    yoksa kayıt düşmesin diye epizot açılır."""
    store = Store(":memory:")
    episode = synthesize(_gateway(), store, _window(), None, "update_episode")
    assert episode is not None and len(store.episodes()) == 1
    assert episode.state == "open"


# --- hayalet epizot: kapanacak bir şey yoksa hiçbir şey yazılmaz ----------

def test_close_without_an_open_episode_writes_nothing():
    store = Store(":memory:")
    gateway = _gateway()
    assert synthesize(gateway, store, _window(), None, "close_episode") is None
    assert store.episodes() == []
    assert store.handoffs() == []
    assert gateway.calls == [], "kapanacak epizot yokken modele hiç gidilmemeli"


def test_close_without_an_open_episode_does_not_fire_the_callback():
    store, embedder = Store(":memory:"), _Embedder()
    synthesize(_gateway(), store, _window(), None, "close_episode",
               on_close=embedder)
    assert embedder.seen == []


def test_two_consecutive_closes_leave_exactly_one_episode():
    """Yönlendirici üst üste iki `close_episode` verebilir ve `_resolve()`
    yalnızca `open_episode`'u indirir — ikincisi hayalet bir olay yazmamalı."""
    store = Store(":memory:")
    synthesize(_gateway(), store, _window(0), None, "open_episode")
    synthesize(_gateway(), store, _window(10), None, "close_episode")
    synthesize(_gateway(), store, _window(20), None, "close_episode")
    assert len(store.episodes()) == 1
    assert store.episodes()[0].end_ts == 19.0


# --- gömme geri çağrısı ---------------------------------------------------

def test_close_triggers_the_embedding_callback():
    store, embedder = Store(":memory:"), _Embedder()
    opened = synthesize(_gateway(), store, _window(0), None, "open_episode",
                        on_close=embedder)
    assert embedder.seen == [], "açılış gömme tetiklememeli"
    synthesize(_gateway(), store, _window(10), None, "close_episode",
               on_close=embedder)
    assert len(embedder.seen) == 1
    episode_id, state, summary = embedder.seen[0]
    assert episode_id == opened.id
    assert state == "closed"
    assert summary == store.episodes()[0].summary_tr


def test_close_works_without_a_callback():
    store = Store(":memory:")
    synthesize(_gateway(), store, _window(0), None, "open_episode")
    episode = synthesize(_gateway(), store, _window(10), None, "close_episode")
    assert episode.state == "closed"


# --- tek açık epizot değişmezinin bekçisi döngüde, burada değil -----------

def test_open_episode_always_creates_even_with_one_already_open():
    """`DecisionLoop._resolve()` açık epizot varken `open_episode`'u
    `update_episode`'a indiriyor; bu ancak `open_episode` KOŞULSUZ açtığı için
    işe yarıyor. Bekçi döngü, sentezleyici değil — bu test o iş bölümünü
    belgeliyor."""
    store = Store(":memory:")
    synthesize(_gateway(), store, _window(0), None, "open_episode")
    synthesize(_gateway(), store, _window(10), None, "open_episode")
    assert len(store.episodes()) == 2


# --- modele ne gidiyor ----------------------------------------------------

def test_synthesize_uses_the_fast_tier_not_the_large_one():
    gateway = _gateway()
    synthesize(gateway, Store(":memory:"), _window(), None, "open_episode")
    assert gateway.last["tier"] == "fast"


def test_schema_goes_to_the_gateway_as_a_plain_pydantic_model():
    """Sertleştirmeyi `Gateway.ask()` yapıyor (Görev 03); ajan `strict_schema`
    çağırmıyor, düz modeli veriyor."""
    gateway = _gateway()
    synthesize(gateway, Store(":memory:"), _window(), None, "open_episode")
    assert gateway.last["schema"] is _SynthesisResponse


def test_the_interpretation_reaches_the_model():
    """Görsel yorumun kaynaşması bu görevin bütün sebebi. Yorumu prompt'a
    koyan satırlar silinirse bu test kırmızıya döner."""
    gateway = _gateway()
    interpretation = Interpretation(
        observation_ts=5.0, model="vlm-test",
        description="istif aracı yan yattı, forkliftin altında kişi var")
    synthesize(gateway, Store(":memory:"), _window(), interpretation,
               "open_episode")
    assert interpretation.description in gateway.user_content


def test_the_interpretation_is_stamped_with_its_own_observation_ts():
    """`Interpretation.observation_ts` pencerenin ORTA damgası (Görev 04);
    yorumu `window[0].ts` ile damgalayan kod yalan söyler."""
    gateway = _gateway()
    interpretation = Interpretation(observation_ts=5.0, model="vlm-test",
                                    description="araç yan yattı")
    synthesize(gateway, Store(":memory:"), _window(), interpretation,
               "open_episode")
    visual = next(line for line in gateway.user_content.splitlines()
                  if interpretation.description in line)
    assert visual.startswith(mmss(5.0))


def test_the_open_episode_summary_is_given_to_the_model_on_update():
    """Kaynaşma bağlam istiyor: devam eden olayın özeti gitmezse model her
    pencereyi sıfırdan anlatır ve süreklilik kaybolur."""
    store = Store(":memory:")
    synthesize(_gateway(), store, _window(0), None, "open_episode")
    gateway = _gateway()
    synthesize(gateway, store, _window(10), None, "update_episode")
    assert store.episodes()[0].summary_tr in gateway.user_content


def test_the_prompt_spells_the_schema_enums_byte_for_byte():
    """CLAUDE.md: bir prompt enum sayıyorsa değerler şemadakiyle birebir aynı
    olmalı. Bunlar bir kez ayrıştı ve sistem sessizce öldü."""
    for phase in PHASES:
        assert phase in SYSTEM_PROMPT
    for level in ("Düşük", "Orta", "Yüksek", "Kritik"):
        assert level in SYSTEM_PROMPT


# --- bozulmuş ve bozuk yanıtlar -------------------------------------------

def test_degraded_fast_tier_still_produces_an_episode():
    """Bozulmuş yanıt geçerli JSON taşısa bile içeriği okunmamalı: bir gün
    bayat bir gövdeyle gelirse (önbellek) o gövde canlı sentez sanılır."""
    gateway = _FakeGateway(Response(content=RESPONSE_JSON, degraded=True))
    store = Store(":memory:")
    episode = synthesize(gateway, store, _window(), None, "open_episode")
    assert episode is not None and len(store.episodes()) == 1
    assert episode.summary_tr == DEGRADED_SUMMARY
    assert episode.preliminary_risk == "Orta"


@pytest.mark.parametrize("content", ["", "   ", "\n"])
def test_empty_content_still_produces_an_episode(content):
    """Boş içerik "okunamadı" değil: kademe hiçbir şey söylemedi. `json.loads`
    ikisini de istisnaya çevirdiği için ayrımı guard yapıyor — denetim kaydı
    susmayı saçmalamadan ayırt edebilmeli."""
    gateway = _FakeGateway(Response(content=content, model="fast-test"))
    store = Store(":memory:")
    episode = synthesize(gateway, store, _window(), None, "open_episode")
    assert episode is not None and len(store.episodes()) == 1
    assert episode.summary_tr == EMPTY_SUMMARY


def test_prose_from_the_schemaless_retry_does_not_drop_the_episode():
    """`ask()` şemalı istek tükendiğinde şemasız bir son deneme yapıyor
    (Görev 03), yani içerik JSON olmayabilir."""
    gateway = _FakeGateway(Response(content="Elbette! İşte olay özeti:",
                                    model="fast-test"))
    episode = synthesize(gateway, Store(":memory:"), _window(), None,
                         "open_episode")
    assert episode is not None and episode.summary_tr == UNREADABLE_SUMMARY


@pytest.mark.parametrize("content", ['["development"]', "null", "42"])
def test_non_object_json_does_not_drop_the_episode(content):
    gateway = _FakeGateway(Response(content=content, model="fast-test"))
    episode = synthesize(gateway, Store(":memory:"), _window(), None,
                         "open_episode")
    assert episode is not None and episode.summary_tr == UNREADABLE_SUMMARY


def test_an_over_long_summary_is_trimmed_instead_of_collapsing_the_episode():
    """`maxLength` tele çıkmıyor (Görev 03), yani model 600'ü aşabilir. Ham
    hâliyle pydantic'e verilirse gerçek bir epizot kabuğa çöker."""
    long_summary = "İstif aracı devrildi ve yerde hareketsiz bir kişi var. " * 20
    assert len(long_summary) > 600
    gateway = _FakeGateway(Response(content=json.dumps(
        {"phase": "development", "summary_tr": long_summary,
         "participants": [], "preliminary_risk": "Kritik"},
        ensure_ascii=False), model="fast-test"))
    episode = synthesize(gateway, Store(":memory:"), _window(), None,
                         "open_episode")
    assert len(episode.summary_tr) <= 600
    assert episode.summary_tr != UNREADABLE_SUMMARY
    assert episode.summary_tr.startswith("İstif aracı devrildi")
    assert episode.preliminary_risk == "Kritik"


def test_an_unknown_phase_falls_back_to_development():
    gateway = _FakeGateway(Response(content=json.dumps(
        {"phase": "baslangic", "summary_tr": "kısa özet",
         "participants": [], "preliminary_risk": "Orta"},
        ensure_ascii=False), model="fast-test"))
    episode = synthesize(gateway, Store(":memory:"), _window(), None,
                         "open_episode")
    assert episode.phase == "development"
    assert episode.summary_tr == "kısa özet", "faz düzeltmesi özeti düşürmemeli"


def test_an_invalid_risk_level_does_not_drop_the_episode():
    gateway = _FakeGateway(Response(content=json.dumps(
        {"phase": "onset", "summary_tr": "kısa özet",
         "participants": [], "preliminary_risk": "Critical"},
        ensure_ascii=False), model="fast-test"))
    episode = synthesize(gateway, Store(":memory:"), _window(), None,
                         "open_episode")
    assert episode is not None and episode.preliminary_risk == "Orta"


# --- boş pencere ----------------------------------------------------------

def test_an_empty_window_produces_nothing():
    store = Store(":memory:")
    gateway = _gateway()
    assert synthesize(gateway, store, [], None, "open_episode") is None
    assert store.episodes() == [] and store.handoffs() == []
    assert gateway.calls == []


# --- devir teslim ---------------------------------------------------------

def test_synthesize_records_a_handoff_to_the_risk_analyst():
    store = Store(":memory:")
    synthesize(_gateway(), store, _window(), None, "open_episode")
    handoff = store.handoffs()[-1]
    assert handoff.source_agent == "synthesizer"
    assert handoff.target_agent == "risk_analyst"
    assert handoff.payload_ref == f"episode:{store.episodes()[0].id}"


def test_the_handoff_carries_the_current_window_not_the_episode_start():
    """Devir teslim defterinin saati epizot boyunca donmamalı: `start_ts`
    kullanılırsa uzun bir olayın bütün devirleri ilk pencereye damgalanır."""
    store = Store(":memory:")
    synthesize(_gateway(), store, _window(0), None, "open_episode")
    synthesize(_gateway(), store, _window(30), None, "update_episode")
    assert store.episodes()[0].start_ts == 0.0
    assert store.handoffs()[-1].ts == 30.0
```

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_synthesizer.py -v
```
Beklenen: `ModuleNotFoundError`

### 3. `gozcu/agents/synthesizer.py` yaz

```python
"""Sentezleyici — kare bağımsızlığının kırıldığı yer.

Bir pencerenin dağınık sinyalleri ve o pencerenin görsel yorumu tek bir
`Episode` kaydında birleşiyor: hangi fazda, kimler var, Türkçe özeti ne, ön
riski ne. Şartnamenin "sahne bütünlüğü, zamansal ilişkiler ve olay akışı"
maddesi ile "başlangıç / gelişim / sonuç" ayrımı burada karşılanıyor.

Epizot yaşam döngüsünün üç kararı üç ayrı davranış:

- `open_episode`   → **koşulsuz** yeni epizot açar
- `update_episode` → `store.open_episode()` üzerine kaynaşır (açık epizot
  yoksa yeni bir tane açar — bkz. `synthesize` içindeki asimetri notu)
- `close_episode`  → açık epizodu kapatır; **açık epizot yoksa hiçbir şey
  yapmaz**

İlk ikisinin koşulsuzluğu tesadüf değil: tek açık epizot değişmezinin bekçisi
`DecisionLoop._resolve()` ve o, açık epizot varken gelen `open_episode`'u
`update_episode`'a indirerek çalışıyor. Sentezleyici bu iş bölümünü bozarsa
değişmez de bozulur (Görev 05 notu).
"""

import json

from pydantic import BaseModel, ConfigDict, Field

from gozcu.agents.interpreter import _sanitize_text
from gozcu.agents.router import mmss
from gozcu.models import (Episode, Handoff, Interpretation, Observation,
                          RiskLevel)

# `Episode.summary_tr` ile aynı sınır. Şema sertleştirmesi `maxLength`'i telden
# söküyor (bkz. `gozcu.gateway.strict_schema`), yani model bu sınırı aşabilir;
# kesme doğrulamadan ÖNCE Python tarafında yapılıyor.
MAX_SUMMARY = 600

PHASES = ("onset", "development", "outcome")

SYSTEM_PROMPT = """Sen bir fabrika kontrol odasının kâtibisin. Sana bir zaman
aralığındaki gözlemler ve görsel yorumlar verilir. Bunları TEK BİR OLAY
halinde birleştir.

Kurallar:
- Olayın hangi fazda olduğunu belirt — tam olarak bu değerlerden biri:
  onset (olayın başlangıcı), development (olayın gelişimi), outcome (olayın
  sonucu)
- Özet Türkçe, kısa cümlelerle, saha terminolojisiyle yazılır
- Görmediğin bir şeyi yazma. Emin değilsen "olası" de.
- Ön riski şu dördünden biri olarak ver: Düşük, Orta, Yüksek, Kritik

Sadece JSON döndür."""

# Yedek özetler. Üçü bilerek farklı: denetim kaydı ve konsol "kademe sustu",
# "kademe boş yanıt döndü" ve "yanıt okunamadı" ayrımını görebilmeli — üçü
# farklı arızalar ve farklı müdahale gerektiriyor. Aynı metni paylaşsalardı
# boş içerik guard'ı da sessizce ölü koda dönerdi: `json.loads("")` zaten
# istisna atıp okunamayan dala düşüyor ve fark hiçbir yerde görünmüyordu.
DEGRADED_SUMMARY = "Sentez katmanı yanıt vermiyor; ham gözlemler kayıtlı."
EMPTY_SUMMARY = "Sentez katmanı boş yanıt döndürdü; ham gözlemler kayıtlı."
UNREADABLE_SUMMARY = "Sentez üretilemedi; ham gözlemler kayıtlı."
FALLBACK_PHASE = "development"
FALLBACK_RISK: RiskLevel = "Orta"


class _SynthesisResponse(BaseModel):
    """Hızlı kademeden beklenen çıktı.

    `phase` bilerek `str` — `Literal` olsaydı modelin uydurduğu bir faz bütün
    kaydı doğrulama hatasına düşürürdü; burada okunup `PHASES`'e çekiliyor.
    Uzunluk sınırı modelde kalır, şemadan çıkar (bkz. `strict_schema`).
    """

    model_config = ConfigDict(extra="forbid")

    phase: str
    summary_tr: str = Field(max_length=MAX_SUMMARY)
    participants: list[str] = Field(default_factory=list)
    preliminary_risk: RiskLevel


def _fallback(summary_tr: str) -> _SynthesisResponse:
    """Sentez okunamadığında pencere yine de bir epizota dönüşür.

    Boş dönmek pencereyi tamamen kaybetmek demek: ham gözlemler depoda kalır
    ama şartnamenin `events[]` listesinde o an hiç yaşanmamış görünür.
    """
    return _SynthesisResponse(phase=FALLBACK_PHASE, summary_tr=summary_tr,
                              preliminary_risk=FALLBACK_RISK)


def _digest(window: list[Observation],
            interpretation: Interpretation | None,
            previous: Episode | None) -> str:
    """Modele gidecek düz metin — gözlem başına bir satır.

    Görsel yorum kendi zaman damgasıyla ekleniyor: `Interpretation.observation_ts`
    pencerenin ORTA damgası, `window[0].ts` değil (Görev 04). Devam eden bir
    olay varsa özeti en başa konuyor ki model her pencereyi sıfırdan
    anlatmasın — kaynaşmanın süreklilik tarafı bu satıra bağlı.
    """
    lines = [f"{mmss(observation.ts)} "
             f"kişi={observation.signals.person_count} "
             f"hızlar={observation.signals.velocities or '-'}"
             for observation in window]
    if interpretation is not None:
        lines.append(f"{mmss(interpretation.observation_ts)} GÖRSEL: "
                     f"{interpretation.description}")
    if previous is not None:
        lines.insert(0, f"DEVAM EDEN OLAY: {previous.summary_tr}")
    return "\n".join(lines)


def _parse(content: str) -> _SynthesisResponse | None:
    """Modelin ham çıktısını doğrulanmış bir yanıta çevirir; olmazsa `None`.

    İçeriğin iyi biçimli JSON olduğu varsayılmıyor: `ask()` şemalı istek
    tükendiğinde şemasız bir son deneme yapıyor (Görev 03), dolayısıyla geri
    düz metin de gelebilir.

    Kesme doğrulamadan ÖNCE: şemada `maxLength` olmadığı için model 600'ü
    aşabilir ve ham hâliyle pydantic'e verilirse gerçek bir epizot sentezi
    kabuğa çökerdi. Kesme mantığı yorumlayıcıdan geliyor — sarkan yarım
    kelimeyi de buduyor.
    """
    try:
        data = json.loads(content)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    summary = data.get("summary_tr")
    if isinstance(summary, str):
        data["summary_tr"] = _sanitize_text(summary, MAX_SUMMARY)

    try:
        parsed = _SynthesisResponse(**data)
    except Exception:  # noqa: BLE001 — bozuk çıktı bir koşuyu düşürmemeli
        return None

    if parsed.phase not in PHASES:
        parsed.phase = FALLBACK_PHASE
    return parsed


def _ask_synthesis(gw, window: list[Observation],
                   interpretation: Interpretation | None,
                   previous: Episode | None) -> _SynthesisResponse:
    """Hızlı kademeye sorar; okunamayan her şey yedek özete düşer.

    İki guard da açık. Bozulmuş yanıt bir gün boş olmayan bir gövdeyle
    gelirse (ör. önbellekten dönen bayat sentez) `degraded` kontrolü olmadan
    o bayat özet canlı sentez gibi kaydedilir; boş içerik ise `json.loads("")`
    tesadüfen istisna attığı için "okunamadı" diye raporlanırdı — kademe
    aslında hiçbir şey söylememişken.
    """
    response = gw.ask("fast", [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _digest(window, interpretation, previous)},
    ], schema=_SynthesisResponse)

    if response.degraded:
        return _fallback(DEGRADED_SUMMARY)
    if not (response.content or "").strip():
        return _fallback(EMPTY_SUMMARY)

    parsed = _parse(response.content)
    return parsed if parsed is not None else _fallback(UNREADABLE_SUMMARY)


def synthesize(gw, store, window: list[Observation],
               interpretation: Interpretation | None,
               decision: str, on_close=None) -> Episode | None:
    """Gözlem penceresini bir `Episode`'a dönüştürür.

    `decision == "open_episode"`   → koşulsuz yeni epizot
    `decision == "update_episode"` → açık epizota kaynaşır
    `decision == "close_episode"`  → açık epizodu kapatır ve varsa
    `on_close(episode)` çağrılır (gömme geri çağrısı, Görev 08).

    Açık epizot yokken gelen karar iki farklı şey demek — **iki dal bilerek
    ayrı:**

    - `update_episode`: döngü depo boşken de kaynaşma yönlendirebiliyor
      (Görev 06 notu: prompt yasaklıyor ama hiçbir şey düzeltmiyor). Kaynaşacak
      bir şey yoksa pencereyi kaybetmektense epizot AÇILIR.
    - `close_episode`: kapanacak bir şey yok. Burada epizot üretmek tam olarak
      **yaşanmamış bir olay uydurmak** olur — üstelik `state="closed"` ile,
      yani doğrudan şartnamenin `events[]` listesine ve Görev 08'in gömme
      hafızasına. Üst üste iki kapanış kararı (`_resolve()` yalnızca
      `open_episode`'u indiriyor) tam olarak bunu üretiyordu. Bu dal
      NO-OP: ne epizot, ne devir teslim, ne geri çağrı, ne de model çağrısı.

    İki dalı "sadeleştirip" birleştirmek hayalet epizot hatasını geri getirir.
    """
    if not window:
        return None

    open_episode = store.open_episode() if decision != "open_episode" else None
    if decision == "close_episode" and open_episode is None:
        return None

    synthesis = _ask_synthesis(gw, window, interpretation, open_episode)
    closing = decision == "close_episode"
    end_ts = window[-1].ts

    if open_episode is None:
        episode = Episode(start_ts=window[0].ts, end_ts=end_ts,
                          phase=synthesis.phase,
                          summary_tr=synthesis.summary_tr,
                          participants=synthesis.participants,
                          preliminary_risk=synthesis.preliminary_risk,
                          state="open")
        episode.id = store.create_episode(episode)
    else:
        fields = {"end_ts": end_ts, "summary_tr": synthesis.summary_tr,
                  "participants": synthesis.participants,
                  "preliminary_risk": synthesis.preliminary_risk,
                  "phase": "outcome" if closing else synthesis.phase}
        if closing:
            fields["state"] = "closed"
        store.update_episode(open_episode.id, **fields)
        episode = next(e for e in store.episodes() if e.id == open_episode.id)

    # Devir teslimin saati GEÇERLİ pencerenin ilk damgası, epizodun `start_ts`'i
    # değil: uzun bir olayda ikincisi defterin saatini olayın başında dondurur
    # ve zaman çizelgesi (Görev 15/16) devirleri yanlış ana yazar.
    store.save_handoff(Handoff(ts=window[0].ts,
                               source_agent="synthesizer",
                               target_agent="risk_analyst",
                               reason=f"{decision} → episode {episode.id}",
                               confidence=0.8,
                               payload_ref=f"episode:{episode.id}"))

    if closing and on_close is not None:
        on_close(episode)

    return episode
```

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_synthesizer.py -v
```
Beklenen: 30 passed

### 5. Commit

```bash
git add gozcu/agents/synthesizer.py tests/test_synthesizer.py
git commit -m "feat: synthesizer with no-op close and sanitised summaries"
```

## Doğrulama

```bash
uv run pytest tests/test_synthesizer.py -v
```
Beklenen: **30 passed**

## Takvim kaydıysa

> **Konusuz kaldı:** görev 23 Ağustos'ta tamamlandı, kesilmedi. Aşağısı o gün
> verilmiş kesme planının kaydı.

Bu görev, 24 Ağustos gecikirse **entegrasyondan önce kesilecek** olan görevdi.
Kesilirse yerine sinyallerden şablon epizot üret (`f"{kisi} kişi, {hiz} hız"`) —
kaba olur ama uçtan uca akış ayakta kalır. Bir arada çalışmayan altı modül,
kaba epizotlu çalışan bir sistemden kötüdür.

## Tamamlanma notları (gelecek görevleri bağlayan)

- **Üç kararın iş bölümü, tek açık epizot değişmezini ayakta tutan şey.**
  `open_episode` **koşulsuz** yeni epizot açar; `update_episode`
  `store.open_episode()` üzerine kaynaşır (açık epizot yoksa yeni bir tane
  açar); `close_episode` açık epizot yokken **hiçbir şey yapmaz**. İlk ikisinin
  koşulsuz olması, bekçiliğin tek bir yerde — `DecisionLoop._resolve()` içinde
  ([Görev 05](05-karar-dongusu.md)) — toplanmasını mümkün kılıyor. Bu asimetri
  bozulursa değişmez de bozulur.
- **Kapanışın no-op olması bir hata düzeltmesi, sadeleştirme değil.** Önceden
  açık epizot yokken gelen bir `close_episode`, uydurma bir özetle
  `state="closed"` tam bir epizot yaratıyor, devir teslim defterine kayıt
  düşüyor ve gömme geri çağrısını tetikliyordu — doğrudan şartnamenin
  `events[]` listesine yazılan bir hayalet olay. `_resolve()` yalnızca
  `open_episode`'u indirdiği için, yönlendiriciden üst üste gelen iki kapanış
  kararı tam olarak bunu üretiyordu. İki dalı birleştirmek hatayı geri getirir.
- **`on_close` tam bir kez ve DEPOYA YAZILMIŞ kapalı epizotla çağrılıyor:**
  gerçek `id`, `state="closed"`, tazelenmiş `summary_tr`. [Görev
  08](08-hafiza.md) gömme satırını `episode.id` üzerine anahtarlayabilir.
- **`on_close` istisna atmamalı.** `synthesize`'ın içinden çağrılıyor; oradan
  kaçan bir istisna, zaten başarılı olmuş bir epizot yazımını ve devir teslimi
  birlikte götürür. Geri çağrıyı bağlayan taraf onu kendi içinde sarmak zorunda.
- **Temizlik doğrulamadan önce.** `summary_tr` `_SynthesisResponse`'a
  verilmeden önce `MAX_SUMMARY` (600) sınırına kesiliyor: `maxLength` artık
  tele çıkmıyor ([Görev 06](06-yonlendirici.md)) ve orada patlayacak bir
  `ValidationError` gerçek bir epizodu çöpe atardı.
- **Üç ayrı geri düşüş özeti — `DEGRADED_SUMMARY`, `EMPTY_SUMMARY`,
  `UNREADABLE_SUMMARY`.** Metinler bilerek farklı: üç farklı arıza ve denetim
  defteri bunları ayırt edebilmeli. Tek metne indirilirse guard'lar test
  edilemez hale gelir — boş içerik guard'ı tam bu yüzden bir süre sessizce
  taşıyıcı olmayan koddu.
- **`Handoff.ts` GEÇERLİ pencerenin ilk damgası, `episode.start_ts` değil.**
  İkincisi kullanılırsa devir teslim defterinin saati epizodun ömrü boyunca
  donar ve Görev 15/16 zaman çizelgeleri devirleri yanlış ana yazar.
- **`Episode.start_ts` güncellemeler boyunca ilk pencerenin damgası olarak
  kalıyor; `Interpretation.observation_ts` ise pencerenin ORTA damgası**
  ([Görev 04](04-yorumlayici.md)). İkisini aynı sanan kod yalan söyler.
