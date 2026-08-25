# Görev 06 — Yönlendirici ajanı (`gozcu/agents/router.py`)

> ## ✅ TAMAMLANDI — 23 Ağustos 2026, `768635d`
>
> **Yönlendirici indi.** `gozcu/agents/router.py` var, `tests/test_router.py`
> 15 test fonksiyonu / 17 durum ile yeşil. Bu dosyayı yeniden uygulama —
> aşağısı ne yapıldığının kaydı.
>
> **Sonraki göreve başlarken bilmen gerekenler**
> ([kararlar](#tamamlanma-notları-gelecek-görevleri-bağlayan) bölümüne bak):
> modül `gozcu/agents/router.py` ve **`mmss` oradan import ediliyor** — Görev
> 07 (ve 14, 17) tek kopyayı buradan alıyor; `mmss` **`"99:59"`de tavana
> oturuyor**, saat devri yok; ve **şema sertleştirmesi artık gateway'in
> içinde** — `strict_schema()`'i hiçbir çağıran elle çağırmıyor, ama bunun
> bedeli her ajanın kendi değerlerini doğrulamadan önce temizlemesi.

**Bağımlılık:** [01](01-sozlesme.md), [03](03-gateway.md)

## Bağlam

Sistemin **dikkat mekanizması.** 10 saniyelik pencerelerin sinyal özetine bakıp
"burada dikkat gerektiren bir şey var mı, varsa kime gider" kararını veriyor.

İki tasarım kararı önemli:

**Görüntü görmüyor.** Sadece yapılandırılmış sinyal özeti alıyor. 8B'lik bir
modelin yetmesinin ve hızlı olmasının sebebi bu — kararların büyük çoğunluğu
burada, en ucuz modelde kapanıyor. Slayta giden manşet sayı da bu:
*"kararların %89'u en küçük modelde kapandı."*

**Tetikleyicinin model kararı olması kasıtlı.** Şartname *"sabit kurallara
dayalı basit bir pipeline yerine ... model tabanlı karar mekanizmaları içeren
bir mimari"* istiyor. Sinyal eşiği yerine model kararı koymak bunun doğrudan
kanıtı.

## Kurulum

```bash
uv sync --extra dev
uv run pytest tests/test_gateway.py -v      # Görev 03 yeşil olmalı
```

## Bağımlı olduğun imzalar

```python
# gozcu/gateway.py
Gateway.ask(tier, messages, schema=None, tools=None,
            max_tokens=None, temperature=None) -> Response   # kademe pozisyonel
Response(content, tool_calls, model, latency_ms, tokens, degraded)

# gozcu/models.py
Observation(id, ts, detections, signals)
Signals(velocities: dict[int, float], vanished_tracks: list[int],
          person_count: int, person_count_delta: int, gathering: bool)
RouterDecision(decision, rationale, confidence)
```

**Bozulmuş yanıt guard'ı (Görev 03).** `router` kademesi artık kesintide
`GatewayError` atmıyor, **bozuluyor**: `content=""`, `tool_calls=[]`,
`degraded=True` bir `Response` dönüyor. Yani aşağıdaki bozulma dalı mock'a özel
bir kurgu değil, canlı yol — `response.degraded` bayrağına bakıp `ignore`'a
düşecek ve JSON ayrıştırmayı boş içeriğe karşı koruyacaksın. `except
GatewayError` kesinti işleme **değildir**: o istisna artık sadece kademe adı
yanlış yazıldığında fırlar.

**Şema sertleştirmesi gateway'in içinde (Görev 03/04).** `Gateway.ask()`'e düz
bir pydantic modeli ver; `strict_schema()`'i kimse elle çağırmıyor. Sonucu:
`maxLength`, `minimum`/`maximum` ve `pattern` artık tele hiç çıkmıyor — yani
**her ajan doğrulamadan ÖNCE kendi değerlerini temizlemek zorunda**. Ayrıca
`ask()` şemalı istek tükendiğinde şemasız bir son deneme yapıyor, dolayısıyla
dönen içerik iyi biçimli JSON olmayabilir; ayrıştırıcılar bunu varsaymamalı.

Burada bu iki alanı vuruyor: `RouterDecision.rationale` (200 karakter) ve
`RouterDecision.confidence` (0..1). Model ikisini de aşabilir; ham hâliyle
pydantic'e verilen bir `escalate` doğrulama hatasında `ignore`'a çöker.

## Ne yapacaksın

```python
mmss(ts: float) -> str                                    # 192.0 -> "03:12"
window_digest(window: list[Observation]) -> str
route(gw, window: list[Observation], has_open_episode: bool) -> RouterDecision
```

`mmss` burada tanımlanıp Görev 07, 14 ve 17 tarafından import ediliyor — tek
kopya olsun.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_router.py`

```python
"""Yönlendirici ajanının testleri.

Sahte gateway bilerek `Mock()` değil. Görev dosyasının testleri `Mock()`
kullanıyordu ve hiçbiri `schema=` geçilip geçilmediğine bakmıyordu: `schema`
argümanını tamamen silmek altı testi de yeşil bırakıyordu — sertleştirme
kusuru tam bu yüzden görünmez kaldı. `_FakeGateway` `Gateway.ask` imzasını
birebir taşır ve ne ile çağrıldığını kaydeder.
"""

import json
import re
from typing import get_args

import pytest

from gozcu.agents.router import (MAX_RATIONALE, SYSTEM_PROMPT, mmss, route,
                                 window_digest)
from gozcu.gateway import Response
from gozcu.models import EventSummary, Observation, RouterDecision

DECISION = '{"decision":"escalate","rationale":"araç devrildi","confidence":0.91}'


class _FakeGateway:
    """Şekilli sahte: kademe, mesajlar ve şema tek tek incelenebilir."""

    def __init__(self, response: Response | None = None) -> None:
        self.response = response if response is not None else Response(
            content=DECISION, model="router-test")
        self.calls: list[dict] = []

    def ask(self, tier, messages, schema=None, tools=None,
            max_tokens=None, temperature=None) -> Response:
        self.calls.append({"tier": tier, "messages": messages,
                           "schema": schema, "tools": tools})
        return self.response

    @property
    def last(self) -> dict:
        assert self.calls, "gateway hiç çağrılmadı"
        return self.calls[-1]


def _observation(ts, **signals) -> Observation:
    return Observation(ts=ts, signals=signals)


def _prompt_text(gateway: _FakeGateway) -> str:
    return gateway.last["messages"][-1]["content"]


# --- mmss -----------------------------------------------------------------

def test_mmss_formats_video_time():
    assert mmss(192.0) == "03:12" and mmss(0.0) == "00:00"


def test_mmss_clamps_instead_of_emitting_an_invalid_timestamp():
    """Saat devri yok: `mmss(6000)` düz hesapla "100:00" verir ve bu
    `EventSummary.time`'ın `^\\d{2}:\\d{2}$` desenini ihlal eder — Görev 17'de
    doğrulama hatası olur. Demo klipleri dakikalarla ölçülüyor, o yüzden saat
    desteği kapsam dışı; ama geçersiz bir damga da üretilmemeli."""
    assert mmss(6000.0) == "99:59"
    assert re.fullmatch(r"\d{2}:\d{2}", mmss(6000.0))
    EventSummary(time=mmss(6000.0), event="devrilme")


# --- window_digest --------------------------------------------------------

def test_digest_is_one_stamped_line_per_observation():
    """Görev dosyasının `"base64" not in digest` iddiası boştu — herhangi bir
    Türkçe metin geçiyordu. Asıl sözleşme şu: gözlem başına bir satır, başında
    zaman damgası, gövdesinde o gözlemin sinyalleri."""
    digest = window_digest([_observation(0.0, person_count=2, velocities={1: 3.4}),
                            _observation(61.0, vanished_tracks=[1])])
    lines = digest.splitlines()
    assert len(lines) == 2
    assert lines[0] == "00:00 kişi=2 hızlar=1:3.4"
    assert lines[1] == "01:01 kişi=0 kaybolan=[1]"


def test_digest_reports_the_remaining_signals():
    digest = window_digest([_observation(5.0, person_count=4,
                                         person_count_delta=3, gathering=True)])
    assert digest == "00:05 kişi=4 değişim=+3 toplanma"


def test_digest_of_an_empty_window_is_empty():
    assert window_digest([]) == ""


# --- prompt ---------------------------------------------------------------

def test_the_prompt_lists_exactly_the_schema_decision_values():
    """CLAUDE.md: bir prompt enum sayıyorsa değerleri şemadakiyle birebir aynı
    olmalı. Bu bir kez ayrıldı ve sistem sessizce ölü hâle geldi."""
    listed = re.findall(r"(?m)^- ([a-z_]+):", SYSTEM_PROMPT)
    assert listed == list(get_args(
        RouterDecision.model_fields["decision"].annotation))


def test_open_episode_state_reaches_the_prompt():
    gw = _FakeGateway()
    route(gw, [_observation(0.0)], has_open_episode=True)
    assert "Açık bir olay var" in _prompt_text(gw)


def test_closed_episode_state_reaches_the_prompt():
    gw = _FakeGateway()
    route(gw, [_observation(0.0)], has_open_episode=False)
    assert "Açık olay yok" in _prompt_text(gw)


# --- gateway'e giden istek ------------------------------------------------

def test_route_asks_the_router_tier_with_the_decision_schema():
    """Şemanın gerçekten geçildiğini kimse doğrulamıyordu; `schema=` silinince
    bütün takım yeşil kalıyordu."""
    gw = _FakeGateway()
    route(gw, [_observation(0.0, person_count=1)], has_open_episode=False)
    assert gw.last["tier"] == "router"
    assert gw.last["schema"] is RouterDecision
    assert gw.last["messages"][0]["role"] == "system"
    assert gw.last["messages"][0]["content"] == SYSTEM_PROMPT
    assert "00:00 kişi=1" in _prompt_text(gw)


def test_the_window_digest_reaches_the_prompt_not_an_image():
    gw = _FakeGateway()
    route(gw, [_observation(0.0, person_count=2)], has_open_episode=False)
    assert isinstance(_prompt_text(gw), str)
    assert window_digest([_observation(0.0, person_count=2)]) in _prompt_text(gw)


# --- karar ayrıştırma -----------------------------------------------------

def test_route_parses_the_model_decision():
    gw = _FakeGateway()
    decision = route(gw, [_observation(0.0, person_count=1)],
                     has_open_episode=False)
    assert decision.decision == "escalate" and decision.confidence == 0.91
    assert decision.rationale == "araç devrildi"


def test_unparseable_response_degrades_to_ignore_not_a_crash():
    gw = _FakeGateway(Response(content="model bugün konuşmuyor"))
    assert route(gw, [_observation(0.0)], has_open_episode=False).decision == "ignore"


def test_degraded_router_tier_degrades_to_ignore():
    """Görev dosyasının testi `Response(degraded=True)` kullanıyordu; onun
    `content`'i `""` olduğu için `json.loads("")` aynı yedeğe düşüyor ve
    `degraded` dalını tamamen silmek de testi geçiriyordu. Geçerli JSON taşıyan
    bozuk bir yanıt yalnızca gerçek bir `degraded` kontrolüyle `ignore` verir."""
    gw = _FakeGateway(Response(content=DECISION, degraded=True))
    decision = route(gw, [_observation(0.0)], has_open_episode=False)
    assert decision.decision == "ignore" and decision.confidence == 0.0


# --- modelin döndürdüğü değerlerin temizlenmesi ---------------------------

def test_over_long_rationale_is_truncated_not_dropped():
    """`maxLength` artık tele çıkmıyor (Görev 03 sertleştirmesi), yani model
    sınırı aşabilir. Ham hâliyle pydantic'e verilirse gerçek bir karar
    doğrulama hatasında `ignore`'a çöker."""
    gw = _FakeGateway(Response(content=json.dumps(
        {"decision": "escalate", "rationale": "a" * 500, "confidence": 0.9})))
    decision = route(gw, [_observation(0.0)], has_open_episode=False)
    assert decision.decision == "escalate"
    assert len(decision.rationale) == MAX_RATIONALE


@pytest.mark.parametrize("raw,clamped", [(1.7, 1.0), (-0.5, 0.0), (0.42, 0.42)])
def test_out_of_range_confidence_is_clamped_not_dropped(raw, clamped):
    gw = _FakeGateway(Response(content=json.dumps(
        {"decision": "inspect", "rationale": "kaynak sızıntısı", "confidence": raw})))
    decision = route(gw, [_observation(0.0)], has_open_episode=False)
    assert decision.decision == "inspect" and decision.confidence == clamped
```

Son üç blok göründüğünden önemli: bozuk JSON'da patlayan bir yönlendirici, tek
bir kötü yanıtta bütün koşuyu düşürür; sınır dışı bir değeri temizlemeyen bir
yönlendirici ise gerçek bir `escalate`'i sessizce `ignore`'a çevirir.

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_router.py -v
```
Beklenen: `ModuleNotFoundError`

### 3. `gozcu/agents/router.py` yaz

```python
"""Yönlendirici ajanı — sistemin dikkat mekanizması.

10 saniyelik bir pencerenin sinyal özetine bakıp "burada dikkat gerektiren bir
şey var mı, varsa kime gider" kararını veriyor. **Görüntü görmüyor:** yalnızca
yapılandırılmış sinyal özeti alıyor. Küçük ve hızlı bir modelin yetmesinin
sebebi bu — kararların büyük çoğunluğu burada, en ucuz kademede kapanıyor.

Tetikleyicinin sabit bir sinyal eşiği değil de model kararı olması kasıtlı:
şartname "sabit kurallara dayalı basit bir pipeline yerine ... model tabanlı
karar mekanizmaları içeren bir mimari" istiyor.

Tek açık epizot değişmezi burada DEĞİL, `DecisionLoop._resolve()`'da korunuyor:
prompt açık bir epizot varken `open_episode` demeyi bilerek yasaklamıyor, karar
döngüde `update_episode`'a indiriliyor.
"""

import json

from gozcu.models import Observation, RouterDecision

# `EventSummary.time` deseni (`^\d{2}:\d{2}$`) iki haneli dakika istiyor ve
# `mmss`'in saat devri yok. Demo klipleri dakikalarla ölçülüyor; saat desteği
# kapsam dışı, ama geçersiz bir damga üretmek de seçenek değil — tavana
# yapıştırılıyor.
MAX_MINUTES = 99
_CLAMPED_STAMP = "99:59"

# `RouterDecision.rationale`'ın sınırı. Şema sertleştirmesi `maxLength`'i telden
# söküyor (bkz. `gozcu.gateway.strict_schema`), yani modelin sınırı aşması
# mümkün; kesme bu yüzden Python tarafında.
MAX_RATIONALE = 200

SYSTEM_PROMPT = """Sen bir fabrika güvenlik kontrol odasının yönlendiricisisin.
Sana 10 saniyelik bir pencerenin sinyal özeti verilir. Görüntü görmezsin.
Görevin: bu pencere dikkat gerektiriyor mu, gerekiyorsa kime gitmeli.

Kararlar (tam olarak bu değerlerden birini döndür):
- ignore: olağan hareket, ilgilenmeye değmez
- inspect: bir şey var ama ne olduğu sinyalden anlaşılmıyor
- open_episode: yeni bir olay başlıyor
- update_episode: açık olay devam ediyor
- close_episode: açık olay sonuçlandı
- escalate: can güvenliği riski, operatör derhal haberdar edilmeli

Açık bir olay yokken update_episode veya close_episode verme.
Sadece JSON döndür."""


def mmss(ts: float) -> str:
    """Video saniyesini "DD:SS" damgasına çevirir; 99:59'da tavana oturur.

    Tek kopya bilerek burada: Görev 07, 14 ve 17 bunu import ediyor.
    """
    minutes, seconds = divmod(int(ts), 60)
    if minutes > MAX_MINUTES:
        return _CLAMPED_STAMP
    return f"{minutes:02d}:{seconds:02d}"


def window_digest(window: list[Observation]) -> str:
    """Pencereyi modele gidecek düz metne çevirir — gözlem başına bir satır."""
    lines = []
    for observation in window:
        signals = observation.signals
        parts = [f"kişi={signals.person_count}"]
        if signals.person_count_delta:
            parts.append(f"değişim={signals.person_count_delta:+d}")
        if signals.velocities:
            parts.append("hızlar=" + ",".join(
                f"{track_id}:{speed:.1f}"
                for track_id, speed in signals.velocities.items()))
        if signals.vanished_tracks:
            parts.append(f"kaybolan={signals.vanished_tracks}")
        if signals.gathering:
            parts.append("toplanma")
        lines.append(f"{mmss(observation.ts)} " + " ".join(parts))
    return "\n".join(lines)


def _fallback(rationale: str) -> RouterDecision:
    """Karar okunamadığında pencere sessizce geçilir.

    Bozuk bir JSON'da patlayan yönlendirici tek bir kötü yanıtta bütün koşuyu
    düşürür; güven sıfır veriliyor ki ölçümde gerçek bir kararla karışmasın.
    """
    return RouterDecision(decision="ignore", rationale=rationale, confidence=0.0)


def _sanitize(data: dict) -> dict:
    """Modelin döndürdüğü değerleri doğrulamadan ÖNCE sınırlara sokar.

    Sertleştirme `maxLength`/`minimum`/`maximum`'u telden söküyor, yani model
    200 karakteri aşan bir gerekçe ya da 0..1 dışında bir güven döndürebilir.
    Ham hâliyle `RouterDecision(**…)`'a verilirse doğrulama patlar ve gerçek
    bir karar — belki bir `escalate` — `ignore`'a çöker. Sınıra çekmek kararı
    korur, uydurmaz.
    """
    rationale = data.get("rationale")
    if isinstance(rationale, str) and len(rationale) > MAX_RATIONALE:
        data["rationale"] = rationale[:MAX_RATIONALE]

    confidence = data.get("confidence")
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        data["confidence"] = min(1.0, max(0.0, float(confidence)))
    return data


def route(gw, window: list[Observation],
          has_open_episode: bool) -> RouterDecision:
    """Pencereyi yönlendirici kademesine sorar; okunamayan her şey `ignore`.

    Kesinti guard'ı açık: `router` kademesi kesintide istisna atmıyor,
    `content=""`, `degraded=True` bir `Response` döndürüyor. Boş içeriğin
    ayrıştırmada tesadüfen patlamasına güvenilmiyor — bozuk yanıt bir gün
    dolu gövdeyle gelirse (ör. önbellekten dönen bayat karar) o tesadüf
    çalışmaz ve bayat karar canlı karar gibi işlenir.
    """
    state = "Açık bir olay var." if has_open_episode else "Açık olay yok."
    response = gw.ask("router", [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"{state}\n\n{window_digest(window)}"},
    ], schema=RouterDecision)

    if response.degraded:
        return _fallback("yönlendirici kademesi yanıt vermiyor")

    try:
        data = json.loads(response.content)
    except (ValueError, TypeError):
        return _fallback("yönlendirici yanıtı okunamadı")
    if not isinstance(data, dict):
        return _fallback("yönlendirici yanıtı okunamadı")

    try:
        return RouterDecision(**_sanitize(data))
    except Exception:  # noqa: BLE001 — kötü bir karar koşuyu durdurmamalı
        return _fallback("yönlendirici yanıtı okunamadı")
```

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_router.py -v
```
Beklenen: 17 passed

### 5. Commit

```bash
git add gozcu/agents/router.py tests/test_router.py
git commit -m "feat: router agent with sanitised decisions"
```

## Doğrulama

```bash
uv run pytest tests/test_router.py -v
```
Beklenen: **17 passed**

## Tamamlanma notları (gelecek görevleri bağlayan)

- **Modül `gozcu/agents/router.py`;** dışa verdikleri `mmss`, `window_digest`,
  `route`, `SYSTEM_PROMPT` ve `MAX_RATIONALE`. **Görev 07 `mmss`'i buradan
  import ediyor** (Görev 14 ve 17 de). İkinci bir kopya yazılmayacak.
- **`mmss` `"99:59"`de tavana oturuyor.** Tavan olmadan 99 dakikayı aşan bir
  video örneğin `"100:00"` üretir; bu `EventSummary.time`'ın `^\d{2}:\d{2}$`
  desenini ihlal eder ve Görev 17'de doğrulama hatasına düşer. Tam saat
  desteği demo uzunluğundaki klipler için **bilerek kapsam dışı** — ama
  geçersiz bir damga üretmek de seçenek değildi.
- **Prompt, açık bir epizot varken `open_episode` demeyi bilerek
  yasaklamıyor.** Tek açık epizot değişmezinin tek bekçisi
  `DecisionLoop._resolve()`; bu tasarım gereği. Prompt açık epizot **yokken**
  `update_episode`/`close_episode`'u yasaklıyor — ama yönlendirici yine de
  bunları döndürebilir ve **hiçbir yer bunu düzeltmiyor**. Görev 07 açık
  epizot yokken gelen bir `update_episode`/`close_episode` ile karşılaşmayı
  hesaba katmak zorunda.
- **Prompt'taki karar değerleri `RouterDecision.decision`'ın `Literal`'ıyla
  bayt bayt aynı.** CLAUDE.md'nin kuralı: bir prompt enum sayıyorsa değerler
  şemadakiyle birebir aynı olmalı. Bir test bunu doğruluyor; değerleri
  Türkçeleştirme ya da yeniden ifade etme.
- **Yönlendirici sistemin en sık çağrılan modeli** ve önünde `passes_floor`
  var (Görev 05): taban sinyali geçmeyen pencere modele hiç gitmiyor. Özet
  gözlem başına tek satır ve 10 saniyelik pencereyle sınırlı — 10 dakikalık
  bir video için ~60 çağrı. Özeti büyütmek doğrudan gecikme ve token demek.
