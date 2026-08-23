from unittest.mock import Mock, patch

import pytest

from gozcu.gateway import Gateway, GatewayError

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
