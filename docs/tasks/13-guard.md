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
Gateway.sor(kademe, mesajlar, sema=None, araclar=None) -> Yanit
#   kademe pozisyonel; bu görevde "guard"
Yanit(icerik: str, arac_cagrilari: list, model: str, gecikme_ms: int,
      token: int, bozulmus: bool)
```

## Ne yapacaksın

```python
denetle(gw, metin: str, kritik: bool = False) -> str
```

Metin uygunsa aynen döner. Uygunsuzsa nötr bir bildirimle değiştirilir.
`kritik=True` ise model hiç çağrılmaz.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_guard.py`

```python
from unittest.mock import Mock

from gozcu.gateway import Yanit
from gozcu.guard import denetle


def _gw(icerik="uygun", **kw):
    gw = Mock(); gw.sor.return_value = Yanit(icerik=icerik, **kw)
    return gw


def test_clean_text_passes_through_unchanged():
    metin = "Sağlık ekibi 2 dakikaya varıyor."
    assert denetle(_gw("uygun"), metin) == metin


def test_flagged_text_is_replaced_with_a_neutral_notice():
    metin = "uygunsuz bir ifade"
    assert denetle(_gw("uygunsuz"), metin) != metin


def test_verdict_matching_is_case_insensitive():
    assert denetle(_gw("UYGUNSUZ"), "x") != "x"


def test_critical_alerts_are_never_blocked():
    gw = _gw("uygunsuz")
    metin = "KRİTİK: yerde hareketsiz kişi var."
    assert denetle(gw, metin, kritik=True) == metin
    gw.sor.assert_not_called()


def test_guard_failure_lets_text_through_rather_than_silencing_the_system():
    gw = Mock(); gw.sor.side_effect = RuntimeError("guard down")
    metin = "Vardiya amirine bildirildi."
    assert denetle(gw, metin) == metin


def test_degraded_guard_tier_lets_text_through():
    metin = "B-Hattı durduruldu."
    assert denetle(_gw(bozulmus=True), metin) == metin


def test_empty_text_is_returned_without_calling_the_model():
    gw = _gw()
    assert denetle(gw, "") == ""
    gw.sor.assert_not_called()
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
SISTEM = """Aşağıdaki metin bir fabrika kontrol odasında operatöre gösterilecek.
Metin ayrımcı, aşağılayıcı, kişiyi hedef alan veya yanlı bir ifade içeriyor mu?
Kişi hakkında kimlik, etnik köken, cinsiyet veya yaş çıkarımı var mı?
Sadece "uygun" veya "uygunsuz" yaz."""

NOTR = "[Bu ifade uygunsuz bulundu ve gösterilmedi. Olay kaydı korunmuştur.]"


def denetle(gw, metin: str, kritik: bool = False) -> str:
    """Operatöre giden metni denetler.

    Can güvenliği uyarısı asla tutulmaz: bir yaralanmayı kaçırmak, ton
    ihlalinden ağır basar. Denetim katmanı çökerse metin geçer — açık
    başarısız olur, çünkü bir denetim katmanının sistemi susturabilmesi
    kabul edilebilir bir tasarım değil.
    """
    if kritik or not metin.strip():
        return metin
    try:
        yanit = gw.sor("guard", [{"role": "system", "content": SISTEM},
                                 {"role": "user", "content": metin}])
    except Exception:  # noqa: BLE001 — açık başarısız ol, sistemi susturma
        return metin
    if yanit.bozulmus:
        return metin
    return NOTR if "uygunsuz" in yanit.icerik.strip().lower() else metin
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
