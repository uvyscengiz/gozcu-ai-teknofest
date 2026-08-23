import pytest
from pydantic import ValidationError

from gozcu.models import Episode, PipelineOutput, RouterDecision, Signals


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
