"""Görev 05 — olay anında karar döngüsü.

Bu dosyanın koruduğu iki şey var: kararın videonun *içinde* verilmesi
(`run` bir generator ve yükseltmede duruyor) ve aynı anda **tek bir açık
epizot** değişmezi — depo bunu korumuyor, döngü koruyor.
"""

from gozcu.loop import DecisionLoop, passes_floor, windows
from gozcu.models import (Detection, Episode, Interpretation, LoopEvent,
                          Observation, RouterDecision, Signals)
from gozcu.store import Store


def _observation(ts, person_count=0, velocities=None):
    return Observation(
        ts=ts,
        detections=[Detection(label="person", confidence=0.9,
                              box=(0, 0, 1, 1), track_id=1)] * person_count,
        signals=Signals(person_count=person_count,
                        velocities=velocities or {}))


def _episode(ts=0.0):
    return Episode(start_ts=ts, phase="development", summary_tr="x",
                   preliminary_risk="Kritik")


def _interpretation(ts=0.0):
    """Gerçek `interpret` bunu ya da `None` döndürür — çıplak `object()` değil.

    Sahte iş arkadaşının şekli gerçeğiyle aynı olmazsa test yalancı yeşile
    döner: `synthesize` alan okur, `object()` alan okumaz.
    """
    return Interpretation(observation_ts=ts, description="forklift geçiyor",
                          model="test-vlm")


def _loop(store, route, synthesize=None, interpret=None, is_degraded=None):
    return DecisionLoop(
        store,
        route=route,
        interpret=interpret or (lambda window: None),
        synthesize=synthesize or (lambda window, interpretation, decision:
                                  _episode(window[0].ts)),
        is_degraded=is_degraded or (lambda: False))


def _store_backed_synthesize(store):
    """Görev 07'nin sentezleyicisinin depoya yazan davranışını taklit eder.

    Gerçek sentezleyici de `open_episode` kararında koşulsuz yeni epizot açar;
    kaynaşma yalnızca karar `update_episode` olduğunda gerçekleşir. Tek açık
    epizot değişmezinin döngüde yaşamasının sebebi tam olarak bu.
    """
    def synthesize(window, interpretation, decision):
        open_ep = store.open_episode() if decision != "open_episode" else None
        if decision == "close_episode":
            if open_ep is None:
                return None
            store.update_episode(open_ep.id, end_ts=window[-1].ts,
                                 state="closed")
            return open_ep
        if open_ep is not None:
            store.update_episode(open_ep.id, end_ts=window[-1].ts)
            return open_ep
        episode = _episode(window[0].ts)
        episode.id = store.create_episode(episode)
        return episode
    return synthesize


def test_windows_group_by_ten_seconds():
    observations = [_observation(float(t)) for t in range(25)]
    assert [len(w) for w in windows(observations)] == [10, 10, 5]


def test_floor_blocks_a_completely_still_window():
    assert passes_floor([_observation(float(t)) for t in range(10)]) is False
    assert passes_floor(
        [_observation(float(t), person_count=2) for t in range(10)]) is True


def test_router_is_not_called_for_windows_below_the_floor():
    calls = []
    loop = _loop(Store(":memory:"),
                 lambda window: calls.append(window) or RouterDecision(
                     decision="ignore", rationale="x", confidence=0.5))
    list(loop.run([_observation(float(t)) for t in range(20)]))
    assert calls == []


def test_escalation_yields_an_episode_before_the_video_ends():
    """§3a'nın bekçisi. Biri döngüyü 'topla-sonra-karar-ver' haline
    çevirirse bu test kırmızıya döner."""
    observations = [_observation(float(t), person_count=2) for t in range(30)]

    def route(window):
        return RouterDecision(
            decision="escalate" if window[0].ts < 10 else "ignore",
            rationale="x", confidence=0.9)

    loop = _loop(Store(":memory:"), route)
    first = next(loop.run(observations))
    assert isinstance(first, LoopEvent)
    assert isinstance(first.episode, Episode)
    assert first.episode.start_ts < observations[-1].ts


def test_escalation_synthesises_an_episode_first():
    """Yükseltilecek bir epizot yoksa risk analizi tutunacak bir şey bulamaz."""
    calls = []
    loop = _loop(Store(":memory:"),
                 lambda window: RouterDecision(decision="escalate",
                                               rationale="x", confidence=0.9),
                 synthesize=lambda window, interpretation, decision:
                     calls.append(decision) or _episode(window[0].ts))
    next(loop.run([_observation(float(t), person_count=2) for t in range(10)]))
    assert calls == ["open_episode"]


def test_the_decision_is_passed_through_to_the_synthesiser():
    decisions = []
    sequence = iter(["open_episode", "update_episode", "close_episode"])
    loop = _loop(Store(":memory:"),
                 lambda window: RouterDecision(decision=next(sequence),
                                               rationale="x", confidence=0.9),
                 synthesize=lambda window, interpretation, decision:
                     decisions.append(decision) or _episode(window[0].ts))
    list(loop.run([_observation(float(t), person_count=1) for t in range(30)]))
    assert decisions == ["open_episode", "update_episode", "close_episode"]


def test_every_routing_decision_is_written_to_the_handoff_ledger():
    store = Store(":memory:")
    loop = _loop(store, lambda window: RouterDecision(
        decision="ignore", rationale="sakin", confidence=0.8))
    list(loop.run([_observation(float(t), person_count=1) for t in range(20)]))
    assert len(store.handoffs()) == 2
    assert store.handoffs()[0].source_agent == "router"


def test_ledger_timestamps_are_video_relative_not_wall_clock():
    store = Store(":memory:")
    loop = _loop(store, lambda window: RouterDecision(
        decision="ignore", rationale="x", confidence=0.8))
    list(loop.run([_observation(float(t), person_count=1) for t in range(20)]))
    assert [handoff.ts for handoff in store.handoffs()] == [0.0, 10.0]


# --- Tek açık epizot değişmezi ------------------------------------------

def test_two_escalations_produce_exactly_one_open_episode():
    """00:00'da açılan epizot 00:10'da rakip bir epizota bölünemez.

    Bölünürse şartnamenin `events[]` listesi aynı forklifti iki kez sayar ve
    ilk epizot sonsuza dek açık kalır."""
    store = Store(":memory:")
    loop = _loop(store, lambda window: RouterDecision(
        decision="escalate", rationale="x", confidence=0.9),
        synthesize=_store_backed_synthesize(store))
    events = list(loop.run(
        [_observation(float(t), person_count=2) for t in range(20)]))
    assert len(events) == 2
    assert len(store.episodes()) == 1
    assert store.open_episode() is not None


def test_open_episode_decision_merges_while_an_episode_is_open():
    store = Store(":memory:")
    decisions = []
    synthesize = _store_backed_synthesize(store)
    loop = _loop(store, lambda window: RouterDecision(
        decision="open_episode", rationale="x", confidence=0.9),
        synthesize=lambda window, interpretation, decision:
            decisions.append(decision) or synthesize(window, interpretation,
                                                     decision))
    list(loop.run([_observation(float(t), person_count=1) for t in range(30)]))
    assert decisions == ["open_episode", "update_episode", "update_episode"]
    assert len(store.episodes()) == 1


def test_open_episode_after_a_close_opens_a_new_episode():
    store = Store(":memory:")
    decisions = []
    sequence = iter(["open_episode", "close_episode", "open_episode"])
    synthesize = _store_backed_synthesize(store)
    loop = _loop(store, lambda window: RouterDecision(
        decision=next(sequence), rationale="x", confidence=0.9),
        synthesize=lambda window, interpretation, decision:
            decisions.append(decision) or synthesize(window, interpretation,
                                                     decision))
    list(loop.run([_observation(float(t), person_count=1) for t in range(30)]))
    assert decisions == ["open_episode", "close_episode", "open_episode"]
    assert len(store.episodes()) == 2
    assert store.open_episode().start_ts == 20.0


# --- Canlı yükseltme mi, geç telafi mi ----------------------------------

def test_windows_skipped_while_degraded_are_deferred_and_replayed():
    """Beat 6: bağlantı kesikken atlanan pencereler kaybolmuyor, dönünce
    yeniden işleniyor."""
    down = {"vlm": True}
    loop = DecisionLoop(
        Store(":memory:"),
        route=lambda window: RouterDecision(decision="inspect", rationale="x",
                                            confidence=0.9),
        interpret=lambda window: (None if down["vlm"]
                                  else _interpretation(window[0].ts)),
        synthesize=lambda window, interpretation, decision:
            _episode(window[0].ts),
        is_degraded=lambda: down["vlm"])

    list(loop.run([_observation(float(t), person_count=1) for t in range(20)]))
    assert len(loop.deferred) == 2

    down["vlm"] = False
    replayed = list(loop.catch_up())
    assert len(replayed) == 2 and loop.deferred == []


def test_catch_up_is_a_no_op_while_still_degraded():
    loop = DecisionLoop(
        Store(":memory:"),
        route=lambda window: RouterDecision(decision="inspect", rationale="x",
                                            confidence=0.9),
        interpret=lambda window: None,
        synthesize=lambda window, interpretation, decision:
            _episode(window[0].ts),
        is_degraded=lambda: True)
    list(loop.run([_observation(float(t), person_count=1) for t in range(10)]))
    assert list(loop.catch_up()) == [] and len(loop.deferred) == 1


def test_live_escalations_are_not_marked_late():
    loop = _loop(Store(":memory:"), lambda window: RouterDecision(
        decision="escalate", rationale="x", confidence=0.9))
    events = list(loop.run(
        [_observation(float(t), person_count=2) for t in range(10)]))
    assert [event.late for event in events] == [False]


def test_backfilled_episodes_are_marked_late():
    """Kesinti sonrası kurtarılan epizot operatöre canlı kriz gibi
    duyurulmamalı — duyuruluyor ama `late` damgasıyla."""
    down = {"vlm": True}
    store = Store(":memory:")
    loop = DecisionLoop(
        store,
        route=lambda window: RouterDecision(
            decision="escalate" if window[0].ts >= 10 else "inspect",
            rationale="x", confidence=0.9),
        interpret=lambda window: (None if down["vlm"]
                                  else _interpretation(window[0].ts)),
        synthesize=_store_backed_synthesize(store),
        is_degraded=lambda: down["vlm"])

    live = list(loop.run(
        [_observation(float(t), person_count=1) for t in range(20)]))
    assert [event.late for event in live] == [False]
    assert len(loop.deferred) == 2

    down["vlm"] = False
    replayed = list(loop.catch_up())
    assert replayed and all(event.late is True for event in replayed)


# --- Erteleme yalnızca kesintide ----------------------------------------

def test_a_failed_parse_is_not_deferred_while_the_vision_tier_is_healthy():
    """`interpret` bozuk JSON'da da `None` döndürüyor. Sağlıklı kademede
    bunu ertelemek pencereyi her `catch_up`'ta yeniden VLM'e sorar."""
    loop = DecisionLoop(
        Store(":memory:"),
        route=lambda window: RouterDecision(decision="inspect", rationale="x",
                                            confidence=0.9),
        interpret=lambda window: None,
        synthesize=lambda window, interpretation, decision:
            _episode(window[0].ts),
        is_degraded=lambda: False)
    list(loop.run([_observation(float(t), person_count=1) for t in range(20)]))
    assert loop.deferred == []


def test_close_episode_windows_are_never_deferred():
    """`close_episode` bilerek hiç yorumlanmıyor; `None` yorumu bir kesinti
    kanıtı değil."""
    store = Store(":memory:")
    loop = DecisionLoop(
        store,
        route=lambda window: RouterDecision(decision="close_episode",
                                            rationale="x", confidence=0.9),
        interpret=lambda window: _interpretation(window[0].ts),
        synthesize=_store_backed_synthesize(store),
        is_degraded=lambda: True)
    list(loop.run([_observation(float(t), person_count=1) for t in range(20)]))
    assert loop.deferred == []
