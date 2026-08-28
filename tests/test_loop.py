"""Görev 05 — olay anında karar döngüsü.

Bu dosyanın koruduğu iki şey var: kararın videonun *içinde* verilmesi
(`run` bir generator ve yükseltmede duruyor) ve aynı anda **tek bir açık
epizot** değişmezi — depo bunu korumuyor, döngü koruyor.
"""

import math

import pytest

from gozcu.pipeline.loop import (FLOOR_VELOCITY, FORCED_REASON, FORCED_REASON_PREFIX,
                        FORCED_SAMPLE_EVERY, MAX_HANDOFF_REASON,
                        OPEN_EPISODE_FORCED_REASON, ROUTED_FORCED_REASON,
                        DecisionLoop, passes_floor, windows)
from gozcu.core.models import (Detection, Episode, Interpretation, LoopEvent,
                          Observation, RouterDecision, Signals)
from gozcu.core.store import Store


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


def _interpretation(ts=0.0, notable_event=None, severity="rutin"):
    """Gerçek `interpret` bunu ya da `None` döndürür — çıplak `object()` değil.

    Sahte iş arkadaşının şekli gerçeğiyle aynı olmazsa test yalancı yeşile
    döner: `synthesize` alan okur, `object()` alan okumaz.

    `severity` varsayılanı `"rutin"` — Görev 20 öncesi `notable_event=None`
    "kayda değer değil" demekti; epizot açılışının geçidi artık `severity`
    olduğu için varsayılan da aynı niyeti taşıyor. Bir çağıranın epizot
    AÇILMASINI beklediği yerde `severity="olay"` açıkça geçilir.
    """
    return Interpretation(observation_ts=ts, description="forklift geçiyor",
                          notable_event=notable_event, severity=severity,
                          model="test-vlm")


def _loop(store, route, synthesize=None, interpret=None, is_degraded=None,
          motion_for=None):
    return DecisionLoop(
        store,
        route=route,
        interpret=interpret or (lambda window: None),
        synthesize=synthesize or (lambda window, interpretation, decision:
                                  _episode(window[0].ts)),
        is_degraded=is_degraded or (lambda: False),
        motion_for=motion_for)


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


def test_the_floor_still_gates_on_velocity_at_the_new_unit():
    """`FLOOR_VELOCITY` artık kare-genişliği/saniye biriminde (26 Ağustos —
    eski piksel/saniye sahneye göre yalan söylüyordu, bkz. `gozcu.signals`).
    Davranış korunuyor: eşiğin altı geçmiyor, üstü geçiyor — kişi/kaybolan/
    toplanma sinyali hiç olmadan, salt hız üzerinden."""
    below = [_observation(float(t), velocities={1: FLOOR_VELOCITY / 2})
            for t in range(10)]
    above = [_observation(float(t), velocities={1: FLOOR_VELOCITY * 2})
            for t in range(10)]
    assert passes_floor(below) is False
    assert passes_floor(above) is True


def test_the_floor_still_keeps_most_windows_away_from_the_models():
    """Taban hâlâ maliyet filtresi. Zorunlu örnekleme onu iptal etmiyor,
    seyreltiyor: 19 durgun pencereden yalnız 4'ü modele gidiyor — ve o dördü
    yönlendiriciye DEĞİL, doğrudan görü kademesine gidiyor."""
    routed, seen = [], []
    loop = _loop(Store(":memory:"),
                 lambda window: routed.append(window) or RouterDecision(
                     decision="ignore", rationale="x", confidence=0.5),
                 interpret=lambda window: seen.append(window) or None)
    list(loop.run([_observation(float(t)) for t in range(190)]))
    assert len(seen) == 4
    assert routed == []


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
    assert store.handoffs()[0].source_agent == "orchestrator"


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
        # Bu test telafi replay'ini sınıyor, severity geçidini değil — o
        # yüzden yorum bir "olay" taşıyor: aksi hâlde epizot hiç açılmaz ve
        # `replayed` her zaman boş kalır.
        interpret=lambda window: (None if down["vlm"]
                                  else _interpretation(window[0].ts,
                                                       severity="olay")),
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


# --- Zorunlu periyodik örnekleme ----------------------------------------
#
# Canlı ölçüm (5 klipli benchmark, `status: degraded`, 0/5 ölçüldü) tabanın
# sıfır tespitte bütün boru hattını susturduğunu gösterdi: raf çökmesi klibinde
# 23 gözlem, hiç tespit yok, üç pencerenin üçü de tabandan geçemedi, `route()`
# hiç çağrılmadı ve şartnamenin dört anahtarı boş döndü.
#
# İlk onarım pencereyi yönlendiriciye gönderiyordu; canlı koşu (24 Ağustos,
# `forklift-compilation--N9bG-sOU6LE-k03`) o onarımın da yetmediğini ölçtü:
# 1 yönlendirici çağrısı, güven 0,90, 0 epizot. Sinyal özeti boşken
# yönlendiricinin okuyacağı hiçbir şey yok ve doğru cevabı "sakin" oluyor.
# Bu yüzden zorunlu pencere artık yönlendiriciyi ATLAYIP doğrudan görüye gider.


def test_a_run_where_every_window_fails_the_floor_reaches_the_vision_tier():
    """Taban *ne zaman soracağını* belirlemeliydi; sıfır tespitte sessizce
    *hiç sorma* diyor. Zorunlu örnekleme o sessizliği kırar — ve soruyu
    görebilen kademeye sorar.

    İlk pencere de soruluyor: arızayı ortaya çıkaran klip 22,9 saniye, yani
    yalnız üç pencere. Sayaç boş başlasa altıncı pencere hiç gelmez ve o klip
    aynen sessiz kalırdı."""
    routed, seen = [], []
    loop = _loop(Store(":memory:"),
                 lambda window: routed.append(window[0].ts) or RouterDecision(
                     decision="ignore", rationale="x", confidence=0.5),
                 interpret=lambda window: seen.append(window[0].ts) or None)
    # 19 pencerelik tamamen durgun bir koşu — tespit yok, hareket yok.
    list(loop.run([_observation(float(t)) for t in range(190)]))
    assert seen == [0.0, 60.0, 120.0, 180.0]
    assert routed == []             # boş bir özete sorulacak soru yok


def test_every_window_passing_the_floor_produces_no_forced_vision_calls():
    """Zorunlu örnekleme ek çağrı eklemiyor; yalnız boşluğu dolduruyor.

    Tabandan geçen pencere eski yolunda kalır: önce yönlendirici, görü
    kademesi ancak karar gerektiriyorsa."""
    routed, seen = [], []
    loop = _loop(Store(":memory:"),
                 lambda window: routed.append(window[0].ts) or RouterDecision(
                     decision="ignore", rationale="x", confidence=0.5),
                 interpret=lambda window: seen.append(window[0].ts) or None)
    list(loop.run([_observation(float(t), person_count=1)
                   for t in range(190)]))
    assert routed == [float(10 * i) for i in range(19)]
    assert seen == []


def test_the_forced_counter_resets_when_the_floor_passes():
    """Sayaç model HER çağrıldığında sıfırlanır — tabandan geçen pencereler de
    sayılır. Sıfırlanmazsa tabandan geçen bir pencerenin hemen ardından
    gereksiz bir zorunlu görü çağrısı gelir ve maliyet iddiası aşınır."""
    routed, seen = [], []

    def _busy(ts: float) -> bool:
        return 30.0 <= ts < 40.0        # yalnız 4. pencere tabandan geçer

    observations = [_observation(float(t),
                                 person_count=1 if _busy(float(t)) else 0)
                    for t in range(190)]
    loop = _loop(Store(":memory:"),
                 lambda window: routed.append(window[0].ts) or RouterDecision(
                     decision="ignore", rationale="x", confidence=0.5),
                 interpret=lambda window: seen.append(window[0].ts) or None)
    list(loop.run(observations))
    assert routed == [30.0]
    # 00:30 tabandan geçti ve sayacı sıfırladı; sıfırlanmasaydı sıradaki
    # zorunlu çağrı 01:30 yerine 01:10'da gelirdi.
    assert seen == [0.0, 90.0, 150.0]


def test_the_forced_handoff_names_the_interpreter_not_the_router():
    """Defter olanı yazmalı: zorunlu çağrı bir yönlendirici kararı değil.

    `[periyodik]` öneki duruyor — ölçüm (Görev 15) zorunlu işi tabandan geçmiş
    işten böyle ayırıyor — ama kaynak/hedef artık dürüst: algı katmanı
    doğrudan yorumlayıcıyı çağırıyor."""
    store = Store(":memory:")
    observations = [_observation(float(t),
                                 person_count=1 if float(t) < 10.0 else 0)
                    for t in range(70)]
    loop = _loop(store, lambda window: RouterDecision(
        decision="ignore", rationale="sakin", confidence=0.5))
    list(loop.run(observations))

    floor_passing, forced = store.handoffs()
    assert (floor_passing.source_agent, floor_passing.target_agent) == (
        "orchestrator", "perception")
    assert floor_passing.reason == "sakin"
    assert (forced.source_agent, forced.target_agent) == (
        "perception", "interpreter")
    assert forced.reason.startswith(FORCED_REASON_PREFIX)


def test_the_forced_reason_stays_within_the_handoff_limit():
    """`Handoff.reason` 200 karakterle sınırlı; taşan bir gerekçe doğrulamayı
    patlatır ve zorunlu çağrı bütün koşuyu düşürür."""
    store = Store(":memory:")
    loop = _loop(store, lambda window: RouterDecision(
        decision="ignore", rationale="x", confidence=0.5))
    list(loop.run([_observation(float(t)) for t in range(60)]))
    assert len(FORCED_REASON) <= MAX_HANDOFF_REASON
    assert store.handoffs()[0].reason == FORCED_REASON


def test_a_forced_window_with_a_notable_event_opens_an_episode():
    """Zorunlu pencere yalnız deftere not düşmek için gitmiyor: görü kademesi
    kayda değer bir şey gördüyse epizot açılır. Raf çökmesi klibinin
    şartnamenin dört anahtarına ulaşabildiği tek yol bu."""
    store = Store(":memory:")
    decisions = []
    synthesize = _store_backed_synthesize(store)
    loop = _loop(store, lambda window: RouterDecision(
        decision="ignore", rationale="x", confidence=0.5),
        interpret=lambda window: _interpretation(
            window[0].ts, notable_event="raf çöktü", severity="olay"),
        synthesize=lambda window, interpretation, decision:
            decisions.append(decision) or synthesize(window, interpretation,
                                                     decision))
    list(loop.run([_observation(float(t)) for t in range(130)]))
    # Üç zorunlu pencere: ilki epizodu açar, kalanı ona kaynaşır.
    assert decisions == ["open_episode", "update_episode", "update_episode"]
    assert len(store.episodes()) == 1


def test_a_forced_window_without_a_notable_event_opens_nothing():
    """Görü kademesi sıradan bir sahne gördüyse epizot uydurulmaz."""
    store = Store(":memory:")
    calls = []
    loop = _loop(store, lambda window: RouterDecision(
        decision="ignore", rationale="x", confidence=0.5),
        interpret=lambda window: _interpretation(window[0].ts,
                                                 severity="rutin"),
        synthesize=lambda window, interpretation, decision:
            calls.append(decision) or _episode(window[0].ts))
    list(loop.run([_observation(float(t)) for t in range(60)]))
    assert calls == []
    assert store.episodes() == []


def test_a_forced_window_with_no_interpretation_is_skipped_cleanly():
    """`interpret` klip kesilemediğinde ya da yanıt ayrıştırılamadığında da
    `None` döndürüyor. Sağlıklı kademede bu bir kesinti değil: pencere
    atlanır, ertelenmez — ertelenirse her `catch_up`'ta yeniden VLM'e sorulur
    ve hiç kurtulmaz."""
    store = Store(":memory:")
    calls = []
    loop = _loop(store, lambda window: RouterDecision(
        decision="ignore", rationale="x", confidence=0.5),
        interpret=lambda window: None,
        synthesize=lambda window, interpretation, decision:
            calls.append(decision) or _episode(window[0].ts),
        is_degraded=lambda: False)
    list(loop.run([_observation(float(t)) for t in range(60)]))
    assert loop.deferred == []
    assert calls == []
    assert store.episodes() == []


def test_a_forced_window_during_an_outage_is_deferred_like_any_other():
    """Gerçek kesintide zorunlu pencere de kuyruğa girer ve bağlantı dönünce
    telafi edilir — beat 6 zorunlu örnekleme için de geçerli."""
    down = {"vlm": True}
    store = Store(":memory:")
    loop = DecisionLoop(
        store,
        route=lambda window: RouterDecision(decision="ignore", rationale="x",
                                            confidence=0.5),
        interpret=lambda window: (None if down["vlm"]
                                  else _interpretation(
                                      window[0].ts, notable_event="raf çöktü",
                                      severity="olay")),
        synthesize=_store_backed_synthesize(store),
        is_degraded=lambda: down["vlm"])

    list(loop.run([_observation(float(t)) for t in range(60)]))
    assert [window[0].ts for window in loop.deferred] == [0.0]

    down["vlm"] = False
    replayed = list(loop.catch_up())
    assert [event.late for event in replayed] == [True]
    assert loop.deferred == []


def test_the_forced_cadence_stays_cheap_enough_for_the_cost_claim():
    """10 dakikalık video 10 s'lik pencerelerle 60 pencere; N=6 en kötü hâlde
    ~10 ek görü çağrısı demek (~11 s/çağrı, canlı ölçüldü). Pahalı olan da,
    YOLO'nun göremediği bir olayı yakalayan tek yol olan da bu."""
    assert FORCED_SAMPLE_EVERY == 6


# -- Görev 16: bütçe sayaca değil kanıta harcanıyor ---------------------------
#
# Bütçe aynı kalıyor (`ceil(taban_geçemeyen / FORCED_SAMPLE_EVERY)`), NİŞAN
# değişiyor. Aşağıdaki testlerin hepsi sahte bir `motion_for` ile koşuyor:
# enerjiyi gerçekten hesaplamak `tests/test_motion.py`'ın işi, buradaki soru
# döngünün o enerjiyle ne yaptığı.

def _energy_map(energies: dict[float, float]):
    """Pencere başlangıcı → enerji eşlemesini `motion_for` kapanışına çevirir."""
    def motion_for(window):
        return energies.get(window[0].ts)
    return motion_for


def _quiet(count: int):
    return [_observation(float(t)) for t in range(count)]


def _forced_timestamps(observations, motion_for, store=None):
    seen = []
    loop = _loop(store or Store(":memory:"),
                 lambda window: RouterDecision(decision="ignore",
                                               rationale="x", confidence=0.5),
                 interpret=lambda window: seen.append(window[0].ts) or None,
                 motion_for=motion_for)
    list(loop.run(observations))
    return seen


def test_the_budget_lands_on_the_loudest_window_not_the_first_one():
    """Ölçülen arızanın birebir minyatürü.

    Altı durgun pencere, bütçe bir çağrı. Sayaç ilkini seçiyordu; enerji
    üçüncüsünü (W3, ts=20) seçiyor — olay orada. Raf çökmesi klibinde
    kaybedilen tam olarak bu tek seçimdi.
    """
    energies = {0.0: 0.10, 10.0: 0.20, 20.0: 0.90,
                30.0: 0.10, 40.0: 0.05, 50.0: 0.30}
    assert _forced_timestamps(_quiet(60), _energy_map(energies)) == [20.0]
    # Aynı gözlemler, enerji yokken: sayaç ilk pencereyi seçiyor.
    assert _forced_timestamps(_quiet(60), None) == [0.0]


def test_the_budget_is_ceil_of_all_windows_over_the_cadence():
    """Baştan sona durgun bir koşuda triyaj bir çağrı bile EKLEMİYOR.

    13 pencerenin 13'ü de tabandan geçemiyor, yani `ceil(n_windows / 6)` ile
    `ceil(taban_geçemeyen / 6)` burada aynı sayı: 3. Periyodik nöbetin aynı
    gözlemlerde ürettiği sayı da 3. İkisinin AYRILDIĞI yer taban geçen
    pencerelerin bulunduğu koşular ve orası kendi testlerinde ölçülüyor.
    """
    energies = {float(10 * i): 1.0 - i / 100 for i in range(13)}
    triaged = _forced_timestamps(_quiet(130), _energy_map(energies))
    periodic = _forced_timestamps(_quiet(130), None)
    assert len(triaged) == math.ceil(13 / FORCED_SAMPLE_EVERY) == 3
    assert len(triaged) == len(periodic)


def test_the_top_k_set_grows_with_the_number_of_windows():
    """Bütçe formülü tek bir noktada değil, ölçek boyunca doğru olmalı."""
    for windows_count in (1, 6, 7, 12, 13, 19):
        energies = {float(10 * i): 1.0 - i / 100
                    for i in range(windows_count)}
        seen = _forced_timestamps(_quiet(10 * windows_count),
                                  _energy_map(energies))
        assert len(seen) == math.ceil(windows_count / FORCED_SAMPLE_EVERY)


# -- Görü bütçesi tabandan ayrıldı --------------------------------------------
#
# Ölçülen arıza (`forklift-compilation--N9bG-sOU6LE-k05.mp4`): `205052f` izlemeyi
# bir zenginleştirmeye çevirdi, izsiz tespitler de `person_count`'a sayılmaya
# başladı, taban deseni `++--++++`'ten `++++++++`'e döndü. Bütçe yalnız taban
# GEÇEMEYEN pencereler arasında dağıtıldığı için bütçe sıfırlandı: yönlendirici
# sekiz kez `ignore` dedi, devrilen forkliftin epizodu (Yüksek, 00:30) ve üç
# aksiyon yok oldu. Algı katmanı iyileştikçe sistem körleşti.
#
# Onarım: taban "soralım mı"yı, enerji "nereye bakalım"ı belirler. Sıralama
# bütün pencereler üzerinde, bütçe `ceil(n_windows / FORCED_SAMPLE_EVERY)`.


def _router_calls_and_vision(observations, motion_for, decision="ignore",
                             store=None, interpretation=None):
    """(yönlendiriciye giden pencereler, görü çağrısı alan pencereler)."""
    routed, seen = [], []

    def _interpret(window):
        seen.append(window[0].ts)
        return interpretation(window) if interpretation else None

    loop = _loop(store or Store(":memory:"),
                 lambda window: routed.append(window[0].ts) or RouterDecision(
                     decision=decision, rationale="sakin", confidence=0.5),
                 interpret=_interpret,
                 motion_for=motion_for)
    list(loop.run(observations))
    return routed, seen


def test_a_floor_passing_window_the_router_ignores_can_still_be_looked_at():
    """k05 arızasının minyatürü.

    Altı pencerenin altısı da tabandan geçiyor, yönlendirici altısına da
    `ignore` diyor. Eski kuralda hiçbir katman hiçbir pencereye bakmıyordu —
    devrilen forklift tam da böyle kayboldu. Şimdi bütçe (`ceil(6/6)` = 1)
    en yüksek enerjili pencereye harcanıyor.
    """
    energies = {0.0: 0.1, 10.0: 0.2, 20.0: 0.9,
                30.0: 0.1, 40.0: 0.05, 50.0: 0.3}
    routed, seen = _router_calls_and_vision(
        [_observation(float(t), person_count=1) for t in range(60)],
        _energy_map(energies))
    assert routed == [float(10 * i) for i in range(6)]   # karar hâlâ onun
    assert seen == [20.0]                                # ama bakılıyor


def test_a_looked_at_ignore_window_can_open_an_episode():
    """Bakmak yetmez; görülen şey kayda değerse epizot açılmalı — yoksa k05
    yine sıfır epizotla biter."""
    store = Store(":memory:")
    decisions = []
    synthesize = _store_backed_synthesize(store)
    loop = _loop(store,
                 lambda window: RouterDecision(decision="ignore",
                                               rationale="sakin",
                                               confidence=0.5),
                 interpret=lambda window: _interpretation(
                     window[0].ts, notable_event="forklift devrildi",
                     severity="olay"),
                 synthesize=lambda window, interpretation, decision:
                     decisions.append(decision) or synthesize(
                         window, interpretation, decision),
                 motion_for=_energy_map({float(10 * i): i / 10
                                         for i in range(6)}))
    list(loop.run([_observation(float(t), person_count=1) for t in range(60)]))
    assert decisions == ["open_episode"]
    assert [episode.start_ts for episode in store.episodes()] == [50.0]


def test_the_looked_at_ignore_window_records_an_honest_handoff():
    """Defter olanı yazmalı. Burada taban GEÇİLDİ ve yönlendirici gerçekten
    karar verdi; gerekçe "taban geçilemedi" diyemez. Kaynak yine algı katmanı:
    bu ikinci bakış bir model kararı değil, döngünün kendi kuralı — ve ölçüm
    (`benchmark/kpi.py`) yönlendirici dağılımını `source_agent` ile ayıklıyor.
    """
    store = Store(":memory:")
    _router_calls_and_vision(
        [_observation(float(t), person_count=1) for t in range(20)],
        _energy_map({0.0: 0.9, 10.0: 0.1}), store=store)

    routed_first, looked, routed_second = store.handoffs()
    assert [h.ts for h in store.handoffs()] == [0.0, 0.0, 10.0]
    assert (routed_first.source_agent, routed_second.source_agent) == (
        "orchestrator", "orchestrator")
    assert routed_first.reason == "sakin"
    assert (looked.source_agent, looked.target_agent) == (
        "perception", "interpreter")
    assert looked.reason == ROUTED_FORCED_REASON
    assert looked.reason.startswith(FORCED_REASON_PREFIX)
    assert len(ROUTED_FORCED_REASON) <= MAX_HANDOFF_REASON


def test_a_budgeted_window_the_router_sends_to_vision_is_not_looked_at_twice():
    """Sözleşme: pencere başına EN FAZLA bir görü çağrısı.

    Pencere hem tabandan geçiyor hem bütçeye seçilmiş; yönlendirici zaten görü
    isteyen bir karar veriyor. Bakış orada yapılır ve bütçe orada harcanmış
    sayılır — ikinci bir çağrı maliyeti sessizce ikiye katlardı.
    """
    routed, seen = _router_calls_and_vision(
        [_observation(float(t), person_count=1) for t in range(20)],
        _energy_map({0.0: 0.9, 10.0: 0.1}), decision="open_episode",
        interpretation=lambda window: _interpretation(window[0].ts))
    assert routed == [0.0, 10.0]
    # Her pencere yönlendiricinin kararı yüzünden zaten bir kez yorumlanıyor;
    # bütçeli olan (ts=0) İKİNCİ kez yorumlanmıyor — olsaydı [0.0, 0.0, 10.0].
    assert seen == [0.0, 10.0]


def test_a_budgeted_window_the_router_closes_is_left_alone():
    """`close_episode` bilerek dışarıda.

    Yönlendirici o pencereyle bir epizodu kapatmışken aynı pencereden yeni bir
    epizot açmak `events[]` içinde aynı olayı iki kez sayardı. Bütçe orada
    harcanmıyor — maliyet yalnız DÜŞÜYOR, artmıyor.
    """
    _, seen = _router_calls_and_vision(
        [_observation(float(t), person_count=1) for t in range(20)],
        _energy_map({0.0: 0.9, 10.0: 0.1}), decision="close_episode")
    assert seen == []


def test_no_run_exceeds_one_vision_call_per_window():
    """Yönerge 3'ün bekçisi: üst sınır pencere sayısı, taban deseni ne olursa
    olsun. Bu kırmızıya dönerse maliyet iddiası çürümüş demektir."""
    for stride in (1, 2, 3, 5):
        observations = [
            _observation(float(t),
                         person_count=1 if (int(t) // 10) % stride == 0 else 0)
            for t in range(190)]
        _, seen = _router_calls_and_vision(
            observations,
            _energy_map({float(10 * i): (i * 7 % 19) / 19 for i in range(19)}))
        assert len(seen) <= 19
        assert len(seen) == len(set(seen))


def test_the_budget_never_exceeds_ceil_of_all_windows_over_the_cadence():
    """Bütçe payda TOPLAM pencere sayısı; taban deseni onu büyütemez.

    `ceil(taban_geçemeyen / N)` seçilseydi k05'te bütçe sıfır olurdu (taban her
    yerde geçiyor) — yani onarılmak istenen arıza. Seçilen formülün bedeli bu
    testin koruduğu şey: sınır aşılmıyor.
    """
    for count in (1, 6, 7, 12, 13, 19):
        for passing in (0, 1, count // 2, count):
            observations = [
                _observation(float(t),
                             person_count=1 if int(t) // 10 < passing else 0)
                for t in range(10 * count)]
            _, seen = _router_calls_and_vision(
                observations,
                _energy_map({float(10 * i): 1.0 - i / 100
                             for i in range(count)}))
            assert len(seen) <= math.ceil(count / FORCED_SAMPLE_EVERY)


def test_a_budgeted_ignore_does_not_reorder_the_stream():
    """§3a'nın bekçisi, bütçe sürümü.

    Bütçe ilk pencereye düşüyor, yükseltme ikincide. Biri bakışı döngüden
    çıkarıp toplu bir ön geçişe taşırsa zorunlu devir yükseltmeden ÖNCE
    deftere düşer ve sıra bozulur.
    """
    store = Store(":memory:")
    observations = [_observation(float(t), person_count=1) for t in range(20)]
    decisions = iter(["ignore", "escalate"])
    loop = _loop(store,
                 lambda window: RouterDecision(decision=next(decisions),
                                               rationale="x", confidence=0.9),
                 motion_for=_energy_map({0.0: 0.9, 10.0: 0.1}))

    stream = loop.run(observations)
    assert next(stream).episode.start_ts == 10.0
    # Yükseltme anında defter: yönlendirici@0 · bütçeli bakış@0 · yönlendirici@10
    assert [handoff.ts for handoff in store.handoffs()] == [0.0, 0.0, 10.0]
    assert list(stream) == []


def test_the_periodic_fallback_still_only_watches_failing_windows():
    """Enerji yoksa eski nöbet aynen: sayaç yalnız taban geçemeyen pencereleri
    sayıyor. Yedek bilerek genişletilmedi — kanıt yokken tabandan geçmiş bir
    pencereye bakmak hiçbir gerekçesi olmayan bir maliyet olurdu."""
    _, seen = _router_calls_and_vision(
        [_observation(float(t), person_count=1) for t in range(190)], None)
    assert seen == []


def test_an_active_opening_window_no_longer_silences_the_whole_clip():
    """Ölçülen ikinci delik: sayaç yönlendirici çağrısında sıfırlanıyordu.

    60 saniyelik klip, ilk pencere hareketli (tabandan geçiyor), sonrası
    sessiz. Sayaç ilk pencerede sıfırlanıyor ve kalan 5 durgun pencere altıya
    hiç ulaşamıyor — koşu SIFIR zorunlu örnekle bitiyordu. Triyajda taban
    geçemeyen 5 pencere var, `ceil(5 / 6)` = 1: en yüksek enerjili pencereye
    bir çağrı gidiyor.
    """
    observations = [_observation(float(t), person_count=1 if t < 10 else 0)
                    for t in range(60)]
    assert _forced_timestamps(observations, None) == []
    energies = {10.0: 0.1, 20.0: 0.2, 30.0: 0.8, 40.0: 0.1, 50.0: 0.2}
    assert _forced_timestamps(observations, _energy_map(energies)) == [30.0]


def test_a_motion_layer_with_nothing_to_say_falls_back_to_the_cadence():
    """`motion_for` her pencerede `None` derse elde kanıt yok demektir;
    periyodik nöbet aynen devrede kalıyor — sessizliğe DÜŞÜLMÜYOR."""
    assert _forced_timestamps(_quiet(130), lambda window: None) == \
        _forced_timestamps(_quiet(130), None) == [0.0, 60.0, 120.0]


def test_a_motion_layer_that_explodes_falls_back_instead_of_killing_the_run():
    """Triyaj koşunun sigortası değil nişancısı: patlarsa nişan bozulur,
    koşu bozulmaz."""
    def boom(window):
        raise RuntimeError("opencv patladı")

    assert _forced_timestamps(_quiet(130), boom) == [0.0, 60.0, 120.0]


def test_windows_without_energy_are_ranked_out_not_ranked_first():
    """Kanıtsız pencere (`None`) sıfır enerjiyle KARIŞTIRILMAMALI.

    `None` 'burada kanıt yok' demek; onu 0,0 sayıp sıralamaya sokmak zararsız
    ama tersini yapmak — `None`'ı en yükseğe koymak ya da sıralamayı
    çökertmek — bütçeyi kör pencerelere harcardı.
    """
    energies = {0.0: None, 10.0: None, 20.0: 0.3,
                30.0: None, 40.0: None, 50.0: 0.1}
    assert _forced_timestamps(_quiet(60), _energy_map(energies)) == [20.0]


def test_each_window_is_measured_once_per_run():
    """Enerji koşu başına bir kez soruluyor — pencere başına bir çağrı,
    fazlası değil. Ölçüm döngünün içine kayarsa maliyet sessizce artar."""
    asked = []
    energies = {float(10 * i): i / 10 for i in range(6)}

    def motion_for(window):
        asked.append(window[0].ts)
        return energies.get(window[0].ts)

    _forced_timestamps(_quiet(60), motion_for)
    assert sorted(asked) == [float(10 * i) for i in range(6)]


def test_the_chosen_window_is_still_visited_in_timeline_order():
    """§3a'nın bekçisi, triyaj sürümü.

    En yüksek enerji SON penceredeyse bile o pencere sırası gelince
    işlenmeli. Biri seçimi 'önce hepsini seç, sonra hepsini işle' hâline
    çevirirse zorunlu devir yükseltmeden ÖNCE deftere düşer ve bu test
    kırmızıya döner.
    """
    store = Store(":memory:")
    observations = [_observation(float(t),
                                 person_count=1 if 10 <= t < 20 else 0)
                    for t in range(30)]
    loop = _loop(store,
                 lambda window: RouterDecision(decision="escalate",
                                               rationale="x", confidence=0.9),
                 motion_for=_energy_map({0.0: 0.1, 20.0: 0.9}))

    stream = loop.run(observations)
    assert next(stream).episode.start_ts == 10.0
    # Yükseltme anında henüz yalnız yönlendiricinin devri var; ts=20'deki
    # zorunlu çağrı GELECEKTE ve deftere düşmemiş olmalı.
    assert [handoff.ts for handoff in store.handoffs()] == [10.0]

    list(stream)
    assert [handoff.ts for handoff in store.handoffs()] == [10.0, 20.0]


# --- pencere kaydı (Görev 19) ------------------------------------------------

def _wr_obs(ts, people=0, labels=()):
    """Pencere kaydı testleri için gözlem — etiketli tespitlerle."""
    return Observation(
        ts=ts, signals=Signals(person_count=people),
        detections=[Detection(label=label, confidence=0.9, box=(0, 0, 1, 1))
                    for label in labels])


def _quiet_loop(store):
    return DecisionLoop(
        store,
        route=lambda w: RouterDecision(decision="ignore", rationale="sakin",
                                       confidence=0.9),
        interpret=lambda w: None,
        synthesize=lambda w, i, d: None)


def test_a_window_record_is_written_for_every_window():
    """Besleme "sistem bu on saniyede ne gördü"yü buradan okuyor — 30 ham
    gözlemden değil. 3 fps'te ham gözlem ekrana basılamaz."""
    store = Store(":memory:")
    observations = [_wr_obs(t, people=2, labels=("person", "forklift"))
                    for t in (0.0, 3.0, 6.0, 11.0, 14.0)]

    list(_quiet_loop(store).run(observations))

    records = store.window_records()
    assert [r.index for r in records] == [1, 2]
    assert [r.total for r in records] == [2, 2]
    assert records[0].frames == 3
    assert records[0].person_peak == 2
    assert records[0].detections == 6
    assert records[0].labels == ["forklift", "person"]
    assert records[0].floor_passed is True
    assert (records[0].ts, records[0].end_ts) == (0.0, 6.0)


def test_the_three_window_outcomes_stay_distinct():
    """`skipped` ile `routed` aynı satıra düşemez: "bakılmadı" ile
    "bakıldı, bir şey yoktu" farklı şeyler."""
    store = Store(":memory:")
    # ilk pencere tabandan geçiyor (insan var), ikincisi geçemiyor ve
    # periyodik nöbet sayacı (_PRIMED=5) onu bütçeye almıyor
    observations = [_wr_obs(0.0, people=1), _wr_obs(11.0, people=0)]

    list(_quiet_loop(store).run(observations))

    assert [r.outcome for r in store.window_records()] == ["routed", "skipped"]


def test_the_window_record_matches_what_the_trace_line_says():
    """İki gösterim TEK yardımcıdan doğuyor. Ayrışırlarsa ekran ile kayıt
    farklı şeyler söyler ve hangisinin doğru olduğu anlaşılamaz."""
    from gozcu.pipeline.loop import window_record, window_span

    window = [_wr_obs(0.0, people=1, labels=("person",)),
              _wr_obs(2.0, people=3, labels=("forklift",))]
    record = window_record(window, index=1, total=4, floor_passed=True,
                           vision_budgeted=False, outcome="routed")
    assert (record.ts, record.end_ts) == (0.0, 2.0)
    assert record.person_peak == 3
    assert record.detections == 2
    assert record.labels == ["forklift", "person"]
    assert "kişi≤3" in window_span(record)
    assert "forklift,person" in window_span(record)


def test_window_records_are_journalled_so_the_feed_can_order_them():
    store = Store(":memory:")
    list(_quiet_loop(store).run([_wr_obs(0.0, people=1)]))
    assert [e.source for e in store.journal()][0] == "window_record"


def test_a_deferred_window_stops_claiming_it_reached_the_router():
    """Kayıt işleme başlamadan yazılıyor (algı satırı beslemede
    yönlendiriciden önce gelsin diye), ama erteleme ancak görü kademesi
    düştükten sonra biliniyor. Düzeltmesiz hâlde besleme telafiye alınmış
    bir pencere için "yönlendiriciye gitti" der — kesintiyi tam da
    göstermesi gereken anda gizler."""
    store = Store(":memory:")
    loop = DecisionLoop(
        store,
        route=lambda w: RouterDecision(decision="inspect", rationale="bak",
                                       confidence=0.9),
        interpret=lambda w: None,          # görü kademesi düştü
        synthesize=lambda w, i, d: None,
        is_degraded=lambda: True)          # ve bu bir KESİNTİ

    list(loop.run([_wr_obs(0.0, people=1)]))

    record, = store.window_records()
    assert record.outcome == "deferred"
    assert loop.deferred, "pencere telafi kuyruğuna girmedi"
    # Düzeltme AYRI bir defter satırı: pencere gerçekten işlendi, sonra
    # ertelendi ve ikisi de olmuş şeyler.
    window_rows = [e for e in store.journal() if e.source == "window_record"]
    assert [e.kind for e in window_rows] == ["create", "update"]
    assert window_rows[1].snapshot == {"outcome": "deferred"}


def test_a_healthy_window_is_not_marked_deferred():
    """`interpret` bozuk JSON'da da `None` döndürüyor ve o bir kesinti
    DEĞİL — ertelenmeyen pencere düzeltme de almamalı."""
    store = Store(":memory:")
    loop = DecisionLoop(
        store,
        route=lambda w: RouterDecision(decision="inspect", rationale="bak",
                                       confidence=0.9),
        interpret=lambda w: None,
        synthesize=lambda w, i, d: None,
        is_degraded=lambda: False)         # sağlam

    list(loop.run([_wr_obs(0.0, people=1)]))

    assert store.window_records()[0].outcome == "routed"
    assert [e.kind for e in store.journal()
            if e.source == "window_record"] == ["create"]


# --- görü kademesi kararı gerçekten etkiliyor (Görev 20) ---------------------

def _seeing_loop(store, notable, risk="Kritik", decision="inspect",
                 severity="olay"):
    """Yönlendirici `inspect` diyor, yorumlayıcı kayda değer bir şey görüyor.

    `severity` varsayılanı `"olay"`: bu yardımcının çağıranlarının çoğu
    epizodun AÇILMASINI bekliyor. Açılmaması gereken tek senaryo
    (`test_an_unremarkable_inspect_window_still_opens_nothing`) `severity`yi
    açıkça `"rutin"`e çeker.
    """
    from gozcu.core.models import Interpretation

    def _interpret(window):
        return Interpretation(observation_ts=window[0].ts,
                              description="forklift üst üste binmiş",
                              notable_event=notable, severity=severity,
                              model="vlm")

    def _synthesize(window, interpretation, decided):
        episode = Episode(start_ts=window[0].ts, phase="onset",
                          summary_tr="forklift üst üste binmiş",
                          preliminary_risk=risk)
        if decided == "open_episode":
            episode.id = store.create_episode(episode)
        else:
            open_episode = store.open_episode()
            store.update_episode(open_episode.id, summary_tr=episode.summary_tr)
            episode.id = open_episode.id
        return episode

    return DecisionLoop(
        store,
        route=lambda w: RouterDecision(decision=decision, rationale="bak",
                                       confidence=0.8),
        interpret=_interpret, synthesize=_synthesize)


def test_what_the_camera_saw_on_an_inspect_window_is_no_longer_thrown_away():
    """26 Ağustos canlı koşusu: 00:05'te yorumlayıcı "bir forklift başka bir
    forkliftin üstünde" dedi ve hiçbir şey olmadı. `inspect` dalı görüyü
    ÇAĞIRIYOR, parasını ödüyor ve sonucu atıyordu; `notable_event` yalnız
    `_forced_sample` içinde okunuyordu."""
    store = Store(":memory:")
    loop = _seeing_loop(store, notable="Forklift başka bir forkliftin üstünde.")

    list(loop.run([_wr_obs(0.0, people=1)]))

    assert store.episodes(), "görü kayda değer bir şey gördü, olay açılmadı"
    assert store.episodes()[0].summary_tr == "forklift üst üste binmiş"


def test_an_unremarkable_inspect_window_still_opens_nothing():
    """Görü kademesi "rutin" dediyse olay AÇILMAZ: her bakılan pencereyi
    olaya çevirmek `events[]` listesini kayıt dökümüne çevirirdi."""
    store = Store(":memory:")
    loop = _seeing_loop(store, notable=None, severity="rutin")

    list(loop.run([_wr_obs(0.0, people=1)]))

    assert store.episodes() == []


def test_a_high_risk_sighting_reaches_the_operator_at_that_moment():
    """"Kararlar olay anında verilir" — sentezleyici Kritik dediyse operatör
    videonun sonunu beklememeli."""
    store = Store(":memory:")
    loop = _seeing_loop(store, notable="Forklift devriliyor.", risk="Kritik")

    events = list(loop.run([_wr_obs(0.0, people=1)]))

    assert len(events) == 1
    assert events[0].late is False
    assert events[0].episode.preliminary_risk == "Kritik"


def test_a_low_risk_sighting_is_recorded_but_does_not_page_anyone():
    """Her "olay" operatörü çağırmaz; epizot yine de açılır. Metin bilerek
    gerçekten OLMUŞ küçük bir şey ("Bir kişi yürüyor." DEĞİL — o `severity`
    anchor'larında bizzat "rutin" örneği, `_may_open`'ı hiç geçmezdi)."""
    store = Store(":memory:")
    loop = _seeing_loop(store, notable="Bir kutu raftan düştü.", risk="Düşük")

    events = list(loop.run([_wr_obs(0.0, people=1)]))

    assert events == []
    assert store.episodes(), "olay yine de kaydedilmeli"


def test_a_merged_olay_sighting_now_pages_the_operator_with_a_bulletin():
    """Görev 20 sonrası ölçüm: yönlendirici HER pencerede `inspect` dedi,
    epizot açıldıktan sonraki ~50 saniye boyunca (insanlar toplandı, biri
    yere düştü) sistem TEK bir gelişme bülteni bile vermedi — kaynaşan HER
    pencere `update_episode`'a iniyordu ve `_routed` yalnız İLK açılışta
    yield ediyordu (bkz. `DecisionLoop._fuses_a_notable_event`). Bu testin
    eski hâli tam tersini iddia ediyordu ("yalnız olay AÇILIRKEN
    seslenilmeli") — o iddia arızanın ta kendisiydi ve burada tersine
    çevrildi: görü kademesi "olay" dediği SÜRECE her kaynaşma bir bülten
    üretir; `Supervisor.escalate`'in iki kipli yükseltmesi bunu ucuza mal
    ediyor (ilk çağrı tam müdahale, sonrakiler yalnız özet)."""
    store = Store(":memory:")
    loop = _seeing_loop(store, notable="Forklift devriliyor.", risk="Kritik")

    events = list(loop.run([_wr_obs(0.0, people=1), _wr_obs(11.0, people=1),
                            _wr_obs(22.0, people=1)]))

    assert len(events) == 3, "her 'olay' penceresi operatöre ulaşmalı"
    assert len(store.episodes()) == 1


# --- kaynaşan pencere bülteni (Görev 22, defect 2) --------------------------
#
# Yukarıdaki testin ölçtüğü aynı arızanın DOĞRUDAN `update_episode` kararı
# üzerinden koruması: `_routed`'ın `open_episode`/`update_episode` dalı
# sentezliyordu ama HİÇBİR ZAMAN yield etmiyordu, kararın `inspect`
# üzerinden mi yoksa yönlendiricinin doğrudan `update_episode` demesinden mi
# geldiği fark etmeksizin.

@pytest.mark.parametrize("severity,expect_second_yield", [
    ("olay", True), ("dikkat", False), ("rutin", False)])
def test_only_olay_severity_yields_on_fusion_into_an_open_episode(
        severity, expect_second_yield):
    """Seçicilik TEK ölçüt: yalnız görü kademesinin "olay" dediği pencere
    bir bülten üretir. Bu, alarm yağmurunu bir kez düzelten
    `ESCALATING_RISKS` gate'iyle aynı disiplin — her kaynaşmayı
    bültenletmek aynı arızayı geri getirirdi."""
    store = Store(":memory:")
    synthesize = _store_backed_synthesize(store)
    sequence = iter(["olay", severity])
    loop = _loop(store, lambda window: RouterDecision(
        decision="update_episode", rationale="x", confidence=0.9),
        interpret=lambda window: _interpretation(window[0].ts,
                                                 severity=next(sequence)),
        synthesize=synthesize)

    events = list(loop.run(
        [_observation(float(t), person_count=1) for t in range(20)]))

    # İlk pencere depo boşken de bir epizot açar (Görev 06 kuralı) ve
    # severity="olay" olduğu için o açılış da bir bülten üretir; ikinci
    # pencerenin KAYNAŞMASI yalnız severity=="olay" ise bülten üretir.
    assert len(events) == (2 if expect_second_yield else 1)
    assert len(store.episodes()) == 1


def test_the_first_opening_still_yields_exactly_once_not_twice():
    """İlk açılışta hem 'yüksek risk' hem 'olay severity' koşulu aynı
    pencerede birden doğru olabilir (`resolved == "open_episode"` VE
    `severity == "olay"`); iki ayrı yield koşulu çakışırsa aynı pencere iki
    kez duyurulmamalı — bu, Defect 2'nin eklediği ikinci yield yolunun
    ilkini ikiye katlamadığının kanıtı."""
    store = Store(":memory:")
    loop = _seeing_loop(store, notable="Forklift devriliyor.", risk="Kritik")

    events = list(loop.run([_wr_obs(0.0, people=1)]))

    assert len(events) == 1


def test_a_none_interpretation_fusing_into_an_open_episode_does_not_yield():
    """`interpretation is None` (görü kademesi düştü, klip kesilemedi, yanıt
    ayrıştırılamadı) YENİ bir olayın kanıtı değil — kaynaşma sessiz kalır,
    bugünkü davranış gibi."""
    store = Store(":memory:")
    synthesize = _store_backed_synthesize(store)
    interpretations = iter([_interpretation(severity="olay"), None])
    loop = _loop(store, lambda window: RouterDecision(
        decision="update_episode", rationale="x", confidence=0.9),
        interpret=lambda window: next(interpretations),
        synthesize=synthesize)

    events = list(loop.run(
        [_observation(float(t), person_count=1) for t in range(20)]))

    assert len(events) == 1   # yalnız ilk ("olay") pencere yield eder
    assert len(store.episodes()) == 1


# --- severity: epizot açılışının tek geçidi (Görev 21) ----------------------
#
# Ölçülen arıza: k04 (98.8 sn forklift kazası klibi) epizodu 00:00'da açtı —
# park hâlindeki bir kamyonun yanından yürüyen biri yüzünden — ve tek açık
# epizot değişmezi yüzünden kazanın gerçekleştiği 40-50 sn'yi de yuttu.
# Taban her insan içeren pencereyi geçiriyor, yönlendirici kuralları her
# pencerede tetikleniyor; görüntüyü GERÇEKTEN gören tek katman görü kademesi.
# `_may_open` bu yüzden `severity`ye bakıyor, `notable_event`in doluluğuna
# değil.

def test_may_open_blocks_a_routine_or_attention_reading_with_nothing_open():
    loop = _loop(Store(":memory:"), lambda w: RouterDecision(
        decision="ignore", rationale="x", confidence=0.5))
    assert loop._may_open(_interpretation(severity="rutin")) is False
    assert loop._may_open(_interpretation(severity="dikkat")) is False


def test_may_open_allows_an_event_reading_with_nothing_open():
    loop = _loop(Store(":memory:"), lambda w: RouterDecision(
        decision="ignore", rationale="x", confidence=0.5))
    assert loop._may_open(_interpretation(severity="olay")) is True


def test_may_open_falls_back_to_todays_behaviour_when_interpretation_is_none():
    """Görü kademesi düştüğünde (klip kesilemedi, yanıt ayrıştırılamadı,
    kesinti) açılış YİNE serbest — bozuk bir katman bütün koşuyu
    susturmamalı."""
    loop = _loop(Store(":memory:"), lambda w: RouterDecision(
        decision="ignore", rationale="x", confidence=0.5))
    assert loop._may_open(None) is True


def test_may_open_always_allows_fusion_when_an_episode_is_already_open():
    """Açılış sorusu, açık bir epizot varken hiç sorulmuyor: kaynaşma
    severity'den bağımsız sürüyor."""
    store = Store(":memory:")
    store.create_episode(_episode(0.0))
    loop = _loop(store, lambda w: RouterDecision(
        decision="ignore", rationale="x", confidence=0.5))
    for severity in ("rutin", "dikkat", "olay"):
        assert loop._may_open(_interpretation(severity=severity)) is True


def test_update_episode_with_nothing_open_and_a_routine_reading_opens_nothing():
    """`update_episode` depo boşken de gelebiliyor (Görev 06 notu) ve o
    durumda gerçek sentezleyici kaynaşacak bir şey bulamayınca koşulsuz yeni
    epizot AÇAR (`anomaly_analyst.synthesize`) — bu yol da `_may_open`
    geçidinden geçmeli."""
    store = Store(":memory:")
    loop = _loop(store, lambda window: RouterDecision(
        decision="update_episode", rationale="x", confidence=0.9),
        interpret=lambda window: _interpretation(window[0].ts,
                                                 severity="rutin"),
        synthesize=_store_backed_synthesize(store))
    list(loop.run([_observation(float(t), person_count=1) for t in range(10)]))
    assert store.episodes() == []


def test_update_episode_with_nothing_open_and_an_event_reading_opens_one():
    store = Store(":memory:")
    loop = _loop(store, lambda window: RouterDecision(
        decision="update_episode", rationale="x", confidence=0.9),
        interpret=lambda window: _interpretation(window[0].ts,
                                                 severity="olay"),
        synthesize=_store_backed_synthesize(store))
    list(loop.run([_observation(float(t), person_count=1) for t in range(10)]))
    assert len(store.episodes()) == 1


def test_escalate_with_a_routine_or_attention_reading_opens_nothing():
    """Yükseltme kararı bile açılışı zorlayamaz: kapı severity'de."""
    for severity in ("rutin", "dikkat"):
        store = Store(":memory:")
        loop = _loop(store, lambda window: RouterDecision(
            decision="escalate", rationale="x", confidence=0.9),
            interpret=lambda window: _interpretation(window[0].ts,
                                                     severity=severity),
            synthesize=_store_backed_synthesize(store))
        events = list(loop.run(
            [_observation(float(t), person_count=2) for t in range(10)]))
        assert events == [], severity
        assert store.episodes() == [], severity


def test_none_interpretation_still_opens_exactly_as_today():
    """Görü kademesi hiç sorulmadıysa (`interpretation is None`) açılış
    bugünküyle birebir aynı kalır — bu, geriye dönük uyumluluğun kanıtı."""
    store = Store(":memory:")
    loop = _loop(store, lambda window: RouterDecision(
        decision="escalate", rationale="x", confidence=0.9),
        interpret=lambda window: None,
        synthesize=_store_backed_synthesize(store))
    events = list(loop.run(
        [_observation(float(t), person_count=2) for t in range(10)]))
    assert len(events) == 1
    assert len(store.episodes()) == 1


def test_a_routine_reading_still_fuses_into_an_already_open_episode():
    """Açılış geçidi kaynaşmayı etkilemez: ilk pencere 'olay' epizodu açar,
    ikinci pencere 'rutin' olsa bile zaten açık olan epizoda eklenir."""
    store = Store(":memory:")
    decisions = []
    synthesize = _store_backed_synthesize(store)
    sequence = iter(["olay", "rutin"])
    loop = _loop(store, lambda window: RouterDecision(
        decision="escalate", rationale="x", confidence=0.9),
        interpret=lambda window: _interpretation(window[0].ts,
                                                 severity=next(sequence)),
        synthesize=lambda window, interpretation, decision:
            decisions.append(decision) or synthesize(window, interpretation,
                                                     decision))
    list(loop.run([_observation(float(t), person_count=2) for t in range(20)]))
    assert decisions == ["open_episode", "update_episode"]
    assert len(store.episodes()) == 1


def test_a_forced_window_opens_with_its_own_start_ts_not_an_earlier_ones():
    """Ölçülen arızanın minyatürü (k04): epizot OLAYIN penceresinde açılmalı
    — daha önceki 'rutin' bir pencerede, sıfırda değil."""
    store = Store(":memory:")
    energies = {0.0: 1.0, 10.0: 0.9, 20.0: 0.1, 30.0: 0.05, 40.0: 0.05,
               50.0: 0.05, 60.0: 0.05}
    readings = {0.0: "rutin", 10.0: "olay"}
    loop = _loop(store, lambda window: RouterDecision(
        decision="ignore", rationale="x", confidence=0.5),
        interpret=lambda window: _interpretation(
            window[0].ts, severity=readings[window[0].ts]),
        synthesize=_store_backed_synthesize(store),
        motion_for=_energy_map(energies))
    # 7 durgun pencere → bütçe ceil(7/6) = 2, en yüksek iki enerji (0.0, 10.0)
    # seçilir; ikisi de tabandan geçemiyor, yani ikisi de zorunlu görüye gider.
    list(loop.run([_observation(float(t)) for t in range(70)]))
    assert len(store.episodes()) == 1
    assert store.episodes()[0].start_ts == 10.0


# --- 26 Ağustos: yönlendiriciye enerji, ignore'a açık-olay güvencesi -------
#
# Orchestrator artık gerçekten `ignore` diyebiliyor (eskiden K1-K4 yapısal olarak
# imkânsız kılıyordu — bkz. `gozcu.agents.orchestrator.SYSTEM_PROMPT`). Bunun
# güvenli olmasının şartı: açık bir olayın ortasında `ignore` asla sessizce
# bir pencereyi atlatmamalı, çünkü enerji güvenlik ağı (`_forced_indices`)
# artık gerçekten devrede olan bir yolu koruyor.

def test_the_loop_passes_the_windows_energy_through_to_route():
    """`route` ikinci konumsal argümanı kabul ediyorsa `route(window,
    energy)` çağrılıyor — enerji `motion_for`dan, tıpkı görü bütçesi gibi."""
    seen_energy = []

    def route(window, energy):
        seen_energy.append(energy)
        return RouterDecision(decision="ignore", rationale="x", confidence=0.5)

    energies = {0.0: 0.42, 10.0: 0.13}
    loop = _loop(Store(":memory:"), route, motion_for=_energy_map(energies))
    list(loop.run([_observation(float(t), person_count=1) for t in range(20)]))
    assert seen_energy == [0.42, 0.13]


def test_a_route_without_a_second_parameter_is_still_called_the_old_way():
    """Geriye dönük uyumluluk: onlarca test hâlâ tek argümanlı bir sahte
    yönlendirici veriyor; enerjiyi yine de geçmek bunların hepsini
    `TypeError`'a düşürürdü."""
    calls = []

    def route(window):
        calls.append(window[0].ts)
        return RouterDecision(decision="ignore", rationale="x", confidence=0.5)

    loop = _loop(Store(":memory:"), route,
                motion_for=_energy_map({0.0: 0.9, 10.0: 0.1}))
    list(loop.run([_observation(float(t), person_count=1) for t in range(20)]))
    assert calls == [0.0, 10.0]


def test_an_open_episode_is_never_silently_ignored():
    """Açık bir olay varken yönlendiricinin `ignore` demesi pencereyi
    atlatmıyor: enerji güvenlik ağı devreye girip pencereyi yine görü
    kademesine gönderiyor — bütçeye seçilmiş olsun ya da olmasın."""
    store = Store(":memory:")
    synthesize = _store_backed_synthesize(store)
    seen = []
    decisions = iter(["escalate", "ignore"])

    def route(window):
        return RouterDecision(decision=next(decisions), rationale="x",
                              confidence=0.9)

    def interpret(window):
        seen.append(window[0].ts)
        return None

    loop = _loop(store, route, synthesize=synthesize, interpret=interpret)
    list(loop.run([_observation(float(t), person_count=1) for t in range(20)]))

    assert store.open_episode() is not None
    # İkinci pencere (00:10) "ignore" dedi ama olay açıkken atlanmadı: görü
    # kademesi (`interpret`) yine de çağrıldı.
    assert seen == [0.0, 10.0]
    handoffs = store.handoffs()
    last = handoffs[-1]
    assert (last.source_agent, last.target_agent) == ("perception",
                                                       "interpreter")
    assert last.reason == OPEN_EPISODE_FORCED_REASON


def test_ignoring_before_any_episode_is_open_still_costs_nothing():
    """Karşı örnek: açık bir olay YOKKEN `ignore` eskisi gibi ucuz kalmalı —
    yorum kademesi çağrılmıyor. Bu, açık-olay güvencesinin maliyeti sadece
    gerektiğinde ödediğinin kanıtı."""
    store = Store(":memory:")
    seen = []
    loop = _loop(store, lambda window: RouterDecision(
        decision="ignore", rationale="x", confidence=0.5),
        interpret=lambda window: seen.append(window[0].ts) or None)
    list(loop.run([_observation(float(t), person_count=1) for t in range(20)]))
    assert seen == []
    assert store.open_episode() is None
