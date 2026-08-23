"""Tesis dünyası fikstürleri — Görev 09.

Bu testler `gozcu.tools`'a DOKUNMAZ. Araçlar Görev 10'un işi; buradaki
sözleşme sadece fikstür dosyaları ve yükleyicidir.
"""

import json
from datetime import date, datetime
from unittest.mock import Mock

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
        assert occurred.date() < SCENARIO_DATE
        assert incident["date"] == occurred.date().isoformat()


def test_the_archive_stores_video_seconds_not_epoch_timestamps():
    """`Episode.start_ts` **video saniyesi**; olayın takvim anı `occurred_at`
    ile `date` alanlarında yaşıyor.

    Bu sütun bir zamanlar arşivde epoch saniyesi taşıyordu: `mmss()` onu
    `99:59`'a yapıştırıyor, rapor ve konsol da makul görünen yanlış bir saat
    basıyordu. Süre korunuyor — kaybolan tek şey, o sütunda hiç işi olmayan
    takvim bilgisi.
    """
    for incident in load_fixture("prior_incidents")["incidents"]:
        episode = incident["episode"]
        assert episode["start_ts"] == 0.0
        assert 0.0 < episode["end_ts"] < 60 * 60, "süre video ölçeğinde değil"


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
