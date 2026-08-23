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
