# Görev 04 — Yorumlayıcı adaptörü (`gozcu/agents/interpreter.py`)

> ## ✅ TAMAMLANDI — 23 Ağustos 2026, `89f7c21`
>
> **Yorumlayıcı indi.** `gozcu/agents/interpreter.py` var,
> `tests/test_interpreter.py` 28 test fonksiyonu / 34 durum ile yeşil. Bu
> dosyayı yeniden uygulama — aşağısı ne yapıldığının kaydı.
>
> **Sonraki göreve başlarken bilmen gerekenler**
> ([kararlar](#tamamlanma-notları-gelecek-görevleri-bağlayan) bölümüne bak):
> pencere başına **üç kare** gidiyor — ilk, orta ve son, tek orta kare değil;
> **şema sertleştirmesi artık gateway'in içinde** — `Gateway.ask()`'e düz bir
> pydantic modeli verilir, `strict_schema()`'i kimse elle çağırmaz, ama
> sınırlar tele çıkmadığı için **her ajan doğrulamadan önce kendi değerlerini
> temizlemek zorunda**; ve `Gateway.ask()` artık isteğe bağlı `max_tokens` /
> `temperature` alıyor.

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
Gateway.ask(tier, messages, schema=None, tools=None,
            max_tokens=None, temperature=None) -> Response
Response(content, tool_calls, model, latency_ms, tokens, degraded)

# gozcu/models.py
Observation(id, ts, detections, signals)
Interpretation(id, observation_ts, description, notable_event, model, latency_ms, tokens)

# gozcu/store.py
Store.save_interpretation(y: Interpretation) -> int
```

`max_tokens` / `temperature` bu görevde `Gateway.ask`'e eklendi; verilmezse
istekte hiç görünmüyorlar, yani mevcut çağrı yerleri değişmedi.

**Bozulmuş yanıt guard'ı (Görev 03).** `gw.ask()` kesintide istisna atmıyor;
`content=""`, `tool_calls=[]` olan `degraded=True` bir `Response` dönüyor.
Bozulmuş yanıt hiçbir şeye ayrışmaz — `response.degraded` kontrolünden sonra
bile boş içeriğe karşı korun. `except GatewayError` bunu yakalamaz.

## Ne yapacaksın

Üreteceğin arayüz:

```python
strict_schema(schema: dict) -> dict                # ask() bunu kendi uyguluyor, çağıran değil
frame_data_uri(frame_path: str | Path) -> str      # "data:image/jpeg;base64,..."
interpret(gw, store, window: list[Observation], frame_for) -> Interpretation | None
```

`interpret` pencerenin **ilk, orta ve son** karesini alır (kısa pencerede
yinelenenler atılır, bulunamayan kare atlanır), base64'ler, `gw.ask("vlm", ...)`
ile yorumlatır, `Interpretation` üretip depoya yazar. Üretilen kaydın
`observation_ts` alanı **orta** karenin zaman damgasıdır. Görü kademesi
bozulmuşsa `None` döner — çağıran taraf bunu bekliyor.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_interpreter.py`

```python
"""Yorumlayıcı adaptörünün testleri.

Sahte gateway bilerek `Mock()` değil: bu depoda beş kusur şekilsiz bir
`Mock()` collaborator'ın arkasında saklandı. `_FakeGateway` ne ile
çağrıldığını kaydeder ve gerçek bir `Response` döndürür — şema, mesajlar ve
üretim parametreleri tek tek incelenebilir.
"""

import base64
import json
from unittest.mock import Mock, patch

import pytest
from pydantic import BaseModel, ConfigDict

from gozcu.agents.interpreter import (SYSTEM_PROMPT, _sanitize_text,
                                      _VisionResponse, frame_data_uri,
                                      interpret, strict_schema)
from gozcu.gateway import Gateway, Response
from gozcu.models import Detection, Observation, Signals
from gozcu.store import Store


class _FakeGateway:
    """Şekilli sahte: `Gateway.ask` imzasını birebir taşır ve kaydeder."""

    def __init__(self, response: Response | None = None) -> None:
        self.response = response if response is not None else Response(
            content='{"description":"varsayılan","notable_event":null}',
            model="vlm-test")
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


def _window(count: int = 10) -> list[Observation]:
    return [Observation(ts=float(t), signals=Signals(person_count=1))
            for t in range(count)]


def _frame(tmp_path):
    path = tmp_path / "k.jpg"
    path.write_bytes(b"\xff\xd8\xff\xe0x")
    return path


def _image_parts(messages: list[dict]) -> list[dict]:
    return [p for p in messages[-1]["content"] if p["type"] == "image_url"]


def _text_part(messages: list[dict]) -> str:
    return next(p["text"] for p in messages[-1]["content"] if p["type"] == "text")


# --- frame_data_uri -------------------------------------------------------

def test_data_uri_embeds_the_image_not_a_path(tmp_path):
    path = tmp_path / "kare.jpg"
    path.write_bytes(b"\xff\xd8\xff\xe0sahte-jpeg")
    uri = frame_data_uri(path)
    assert uri.startswith("data:image/jpeg;base64,")
    assert base64.b64decode(uri.split(",", 1)[1]) == b"\xff\xd8\xff\xe0sahte-jpeg"
    assert str(path) not in uri


# --- strict şema (RULING 1 / RULING 2) ------------------------------------

def test_schema_handed_to_the_gateway_lists_every_property_as_required(tmp_path):
    """OpenAI strict structured outputs HER alanın `required` içinde olmasını
    ister. `notable_event`'in varsayılanı olduğu için pydantic onu listeden
    düşürüyor; gerçek gateway buna 400 veriyor, denemeler tükeniyor,
    `degraded=True` oluyor ve `interpret` HER pencere için `None` dönüyor —
    sistem yeşil test takımıyla birlikte sessizce hiçbir şey üretmiyor."""
    gw = _FakeGateway()
    interpret(gw, Store(":memory:"), _window(), lambda ts: _frame(tmp_path))
    schema = gw.last["schema"].model_json_schema()
    assert set(schema["required"]) == set(schema["properties"])
    assert "notable_event" in schema["required"]


def test_schema_handed_to_the_gateway_carries_no_max_length(tmp_path):
    """`Field(max_length=…)` şemaya `maxLength` basıyor; strict-mode arka
    uçları bunu yaygın olarak reddediyor. Sınır pydantic modelinde kalır,
    şemadan çıkar, kesme Python tarafında yapılır."""
    gw = _FakeGateway()
    interpret(gw, Store(":memory:"), _window(), lambda ts: _frame(tmp_path))
    schema = gw.last["schema"].model_json_schema()
    assert "maxLength" not in json.dumps(schema)


def test_schema_handed_to_the_gateway_forbids_additional_properties(tmp_path):
    gw = _FakeGateway()
    interpret(gw, Store(":memory:"), _window(), lambda ts: _frame(tmp_path))
    schema = gw.last["schema"].model_json_schema()
    assert schema["additionalProperties"] is False


def test_pydantic_still_enforces_the_length_limits():
    """Şemadan çıkan sınır modelde duruyor — son doğrulama ağı."""
    with pytest.raises(Exception):
        _VisionResponse(description="a" * 301)


def test_notable_event_schema_description_spells_out_a_valid_value(tmp_path):
    """Küçük VLM, çıplak alan adından başka tutunacak bir şey bulamayınca
    `notable_event` değerini alan adının kendisi olarak geri yazdı (bir gerçek
    karede 4/4 tekrarlandı). Şema açıklaması o döngüyü kapatıyor."""
    gw = _FakeGateway()
    interpret(gw, Store(":memory:"), _window(), lambda ts: _frame(tmp_path))
    schema = gw.last["schema"].model_json_schema()
    description = schema["properties"]["notable_event"]["description"]
    assert "null" in description.lower()
    assert "notable_event" in description


def test_strict_schema_bounds_arrays_against_runaway_repetition():
    """Üst sınır olmadan strict-JSON şema kod çözümü dizi içinde kaçak tekrara
    giriyor: uydurma etiketleri max_tokens tükenene kadar yineliyor, JSON hiç
    kapanmıyor ve sonraki alanlara hiç ulaşılmıyor."""

    class _WithArray(BaseModel):
        model_config = ConfigDict(extra="forbid")
        labels: list[str]

    schema = strict_schema(_WithArray.model_json_schema())
    assert schema["properties"]["labels"]["maxItems"] >= 1


def test_strict_schema_does_not_mutate_the_input():
    source = {"type": "object", "properties": {"a": {"type": "string",
                                                     "maxLength": 5}}}
    strict_schema(source)
    assert source["properties"]["a"]["maxLength"] == 5


# --- gateway'e gerçekten ulaşan istek (RULING 1 + RULING 4 uçtan uca) ------

def test_the_wire_request_is_strict_safe_and_carries_generation_controls(tmp_path):
    """`Gateway.ask` şemayı kendisi üretiyor — asıl kanıt istemciye giden
    gövdedeki şema."""
    gw = Gateway()
    completion = Mock(choices=[Mock(message=Mock(content='{"description":"a",'
                                                         '"notable_event":null}',
                                                 tool_calls=[]))],
                      usage=Mock(total_tokens=7))
    with patch.object(gw, "_client") as client:
        client.chat.completions.create.return_value = completion
        interpret(gw, Store(":memory:"), _window(), lambda ts: _frame(tmp_path))
        request = client.chat.completions.create.call_args.kwargs

    schema = request["response_format"]["json_schema"]["schema"]
    assert request["response_format"]["json_schema"]["strict"] is True
    assert set(schema["required"]) == set(schema["properties"])
    assert "maxLength" not in json.dumps(schema)
    assert request["max_tokens"] > 0
    assert 0.0 <= request["temperature"] <= 1.0


def test_generation_controls_are_passed_to_the_gateway(tmp_path):
    gw = _FakeGateway()
    interpret(gw, Store(":memory:"), _window(), lambda ts: _frame(tmp_path))
    assert gw.last["max_tokens"] is not None and gw.last["max_tokens"] > 0
    assert gw.last["temperature"] is not None


# --- üç kare (RULING 3) ---------------------------------------------------

def test_interpret_requests_the_first_middle_and_last_frame(tmp_path):
    """Devrilen bir istif aracı hareket olayı: tek kare onu ya hâlâ ayakta ya
    da çoktan yerde gösterir."""
    requested: list[float] = []
    gw = _FakeGateway()
    interpret(gw, Store(":memory:"), _window(),
              lambda ts: requested.append(ts) or _frame(tmp_path))
    assert requested == [0.0, 5.0, 9.0]
    assert len(_image_parts(gw.last["messages"])) == 3


def test_interpret_handles_a_single_observation_window(tmp_path):
    requested: list[float] = []
    gw = _FakeGateway()
    window = [Observation(ts=3.0, signals=Signals(person_count=1))]
    result = interpret(gw, Store(":memory:"), window,
                       lambda ts: requested.append(ts) or _frame(tmp_path))
    assert requested == [3.0]
    assert len(_image_parts(gw.last["messages"])) == 1
    assert result is not None


def test_interpret_uses_the_frames_it_got_when_one_is_missing(tmp_path):
    gw = _FakeGateway()
    result = interpret(gw, Store(":memory:"), _window(),
                       lambda ts: None if ts == 5.0 else _frame(tmp_path))
    assert len(_image_parts(gw.last["messages"])) == 2
    assert result is not None


def test_the_prompt_asks_what_changes_across_the_frames(tmp_path):
    gw = _FakeGateway()
    interpret(gw, Store(":memory:"), _window(), lambda ts: _frame(tmp_path))
    text = _text_part(gw.last["messages"])
    assert "değiş" in text.lower() or "değiş" in SYSTEM_PROMPT.lower()
    assert "tespitler:" in text
    assert "detections" not in text


# --- temel akış -----------------------------------------------------------

def test_interpret_sends_through_the_vlm_tier(tmp_path):
    gw = _FakeGateway(Response(
        content='{"description":"İstif aracı yan yattı.","notable_event":null}',
        model="vlm-test", latency_ms=420, tokens=180))
    result = interpret(gw, Store(":memory:"), _window(), lambda ts: _frame(tmp_path))
    assert gw.last["tier"] == "vlm"
    assert result.description == "İstif aracı yan yattı."
    assert result.model == "vlm-test"
    assert result.latency_ms == 420 and result.tokens == 180


def test_interpretation_is_persisted_with_the_window_timestamp(tmp_path):
    gw = _FakeGateway(Response(content='{"description":"tamam"}', model="v"))
    store = Store(":memory:")
    result = interpret(gw, store, _window(), lambda ts: _frame(tmp_path))
    assert store.interpretations()[0].observation_ts == 5.0
    assert result.id == store.interpretations()[0].id


# --- None'ın dört ayrı anlamı (RULING 5) ----------------------------------

def test_empty_window_is_none_without_asking_the_gateway():
    gw = _FakeGateway()
    assert interpret(gw, Store(":memory:"), [], lambda ts: None) is None
    assert gw.calls == []


def test_every_frame_missing_is_none_without_asking_the_gateway():
    gw = _FakeGateway()
    store = Store(":memory:")
    assert interpret(gw, store, _window(), lambda ts: None) is None
    assert gw.calls == []
    assert store.interpretations() == []


def test_degraded_is_none_even_when_the_response_carries_valid_json(tmp_path):
    """Görev dosyasının 4. testi `Response(degraded=True)` kullanıyordu; onun
    `content`'i `""` olduğu için `degraded` dalını tamamen silmek de testi
    geçiriyordu. Geçerli JSON taşıyan bozuk bir yanıt yalnızca gerçek bir
    `degraded` kontrolüyle `None` verir."""
    gw = _FakeGateway(Response(
        content='{"description":"bir şey","notable_event":null}',
        model="vlm-test", degraded=True))
    store = Store(":memory:")
    assert interpret(gw, store, _window(), lambda ts: _frame(tmp_path)) is None
    assert store.interpretations() == []


def test_empty_content_is_none(tmp_path):
    gw = _FakeGateway(Response(content="   ", model="vlm-test"))
    store = Store(":memory:")
    assert interpret(gw, store, _window(), lambda ts: _frame(tmp_path)) is None
    assert store.interpretations() == []


def test_unparsable_content_is_none(tmp_path):
    gw = _FakeGateway(Response(content="JSON değil", model="vlm-test"))
    store = Store(":memory:")
    assert interpret(gw, store, _window(), lambda ts: _frame(tmp_path)) is None
    assert store.interpretations() == []


def test_schema_violating_content_is_none(tmp_path):
    gw = _FakeGateway(Response(content='{"notable_event":"x"}', model="vlm-test"))
    assert interpret(gw, Store(":memory:"), _window(),
                     lambda ts: _frame(tmp_path)) is None


# --- çıktı temizleme (RULING 2) -------------------------------------------

def test_cut_off_description_loses_the_dangling_fragment():
    body = "Sahada bir kişi var. " * 13          # 273 karakter
    text = (body + "yerdeki ekipmana doğru il")[:300]
    cleaned = _sanitize_text(text, 300)
    assert not cleaned.endswith("il")
    assert cleaned.endswith("doğru")


def test_trailing_control_character_is_stripped():
    assert _sanitize_text("Binanın çatısında duman var.\x01", 300) == \
        "Binanın çatısında duman var."


def test_over_long_description_is_truncated_not_dropped(tmp_path):
    """Şemadan `maxLength` çıktığı için model sınırı aşabilir. Bu, kaydı
    düşürmek yerine Python tarafında kesilir."""
    long = "Sahada bir kişi var. " * 30
    gw = _FakeGateway(Response(content=json.dumps({"description": long}),
                               model="vlm-test"))
    result = interpret(gw, Store(":memory:"), _window(), lambda ts: _frame(tmp_path))
    assert result is not None
    assert len(result.description) <= 300


@pytest.mark.parametrize("value", ["notable_event", "notable event", "none",
                                   "null", "N/A", "placeholder", "  NULL  "])
def test_placeholder_notable_event_is_treated_as_no_event(value, tmp_path):
    gw = _FakeGateway(Response(
        content=json.dumps({"description": "tamam", "notable_event": value}),
        model="vlm-test"))
    result = interpret(gw, Store(":memory:"), _window(), lambda ts: _frame(tmp_path))
    assert result.notable_event is None


def test_a_real_notable_event_survives(tmp_path):
    gw = _FakeGateway(Response(
        content=json.dumps({"description": "tamam",
                            "notable_event": "İstif aracı devrildi."}),
        model="vlm-test"))
    result = interpret(gw, Store(":memory:"), _window(), lambda ts: _frame(tmp_path))
    assert result.notable_event == "İstif aracı devrildi."


# --- bağlam metni ---------------------------------------------------------

def test_context_lists_detected_labels_in_turkish(tmp_path):
    window = _window()
    window[5].detections = [Detection(label="person", confidence=0.9,
                                      box=(0, 0, 1, 1))]
    gw = _FakeGateway()
    interpret(gw, Store(":memory:"), window, lambda ts: _frame(tmp_path))
    text = _text_part(gw.last["messages"])
    assert "person" in text and "kişi sayısı" in text
```

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_interpreter.py -v
```
Beklenen: `ModuleNotFoundError`

### 3. `gozcu/agents/interpreter.py` yaz

`gozcu/agents/__init__.py` (boş) da gerekiyor.

```python
"""Yorumlayıcı adaptörü — pencereyi görü kademesine soran tek yer.

`gozcu/interpret.py` çalışıyor ama kendi `OpenAI` istemcisini kuruyor:
`Gateway`'i baypas ettiği için `inject_failure({"vlm"})` gerçek VLM
çağrılarını yönetmiyor, ve kareyi yerel dosya yolu olarak gönderdiği için
uzaktaki bir gateway görüntüyü hiç okuyamıyor. Bu modül arayı kapatıyor:
kareler base64 data-URI olarak gömülüyor, istek `gw.ask("vlm", …)` üzerinden
geçiyor.

Buradaki şema sertleştirmesi ve çıktı temizleme mantığı `interpret.py`'da
gerçek karelerle görülmüş hatalardan doğdu; her birinin gerekçesi ilgili
sabitin başında duruyor. `interpret.py`'dan import edilmiyor — o modül donuk
algı katmanının parçası ve Görev 17'de çağrısız kalacak.
"""

import base64
import copy
import json
import mimetypes
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from gozcu.models import Interpretation, Observation

MAX_DESCRIPTION = 300
MAX_NOTABLE_EVENT = 200

# Token tavanı. Kaçak tekrar (aşağıdaki `_MAX_ARRAY_ITEMS` notu) yalnızca bir
# üst sınırla tam olarak kapanıyor: sınır yoksa kod çözücü JSON'u hiç
# kapatmadan üretmeye devam ediyor. 300 + 200 karakterlik iki alan Türkçede
# ~250 token; JSON iskeleti için pay bırakıyoruz.
MAX_TOKENS = 400
# Güvenlik kaydı için düşük ama sıfır değil: sıfır sıcaklık aynı yanlış
# betimlemeyi her karede tekrar üretiyordu.
TEMPERATURE = 0.3

SYSTEM_PROMPT = """Sen bir fabrika güvenlik kamerasını izleyen gözlemcisin.
Sana aynı zaman penceresinden zaman sırasıyla birkaç kare ve o penceredeki
tespit/sinyal özeti verilir.

Kurallar:
- Kareleri tek tek anlatma. Aralarında NE DEĞİŞTİĞİNİ yaz — hareket, duruş,
  yeni giren ya da kadrajdan çıkan nesne.
- Sadece GÖRDÜĞÜNÜ yaz. Emin değilsen "olası" de.
- Türkçe, tek-iki kısa cümle, saha terminolojisi.
- Kişi kimliği, yaş, cinsiyet tahmini YAPMA.
- Dikkat çekici bir şey yoksa notable_event null olsun.

Sadece JSON döndür."""

# Çıplak alan adı (pydantic'in otomatik başlığı "Notable Event") küçük yerel
# VLM'e içerik üretirken tutunacak hiçbir şey vermiyordu: zayıf/belirsiz
# hareket sinyali olan karelerde değer olarak alan adının kendisini geri
# yazmaya başladı (bir gerçek karede 4/4 tekrarlandı). Geçerli bir değerin
# neye benzediğini şemada hecelemek o döngüyü kapatıyor.
_NOTABLE_EVENT_DESCRIPTION = (
    "Görüntüde ya da hareket verisinde gerçekten dayanağı olan dikkat çekici "
    "bir olayı anlatan kısa ve somut bir cümle; öyle bir olay yoksa null. "
    "Asla 'notable_event' ya da başka bir yer tutucu metin olmasın.")

# Şema/prompt düzeyindeki önlem olasılıksal bir hataya olasılıksal bir çözüm;
# bu, tekrarını yakalayan mekanik güvenlik ağı. Model bunlardan birini değer
# olarak yazarsa "olay yok" diye okunur.
_NOTABLE_EVENT_PLACEHOLDERS = {
    "notable_event", "notable event", "none", "null", "n/a",
    "yok", "placeholder", "yer tutucu",
}

_SENTENCE_END = (".", "!", "?")
# Sınıra "ne kadar yakınsa kesilmiş sayılır" penceresi. Kod çözücü her zaman
# tam sınıra oturmuyor (gözlenen: bir kare tam 300, bir başkası 296 karakterde
# kesildi) — sabit 1 karakterlik tolerans gevşek olanı kaçırıyor.
_BOUNDARY_SLACK = 10

# Üst sınır olmadan strict-JSON şema kod çözümü dizi alanlarında kaçak tekrara
# giriyor: uydurma etiketleri `max_tokens` tükenene kadar yineliyor, JSON hiç
# kapanmıyor ve sonraki alanlara hiç ulaşılmıyor. Bugünkü görü şemasında dizi
# yok; sınır şema sertleştiricisinde duruyor ki bir dizi eklendiği an korumasız
# kalmasın.
_MAX_ARRAY_ITEMS = 8


def strict_schema(schema: dict) -> dict:
    """JSON şemasını OpenAI **strict** structured outputs'a uygun hâle getirir.

    Strict mod HER alanın `required` içinde olmasını ister; pydantic ise
    varsayılanı olan alanı listeden düşürür. `notable_event`'in varsayılanı
    var — yani düz `model_json_schema()` gerçek gateway'de 400 üretiyor,
    denemeler tükeniyor, kademe `degraded` oluyor ve yorumlayıcı HER pencere
    için `None` dönüyor. Sistem çalışıyor görünüp hiçbir şey üretmiyor.

    `maxLength` de çıkarılıyor: `Field(max_length=…)` onu şemaya basıyor ve
    strict-mod arka uçları bunu yaygın olarak reddediyor. Sınır pydantic
    modelinde kalır, kesme `_sanitize_text` ile Python tarafında yapılır.

    Girdi kopyalanır; çağıranın sözlüğü değişmez.
    """
    hardened = copy.deepcopy(schema)
    _harden(hardened)
    return hardened


def _harden(node) -> None:
    if isinstance(node, dict):
        node.pop("maxLength", None)
        if node.get("type") == "array":
            node.setdefault("maxItems", _MAX_ARRAY_ITEMS)
        if "properties" in node:
            node["additionalProperties"] = False
            node["required"] = list(node["properties"])
        for value in list(node.values()):
            _harden(value)
    elif isinstance(node, list):
        for value in node:
            _harden(value)


class _VisionResponse(BaseModel):
    """Görü kademesinden beklenen çıktı. Uzunluk sınırları burada kalır —
    şemadan çıkarılırlar (bkz. `strict_schema`), doğrulamadan çıkmazlar."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(max_length=MAX_DESCRIPTION)
    notable_event: str | None = Field(default=None, max_length=MAX_NOTABLE_EVENT,
                                      description=_NOTABLE_EVENT_DESCRIPTION)

    @classmethod
    def model_json_schema(cls, *args, **kwargs) -> dict:
        """`Gateway.ask` şemayı buradan üretiyor; sertleştirme tek noktada
        kalsın diye üretimin kendisi eziliyor."""
        return strict_schema(super().model_json_schema(*args, **kwargs))


def _sanitize_text(text: str, max_length: int) -> str:
    """Uzunluk sınırlı bir metin alanını (`description` / `notable_event`)
    temizler.

    Gerçek karelerde gözlenen, ikisi de pydantic doğrulamasından sessizce
    geçen iki belirti:
    - kapanış tırnağından hemen önce eklenmiş ham bir kontrol karakteri
      (kare 0011: "...roof of the building. There\\x01")
    - tam sınırda, hata vermeden yarım kelimede kesilme (kare 0005:
      "...a building in the")

    Şemadan `maxLength` çıktığı için kesme artık bize düşüyor; kesilmiş metnin
    yarım kalan son kelimesi de aynı şekilde budanıyor.
    """
    cleaned = text
    while cleaned and not cleaned[-1].isprintable():
        cleaned = cleaned[:-1]
    cleaned = cleaned.rstrip()

    original_length = len(cleaned)
    if original_length > max_length:
        cleaned = cleaned[:max_length].rstrip()

    # Metin sınıra oturmuşsa ve cümle sonuyla bitmiyorsa, büyük olasılıkla
    # yarım kelimede kesildi — sarkan parçayı bırakmaktansa son tam kelimeye
    # geri budanır.
    at_boundary = original_length >= max_length - _BOUNDARY_SLACK
    if at_boundary and not cleaned.endswith(_SENTENCE_END):
        trimmed, _, _ = cleaned.rpartition(" ")
        if trimmed:
            cleaned = trimmed.rstrip()

    return cleaned


def frame_data_uri(frame_path: str | Path) -> str:
    """Kareyi base64 data-URI'ye gömer.

    Uzaktaki gateway yerel dosya yolunu okuyamaz; `interpret.py` görüntüyü
    `{"url": str(frame_path)}` diye gönderiyor ve bu yüzden gateway'e karşı
    hiç çalışamıyor.
    """
    path = Path(frame_path)
    kind = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{kind};base64,{payload}"


def _frame_timestamps(window: list[Observation]) -> list[float]:
    """Pencerenin ilk, orta ve son karesi — sırayla, yinelenenler atılmış.

    Tek kare yetmiyor: devrilen bir istif aracı bir hareket olayı, tek durağan
    görüntü onu ya hâlâ ayakta ya da çoktan yerde gösterir. Yönlendirici hangi
    pencerenin VLM'e ulaşacağını zaten süzdüğü için işaretlenmemiş pencereler
    yine hiçbir şeye mal olmuyor.
    """
    picks = [window[0].ts, window[len(window) // 2].ts, window[-1].ts]
    ordered: list[float] = []
    for ts in picks:
        if ts not in ordered:
            ordered.append(ts)
    return ordered


def _context(window: list[Observation]) -> str:
    labels = sorted({d.label for o in window for d in o.detections})
    middle = window[len(window) // 2]
    signals = middle.signals
    parts = [f"tespitler: {', '.join(labels) or 'yok'}",
             f"kişi sayısı: {signals.person_count}"]
    if signals.velocities:
        parts.append("hızlar: " + ", ".join(
            f"{track_id}:{speed:.1f}" for track_id, speed in signals.velocities.items()))
    if signals.vanished_tracks:
        parts.append(f"kadraj dışına çıkan: {signals.vanished_tracks}")
    return " | ".join(parts)


def _message(window: list[Observation], images: list[dict],
             stamps: list[float]) -> list[dict]:
    """Çok parçalı istek gövdesini kuran tek yer.

    Kareler satır içi base64 gidiyor, çekilebilir URL olarak değil: modeller
    verinin yerelde kalması için organizasyonun kendi sunucusunda ayakta ve
    URL isteyen bir gateway görüntüyü almak için dışarı çıkmak zorunda kalırdı
    (decision-log, 23 Ağustos). Kalan risk içerik biçiminin sunucuya göre
    değişmesi — bozulursa düzeltilecek tek yer burası.
    """
    stamp_line = ", ".join(f"{ts:.1f}s" for ts in stamps)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": [
            {"type": "text",
             "text": (f"Sinyaller — {_context(window)}\n\n"
                      f"Aşağıdaki {len(images)} kare zaman sırasıyla "
                      f"{stamp_line} anlarına ait. Bu pencerede ne oluyor, "
                      f"kareler arasında ne değişiyor?")},
            *images]}]


def _parse(content: str) -> _VisionResponse | None:
    """Modelin ham çıktısını doğrulanmış bir yanıta çevirir; olmazsa `None`.

    Kesme doğrulamadan ÖNCE yapılıyor: şemada `maxLength` olmadığı için model
    sınırı aşabilir ve pydantic'e olduğu gibi verilirse kayıt tamamen düşerdi.
    """
    try:
        data = json.loads(content)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    description = data.get("description")
    if not isinstance(description, str):
        return None
    data["description"] = _sanitize_text(description, MAX_DESCRIPTION)

    notable_event = data.get("notable_event")
    if isinstance(notable_event, str):
        cleaned = _sanitize_text(notable_event, MAX_NOTABLE_EVENT)
        if not cleaned or cleaned.strip().lower() in _NOTABLE_EVENT_PLACEHOLDERS:
            cleaned = None
        data["notable_event"] = cleaned

    try:
        return _VisionResponse(**data)
    except Exception:  # noqa: BLE001 — bozuk çıktı bir koşuyu düşürmemeli
        return None


def interpret(gw, store, window: list[Observation],
              frame_for) -> Interpretation | None:
    """Pencereyi görü kademesine sorar, sonucu depoya yazar.

    `frame_for`: bir `ts` alıp o ana ait kare dosya yolunu (ya da `None`)
    döndüren çağrılabilir.

    `None`'ın dört ayrı anlamı var ve ayrımı `DecisionLoop` için önemli — o
    pencereyi YALNIZCA görü kademesi gerçekten bozukken erteliyor:
    boş pencere, hiç kare bulunamaması ve ayrıştırılamayan çıktı kesinti
    DEĞİL; yalnızca `response.degraded` kesintidir.
    """
    if not window:
        return None

    images = []
    stamps = []
    for ts in _frame_timestamps(window):
        path = frame_for(ts)
        if path is None:
            continue
        images.append({"type": "image_url",
                       "image_url": {"url": frame_data_uri(path)}})
        stamps.append(ts)
    if not images:
        return None

    middle = window[len(window) // 2]

    response = gw.ask("vlm", _message(window, images, stamps),
                      schema=_VisionResponse,
                      max_tokens=MAX_TOKENS,
                      temperature=TEMPERATURE)

    # Açık kesinti guard'ı. `json.loads("")`'ın tesadüfen istisna atmasına
    # güvenilmiyor: bozuk yanıt bir gün boş olmayan içerikle gelirse (ör.
    # önbellekten dönen bayat gövde) o tesadüf çalışmaz.
    if response.degraded:
        return None
    if not (response.content or "").strip():
        return None

    parsed = _parse(response.content)
    if parsed is None:
        return None

    interpretation = Interpretation(
        observation_ts=middle.ts,
        description=parsed.description,
        notable_event=parsed.notable_event,
        model=response.model,
        latency_ms=response.latency_ms,
        tokens=response.tokens)
    interpretation.id = store.save_interpretation(interpretation)
    return interpretation
```

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_interpreter.py -v
```
Beklenen: 34 passed

### 5. Commit

```bash
git add gozcu/agents/__init__.py gozcu/agents/interpreter.py \
        tests/test_interpreter.py gozcu/gateway.py tests/test_gateway.py
git commit -m "feat: VLM interpreter adapter with hardened strict-mode schema"
```

## Doğrulama

```bash
uv run pytest tests/test_interpreter.py -v
```
Beklenen: **34 passed**

## Tamamlanma notları (gelecek görevleri bağlayan)

- **Şema sertleştirmesi gateway'in içine taşındı** (`gozcu/gateway.py`,
  `f9e5029`); bu dosya onu yalnızca yeniden dışa veriyor. `Gateway.ask()`'e
  düz bir pydantic modeli ver; `strict_schema()`'i kimse elle çağırmıyor —
  burada bir kural olarak yaşarken üç görev dosyası onu unuttu. Düz
  `model_json_schema()` varsayılanı olan alanı `required` listesinden
  düşürüyor, strict structured outputs ise HER alanın orada olmasını istiyor:
  sonuç gerçek gateway'de sessiz bir 400, tükenen denemeler, `degraded` bir
  kademe ve **her pencere için `None`** dönen bir yorumlayıcı. Sistem ayakta
  görünür, hiçbir şey üretmez, test takımı yeşildir.
- **Sertleştirmenin bedeli: sınırlar artık tele hiç çıkmıyor.** Sökülen
  anahtarlar `maxLength`, `minLength`, `pattern`, `format`, `minimum`,
  `maximum`, `exclusiveMinimum`, `exclusiveMaximum`, `multipleOf` — hepsi
  pydantic modelinde kalır, doğrulama gücünden bir şey kaybedilmez. Ama model
  artık sınırı aşabilir, yani **her ajan doğrulamadan ÖNCE kendi değerlerini
  temizlemek zorunda** (`_sanitize_text` burada, Görev 06'daki `_sanitize`
  aynı sebeple). `maxItems` bilerek listede değil: kaçak tekrar hatasına karşı
  tek koruma o.
- **`ask()` şemalı istek tükendiğinde şemasız bir son deneme yapıyor.**
  Reddedilen bir şema kesintiden ayırt edilemeyip kademeyi sonsuza dek
  `degraded` bırakırdı; prompt'la istenen JSON'a düşmek tam kaybı kurtarıyor.
  Bedeli: dönen içerik iyi biçimli JSON olmayabilir — ayrıştırıcılar bunu
  varsaymamalı.
- **Pencere başına üç kare gidiyor: ilk, orta, son.** Kısa pencerede
  yinelenenler atılıyor, bulunamayan kare atlanıyor, kalanla devam ediliyor.
  Tek kare yetmiyordu: devrilen bir istif aracı bir *hareket* olayı — tek
  durağan görüntü onu ya hâlâ ayakta ya da çoktan yerde gösterir.
- **`Interpretation.observation_ts` pencerenin ORTA zaman damgası**, `window[0].ts`
  değil. Görev 07 yorumu pencereye geri bağlarken ilkini varsaymamalı.
- **`Gateway.ask()` artık isteğe bağlı `max_tokens` / `temperature` alıyor;**
  yalnızca geçildiklerinde istekte görünüyorlar. Token tavanı kod çözücünün
  kaçak tekrar hatasını kapatan şey: üst sınır olmadan JSON hiç kapanmıyor.
- **`interpret.py`'dan dört koruma taşındı ve hiçbiri teori değil** — dördü de
  gerçek karelerde gözlenmiş hatalar: `required` ezmesi, `notable_event` yer
  tutucu güvenlik ağı (bir gerçek karede 4/4 tekrarlandı), `maxItems` kaçak
  tekrar sınırı ve kesilmiş betimleme onarımı. "Sadeleştirip" atma.
- **Kareler satır içi base64 gidiyor, çekilebilir URL olarak değil.** Modeller
  verinin yerelde kalması için kendi sunucumuzda ayakta; URL isteyen bir
  gateway görüntüyü almak için dışarı çıkardı ve bunu boşa çıkarırdı. İçerik
  biçimi sunucuya göre değişirse değiştirilecek tek yer `_message()`.
- **`None`'ın iki ayrı anlamı var.** Boş pencere / hiç kare bulunamaması /
  ayrıştırılamayan çıktı kesinti **değil**; yalnızca `response.degraded`
  kesintidir. `DecisionLoop` pencereyi sadece ikinci durumda erteliyor.
