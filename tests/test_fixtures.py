"""Tesis dünyası fikstürleri — Görev 09.

Bu testler `gozcu.tools`'a DOKUNMAZ. Araçlar Görev 10'un işi; buradaki
sözleşme sadece fikstür dosyaları ve yükleyicidir.
"""

import json
from datetime import date, datetime
from unittest.mock import Mock

from gozcu.core.config import QDRANT_VECTOR_SIZE
from gozcu.fixtures import FIXTURE_DIR
from gozcu.fixtures.loader import (SCENARIO_DATE, load_fixture, load_history,
                                   overdue_maintenance_months, resolve_shift,
                                   resolve_zone)
from gozcu.core.store import Store


def _gateway(vector):
    """Sahte gömme kademesi.

    Vektör gerçek modelin boyutuna dolduruluyor: Görev 08 hafızayı Qdrant'a
    taşıdı ve koleksiyonun boyutu sabit — kısa bir vektör canlı kademede de
    reddedilirdi. Bozulmuş kademe `[]` döndürüyor ve öyle kalıyor.
    """
    padded = [0.0] * QDRANT_VECTOR_SIZE
    for index, value in enumerate(vector):
        padded[index] = value
    gw = Mock()
    gw.embed.return_value = padded if vector else []
    return gw


def _archive_size():
    """Arşivde kaç kayıt var — dosyadan sayılıyor, teste yazılmıyor."""
    return len(load_fixture("prior_incidents")["incidents"])


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
    # Arıza defterindeki her kayıt en geç arşivin son IST-04 olayı kadar eski.
    assert all(f["date"] <= "2026-08-12" for f in faults)


def test_no_fault_record_is_left_unlinked_to_the_archive():
    """İki fikstür dosyası birbirinden ayrışmasın: arıza defterinde duran
    ama arşivde karşılığı olmayan bir kayıt, precedent_line anlatısını yarım bırakır."""
    faults = load_fixture("equipment")["equipment"]["IST-04"]["fault_records"]
    archive = {i["incident_id"] for i in load_fixture("prior_incidents")["incidents"]}
    for fault in faults:
        assert fault["incident_id"], f"bağlanmamış arıza kaydı: {fault['date']}"
        assert fault["incident_id"] in archive


def test_the_archive_shows_ist04_as_a_repeated_brake_problem():
    """§7'nin precedent_line→araç zinciri buna dayanıyor: örüntü İKİ gerçek kayıttan
    doğuyor, uydurulmuş bir üçüncüden değil."""
    records = [i for i in load_fixture("prior_incidents")["incidents"]
               if i["equipment_id"] == "IST-04"]
    assert len(records) == 2
    assert all("fren" in i["episode"]["summary_tr"].lower() for i in records)


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

def _memory_client():
    """Süreç içi Qdrant — yükleyicinin yazdığı yer artık burası."""
    from qdrant_client import QdrantClient
    return QdrantClient(":memory:")


def _points(client):
    from gozcu.core.config import QDRANT_COLLECTION
    if not client.collection_exists(QDRANT_COLLECTION):
        return []
    return client.scroll(QDRANT_COLLECTION, limit=100, with_payload=True)[0]


def test_prior_incidents_are_embedded_and_never_touch_the_store():
    """Arşiv koşunun deposuna GİRMEZ: girdiği gün fikstürler `00:00`
    damgasıyla şartnamenin puanlanan `events[]` dizisine girer, `risk`
    yedeği kayar ve körlük itirafı ölür (spec §0)."""
    store, gw = Store(":memory:"), _gateway([0.1, 0.2, 0.3])
    client = _memory_client()
    n = load_history(gw, client)
    assert n == _archive_size()
    assert len(_points(client)) == n
    assert store.episodes() == [], "arşiv depoya girmemeli"


def test_every_archive_point_carries_its_provenance():
    """Eşleme yapılmazsa hepsi `source=None` ile gömülür ve kaynak
    tekilleştirmesi hepsini TEK kovaya koyar — precedent_line listesine yalnız
    biri girer ve beat 5 hatasız kesilir (spec §4)."""
    client = _memory_client()
    load_history(_gateway([0.1]), client)
    sources = {p.payload["source"] for p in _points(client)}
    # Sabit `3` DEĞİL: Görev 13 dördüncü kaydı ekledi ve sabit bir sayı o
    # gün sessizce kırılırdı. İddia "her kayıt KENDİ kaynağını taşıyor".
    assert len(sources) == _archive_size(), \
        f"her kayıt kendi kaynağını taşımalı: {sources}"
    assert all(k.startswith("arşiv:") for k in sources)
    assert all(p.payload["occurred_at"] for p in _points(client))


def test_a_prior_incident_involves_the_same_vehicle_as_the_demo():
    """ALAN KURALI: demo aracının arşivde bir emsali olmak zorunda — §7'nin
    bütün precedent_line→araç zinciri (IST-04 → query_equipment_history →
    gecikmiş bakım) buna dayanıyor."""
    client = _memory_client()
    load_history(_gateway([0.1]), client)
    assert any("IST-04" in p.payload["participants"]
               or "IST-04" in p.payload.get("equipment_ids", [])
               for p in _points(client))


def test_loading_twice_does_not_duplicate_the_archive():
    """Tekrarsızlık kontrolü SİLİNDİ — kararlı kimlik `upsert`'ü zaten
    idempotent yapıyor. Dönen sayı artık 0 değil arşivin boyu: yükleyici
    "kaç kayıt arşivde" diyor, "kaç YENİ kayıt" değil."""
    client = _memory_client()
    n = load_history(_gateway([0.1]), client)
    assert load_history(_gateway([0.1]), client) == n
    assert len(_points(client)) == n


def test_a_degraded_embedding_tier_is_reported_as_zero_not_as_success():
    """ALAN KURALI — sessiz düşüş yasak: kademe bozuksa yükleyici yalan
    söylemez. Sayı doğrudan rozete gidiyor (`session.archive_count`)."""
    client = _memory_client()
    assert load_history(_gateway([]), client) == 0
    assert _points(client) == []


def test_a_blind_run_still_confesses_even_though_the_archive_is_seeded():
    """Körlük itirafı `if not episodes and perception.blind`'a bağlı
    (`report.py`). Arşiv depoya girseydi fikstürler o koşulu ASLA tetiklemez
    ve kör bir koşu "kayda değer olay tespit edilmedi" derdi — bu bir gözlem
    iddiasıdır ve gözlem yapılmamıştır."""
    from gozcu.output.report import PerceptionHealth, build_output
    store, client = Store(":memory:"), _memory_client()
    load_history(_gateway([0.1]), client)

    blind_health = PerceptionHealth(frames=20, detections=0)
    assert blind_health.blind
    output = build_output(store, "kayda değer olay tespit edilmedi",
                          perception=blind_health)
    assert output.summary == blind_health.blind_summary()
    assert output.events == [], "arşiv hayalet satır üretmemeli"
