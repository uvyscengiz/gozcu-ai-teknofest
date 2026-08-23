# Görev 10 — Tesis dünyası (`gozcu/fixtures/`)

**Sahip:** `Xana-bit` · **Gün:** 25 Ağustos · **Süre:** ~2 saat
**Bağımlılık:** [01](01-sozlesme.md), [02](02-olay-deposu.md)
**Etiket:** `cold-start` · **Demo'nun yarısı buna dayanıyor**

## Bağlam

### Proje ne?

Gözcü, fabrika kamera kaydını izleyip olayları fark eden ve operatörle Türkçe
konuşan bir karar destek sistemi. TEKNOFEST Yapay Zekâ Dil Ajanları Yarışması,
3. senaryo. Teslim 26 Ağustos 23:59.

### Bu görev neden var?

Demo senaryomuzda iki an var ki **veri olmadan çalışmıyor:**

- Operatör soruyor: *"Daha önce bu araçla ilgili bir olay olmuş muydu?"* →
  arşivde önceki olaylar yoksa sistemin verecek cevabı yok.
- Kapanış raporu diyor ki: *"Muhtemel kök neden: fren bakımının 4 ay gecikmiş
  olması."* → ekipman kaydında o gecikme yoksa rapor boş çıkıyor.

Yani kurgulanması gereken bir **tesis dünyası** var: personel, yetki belgeleri,
ekipman envanteri, bakım geçmişi, önceki olaylar. Bu süs değil, demo'nun taşıyıcı
kolonu.

Ayrıca bu dosyalar yayınlayacağımız **açık veri setinin** parçası oluyor —
şartname indirilebilir bir veri seti linki istiyor.

**İyi haber:** bu görev neredeyse tamamen JSON yazmak. Model çağrısı yok.

## Kurulum

```bash
git clone git@github.com:uvyscengiz/gozcu-ai-teknofest.git
cd gozcu-ai-teknofest
uv sync --extra dev
uv run pytest tests/ -v
```

## Bağımlı olduğun imzalar

```python
# gozcu/models.py
Epizot(id: int | None, baslangic_ts: float, bitis_ts: float | None,
       faz: "baslangic" | "gelisim" | "sonuc", ozet_tr: str,
       katilimcilar: list[str],
       on_risk: "Düşük" | "Orta" | "Yüksek" | "Kritik",
       durum: "acik" | "kapali")

# gozcu/store.py
Store.epizot_ac(e: Epizot) -> int
Store.epizotlar() -> list[Epizot]
Store.embeddingler() -> list[tuple[int, list[float]]]

# gozcu/memory.py
epizodu_gom(gw, store, epizot: Epizot) -> None
```

## Ne yapacaksın

Dört fixture dosyası + bir yükleyici.

```python
# gozcu/fixtures/loader.py
gecmisi_yukle(gw, store) -> int    # önceki olayları arşive yükler ve gömer
```

**Senaryo tutarlılığı şart.** Demo videosundaki olay `IST-04` numaralı istif
aracının B-Hattı sevkiyat alanında yük düşürmesi. Dolayısıyla:

- `IST-04` ekipman envanterinde olmalı, **bakımı gecikmiş** olmalı
- B-Hattı vardiyasında **yetki belgesi olmayan** en az bir kişi olmalı
- Önceki olaylardan **en az biri `IST-04` ile ilgili** olmalı

## Adımlar

### 1. Başarısız testi yaz — `tests/test_fixtures.py`

```python
from unittest.mock import Mock

from gozcu.fixtures.loader import gecmisi_yukle
from gozcu.store import Store
from gozcu.tools.registry import cagir


def test_the_incident_vehicle_has_overdue_brake_maintenance():
    g = cagir(Store(":memory:"), "ekipman_gecmisi_sorgula",
              {"ekipman_id": "IST-04"})
    assert g["geciken_bakim_ay"] >= 4
    assert any("fren" in b["islem"].lower() for b in g["bakim_gecmisi"])


def test_the_shift_has_a_person_without_forklift_certification():
    p = cagir(Store(":memory:"), "vardiya_personel_sorgula",
              {"bolge": "B-Hattı", "zaman": "03:12"})["personel"]
    assert any("istif_araci" not in k["yetkiler"] for k in p)


def test_prior_incidents_are_loaded_closed_and_embedded():
    store, gw = Store(":memory:"), Mock()
    gw.goem.return_value = [0.1, 0.2, 0.3]
    n = gecmisi_yukle(gw, store)
    assert n >= 3
    assert len(store.embeddingler()) == n
    assert all(e.durum == "kapali" for e in store.epizotlar())


def test_a_prior_incident_involves_the_same_vehicle_as_the_demo():
    store, gw = Store(":memory:"), Mock()
    gw.goem.return_value = [0.1]
    gecmisi_yukle(gw, store)
    assert any("IST-04" in e.ozet_tr or "IST-04" in e.katilimcilar
               for e in store.epizotlar())


def test_loading_twice_does_not_duplicate_the_archive():
    store, gw = Store(":memory:"), Mock()
    gw.goem.return_value = [0.1]
    n = gecmisi_yukle(gw, store)
    gecmisi_yukle(gw, store)
    assert len(store.epizotlar()) == n
```

Dördüncü test demo anını koruyor: operatör bu araçla ilgili geçmişi soruyor ve
arşivin cevabı olmak zorunda.

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_fixtures.py -v
```
Beklenen: fixture dosyaları yok.

### 3. `gozcu/fixtures/personel.json`

```json
{
  "personel": [
    {"ad": "M.K.", "bolge": "B-Hattı", "gorev": "istif aracı operatörü",
     "yetkiler": ["istif_araci", "yuksekte_calisma"], "vardiya": "gece"},
    {"ad": "S.A.", "bolge": "B-Hattı", "gorev": "sevkiyat personeli",
     "yetkiler": [], "vardiya": "gece"},
    {"ad": "H.Y.", "bolge": "B-Hattı", "gorev": "vardiya amiri",
     "yetkiler": ["isg_sorumlusu", "istif_araci"], "vardiya": "gece"},
    {"ad": "E.D.", "bolge": "C-Hattı", "gorev": "bakım teknisyeni",
     "yetkiler": ["elektrik", "mekanik"], "vardiya": "gece"}
  ]
}
```

### 4. `gozcu/fixtures/ekipman.json`

```json
{
  "ekipman": {
    "IST-04": {
      "tur": "istif aracı", "model": "2019 dizel forklift",
      "bolge": "B-Hattı", "durum": "serviste",
      "geciken_bakim_ay": 4,
      "bakim_gecmisi": [
        {"tarih": "2026-04-11", "islem": "Fren balata kontrolü",
         "sonuc": "uyarı verildi"},
        {"tarih": "2026-01-08", "islem": "Periyodik bakım", "sonuc": "tamam"}
      ],
      "ariza_kayitlari": [
        {"tarih": "2026-06-02",
         "aciklama": "Fren mesafesi uzun, operatör bildirimi"}
      ]
    },
    "IST-07": {
      "tur": "istif aracı", "model": "2022 elektrikli forklift",
      "bolge": "C-Hattı", "durum": "serviste", "geciken_bakim_ay": 0,
      "bakim_gecmisi": [
        {"tarih": "2026-08-01", "islem": "Periyodik bakım", "sonuc": "tamam"}
      ],
      "ariza_kayitlari": []
    }
  }
}
```

### 5. `gozcu/fixtures/gecmis_olaylar.json`

```json
{
  "olaylar": [
    {"baslangic_ts": 0.0, "bitis_ts": 42.0, "faz": "sonuc", "on_risk": "Orta",
     "katilimcilar": ["IST-04", "personel"],
     "ozet_tr": "12 Ağustos gecesi B-Hattı'nda IST-04 istif aracının fren mesafesi uzadı, operatör raf hizasında zor durdu. Yaralanma olmadı, olay kaydı açıldı."},
    {"baslangic_ts": 0.0, "bitis_ts": 25.0, "faz": "sonuc", "on_risk": "Düşük",
     "katilimcilar": ["IST-07"],
     "ozet_tr": "3 Ağustos'ta C-Hattı'nda IST-07 istif aracı yükü hatalı istifledi, yük kaymadı, uyarı yapıldı."},
    {"baslangic_ts": 0.0, "bitis_ts": 60.0, "faz": "sonuc", "on_risk": "Yüksek",
     "katilimcilar": ["personel"],
     "ozet_tr": "28 Temmuz'da B-Hattı sevkiyat alanında kask takmayan personel tespit edildi, vardiya amiri uyardı."}
  ]
}
```

### 6. `gozcu/fixtures/README.md`

Şunu açıkça yaz — bu dosya açık veri setinde yayınlanacak:

> Bu dizindeki veriler **yarışma demosu için uydurulmuştur.** Kurgusal bir
> savunma sanayi üretim tesisini tanımlar. Hiçbir gerçek kişiyi, ekipmanı veya
> olayı temsil etmez. Personel isimleri baş harflerdir ve rastgeledir.

### 7. `gozcu/fixtures/loader.py`

`gozcu/fixtures/__init__.py` (boş) de gerekiyor.

```python
import json
from pathlib import Path

from gozcu.memory import epizodu_gom
from gozcu.models import Epizot

FIXTURE = Path(__file__).parent


def gecmisi_yukle(gw, store) -> int:
    """Önceki olayları arşive yükler ve gömer. Tekrar çağrılırsa çoğaltmaz."""
    veri = json.loads(
        (FIXTURE / "gecmis_olaylar.json").read_text(encoding="utf-8"))
    mevcut = {e.ozet_tr for e in store.epizotlar()}
    n = 0
    for kayit in veri["olaylar"]:
        if kayit["ozet_tr"] in mevcut:
            continue
        e = Epizot(**kayit, durum="kapali")
        e.id = store.epizot_ac(e)
        epizodu_gom(gw, store, e)
        n += 1
    return n or len(veri["olaylar"])
```

### 8. Yeşil olduğunu gör

```bash
uv run pytest tests/test_fixtures.py -v
```
Beklenen: 5 passed

### 9. Commit

```bash
git add gozcu/fixtures tests/test_fixtures.py
git commit -m "feat: seeded facility world — personnel, equipment, prior incidents"
```

## Doğrulama

```bash
uv run pytest tests/test_fixtures.py -v
```
Beklenen: **5 passed**

## Takıldığında

Üveys'e yaz. **Bekleme** — bu sprintte bir saat, toplam kapasitenin yaklaşık %4'ü.
