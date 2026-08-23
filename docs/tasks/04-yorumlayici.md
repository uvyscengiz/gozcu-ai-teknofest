# Görev 04 — Yorumlayıcı adaptörü (`gozcu/agents/interpreter.py`)

**Sahip:** `uvyscengiz` · **Gün:** 24 Ağustos · **Süre:** ~2 saat
**Bağımlılık:** [01](01-sozlesme.md), [02](02-olay-deposu.md), [03](03-gateway.md)

## Bağlam

Mevcut `gozcu/interpret.py` çalışıyor ama **uzak gateway'e konuşamaz.** İki
sebepten:

1. Kendi `OpenAI` istemcisini `VLM_BASE_URL`'e karşı kuruyor — `Gateway`'i
   baypas ediyor. Bu yüzden `hata_enjekte({"vlm"})` gerçek VLM çağrılarını
   yönetmiyor: demo sırasında bastığımız "bağlantıyı kes" düğmesi
   **hiç kullanılmayan bir katmanı** kesiyor olurdu.
2. `interpret.py:171` görüntüyü `{"url": str(frame_path)}` diye gönderiyor —
   yerel bir dosya yolu. Uzaktaki bir gateway o dosyayı okuyamaz; görüntünün
   base64 data-URI olarak gömülmesi gerekiyor.

Bu görev arayı kapatan adaptörü yazıyor. `interpret.py` **silinmiyor** — donuk
algı katmanının parçası, prompt kurgusu ve çıktı temizleme mantığı oradan
alınıyor.

Ayrıca bu, `Interpretation` kayıtlarını üreten tek yer. Onlar olmadan
`vlm_trigger_rate` KPI'ı hep sıfır okur.

## Kurulum

```bash
uv sync --extra dev
export GOZCU_GATEWAY_BASE_URL="http://<adres>:4000/v1"
uv run pytest tests/test_gateway.py -v      # Görev 03 yeşil olmalı
```

## Bağımlı olduğun imzalar

```python
# gozcu/gateway.py
Gateway.ask(tier, messages, schema=None, tools=None) -> Response
Response(content, tool_calls, model, latency_ms, tokens, degraded)

# gozcu/models.py
Observation(id, ts, detections, signals)
Interpretation(id, observation_ts, description, notable_event, model, latency_ms, tokens)

# gozcu/store.py
Store.save_interpretation(y: Interpretation) -> int
```

## Ne yapacaksın

Üreteceğin arayüz:

```python
frame_data_uri(frame_path: str | Path) -> str      # "data:image/jpeg;base64,..."
interpret(gw, store, window: list[Observation], frame_for) -> Interpretation | None
```

`interpret` pencerenin **orta karesini** seçer (en temsili olan), base64'ler,
`gw.ask("vlm", ...)` ile yorumlatır, `Interpretation` üretip depoya yazar.
Gateway bozulmuşsa `None` döner — çağıran taraf bunu bekliyor.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_interpreter.py`

```python
import base64
from unittest.mock import Mock

from gozcu.agents.interpreter import frame_data_uri, interpret
from gozcu.gateway import Response
from gozcu.models import Observation, Signals
from gozcu.store import Store


def _win():
    return [Observation(ts=float(t), signals=Signals(person_count=1))
            for t in range(10)]


def test_data_uri_embeds_the_image_not_a_path(tmp_path):
    p = tmp_path / "kare.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0sahte-jpeg")
    uri = frame_data_uri(p)
    assert uri.startswith("data:image/jpeg;base64,")
    assert base64.b64decode(uri.split(",", 1)[1]) == b"\xff\xd8\xff\xe0sahte-jpeg"
    assert str(p) not in uri


def test_interpret_sends_through_the_vlm_tier(tmp_path):
    p = tmp_path / "k.jpg"; p.write_bytes(b"x")
    gw = Mock()
    gw.ask.return_value = Response(
        content='{"description":"İstif aracı yan yattı.","notable_event":null}',
        model="vlm-test", latency_ms=420, tokens=180)
    y = interpret(gw, Store(":memory:"), _win(), lambda ts: p)
    assert gw.ask.call_args.args[0] == "vlm"
    assert y.description == "İstif aracı yan yattı."
    assert y.latency_ms == 420 and y.tokens == 180


def test_interpret_picks_the_middle_frame_of_the_window(tmp_path):
    p = tmp_path / "k.jpg"; p.write_bytes(b"x")
    istenen = []
    gw = Mock(); gw.ask.return_value = Response(content='{"description":"x"}')
    interpret(gw, Store(":memory:"), _win(),
            lambda ts: istenen.append(ts) or p)
    assert istenen == [5.0]


def test_interpret_returns_none_when_the_vlm_tier_is_degraded(tmp_path):
    p = tmp_path / "k.jpg"; p.write_bytes(b"x")
    gw = Mock(); gw.ask.return_value = Response(degraded=True)
    store = Store(":memory:")
    assert interpret(gw, store, _win(), lambda ts: p) is None
    assert store.interpretations() == []


def test_interpretation_is_persisted_with_the_window_timestamp(tmp_path):
    p = tmp_path / "k.jpg"; p.write_bytes(b"x")
    gw = Mock(); gw.ask.return_value = Response(content='{"description":"tamam"}')
    store = Store(":memory:")
    interpret(gw, store, _win(), lambda ts: p)
    assert store.interpretations()[0].observation_ts == 5.0
```

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_interpreter.py -v
```
Beklenen: `ModuleNotFoundError`

### 3. `gozcu/agents/interpreter.py` yaz

`gozcu/agents/__init__.py` (boş) da gerekiyor.

```python
import base64
import json
import mimetypes
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from gozcu.models import Observation, Interpretation

SYSTEM_PROMPT = """Sen bir fabrika güvenlik kamerasının görüntüsünü inceleyen
gözlemcisin. Sana bir kare ve o karedeki tespit/sinyal özeti verilir.

Kurallar:
- Sadece GÖRDÜĞÜNÜ yaz. Emin değilsen "olası" de.
- Türkçe, tek-iki kısa cümle, saha terminolojisi
- Dikkat çekici bir şey yoksa notable_event null olsun
- Kişi kimliği, yaş, cinsiyet tahmini YAPMA

Sadece JSON döndür."""


class _VisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(max_length=300)
    notable_event: str | None = Field(default=None, max_length=200)


def frame_data_uri(frame_path: str | Path) -> str:
    p = Path(frame_path)
    kind = mimetypes.guess_type(p.name)[0] or "image/jpeg"
    payload = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{kind};base64,{payload}"


def _context(window: list[Observation]) -> str:
    labels = sorted({t.label for g in window for t in g.detections})
    middle = window[len(window) // 2]
    s = middle.signals
    parts = [f"detections: {', '.join(labels) or 'yok'}",
                f"kişi sayısı: {s.person_count}"]
    if s.velocities:
        parts.append("hızlar: " + ", ".join(
            f"{tid}:{h:.1f}" for tid, h in s.velocities.items()))
    if s.vanished_tracks:
        parts.append(f"kadraj dışına çıkan: {s.vanished_tracks}")
    return " | ".join(parts)


def interpret(gw, store, window: list[Observation], frame_for) -> Interpretation | None:
    """kare_yolu: bir ts alıp o ana ait kare dosya yolunu döndüren çağrılabilir."""
    if not window:
        return None

    middle = window[len(window) // 2]
    path = frame_for(middle.ts)
    if path is None:
        return None

    response = gw.ask("vlm", [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": [
            {"type": "text",
             "text": f"Signals — {_context(window)}\n\nBu karede ne oluyor?"},
            {"type": "image_url",
             "image_url": {"url": frame_data_uri(path)}},
        ]},
    ], schema=_VisionResponse)

    if response.degraded:
        return None

    try:
        parsed = _VisionResponse(**json.loads(response.content))
    except Exception:  # noqa: BLE001 — bozuk JSON bir koşuyu düşürmemeli
        return None

    interpretation = Interpretation(observation_ts=middle.ts, description=parsed.description,
                  notable_event=parsed.notable_event, model=response.model,
                  latency_ms=response.latency_ms, tokens=response.tokens)
    interpretation.id = store.save_interpretation(interpretation)
    return interpretation
```

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_interpreter.py -v
```
Beklenen: 5 passed

### 5. Commit

```bash
git add gozcu/agents/__init__.py gozcu/agents/interpreter.py tests/test_interpreter.py
git commit -m "feat: VLM interpreter adapter with base64 frames over the gateway"
```

## Doğrulama

```bash
uv run pytest tests/test_interpreter.py -v
```
Beklenen: **5 passed**
