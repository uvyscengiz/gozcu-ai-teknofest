import pytest
from pydantic import ValidationError

from gozcu.models import (MAX_BEAT_TEXT, ClipBeat, Episode, EventBeat,
                          PipelineOutput, RouterDecision, Signals)


def test_router_decision_rejects_unknown_decision():
    with pytest.raises(ValidationError):
        RouterDecision(decision="belki", rationale="x", confidence=0.5)


def test_episode_requires_known_risk_level():
    with pytest.raises(ValidationError):
        Episode(start_ts=0.0, phase="onset", summary_tr="x",
                preliminary_risk="High", state="open")


def test_pipeline_output_has_the_four_sartname_keys():
    c = PipelineOutput(summary="özet", events=[], risk="Yüksek", actions=[])
    assert set(c.model_dump(exclude_none=True)) == {
        "summary", "events", "risk", "actions"}


def test_signals_defaults_are_empty_not_none():
    s = Signals()
    assert s.velocities == {} and s.vanished_tracks == [] and s.person_count == 0


def test_episode_beats_carry_absolute_video_time():
    e = Episode(start_ts=10.0, phase="onset", summary_tr="x",
                preliminary_risk="Orta",
                beats=[EventBeat(ts=13.0, text="raf çöktü")])
    assert e.beats[0].ts == 13.0


def test_episode_defaults_to_no_beats():
    e = Episode(start_ts=0.0, phase="onset", summary_tr="x",
                preliminary_risk="Orta")
    assert e.beats == [] and e.event_ts == 0.0


def test_episode_event_moment_is_the_first_beat():
    """`start_ts` pencerenin sınırı olarak kalıyor; olayın gerçekten
    başladığı an ayrı taşınıyor."""
    e = Episode(start_ts=10.0, phase="onset", summary_tr="x",
                preliminary_risk="Orta",
                beats=[EventBeat(ts=14.0, text="b"), EventBeat(ts=13.0, text="a")])
    assert e.start_ts == 10.0 and e.event_ts == 13.0


def test_beats_do_not_open_the_model_to_extra_fields():
    with pytest.raises(ValidationError):
        EventBeat(ts=1.0, text="x", note="fazladan")
    with pytest.raises(ValidationError):
        ClipBeat(offset_s=1.0, text="x", note="fazladan")


def test_a_clip_beat_offset_cannot_be_negative():
    with pytest.raises(ValidationError):
        ClipBeat(offset_s=-1.0, text="x")


def test_beat_text_has_an_upper_bound():
    with pytest.raises(ValidationError):
        EventBeat(ts=1.0, text="a" * (MAX_BEAT_TEXT + 1))


def test_an_episode_carries_its_provenance():
    from gozcu.models import Episode
    episode = Episode(start_ts=0.0, phase="onset", summary_tr="devrilme",
                      preliminary_risk="Yüksek", source="9f2a",
                      occurred_at="2026-08-12T23:41:00+03:00",
                      equipment_ids=["IST-04"],
                      actions_taken=[{"tool": "dispatch_medical",
                                      "eta_minutes": 4}])
    assert episode.source == "9f2a"
    assert episode.equipment_ids == ["IST-04"]
    assert episode.actions_taken[0]["eta_minutes"] == 4


def test_provenance_fields_default_to_empty_so_old_rows_still_load():
    """Alanlar eklemeden ÖNCE yazılmış satırlar okunmaya devam etmeli."""
    from gozcu.models import Episode
    episode = Episode(start_ts=0.0, phase="onset", summary_tr="x",
                      preliminary_risk="Düşük")
    assert episode.source is None and episode.occurred_at is None
    assert episode.equipment_ids == [] and episode.actions_taken == []


def test_occurred_at_is_a_separate_text_field_from_start_ts():
    """`start_ts` VİDEO saniyesi. Oraya epoch damgası yazılırsa `mmss()` onu
    `99:59`'a yapıştırır ve `kpi.epoch_scale_episodes` koşuyu düşürür —
    olayın takvim tarihi bu yüzden AYRI bir alanda yaşıyor."""
    from benchmark.kpi import EPOCH_THRESHOLD_S
    from gozcu.models import Episode
    episode = Episode(start_ts=12.5, phase="onset", summary_tr="x",
                      preliminary_risk="Düşük",
                      occurred_at="2026-08-12T23:41:00+03:00")
    assert episode.start_ts < EPOCH_THRESHOLD_S
    assert isinstance(episode.occurred_at, str)
