# Görev 17 — Çıktı sözleşmesi ve entegrasyon (`gozcu/report.py`, `gozcu/run.py`)

**Sahip:** `uvyscengiz` · **Gün:** 26 Ağustos sabahı · **Süre:** ~3 saat
**Bağımlılık:** hepsi
**Puanın %35'i tek bir dosyada — projedeki en yüksek getirili teslim**

## Bağlam

Şartnamenin puanladığı senaryo şu: video yüklenir, sistem **zaman damgalı olay
listesi, genel özet, risk değerlendirmesi ve aksiyon önerileri** üretir.
Verdikleri örnek JSON'un anahtarları `summary`, `events`, `risk`, `actions`.

**Bu dört anahtar, diğer her şey çökse bile üretilmek zorunda.** Jüri çıktımızı
kendi örnekleriyle karşılaştıracak; aynı anahtarları görmeli. Bozulmuş bir koşu
bile geçerli, notlandırılabilir bir sonuç döndürmeli.

Eklediğimiz her şey — fazlı epizotlar, devir defteri, risk gerekçeleri, aksiyon
defteri, kök neden raporu — o sözleşmenin **yanında**, `ayrintili` anahtarı
altında duruyor. Yerine değil.

İkinci kural: `actions[]` metinleri Risk Analisti'nin **gerçekten bir araca
eşlediği** adaylardan türetiliyor. İnsanın okuduğu liste ile makinenin aksiyon
defteri birbirinden ayrışamaz.

## Kurulum

```bash
uv sync --extra dev
uv run pytest tests/ -v      # her şey yeşil olmalı
```

## Ne yapacaksın

Üç parça.

### A. `gozcu/report.py` — sözleşme derleyicisi

```python
ciktiyi_derle(store, ozet: str, kok_neden=None) -> PipelineCiktisi
```

### B. `gozcu/adapter.py` — donuk algı katmanını modellere bağlar

Mevcut `signals.py` `FrameSignals(velocities, vanished_tracks, person_count,
person_count_delta)` üretiyor; bizim `Sinyaller` tipimizin bir de `toplanma`
alanı var ve **algı katmanı onu hesaplamıyor.** Burada türetiyoruz.

```python
gozlem_uret(frame_ts, tespitler, frame_signals) -> Gozlem
TOPLANMA_ESIGI = 3
```

### C. `gozcu/run.py` — uçtan uca akış

`run_pipeline(video_path)` artık: kare çıkar → `Gozlem` üret → `KararDongusu`
kur → koştur → `ciktiyi_derle` döndür.

**Genişletilmiş yolun tamamı `try` içinde.** Çöktüğünde bile dört anahtarlı
geçerli bir `PipelineCiktisi` dönmeli, `ayrintili=None` ile.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_report.py`

```python
from gozcu.adapter import gozlem_uret
from gozcu.models import (AdayAksiyon, AksiyonKaydi, Epizot, RiskDegerlendirme)
from gozcu.report import ciktiyi_derle
from gozcu.store import Store


class _FS:
    def __init__(self, **kw):
        self.velocities = kw.get("velocities", {})
        self.vanished_tracks = kw.get("vanished_tracks", [])
        self.person_count = kw.get("person_count", 0)
        self.person_count_delta = kw.get("person_count_delta", 0)


def test_four_keys_exist_even_with_a_completely_empty_run():
    c = ciktiyi_derle(Store(":memory:"), ozet="Kayda değer olay yok.")
    d = c.model_dump(exclude_none=True)
    assert {"summary", "events", "risk", "actions"} <= set(d)
    assert d["risk"] == "Düşük"


def test_events_use_mmss_and_come_from_episodes():
    store = Store(":memory:")
    store.epizot_ac(Epizot(baslangic_ts=15.0, faz="baslangic",
                           ozet_tr="İstif aracı devrildi", on_risk="Yüksek"))
    c = ciktiyi_derle(store, ozet="ö")
    assert c.events[0].time == "00:15"
    assert c.events[0].event == "İstif aracı devrildi"


def test_overall_risk_is_the_highest_assessed_level():
    store = Store(":memory:")
    for seviye in ("Düşük", "Kritik", "Orta"):
        store.kaydet_risk(RiskDegerlendirme(epizot_id=1, seviye=seviye,
                                            gerekce_tr="g", onlenebilir=True))
    assert ciktiyi_derle(store, ozet="ö").risk == "Kritik"


def test_risk_falls_back_to_episode_preliminary_when_no_assessment_exists():
    store = Store(":memory:")
    store.epizot_ac(Epizot(baslangic_ts=0.0, faz="gelisim", ozet_tr="x",
                           on_risk="Yüksek"))
    assert ciktiyi_derle(store, ozet="ö").risk == "Yüksek"


def test_actions_are_rendered_from_tool_backed_candidates_only():
    store = Store(":memory:")
    store.kaydet_risk(RiskDegerlendirme(
        epizot_id=1, seviye="Kritik", gerekce_tr="g", onlenebilir=True,
        aday_aksiyonlar=[AdayAksiyon(aciklama_tr="Sağlık ekibini çağır",
                                     tool_adi="saglik_ekibi_cagir")]))
    assert ciktiyi_derle(store, ozet="ö").actions == ["Sağlık ekibini çağır"]


def test_duplicate_actions_are_not_repeated():
    store = Store(":memory:")
    for _ in range(3):
        store.kaydet_risk(RiskDegerlendirme(
            epizot_id=1, seviye="Orta", gerekce_tr="g", onlenebilir=True,
            aday_aksiyonlar=[AdayAksiyon(aciklama_tr="Alanı güvenlik altına al",
                                         tool_adi="saha_alarmi")]))
    assert ciktiyi_derle(store, ozet="ö").actions == [
        "Alanı güvenlik altına al"]


def test_detail_block_is_attached_but_never_replaces_the_four_keys():
    store = Store(":memory:")
    store.kaydet_aksiyon(AksiyonKaydi(ts=1.0, tool_adi="saha_alarmi",
                                      parametreler={}, sonuc={}, kim="ajan",
                                      onay_durumu="gerekmiyor"))
    c = ciktiyi_derle(store, ozet="ö")
    assert c.ayrintili is not None and len(c.ayrintili.aksiyon_defteri) == 1
    assert c.summary == "ö"


def test_adapter_derives_gathering_from_person_count():
    g = gozlem_uret(1.0, [], _FS(person_count=3))
    assert g.sinyaller.toplanma is True
    assert gozlem_uret(1.0, [], _FS(person_count=2)).sinyaller.toplanma is False


def test_adapter_keeps_the_person_count_delta():
    g = gozlem_uret(1.0, [], _FS(person_count=4, person_count_delta=2))
    assert g.sinyaller.kisi_sayisi_degisim == 2


def test_adapter_maps_velocities_and_vanished_tracks():
    g = gozlem_uret(2.0, [], _FS(velocities={7: 3.1}, vanished_tracks=[9]))
    assert g.sinyaller.hizlar == {7: 3.1}
    assert g.sinyaller.kaybolan_trackler == [9]
    assert g.ts == 2.0
```

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_report.py -v
```
Beklenen: `ModuleNotFoundError`

### 3. `gozcu/adapter.py` yaz

```python
from gozcu.models import Gozlem, Sinyaller, Tespit

TOPLANMA_ESIGI = 3


def gozlem_uret(frame_ts: float, tespitler, frame_signals) -> Gozlem:
    """Donuk algı katmanının çıktısını ajan katmanının tipine çevirir.

    `toplanma` signals.py'da hesaplanmıyor — burada kişi sayısından
    türetiliyor. Eşiği aşan kişi sayısı 'toplanma' sayılıyor; bu bir
    heuristik ve yönlendiriciye sadece bir sinyal olarak gidiyor, karar
    olarak değil.
    """
    return Gozlem(
        ts=frame_ts,
        tespitler=[Tespit(sinif=t.class_name, guven=getattr(t, "confidence", 1.0),
                          kutu=tuple(float(v) for v in t.bbox),
                          track_id=getattr(t, "track_id", None))
                   for t in tespitler],
        sinyaller=Sinyaller(
            hizlar=dict(frame_signals.velocities),
            kaybolan_trackler=list(frame_signals.vanished_tracks),
            kisi_sayisi=frame_signals.person_count,
            kisi_sayisi_degisim=frame_signals.person_count_delta,
            toplanma=frame_signals.person_count >= TOPLANMA_ESIGI))
```

### 4. `gozcu/report.py` yaz

```python
from gozcu.agents.router import mmss
from gozcu.models import Ayrintili, OlayOzeti, PipelineCiktisi, RiskSeviyesi

SIRA: list[RiskSeviyesi] = ["Düşük", "Orta", "Yüksek", "Kritik"]


def ciktiyi_derle(store, ozet: str, kok_neden=None) -> PipelineCiktisi:
    """Şartnamenin dört anahtarını üretir; her şey ayrintili altında yanına
    eklenir, yerine değil."""
    epizotlar = store.epizotlar()
    riskler = store.riskler()

    events = [OlayOzeti(time=mmss(e.baslangic_ts), event=e.ozet_tr[:200])
              for e in epizotlar]

    seviyeler = [r.seviye for r in riskler] or [e.on_risk for e in epizotlar]
    risk = max(seviyeler, key=SIRA.index) if seviyeler else "Düşük"

    # Sadece araca bağlanmış adaylardan; böylece insanın okuduğu liste ile
    # makinenin aksiyon defteri birbirinden ayrışamaz.
    actions: list[str] = []
    for r in riskler:
        for a in r.aday_aksiyonlar:
            if a.aciklama_tr not in actions:
                actions.append(a.aciklama_tr)

    return PipelineCiktisi(
        summary=ozet, events=events, risk=risk, actions=actions,
        ayrintili=Ayrintili(
            epizotlar=epizotlar,
            risk_degerlendirmeleri=riskler,
            devir_zinciri=store.devirler(),
            aksiyon_defteri=store.aksiyonlar(),
            kok_neden_raporu=kok_neden.model_dump() if kok_neden else None))
```

### 5. `gozcu/run.py` yeniden yaz

```python
def run_pipeline(video_path, store=None, gw=None, nobetci=None):
    """Uçtan uca akış. Genişletilmiş katman çökse bile dört anahtarlı geçerli
    bir çıktı döner — bozulmuş bir koşu da notlandırılabilir olmalı."""
    frames = extract_frames(video_path, output_dir)
    tracked = track_video([f.path for f in frames])
    signals = compute_signals(tracked, [f.timestamp_s for f in frames])

    gozlemler = [gozlem_uret(f.timestamp_s, t, s)
                 for f, t, s in zip(frames, tracked, signals, strict=True)]
    for g in gozlemler:
        store.kaydet_gozlem(g)

    ozet = "Kayda değer olay tespit edilmedi."
    kok_neden = None
    try:
        dongu = KararDongusu(store,
                             yonlendir=lambda p: yonlendir(
                                 gw, p, store.acik_epizot() is not None),
                             yorumla=lambda p: yorumla(
                                 gw, store, p, _kare_yolu(frames)),
                             sentezle=lambda p, y, k: sentezle(
                                 gw, store, p, y, k,
                                 gom=lambda e: epizodu_gom(gw, store, e)))
        for epizot in dongu.calistir(gozlemler):
            if nobetci is not None:
                nobetci.yukselt(epizot)
        if store.epizotlar():
            kok_neden = kok_neden_raporu_uret(gw, store)
            ozet = kok_neden.ne_oldu
    except Exception:  # noqa: BLE001 — bozulmuş koşu da geçerli çıktı vermeli
        return ciktiyi_derle(store, ozet=ozet), output_dir

    return ciktiyi_derle(store, ozet=ozet, kok_neden=kok_neden), output_dir
```

`_kare_yolu(frames)` bir `ts` alıp o ana en yakın karenin dosya yolunu
döndüren kapanış — Görev 04'ün `yorumla` imzası bunu bekliyor.

`app.py` üç satırlık giriş noktası olarak kalsın:

```python
from gozcu.ui.console import baslat

if __name__ == "__main__":
    baslat()
```

### 6. Yeşil olduğunu gör

```bash
uv run pytest tests/ -v
```
Beklenen: hepsi yeşil.

### 7. Uçtan uca dene

```bash
uv run python app.py
```

Bir klip yükle. Dört anahtarlı JSON çıkmalı.

### 8. Commit

```bash
git add gozcu/report.py gozcu/adapter.py gozcu/run.py app.py tests/test_report.py
git commit -m "feat: şartname output contract with detail block and safe fallback"
```

## Doğrulama

```bash
uv run pytest tests/test_report.py -v && uv run pytest tests/ -q
```
Beklenen: **10 passed** ve tüm suite yeşil.
