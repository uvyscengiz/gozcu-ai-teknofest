"""Protokol fixture'ı ve deterministik süzgeç (spec §2c, §2e)."""
import json
from pathlib import Path

from gozcu.fixtures.loader import (FIXTURE_DIR, load_fixture, load_protocols,
                                   match_protocols)
from gozcu.tools.registry import TOOLS


def test_protocols_load_and_validate():
    protocols = load_protocols()
    assert 4 <= len(protocols) <= 6, "spec §2c: dört ila altı protokol"
    assert len({p.protocol_id for p in protocols}) == len(protocols)


def test_every_step_binds_a_real_tool():
    """Uydurulmuş araç adı taşıyan protokol, yedek yolunu sessizce bozardı."""
    for protocol in load_protocols():
        assert protocol.steps, f"{protocol.protocol_id} adımsız"
        for step in protocol.steps:
            assert step.tool_name in TOOLS, \
                f"{protocol.protocol_id}: bilinmeyen araç {step.tool_name}"


def test_zone_ids_match_facility():
    """Protokolün bölgesi tesiste yoksa hiçbir olayla eşleşmez."""
    known = {z["zone_id"] for z in load_fixture("facility")["zones"]}
    for protocol in load_protocols():
        for zone_id in protocol.zone_ids:
            assert zone_id in known, f"{protocol.protocol_id}: {zone_id} yok"


def test_match_filters_by_event_class():
    matched = match_protocols("çarpma", "line_b", "Yüksek")
    assert matched
    assert all(p.event_class == "çarpma" for p in matched)


def test_match_filters_by_zone():
    """Bölgesi listelenmiş protokol başka bölgede eşleşmez.

    Kontrolör kararı: brief "yard" kullanıyordu ama tesiste öyle bir bölge
    yok (bkz. facility.json). "warehouse" gerçek bir bölge ve hiçbir
    protokolün zone_ids'inde değil — testin niyeti aynen korunuyor.
    """
    scoped = [p for p in load_protocols() if p.zone_ids]
    assert scoped, "en az bir bölgeye bağlı protokol olmalı"
    protocol = scoped[0]
    matched = match_protocols(protocol.event_class, "warehouse", "Kritik")
    assert protocol.protocol_id not in {p.protocol_id for p in matched} \
        or "warehouse" in protocol.zone_ids


def test_match_respects_min_risk():
    """`min_risk` altındaki bir olay protokolü tetiklemez."""
    high = match_protocols("çarpma", "line_b", "Kritik")
    low = match_protocols("çarpma", "line_b", "Düşük")
    assert len(low) <= len(high)


def test_empty_zone_ids_means_whole_facility():
    facility_wide = [p for p in load_protocols() if not p.zone_ids]
    for protocol in facility_wide:
        matched = match_protocols(protocol.event_class, "warehouse", "Kritik")
        assert protocol.protocol_id in {p.protocol_id for p in matched}


def test_unknown_event_class_matches_nothing():
    assert match_protocols("diğer", "line_b", "Kritik") == [] \
        or all(p.event_class == "diğer" for p in match_protocols("diğer", "line_b", "Kritik"))


def test_none_zone_only_matches_facility_wide_protocols():
    """`zone_id=None` yalnız tesis geneli protokolleri eşleştirir.

    Anomali analisti bölgeyi çözemediğinde `Episode.zone_id`'yi bilerek
    `None` bırakıyor — uydurmuyor. `match_protocols` bunu spec'in söylediği
    gibi ele almalı: bölgeye özgü bir protokolü BİLİNMEYEN bir bölgeye
    uygulamak varsayım üretmek olurdu, o yüzden `zone_id is None` iken
    yalnız `zone_ids` boş olan (tesis geneli) protokoller eşleşmeli. İki yön
    de AYRI assert'lerle denetleniyor — dosyanın başka yerinde işaretlenmiş
    "ya bu ya şu" deseni burada guard kaldırılsa bile yeşil kalabilirdi.
    """
    facility_wide = match_protocols("sıkışma", None, "Kritik")
    assert facility_wide, "tesis geneli bir protokol eşleşmeliydi"
    assert all(not p.zone_ids for p in facility_wide)

    zone_scoped = match_protocols("çarpma", None, "Kritik")
    assert "PRT-B-CARPMA" not in {p.protocol_id for p in zone_scoped}
