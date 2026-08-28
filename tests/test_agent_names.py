"""Ajan adları mimari dokümanla eşit olmalı (spec §4)."""
import pytest
from pydantic import ValidationError

from gozcu.core.models import Handoff


def _handoff(source: str, target: str) -> Handoff:
    return Handoff(ts=1.0, source_agent=source, target_agent=target,
                   reason="test", confidence=0.5, payload_ref="x:1")


def test_new_names_accepted():
    assert _handoff("orchestrator", "interpreter").source_agent == "orchestrator"
    assert _handoff("anomaly_analyst", "risk_analyst").source_agent == "anomaly_analyst"


@pytest.mark.parametrize("stale", ["router", "synthesizer"])
def test_stale_names_rejected(stale):
    """Eski ad kabul edilirse iki sözlük yan yana yaşar ve ayrışır."""
    with pytest.raises(ValidationError):
        _handoff(stale, "supervisor")
