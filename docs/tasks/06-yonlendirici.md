# Görev 06 — Yönlendirici ajanı (`gozcu/agents/router.py`)

**Sahip:** `uvyscengiz` · **Gün:** 24 Ağustos · **Süre:** ~1.5 saat
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
Gateway.ask(tier, messages, schema=None, tools=None) -> Response   # kademe pozisyonel
Response(content, tool_calls, model, latency_ms, tokens, degraded)

# gozcu/models.py
Observation(id, ts, detections, signals)
Signals(velocities: dict[int, float], vanished_tracks: list[int],
          person_count: int, person_count_delta: int, gathering: bool)
RouterDecision(decision, rationale, confidence)
```

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
from unittest.mock import Mock

from gozcu.agents.router import mmss, window_digest, route
from gozcu.gateway import Response
from gozcu.models import Observation, Signals


def _g(ts, **kw):
    return Observation(ts=ts, signals=Signals(**kw))


def test_mmss_formats_video_time():
    assert mmss(192.0) == "03:12" and mmss(0.0) == "00:00"


def test_digest_is_text_and_carries_no_image():
    digest = window_digest([_g(0.0, person_count=2, velocities={1: 3.4}),
                          _g(1.0, vanished_tracks=[1])])
    assert "00:00" in digest and "2" in digest and "3.4" in digest
    assert "base64" not in digest and "image" not in digest


def test_route_parses_the_model_decision():
    gw = Mock()
    gw.ask.return_value = Response(
        content='{"decision":"escalate","rationale":"araç devrildi","confidence":0.91}')
    k = route(gw, [_g(0.0, person_count=1)], has_open_episode=False)
    assert k.decision == "escalate" and k.confidence == 0.91
    assert gw.ask.call_args.args[0] == "router"


def test_open_episode_state_reaches_the_prompt():
    gw = Mock(); gw.ask.return_value = Response(content='{"decision":"ignore","rationale":"x","confidence":0.5}')
    route(gw, [_g(0.0)], has_open_episode=True)
    prompt_text = gw.ask.call_args.args[1][-1]["content"]
    assert "Açık bir olay var" in prompt_text


def test_unparseable_response_degrades_to_ignore_not_a_crash():
    gw = Mock()
    gw.ask.return_value = Response(content="model bugün konuşmuyor")
    assert route(gw, [_g(0.0)], has_open_episode=False).decision == "ignore"


def test_degraded_router_tier_degrades_to_ignore():
    gw = Mock(); gw.ask.return_value = Response(degraded=True)
    assert route(gw, [_g(0.0)], has_open_episode=False).decision == "ignore"
```

Son iki test göründüğünden önemli: bozuk JSON'da patlayan bir yönlendirici, tek
bir kötü yanıtta bütün koşuyu düşürür.

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_router.py -v
```
Beklenen: `ModuleNotFoundError`

### 3. `gozcu/agents/router.py` yaz

```python
import json

from gozcu.models import Observation, RouterDecision

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
    return f"{int(ts) // 60:02d}:{int(ts) % 60:02d}"


def window_digest(window: list[Observation]) -> str:
    lines = []
    for g in window:
        s = g.signals
        parts = [f"kişi={s.person_count}"]
        if s.person_count_delta:
            parts.append(f"değişim={s.person_count_delta:+d}")
        if s.velocities:
            parts.append("hızlar=" + ",".join(
                f"{tid}:{h:.1f}" for tid, h in s.velocities.items()))
        if s.vanished_tracks:
            parts.append(f"kaybolan={s.vanished_tracks}")
        if s.gathering:
            parts.append("gathering")
        lines.append(f"{mmss(g.ts)} " + " ".join(parts))
    return "\n".join(lines)


def route(gw, window: list[Observation],
          has_open_episode: bool) -> RouterDecision:
    state = "Açık bir olay var." if has_open_episode else "Açık olay yok."
    response = gw.ask("router", [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"{state}\n\n{window_digest(window)}"},
    ], schema=RouterDecision)

    if response.degraded:
        return RouterDecision(decision="ignore",
                            rationale="yönlendirici kademesi yanıt vermiyor",
                            confidence=0.0)
    try:
        return RouterDecision(**json.loads(response.content))
    except Exception:  # noqa: BLE001 — kötü bir karar koşuyu durdurmamalı
        return RouterDecision(decision="ignore",
                            rationale="yönlendirici yanıtı okunamadı",
                            confidence=0.0)
```

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_router.py -v
```
Beklenen: 6 passed

### 5. Commit

```bash
git add gozcu/agents/router.py tests/test_router.py
git commit -m "feat: router agent over windowed signal digests"
```

## Doğrulama

```bash
uv run pytest tests/test_router.py -v
```
Beklenen: **6 passed**
