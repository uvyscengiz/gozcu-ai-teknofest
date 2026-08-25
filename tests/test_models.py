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
