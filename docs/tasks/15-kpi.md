# Görev 15 — KPI ve benchmark (`benchmark/`)

**Sahip:** `rumeysaoru` · **Gün:** 26 Ağustos sabahı · **Süre:** ~3 saat
**Bağımlılık:** [02](02-olay-deposu.md), [17](17-cikti-sozlesmesi.md)
**Etiket:** `cold-start`

## Bağlam

### Proje ne?

Gözcü, fabrika kamera kaydını izleyip olayları fark eden ve operatörle Türkçe
konuşan bir karar destek sistemi. TEKNOFEST Yapay Zekâ Dil Ajanları Yarışması,
3. senaryo. Teslim 26 Ağustos 23:59.

### Bu görev neden var?

Şartname iki şey istiyor: *"katılımcılar, geliştirdikleri sistemin başarısını
ölçmek için kendi metriklerini tanımlamalıdır"* ve teslim kalemi olarak
**benchmark kodu**. Ayrıca dokümantasyonda "ölçümleme sonuçları" bölümü zorunlu.

**Ve bir tanesi sunumun manşet sayısı oluyor.** Mimarimizin iddiası şu: her karar
yetecek en ucuz modele düşüyor, kararların büyük çoğunluğu en küçük modelde
kapanıyor. Bu iddianın kanıtı senin üreteceğin **karar dağılımı grafiği**.
4 dakikalık sunumda tek grafik gidiyor ve o bu.

**İyi haber:** metriklerin tamamı depodaki kayıtlardan hesaplanıyor. Model
çağrısı yok, etiketleme neredeyse yok.

## Kurulum

```bash
git clone git@github.com:uvyscengiz/gozcu-ai-teknofest.git
cd gozcu-ai-teknofest
uv sync --extra dev
uv run pytest tests/ -v
```

## Bağımlı olduğun imzalar

```python
# gozcu/store.py — hepsi okuma
Store(db_path)                      # dosya yolu verilebilir, ":memory:" de olur
Store.gozlemler() -> list[Gozlem]
Store.yorumlar() -> list[Yorum]     # Yorum.model: str, .token: int, .gecikme_ms: int
Store.epizotlar() -> list[Epizot]   # Epizot.baslangic_ts: float
Store.devirler() -> list[Devir]     # Devir.kaynak_ajan, .hedef_ajan
Store.duzeltmeler(epizot_id) -> list[Duzeltme]   # .epizot_id, .eski, .yeni

# gozcu/report.py  (Görev 17)
ciktiyi_derle(store, ozet: str, kok_neden=None) -> PipelineCiktisi
```

**Ajan adları** (`Devir.kaynak_ajan` / `hedef_ajan` alanlarında görürsün):
`algi`, `yonlendirici`, `yorumlayici`, `sentezleyici`, `risk_analisti`,
`nobetci`, `raportor`.

## Ne yapacaksın

`benchmark/kpi.py` — beş saf fonksiyon:

```python
karar_dagilimi(store) -> dict[str, float]
vlm_tetikleme_orani(store) -> float
olay_basina_token(store) -> dict[str, float]
duzeltme_yayilimi(store) -> float
zaman_damgasi_sapmasi(store, gercek: list[tuple[float, float]]) -> float
```

**`karar_dagilimi` için kritik uyarı:** `devir` tablosuna sadece yönlendirici
yazmıyor — sentezleyici ve risk analisti de kendi devirlerini yazıyor. Hepsini
sayarsan oranlar 1'e toplanmaz ve manşet sayı sulanır. **Sadece
`kaynak_ajan == "yonlendirici"` olan satırları say.**

`benchmark/run.py` — etiketli her klibi koşturur, klip başına bir SQLite dosyası
üretir, `runs/kpi.json` yazar.
`benchmark/report.py` — onu okuyup `runs/kpi.md` ve karar dağılımı grafiğini üretir.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_kpi.py`

```python
from benchmark.kpi import (duzeltme_yayilimi, karar_dagilimi,
                           olay_basina_token, vlm_tetikleme_orani,
                           zaman_damgasi_sapmasi)
from gozcu.models import Devir, Duzeltme, Epizot, Gozlem, Yorum
from gozcu.store import Store


def _store(devirler=(), gozlem=0, yorum=0):
    s = Store(":memory:")
    for kaynak, hedef in devirler:
        s.kaydet_devir(Devir(ts=0.0, kaynak_ajan=kaynak, hedef_ajan=hedef,
                             neden="n", guven=0.5, payload_ref="r"))
    for i in range(gozlem):
        s.kaydet_gozlem(Gozlem(ts=float(i)))
    for i in range(yorum):
        s.kaydet_yorum(Yorum(gozlem_ts=float(i), aciklama="x", model="vlm",
                             token=100, gecikme_ms=500))
    return s


def test_decision_distribution_sums_to_one():
    s = _store([("yonlendirici", "algi"), ("yonlendirici", "algi"),
                ("yonlendirici", "yorumlayici"), ("yonlendirici", "nobetci")])
    d = karar_dagilimi(s)
    assert abs(sum(d.values()) - 1.0) < 1e-9
    assert d["yonlendiricide_kapandi"] == 0.5


def test_distribution_ignores_handoffs_written_by_other_agents():
    """sentezleyici ve risk_analisti de devir yazıyor; onları saymak manşet
    sayıyı sulandırır."""
    s = _store([("yonlendirici", "algi"),
                ("sentezleyici", "risk_analisti"),
                ("risk_analisti", "nobetci")])
    assert karar_dagilimi(s)["yonlendiricide_kapandi"] == 1.0


def test_distribution_is_all_zero_on_an_empty_run():
    assert sum(karar_dagilimi(_store()).values()) == 0.0


def test_vlm_trigger_rate_is_interpretations_over_observations():
    assert vlm_tetikleme_orani(_store(gozlem=100, yorum=3)) == 0.03


def test_trigger_rate_is_zero_not_a_crash_on_an_empty_run():
    assert vlm_tetikleme_orani(_store()) == 0.0


def test_token_totals_are_grouped_by_model():
    assert olay_basina_token(_store(gozlem=10, yorum=2))["vlm"] == 200.0


def test_correction_propagation_is_one_when_the_summary_was_updated():
    s = Store(":memory:")
    e = Epizot(baslangic_ts=0.0, faz="sonuc", ozet_tr="yük düştü",
               on_risk="Orta")
    e.id = s.epizot_ac(e)
    s.kaydet_duzeltme(Duzeltme(ts=0.0, epizot_id=e.id, alan="olay_turu",
                               eski="araç devrildi", yeni="yük düştü",
                               gerekce="g"))
    assert duzeltme_yayilimi(s) == 1.0


def test_correction_propagation_is_zero_when_the_summary_was_not_updated():
    s = Store(":memory:")
    e = Epizot(baslangic_ts=0.0, faz="sonuc", ozet_tr="araç devrildi",
               on_risk="Orta")
    e.id = s.epizot_ac(e)
    s.kaydet_duzeltme(Duzeltme(ts=0.0, epizot_id=e.id, alan="olay_turu",
                               eski="araç devrildi", yeni="yük düştü",
                               gerekce="g"))
    assert duzeltme_yayilimi(s) == 0.0


def test_timestamp_drift_is_the_median_absolute_error():
    s = Store(":memory:")
    for ts in (10.0, 30.0):
        s.epizot_ac(Epizot(baslangic_ts=ts, faz="baslangic", ozet_tr="x",
                           on_risk="Orta"))
    assert zaman_damgasi_sapmasi(s, [(12.0, 20.0), (33.0, 40.0)]) == 2.5
```

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_kpi.py -v
```
Beklenen: `ModuleNotFoundError: No module named 'benchmark'`

### 3. `benchmark/kpi.py` yaz

`benchmark/__init__.py` (boş) de gerekiyor.

```python
from collections import defaultdict

BOS_DAGILIM = {"yonlendiricide_kapandi": 0.0, "yorumlamaya_gitti": 0.0,
               "sentezlemeye_gitti": 0.0, "nobetciye_yukseldi": 0.0}


def karar_dagilimi(store) -> dict[str, float]:
    """Yönlendiricinin kararlarının nereye düştüğü.

    SADECE yönlendiricinin yazdığı devirler sayılır — sentezleyici ve risk
    analisti de devir yazıyor ve onları katmak oranları bozar.
    """
    devirler = [d for d in store.devirler() if d.kaynak_ajan == "yonlendirici"]
    if not devirler:
        return dict(BOS_DAGILIM)
    n = len(devirler)
    sayac: dict[str, int] = defaultdict(int)
    for d in devirler:
        sayac[d.hedef_ajan] += 1
    return {
        "yonlendiricide_kapandi": sayac["algi"] / n,
        "yorumlamaya_gitti": sayac["yorumlayici"] / n,
        "sentezlemeye_gitti": sayac["sentezleyici"] / n,
        "nobetciye_yukseldi": sayac["nobetci"] / n,
    }


def vlm_tetikleme_orani(store) -> float:
    """Karelerin yüzde kaçı görsel modele gitti. Hedef: %5'in altı."""
    gozlem = len(store.gozlemler())
    return 0.0 if gozlem == 0 else len(store.yorumlar()) / gozlem


def olay_basina_token(store) -> dict[str, float]:
    toplam: dict[str, float] = defaultdict(float)
    for y in store.yorumlar():
        toplam[y.model] += y.token
    return dict(toplam)


def duzeltme_yayilimi(store) -> float:
    """Operatör düzeltmelerinin kaçı epizot özetine yansıdı. Hedef: 1.0."""
    epizotlar = {e.id: e for e in store.epizotlar()}
    duzeltmeler = [d for eid in epizotlar for d in store.duzeltmeler(eid)]
    if not duzeltmeler:
        return 1.0
    yansiyan = sum(1 for d in duzeltmeler
                   if d.epizot_id in epizotlar
                   and d.yeni in epizotlar[d.epizot_id].ozet_tr)
    return yansiyan / len(duzeltmeler)


def zaman_damgasi_sapmasi(store, gercek: list[tuple[float, float]]) -> float:
    """Etiketli olay başlangıcı ile en yakın epizot başlangıcı arasındaki
    medyan mutlak fark, saniye."""
    epizotlar = store.epizotlar()
    if not epizotlar or not gercek:
        return float("nan")
    sapmalar = sorted(
        min(abs(e.baslangic_ts - baslangic) for e in epizotlar)
        for baslangic, _bitis in gercek)
    orta = len(sapmalar) // 2
    return (sapmalar[orta] if len(sapmalar) % 2
            else (sapmalar[orta - 1] + sapmalar[orta]) / 2)
```

### 4. `benchmark/ground_truth.csv` — 5 klip yeter

15 değil, **5.** Etiketleme el işi ve zamanı yok. `data/` altındaki kliplerden
beşini seç, olay penceresini gözle işaretle.

```csv
video,olay_var,baslangic_s,bitis_s,tur
forklift-accident--qOPnf-YRuk8.mp4,1,12.5,19.0,arac_devrilmesi
fire-single--lleF2nmlkMY.mp4,1,4.0,22.0,yangin
pl1-01--B5xphv6lYkw.mp4,0,,,yok
```

`tur` sözlüğü — sadece bunları kullan:
`arac_devrilmesi` · `yuk_dusmesi` · `yangin` · `kkd_ihlali` · `dusme` · `yok`

### 5. `benchmark/run.py` ve `benchmark/report.py`

`run.py` her etiketli klip için: videoyu `run_pipeline` ile koşturur, o klibin
deposunu `runs/<klip>.db` olarak saklar, `kpi.py`'daki beş fonksiyonu çağırır,
`runs/kpi.json` yazar.

`report.py` `runs/kpi.json`'u okur, `runs/kpi.md` üretir ve **karar dağılımı
çubuk grafiğini** `runs/karar-dagilimi.png` olarak kaydeder (matplotlib).
Slayta giden grafik bu.

Bir klip çökerse **koşuyu durdurma** — hatayı `kpi.json`'a yaz ve devam et.
Kısmi sonuç, hiç sonuç olmamasından iyidir.

### 6. Yeşil olduğunu gör

```bash
uv run pytest tests/test_kpi.py -v
```
Beklenen: 9 passed

### 7. Commit

```bash
git add benchmark tests/test_kpi.py
git commit -m "feat: KPI harness for decision distribution, trigger rate and drift"
```

## Doğrulama

```bash
uv run pytest tests/test_kpi.py -v
```
Beklenen: **9 passed**

## Takıldığında

Üveys'e yaz. **Bekleme** — bu sprintte bir saat, toplam kapasitenin yaklaşık %4'ü.
