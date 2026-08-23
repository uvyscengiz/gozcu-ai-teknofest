# Görev 01 — Paylaşılan sözleşme (`gozcu/models.py`)

**Sahip:** `uvyscengiz` · **Gün:** 23 Ağustos · **Süre:** ~1.5 saat
**Bağımlılık:** [00](00-test-altyapisi.md)

## Bağlam

Sistemdeki her modül birbirine tipli kayıtlar geçiriyor — serbest metin değil.
Bu dosya o kayıtların tamamını tanımlıyor. Diğer 16 görev bu tiplere karşı kod
yazacak, o yüzden **ilk bu iniyor** ve sonradan değişmiyor.

Bir tip eksik çıkarsa buraya eklenir; hiçbir görev modül sınırını geçen kendi
tipini uydurmaz.

## Kurulum

```bash
uv sync --extra dev
```

## Ne yapacaksın

`gozcu/models.py` dosyasını oluştur. Pydantic v2, hepsi `extra="forbid"`.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_models.py`

```python
import pytest
from pydantic import ValidationError

from gozcu.models import Epizot, PipelineCiktisi, RouterKarari, Sinyaller


def test_router_karari_rejects_unknown_decision():
    with pytest.raises(ValidationError):
        RouterKarari(karar="belki", gerekce="x", guven=0.5)


def test_epizot_requires_known_risk_level():
    with pytest.raises(ValidationError):
        Epizot(baslangic_ts=0.0, faz="baslangic", ozet_tr="x",
               on_risk="High", durum="acik")


def test_pipeline_ciktisi_has_the_four_sartname_keys():
    c = PipelineCiktisi(summary="özet", events=[], risk="Yüksek", actions=[])
    assert set(c.model_dump(exclude_none=True)) == {
        "summary", "events", "risk", "actions"}


def test_sinyaller_defaults_are_empty_not_none():
    s = Sinyaller()
    assert s.hizlar == {} and s.kaybolan_trackler == [] and s.kisi_sayisi == 0
```

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_models.py -v
```
Beklenen: `ModuleNotFoundError: No module named 'gozcu.models'`

### 3. `gozcu/models.py` yaz

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RiskSeviyesi = Literal["Düşük", "Orta", "Yüksek", "Kritik"]
AjanAdi = Literal["algi", "yonlendirici", "yorumlayici", "sentezleyici",
                  "risk_analisti", "nobetci", "raportor"]


class Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Tespit(Base):
    sinif: str
    guven: float
    kutu: tuple[float, float, float, float]
    track_id: int | None = None


class Sinyaller(Base):
    hizlar: dict[int, float] = Field(default_factory=dict)
    kaybolan_trackler: list[int] = Field(default_factory=list)
    kisi_sayisi: int = 0
    kisi_sayisi_degisim: int = 0
    toplanma: bool = False


class Gozlem(Base):
    id: int | None = None
    ts: float
    tespitler: list[Tespit] = Field(default_factory=list)
    sinyaller: Sinyaller = Field(default_factory=Sinyaller)


class RouterKarari(Base):
    karar: Literal["yoksay", "gorsel_incele", "epizot_ac",
                   "epizot_guncelle", "epizot_kapat", "acil_yukselt"]
    gerekce: str = Field(max_length=200)
    guven: float = Field(ge=0.0, le=1.0)


class Yorum(Base):
    id: int | None = None
    gozlem_ts: float
    aciklama: str = Field(max_length=300)
    notable_event: str | None = Field(default=None, max_length=200)
    model: str
    gecikme_ms: int = 0
    token: int = 0


class Epizot(Base):
    id: int | None = None
    baslangic_ts: float
    bitis_ts: float | None = None
    faz: Literal["baslangic", "gelisim", "sonuc"]
    ozet_tr: str = Field(max_length=600)
    katilimcilar: list[str] = Field(default_factory=list)
    on_risk: RiskSeviyesi
    durum: Literal["acik", "kapali"] = "acik"


class AdayAksiyon(Base):
    aciklama_tr: str = Field(max_length=200)
    tool_adi: str
    parametreler: dict = Field(default_factory=dict)


class RiskDegerlendirme(Base):
    id: int | None = None
    epizot_id: int
    seviye: RiskSeviyesi
    gerekce_tr: str = Field(max_length=800)
    onlenebilir: bool
    aday_aksiyonlar: list[AdayAksiyon] = Field(default_factory=list)


class Devir(Base):
    id: int | None = None
    ts: float
    kaynak_ajan: AjanAdi
    hedef_ajan: AjanAdi
    neden: str = Field(max_length=200)
    guven: float = Field(ge=0.0, le=1.0)
    payload_ref: str


class AksiyonKaydi(Base):
    id: int | None = None
    ts: float
    tool_adi: str
    parametreler: dict = Field(default_factory=dict)
    sonuc: dict = Field(default_factory=dict)
    kim: Literal["ajan", "operator"]
    onay_durumu: Literal["gerekmiyor", "bekliyor", "onaylandi", "reddedildi"]


class Duzeltme(Base):
    id: int | None = None
    ts: float
    epizot_id: int
    alan: str
    eski: str
    yeni: str
    gerekce: str = Field(max_length=300)


class DiyalogSatiri(Base):
    id: int | None = None
    ts: float
    rol: Literal["operator", "nobetci", "sistem"]
    metin: str


class OlayOzeti(Base):
    time: str = Field(pattern=r"^\d{2}:\d{2}$")
    event: str = Field(max_length=200)


class Ayrintili(Base):
    epizotlar: list[Epizot] = Field(default_factory=list)
    risk_degerlendirmeleri: list[RiskDegerlendirme] = Field(default_factory=list)
    devir_zinciri: list[Devir] = Field(default_factory=list)
    aksiyon_defteri: list[AksiyonKaydi] = Field(default_factory=list)
    kok_neden_raporu: dict | None = None


class PipelineCiktisi(Base):
    summary: str
    events: list[OlayOzeti] = Field(default_factory=list)
    risk: RiskSeviyesi
    actions: list[str] = Field(default_factory=list)
    ayrintili: Ayrintili | None = None
```

`kisi_sayisi_degisim` mevcut `signals.py`'daki `person_count_delta`'nın karşılığı —
donuk algı katmanı bunu zaten hesaplıyor, kaybetmeyelim. `toplanma` ise
`signals.py`'da **hesaplanmıyor**; Görev 17'deki adaptör onu
`kisi_sayisi >= 3` kuralıyla türetecek.

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_models.py -v
```
Beklenen: 4 passed

### 5. Commit

```bash
git add gozcu/models.py tests/test_models.py
git commit -m "feat: shared Pydantic contract for the agent layer"
```

## Doğrulama

```bash
uv run pytest tests/test_models.py -v
```
Beklenen: **4 passed**
