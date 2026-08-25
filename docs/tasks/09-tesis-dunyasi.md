# Görev 09 — Tesis dünyası (`gozcu/fixtures/`)

> ## ✅ TAMAMLANDI — 23 Ağustos 2026, `c6d82ec`
>
> **Tesis dünyası indi.** `gozcu/fixtures/` altında dört JSON, bir yükleyici ve
> veri seti README'si var; `tests/test_fixtures.py` 11 test ile yeşil. Bu
> dosyayı yeniden uygulama — aşağısı ne yapıldığının kaydı.
>
> **Sonraki göreve başlarken bilmen gerekenler**
> ([kararlar](#tamamlanma-notları-gelecek-görevleri-bağlayan) bölümüne bak):
> **sertifikasyon hikâyesi kesildi** — istif aracı operatörünün belgesi tam,
> kök neden tamamen mekanik (fren/bakım zinciri); **olay tarihi sabit**,
> `SCENARIO_DATE = 2026-08-15` ve hiçbir sayı `date.today()`'den türemiyor; ve
> **`overdue` artık saklanmıyor, türetiliyor** —
> `overdue_maintenance_months()` bir fonksiyon, JSON anahtarı değil.

**Bağımlılık:** [01](01-sozlesme.md), [02](02-olay-deposu.md)

## [Görev 10](10-saha-araclari.md) ile ilişkisi

**Fikstürler bu görevde iner; onları okuyan araçlar Görev 10'da.** İkisinin
sahibi aynı kişi ve sıra bellidir: **önce 09, sonra 10.** Bu dosya
`gozcu.tools`'a hiç dokunmaz — bağımlılığı gerçekten sadece 01 ve 02.

Daha önce buradaki iki test `gozcu.tools.registry`'yi import ediyordu, yani
Görev 09 tek başına yeşile dönemiyordu: sahibi önce Görev 10'u yazmak zorunda
kalıyordu ve dosya bunu hiçbir yerde söylemiyordu. O iki test artık ait olduğu
yerde — [Görev 10](10-saha-araclari.md)'un test bloğunda.

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
  olması."* → ekipman kaydında o zincir yoksa rapor boş çıkıyor.

Yani kurgulanması gereken bir **tesis dünyası** var: tesis bölgeleri, vardiya
saatleri, personel, ekipman envanteri, bakım geçmişi, önceki olaylar. Bu süs
değil, demo'nun taşıyıcı kolonu.

Ayrıca bu dosyalar yayınlayacağımız **açık veri setinin** parçası oluyor —
şartname indirilebilir bir veri seti linki istiyor.

**İyi haber:** bu görev neredeyse tamamen JSON yazmak. Model çağrısı yok.

### Senaryo tutarlılığı — iki ürün kararı

Olay **15 Ağustos 2026, 03:12**'de, B-Hattı sevkiyat alanında `IST-04` istif
aracıyla geçiyor. Fikstürler bunu şu iki karara göre kuruyor:

1. **Sertifikasyon hikâyesi kesildi.** Operatörün (`PRS-001`) istif aracı
   belgesi **tam**. Kök neden tamamen mekanik: geciken fren bakımı. Veriyi
   hikâyeye uydurmak yerine hikâye kesildi — `certifications` alanı gerçekçi
   vardiya verisi olarak duruyor ama artık bir kök neden taşımıyor.
2. **Bütün tarihler dosyalarda sabit.** Hiçbir değer "bugün"den hesaplanmıyor;
   aksi hâlde demo aylar sonra oynatıldığında dört ay gecikmiş bakım beş ay
   gecikmiş olur. Tek kaynak `SCENARIO_DATE`.

Dolayısıyla:

- `IST-04` envanterde ve bakımı gecikmiş — ama **gecikme dosyada yazmıyor**,
  bakım vadeleriyle senaryo tarihi arasından türetiliyor.
- Arıza defteri ile olay arşivi aynı olayı (`OLY-2026-0812`) anlatıyor,
  çelişmiyor.
- Önceki olaylardan biri `IST-04` ile ilgili.

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
       phase: "onset" | "development" | "outcome", summary_tr: str,
       participants: list[str],
       preliminary_risk: "Düşük" | "Orta" | "Yüksek" | "Kritik",
       state: "open" | "closed")
#   ^ faz değerleri İNGİLİZCE. Türkçe bir faz yazan fikstür ValidationError
#     ile patlar; risk seviyeleri ise Türkçe kalır.

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

Dört fikstür dosyası + bir yükleyici + veri seti README'si.

```python
# gozcu/fixtures/__init__.py
FIXTURE_DIR: Path                              # fikstürlerin tek adresi

# gozcu/fixtures/loader.py
SCENARIO_DATE: date                            # 2026-08-15, dosyadan okunur
load_fixture(name) -> dict
resolve_zone(name) -> dict | None              # "B-Hattı" / "B" / takma ad
resolve_shift(at_time) -> str | None           # "03:12" -> "night"
overdue_maintenance_months(equipment_id) -> int
load_history(gw, store) -> int                 # arşivi tohumlar ve gömer
```

## Adımlar

### 1. Başarısız testi yaz — `tests/test_fixtures.py`

```python
"""Tesis dünyası fikstürleri — Görev 09.

Bu testler `gozcu.tools`'a DOKUNMAZ. Araçlar Görev 10'un işi; buradaki
sözleşme sadece fikstür dosyaları ve yükleyicidir.
"""

import json
from datetime import date, datetime
from unittest.mock import Mock

import pytest

from gozcu.fixtures import FIXTURE_DIR
from gozcu.fixtures.loader import (SCENARIO_DATE, load_fixture, load_history,
                                   overdue_maintenance_months, resolve_shift,
                                   resolve_zone)
from gozcu.store import Store


def _gateway(vector):
    gw = Mock()
    gw.embed.return_value = vector
    return gw


# --- fikstür içeriği -------------------------------------------------------

def test_the_incident_vehicle_has_an_overdue_brake_service_derived_from_dates():
    """Gecikme veriden ÇIKARILIYOR — dosyada yazan bir sayı değil."""
    vehicle = load_fixture("equipment")["equipment"]["IST-04"]
    brake = [m for m in vehicle["maintenance_history"]
             if m["operation_type"] == "brake_service"]
    assert brake, "IST-04'ün fren bakım kaydı yok"
    assert all("next_due" in m and "interval_months" in m for m in brake)
    # Gecikme sayısı hiçbir yerde sabit yazılmıyor.
    assert "overdue_maintenance_months" not in vehicle
    assert overdue_maintenance_months("IST-04") == 4
    assert overdue_maintenance_months("IST-07") == 0
    # Vade tarihi gerçekten geçmiş ve senaryo tarihinden 4 ay önce.
    due = min(date.fromisoformat(m["next_due"])
              for m in vehicle["maintenance_history"])
    assert due == date(2026, 4, 8) and due < SCENARIO_DATE


def test_the_fault_log_and_the_archive_tell_the_same_ist04_story():
    """Arıza defteri ile olay arşivi aynı olayı anlatmalı, çelişmemeli."""
    faults = load_fixture("equipment")["equipment"]["IST-04"]["fault_records"]
    archive = load_fixture("prior_incidents")["incidents"]
    linked = {f["incident_id"] for f in faults if f["incident_id"]}
    assert linked, "hiçbir arıza kaydı arşivdeki olaya bağlanmamış"
    for incident in archive:
        if incident["equipment_id"] != "IST-04":
            continue
        assert incident["incident_id"] in linked
        fault = next(f for f in faults
                     if f["incident_id"] == incident["incident_id"])
        assert fault["date"] == incident["date"]
        assert "IST-04" in incident["episode"]["summary_tr"]
    # Bağlanmamış arıza kaydı da çelişmemeli: arşivdeki olaydan önce olmalı.
    assert all(f["date"] <= "2026-08-12" for f in faults)


def test_the_night_shift_roster_resolves_from_the_incident_time():
    people = load_fixture("personnel")["personnel"]
    assert resolve_shift("03:12") == "night"
    assert resolve_shift("09:00") == "day"

    on_shift = [p for p in people
                if p["zone"] == "B-Hattı" and p["shift_id"] == "night"]
    assert {p["personnel_id"] for p in on_shift} == {"PRS-001", "PRS-002",
                                                     "PRS-003"}
    # Aynı bölgede gündüz vardiyasında da personel var — filtre taşıyıcı.
    assert any(p["zone"] == "B-Hattı" and p["shift_id"] == "day"
               for p in people)

    by_id = {p["personnel_id"]: p for p in on_shift}
    # Ruling 2: istif aracı operatörünün belgesi TAM. Kök neden mekanik.
    assert by_id["PRS-001"]["job_title"] == "istif aracı operatörü"
    assert "forklift_licence" in by_id["PRS-001"]["certifications"]
    assert by_id["PRS-001"]["assigned_equipment_id"] == "IST-04"
    assert by_id["PRS-003"]["job_title"] == "vardiya amiri"
    # Sevkiyat personelinin istif aracı belgesi yok — gerçekçi, ama kök neden değil.
    assert "forklift_licence" not in by_id["PRS-002"]["certifications"]
    assert by_id["PRS-002"]["certifications"] == ["manual_handling"]
    # Her personelin kararlı bir kimliği ve vardiyası var.
    assert all(p["personnel_id"].startswith("PRS-") for p in people)
    assert len({p["personnel_id"] for p in people}) == len(people)


def test_the_demo_zone_and_line_ids_resolve():
    facility = load_fixture("facility")
    zones = {z["zone_id"]: z for z in facility["zones"]}
    assert {"line_b", "line_b_shipping", "line_c"} <= set(zones)
    assert zones["line_b_shipping"]["line_id"] == "B"
    assert zones["line_b_shipping"]["parent_zone_id"] == "line_b"

    # Görev 10/14 bu adlarla çağırıyor; hepsi aynı bölgeye çözülmeli.
    assert resolve_zone("B-Hattı")["zone_id"] == "line_b"
    assert resolve_zone("B")["zone_id"] == "line_b"
    assert resolve_zone("B-Hattı sevkiyat alanı")["zone_id"] == "line_b_shipping"
    assert resolve_zone("YOK-99") is None

    lines = {ln["line_id"] for ln in facility["production_lines"]}
    assert {"B", "C"} <= lines
    assert all(z["line_id"] in lines or z["line_id"] is None
               for z in facility["zones"])

    shifts = {s["shift_id"]: s for s in facility["shifts"]}
    assert {"night", "day", "evening"} == set(shifts)
    assert shifts["night"]["start"] == "00:00" and shifts["night"]["end"] == "08:00"


def test_the_scenario_dates_are_stamped_and_never_computed_from_today():
    """Demo gerçek zaman geçtikçe kaymamalı: her tarih dosyada sabit."""
    assert SCENARIO_DATE == date(2026, 8, 15)
    assert load_fixture("facility")["facility"]["scenario_date"] == "2026-08-15"
    for incident in load_fixture("prior_incidents")["incidents"]:
        occurred = datetime.fromisoformat(incident["occurred_at"])
        assert incident["episode"]["start_ts"] == pytest.approx(
            occurred.timestamp())
        assert incident["episode"]["start_ts"] > 0.0
        assert occurred.date() < SCENARIO_DATE
        assert incident["date"] == occurred.date().isoformat()


def test_the_fixture_files_live_next_to_the_loader():
    for name in ("personnel", "equipment", "facility", "prior_incidents"):
        path = FIXTURE_DIR / f"{name}.json"
        assert path.is_file()
        json.loads(path.read_text(encoding="utf-8"))
    assert (FIXTURE_DIR / "README.md").is_file()


# --- yükleyici -------------------------------------------------------------

def test_prior_incidents_are_loaded_closed_and_embedded():
    store, gw = Store(":memory:"), _gateway([0.1, 0.2, 0.3])
    n = load_history(gw, store)
    assert n >= 3
    assert len(store.embeddings()) == n
    assert all(e.state == "closed" for e in store.episodes())
    assert all(e.phase in ("onset", "development", "outcome")
               for e in store.episodes())


def test_a_prior_incident_involves_the_same_vehicle_as_the_demo():
    store, gw = Store(":memory:"), _gateway([0.1])
    load_history(gw, store)
    assert any("IST-04" in e.summary_tr or "IST-04" in e.participants
               for e in store.episodes())


def test_loading_twice_does_not_duplicate_the_archive():
    store, gw = Store(":memory:"), _gateway([0.1])
    n = load_history(gw, store)
    assert load_history(gw, store) == 0
    assert len(store.episodes()) == n
    assert len(store.embeddings()) == n


def test_a_degraded_embedding_tier_is_reported_as_zero_not_as_success():
    """Kademe bozuksa yükleyici yalan söylemez: sayı gerçekten yazılanı sayar."""
    store, gw = Store(":memory:"), _gateway([])
    n = load_history(gw, store)
    assert n == 0
    assert len(store.embeddings()) == n
    # Epizotlar yine de arşivde — sadece aramada bulunamıyorlar.
    assert len(store.episodes()) == 3


def test_a_second_call_embeds_what_the_degraded_tier_missed():
    store = Store(":memory:")
    assert load_history(_gateway([]), store) == 0
    n = load_history(_gateway([0.1, 0.2]), store)
    assert n == 3
    assert len(store.episodes()) == 3
    assert len(store.embeddings()) == 3
```

Testlerin hiçbiri `gozcu.tools`'a dokunmuyor: araçlar Görev 10'un işi, buradaki
sözleşme yalnızca fikstür dosyaları ve yükleyici.

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_fixtures.py -v
```
Beklenen: fikstür dosyaları yok.

### 3. `gozcu/fixtures/facility.json`

Bölgeler, hatlar ve vardiya saatleri. `dispatch_medical(location)` ile
`halt_production_line(line_id)` çözecek bir şey bulsun diye var; `at_time`
parametresinin karşılığı da burada.

```json
{
  "facility": {
    "facility_id": "TSS-01",
    "name": "Kurgusal savunma sanayi üretim tesisi",
    "timezone": "Europe/Istanbul",
    "scenario_date": "2026-08-15",
    "scenario_time": "03:12"
  },
  "production_lines": [
    {
      "line_id": "B",
      "name": "B-Hattı",
      "product": "gövde kaynak ve sevkiyat",
      "state": "running",
      "zone_ids": ["line_b", "line_b_shipping"]
    },
    {
      "line_id": "C",
      "name": "C-Hattı",
      "product": "montaj",
      "state": "running",
      "zone_ids": ["line_c", "line_c_assembly"]
    }
  ],
  "zones": [
    {
      "zone_id": "line_b",
      "name": "B-Hattı",
      "line_id": "B",
      "parent_zone_id": null,
      "kind": "production_line",
      "aliases": ["B-Hattı", "B Hattı", "B", "B hattı"],
      "medical_team": "Revir-2",
      "medical_eta_minutes": 2
    },
    {
      "zone_id": "line_b_shipping",
      "name": "B-Hattı sevkiyat alanı",
      "line_id": "B",
      "parent_zone_id": "line_b",
      "kind": "shipping",
      "aliases": ["B-Hattı sevkiyat alanı", "B-Hattı sevkiyat",
                  "sevkiyat alanı", "sevkiyat"],
      "medical_team": "Revir-2",
      "medical_eta_minutes": 2
    },
    {
      "zone_id": "line_c",
      "name": "C-Hattı",
      "line_id": "C",
      "parent_zone_id": null,
      "kind": "production_line",
      "aliases": ["C-Hattı", "C Hattı", "C", "C hattı"],
      "medical_team": "Revir-1",
      "medical_eta_minutes": 5
    },
    {
      "zone_id": "line_c_assembly",
      "name": "C-Hattı montaj alanı",
      "line_id": "C",
      "parent_zone_id": "line_c",
      "kind": "assembly",
      "aliases": ["C-Hattı montaj alanı", "C-Hattı montaj", "montaj alanı"],
      "medical_team": "Revir-1",
      "medical_eta_minutes": 5
    },
    {
      "zone_id": "warehouse",
      "name": "Ambar",
      "line_id": null,
      "parent_zone_id": null,
      "kind": "warehouse",
      "aliases": ["Ambar", "ambar", "depo"],
      "medical_team": "Revir-1",
      "medical_eta_minutes": 7
    }
  ],
  "shifts": [
    {"shift_id": "night", "name": "gece", "label_tr": "gece vardiyası",
     "start": "00:00", "end": "08:00"},
    {"shift_id": "day", "name": "gündüz", "label_tr": "gündüz vardiyası",
     "start": "08:00", "end": "16:00"},
    {"shift_id": "evening", "name": "akşam", "label_tr": "akşam vardiyası",
     "start": "16:00", "end": "24:00"}
  ]
}
```

### 4. `gozcu/fixtures/personnel.json`

```json
{
  "personnel": [
    {"personnel_id": "PRS-001", "name": "M.K.", "zone": "B-Hattı",
     "zone_id": "line_b", "job_title": "istif aracı operatörü",
     "certifications": ["forklift_licence", "working_at_height"],
     "certified_until": "2027-03-01",
     "shift": "gece", "shift_id": "night",
     "assigned_equipment_id": "IST-04"},

    {"personnel_id": "PRS-002", "name": "S.A.", "zone": "B-Hattı",
     "zone_id": "line_b_shipping", "job_title": "sevkiyat personeli",
     "certifications": ["manual_handling"],
     "certified_until": "2027-01-15",
     "shift": "gece", "shift_id": "night",
     "assigned_equipment_id": null},

    {"personnel_id": "PRS-003", "name": "H.Y.", "zone": "B-Hattı",
     "zone_id": "line_b", "job_title": "vardiya amiri",
     "certifications": ["safety_officer", "forklift_licence"],
     "certified_until": "2028-06-30",
     "shift": "gece", "shift_id": "night",
     "assigned_equipment_id": null},

    {"personnel_id": "PRS-004", "name": "E.D.", "zone": "C-Hattı",
     "zone_id": "line_c", "job_title": "bakım teknisyeni",
     "certifications": ["electrical", "mechanical"],
     "certified_until": "2027-11-20",
     "shift": "gece", "shift_id": "night",
     "assigned_equipment_id": null},

    {"personnel_id": "PRS-005", "name": "T.Ö.", "zone": "B-Hattı",
     "zone_id": "line_b", "job_title": "istif aracı operatörü",
     "certifications": ["forklift_licence"],
     "certified_until": "2027-05-10",
     "shift": "gündüz", "shift_id": "day",
     "assigned_equipment_id": "IST-04"},

    {"personnel_id": "PRS-006", "name": "N.Ç.", "zone": "B-Hattı",
     "zone_id": "line_b", "job_title": "vardiya amiri",
     "certifications": ["safety_officer"],
     "certified_until": "2028-02-28",
     "shift": "gündüz", "shift_id": "day",
     "assigned_equipment_id": null}
  ]
}
```

`PRS-00N` kimlikleri kararlı: epizotların `participants` listesi bir insana
ancak böyle bağlanabiliyor. `zone` insana görünen adı taşıyor, `zone_id`
makine kimliğini. Belgeler İngilizce ve tek biçimli.

### 5. `gozcu/fixtures/equipment.json`

```json
{
  "equipment": {
    "IST-04": {
      "kind": "istif aracı",
      "model": "2019 dizel forklift",
      "zone": "B-Hattı",
      "zone_id": "line_b",
      "state": "in_service",
      "commissioned_on": "2019-05-20",
      "maintenance_history": [
        {"date": "2026-01-08", "operation_type": "brake_service",
         "operation": "Fren balata kontrolü",
         "result": "uyarı verildi — balata aşınma sınırında, üç ay içinde değişim önerildi",
         "interval_months": 3, "next_due": "2026-04-08", "completed": true},
        {"date": "2025-10-08", "operation_type": "periodic_service",
         "operation": "Periyodik bakım", "result": "tamam",
         "interval_months": 6, "next_due": "2026-04-08", "completed": true}
      ],
      "fault_records": [
        {"date": "2026-08-12", "time": "23:41",
         "description": "Fren mesafesi uzadı; operatör raf hizasında zor durdu.",
         "reported_by": "PRS-001", "severity": "high",
         "status": "open", "incident_id": "OLY-2026-0812"},
        {"date": "2026-04-19", "time": "10:05",
         "description": "Fren pedalı sertleşti; bakım talebi açıldı, iş emri kapanmadı.",
         "reported_by": "PRS-005", "severity": "medium",
         "status": "open", "incident_id": null}
      ]
    },
    "IST-07": {
      "kind": "istif aracı",
      "model": "2022 elektrikli forklift",
      "zone": "C-Hattı",
      "zone_id": "line_c",
      "state": "in_service",
      "commissioned_on": "2022-02-14",
      "maintenance_history": [
        {"date": "2026-08-01", "operation_type": "periodic_service",
         "operation": "Periyodik bakım", "result": "tamam",
         "interval_months": 6, "next_due": "2027-02-01", "completed": true},
        {"date": "2026-08-01", "operation_type": "brake_service",
         "operation": "Fren balata kontrolü", "result": "tamam",
         "interval_months": 6, "next_due": "2027-02-01", "completed": true}
      ],
      "fault_records": []
    }
  }
}
```

Dikkat: **`overdue_maintenance_months` diye bir anahtar yok.** Her bakım
kaydının `next_due` vadesi var; gecikme oradan türetiliyor. Elle yazılan bir
sayı kendi tarihleriyle çelişebilir — bir kez çelişti de (dosyada `4` yazıyordu,
tarihlerin söylediği ~7.5 aydı).

### 6. `gozcu/fixtures/prior_incidents.json`

```json
{
  "incidents": [
    {
      "incident_id": "OLY-2026-0812",
      "date": "2026-08-12",
      "occurred_at": "2026-08-12T23:41:00+03:00",
      "zone_id": "line_b_shipping",
      "line_id": "B",
      "shift_id": "night",
      "equipment_id": "IST-04",
      "equipment_fault": true,
      "episode": {
        "start_ts": 1786567260.0,
        "end_ts": 1786567302.0,
        "phase": "outcome",
        "preliminary_risk": "Orta",
        "participants": ["IST-04", "PRS-001"],
        "summary_tr": "12 Ağustos gecesi B-Hattı sevkiyat alanında IST-04 istif aracının fren mesafesi uzadı; operatör raf hizasında zor durdu. Yaralanma olmadı, arıza kaydı açıldı ve gecikmiş fren bakımı yeniden talep edildi."
      }
    },
    {
      "incident_id": "OLY-2026-0803",
      "date": "2026-08-03",
      "occurred_at": "2026-08-03T14:20:00+03:00",
      "zone_id": "line_c_assembly",
      "line_id": "C",
      "shift_id": "day",
      "equipment_id": "IST-07",
      "equipment_fault": false,
      "episode": {
        "start_ts": 1785756000.0,
        "end_ts": 1785756025.0,
        "phase": "outcome",
        "preliminary_risk": "Düşük",
        "participants": ["IST-07"],
        "summary_tr": "3 Ağustos'ta C-Hattı montaj alanında IST-07 istif aracı yükü hatalı istifledi. Yük kaymadı, ekipman arızası saptanmadı, operatöre uyarı yapıldı."
      }
    },
    {
      "incident_id": "OLY-2026-0728",
      "date": "2026-07-28",
      "occurred_at": "2026-07-28T02:05:00+03:00",
      "zone_id": "line_b_shipping",
      "line_id": "B",
      "shift_id": "night",
      "equipment_id": null,
      "equipment_fault": false,
      "episode": {
        "start_ts": 1785193500.0,
        "end_ts": 1785193560.0,
        "phase": "outcome",
        "preliminary_risk": "Yüksek",
        "participants": ["PRS-002", "PRS-003"],
        "summary_tr": "28 Temmuz gecesi B-Hattı sevkiyat alanında kask takmayan personel tespit edildi. Vardiya amiri uyardı ve tutanak tutuldu."
      }
    }
  ]
}
```

Her kayıt bir `Episode` gövdesi (`episode`) + makine okunur üst veri taşıyor.
`start_ts` damgaları `occurred_at` ile birebir uyumlu, faz değerleri İngilizce
ve 2026-08-12 olayı arıza defteriyle aynı `incident_id`'yi paylaşıyor.

### 7. `gozcu/fixtures/README.md`

Şunu açıkça yaz — bu dosya açık veri setinde yayınlanacak:

> Bu dizindeki veriler **yarışma demosu için uydurulmuştur.** Kurgusal bir
> savunma sanayi üretim tesisini tanımlar. Hiçbir gerçek kişiyi, ekipmanı veya
> olayı temsil etmez. Personel isimleri baş harflerdir ve rastgeledir.

Dosya ayrıca `IST-04`'ün kök neden zincirini tarih tarih tablolaştırıyor:
kapanış raporunun iddia ettiği şeyin nereden geldiği tek bakışta görünsün diye.

### 8. `gozcu/fixtures/loader.py`

`gozcu/fixtures/__init__.py` `FIXTURE_DIR`'i veriyor — fikstürleri okuyan hiçbir
modül (Görev 10'un araçları, Görev 12'nin raporu) dizini kendi başına tahmin
etmesin diye.

```python
"""Fikstür okuyucu ve olay arşivi tohumlayıcısı.

Burada iki iş var:

1. **Okuma yardımcıları.** `load_fixture()` dosyaları, `resolve_zone()` /
   `resolve_shift()` / `overdue_maintenance_months()` ise araçların ve
   raporun sorduğu türetilmiş bilgiyi verir. Bakımın kaç ay geciktiği
   hiçbir dosyada **yazmıyor** — tarihlerden hesaplanıyor. Elle yazılan bir
   sayı kendi tarihleriyle çelişebilir; hesaplanan sayı çelişemez.

2. **Arşiv tohumlama.** `load_history()` önceki olayları epizot olarak
   kaydeder ve gömer; operatör *"bu araçla ilgili daha önce bir olay olmuş
   muydu?"* diye sorduğunda cevabın geldiği yer burasıdır.

Bütün tarihler dosyalarda **sabit**: senaryo 15 Ağustos 2026'da geçiyor ve
hiçbir değer "bugün"den hesaplanmıyor. Aksi hâlde demo gerçek zaman
ilerledikçe kayar — dört ay gecikmiş bakım bir ay sonra beş ay gecikmiş olur.
"""

import json
from datetime import date

from gozcu.fixtures import FIXTURE_DIR
from gozcu.memory import embed_episode
from gozcu.models import Episode


def load_fixture(name: str) -> dict:
    """Adı verilen fixture dosyasını `gozcu/fixtures/` altından okur."""
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))


#: Senaryonun geçtiği gün. Tek kaynağı fikstür dosyası — kod kendi tarihini
#: uydurmaz ve `date.today()` çağrılmaz.
SCENARIO_DATE = date.fromisoformat(
    load_fixture("facility")["facility"]["scenario_date"])


def resolve_zone(name: str) -> dict | None:
    """Bir bölge adını, hat kodunu veya takma adı bölge kaydına çözer.

    Ajan bir yeri üç ayrı biçimde söyleyebiliyor — `"B-Hattı"`, `"B"`,
    `"B-Hattı sevkiyat alanı"` — ve üçü de gerçek bir bölgeye oturmalı;
    yoksa `dispatch_medical` ile `halt_production_line` serbest metne
    konuşur. Tanınmayan ad için `None` döner, istisna atmaz.
    """
    wanted = str(name).casefold().strip()
    for zone in load_fixture("facility")["zones"]:
        candidates = [zone["zone_id"], zone["name"], *zone["aliases"]]
        if any(wanted == c.casefold() for c in candidates):
            return zone
    return None


def resolve_shift(at_time: str, facility: dict | None = None) -> str | None:
    """`"03:12"` gibi bir saati vardiya kimliğine çözer; bilinmiyorsa `None`."""
    facility = facility or load_fixture("facility")
    for shift in facility["shifts"]:
        if shift["start"] <= at_time < shift["end"]:
            return shift["shift_id"]
    return None


def _months_between(earlier: date, later: date) -> int:
    """İki tarih arasındaki **tam** ay sayısı; geçmemişse negatif."""
    months = (later.year - earlier.year) * 12 + (later.month - earlier.month)
    return months - 1 if later.day < earlier.day else months


def overdue_maintenance_months(equipment_id: str,
                               as_of: date | None = None) -> int:
    """Bir ekipmanın bakımının kaç **tam ay** geciktiği.

    Her bakım türünün (`operation_type`) en son kaydı alınır, o kaydın
    `next_due` vadesi senaryo tarihiyle karşılaştırılır ve en kötü gecikme
    döner. Vadesi geçmemiş ekipman için `0`. Bilinmeyen ekipman da `0` —
    "gecikme yok" demek değil, "kaydı yok" demek; onu `not_found` ile
    ayırmak çağıranın işi.
    """
    record = load_fixture("equipment")["equipment"].get(equipment_id)
    if record is None:
        return 0
    as_of = as_of or SCENARIO_DATE
    latest: dict[str, dict] = {}
    for entry in record["maintenance_history"]:
        kind = entry["operation_type"]
        if kind not in latest or entry["date"] > latest[kind]["date"]:
            latest[kind] = entry
    overdue = [_months_between(date.fromisoformat(e["next_due"]), as_of)
               for e in latest.values()]
    return max([*overdue, 0])


def load_history(gw, store) -> int:
    """Önceki olayları arşive yükler ve gömer; **gerçekten gömülen** sayısı döner.

    Dönen sayı `store.embeddings()` ile birebir aynıdır. Epizot kaydedilmiş
    ama gömülememişse sayılmaz: gömme kademesi bozukken "3 olay yüklendi"
    demek, arama hiçbir şey bulamazken sistemin çalıştığını sanmak demektir.

    `embed_episode()` bir fikstür için `False` döndürdüğünde o olay
    **arşivde durur ama hafıza aramasında bulunamaz** — kademe düzelip
    yeniden gömülene kadar. Bu yüzden ikinci çağrı zararsız ve onarıcıdır:
    epizodu çoğaltmaz, yalnızca vektörü eksik olanları yeniden gömer.
    """
    payload = load_fixture("prior_incidents")
    archived = {e.summary_tr: e for e in store.episodes()}
    embedded = {episode_id for episode_id, _ in store.embeddings()}
    stored = 0
    for record in payload["incidents"]:
        fields = record["episode"]
        episode = archived.get(fields["summary_tr"])
        if episode is None:
            episode = Episode(**fields, state="closed")
            episode.id = store.create_episode(episode)
        elif episode.id in embedded:
            continue
        if embed_episode(gw, store, episode):
            stored += 1
        else:
            print(f"UYARI: fikstür gömülemedi — {episode.summary_tr}")
    return stored
```

### 9. Yeşil olduğunu gör

```bash
uv run pytest tests/test_fixtures.py -v
```
Beklenen: 11 passed

### 10. Commit

```bash
git add gozcu/fixtures tests/test_fixtures.py
git commit -m "feat: facility fixtures with a derivable maintenance chain"
```

## Doğrulama

```bash
uv run pytest tests/test_fixtures.py -v
```
Beklenen: **11 passed**

## Tamamlanma notları (gelecek görevleri bağlayan)

- **`FIXTURE_DIR` ve `SCENARIO_DATE` tek kaynaktır.** İlki
  `gozcu/fixtures/__init__.py`'de, ikincisi `gozcu/fixtures/loader.py`'de ve
  `facility.json`'dan okunuyor. Fikstür okuyan hiçbir modül kendi dizin yolunu
  kurmayacak, kendi tarihini uydurmayacak ve `date.today()` çağırmayacak —
  demo aylar sonra oynatıldığında da aynı sayıları vermeli.
- **`overdue_maintenance_months(equipment_id)` bir FONKSİYON, anahtar değil.**
  Her `operation_type` için son bakım kaydının `next_due` vadesi
  `SCENARIO_DATE` ile karşılaştırılıp en kötü gecikme dönüyor
  (`IST-04` → `4`, `IST-07` → `0`, bilinmeyen ekipman → `0`). Eski
  `overdue_maintenance_months` **anahtarı JSON'dan kalktı**: onu sözlükten
  okuyan kod `KeyError` alır. [Görev 10](10-saha-araclari.md)'un
  `query_equipment_history`'si fonksiyonu çağırmak zorunda.
- **Bölge kimlikleri: `line_b`, `line_b_shipping`, `line_c`,
  `line_c_assembly`, `warehouse`.** `resolve_zone()` Türkçe yazımları da kabul
  ediyor (`"B-Hattı"`, `"B"`, `"B-Hattı sevkiyat alanı"`), tanımadığı ad için
  **istisna atmaz, `None` döner**. Her bölge `medical_team` ve
  `medical_eta_minutes` taşıyor — `dispatch_medical` artık sabit `"Revir-2"`
  yazmak zorunda değil. `halt_production_line` içinse hat kimlikleri `"B"` ve
  `"C"`.
- **Personel kimlikleri `PRS-001`…`PRS-006`**, her biri `zone`, `zone_id`,
  `shift_id` ve `certifications` ile. Belgeler tek biçimli İngilizce
  (`forklift_licence`, `safety_officer`, `electrical`, `mechanical`,
  `manual_handling`) — yarısı Türkçe yarısı İngilizce bir liste üzerinde
  filtre yazılamaz.
- **Vardiyalar `night` / `day` / `evening`** ve `resolve_shift("03:12")`
  `"night"` dönüyor. Bu, `at_time` parametresinin ilk kez gerçekten bir
  karşılığı olması demek: Görev 10'un vardiya sorgusu artık saati yok sayıp
  bölgedeki herkesi dökmek zorunda değil.
- **`load_history` yalnızca GERÇEKTEN gömülen vektörleri sayıyor** ve
  `store.embeddings()` ile birebir aynı sayıyı döner. Gömme kademesi bozukken
  `0` döner — epizotlar arşivde durur ama aramada bulunmaz. **İkinci çağrı
  onarıcıdır:** epizodu çoğaltmadan, vektörü eksik olanları yeniden gömer.
- **`IST-04` zinciri kendi içinde tutarlı ve arşivdeki olay ile arıza kaydı
  TEK olaydır** (`OLY-2026-0812`, 2026-08-12). Kök neden artık **tek** ipliğe
  dayanıyor: **sertifikasyon hikâyesi kesildi**, operatör (`PRS-001`)
  ehliyetli. Yedek iplik olmadığı için zincirin iç tutarlılığı bir düzen
  meselesi değil, doğruluk meselesi — bakım tarihleri ya da arıza kaydı
  kayarsa rapor kendi verisinin yalanladığı bir kök neden iddia eder.
