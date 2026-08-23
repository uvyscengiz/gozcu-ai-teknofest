import json
from unittest.mock import Mock, patch

import pytest
from pydantic import BaseModel, ConfigDict, Field

from gozcu.gateway import Gateway, GatewayError, Response

MESSAGES = [{"role": "user", "content": "x"}]
TIERS = ["router", "fast", "main", "vlm", "guard", "embed", "rerank"]


def _completion(content: str, tokens: int = 12) -> Mock:
    """OpenAI sohbet yanıtının test için yeten kadarı."""
    message = Mock(content=content, tool_calls=[])
    return Mock(choices=[Mock(message=message)], usage=Mock(total_tokens=tokens))


def test_injected_failure_marks_degraded_not_crash():
    gw = Gateway()
    gw.inject_failure({"vlm"})
    response = gw.ask("vlm", MESSAGES)
    assert response.degraded is True and response.content == ""
    assert gw.is_degraded() is True


def test_injected_failure_is_scoped_to_named_tiers():
    """Enjeksiyon sadece adı geçen kademeyi vurmalı. Sızarsa beat 6 tam
    kesinti gibi görünür, kısmi bozulma gibi değil."""
    gw = Gateway()
    gw.inject_failure({"vlm"})
    with patch.object(gw, "_client") as c:
        c.chat.completions.create.return_value = _completion("tamam")
        response = gw.ask("main", MESSAGES, _retries=1)
        c.chat.completions.create.assert_called_once()
    assert response.degraded is False and response.content == "tamam"


@pytest.mark.parametrize("tier", TIERS)
def test_every_tier_degrades_instead_of_raising(tier):
    """Hiçbir kesinti koşuyu düşürmez: şartnamenin dört anahtarı, genişletilmiş
    katmanların hepsi çökse bile üretilebilmeli."""
    gw = Gateway()
    gw.inject_failure({tier})
    response = gw.ask(tier, MESSAGES)
    assert response.degraded is True and response.content == ""
    assert gw.is_degraded(tier) is True


def test_unknown_tier_is_a_programming_error():
    """GatewayError artık kesintiyi değil, olmayan bir kademe adını bildirir."""
    gw = Gateway()
    with pytest.raises(GatewayError):
        gw.ask("supervisor", MESSAGES)


def test_degraded_rerank_does_not_degrade_the_vision_tier():
    """Görev 05 `is_degraded("vlm")`'i 'görü katmanı çöktü' diye okuyor. rerank'ın
    beklenen 400'ü bunu latch'lerse döngü her pencereyi sonsuza dek erteler."""
    gw = Gateway()
    gw.inject_failure({"rerank"})
    gw.ask("rerank", MESSAGES)
    assert gw.is_degraded("rerank") is True
    assert gw.is_degraded("vlm") is False
    assert gw.is_degraded() is True


def test_inject_failure_replaces_the_previous_injection():
    gw = Gateway()
    gw.inject_failure({"rerank"})
    gw.ask("rerank", MESSAGES)
    gw.inject_failure({"vlm"})
    assert gw.is_degraded("rerank") is False
    assert gw.is_degraded() is False


def test_recovery_clears_degraded_flag():
    gw = Gateway()
    gw.inject_failure({"vlm"})
    gw.ask("vlm", MESSAGES)
    gw.inject_failure(set())
    assert gw.is_degraded() is False


def test_a_later_success_clears_that_tiers_degradation():
    gw = Gateway()
    with patch.object(gw, "_client") as c:
        c.chat.completions.create.side_effect = RuntimeError("ağ yok")
        assert gw.ask("vlm", MESSAGES, _retries=1).degraded is True
        assert gw.is_degraded("vlm") is True
        c.chat.completions.create.side_effect = None
        c.chat.completions.create.return_value = _completion("tamam")
        response = gw.ask("vlm", MESSAGES, _retries=1)
    assert response.degraded is False and response.content == "tamam"
    assert gw.is_degraded("vlm") is False and gw.is_degraded() is False


def test_rerank_failure_falls_back_to_identity_order():
    """Reranker modelleri sohbet talimatı almaz; gateway'de 400 dönebilir.
    Bu asla yukarı kabarcıklanmamalı — arama beat 5'in ortasında çöker."""
    gw = Gateway()
    with patch.object(gw, "ask", side_effect=GatewayError("rerank yok")):
        assert gw.rerank("query", ["a", "b", "c"]) == [0, 1, 2]


def test_rerank_falls_back_when_its_tier_is_degraded():
    gw = Gateway()
    gw.inject_failure({"rerank"})
    assert gw.rerank("query", ["a", "b", "c"]) == [0, 1, 2]


def test_embed_goes_through_retry_not_a_raw_call():
    gw = Gateway()
    with patch.object(gw, "_client") as c, patch("gozcu.gateway.time.sleep"):
        c.embeddings.create.side_effect = RuntimeError("ağ yok")
        assert gw.embed("text", _retries=2) == []
        assert c.embeddings.create.call_count == 2


def test_embed_returns_an_empty_vector_when_degraded():
    """Görev 08 boş vektörü 'sonuç yok' diye okuyor — burada patlamak yok."""
    gw = Gateway()
    gw.inject_failure({"embed"})
    assert gw.embed("text") == []
    assert gw.is_degraded("embed") is True


def test_generation_controls_reach_the_client_when_given():
    """Görü kademesi bir token tavanına muhtaç: üst sınır olmadan strict-JSON
    kod çözümü kaçak tekrara girip max_tokens tükenene kadar yineliyor."""
    gw = Gateway()
    with patch.object(gw, "_client") as c:
        c.chat.completions.create.return_value = _completion("tamam")
        gw.ask("vlm", MESSAGES, max_tokens=300, temperature=0.3, _retries=1)
        request = c.chat.completions.create.call_args.kwargs
    assert request["max_tokens"] == 300
    assert request["temperature"] == 0.3


def test_generation_controls_are_absent_when_not_given():
    """Verilmediklerinde istekte hiç görünmemeliler — mevcut on sekiz çağrı
    yerinin gövdesi bir karakter bile değişmiyor."""
    gw = Gateway()
    with patch.object(gw, "_client") as c:
        c.chat.completions.create.return_value = _completion("tamam")
        gw.ask("main", MESSAGES, _retries=1)
        request = c.chat.completions.create.call_args.kwargs
    assert "max_tokens" not in request and "temperature" not in request


# --- şema sertleştirmesi gateway'in içinde (Görev 06 kararı) ----------------

class _Bounded(BaseModel):
    """Sertleştirmenin sökmesi gereken her doğrulama anahtarını taşıyan şema."""

    model_config = ConfigDict(extra="forbid")

    decision: str = Field(max_length=200, min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    labels: list[str] = Field(default_factory=list)


def _wire_schema(gw: Gateway, **kwargs) -> dict:
    """`_client`e giden gövdedeki şema — sertleştirmenin tek gerçek kanıtı."""
    with patch.object(gw, "_client") as c:
        c.chat.completions.create.return_value = _completion("tamam")
        gw.ask("router", MESSAGES, schema=_Bounded, _retries=1, **kwargs)
        request = c.chat.completions.create.call_args.kwargs
    return request["response_format"]["json_schema"]["schema"]


def test_ask_hardens_a_raw_schema_it_is_handed():
    """Çağıran `strict_schema()` çağırmayı unutabilir — üç görev dosyası zaten
    unuttu. Sertleştirme `ask()`'in içinde olduğu için unutulamaz."""
    schema = _wire_schema(Gateway())
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
    assert "maxLength" not in json.dumps(schema)


def test_ask_strips_numeric_bounds_from_the_schema():
    """`Field(ge=…, le=…)` şemaya `minimum`/`maximum` basıyor; strict arka uçlar
    bunları da reddediyor. Sınır pydantic modelinde kalır, tele çıkmaz."""
    wire = json.dumps(_wire_schema(Gateway()))
    for keyword in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
                    "multipleOf", "minLength", "pattern", "format"):
        assert keyword not in wire


def test_ask_keeps_the_array_bound():
    """`maxItems` ampirik bir hata için orada: üst sınır olmadan kod çözücü dizi
    alanında kaçak tekrara girip JSON'u hiç kapatmıyor. Sökülmez."""
    schema = _wire_schema(Gateway())
    assert schema["properties"]["labels"]["maxItems"] >= 1


def test_a_rejected_schema_falls_back_to_a_schemaless_request():
    """Organizasyonun gateway'i hiç görülmedi: şemayı reddetmesi bir kesintiden
    ayırt edilemez ve kademeyi sonsuza dek bozuk bırakırdı."""
    gw = Gateway()
    with patch.object(gw, "_client") as c, patch("gozcu.gateway.time.sleep"):
        def _create(**kwargs):
            if "response_format" in kwargs:
                raise RuntimeError("şema desteklenmiyor")
            return _completion("tamam")

        c.chat.completions.create.side_effect = _create
        response = gw.ask("router", MESSAGES, schema=_Bounded, _retries=2)
        calls = c.chat.completions.create.call_args_list

    assert response.degraded is False and response.content == "tamam"
    assert gw.is_degraded("router") is False
    assert len(calls) == 3, "iki şemalı deneme + bir şemasız yedek"
    assert "response_format" not in calls[-1].kwargs
    assert calls[-1].kwargs["messages"] == MESSAGES


def test_the_tier_degrades_when_the_schemaless_fallback_also_fails():
    gw = Gateway()
    with patch.object(gw, "_client") as c, patch("gozcu.gateway.time.sleep"):
        c.chat.completions.create.side_effect = RuntimeError("ağ yok")
        response = gw.ask("router", MESSAGES, schema=_Bounded, _retries=1)
        calls = c.chat.completions.create.call_args_list

    assert response.degraded is True and response.content == ""
    assert gw.is_degraded("router") is True
    assert any("response_format" not in call.kwargs for call in calls), \
        "şemasız yedek denenmiş olmalı"


def test_rerank_completes_a_partial_response():
    """Model adayların bir kısmını sayarsa kalanlar düşmemeli: eksik indeksler
    özgün sıralarıyla sona eklenir, yoksa arama sessizce aday kaybeder."""
    gw = Gateway()
    with patch.object(gw, "ask", return_value=Response(content="2")):
        assert gw.rerank("query", ["a", "b", "c"]) == [2, 0, 1]


def test_rerank_drops_repeated_indices():
    """Tekrar eden indeks aynı adayı iki kez döndürür — dönen sıra her adayı
    tam olarak bir kez içeren bir permütasyon olmalı."""
    gw = Gateway()
    with patch.object(gw, "ask", return_value=Response(content="1,1,0")):
        assert gw.rerank("query", ["a", "b", "c"]) == [1, 0, 2]
