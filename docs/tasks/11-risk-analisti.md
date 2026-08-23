# Görev 11 — Risk analisti (`gozcu/agents/risk.py`)

**Sahip:** `uvyscengiz` · **Gün:** 25 Ağustos · **Süre:** ~2 saat
**Bağımlılık:** [08](08-hafiza.md), [09](09-saha-araclari.md)

## Bağlam

Olayı alıp riski biçen, gerekçesini yazan ve **ne yapılması gerektiğini söyleyen**
uzman. İki tasarım kuralı belirleyici:

**Her aday aksiyon gerçek bir araca bağlanmak zorunda.** Sistemin
çalıştıramayacağı bir öneri sadece bir cümledir — ve cümleler tam olarak saha
araçlarının var olma sebebini boşa çıkarır. Model olmayan bir araç adı
uydurursa o öneri **sessizce düşürülür**, Nöbetçi'ye hiç ulaşmaz.

**Kesin hüküm vermez.** Kamera verisine dayanan bir sistem, bir kazanın sebebine
hükmedemez; kalibre edilmiş bir tahmin verir. Prompt bunu zorluyor, rapor da
(Görev 12) aynı çizgiyi sürdürüyor.

Analiz, karar vermeden önce **arşive bakıyor** — bu ekipmanın geçmişi var mı,
benzer bir olay olmuş mu. Hafıza katmanının mimari süs değil, muhakemenin
girdisi olduğu yer burası.

## Kurulum

```bash
uv sync --extra dev
uv run pytest tests/test_memory.py tests/test_tools.py -v
```

## Bağımlı olduğun imzalar

```python
# gozcu/memory.py
zaman_cizelgesi_ara(gw, store, sorgu: str, ust_k: int = 5) -> list[Epizot]

# gozcu/tools/registry.py
ARACLAR: dict[str, Callable]        # geçerli araç adlarının kaynağı

# gozcu/gateway.py
Gateway.sor(kademe, mesajlar, sema=None, araclar=None) -> Yanit

# gozcu/store.py
Store.kaydet_risk(r: RiskDegerlendirme) -> int
Store.duzeltmeler(epizot_id: int) -> list[Duzeltme]
Store.kaydet_devir(d: Devir) -> int

# gozcu/models.py
AdayAksiyon(aciklama_tr, tool_adi, parametreler)
RiskDegerlendirme(id, epizot_id, seviye, gerekce_tr, onlenebilir, aday_aksiyonlar)
```

## Ne yapacaksın

```python
risk_analiz_et(gw, store, epizot: Epizot) -> RiskDegerlendirme
```

**Şema notu:** modele `RiskDegerlendirme`'yi doğrudan verme — `id` ve
`epizot_id` alanları var ve katı şema modunda modeli bunları uydurmaya zorlar.
Ayrı bir `_RiskYaniti` yanıt modeli tanımla.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_risk.py`

```python
from unittest.mock import Mock, patch

from gozcu.agents.risk import risk_analiz_et
from gozcu.gateway import Yanit
from gozcu.models import Duzeltme, Epizot
from gozcu.store import Store

YANIT = ('{"seviye":"Kritik","gerekce_tr":"Yerde hareketsiz kişi var ve '
         'aracın fren bakımı gecikmiş.","onlenebilir":true,'
         '"aday_aksiyonlar":[{"aciklama_tr":"Sağlık ekibini çağır",'
         '"tool_adi":"saglik_ekibi_cagir",'
         '"parametreler":{"konum":"B-Hattı","aciliyet":"kritik"}}]}')


def _epizot(store):
    e = Epizot(baslangic_ts=0.0, faz="gelisim", ozet_tr="araç devrildi",
               on_risk="Yüksek")
    e.id = store.epizot_ac(e)
    return e


def _gw(icerik=YANIT, **kw):
    gw = Mock(); gw.sor.return_value = Yanit(icerik=icerik, **kw)
    return gw


def test_candidate_actions_map_to_real_registered_tools():
    from gozcu.tools.registry import ARACLAR
    store = Store(":memory:")
    with patch("gozcu.agents.risk.zaman_cizelgesi_ara", return_value=[]):
        r = risk_analiz_et(_gw(), store, _epizot(store))
    assert r.aday_aksiyonlar
    assert all(a.tool_adi in ARACLAR for a in r.aday_aksiyonlar)


def test_invented_tool_names_are_dropped_not_passed_through():
    kotu = YANIT.replace("saglik_ekibi_cagir", "helikopter_gonder")
    store = Store(":memory:")
    with patch("gozcu.agents.risk.zaman_cizelgesi_ara", return_value=[]):
        r = risk_analiz_et(_gw(kotu), store, _epizot(store))
    assert r.aday_aksiyonlar == []


def test_analysis_consults_the_archive_before_deciding():
    store = Store(":memory:")
    with patch("gozcu.agents.risk.zaman_cizelgesi_ara",
               return_value=[]) as ara:
        risk_analiz_et(_gw(), store, _epizot(store))
    ara.assert_called_once()


def test_operator_corrections_reach_the_prompt():
    store = Store(":memory:")
    e = _epizot(store)
    store.kaydet_duzeltme(Duzeltme(ts=1.0, epizot_id=e.id, alan="olay_turu",
                                   eski="araç devrildi", yeni="yük düştü",
                                   gerekce="operatör gözlemi"))
    gw = _gw()
    with patch("gozcu.agents.risk.zaman_cizelgesi_ara", return_value=[]):
        risk_analiz_et(gw, store, e)
    istem = gw.sor.call_args.args[1][-1]["content"]
    assert "yük düştü" in istem and "araç devrildi" in istem


def test_assessment_is_persisted_with_a_handoff_to_the_supervisor():
    store = Store(":memory:")
    with patch("gozcu.agents.risk.zaman_cizelgesi_ara", return_value=[]):
        risk_analiz_et(_gw(), store, _epizot(store))
    assert len(store.riskler()) == 1
    assert store.devirler()[-1].hedef_ajan == "nobetci"


def test_degraded_tier_keeps_the_preliminary_risk_instead_of_crashing():
    store = Store(":memory:")
    e = _epizot(store)
    gw = Mock(); gw.sor.return_value = Yanit(bozulmus=True)
    with patch("gozcu.agents.risk.zaman_cizelgesi_ara", return_value=[]):
        r = risk_analiz_et(gw, store, e)
    assert r.seviye == e.on_risk and r.aday_aksiyonlar == []
```

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_risk.py -v
```
Beklenen: `ModuleNotFoundError`

### 3. `gozcu/agents/risk.py` yaz

```python
import json

from pydantic import BaseModel, ConfigDict, Field

from gozcu.memory import zaman_cizelgesi_ara
from gozcu.models import (AdayAksiyon, Devir, Epizot, RiskDegerlendirme,
                          RiskSeviyesi)
from gozcu.tools.registry import ARACLAR

SISTEM = """Sen bir savunma sanayi üretim tesisinin iş güvenliği uzmanısın.
Sana bir olay ve arşivden gelen benzer geçmiş olaylar verilir.

Görevin:
- Risk seviyesini belirle: Düşük, Orta, Yüksek, Kritik
- Gerekçeni Türkçe, kısa cümlelerle yaz. Kamera verisine dayan.
- KESİN HÜKÜM VERME. "olası", "muhtemelen", "görüntüye dayanarak" kullan.
- Önlenebilir olup olmadığını söyle
- Operatör düzeltmesi varsa DÜZELTİLMİŞ hâli esas al
- Her aksiyon önerisini SADECE şu araçlardan birine bağla:
{araclar}

Var olmayan bir araç adı uydurma. Sadece JSON döndür."""


class _RiskYaniti(BaseModel):
    """Modelin döndürdüğü şekil. RiskDegerlendirme'den ayrı, çünkü onun
    id/epizot_id alanları var ve katı şema modunda model onları uydurmaya
    zorlanır."""
    model_config = ConfigDict(extra="forbid")
    seviye: RiskSeviyesi
    gerekce_tr: str = Field(max_length=800)
    onlenebilir: bool
    aday_aksiyonlar: list[AdayAksiyon] = Field(default_factory=list)


def risk_analiz_et(gw, store, epizot: Epizot) -> RiskDegerlendirme:
    gecmis = zaman_cizelgesi_ara(
        gw, store, f"{epizot.ozet_tr} {' '.join(epizot.katilimcilar)}")
    gecmis_metin = "\n".join(f"- {e.ozet_tr}" for e in gecmis) or "- (kayıt yok)"

    duzeltmeler = store.duzeltmeler(epizot.id) if epizot.id else []
    duzeltme_metin = "\n".join(
        f"- OPERATÖR DÜZELTMESİ — {d.alan}: '{d.eski}' yerine '{d.yeni}'"
        for d in duzeltmeler)

    yanit = gw.sor("ana", [
        {"role": "system",
         "content": SISTEM.format(araclar="\n".join(f"- {a}" for a in ARACLAR))},
        {"role": "user",
         "content": f"OLAY: {epizot.ozet_tr}\nÖN RİSK: {epizot.on_risk}\n"
                    f"{duzeltme_metin}\n\nARŞİV:\n{gecmis_metin}"},
    ], sema=_RiskYaniti)

    if yanit.bozulmus:
        cozum = _RiskYaniti(seviye=epizot.on_risk,
                            gerekce_tr="Risk analiz katmanı yanıt vermiyor; "
                                       "ön risk korundu.",
                            onlenebilir=False)
    else:
        try:
            cozum = _RiskYaniti(**json.loads(yanit.icerik))
        except Exception:  # noqa: BLE001
            cozum = _RiskYaniti(seviye=epizot.on_risk,
                                gerekce_tr="Risk analizi üretilemedi; "
                                           "ön risk korundu.",
                                onlenebilir=False)

    # Uydurulmuş araç adları düşürülür, süpervizöre asla iletilmez.
    aksiyonlar = [a for a in cozum.aday_aksiyonlar if a.tool_adi in ARACLAR]

    degerlendirme = RiskDegerlendirme(
        epizot_id=epizot.id, seviye=cozum.seviye,
        gerekce_tr=cozum.gerekce_tr, onlenebilir=cozum.onlenebilir,
        aday_aksiyonlar=aksiyonlar)
    degerlendirme.id = store.kaydet_risk(degerlendirme)

    store.kaydet_devir(Devir(ts=epizot.baslangic_ts,
                             kaynak_ajan="risk_analisti", hedef_ajan="nobetci",
                             neden=f"risk: {cozum.seviye}", guven=0.85,
                             payload_ref=f"risk:{degerlendirme.id}"))
    return degerlendirme
```

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_risk.py -v
```
Beklenen: 6 passed

### 5. Commit

```bash
git add gozcu/agents/risk.py tests/test_risk.py
git commit -m "feat: risk analyst grounding every recommendation in a real tool"
```

## Doğrulama

```bash
uv run pytest tests/test_risk.py -v
```
Beklenen: **6 passed**
