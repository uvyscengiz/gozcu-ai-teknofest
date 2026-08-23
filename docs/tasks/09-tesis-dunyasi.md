# Görev 09 — Tesis dünyası (`gozcu/fixtures/`)

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
Episode(id: int | None, start_ts: float, end_ts: float | None,
       phase: "baslangic" | "gelisim" | "result", summary_tr: str,
       participants: list[str],
       preliminary_risk: "Düşük" | "Orta" | "Yüksek" | "Kritik",
       state: "open" | "closed")

# gozcu/store.py
Store.create_episode(e: Episode) -> int
Store.episodes() -> list[Episode]
Store.embeddings() -> list[tuple[int, list[float]]]

# gozcu/memory.py
embed_episode(gw, store, episode: Episode) -> bool
#   ^ vektör yazıldıysa True. İstisna ATMIYOR (Görev 08): bozulmuş gömme
#     kademesi, kaydedilmemiş epizot ve gateway hatası hepsi False.
```

## Ne yapacaksın

Dört fixture dosyası + bir yükleyici.

```python
# gozcu/fixtures/loader.py
load_history(gw, store) -> int    # önceki olayları arşive yükler ve gömer
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

from gozcu.fixtures.loader import load_history
from gozcu.store import Store
from gozcu.tools.registry import call_tool


def test_the_incident_vehicle_has_overdue_brake_maintenance():
    g = call_tool(Store(":memory:"), "query_equipment_history",
              {"equipment_id": "IST-04"})
    assert g["overdue_maintenance_months"] >= 4
    assert any("fren" in b["operation"].lower() for b in g["maintenance_history"])


def test_the_shift_has_a_person_without_forklift_certification():
    p = call_tool(Store(":memory:"), "query_shift_personnel",
              {"zone": "B-Hattı", "at_time": "03:12"})["personnel"]
    assert any("forklift_licence" not in k["certifications"] for k in p)


def test_prior_incidents_are_loaded_closed_and_embedded():
    store, gw = Store(":memory:"), Mock()
    gw.embed.return_value = [0.1, 0.2, 0.3]
    n = load_history(gw, store)
    assert n >= 3
    assert len(store.embeddings()) == n
    assert all(e.state == "closed" for e in store.episodes())


def test_a_prior_incident_involves_the_same_vehicle_as_the_demo():
    store, gw = Store(":memory:"), Mock()
    gw.embed.return_value = [0.1]
    load_history(gw, store)
    assert any("IST-04" in e.summary_tr or "IST-04" in e.participants
               for e in store.episodes())


def test_loading_twice_does_not_duplicate_the_archive():
    store, gw = Store(":memory:"), Mock()
    gw.embed.return_value = [0.1]
    n = load_history(gw, store)
    load_history(gw, store)
    assert len(store.episodes()) == n
```

Dördüncü test demo anını koruyor: operatör bu araçla ilgili geçmişi soruyor ve
arşivin cevabı olmak zorunda.

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_fixtures.py -v
```
Beklenen: fixture dosyaları yok.

### 3. `gozcu/fixtures/personnel.json`

```json
{
  "personnel": [
    {"name": "M.K.", "zone": "B-Hattı", "job_title": "istif aracı operatörü",
     "certifications": ["forklift_licence", "working_at_height"], "shift": "gece"},
    {"name": "S.A.", "zone": "B-Hattı", "job_title": "sevkiyat personeli",
     "certifications": [], "shift": "gece"},
    {"name": "H.Y.", "zone": "B-Hattı", "job_title": "shift amiri",
     "certifications": ["safety_officer", "forklift_licence"], "shift": "gece"},
    {"name": "E.D.", "zone": "C-Hattı", "job_title": "bakım teknisyeni",
     "certifications": ["elektrik", "mekanik"], "shift": "gece"}
  ]
}
```

### 4. `gozcu/fixtures/equipment.json`

```json
{
  "equipment": {
    "IST-04": {
      "kind": "istif aracı", "model": "2019 dizel forklift",
      "zone": "B-Hattı", "state": "in_service",
      "overdue_maintenance_months": 4,
      "maintenance_history": [
        {"date": "2026-04-11", "operation": "Fren balata kontrolü",
         "result": "uyarı verildi"},
        {"date": "2026-01-08", "operation": "Periyodik bakım", "result": "tamam"}
      ],
      "fault_records": [
        {"date": "2026-06-02",
         "description": "Fren mesafesi uzun, operatör bildirimi"}
      ]
    },
    "IST-07": {
      "kind": "istif aracı", "model": "2022 elektrikli forklift",
      "zone": "C-Hattı", "state": "in_service", "overdue_maintenance_months": 0,
      "maintenance_history": [
        {"date": "2026-08-01", "operation": "Periyodik bakım", "result": "tamam"}
      ],
      "fault_records": []
    }
  }
}
```

### 5. `gozcu/fixtures/prior_incidents.json`

```json
{
  "incidents": [
    {"start_ts": 0.0, "end_ts": 42.0, "phase": "outcome", "preliminary_risk": "Orta",
     "participants": ["IST-04", "personnel"],
     "summary_tr": "12 Ağustos gecesi B-Hattı'nda IST-04 istif aracının fren mesafesi uzadı, operatör raf hizasında zor durdu. Yaralanma olmadı, olay kaydı açıldı."},
    {"start_ts": 0.0, "end_ts": 25.0, "phase": "outcome", "preliminary_risk": "Düşük",
     "participants": ["IST-07"],
     "summary_tr": "3 Ağustos'ta C-Hattı'nda IST-07 istif aracı yükü hatalı istifledi, yük kaymadı, uyarı yapıldı."},
    {"start_ts": 0.0, "end_ts": 60.0, "phase": "outcome", "preliminary_risk": "Yüksek",
     "participants": ["personnel"],
     "summary_tr": "28 Temmuz'da B-Hattı sevkiyat alanında kask takmayan personnel tespit edildi, shift amiri uyardı."}
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

from gozcu.memory import embed_episode
from gozcu.models import Episode

FIXTURE_DIR = Path(__file__).parent


def load_history(gw, store) -> int:
    """Önceki olayları arşive yükler ve gömer. Tekrar çağrılırsa çoğaltmaz."""
    payload = json.loads(
        (FIXTURE_DIR / "prior_incidents.json").read_text(encoding="utf-8"))
    existing = {e.summary_tr for e in store.episodes()}
    n = 0
    for record in payload["incidents"]:
        if record["summary_tr"] in existing:
            continue
        e = Episode(**record, state="closed")
        e.id = store.create_episode(e)
        if not embed_episode(gw, store, e):
            # Gömme kademesi bozuk: epizot arşivde ama vektörü yok. Tablo
            # zehirlenmedi (boş satır hiç yazılmıyor), sadece bu fikstür
            # kademe düzelip yeniden gömülene kadar aramada bulunmaz.
            print(f"UYARI: fikstür gömülemedi — {e.summary_tr}")
        n += 1
    return n or len(payload["incidents"])
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
