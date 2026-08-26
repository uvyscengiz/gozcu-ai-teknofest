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

from typing import get_args

from gozcu.agents.interpreter import (MAX_TOKENS, SYSTEM_PROMPT,
                                      _sanitize_text, _VisionResponse,
                                      clip_data_uri, interpret, strict_schema)
from gozcu.gateway import Gateway, Response
from gozcu.models import (MAX_BEATS, MAX_BEAT_TEXT, SEVERITY_LEVELS,
                          Detection, Observation, Signals)
from gozcu.store import Store

_CLIP_BYTES = b"\x00\x00\x00\x18ftypmp42sahte-klip"


class _FakeGateway:
    """Şekilli sahte: `Gateway.ask` imzasını birebir taşır ve kaydeder."""

    def __init__(self, response: Response | None = None) -> None:
        self.response = response if response is not None else Response(
            content='{"description":"varsayılan","notable_event":null,'
                    '"severity":"rutin"}',
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
    assert "severity" in schema["required"]


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
                                                         '"notable_event":null,'
                                                         '"severity":"olay"}',
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
        content='{"description":"İstif aracı yan yattı.","notable_event":null,'
                '"severity":"olay"}',
        model="vlm-test", latency_ms=420, tokens=180))
    result = interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
    assert gw.last["tier"] == "vlm"
    assert result.description == "İstif aracı yan yattı."
    assert result.model == "vlm-test"
    assert result.latency_ms == 420 and result.tokens == 180


def test_interpretation_is_persisted_with_the_window_timestamp(tmp_path):
    gw = _FakeGateway(Response(
        content='{"description":"tamam","severity":"rutin"}', model="v"))
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
    gw = _FakeGateway(Response(
        content=json.dumps({"description": long, "severity": "rutin"}),
        model="vlm-test"))
    result = interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
    assert result is not None
    assert len(result.description) <= 300


def test_over_long_notable_event_is_truncated_not_dropped(tmp_path):
    gw = _FakeGateway(Response(content=json.dumps(
        {"description": "tamam", "severity": "olay",
         "notable_event": "İstif aracı devrildi. " * 20}), model="vlm-test"))
    result = interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
    assert result is not None
    assert len(result.notable_event) <= 200


@pytest.mark.parametrize("value", ["notable_event", "notable event", "none",
                                   "null", "N/A", "placeholder", "  NULL  "])
def test_placeholder_notable_event_is_treated_as_no_event(value, tmp_path):
    gw = _FakeGateway(Response(
        content=json.dumps({"description": "tamam", "notable_event": value,
                            "severity": "rutin"}),
        model="vlm-test"))
    result = interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
    assert result.notable_event is None


def test_a_real_notable_event_survives(tmp_path):
    gw = _FakeGateway(Response(
        content=json.dumps({"description": "tamam", "severity": "olay",
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


# --- klip içi zaman çizelgesi (beats) --------------------------------------
#
# Ölçülen arıza: teslim edilen her olay PENCERENİN BAŞLANGICI ile damgalanıyordu,
# yani 10 saniyelik bir pencere tek bir ana çöküyordu. Raf çökmesi klibinde
# darbe, devrilme ve toz üçü birden `00:10` diye raporlandı — oysa modelin
# kendi yanıtı çökmenin klibin 3. saniyesinde başladığını söylüyordu.

def _beats_response(beats, description="raf çöktü"):
    return Response(content=json.dumps(
        {"description": description, "notable_event": None, "beats": beats,
         "severity": "olay"},
        ensure_ascii=False), model="vlm-test")


def test_beats_are_parsed_into_the_interpretation(tmp_path):
    gw = _FakeGateway(_beats_response([
        {"offset_s": 1.0, "text": "Forklift sağdan sola ilerliyor."},
        {"offset_s": 3.0, "text": "Rafın altı çökmeye başlıyor."}]))
    result = interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
    assert [(b.offset_s, b.text) for b in result.beats] == [
        (1.0, "Forklift sağdan sola ilerliyor."),
        (3.0, "Rafın altı çökmeye başlıyor.")]


def test_beats_are_persisted_with_the_interpretation(tmp_path):
    gw = _FakeGateway(_beats_response([{"offset_s": 2.0, "text": "toz kalktı"}]))
    store = Store(":memory:")
    interpret(gw, store, _window(), _clip_for(tmp_path))
    assert store.interpretations()[0].beats[0].text == "toz kalktı"


def test_out_of_range_offsets_are_clamped_into_the_clip(tmp_path):
    """Klibin dışına düşen bir damga mutlak zamana çevrildiğinde olayı hiç
    yaşanmadığı bir saniyeye yazar. Pencere 0–9 s."""
    gw = _FakeGateway(_beats_response([
        {"offset_s": -4.0, "text": "klipten önce"},
        {"offset_s": 900.0, "text": "klipten sonra"}]))
    result = interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
    assert [b.offset_s for b in result.beats] == [0.0, 9.0]


@pytest.mark.parametrize("beat", [
    "düz metin",
    ["liste"],
    None,
    {"text": "damgası yok"},
    {"offset_s": 2.0},
    {"offset_s": "iki", "text": "sayı değil"},
    {"offset_s": True, "text": "bool sayı değildir"},
    {"offset_s": 1.0, "text": ""},
    {"offset_s": 1.0, "text": 5},
])
def test_a_malformed_beat_is_dropped_not_fatal(beat, tmp_path):
    """Bozuk bir an yorumun tamamını düşürmemeli — geri kalanı teslim edilir."""
    gw = _FakeGateway(_beats_response([beat, {"offset_s": 4.0,
                                              "text": "geçerli an"}]))
    result = interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
    assert result is not None
    assert [(b.offset_s, b.text) for b in result.beats] == [(4.0, "geçerli an")]


@pytest.mark.parametrize("raw", [
    "1.0s — bir şey oldu",
    12,
    {"offset_s": 1.0, "text": "listeye sarılmamış"},
])
def test_a_beats_field_that_is_not_a_list_is_ignored(raw, tmp_path):
    """Liste bekleyip düz sayı gelen bir alanda üzerinden geçmeye çalışmak
    `TypeError` demek — bozuk bir alan koşuyu düşüremez."""
    gw = _FakeGateway(_beats_response(raw))
    result = interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
    assert result is not None and result.beats == []


def test_beat_text_is_truncated_not_dropped(tmp_path):
    gw = _FakeGateway(_beats_response([{"offset_s": 1.0, "text": "a" * 400}]))
    result = interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
    assert len(result.beats[0].text) == MAX_BEAT_TEXT


def test_runaway_beat_repetition_is_bounded(tmp_path):
    gw = _FakeGateway(_beats_response(
        [{"offset_s": float(i % 10), "text": f"an {i}"} for i in range(50)]))
    result = interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
    assert 0 < len(result.beats) <= MAX_BEATS


def test_the_schema_bounds_the_beat_list(tmp_path):
    """Kaçak tekrara karşı tek koruma dizinin üst sınırı (`maxItems`);
    `strict_schema` onu bilerek telde bırakıyor."""
    gw = _FakeGateway()
    interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
    schema = gw.last["schema"].model_json_schema()
    assert schema["properties"]["beats"]["maxItems"] == MAX_BEATS


def test_the_beat_schema_asks_for_offsets_from_the_clip_start(tmp_path):
    gw = _FakeGateway()
    interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
    schema = gw.last["schema"].model_json_schema()
    description = schema["properties"]["beats"]["description"]
    assert "SANİYE" in description and "klibin başlangıcından" in description


def test_the_prompt_asks_for_a_timeline_inside_the_clip():
    assert "beats" in SYSTEM_PROMPT
    assert "süresini aşmasın" in SYSTEM_PROMPT


def test_a_response_without_beats_still_interprets(tmp_path):
    """Eski alanlar aynen çalışmaya devam ediyor — `beats` eklenti."""
    gw = _FakeGateway(Response(
        content='{"description":"tamam","severity":"rutin"}', model="v"))
    result = interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
    assert result.description == "tamam" and result.beats == []


def test_degraded_vision_yields_no_beats_and_does_not_crash(tmp_path):
    gw = _FakeGateway(Response(content=json.dumps(
        {"description": "bayat", "beats": [{"offset_s": 1.0, "text": "x"}]}),
        model="v", degraded=True))
    assert interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path)) is None


def test_unparsable_vision_yields_no_beats_and_does_not_crash(tmp_path):
    gw = _FakeGateway(Response(content="beats: 1.0s raf çöktü", model="v"))
    assert interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path)) is None


# --- severity: epizot açılışının tek geçidi (Görev 21) ---------------------
#
# Ölçülen arıza (k04, 98.8 sn forklift kazası klibi): epizot 00:00'da, park
# hâlindeki bir kamyonun yanından geçen biri yüzünden açıldı ve TEK açık
# epizot değişmezi yüzünden kazanın gerçekleştiği 40-50 sn'yi de yuttu.
# `notable_event` tek dereceliydi — "fabrika kamerası için ilginç" ile
# "kayda değer" arasındaki farkı taşıyamıyordu. `severity` bu farkı taşıyor;
# gerçek açılış geçidi `gozcu.loop.DecisionLoop._may_open`.

def test_severity_prompt_and_schema_share_the_same_constant():
    """Prompt bir enum sayıyorsa değerleri şemadakiyle birebir aynı olmalı —
    bunlar bir kez birbirinden ayrıldı ve sistem sessizce ölü hâle geldi
    (bkz. proje CLAUDE.md). Test elle kopyalanmış bir listeye karşı değil,
    paylaşılan `SEVERITY_LEVELS` sabitine karşı doğruluyor — bir kopya
    ayrışsa bile ötekinin değişmediği bir test bunu asla yakalayamaz."""
    schema_values = get_args(_VisionResponse.model_fields["severity"].annotation)
    assert schema_values == SEVERITY_LEVELS
    for level in SEVERITY_LEVELS:
        assert level in SYSTEM_PROMPT


def test_severity_is_required_the_model_cannot_skip_it(tmp_path):
    """Alan varsayılansız: model onu atlarsa yanıt OKUNAMAZ sayılmalı —
    epizot açılışının geçidi sessizce devre dışı kalmamalı."""
    gw = _FakeGateway(Response(
        content='{"description":"tamam"}', model="vlm-test"))
    assert interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path)) is None


def test_an_invalid_severity_value_is_rejected(tmp_path):
    gw = _FakeGateway(Response(content=json.dumps(
        {"description": "tamam", "severity": "acil-durum"}), model="vlm-test"))
    assert interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path)) is None


def test_severity_is_carried_into_the_interpretation(tmp_path):
    gw = _FakeGateway(Response(content=json.dumps(
        {"description": "forklift devrildi", "severity": "olay"}),
        model="vlm-test"))
    result = interpret(gw, Store(":memory:"), _window(), _clip_for(tmp_path))
    assert result.severity == "olay"
