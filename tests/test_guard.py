"""Çıktı denetimi testleri.

İki dosya boyunca tekrarlanan ders: bir testin **silinen kodu yakalaması**
gerekir. Buradaki testlerin çoğu bilerek mutasyon dirençli yazıldı — hangi
satır silindiğinde hangi testin kırmızıya döndüğü, testin başındaki notta
yazıyor.
"""

from unittest.mock import Mock

import pytest

from gozcu.core.gateway import Response
from gozcu.output.guard import (DELIVERY_FLAG_NOTICE, NEUTRAL_NOTICE, Screening,
                         parse_verdict, screen, screen_delivery, screen_text)
from gozcu.core.models import Detail, EventSummary, PipelineOutput


def _gw(content="uygun", **kw):
    gw = Mock()
    gw.ask.return_value = Response(content=content, **kw)
    return gw


def _report():
    return {
        "what_happened": "İstif aracı B-Hattında yükü düşürdü.",
        "probable_root_cause": "Olası neden gecikmiş fren bakımı.",
        "actions_taken": ["Hat durduruldu.", "Sağlık ekibi çağrıldı."],
        "prevention_recommendations": ["Fren bakımı takvimi sıkılaştırılsın."],
        "confidence_limits": "Kamera aracın iç kabinini görmüyor.",
    }


def _output(summary="B-Hattında yük düştü.", actions=("Hat durduruldu.",)):
    return PipelineOutput(
        summary=summary,
        events=[EventSummary(time="00:12", event="Yük düştü.")],
        risk="Yüksek",
        actions=list(actions),
        detail=Detail(root_cause_report=_report()))


# --- metin denetimi -------------------------------------------------------

def test_clean_text_is_returned_and_the_guard_tier_was_actually_asked():
    """Denetim tamamen silinirse bu test kırmızıya döner.

    Eski hâli yalnız `screen(...) == text` diyordu; `screen` gövdesi
    `return text` olsaydı da geçerdi. Artık çağrının gerçekten yapıldığını,
    doğru kademeye gittiğini ve metni taşıdığını doğruluyor.
    """
    gw = _gw("uygun")
    text = "Sağlık ekibi 2 dakikaya varıyor."
    assert screen(gw, text) == text
    gw.ask.assert_called_once()
    tier, messages = gw.ask.call_args.args
    assert tier == "guard"
    assert any(text in m["content"] for m in messages)


def test_flagged_text_is_replaced_with_a_neutral_notice():
    text = "uygunsuz bir ifade"
    assert screen(_gw("uygunsuz"), text) == NEUTRAL_NOTICE


def test_verdict_matching_is_case_insensitive():
    assert screen(_gw("UYGUNSUZ"), "x") == NEUTRAL_NOTICE


@pytest.mark.parametrize("content", [
    "uygunsuz",
    "Uygun değil.",
    "Bu metin uygun degil",
    "uygun bulunmadı",
    "unsafe",
    "Safety: Unsafe\nCategories: Violent",
    "UNSAFE",
    "Label: unsafe",
])
def test_unsafe_verdict_shapes_are_all_understood(content):
    """Talimat edilen Türkçe hüküm, sınıflandırıcı etiketi ve Türkçe olumsuzlama.

    `guard` kademesi bir sınıflandırıcı (bkz. modül docstring'i): talimatı
    takip etmeyip kendi etiket biçimini basması beklenen davranış. Tek bir
    `"uygunsuz" in content` kontrolü bu satırların çoğunu **temiz** okur.
    """
    assert screen(_gw(content), "x") == NEUTRAL_NOTICE


@pytest.mark.parametrize("content", [
    "uygun",
    "Uygun.",
    "safe",
    "Safety: Safe\nCategories: None",
    "Bu metin uygun görünüyor.",
])
def test_safe_verdict_shapes_pass_the_text_through(content):
    assert screen_text(_gw(content), "x").verdict == "safe"


def test_negation_is_not_read_as_approval():
    """`"uygun" in content` bu satırı onay sanardı — hüküm tersine döner."""
    assert parse_verdict("uygun değil") == "unsafe"


@pytest.mark.parametrize("content", ["", "belki", "hmm, emin değilim",
                                     "Safety: Controversial"])
def test_unreadable_verdict_fails_open_but_is_not_marked_clean(content):
    """Açık başarısız ol — ama denetim kaydı 'temiz' ile 'okunamadı'yı ayırsın."""
    result = screen_text(_gw(content), "B-Hattı durduruldu.")
    assert result.text == "B-Hattı durduruldu."
    assert result.verdict == "unknown"
    assert not result.screened


def test_clean_and_unscreened_are_distinguishable():
    clean = screen_text(_gw("uygun"), "x")
    unscreened = screen_text(_gw("???"), "x")
    assert clean.text == unscreened.text == "x"
    assert clean.screened and not unscreened.screened
    assert clean.verdict != unscreened.verdict
    assert clean.note != unscreened.note


def test_screening_is_deterministic():
    """Sınıflandırma hükmü yaratıcı yazı değil; aynı metin aynı cevabı almalı."""
    gw = _gw("uygun")
    screen(gw, "x")
    assert gw.ask.call_args.kwargs["temperature"] == 0


def test_critical_alerts_are_never_blocked():
    gw = _gw("uygunsuz")
    text = "KRİTİK: yerde hareketsiz kişi var."
    assert screen(gw, text, critical=True) == text
    gw.ask.assert_not_called()


def test_critical_bypass_is_recorded_as_skipped_not_clean():
    result = screen_text(_gw("uygunsuz"), "KRİTİK: yerde hareketsiz kişi var.",
                         critical=True)
    assert result.verdict == "skipped"
    assert not result.screened


def test_degraded_guard_tier_lets_flagged_text_through():
    """`degraded` dalı silinirse bu test kırmızıya döner.

    İçerik `uygunsuz` diyor: yalnızca gerçek bir bozulma kontrolü metni
    geçirebilir. Eski hâli `content="uygun"` mirasını taşıyordu, yani dalın
    tamamı silinse de yeşil kalıyordu.
    """
    text = "B-Hattı durduruldu."
    assert screen(_gw("uygunsuz", degraded=True), text) == text


def test_degraded_screening_is_marked_unscreened():
    result = screen_text(_gw("uygunsuz", degraded=True), "x")
    assert result.verdict == "unknown"
    assert not result.screened


def test_empty_text_is_returned_without_calling_the_model():
    gw = _gw()
    assert screen(gw, "") == ""
    gw.ask.assert_not_called()


def test_unknown_tier_typo_is_not_swallowed():
    """`GatewayError` artık kesinti değil, yazım hatası demek (Görev 03).

    Geniş bir `except Exception` onu yutup denetimi sessizce kapatırdı.
    """
    from gozcu.core.gateway import GatewayError

    gw = Mock()
    gw.ask.side_effect = GatewayError("bilinmeyen kademe: gaurd")
    with pytest.raises(GatewayError):
        screen(gw, "x")


# --- teslim edilen çıktının denetimi (Görev 17) ---------------------------

def test_delivery_is_screened_in_a_single_call_covering_all_prose():
    gw = _gw("uygun")
    result = screen_delivery(gw, _output())
    gw.ask.assert_called_once()
    prompt = "\n".join(m["content"] for m in gw.ask.call_args.args[1])
    assert "B-Hattında yük düştü." in prompt
    assert "Hat durduruldu." in prompt
    assert "İstif aracı B-Hattında yükü düşürdü." in prompt
    assert "Fren bakımı takvimi sıkılaştırılsın." in prompt
    assert "Kamera aracın iç kabinini görmüyor." in prompt
    assert result.verdict == "safe"


def test_clean_delivery_ships_untouched():
    output = _output()
    result = screen_delivery(_gw("uygun"), output)
    assert result.output.model_dump() == output.model_dump()


def test_flagged_delivery_keeps_the_four_keys_and_all_evidence():
    """Denetim teslim edilen yükü ASLA boşaltmaz — dört anahtar hayatta kalır."""
    output = _output()
    result = screen_delivery(_gw("uygunsuz"), output)
    shipped = result.output
    assert result.verdict == "unsafe"
    assert shipped.risk == "Yüksek"
    assert [e.model_dump() for e in shipped.events] == \
           [e.model_dump() for e in output.events]
    assert shipped.actions == output.actions
    assert shipped.detail.root_cause_report == _report()
    assert output.summary in shipped.summary


def test_flagged_delivery_marks_the_prose():
    result = screen_delivery(_gw("uygunsuz"), _output())
    assert DELIVERY_FLAG_NOTICE in result.output.summary


def test_flagged_delivery_does_not_mutate_the_caller_payload():
    output = _output()
    screen_delivery(_gw("uygunsuz"), output)
    assert output.summary == "B-Hattında yük düştü."
    assert DELIVERY_FLAG_NOTICE not in output.summary


def test_degraded_delivery_screening_ships_the_payload_untouched():
    """Denetim kesintisi teslimi engellemez ve yükü işaretlemez."""
    output = _output()
    result = screen_delivery(_gw("uygunsuz", degraded=True), output)
    assert result.output.model_dump() == output.model_dump()
    assert result.verdict == "unknown"
    assert not result.screened


def test_unreadable_delivery_verdict_ships_the_payload_untouched():
    output = _output()
    result = screen_delivery(_gw("???"), output)
    assert result.output.model_dump() == output.model_dump()
    assert not result.screened


def test_delivery_without_prose_is_not_sent_to_the_model():
    gw = _gw()
    output = PipelineOutput(summary="", risk="Düşük")
    result = screen_delivery(gw, output)
    gw.ask.assert_not_called()
    assert result.output.model_dump() == output.model_dump()
    assert result.verdict == "skipped"


def test_screening_dataclass_reports_screened_only_for_a_verdict():
    assert Screening("x", "safe", "n").screened
    assert Screening("x", "unsafe", "n").screened
    assert not Screening("x", "unknown", "n").screened
    assert not Screening("x", "skipped", "n").screened
