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
    for target in ("interpreter", "anomaly_analyst", "risk_analyst"):
        s.save_handoff(Handoff(ts=1.0, source_agent="orchestrator",
                               target_agent=target, reason="n", confidence=0.9,
                               payload_ref="r"))
    assert [h.target_agent for h in s.handoffs()] == [
        "interpreter", "anomaly_analyst", "risk_analyst"]


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
                    ts=1.0, source_agent="orchestrator", target_agent=agent,
                    reason="n", confidence=0.9, payload_ref="r")))
        except Exception as error:      # noqa: BLE001 — teste taşınacak
            errors.append(repr(error))

    threads = [threading.Thread(target=write, args=(a,))
               for a in ("interpreter", "anomaly_analyst")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(ids) == 400
    assert len(set(ids)) == 400, "aynı satır kimliği iki kez dağıtıldı"
    assert len(s.handoffs()) == 400


def test_the_journal_orders_writes_across_tables():
    """Defterin bütün işi bu: farklı tablolara yazılmış satırları GERÇEK
    yazılma sırasında dizmek. Aynı `ts`, ayrı tablo, ayrı kimlik uzayı."""
    s = Store(":memory:")
    s.save_handoff(Handoff(ts=5.0, source_agent="orchestrator",
                           target_agent="interpreter", reason="n",
                           confidence=0.9, payload_ref="r"))
    eid = s.create_episode(Episode(start_ts=5.0, phase="onset", summary_tr="a",
                                   preliminary_risk="Orta"))
    s.save_action(ActionRecord(ts=5.0, tool_name="notify_supervisor",
                               actor="agent", approval="not_required"))
    assert [(e.source, e.kind) for e in s.journal()] == [
        ("handoff", "create"), ("episode", "create"), ("action", "create")]
    seqs = [e.seq for e in s.journal()]
    assert seqs == sorted(seqs)
    assert s.journal()[1].row_id == eid


def test_observations_are_not_journalled():
    """3 fps'te on saniyelik bir pencere ~30 gözlem. Defterlenirlerse besleme
    ayrıntılı kayda döner — ve gözlem bir ajan sınırını geçmiyor."""
    s = Store(":memory:")
    s.save_observation(Observation(ts=1.0))
    s.save_observation(Observation(ts=2.0))
    assert s.observations() != []
    assert s.journal() == []


def test_a_mutated_episode_keeps_the_summary_it_had_at_the_time():
    """Anlık görüntünün bütün sebebi: sentezleyici epizoda kaynaşıyor ve
    `summary_tr` değişiyor. Defter satırını canlı satıra çözmek, koşunun
    başındaki girdiye epizodun SONUNDAKİ özetini bastırırdı."""
    s = Store(":memory:")
    eid = s.create_episode(Episode(start_ts=1.0, phase="onset",
                                   summary_tr="ilk hâli",
                                   preliminary_risk="Düşük"))
    s.update_episode(eid, summary_tr="sonraki hâli", preliminary_risk="Kritik")

    created, updated = s.journal()
    assert created.snapshot["summary_tr"] == "ilk hâli"
    assert created.snapshot["preliminary_risk"] == "Düşük"
    assert updated.kind == "update"
    assert updated.snapshot["summary_tr"] == "sonraki hâli"
    assert updated.snapshot["preliminary_risk"] == "Kritik"


def test_an_episode_update_records_who_asked_for_it():
    """`update_episode`'un iki çağıranı var ve ikisi AYRI şeyler yapıyor:
    sentezleyici kaynaştırıyor, süpervizör operatörün sözüyle özeti
    DÜZELTİYOR. Tek satıra düşerlerse insan müdahalesi model çıktısı gibi
    görünür — %20'lik otonomi kriteri tam olarak bunu soruyor."""
    s = Store(":memory:")
    eid = s.create_episode(Episode(start_ts=1.0, phase="onset", summary_tr="a",
                                   preliminary_risk="Orta"))
    s.update_episode(eid, summary_tr="kaynaştı")
    s.update_episode(eid, summary_tr="düzeltildi", origin="supervisor")

    origins = [e.snapshot["origin"] for e in s.journal()]
    assert origins == ["anomaly_analyst", "anomaly_analyst", "supervisor"]


def test_the_episode_snapshot_freezes_the_end_it_had_at_the_time():
    """`end_ts` sonraki her kaynaşmada ileri kayıyor; damga canlı satırdan
    okunursa erken bir girdi olayın SONUNDAKİ bitişini gösterir."""
    s = Store(":memory:")
    eid = s.create_episode(Episode(start_ts=1.0, end_ts=9.0, phase="onset",
                                   summary_tr="a", preliminary_risk="Orta"))
    s.update_episode(eid, end_ts=29.0)
    created, updated = s.journal()
    assert created.snapshot["end_ts"] == 9.0
    assert updated.snapshot["end_ts"] == 29.0


def test_an_approval_decision_is_its_own_journal_row():
    """Onay kararı AYRI bir girdi. Çağrının kendi satırını güncellemek onu
    beslemede yerinden oynatırdı; çağrı çağrıldığı anda kalmalı, karar
    verildiği anda görünmeli."""
    s = Store(":memory:")
    aid = s.save_action(ActionRecord(ts=3.0, tool_name="halt_production_line",
                                     actor="agent", approval="pending"))
    s.set_action_approval(aid, "approved")
    rows = s.journal()
    assert [r.kind for r in rows] == ["create", "approval"]
    assert rows[1].row_id == aid
    assert rows[1].snapshot == {"approval": "approved"}
    assert rows[0].snapshot == {"approval": "pending"}, (
        "çağrı satırı durumu canlı okursa geriye dönük 'onaylandı' görünür")
