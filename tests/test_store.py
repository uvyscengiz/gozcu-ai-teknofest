import threading

from gozcu.models import (ActionRecord, Episode, EventBeat, Handoff,
                          Observation, Signals)
from gozcu.store import Store


def test_open_episode_returns_only_the_open_one():
    s = Store(":memory:")
    closed = s.create_episode(Episode(start_ts=0.0, phase="outcome", summary_tr="a",
                                      preliminary_risk="Düşük", state="closed"))
    open_ = s.create_episode(Episode(start_ts=10.0, phase="onset", summary_tr="b",
                                     preliminary_risk="Kritik", state="open"))
    assert s.open_episode().id == open_
    assert s.open_episode().id != closed


def test_update_episode_persists_and_roundtrips():
    s = Store(":memory:")
    eid = s.create_episode(Episode(start_ts=1.0, phase="onset", summary_tr="x",
                                   preliminary_risk="Orta"))
    s.update_episode(eid, state="closed", end_ts=9.0, phase="outcome")
    e = s.episodes()[0]
    assert (e.state, e.end_ts, e.phase) == ("closed", 9.0, "outcome")


def test_handoff_ledger_preserves_insertion_order():
    s = Store(":memory:")
    for target in ("interpreter", "synthesizer", "risk_analyst"):
        s.save_handoff(Handoff(ts=1.0, source_agent="router",
                               target_agent=target, reason="n", confidence=0.9,
                               payload_ref="r"))
    assert [h.target_agent for h in s.handoffs()] == [
        "interpreter", "synthesizer", "risk_analyst"]


def test_observation_roundtrips_nested_signals_with_int_keys():
    s = Store(":memory:")
    s.save_observation(Observation(ts=2.0, signals=Signals(person_count=3,
                                                           velocities={7: 1.5})))
    assert s.observations()[0].signals.velocities == {7: 1.5}


def test_action_approval_updates_in_place_without_a_new_row():
    s = Store(":memory:")
    aid = s.save_action(ActionRecord(ts=1.0, tool_name="halt_production_line",
                                     params={}, result={}, actor="agent",
                                     approval="pending"))
    s.set_action_approval(aid, "approved")
    assert len(s.actions()) == 1
    assert s.actions()[0].approval == "approved"


def test_embedding_roundtrips_and_replaces_by_episode_id():
    s = Store(":memory:")
    eid = s.create_episode(Episode(start_ts=1.0, phase="onset", summary_tr="x",
                                   preliminary_risk="Orta"))
    s.save_embedding(eid, [0.1, 0.2, 0.3])
    assert s.embeddings() == [(eid, [0.1, 0.2, 0.3])]
    s.save_embedding(eid, [0.9, 0.8])
    assert s.embeddings() == [(eid, [0.9, 0.8])]


def test_episode_beats_survive_the_payload_round_trip():
    """`Episode` `extra="forbid"`: iç içe an listesi JSON yükünde gidip
    aynen geri okunmalı — güncelleme de yükü yeniden doğruluyor."""
    s = Store(":memory:")
    eid = s.create_episode(Episode(start_ts=10.0, phase="onset", summary_tr="x",
                                   preliminary_risk="Orta",
                                   beats=[EventBeat(ts=13.0, text="raf çöktü")]))
    s.update_episode(eid, state="closed", end_ts=20.0)
    e = s.episodes()[0]
    assert [(b.ts, b.text) for b in e.beats] == [(13.0, "raf çöktü")]
    assert e.state == "closed"


def test_concurrent_writers_never_lose_or_duplicate_a_row():
    """İki iş parçacığı aynı bağlantıya yazıyor — konsolda GERÇEKTEN böyle.

    Boru hattı iş parçacığı `run_pipeline`'da yazarken Gradio olay iş
    parçacığı `nobetci.talk()` ve `set_action_approval` ile aynı depoya
    yazıyor (`console.py:953`, `973`, `988`). Kilitsiz hâlde sqlite3 hem
    `InterfaceError` atıyor hem aynı satır kimliğini iki kez veriyor.
    """
    s = Store(":memory:")
    errors, ids = [], []

    def write(agent):
        try:
            for _ in range(200):
                ids.append(s.save_handoff(Handoff(
                    ts=1.0, source_agent="router", target_agent=agent,
                    reason="n", confidence=0.9, payload_ref="r")))
        except Exception as error:      # noqa: BLE001 — teste taşınacak
            errors.append(repr(error))

    threads = [threading.Thread(target=write, args=(a,))
               for a in ("interpreter", "synthesizer")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(ids) == 400
    assert len(set(ids)) == 400, "aynı satır kimliği iki kez dağıtıldı"
    assert len(s.handoffs()) == 400
