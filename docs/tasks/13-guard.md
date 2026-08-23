# Görev 13 — Çıktı denetimi (`gozcu/guard.py`)

**Sahip:** `beyzaalive` · **Gün:** 25 Ağustos · **Süre:** ~1 saat
**Bağımlılık:** [03](03-gateway.md)
**Etiket:** `cold-start` · **En küçük görev — 12'yi bitirdikten sonra**

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

## Ne yapacaksın

```python
screen(gw, text: str, critical: bool = False) -> str
```

Metin uygunsa aynen döner. Uygunsuzsa nötr bir bildirimle değiştirilir.
`critical=True` ise model hiç çağrılmaz.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_guard.py`

```python
from unittest.mock import Mock

from gozcu.gateway import Response
from gozcu.guard import screen


def _gw(content="uygun", **kw):
    gw = Mock(); gw.ask.return_value = Response(content=content, **kw)
    return gw


def test_clean_text_passes_through_unchanged():
    text = "Sağlık ekibi 2 dakikaya varıyor."
    assert screen(_gw("uygun"), text) == text


def test_flagged_text_is_replaced_with_a_neutral_notice():
    text = "uygunsuz bir ifade"
    assert screen(_gw("uygunsuz"), text) != text


def test_verdict_matching_is_case_insensitive():
    assert screen(_gw("UYGUNSUZ"), "x") != "x"


def test_critical_alerts_are_never_blocked():
    gw = _gw("uygunsuz")
    text = "KRİTİK: yerde hareketsiz kişi var."
    assert screen(gw, text, critical=True) == text
    gw.ask.assert_not_called()


def test_guard_failure_lets_text_through_rather_than_silencing_the_system():
    gw = Mock(); gw.ask.side_effect = RuntimeError("guard down")
    text = "Vardiya amirine bildirildi."
    assert screen(gw, text) == text


def test_degraded_guard_tier_lets_text_through():
    text = "B-Hattı durduruldu."
    assert screen(_gw(degraded=True), text) == text


def test_empty_text_is_returned_without_calling_the_model():
    gw = _gw()
    assert screen(gw, "") == ""
    gw.ask.assert_not_called()
```

Dördüncü ve beşinci test bu görevin bütün amacı. Onlar geçmiyorsa denetim
katmanı bir güvenlik özelliği değil, bir risktir.

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_guard.py -v
```
Beklenen: `ModuleNotFoundError: No module named 'gozcu.guard'`

### 3. `gozcu/guard.py` yaz

```python
SYSTEM_PROMPT = """Aşağıdaki metin bir fabrika kontrol odasında operatöre gösterilecek.
Metin ayrımcı, aşağılayıcı, kişiyi hedef alan veya yanlı bir ifade içeriyor mu?
Kişi hakkında kimlik, etnik köken, cinsiyet veya yaş çıkarımı var mı?
Sadece "uygun" veya "uygunsuz" yaz."""

NEUTRAL_NOTICE = "[Bu ifade uygunsuz bulundu ve gösterilmedi. Olay kaydı korunmuştur.]"


def screen(gw, text: str, critical: bool = False) -> str:
    """Operatöre giden metni denetler.

    Can güvenliği uyarısı asla tutulmaz: bir yaralanmayı kaçırmak, ton
    ihlalinden ağır basar. Denetim katmanı çökerse metin geçer — açık
    başarısız olur, çünkü bir denetim katmanının sistemi susturabilmesi
    kabul edilebilir bir tasarım değil.
    """
    if critical or not text.strip():
        return text
    try:
        response = gw.ask("guard", [{"role": "system", "content": SYSTEM_PROMPT},
                                 {"role": "user", "content": text}])
    except Exception:  # noqa: BLE001 — açık başarısız ol, sistemi susturma
        return text
    if response.degraded:
        return text
    return NEUTRAL_NOTICE if "uygunsuz" in response.content.strip().lower() else text
```

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_guard.py -v
```
Beklenen: 7 passed

### 5. Commit

```bash
git add gozcu/guard.py tests/test_guard.py
git commit -m "feat: guard pass that fails open and never blocks critical alerts"
```

## Doğrulama

```bash
uv run pytest tests/test_guard.py -v
```
Beklenen: **7 passed**

## Takıldığında

Üveys'e yaz. **Bekleme** — bu sprintte bir saat, toplam kapasitenin yaklaşık %4'ü.
