# Görev 07 — Sentezleyici: kareler → epizot (`gozcu/agents/synthesizer.py`)

**Sahip:** `uvyscengiz` · **Gün:** 24 Ağustos · **Süre:** ~2.5 saat
**Bağımlılık:** [01](01-sozlesme.md), [02](02-olay-deposu.md), [03](03-gateway.md), [06](06-yonlendirici.md)

## Bağlam

Şartname açıkça şunu istiyor: *"yalnızca kare bazlı analiz etmekle sınırlı
kalmamalı; sahne bütünlüğünü, zamansal ilişkileri ve olay akışını
anlayabilmelidir"* ve *"olayların başlangıç, gelişim ve sonuç süreçlerini ayırt
edebilmeli."*

**Kare bağımsızlığı tam olarak burada kırılıyor.** Dağınık gözlemler ve görsel
yorumlar tek bir `Epizot` kaydına dönüşüyor: hangi fazda, kimler var, Türkçe
özeti ne, ön riski ne.

### Epizot yaşam döngüsü — bu görevin en kritik kısmı

Yönlendirici üç farklı epizot kararı verebiliyor ve **üçü de farklı davranmalı:**

| Karar | Ne yapılır |
|---|---|
| `epizot_ac` | Yeni epizot açılır |
| `epizot_guncelle` | **Açık epizota kaynaşır** — `epizot_guncelle` ile bitiş zamanı, faz ve özet güncellenir. Yeni epizot AÇILMAZ |
| `epizot_kapat` | Açık epizot `durum="kapali"`, `bitis_ts` set edilir, ve **gömme geri çağrısı** tetiklenir |

Üçü de yeni epizot açarsa tek bir forklift kazası N kopya epizota bölünür,
`events[]` çıktısında aynı olay tekrar tekrar görünür ve kare bağımsızlığını
pencere seviyesinde geri getirmiş oluruz. Bu, düzeltilmesi en pahalı hatalardan
biri — testler onu yakalıyor.

Gömme geri çağrısı opsiyonel (`gom=None`): Görev 08 hafızayı yazana kadar bu
görev tek başına tamamlanabilsin diye.

## Kurulum

```bash
uv sync --extra dev
uv run pytest tests/test_router.py tests/test_store.py -v
```

## Bağımlı olduğun imzalar

```python
# gozcu/agents/router.py
mmss(ts: float) -> str

# gozcu/gateway.py
Gateway.sor(kademe, mesajlar, sema=None, araclar=None) -> Yanit
Yanit(icerik, arac_cagrilari, model, gecikme_ms, token, bozulmus)

# gozcu/store.py
Store.epizot_ac(e: Epizot) -> int
Store.epizot_guncelle(epizot_id: int, **alanlar) -> None
Store.acik_epizot() -> Epizot | None
Store.kaydet_devir(d: Devir) -> int

# gozcu/models.py
Epizot(id, baslangic_ts, bitis_ts, faz, ozet_tr, katilimcilar, on_risk, durum)
Yorum(id, gozlem_ts, aciklama, notable_event, model, gecikme_ms, token)
```

## Ne yapacaksın

```python
sentezle(gw, store, pencere, yorum, karar, gom=None) -> Epizot | None
```

`karar` ∈ `{"epizot_ac", "epizot_guncelle", "epizot_kapat"}`.
`gom` verilirse ve karar `epizot_kapat` ise `gom(epizot)` çağrılır.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_synthesizer.py`

```python
from unittest.mock import Mock

from gozcu.agents.synthesizer import sentezle
from gozcu.gateway import Yanit
from gozcu.models import Epizot, Gozlem, Sinyaller, Yorum
from gozcu.store import Store

YANIT = ('{"faz":"gelisim","ozet_tr":"İstif aracı devrildi, yerde hareketsiz '
         'kişi var.","katilimcilar":["istif aracı","personel"],'
         '"on_risk":"Kritik"}')


def _gw():
    gw = Mock(); gw.sor.return_value = Yanit(icerik=YANIT)
    return gw


def _pencere(bas=0, adet=10):
    return [Gozlem(ts=float(bas + t), sinyaller=Sinyaller(kisi_sayisi=1))
            for t in range(adet)]


def test_ac_merges_a_window_into_one_episode():
    store = Store(":memory:")
    yorum = Yorum(gozlem_ts=3.0, aciklama="araç yan yattı", model="m")
    e = sentezle(_gw(), store, _pencere(), yorum, "epizot_ac")
    assert e.baslangic_ts == 0.0 and e.bitis_ts == 9.0
    assert e.on_risk == "Kritik" and e.faz == "gelisim"
    assert len(store.epizotlar()) == 1


def test_guncelle_extends_the_open_episode_instead_of_opening_a_new_one():
    store = Store(":memory:")
    sentezle(_gw(), store, _pencere(0), None, "epizot_ac")
    sentezle(_gw(), store, _pencere(10), None, "epizot_guncelle")
    assert len(store.epizotlar()) == 1
    assert store.epizotlar()[0].bitis_ts == 19.0


def test_kapat_closes_the_open_episode_and_does_not_open_a_new_one():
    store = Store(":memory:")
    sentezle(_gw(), store, _pencere(0), None, "epizot_ac")
    sentezle(_gw(), store, _pencere(10), None, "epizot_kapat")
    assert len(store.epizotlar()) == 1
    e = store.epizotlar()[0]
    assert e.durum == "kapali" and e.bitis_ts == 19.0
    assert store.acik_epizot() is None


def test_kapat_triggers_the_embedding_callback():
    store, gomulen = Store(":memory:"), []
    sentezle(_gw(), store, _pencere(0), None, "epizot_ac", gom=gomulen.append)
    assert gomulen == []
    sentezle(_gw(), store, _pencere(10), None, "epizot_kapat",
             gom=gomulen.append)
    assert len(gomulen) == 1 and gomulen[0].durum == "kapali"


def test_guncelle_without_an_open_episode_opens_one():
    store = Store(":memory:")
    e = sentezle(_gw(), store, _pencere(), None, "epizot_guncelle")
    assert e is not None and len(store.epizotlar()) == 1


def test_sentezle_uses_the_fast_tier_not_the_large_one():
    gw = _gw()
    sentezle(gw, Store(":memory:"), _pencere(), None, "epizot_ac")
    assert gw.sor.call_args.args[0] == "hizli"


def test_degraded_fast_tier_still_produces_an_episode():
    gw = Mock(); gw.sor.return_value = Yanit(bozulmus=True)
    store = Store(":memory:")
    e = sentezle(gw, store, _pencere(), None, "epizot_ac")
    assert e is not None and len(store.epizotlar()) == 1


def test_sentezle_records_a_handoff_to_the_risk_analyst():
    store = Store(":memory:")
    sentezle(_gw(), store, _pencere(), None, "epizot_ac")
    assert store.devirler()[-1].kaynak_ajan == "sentezleyici"
    assert store.devirler()[-1].hedef_ajan == "risk_analisti"
```

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_synthesizer.py -v
```
Beklenen: `ModuleNotFoundError`

### 3. `gozcu/agents/synthesizer.py` yaz

```python
import json

from pydantic import BaseModel, ConfigDict, Field

from gozcu.agents.router import mmss
from gozcu.models import Devir, Epizot, Gozlem, RiskSeviyesi, Yorum

SISTEM = """Sen bir fabrika kontrol odasının kâtibisin. Sana bir zaman
aralığındaki gözlemler ve görsel yorumlar verilir. Bunları TEK BİR OLAY
halinde birleştir.

Kurallar:
- Olayın hangi fazda olduğunu belirt: baslangic, gelisim, sonuc
- Özet Türkçe, kısa cümlelerle, saha terminolojisiyle yazılır
- Görmediğin bir şeyi yazma. Emin değilsen "olası" de.
- Ön riski şu dördünden biri olarak ver: Düşük, Orta, Yüksek, Kritik

Sadece JSON döndür."""

FAZLAR = ("baslangic", "gelisim", "sonuc")


class _Sentez(BaseModel):
    model_config = ConfigDict(extra="forbid")
    faz: str
    ozet_tr: str = Field(max_length=600)
    katilimcilar: list[str] = Field(default_factory=list)
    on_risk: RiskSeviyesi


def _model_sentezi(gw, pencere: list[Gozlem], yorum: Yorum | None,
                   onceki: Epizot | None) -> _Sentez:
    satirlar = [f"{mmss(g.ts)} kişi={g.sinyaller.kisi_sayisi} "
                f"hızlar={g.sinyaller.hizlar or '-'}" for g in pencere]
    if yorum is not None:
        satirlar.append(f"{mmss(yorum.gozlem_ts)} GÖRSEL: {yorum.aciklama}")
    if onceki is not None:
        satirlar.insert(0, f"DEVAM EDEN OLAY: {onceki.ozet_tr}")

    yanit = gw.sor("hizli", [
        {"role": "system", "content": SISTEM},
        {"role": "user", "content": "\n".join(satirlar)},
    ], sema=_Sentez)

    if yanit.bozulmus:
        return _Sentez(faz="gelisim",
                       ozet_tr="Sentez katmanı yanıt vermiyor; "
                               "ham gözlemler kayıtlı.",
                       on_risk="Orta")
    try:
        s = _Sentez(**json.loads(yanit.icerik))
    except Exception:  # noqa: BLE001
        return _Sentez(faz="gelisim",
                       ozet_tr="Sentez üretilemedi; ham gözlemler kayıtlı.",
                       on_risk="Orta")
    if s.faz not in FAZLAR:
        s.faz = "gelisim"
    return s


def sentezle(gw, store, pencere: list[Gozlem], yorum: Yorum | None,
             karar: str, gom=None) -> Epizot | None:
    """Gözlem penceresini bir Epizot'a dönüştürür.

    karar == "epizot_ac"       -> yeni epizot
    karar == "epizot_guncelle" -> açık epizota kaynaşır
    karar == "epizot_kapat"    -> açık epizotu kapatır ve gom(epizot) çağırır
    """
    if not pencere:
        return None

    acik = store.acik_epizot() if karar != "epizot_ac" else None
    s = _model_sentezi(gw, pencere, yorum, acik)
    bitis = pencere[-1].ts

    if acik is None:
        epizot = Epizot(baslangic_ts=pencere[0].ts, bitis_ts=bitis,
                        faz="sonuc" if karar == "epizot_kapat" else s.faz,
                        ozet_tr=s.ozet_tr, katilimcilar=s.katilimcilar,
                        on_risk=s.on_risk,
                        durum="kapali" if karar == "epizot_kapat" else "acik")
        epizot.id = store.epizot_ac(epizot)
    else:
        alanlar = {"bitis_ts": bitis, "ozet_tr": s.ozet_tr,
                   "katilimcilar": s.katilimcilar, "on_risk": s.on_risk,
                   "faz": "sonuc" if karar == "epizot_kapat" else s.faz}
        if karar == "epizot_kapat":
            alanlar["durum"] = "kapali"
        store.epizot_guncelle(acik.id, **alanlar)
        epizot = next(e for e in store.epizotlar() if e.id == acik.id)

    store.kaydet_devir(Devir(ts=epizot.baslangic_ts,
                             kaynak_ajan="sentezleyici",
                             hedef_ajan="risk_analisti",
                             neden=f"{karar} → epizot {epizot.id}",
                             guven=0.8,
                             payload_ref=f"epizot:{epizot.id}"))

    if karar == "epizot_kapat" and gom is not None:
        gom(epizot)

    return epizot
```

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_synthesizer.py -v
```
Beklenen: 8 passed

### 5. Commit

```bash
git add gozcu/agents/synthesizer.py tests/test_synthesizer.py
git commit -m "feat: synthesizer with full episode lifecycle (open/update/close)"
```

## Doğrulama

```bash
uv run pytest tests/test_synthesizer.py -v
```
Beklenen: **8 passed**

## Takvim kaydıysa

Bu görev, 24 Ağustos gecikirse **entegrasyondan önce kesilecek** olan görevdir.
Kesilirse yerine sinyallerden şablon epizot üret (`f"{kisi} kişi, {hiz} hız"`) —
kaba olur ama uçtan uca akış ayakta kalır. Bir arada çalışmayan altı modül,
kaba epizotlu çalışan bir sistemden kötüdür.
