# Görev 12 — Raportör ve kök neden raporu (`gozcu/agents/raportor.py`)

**Sahip:** `beyzaalive` · **Gün:** 25 Ağustos · **Süre:** ~2.5 saat
**Bağımlılık:** [01](01-sozlesme.md), [02](02-olay-deposu.md), [03](03-gateway.md)
**Etiket:** `cold-start`

## Bağlam

### Proje ne?

Gözcü, fabrika kamera kaydını izleyip olayları fark eden ve operatörle Türkçe
konuşan bir karar destek sistemi. TEKNOFEST Yapay Zekâ Dil Ajanları Yarışması,
3. senaryo. Teslim 26 Ağustos 23:59.

### Bu görev neden var?

Olay kapandığında sistemin yazdığı **kök neden raporu.** Demo'nun kapanış anı
bu. Elindeki malzeme zaten depoda birikmiş durumda: olay zinciri, risk
değerlendirmeleri, operatörün yaptığı düzeltmeler, çağrılan saha sistemleri,
diyalog dökümü. Senin işin bunları tek bir Türkçe rapora dönüştürmek.

Üç kural raporu belirliyor:

**Operatör düzeltmesi kazanır.** Operatör "araç devrilmedi, yük düştü" dediyse
rapor da yük düştü der. Düzeltme raporu etkilemiyorsa, düzeltme hiçbir şey
yapmamış demektir — ve bu, puanın %20'sini taşıyan diyalog kaleminin çöktüğü yer.

**Kesin hüküm yok.** Kamera bir kazanın sebebine hükmedemez. Rapor "muhtemel kök
neden" der ve `guven_sinirlari` alanında **neyi bilemeyeceğini açıkça yazar.**
Bu bir zayıflık değil; şartnamenin *açıklanabilirlik* beklentisinin karşılığı.

**Türkçe, kısa cümle, saha terminolojisi.** `istif aracı`, `vardiya amiri`,
`yerde hareketsiz kişi`. Edilgen çatıdan kaçın.

## Kurulum

```bash
git clone git@github.com:uvyscengiz/gozcu-ai-teknofest.git
cd gozcu-ai-teknofest
uv sync --extra dev
uv run pytest tests/ -v
```

Gateway erişimin olmasa da bu görev biter — bütün testler mock kullanıyor.

## Bağımlı olduğun imzalar

```python
# gozcu/gateway.py
Gateway.sor(kademe, mesajlar, sema=None, araclar=None) -> Yanit
#   kademe pozisyonel; bu görevde "ana" kullanacaksın
Yanit(icerik: str, arac_cagrilari: list, model: str, gecikme_ms: int,
      token: int, bozulmus: bool)

# gozcu/store.py — hepsi okuma
Store.epizotlar() -> list[Epizot]
Store.riskler() -> list[RiskDegerlendirme]
Store.duzeltmeler(epizot_id: int) -> list[Duzeltme]
Store.aksiyonlar() -> list[AksiyonKaydi]
Store.diyalog() -> list[DiyalogSatiri]

# gozcu/models.py — alanları
Epizot(id, baslangic_ts, bitis_ts, faz, ozet_tr, katilimcilar, on_risk, durum)
RiskDegerlendirme(id, epizot_id, seviye, gerekce_tr, onlenebilir, aday_aksiyonlar)
Duzeltme(id, ts, epizot_id, alan, eski, yeni, gerekce)
AksiyonKaydi(id, ts, tool_adi, parametreler, sonuc, kim, onay_durumu)
DiyalogSatiri(id, ts, rol, metin)
```

## Ne yapacaksın

```python
class KokNedenRaporu(BaseModel):
    ne_oldu: str
    muhtemel_kok_neden: str
    alinan_aksiyonlar: list[str]
    onleme_onerileri: list[str]
    guven_sinirlari: str

kok_neden_raporu_uret(gw, store) -> KokNedenRaporu
```

Depodaki her şeyi tek bir isteme topla, `gw.sor("ana", ...)` ile rapor ürettir.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_raportor.py`

```python
from unittest.mock import Mock

from gozcu.agents.raportor import kok_neden_raporu_uret
from gozcu.gateway import Yanit
from gozcu.models import (AksiyonKaydi, DiyalogSatiri, Duzeltme, Epizot,
                          RiskDegerlendirme)
from gozcu.store import Store

YANIT = ('{"ne_oldu":"B-Hattı sevkiyat alanında yük düştü.",'
         '"muhtemel_kok_neden":"Fren bakımının 4 ay gecikmiş olması.",'
         '"alinan_aksiyonlar":["İSG kaydı açıldı"],'
         '"onleme_onerileri":["Bakım periyodu denetlensin"],'
         '"guven_sinirlari":"Kamera görüntüsü fren durumunu doğrudan gösteremez."}')


def _gw(icerik=YANIT, **kw):
    gw = Mock(); gw.sor.return_value = Yanit(icerik=icerik, **kw)
    return gw


def _hazir_store():
    store = Store(":memory:")
    e = Epizot(baslangic_ts=12.0, faz="sonuc", ozet_tr="yük düştü",
               on_risk="Yüksek", durum="kapali")
    e.id = store.epizot_ac(e)
    store.kaydet_risk(RiskDegerlendirme(epizot_id=e.id, seviye="Yüksek",
                                        gerekce_tr="fren gecikmesi",
                                        onlenebilir=True))
    store.kaydet_aksiyon(AksiyonKaydi(ts=1.0, tool_adi="isg_olay_kaydi_ac",
                                      parametreler={}, sonuc={"kayit_no": "x"},
                                      kim="ajan", onay_durumu="gerekmiyor"))
    store.kaydet_diyalog(DiyalogSatiri(ts=1.0, rol="operator",
                                       metin="ne oldu?"))
    return store, e


def _istem(gw):
    return gw.sor.call_args.args[1][-1]["content"]


def test_report_always_states_its_confidence_limits():
    gw = _gw(); store, _ = _hazir_store()
    r = kok_neden_raporu_uret(gw, store)
    assert r.guven_sinirlari.strip()


def test_report_uses_the_large_reasoning_tier():
    gw = _gw(); store, _ = _hazir_store()
    kok_neden_raporu_uret(gw, store)
    assert gw.sor.call_args.args[0] == "ana"


def test_prompt_includes_the_action_ledger():
    gw = _gw(); store, _ = _hazir_store()
    kok_neden_raporu_uret(gw, store)
    assert "isg_olay_kaydi_ac" in _istem(gw)


def test_prompt_includes_risk_assessments_and_dialogue():
    gw = _gw(); store, _ = _hazir_store()
    kok_neden_raporu_uret(gw, store)
    istem = _istem(gw)
    assert "fren gecikmesi" in istem and "ne oldu?" in istem


def test_operator_corrections_reach_the_prompt():
    gw = _gw(); store, e = _hazir_store()
    store.kaydet_duzeltme(Duzeltme(ts=1.0, epizot_id=e.id, alan="olay_turu",
                                   eski="araç devrildi", yeni="yük düştü",
                                   gerekce="operatör gözlemi"))
    kok_neden_raporu_uret(gw, store)
    istem = _istem(gw)
    assert "yük düştü" in istem and "araç devrildi" in istem


def test_degraded_tier_returns_a_report_shell_not_an_exception():
    gw = Mock(); gw.sor.return_value = Yanit(bozulmus=True)
    store, _ = _hazir_store()
    r = kok_neden_raporu_uret(gw, store)
    assert r.ne_oldu and r.guven_sinirlari


def test_empty_store_does_not_crash():
    kok_neden_raporu_uret(_gw(), Store(":memory:"))
```

Beşinci test bu görevin en önemli garantisi: rapora ulaşmayan bir düzeltme,
hiçbir şey yapmamış bir düzeltmedir.

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_raportor.py -v
```
Beklenen: `ModuleNotFoundError: No module named 'gozcu.agents.raportor'`

### 3. `gozcu/agents/raportor.py` yaz

```python
import json

from pydantic import BaseModel, ConfigDict, Field

SISTEM = """Sen bir savunma sanayi üretim tesisinin olay inceleme raportörüsün.
Sana olay zinciri, risk değerlendirmeleri, operatör düzeltmeleri, alınan
aksiyonlar ve diyalog dökümü verilir. Bir kök neden raporu yaz.

Kurallar:
- Türkçe, kısa cümleler, saha terminolojisi (istif aracı, vardiya amiri)
- Edilgen çatıdan kaçın
- KESİN HÜKÜM VERME. Kamera verisine dayanan kalibre edilmiş tahmin ver.
- Operatör düzeltmesi varsa DÜZELTİLMİŞ hâli esas al
- guven_sinirlari alanında neyi bilemeyeceğini açıkça yaz

Sadece JSON döndür."""


class KokNedenRaporu(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ne_oldu: str = Field(max_length=800)
    muhtemel_kok_neden: str = Field(max_length=600)
    alinan_aksiyonlar: list[str] = Field(default_factory=list)
    onleme_onerileri: list[str] = Field(default_factory=list)
    guven_sinirlari: str = Field(max_length=400)


def _bolum(baslik: str, satirlar: list[str]) -> list[str]:
    return [f"\n{baslik}:", *(satirlar or ["- (yok)"])]


def _istem(store) -> str:
    epizotlar = store.epizotlar()
    parcalar: list[str] = []

    parcalar += _bolum("OLAY ZİNCİRİ", [
        f"- {e.baslangic_ts:.0f}s [{e.faz}] {e.ozet_tr}" for e in epizotlar])

    parcalar += _bolum("RİSK DEĞERLENDİRMELERİ", [
        f"- {r.seviye}: {r.gerekce_tr}" for r in store.riskler()])

    duzeltmeler = [d for e in epizotlar if e.id
                   for d in store.duzeltmeler(e.id)]
    parcalar += _bolum("OPERATÖR DÜZELTMELERİ", [
        f"- {d.alan}: '{d.eski}' yerine '{d.yeni}' ({d.gerekce})"
        for d in duzeltmeler])

    parcalar += _bolum("AKSİYON DEFTERİ", [
        f"- {a.tool_adi}({a.parametreler}) → {a.sonuc} [{a.onay_durumu}]"
        for a in store.aksiyonlar()])

    parcalar += _bolum("DİYALOG", [
        f"- {s.rol}: {s.metin}" for s in store.diyalog()])

    return "\n".join(parcalar)


def kok_neden_raporu_uret(gw, store) -> KokNedenRaporu:
    yanit = gw.sor("ana", [
        {"role": "system", "content": SISTEM},
        {"role": "user", "content": _istem(store)},
    ], sema=KokNedenRaporu)

    if yanit.bozulmus:
        return KokNedenRaporu(
            ne_oldu="Rapor katmanı yanıt vermiyor; ham olay zinciri kayıtlıdır.",
            muhtemel_kok_neden="Belirlenemedi.",
            guven_sinirlari="Rapor modeline ulaşılamadı.")
    try:
        return KokNedenRaporu(**json.loads(yanit.icerik))
    except Exception:  # noqa: BLE001
        return KokNedenRaporu(
            ne_oldu="Rapor üretilemedi; ham olay zinciri kayıtlıdır.",
            muhtemel_kok_neden="Belirlenemedi.",
            guven_sinirlari="Rapor yanıtı okunamadı.")
```

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_raportor.py -v
```
Beklenen: 7 passed

### 5. Commit

```bash
git add gozcu/agents/raportor.py tests/test_raportor.py
git commit -m "feat: root-cause reporter honouring corrections and stating limits"
```

## Doğrulama

```bash
uv run pytest tests/test_raportor.py -v
```
Beklenen: **7 passed**

## Takıldığında

Üveys'e yaz. **Bekleme** — bu sprintte bir saat, toplam kapasitenin yaklaşık %4'ü.
