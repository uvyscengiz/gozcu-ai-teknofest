"""Görev 17 — şartnamenin dört anahtarı ve donuk algı katmanının adaptörü.

Burada korunan tek cümle şu: `summary`, `events`, `risk`, `actions` **her
koşuda** üretilir. Genişletilmiş katmanların hepsi çökse bile jüri
notlandırılabilir bir sonuç görür; eklediğimiz her şey `detail` altında
onların YANINDA durur, yerine değil.
"""

import re

from gozcu.adapter import GATHERING_THRESHOLD, to_observation
from gozcu.agents.reporter import RootCauseReport
from gozcu.agents.router import mmss
from gozcu.models import (ActionRecord, Episode, EventBeat, ProposedAction,
                          RiskAssessment)
from gozcu.report import (HIGH_MOTION_ENERGY, PerceptionHealth,
                          build_output)
from gozcu.store import Store


class _FS:
    """`gozcu.signals.FrameSignals`'ın test ikizi — `gathering` alanı YOK."""

    def __init__(self, **kw):
        self.velocities = kw.get("velocities", {})
        self.vanished_tracks = kw.get("vanished_tracks", [])
        self.person_count = kw.get("person_count", 0)
        self.person_count_delta = kw.get("person_count_delta", 0)


class _Tracked:
    """`gozcu.track.TrackedObject`'in test ikizi."""

    def __init__(self, class_name="person", confidence=0.9,
                 bbox=(0, 0, 10, 10), track_id=1):
        self.class_name = class_name
        self.confidence = confidence
        self.bbox = bbox
        self.track_id = track_id


# -- dört anahtar -------------------------------------------------------------

def test_four_keys_exist_even_with_a_completely_empty_run():
    c = build_output(Store(":memory:"), summary="Kayda değer olay yok.")
    d = c.model_dump(exclude_none=True)
    assert {"summary", "events", "risk", "actions"} <= set(d)
    assert d["risk"] == "Düşük"


def test_events_use_mmss_and_come_from_episodes():
    store = Store(":memory:")
    store.create_episode(Episode(start_ts=15.0, phase="onset",
                                 summary_tr="İstif aracı devrildi",
                                 preliminary_risk="Yüksek"))
    c = build_output(store, summary="ö")
    assert c.events[0].time == "00:15"
    assert c.events[0].event == "İstif aracı devrildi"


def test_a_long_episode_summary_is_trimmed_to_the_event_limit():
    """`Episode.summary_tr` 600, `EventSummary.event` 200 — kesilmezse
    doğrulama patlar ve olay listesi tamamen kaybolur."""
    store = Store(":memory:")
    store.create_episode(Episode(start_ts=0.0, phase="onset",
                                 summary_tr="a" * 600,
                                 preliminary_risk="Orta"))
    assert len(build_output(store, summary="ö").events[0].event) == 200


def test_overall_risk_is_the_highest_assessed_level():
    store = Store(":memory:")
    for level in ("Düşük", "Kritik", "Orta"):
        store.save_risk(RiskAssessment(episode_id=1, level=level,
                                       rationale_tr="g", preventable=True))
    assert build_output(store, summary="ö").risk == "Kritik"


def test_risk_falls_back_to_episode_preliminary_when_no_assessment_exists():
    store = Store(":memory:")
    store.create_episode(Episode(start_ts=0.0, phase="development",
                                 summary_tr="x", preliminary_risk="Yüksek"))
    assert build_output(store, summary="ö").risk == "Yüksek"


# -- aksiyonlar ---------------------------------------------------------------

def test_actions_are_rendered_from_tool_backed_candidates_only():
    """Süzgeç silinirse uydurma araç adı taşıyan öneri de jüriye giden
    listeye düşer — o yüzden aday listesi karışık.

    İnsanın okuduğu liste ile makinenin aksiyon defteri ayrışamaz: sistemin
    çalıştıramayacağı bir öneri sadece bir cümledir.
    """
    store = Store(":memory:")
    store.save_risk(RiskAssessment(
        episode_id=1, level="Kritik", rationale_tr="g", preventable=True,
        proposed_actions=[
            ProposedAction(description_tr="Sağlık ekibini çağır",
                           tool_name="dispatch_medical"),
            ProposedAction(description_tr="Helikopter gönder",
                           tool_name="send_helicopter")]))
    assert build_output(store, summary="ö").actions == ["Sağlık ekibini çağır"]


def test_duplicate_actions_are_not_repeated():
    store = Store(":memory:")
    for _ in range(3):
        store.save_risk(RiskAssessment(
            episode_id=1, level="Orta", rationale_tr="g", preventable=True,
            proposed_actions=[
                ProposedAction(description_tr="Alanı güvenlik altına al",
                               tool_name="site_alarm")]))
    assert build_output(store, summary="ö").actions == [
        "Alanı güvenlik altına al"]


# -- detail -------------------------------------------------------------------

def test_detail_block_is_attached_but_never_replaces_the_four_keys():
    store = Store(":memory:")
    store.save_action(ActionRecord(ts=1.0, tool_name="site_alarm",
                                   params={}, result={}, actor="agent",
                                   approval="not_required"))
    c = build_output(store, summary="ö")
    assert c.detail is not None and len(c.detail.action_ledger) == 1
    assert c.summary == "ö"


def test_the_root_cause_report_is_stored_as_a_plain_dict():
    """`Detail.root_cause_report` `dict | None`; model nesnesi oraya girmez."""
    report = RootCauseReport(what_happened="Yük düştü.",
                             probable_root_cause="Olası fren arızası.",
                             confidence_limits="Kamera sesi duymuyor.")
    c = build_output(Store(":memory:"), summary="ö", root_cause=report)
    assert isinstance(c.detail.root_cause_report, dict)
    assert c.detail.root_cause_report["what_happened"] == "Yük düştü."


# -- körlük ile sessizlik ayrımı ---------------------------------------------
#
# `gozcu.motion` "veri yok" (`None`) ile "sıfır" arasındaki farkı zaten
# tutuyordu; teslim katmanı onu düşürüp "hiçbir şey olmadı" diye iddia
# ediyordu. Ölçülen arıza: raf çökmesi klibinde altı kutunun altısı da
# düşürülmüşken çıktı "Kayda değer olay tespit edilmedi." dedi.

QUIET = "Kayda değer olay tespit edilmedi."


def test_a_quiet_run_keeps_the_no_incident_summary():
    """Tespit üretilmiş ve hiçbiri kayda değer çıkmamışsa cümle dürüst."""
    health = PerceptionHealth(detections=19, frames=77,
                              peak_motion_energy=12.9)
    assert health.blind is False
    assert build_output(Store(":memory:"), summary=QUIET,
                        perception=health).summary == QUIET


def test_a_run_without_a_single_detection_reports_blindness_not_absence():
    health = PerceptionHealth(detections=0, frames=23,
                              peak_motion_energy=9.4)
    assert health.blind is True
    summary = build_output(Store(":memory:"), summary=QUIET,
                           perception=health).summary
    assert summary != QUIET
    assert "güvenilir tespit üretemedi" in summary
    assert "23 karenin hiçbirinde" in summary


def test_high_motion_with_nothing_confirmed_also_counts_as_blind():
    """Kareler değişiyor ama hiçbir epizot doğrulanmadı — bu boşluk bir
    "olay yok" hükmüne çevrilemez."""
    health = PerceptionHealth(detections=4, frames=12,
                              peak_motion_energy=HIGH_MOTION_ENERGY + 1)
    assert health.blind is True
    summary = build_output(Store(":memory:"), summary=QUIET,
                           perception=health).summary
    assert "belirgin hareket var" in summary


def test_ordinary_site_motion_does_not_make_a_run_blind():
    """Eşik sıradan saha hareketinin (ölçüldü: 9,4 ve 12,9) üstünde."""
    assert PerceptionHealth(detections=6, frames=23,
                            peak_motion_energy=12.9).blind is False


def test_missing_motion_evidence_is_not_read_as_zero_motion():
    """`peak_motion_energy=None` "kanıt yok" demek; tek başına körlük
    ilan etmiyor, tespit sayısı karar veriyor."""
    assert PerceptionHealth(detections=3, frames=5,
                            peak_motion_energy=None).blind is False
    assert PerceptionHealth(detections=0, frames=5,
                            peak_motion_energy=None).blind is True


def test_blindness_never_overrides_the_summary_of_a_run_with_episodes():
    """Epizot varsa özet kök neden raporundan gelir; körlük dalı susar."""
    store = Store(":memory:")
    store.create_episode(Episode(start_ts=0.0, phase="onset",
                                 summary_tr="İstif aracı devrildi",
                                 preliminary_risk="Yüksek"))
    output = build_output(store, summary="Yük düştü.",
                          perception=PerceptionHealth(detections=0, frames=9))
    assert output.summary == "Yük düştü."


def test_blindness_is_a_confession_not_an_alarm():
    """Kör koşu riski yükseltmiyor, aksiyon uydurmuyor — ama dört anahtar
    her iki dalda da yerinde."""
    for health in (PerceptionHealth(detections=0, frames=23),
                   PerceptionHealth(detections=9, frames=23,
                                    peak_motion_energy=1.0)):
        output = build_output(Store(":memory:"), summary=QUIET,
                              perception=health)
        assert {"summary", "events", "risk", "actions"} <= set(
            output.model_dump())
        assert output.risk == "Düşük"
        assert output.events == [] and output.actions == []


def test_the_summary_is_untouched_when_no_perception_record_is_given():
    """`perception` verilmeyen çağrılar eski davranışta kalıyor."""
    assert build_output(Store(":memory:"),
                        summary=QUIET).summary == QUIET


# -- adaptör ------------------------------------------------------------------

def test_adapter_derives_gathering_from_person_count():
    g = to_observation(1.0, [], _FS(person_count=GATHERING_THRESHOLD))
    assert g.signals.gathering is True
    assert to_observation(
        1.0, [], _FS(person_count=GATHERING_THRESHOLD - 1)
    ).signals.gathering is False


def test_adapter_keeps_the_person_count_delta():
    g = to_observation(1.0, [], _FS(person_count=4, person_count_delta=2))
    assert g.signals.person_count_delta == 2


def test_adapter_maps_velocities_and_vanished_tracks():
    g = to_observation(2.0, [], _FS(velocities={7: 3.1}, vanished_tracks=[9]))
    assert g.signals.velocities == {7: 3.1}
    assert g.signals.vanished_tracks == [9]
    assert g.ts == 2.0


def test_adapter_carries_the_track_id_into_the_detection():
    """Takip kimliği düşerse yönlendiricinin hız satırları kimsenin olmayan
    hızları gösterir."""
    g = to_observation(3.0, [_Tracked(track_id=7, bbox=(1, 2, 3, 4))], _FS())
    assert g.detections[0].track_id == 7
    assert g.detections[0].label == "person"
    assert g.detections[0].box == (1.0, 2.0, 3.0, 4.0)


# -- olaylar gerçekleştikleri anda damgalanıyor --------------------------------
#
# Eskiden epizot başına TEK olay üretiliyordu ve damgası pencerenin başlangıcı
# oluyordu: 10 saniyelik bir pencerede yaşanan darbe, devrilme ve toz üçü de
# aynı `00:10` ile teslim ediliyordu. Şartnamenin kendi örneği de birden çok
# ana işaret ediyor ("00:15 istif aracı devrildi", "00:20 yerde hareketsiz
# kişi").

def _with_beats(store, beats, start_ts=10.0, summary_tr="raf çökmesi"):
    return store.create_episode(Episode(
        start_ts=start_ts, phase="onset", summary_tr=summary_tr,
        preliminary_risk="Yüksek",
        beats=[EventBeat(ts=ts, text=text) for ts, text in beats]))


def test_one_event_is_emitted_per_beat():
    store = Store(":memory:")
    _with_beats(store, [(13.0, "Rafın altı çökmeye başladı."),
                        (14.0, "Toz bulutu yayıldı.")])
    events = build_output(store, summary="ö").events
    assert [(e.time, e.event) for e in events] == [
        ("00:13", "Rafın altı çökmeye başladı."),
        ("00:14", "Toz bulutu yayıldı.")]


def test_beat_events_are_chronological_even_if_stored_out_of_order():
    store = Store(":memory:")
    _with_beats(store, [(18.0, "sonra"), (12.0, "önce")])
    assert [e.time for e in build_output(store, summary="ö").events] == [
        "00:12", "00:18"]


def test_a_beat_event_is_stamped_by_mmss_not_by_model_text():
    """Damga her zaman `mmss()` ile kuruluyor — modelin yazdığı bir metin
    `EventSummary.time` deseninden geçemez."""
    store = Store(":memory:")
    _with_beats(store, [(192.0, "istif aracı devrildi")])
    event = build_output(store, summary="ö").events[0]
    assert event.time == mmss(192.0) == "03:12"
    assert re.fullmatch(r"\d{2}:\d{2}", event.time)


def test_an_episode_without_beats_still_yields_its_single_event():
    """Bugünkü davranış gerilemiyor: an listesi boşsa epizot özeti tek olay
    olarak, pencere başlangıcıyla damgalanıyor."""
    store = Store(":memory:")
    store.create_episode(Episode(start_ts=15.0, phase="onset",
                                 summary_tr="İstif aracı devrildi",
                                 preliminary_risk="Yüksek"))
    events = build_output(store, summary="ö").events
    assert [(e.time, e.event) for e in events] == [
        ("00:15", "İstif aracı devrildi")]


def test_a_beatless_fallback_episode_yields_a_neutral_event():
    """Yedek özetli, anları olmayan bir epizot `events[]`'e arıza metnini
    OLDUĞU GİBİ taşırsa jüriye giden anahtar bir olay tarifi gibi okunur.
    Arıza dürüstçe söylenir ("tarifi üretilemedi") ama uydurma da yok."""
    from gozcu.report import FALLBACK_EVENT

    store = Store(":memory:")
    store.create_episode(Episode(
        start_ts=15.0, phase="onset",
        summary_tr="Sentez üretilemedi; ham gözlemler kayıtlı.",
        preliminary_risk="Yüksek", summary_source="fallback"))
    events = build_output(store, summary="ö").events
    assert events[0].event == FALLBACK_EVENT
    assert "Sentez üretilemedi" not in events[0].event


def test_episodes_with_and_without_beats_live_in_the_same_list():
    store = Store(":memory:")
    _with_beats(store, [(13.0, "çökme")], start_ts=10.0)
    store.create_episode(Episode(start_ts=30.0, phase="outcome",
                                 summary_tr="yerde hareketsiz kişi",
                                 preliminary_risk="Kritik"))
    assert [e.time for e in build_output(store, summary="ö").events] == [
        "00:13", "00:30"]


def test_a_long_beat_text_is_trimmed_to_the_event_limit():
    store = Store(":memory:")
    _with_beats(store, [(13.0, "a" * 160)])
    assert len(build_output(store, summary="ö").events[0].event) <= 200
