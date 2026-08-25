# Görev 13 — Çıktı denetimi (`gozcu/guard.py`)

> ## ✅ TAMAMLANDI — 23 Ağustos 2026, `ec0eca6`
>
> **Çıktı denetimi indi.** `gozcu/guard.py` var; `tests/test_guard.py` 38 test
> ile yeşil. Bu dosyayı yeniden uygulama — aşağısı ne yapıldığının kaydı.
>
> **Sonraki göreve başlarken bilmen gerekenler**
> ([kararlar](#tamamlanma-notları-gelecek-görevleri-bağlayan) bölümüne bak):
> **hüküm hem Türkçe hem sınıflandırıcı etiketini kabul ediyor** — `guard`
> kademesi talimat takip eden bir sohbet modeli değil, tek kelimeye bağlanan
> bir kontrol sahada sessizce no-op'a dönerdi; **`screen_delivery()` teslim
> edilen paketi de tarıyor** — denetim artık yalnız operatör diyaloğunun değil,
> jüriye giden düzyazının da önünde; ve **açık başarısızlık korunuyor** —
> kesinti de okunamayan hüküm de metni geçirir, ama denetim kaydı onu "temiz"
> saymaz.

**Bağımlılık:** [03](03-gateway.md)

## Bağlam

### Proje ne?

Gözcü, fabrika kamera kaydını izleyip olayları fark eden ve operatörle Türkçe
konuşan bir karar destek sistemi. TEKNOFEST Yapay Zekâ Dil Ajanları Yarışması,
3. senaryo. Teslim 26 Ağustos 23:59.

### Bu görev neden var?

Şartnamenin etik maddesi takımların *"geliştirdikleri sistemlerin Türkçe konuşan
tüm bireyler için adil, kapsayıcı ve yanlılıktan arındırılmış olmasına özen
göstermekle yükümlü"* olduğunu söylüyor. Operatöre giden metinlerin önünde ucuz
bir kontrol katmanı bunun somut cevabı.

**Ama iki kural bu görevi tanımlıyor ve ikisi de "engelleme" yönünde değil:**

**Kritik uyarı asla engellenmez.** "Yerde hareketsiz kişi var" mesajını yutan bir
denetim katmanı, hiç denetim olmamasından kötüdür. Bir yaralanmayı kaçırmak, ton
ihlalinden ağır basar. Kritik işaretli metinler modele hiç gitmiyor.

**Denetim çökerse metin geçer.** Guard modeli yanıt vermiyorsa sistem susmaz —
metni olduğu gibi geçirir. Yani bu katman **açık başarısız** oluyor (fail open),
kapalı değil. Bir denetim katmanının sistemin tamamını susturabilmesi kabul
edilebilir bir tasarım değil.

## Kurulum

```bash
git clone git@github.com:uvyscengiz/gozcu-ai-teknofest.git
cd gozcu-ai-teknofest
uv sync --extra dev
uv run pytest tests/ -v
```

Gateway erişimi gerekmiyor — testler mock kullanıyor.

## Bağımlı olduğun imzalar

```python
# gozcu/gateway.py
Gateway.ask(tier, messages, schema=None, tools=None) -> Response
#   kademe pozisyonel; bu görevde "guard"
Response(content: str, tool_calls: list, model: str, latency_ms: int,
      tokens: int, degraded: bool)
```

**Bozulmuş yanıt guard'ı (Görev 03).** `guard` kademesi de artık bozuluyor, yani
`response.degraded` dalı ölü kod değil. Bir kesinti **istisna atmıyor** — ortada
boş içerikli, `degraded=True` bir yanıt var. Metnin olduğu gibi geçmesi bu
yüzden bayrağa bakılarak sağlanıyor; teslim edilen kodda geniş bir
`try/except Exception` yok. Gerekçe [tamamlanma
notlarında](#tamamlanma-notları-gelecek-görevleri-bağlayan).

## Ne yapacaksın

```python
screen(gw, text: str, critical: bool = False) -> str
screen_text(gw, text: str, critical: bool = False) -> Screening
screen_delivery(gw, output: PipelineOutput) -> DeliveryScreening
parse_verdict(content: str) -> "safe" | "unsafe" | "unknown"
```

Metin uygunsa aynen döner. Uygunsuzsa nötr bir bildirimle değiştirilir.
`critical=True` ise model hiç çağrılmaz.

`screen()` Görev 14'ün kısa yolu — yalnız gösterilecek metni verir.
`screen_text()` aynı işi yapar ama hükmü ve Türkçe denetim notunu da döndürür.
`screen_delivery()` ise [Görev 17](17-cikti-sozlesmesi.md)'nin teslim ettiği
paketi tarar: denetim yalnız operatör diyaloğunun değil, jüriye giden
düzyazının da önünde duruyor.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_guard.py`

```python
"""Çıktı denetimi testleri.

İki dosya boyunca tekrarlanan ders: bir testin **silinen kodu yakalaması**
gerekir. Buradaki testlerin çoğu bilerek mutasyon dirençli yazıldı — hangi
satır silindiğinde hangi testin kırmızıya döndüğü, testin başındaki notta
yazıyor.
"""

from unittest.mock import Mock

import pytest

from gozcu.gateway import Response
from gozcu.guard import (DELIVERY_FLAG_NOTICE, NEUTRAL_NOTICE, Screening,
                         parse_verdict, screen, screen_delivery, screen_text)
from gozcu.models import Detail, EventSummary, PipelineOutput


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
    from gozcu.gateway import GatewayError

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
```

`test_critical_alerts_are_never_blocked` ve
`test_degraded_guard_tier_lets_flagged_text_through` bu görevin bütün amacı.
Onlar geçmiyorsa denetim katmanı bir güvenlik özelliği değil, bir risktir.
`test_unsafe_verdict_shapes_are_all_understood` de aynı ağırlıkta: tek bir
`"uygunsuz" in content` kontrolü o satırların çoğunu **temiz** okur ve katman
sahada kalıcı bir no-op'a döner.

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_guard.py -v
```
Beklenen: `ModuleNotFoundError: No module named 'gozcu.guard'`

### 3. `gozcu/guard.py` yaz

```python
"""Çıktı denetimi — operatöre giden ve jüriye teslim edilen metnin önündeki
ucuz kontrol katmanı.

Şartnamenin etik maddesi sistemin "Türkçe konuşan tüm bireyler için adil,
kapsayıcı ve yanlılıktan arındırılmış" olmasını istiyor. Bu modül bunun somut
karşılığı. İki kural onu tanımlıyor ve ikisi de **engelleme** yönünde değil:

**Kritik uyarı asla engellenmez.** "Yerde hareketsiz kişi var" mesajını yutan
bir denetim katmanı, hiç denetim olmamasından kötüdür. Bir yaralanmayı
kaçırmak, ton ihlalinden ağır basar. `critical=True` işaretli metin modele hiç
gitmez.

**Denetim çökerse metin geçer (açık başarısızlık).** Kademe susarsa ya da
hüküm okunamazsa metin olduğu gibi ilerler. Bir denetim katmanının sistemin
tamamını susturabilmesi kabul edilebilir bir tasarım değil.

## Hüküm neden tek bir kelimeye bağlanamaz

`guard` kademesindeki model bir **güvenlik sınıflandırıcısı**, talimat takip
eden bir sohbet modeli değil — `Gateway.rerank`'ın docstring'indeki uyarının
aynısı burada da geçerli. Prompt Türkçe "uygun" / "uygunsuz" istiyor; gerçek
kademe gayet doğal olarak kendi etiket biçimini (`Safety: Unsafe` gibi)
basabilir. Tek bir `"uygunsuz" in content` kontrolü o cevabı **temiz** okur ve
denetim katmanı sahada kalıcı bir no-op'a döner — üstelik bütün testler yeşil
kalır, çünkü testlerdeki gateway bir `Mock`.

Bu yüzden `parse_verdict()` üç biçimi birden tanıyor (Türkçe hüküm,
sınıflandırıcı etiketi, Türkçe olumsuzlama) ve tanımadığı her cevabı
`"unknown"` sayıyor. `"unknown"` metni geçirir ama **temiz demez**: denetim
kaydı "denetlendi, temiz" ile "denetlenemedi" arasındaki farkı görebilmeli.

## Neden `try/except` yok

Görev 03'ten beri hiçbir kademe kesintide istisna atmıyor: `ask()` boş
içerikli, `degraded=True` bir yanıt döndürüyor. Kesinti kontrolü bu yüzden
bayrağa bakıyor. Geriye kalan tek istisna `GatewayError` ve o artık **kesinti
değil, yazım hatası** demek (kayıtlı olmayan kademe adı). Onu yutan bir
`except Exception` denetimi sessizce kapatırdı; bilerek yukarı bırakılıyor.

## Çağıranlar

- **Görev 14 (Nöbetçi):** operatöre giden her mesaj için `screen()` — ya da
  denetim kaydına hüküm yazacaksa `screen_text()`.
- **Görev 17 (boru hattı):** teslimden hemen önce
  `screen_delivery(gw, output)`. Ayrıntı için o fonksiyonun docstring'i.
"""

import re
from dataclasses import dataclass
from typing import Literal

from gozcu.models import PipelineOutput

__all__ = ["DELIVERY_FLAG_NOTICE", "DeliveryScreening", "NEUTRAL_NOTICE",
           "Screening", "Verdict", "parse_verdict", "screen",
           "screen_delivery", "screen_text"]

SYSTEM_PROMPT = """Aşağıdaki metin bir fabrika kontrol odasında operatöre gösterilecek.
Metin ayrımcı, aşağılayıcı, kişiyi hedef alan veya yanlı bir ifade içeriyor mu?
Kişi hakkında kimlik, etnik köken, cinsiyet veya yaş çıkarımı var mı?
Sadece "uygun" veya "uygunsuz" yaz."""

#: Uygunsuz bulunan operatör metninin yerine geçen bildirim. Olayın kendisi
#: kaybolmuyor — kayıt depoda, yalnız ifade gösterilmiyor.
NEUTRAL_NOTICE = ("[Bu ifade uygunsuz bulundu ve gösterilmedi. Olay kaydı "
                  "korunmuştur.]")

#: Teslim edilen yükün işaretlenme notu. Teslim tarafında metin SİLİNMİYOR;
#: gerekçe `screen_delivery()` docstring'inde.
DELIVERY_FLAG_NOTICE = ("[Denetim notu: bu raporun ifadeleri uygunsuz içerik "
                        "açısından işaretlendi. Kayıt bütünlüğü için metin "
                        "kaldırılmadı.]")

#: `unknown` bilerek `unsafe`'ten ayrı: "denetlendi ve uygunsuz" ile
#: "denetlenemedi" farklı olaylar. `skipped` ise denetimin bilerek
#: uygulanmadığı hâl (kritik uyarı, boş metin).
Verdict = Literal["safe", "unsafe", "unknown", "skipped"]

# Denetim kaydına düşen Türkçe notlar. Dördü bilerek farklı: aynı metni
# paylaşsalardı kaydı okuyan kişi "kademe sustu" ile "hüküm okunamadı"yı
# ayırt edemezdi ve `degraded` dalı sessizce ölü koda dönerdi.
CLEAN_NOTE = "Denetlendi, temiz."
FLAGGED_NOTE = "Denetlendi, uygunsuz bulundu."
DEGRADED_NOTE = "Denetim kademesi yanıt vermedi; metin denetlenmeden geçti."
UNREADABLE_NOTE = "Denetim hükmü okunamadı; metin denetlenmeden geçti."
CRITICAL_NOTE = "Can güvenliği uyarısı; denetim uygulanmadı."
NO_TEXT_NOTE = "Denetlenecek metin yok."

# Hüküm kalıpları. Sıra önemli: "uygunsuz" içinde "uygun", "unsafe" içinde
# "safe" geçiyor — kelime sınırları (`\b`) ikisini de ayırıyor, ama Türkçe
# olumsuzlama ("uygun değil") ancak ÖNCE aranarak yakalanabilir.
_UNSAFE = re.compile(
    r"\b(?:uygunsuz|unsafe|harmful|"
    r"uygun\s+(?:değil|degil|olmayan|bulunmad[ıi]|görülmed[ıi]|gorulmedi))\b",
    re.IGNORECASE)

# Sınıflandırıcının kararsız etiketi. `safe` saymak yanlış olurdu: model
# metnin bağlama göre sorunlu olabileceğini söylüyor. `unsafe` saymak da
# yanlış — modelin kendisi emin değil. Emin olmayan hüküm denetlenmemiş
# sayılır: metin geçer, kayıt "temiz" demez.
_UNDECIDED = re.compile(r"\b(?:controversial|tartışmalı|tartismali)\b",
                        re.IGNORECASE)

_SAFE = re.compile(r"\b(?:uygun|safe|güvenli|guvenli)\b", re.IGNORECASE)


def parse_verdict(content: str) -> Verdict:
    """Denetim kademesinin ham cevabını bir hükme çevirir.

    Üç biçim de kabul ediliyor — talimat edilen Türkçe hüküm (`uygun` /
    `uygunsuz`), sınıflandırıcı etiketi (`Safety: Unsafe`, `safe`, çevresinde
    başka metin olsa da) ve Türkçe olumsuzlama (`uygun değil`). Tanınmayan
    her cevap `"unknown"`: metin geçer ama temiz sayılmaz.
    """
    text = (content or "").strip()
    if not text:
        return "unknown"
    if _UNSAFE.search(text):
        return "unsafe"
    if _UNDECIDED.search(text):
        return "unknown"
    if _SAFE.search(text):
        return "safe"
    return "unknown"


@dataclass(frozen=True)
class Screening:
    """Bir metin denetiminin sonucu: gösterilecek metin, hüküm ve Türkçe not.

    `text` her zaman doludur — açık başarısızlık tasarımı gereği denetim
    hiçbir koşulda boş metin döndürmez.
    """

    text: str
    verdict: Verdict
    note: str

    @property
    def screened(self) -> bool:
        """Model gerçekten bir hüküm verdi mi.

        `"unknown"` ve `"skipped"` metni geçirir ama denetlenmiş saymaz —
        çağıran ve denetim kaydı "temiz" ile "denetlenemedi"yi ayırabilmeli.
        """
        return self.verdict in ("safe", "unsafe")


@dataclass(frozen=True)
class DeliveryScreening:
    """Teslim edilen yükün denetim sonucu. `output` her zaman teslim edilebilir."""

    output: PipelineOutput
    verdict: Verdict
    note: str

    @property
    def screened(self) -> bool:
        return self.verdict in ("safe", "unsafe")


def _ask_verdict(gw, text: str) -> Verdict:
    """Kademeye tek bir hüküm sorusu sorar; kesintide `"unknown"`.

    `temperature=0`: bu bir sınıflandırma kararı, yaratıcı yazı değil — aynı
    metin aynı hükmü almalı. Kademe adıyla anılıyor, model kimliği
    `gozcu.config` dışında hiçbir yerde yazılmaz (CLAUDE.md).
    """
    response = gw.ask("guard",
                      [{"role": "system", "content": SYSTEM_PROMPT},
                       {"role": "user", "content": text}],
                      temperature=0)
    if response.degraded:
        return "unknown"
    return parse_verdict(response.content)


def screen_text(gw, text: str, critical: bool = False) -> Screening:
    """Operatöre giden metni denetler ve hükmü de birlikte döndürür.

    Can güvenliği uyarısı asla tutulmaz ve denetim çökerse metin geçer;
    gerekçeler modül docstring'inde.
    """
    if critical:
        return Screening(text, "skipped", CRITICAL_NOTE)
    if not text.strip():
        return Screening(text, "skipped", NO_TEXT_NOTE)

    verdict = _ask_verdict(gw, text)
    if verdict == "unsafe":
        return Screening(NEUTRAL_NOTICE, "unsafe", FLAGGED_NOTE)
    if verdict == "safe":
        return Screening(text, "safe", CLEAN_NOTE)
    return Screening(text, "unknown", UNREADABLE_NOTE)


def screen(gw, text: str, critical: bool = False) -> str:
    """Gösterilecek metni döndürür — Görev 14'ün kısa yolu.

    Hükmü de kaydetmek isteyen çağıran `screen_text()` kullanır.
    """
    return screen_text(gw, text, critical).text


def _prose(output: PipelineOutput) -> list[str]:
    """Teslim edilen yükteki **düzyazı** alanları toplar.

    Yapısal kanıt bilerek dışarıda: `events[]` zaman damgaları, `risk`
    seviyesi, aksiyon defteri ve epizot kayıtları denetime girmez ve
    değiştirilmez. Denetim düzyazıyı işaretler, kayıt tutmaz.

    Kök neden raporu alan adlarıyla değil, **biçimiyle** taranıyor: rapor
    `detail.root_cause_report` altında düz bir `dict` (Görev 12) ve elle
    yazılmış bir alan listesi rapordan ayrışır — CLAUDE.md'nin adıyla
    uyardığı hata. Metin olan ve metin listesi olan her değer düzyazı sayılır.
    """
    parts: list[str] = [output.summary]
    parts += [a for a in output.actions if isinstance(a, str)]

    report = getattr(output.detail, "root_cause_report", None)
    if isinstance(report, dict):
        for value in report.values():
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                parts += [v for v in value if isinstance(v, str)]

    return [p for p in parts if p.strip()]


def screen_delivery(gw, output: PipelineOutput) -> DeliveryScreening:
    """Teslim edilen yükü denetler — **Görev 17 teslimden hemen önce çağırır.**

    Şartnamenin dört anahtarının jüriye giden düzyazısı da model yazımı
    Türkçe: `summary`, `actions[]` ve `detail.root_cause_report`'un anlatı
    alanları. Bunlar Görev 14'ün diyaloğu kadar denetime muhtaç.

    **Yük hiçbir koşulda boşaltılmıyor.** Uygunsuz hükmünde bile metin
    kaldırılmıyor, `summary`'ye bir denetim notu ekleniyor. Gerekçe iki
    katmanlı: (1) CLAUDE.md'nin çıktı sözleşmesi dört anahtarın her hâlükârda
    üretilmesini istiyor; (2) `guard` bir güvenlik sınıflandırıcısı ve bir
    endüstriyel kaza anlatısını ("yerde hareketsiz kişi", "yük düştü") şiddet
    içeriği sayıp işaretlemesi beklenen bir yanlış pozitif. Böyle bir hükümle
    jürinin okuduğu raporu silmek, denetimin engellemediği tek şeyi —
    teslimatı — engellemek olurdu. İşaret görünür, kanıt yerinde kalır.

    Kesinti ve okunamayan hüküm de açık başarısız oluyor: yük olduğu gibi,
    işaretsiz teslim edilir ve `screened` `False` döner.

    Tek bir kademe çağrısı yapılır; alan başına dağıtılmaz.
    """
    prose = _prose(output)
    if not prose:
        return DeliveryScreening(output, "skipped", NO_TEXT_NOTE)

    verdict = _ask_verdict(gw, "\n".join(prose))
    if verdict == "safe":
        return DeliveryScreening(output, "safe", CLEAN_NOTE)
    if verdict != "unsafe":
        return DeliveryScreening(output, "unknown", UNREADABLE_NOTE)

    # Çağıranın nesnesi değişmiyor: teslim edilen kopya işaretleniyor.
    flagged = output.model_copy(deep=True)
    flagged.summary = f"{output.summary}\n\n{DELIVERY_FLAG_NOTICE}".strip()
    return DeliveryScreening(flagged, "unsafe", FLAGGED_NOTE)
```

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_guard.py -v
```
Beklenen: 38 passed

### 5. Commit

```bash
git add gozcu/guard.py tests/test_guard.py
git commit -m "feat: output guard tolerant of classifier verdicts"
```

## Doğrulama

```bash
uv run pytest tests/test_guard.py -v
```
Beklenen: **38 passed**

## Takıldığında

Üveys'e yaz. **Bekleme** — bu sprintte bir saat, toplam kapasitenin yaklaşık %4'ü.

## Tamamlanma notları (gelecek görevleri bağlayan)

- **`MODELS["guard"]` bir GÜVENLİK SINIFLANDIRICISI (`Qwen3Guard-Gen-4B`),
  talimat takip eden bir sohbet modeli değil.** Prompt Türkçe `uygun` /
  `uygunsuz` istiyor ama kademe kendi etiket biçimini (`Safety: Unsafe`) basmakta
  tamamen serbest. İlk hâlindeki tek `"uygunsuz" in content` kontrolü o cevabı
  **temiz** okurdu: denetim katmanı sahada sonsuza dek her metni geçirir, üstelik
  bütün testler yeşil kalırdı — çünkü testlerdeki gateway bir `Mock`. Artık
  `parse_verdict()` hem talimat edilen Türkçe hükmü hem sınıflandırıcı etiketini
  tanıyor. Model kimliği yalnız `gozcu/config.py`'da; kod kademeyi adıyla anıyor.
- **`uygun değil` bir zamanlar ONAY okunuyordu.** Doğal bir Türkçe olumsuzlama
  hükmü tersine çeviriyordu. Olumsuzlama kalıpları artık olumlu kalıptan ÖNCE
  aranıyor (`_UNSAFE` → `_UNDECIDED` → `_SAFE`); sırayı bozan bir düzenleme
  denetimi sessizce geri alır.
- **`parse_verdict(content) -> "safe" | "unsafe" | "unknown"`.**
  `controversial` / `tartışmalı` bilerek `unknown`'a düşüyor: modelin kendisi
  ikili hüküm vermeyi reddetmiş. Temiz saymak yalan, uygunsuz saymak aşırı
  engelleme olurdu.
- **"Denetlendi ve temiz" ile "denetlenemedi" farkı TİP SEVİYESİNDE**, sihirli
  bir metinde değil: `Screening` / `DeliveryScreening` döndürülüyor ve
  `.screened` yalnız `safe` ve `unsafe` için `True`. Dört ayrı Türkçe denetim
  notu var (temiz / uygunsuz / kademe sustu / hüküm okunamadı) — aynı metni
  paylaşsalardı `degraded` dalı sessizce ölü koda dönerdi.
- **Her yerde açık başarısızlık.** Denetim kesintisi de okunamayan hüküm de
  teslimi ASLA engellemiyor; CLAUDE.md'nin dört anahtarlı sözleşmesi her hâlde
  hayatta kalıyor. Bu katman engellemek için değil, işaretlemek için var.
- **`unsafe` hükmünde teslim edilen yük İŞARETLENİYOR, boşaltılmıyor.** Bir
  güvenlik sınıflandırıcısının gerçek bir kaza anlatısını ("yerde hareketsiz
  kişi", "yük düştü") şiddet içeriği sayıp işaretlemesi beklenen bir yanlış
  pozitif; jürinin okuduğu raporu böyle bir hükümle silmek dört anahtarlı
  sözleşmeyi ihlal ederdi. `summary`'ye bir denetim notu ekleniyor, kanıt yerinde
  kalıyor. Operatör diyaloğu tarafında kural farklı: orada uygunsuz metin
  `NEUTRAL_NOTICE` ile değiştiriliyor, çünkü o metin jüriye teslim edilen kayıt
  değil, ekrandaki bir cümle.
- **`temperature=0`** — bu bir sınıflandırma kararı, yaratıcı yazı değil: aynı
  metin aynı hükmü almalı.
- **Bilerek geniş bir `try/except` YOK.** Görev 03/06'dan beri hiçbir kademe
  kesintide istisna atmıyor (`degraded=True` bir yanıt dönüyor), ve geriye kalan
  tek istisna `GatewayError` artık "bilinmeyen kademe" — yani bir yazım hatası.
  Onu yutan bir `except Exception` denetimi sessizce kapatırdı; istisna bilerek
  yukarı bırakılıyor.
