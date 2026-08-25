# Görev 04 — Yorumlayıcı adaptörü (`gozcu/agents/interpreter.py`)

> ## ✅ TAMAMLANDI — 23 Ağustos 2026, `89f7c21`
>
> **25 Ağustos: video pencerelerine geçildi — `886342a`.** Gerçek gateway'de `vlm` görüntü kabul etmiyor.
>
> **Yorumlayıcı indi.** `gozcu/agents/interpreter.py` var,
> `tests/test_interpreter.py` 35 test fonksiyonu / 41 durum ile yeşil. Bu
> dosyayı yeniden uygulama — aşağısı ne yapıldığının kaydı.
>
> **Sonraki göreve başlarken bilmen gerekenler**
> ([kararlar](#tamamlanma-notları-gelecek-görevleri-bağlayan) bölümüne bak):
> pencere başına **tek bir satır içi video klibi** gidiyor — kare değil, ve
> klibi kesen taraf Görev 17; **şema sertleştirmesi artık gateway'in içinde** —
> `Gateway.ask()`'e düz bir pydantic modeli verilir, `strict_schema()`'i kimse
> elle çağırmaz, ama sınırlar tele çıkmadığı için **her ajan doğrulamadan önce
> kendi değerlerini temizlemek zorunda**; ve `Gateway.ask()` artık isteğe bağlı
> `max_tokens` / `temperature` alıyor.

**Bağımlılık:** [01](01-sozlesme.md), [02](02-olay-deposu.md), [03](03-gateway.md)

## Bağlam

Mevcut `gozcu/interpret.py` çalışıyor ama **uzak gateway'e konuşamaz.** İki
sebepten:

1. Kendi `OpenAI` istemcisini `VLM_BASE_URL`'e karşı kuruyor — `Gateway`'i
   baypas ediyor. Bu yüzden `hata_enjekte({"vlm"})` gerçek VLM çağrılarını
   yönetmiyor: demo sırasında bastığımız "bağlantıyı kes" düğmesi
   **hiç kullanılmayan bir katmanı** kesiyor olurdu.
2. `interpret.py:171` yükü `{"url": str(frame_path)}` diye gönderiyor — yerel
   bir dosya yolu. Uzaktaki bir gateway o dosyayı okuyamaz; yükün base64
   data-URI olarak gömülmesi gerekiyor.

**Pencere kare değil, kliptir.** Bu görevin ilk sürümü pencere başına üç base64
JPEG gönderiyordu; 24 Ağustos'ta gerçek gateway'de ölçüldü ki o tasarım hiçbir
kademede çalışmıyor: `vlm` görüntüye `At most 0 image(s) may be provided in one
request.` diyerek 400 veriyor — model görüntü yeteneğine sahip, ama bu kurulum
kodlayıcı piksel bütçesinin tamamını video çözünürlüğüne ayırdığı için görüntü
kapasitesi bilinçli olarak sıfır. Görüntü kabul eden `llm-fast` / `llm-large`
ise istek başına en fazla İKİ tane alıyor; üç kare oraya da sığmıyor. Pencere
artık **tek bir satır içi mp4 klibi** olarak gidiyor
([EVREN saha notları](../06-references/evren-gateway.md)).

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
clip_data_uri(clip_path: str | Path) -> str        # "data:video/mp4;base64,..."
interpret(gw, store, window: list[Observation], clip_for) -> Interpretation | None
```

`interpret` pencerenin tamamını kapsayan **tek bir mp4 klibini**
`clip_for(window[0].ts, window[-1].ts)` ile ister, base64 data-URI'ye gömer,
`gw.ask("vlm", ...)` ile yorumlatır, `Interpretation` üretip depoya yazar.
Üretilen kaydın `observation_ts` alanı pencerenin **orta** zaman damgasıdır.
Klibi bu modül kesmiyor — kesme işi Görev 17'nin adaptörünün, böylece burası
ffmpeg olmadan test edilebiliyor. `clip_for` `None` dönerse istek hiç gitmez.
Görü kademesi bozulmuşsa da `None` döner — çağıran taraf bunu bekliyor.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_interpreter.py`

```python
"""Yorumlayıcı adaptörünün testleri.

Sahte gateway bilerek `Mock()` değil: bu depoda beş kusur şekilsiz bir
`Mock()` collaborator'ın arkasında saklandı. `_FakeGateway` ne ile
çağrıldığını kaydeder ve gerçek bir `Response` döndürür — şema, mesajlar ve
üretim parametreleri tek tek incelenebilir.

24 Ağustos'ta gerçek gateway'e bağlandık ve pencere başına üç base64 KARE
gönderen tasarımın hiçbir kademede çalışmadığı ölçüldü: `vlm` görüntüye
`At most 0 image(s) may be provided in one request.` diyerek 400 veriyor
(kodlayıcı piksel bütçesinin tamamı videoya ayrılmış), `llm-fast`/`llm-large`
ise istek başına en fazla iki görüntü alıyor. Bu yüzden buradaki testler
pencerenin **tek bir satır içi video klip** olarak gittiğini ve isteğe
**hiçbir görüntü parçasının** girmediğini doğruluyor.
"""

import base64
import json
from unittest.mock import Mock, patch

import pytest
from pydantic import BaseModel, ConfigDict

from gozcu.agents.interpreter import (MAX_TOKENS, SYSTEM_PROMPT,
                                      _sanitize_text, _VisionResponse,
                                      clip_data_uri, interpret, strict_schema)
from gozcu.gateway import Gateway, Response
from gozcu.models import Detection, Observation, Signals
from gozcu.store import Store

_CLIP_BYTES = b"\x00\x00\x00\x18ftypmp42sahte-klip"


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


def _clip(tmp_path):
    path = tmp_path / "pencere.mp4"
    path.write_bytes(_CLIP_BYTES)
    return path


def _clip_for(tmp_path):
    """Görev 17'nin sağlayacağı kapanışın sahtesi: (start_ts, end_ts) -> Path."""
    return lambda start_ts, end_ts: _clip(tmp_path)


def _parts(messages: list[dict], kind: str) -> list[dict]:
    return [p for p in messages[-1]["content"] if p["type"] == kind]


def _text_part(messages: list[dict]) -> str:
    return next(p["text"] for p in messages[-1]["content"] if p["type"] == "text")


# --- clip_data_uri --------------------------------------------------------

def test_data_uri_embeds_the_clip_not_a_path(tmp_path):
    path = tmp_path / "pencere.mp4"
    path.write_bytes(_CLIP_BYTES)
    uri = clip_data_uri(path)
    assert uri.startswith("data:video/mp4;base64,")
    assert base64.b64decode(uri.split(",", 1)[1]) == _CLIP_BYTES
    assert str(path) not in uri


def test_data_uri_always_declares_mp4(tmp_path):
    """Doğrulanmış istek biçimi `data:video/mp4;base64,…`. Uzantıdan tür
    tahmini yapılmıyor: klibi kesen taraf uzantıyı unutursa `mimetypes`
    `None` döner ve gateway'e tür bildirmeyen bir URI gider."""
    path = tmp_path / "uzantisiz"
    path.write_bytes(_CLIP_BYTES)
    assert clip_data_uri(path).startswith("data:video/mp4;base64,")


# --- pencere tek bir video klip olarak gidiyor (RULING 1 / RULING 5) -------

def test_the_window_is_sent_as_one_inline_video_clip(tmp_path):
    """`vlm` görüntü kabul etmiyor (`At most 0 image(s)`); pencere videodur."""
    gw = _FakeGateway()
    interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
    videos = _parts(gw.last["messages"], "video_url")
    assert len(videos) == 1
    url = videos[0]["video_url"]["url"]
    assert url.startswith("data:video/mp4;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == _CLIP_BYTES


def test_no_image_part_ever_reaches_the_gateway(tmp_path):
    """Kare göndermeye geri dönen bir düzenleme burada patlar: `vlm`'in
    görüntü kapasitesi bilinçli olarak sıfır, dönen şey 400."""
    gw = _FakeGateway()
    interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
    assert _parts(gw.last["messages"], "image_url") == []
    assert "image_url" not in json.dumps(gw.last["messages"])
    assert "data:image/" not in json.dumps(gw.last["messages"])


def test_the_clip_is_cut_for_the_whole_window(tmp_path):
    """Klip pencerenin ilk ve son gözlemi arasını kapsar — tek an değil."""
    asked: list[tuple[float, float]] = []

    def clip_for(start_ts, end_ts):
        asked.append((start_ts, end_ts))
        return _clip(tmp_path)

    interpret(_FakeGateway(), Store(":memory:"), _window(), clip_for)
    assert asked == [(0.0, 9.0)]


def test_a_single_observation_window_still_asks_for_a_clip(tmp_path):
    asked: list[tuple[float, float]] = []

    def clip_for(start_ts, end_ts):
        asked.append((start_ts, end_ts))
        return _clip(tmp_path)

    window = [Observation(ts=3.0, signals=Signals(person_count=1))]
    result = interpret(_FakeGateway(), Store(":memory:"), window, clip_for)
    assert asked == [(3.0, 3.0)]
    assert result is not None


def test_the_prompt_asks_what_changes_across_the_window(tmp_path):
    """Model bir anı resimlemesin diye isteniyor: pencere boyunca NE OLDUĞU
    ve NE DEĞİŞTİĞİ. Devrilme bir hareket olayı."""
    gw = _FakeGateway()
    interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
    text = _text_part(gw.last["messages"])
    assert "değiş" in text.lower() or "değiş" in SYSTEM_PROMPT.lower()
    assert "tespitler:" in text
    assert "detections" not in text


def test_the_prompt_places_the_clip_on_the_video_timeline(tmp_path):
    """Karar olay anında veriliyor; modelin gördüğü pencerenin videonun
    saatinde nereye düştüğü isteğin içinde olmalı."""
    gw = _FakeGateway()
    interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
    text = _text_part(gw.last["messages"])
    assert "0.0" in text and "9.0" in text


# --- token tavanı (RULING 3) ----------------------------------------------

def test_token_ceiling_leaves_room_for_a_full_description(tmp_path):
    """Canlı ölçümde 400 tavanı cümlenin ortasında kesti. Alt sınır oradan;
    üst sınır ise kaçak tekrara karşı tavanın anlamlı kalması için."""
    assert MAX_TOKENS > 400
    assert MAX_TOKENS <= 2048


# --- strict şema ----------------------------------------------------------

def test_schema_handed_to_the_gateway_lists_every_property_as_required(tmp_path):
    """OpenAI strict structured outputs HER alanın `required` içinde olmasını
    ister. `notable_event`'in varsayılanı olduğu için pydantic onu listeden
    düşürüyor; gerçek gateway buna 400 veriyor, denemeler tükeniyor,
    `degraded=True` oluyor ve `interpret` HER pencere için `None` dönüyor —
    sistem yeşil test takımıyla birlikte sessizce hiçbir şey üretmiyor."""
    gw = _FakeGateway()
    interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
    schema = gw.last["schema"].model_json_schema()
    assert set(schema["required"]) == set(schema["properties"])
    assert "notable_event" in schema["required"]


def test_schema_handed_to_the_gateway_carries_no_max_length(tmp_path):
    """`Field(max_length=…)` şemaya `maxLength` basıyor; strict-mode arka
    uçları bunu yaygın olarak reddediyor. Sınır pydantic modelinde kalır,
    şemadan çıkar, kesme Python tarafında yapılır."""
    gw = _FakeGateway()
    interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
    schema = gw.last["schema"].model_json_schema()
    assert "maxLength" not in json.dumps(schema)


def test_the_plain_pydantic_model_is_handed_over_not_a_hardened_dict(tmp_path):
    """Sertleştirme `Gateway.ask()`'in işi; çağıran `strict_schema`'i elle
    çağırmıyor. Şema yerine sözlük geçirilirse gateway onu modelmiş gibi
    kullanmaya çalışır."""
    gw = _FakeGateway()
    interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
    assert gw.last["schema"] is _VisionResponse


def test_schema_handed_to_the_gateway_forbids_additional_properties(tmp_path):
    gw = _FakeGateway()
    interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
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
    interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
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


# --- gateway'e gerçekten ulaşan istek -------------------------------------

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
        interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
        request = client.chat.completions.create.call_args.kwargs

    schema = request["response_format"]["json_schema"]["schema"]
    assert request["response_format"]["json_schema"]["strict"] is True
    assert set(schema["required"]) == set(schema["properties"])
    assert "maxLength" not in json.dumps(schema)
    assert request["max_tokens"] > 400
    assert 0.0 <= request["temperature"] <= 1.0
    assert "image_url" not in json.dumps(request["messages"])
    assert "video_url" in json.dumps(request["messages"])


def test_generation_controls_are_passed_to_the_gateway(tmp_path):
    gw = _FakeGateway()
    interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
    assert gw.last["max_tokens"] == MAX_TOKENS
    assert gw.last["temperature"] is not None


# --- temel akış -----------------------------------------------------------

def test_interpret_sends_through_the_vlm_tier(tmp_path):
    gw = _FakeGateway(Response(
        content='{"description":"İstif aracı yan yattı.","notable_event":null}',
        model="vlm-test", latency_ms=420, tokens=180))
    result = interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
    assert gw.last["tier"] == "vlm"
    assert result.description == "İstif aracı yan yattı."
    assert result.model == "vlm-test"
    assert result.latency_ms == 420 and result.tokens == 180


def test_interpretation_is_persisted_with_the_window_timestamp(tmp_path):
    gw = _FakeGateway(Response(content='{"description":"tamam"}', model="v"))
    store = Store(":memory:")
    result = interpret(gw, store, _window(), _clip_for(tmp_path))
    assert store.interpretations()[0].observation_ts == 5.0
    assert result.id == store.interpretations()[0].id


# --- None'ın dört ayrı anlamı (RULING 2 / RULING 6) -----------------------

def test_empty_window_is_none_without_asking_the_gateway():
    gw = _FakeGateway()
    assert interpret(gw, Store(":memory:"), [], lambda s, e: None) is None
    assert gw.calls == []


def test_missing_clip_is_none_and_never_a_text_only_request():
    """Klip kesilemediyse istek hiç gitmez. Metin-only bir istek gönderip
    'video analizi' diye kaydetmek sessizce uydurma üretmek olurdu."""
    gw = _FakeGateway()
    store = Store(":memory:")
    assert interpret(gw, store, _window(), lambda s, e: None) is None
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
    assert interpret(gw, store, _window(), _clip_for(tmp_path)) is None
    assert store.interpretations() == []


def test_empty_content_is_none(tmp_path):
    gw = _FakeGateway(Response(content="   ", model="vlm-test"))
    store = Store(":memory:")
    assert interpret(gw, store, _window(), _clip_for(tmp_path)) is None
    assert store.interpretations() == []


def test_empty_content_never_reaches_the_parser(monkeypatch, tmp_path):
    """Boş içerik guard'ı `json.loads("")`'ın tesadüfen istisna atmasına
    DAYANMIYOR. Bozuk bir yanıt bir gün boş olmayan ama anlamsız bir gövdeyle
    gelirse (ör. önbellekten dönen bayat içerik) o tesadüf çalışmaz; guard
    silinirse ayrıştırıcının ürettiği her şey kayıt olur."""
    from gozcu.agents import interpreter
    monkeypatch.setattr(
        interpreter, "_parse",
        lambda content: interpreter._VisionResponse(description="uydurma"))
    gw = _FakeGateway(Response(content="   ", model="vlm-test"))
    store = Store(":memory:")
    assert interpret(gw, store, _window(), _clip_for(tmp_path)) is None
    assert store.interpretations() == []


def test_unparsable_content_is_none(tmp_path):
    gw = _FakeGateway(Response(content="JSON değil", model="vlm-test"))
    store = Store(":memory:")
    assert interpret(gw, store, _window(), _clip_for(tmp_path)) is None
    assert store.interpretations() == []


def test_schema_violating_content_is_none(tmp_path):
    gw = _FakeGateway(Response(content='{"notable_event":"x"}', model="vlm-test"))
    assert interpret(gw, Store(":memory:"), _window(),
                     _clip_for(tmp_path)) is None


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
    """Gateway `maxLength`'i kabul ediyor ama UYGULAMIYOR (24 Ağustos, canlı):
    sınırlı bir alan sınırın çok ötesinde geldi ve pydantic patladı. Kesme
    doğrulamadan önce yapılmazsa kayıt tamamen düşer."""
    long = "Sahada bir kişi var. " * 30
    gw = _FakeGateway(Response(content=json.dumps({"description": long}),
                               model="vlm-test"))
    result = interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
    assert result is not None
    assert len(result.description) <= 300


def test_over_long_notable_event_is_truncated_not_dropped(tmp_path):
    gw = _FakeGateway(Response(content=json.dumps(
        {"description": "tamam",
         "notable_event": "İstif aracı devrildi. " * 20}), model="vlm-test"))
    result = interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
    assert result is not None
    assert len(result.notable_event) <= 200


@pytest.mark.parametrize("value", ["notable_event", "notable event", "none",
                                   "null", "N/A", "placeholder", "  NULL  "])
def test_placeholder_notable_event_is_treated_as_no_event(value, tmp_path):
    gw = _FakeGateway(Response(
        content=json.dumps({"description": "tamam", "notable_event": value}),
        model="vlm-test"))
    result = interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
    assert result.notable_event is None


def test_a_real_notable_event_survives(tmp_path):
    gw = _FakeGateway(Response(
        content=json.dumps({"description": "tamam",
                            "notable_event": "İstif aracı devrildi."}),
        model="vlm-test"))
    result = interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
    assert result.notable_event == "İstif aracı devrildi."


# --- bağlam metni ---------------------------------------------------------

def test_context_lists_detected_labels_in_turkish(tmp_path):
    window = _window()
    window[5].detections = [Detection(label="person", confidence=0.9,
                                      box=(0, 0, 1, 1))]
    gw = _FakeGateway()
    interpret(gw, Store(":memory:"), window, _clip_for(tmp_path))
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
çağrılarını yönetmiyor, ve görüntüyü yerel dosya yolu olarak gönderdiği için
uzaktaki bir gateway onu hiç okuyamıyor. Bu modül arayı kapatıyor: pencere
base64 data-URI olarak gömülüyor, istek `gw.ask("vlm", …)` üzerinden geçiyor.

**Pencere kare değil, kliptir.** İlk sürüm pencere başına üç base64 JPEG
gönderiyordu; 24 Ağustos'ta gerçek gateway'de ölçüldü ki bu tasarım hiçbir
kademede çalışmıyor:

- `vlm` görüntüye 400 veriyor — `At most 0 image(s) may be provided in one
  request.` Model görüntü yeteneğine sahip, ama bu kurulum kodlayıcı piksel
  bütçesinin tamamını video çözünürlüğüne ayırdığı için görüntü kapasitesi
  bilinçli olarak sıfır.
- Görüntü kabul eden `llm-fast` / `llm-large` istek başına en fazla İKİ tane
  alıyor; üç kare oraya da sığmıyor.

Aynı gün gerçek bir 10 saniyelik pencere klip olarak `vlm`'e gönderildi:
11,4 s, 431 KB klip → 561 KB base64, 8.285 token, düzgün Türkçe analiz — ve
**zaman içindeki değişimi** okuyor. Üç durağan karenin taklit etmeye çalıştığı
şey buydu (bkz. `docs/06-references/evren-gateway.md`).

Klibi bu modül kesmiyor: kareler nasıl dışarıdan enjekte ediliyorsa klip de
öyle geliyor (`clip_for`). Kesme işi Görev 17'nin adaptörünün — böylece burası
ffmpeg olmadan test edilebiliyor.

Buradaki çıktı temizleme mantığı gerçek çıktılarda görülmüş hatalardan doğdu;
her birinin gerekçesi ilgili sabitin başında duruyor. Şema sertleştirmesi
(`strict_schema`) artık `gozcu/gateway.py`'da ve `Gateway.ask()` onu her şemaya
kendisi uyguluyor — bir çağıranın unutması mümkün değil.
"""

import base64
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from gozcu.gateway import strict_schema
from gozcu.models import Interpretation, Observation

# Sertleştirme artık `gozcu.gateway`'de yaşıyor ve `Gateway.ask()` onu kendisi
# uyguluyor. Buradan yeniden dışa aktarılıyor: mevcut import'lar çalışmaya
# devam etsin.
__all__ = ["clip_data_uri", "interpret", "strict_schema"]

MAX_DESCRIPTION = 300
MAX_NOTABLE_EVENT = 200

# Token tavanı. Kaçak tekrar (`gozcu.gateway._MAX_ARRAY_ITEMS` notu) yalnızca
# bir üst sınırla tam olarak kapanıyor: sınır yoksa kod çözücü JSON'u hiç
# kapatmadan üretmeye devam ediyor.
#
# 400 ölçülerek elendi: canlı video çağrısında cümlenin ORTASINDA kesti. 300 +
# 200 karakterlik iki alan Türkçede ~250 token, ama video yanıtları uzun
# başlıyor ve JSON iskeleti de pay istiyor.
#
# Diğer yönde de bir duvar var ve daha sinsi: akıl yürütme (reasoning) açıkken
# dar bir `max_tokens` **boş dize** üretiyor — düşünme izi bütçeyi yiyor,
# ayrıştırıcı izi söküyor ve geriye hiçbir şey kalmıyor (ölçülen: 128, 256 ve
# 512'nin üçü de sıfır karakter). Bu modeller için akıl yürütme varsayılan
# olarak kapalı ve öyle kalıyor; 1024 hem tam bir betimlemeye hem zarfa rahat
# yetiyor, hem de tavanın kaçak tekrara karşı anlamını koruyacak kadar dar.
MAX_TOKENS = 1024
# Güvenlik kaydı için düşük ama sıfır değil: sıfır sıcaklık aynı yanlış
# betimlemeyi her karede tekrar üretiyordu.
TEMPERATURE = 0.3

SYSTEM_PROMPT = """Sen bir fabrika güvenlik kamerasını izleyen gözlemcisin.
Sana kameranın kısa bir video kesiti ve o pencereye ait tespit/sinyal özeti
verilir.

Kurallar:
- Tek bir anı resimleme. Klip boyunca NE OLDUĞUNU ve NE DEĞİŞTİĞİNİ yaz —
  hareket, duruş bozulması, hızlanma, devrilme, kadraja giren ya da çıkan
  nesne, yerde kalan kişi.
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


class _VisionResponse(BaseModel):
    """Görü kademesinden beklenen çıktı. Uzunluk sınırları burada kalır —
    şemadan çıkarılırlar (bkz. `strict_schema`), doğrulamadan çıkmazlar."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(max_length=MAX_DESCRIPTION)
    notable_event: str | None = Field(default=None, max_length=MAX_NOTABLE_EVENT,
                                      description=_NOTABLE_EVENT_DESCRIPTION)

    @classmethod
    def model_json_schema(cls, *args, **kwargs) -> dict:
        """`Gateway.ask` artık şemayı kendisi sertleştiriyor; bu ezme yine de
        duruyor ki modeli doğrudan inceleyen kod da sertleştirilmiş şemayı
        görsün. `strict_schema` girdisini kopyalar — iki kez uygulanması
        zararsız."""
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


# Doğrulanmış istek biçiminin MIME türü. Uzantıdan tahmin edilmiyor: klibi
# kesen taraf uzantıyı unutursa `mimetypes` `None` döner ve gateway'e türü
# bildirilmemiş bir data-URI gider.
_CLIP_MIME = "video/mp4"


def clip_data_uri(clip_path: str | Path) -> str:
    """Pencere klibini base64 data-URI'ye gömer.

    Satır içi base64, çekilebilir URL değil: modeller verinin yerelde kalması
    için organizasyonun kendi sunucusunda ayakta ve URL isteyen bir gateway
    videoyu almak için dışarı çıkmak zorunda kalırdı (decision-log, 23
    Ağustos). Uzaktaki gateway zaten yerel dosya yolunu da okuyamaz.
    """
    path = Path(clip_path)
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{_CLIP_MIME};base64,{payload}"


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


def _message(window: list[Observation], clip_uri: str,
             start_ts: float, end_ts: float) -> list[dict]:
    """Çok parçalı istek gövdesini kuran tek yer.

    Parça biçimi organizasyonun dokümanından alındı ve canlı doğrulandı:
    `{"type": "video_url", "video_url": {"url": "data:video/mp4;base64,…"}}`.
    Bir `image_url` parçası buraya asla girmemeli — `vlm`'in görüntü kapasitesi
    sıfır, dönen şey 400. Kalan risk içerik biçiminin sunucuya göre değişmesi;
    bozulursa düzeltilecek tek yer burası.
    """
    span = max(end_ts - start_ts, 0.0)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": [
            {"type": "text",
             "text": (f"Sinyaller — {_context(window)}\n\n"
                      f"Aşağıdaki {span:.1f} saniyelik kamera kesiti videonun "
                      f"{start_ts:.1f}s–{end_ts:.1f}s aralığına ait. Bu "
                      f"pencerede ne oluyor, kesit boyunca ne değişiyor?")},
            {"type": "video_url", "video_url": {"url": clip_uri}}]}]


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
              clip_for) -> Interpretation | None:
    """Pencereyi görü kademesine sorar, sonucu depoya yazar.

    `clip_for`: `(start_ts, end_ts)` alıp o aralığın kısa mp4 klibinin dosya
    yolunu (ya da kesilemediyse `None`) döndüren çağrılabilir. Kesme işi
    burada değil, Görev 17'nin adaptöründe — kareler nasıl enjekte ediliyorsa
    klip de öyle, ve modül ffmpeg olmadan test edilebiliyor.

    **Pencere başına bir klip; pencereler birleştirilmiyor.** Ön ek önbelleği
    (4,8× hızlanma) bütün videoyu tek seferde göndermeyi cazip gösteriyor, ama
    çözünürlük ölçeği klip süresine bağlı: 15 s → 0,95 · 30 s → 0,65 ·
    60 s → 0,47 · 180 s → 0,28. İşlenmiş karede bir token 32×32 piksel ve iki
    tokenin altında kalan nesne hiç çözülemiyor. "Yerde hareketsiz kişi"
    küçük ve düşük kontrastlı bir hedef — çözünürlük hızdan önce gelir.
    `WINDOW_S` = 10 s bu cetvelin iyi ucunda (~0,95) ve tavanların
    (260 s süre, 2,0 fps / 520 kare) çok içinde kalıyor. Pencereleri uzun
    kliplerde toplamak burayı sessizce kör eder.

    `None`'ın dört ayrı anlamı var ve ayrımı `DecisionLoop` için önemli — o
    pencereyi YALNIZCA görü kademesi gerçekten bozukken erteliyor:
    boş pencere, klip kesilememesi ve ayrıştırılamayan çıktı kesinti DEĞİL;
    yalnızca `response.degraded` kesintidir.
    """
    if not window:
        return None

    start_ts, end_ts = window[0].ts, window[-1].ts
    clip_path = clip_for(start_ts, end_ts)
    # Klip yoksa istek hiç gitmez. Metin-only bir istek gönderip sonucu "video
    # analizi" diye kaydetmek sessizce uydurma üretmek olurdu.
    if clip_path is None:
        return None

    middle = window[len(window) // 2]

    response = gw.ask("vlm",
                      _message(window, clip_data_uri(clip_path),
                               start_ts, end_ts),
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
Beklenen: 41 passed

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
Beklenen: **41 passed**

## Tamamlanma notları (gelecek görevleri bağlayan)

- **Pencere tek bir satır içi video klibi olarak gidiyor.** İstek gövdesindeki
  tek görsel parça
  `{"type": "video_url", "video_url": {"url": "data:video/mp4;base64,…"}}` —
  pencere başına bir tane. **Bir `image_url` parçası oraya asla girmemeli:**
  `vlm`'in görüntü kapasitesi bilinçli olarak sıfır (`At most 0 image(s) may be
  provided in one request.`, HTTP 400) çünkü kodlayıcı piksel bütçesinin tamamı
  video çözünürlüğüne ayrılmış, görüntü kabul eden `llm-fast` / `llm-large` ise
  istek başına en fazla İKİ tane alıyor. Testler bunu iki ayrı yerden çitliyor
  (`test_no_image_part_ever_reaches_the_gateway` ve tele giden gövdeyi inceleyen
  `test_the_wire_request_is_strict_safe_and_carries_generation_controls`) —
  kareye geri dönen bir düzenleme orada patlar.
- **Enjekte edilen çağrılabilir artık `clip_for(start_ts, end_ts)`;** dönüşü
  `pathlib.Path | None`. Pencere başına bir kez, `window[0].ts` ve
  `window[-1].ts` ile çağrılıyor. O aralığı kapsayan, okunabilir bir **H.264
  mp4** dosyasının yolunu döndürmeli — kesilemediyse `None`. Klibi kesmek
  Görev 17'nin işi; yorumlayıcı bu yüzden ffmpeg olmadan test edilebiliyor.
- **`None`'ın dört ayrı anlamı var ve ayrımı `DecisionLoop` için önemli.** Boş
  pencere, **klip kesilememesi** ve ayrıştırılamayan çıktı kesinti DEĞİL —
  ilk ikisinde gateway hiç çağrılmıyor bile, dolayısıyla döngü o pencereyi
  ertelememeli. Yalnızca `response.degraded` kesintidir. Klip yoksa istek hiç
  gitmiyor: metin-only bir istek gönderip sonucu "video analizi" diye kaydetmek
  sessizce uydurma üretmek olurdu.
- **Pencere başına bir klip; pencereler asla birleştirilmiyor.** Ön ek
  önbelleği (prefix caching) aynı video üzerinde ardışık sorgularda 4,8×
  hızlanma veriyor ve bütün videoyu tek seferde yükleyip çok soru sormayı cazip
  kılıyor. Reddedildi: çözünürlük ölçeği klip süresine bağlı — 15 s → 0,95 ·
  30 s → 0,65 · 60 s → 0,47 · 180 s → 0,28. İşlenmiş karede bir token 32×32
  piksel ve **iki tokenin altında kalan bir nesne hiç çözülemiyor.** Yerde
  hareketsiz yatan bir kişi küçük ve düşük kontrastlı bir hedef; onu kaybetmek
  kazanılan saniyelerden pahalı — **çözünürlük hızdan önce gelir.** Gerekçe
  `interpret`'in docstring'inde duruyor; sonradan "optimize eden" biri onu
  silmesin.
- **`MAX_TOKENS = 1024`, ve iki duvarın arasında.** 400 canlıda cümlenin
  ORTASINDA kesti — alt sınır oradan. Ters yöndeki duvar daha sinsi: akıl
  yürütme (reasoning) açıkken dar bir tavan **boş dize** döndürüyor (128, 256
  ve 512'nin üçü de sıfır karakter ölçüldü), çünkü düşünme izi bütçeyi tüketiyor
  ve ayrıştırıcı izi söküp atıyor. Akıl yürütme kapalı kalıyor; 1024 hem
  300 + 200 karakterlik Türkçe yükü hem JSON zarfını taşıyor, hem de kaçak dizi
  tekrarına karşı tavanın anlamını koruyacak kadar dar.
- **Şema sertleştirmesi gateway'in içinde** (`gozcu/gateway.py`, `f9e5029`); bu
  dosya onu yalnızca yeniden dışa veriyor. `Gateway.ask()`'e düz bir pydantic
  modeli ver; `strict_schema()`'i kimse elle çağırmıyor — burada bir kural
  olarak yaşarken üç görev dosyası onu unuttu. Düz `model_json_schema()`
  varsayılanı olan alanı `required` listesinden düşürüyor, strict structured
  outputs ise HER alanın orada olmasını istiyor: sonuç gerçek gateway'de sessiz
  bir 400, tükenen denemeler, `degraded` bir kademe ve **her pencere için
  `None`** dönen bir yorumlayıcı. Sistem ayakta görünür, hiçbir şey üretmez,
  test takımı yeşildir.
- **Sertleştirmenin bedeli: sınırlar artık tele hiç çıkmıyor.** Sökülen
  anahtarlar `maxLength`, `minLength`, `pattern`, `format`, `minimum`,
  `maximum`, `exclusiveMinimum`, `exclusiveMaximum`, `multipleOf` — hepsi
  pydantic modelinde kalır, doğrulama gücünden bir şey kaybedilmez. Ama model
  artık sınırı aşabilir, yani **her ajan doğrulamadan ÖNCE kendi değerlerini
  temizlemek zorunda** (`_sanitize_text` burada, Görev 06'daki `_sanitize` aynı
  sebeple). Gateway `maxLength`'i kabul ediyor ama **UYGULAMIYOR** — 24 Ağustos,
  canlı: sınırlı bir alan sınırın çok ötesinde geldi ve kesme doğrulamadan önce
  yapılmasa kayıt tamamen düşecekti. `maxItems` bilerek sökülenler listesinde
  değil: kaçak tekrar hatasına karşı tek koruma o.
- **`ask()` şemalı istek tükendiğinde şemasız bir son deneme yapıyor.**
  Reddedilen bir şema kesintiden ayırt edilemeyip kademeyi sonsuza dek
  `degraded` bırakırdı; prompt'la istenen JSON'a düşmek tam kaybı kurtarıyor.
  Bedeli: dönen içerik iyi biçimli JSON olmayabilir — ayrıştırıcılar bunu
  varsaymamalı.
- **`notable_event` yer tutucu güvenlik ağı duruyor.** Küçük VLM, çıplak alan
  adından başka tutunacak bir şey bulamayınca değer olarak alan adının kendisini
  geri yazdı (bir gerçek karede 4/4). Şema açıklaması olasılıksal önlem,
  `_NOTABLE_EVENT_PLACEHOLDERS` ise tekrarını yakalayan mekanik ağ. "Sadeleştirip"
  atma.
- **`degraded` ve boş içerik guard'ları AYRI ve ikisi de açık.** `degraded`
  guard'ı geçerli JSON taşıyan bozuk bir yanıtta da tutuyor; boş içerik guard'ı
  `json.loads("")`'ın tesadüfen istisna atmasına dayanmıyor, çünkü bozuk bir
  yanıt bir gün boş olmayan ama anlamsız bir gövdeyle gelirse o tesadüf çalışmaz.
  Her ikisinin de kendi mutasyon testi var.
- **`Interpretation.observation_ts` pencerenin ORTA zaman damgası**,
  `window[0].ts` değil. Görev 07 yorumu pencereye geri bağlarken ilkini
  varsaymamalı.
- **`Gateway.ask()` isteğe bağlı `max_tokens` / `temperature` alıyor;** yalnızca
  geçildiklerinde istekte görünüyorlar.
- **Klip satır içi base64 gidiyor, çekilebilir URL olarak değil.** Modeller
  verinin yerelde kalması için organizasyonun kendi sunucusunda ayakta; URL
  isteyen bir gateway videoyu almak için dışarı çıkardı ve bunu boşa çıkarırdı.
  İçerik biçimi sunucuya göre değişirse değiştirilecek tek yer `_message()`.
- **Canlı doğrulama** (25 Ağustos, `vlm`, 10 saniyelik gerçek forklift
  penceresi, 431 KB klip, 4,8 s):

  > *"Bir forklift, başka bir forklifti yükleyerek yüksek bir konumda tutuyor.
  > Yüklenmiş forklift, **hafifçe sallanıyor**; alttaki forklift sabit durumda.
  > Arka planda bina penceresinde iki kişi izliyor."*
  >
  > `notable_event: "yüklenmiş forkliftin hafif sallanması"`

  "Hafifçe sallanıyor" tam olarak üç durağan karenin veremeyeceği cümle:
  model zaman içindeki değişimi okuyor. Bu, kare→video geçişinin bir gerileme
  değil iyileşme olduğunun kanıtı.
