"""Görev 05 — olay anında karar döngüsü.

Bu dosyanın koruduğu iki şey var: kararın videonun *içinde* verilmesi
(`run` bir generator ve yükseltmede duruyor) ve aynı anda **tek bir açık
epizot** değişmezi — depo bunu korumuyor, döngü koruyor.
"""

import math

from gozcu.loop import (FORCED_REASON, FORCED_REASON_PREFIX,
                        FORCED_SAMPLE_EVERY, MAX_HANDOFF_REASON, DecisionLoop,
                        passes_floor, windows)
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


def _interpretation(ts=0.0, notable_event=None):
    """Gerçek `interpret` bunu ya da `None` döndürür — çıplak `object()` değil.

    Sahte iş arkadaşının şekli gerçeğiyle aynı olmazsa test yalancı yeşile
    döner: `synthesize` alan okur, `object()` alan okumaz.
    """
    return Interpretation(observation_ts=ts, description="forklift geçiyor",
                          notable_event=notable_event, model="test-vlm")


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
        "router", "perception")
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
            window[0].ts, notable_event="raf çöktü"),
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
        interpret=lambda window: _interpretation(window[0].ts),
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
                                      window[0].ts, notable_event="raf çöktü")),
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


def test_the_budget_is_ceil_of_the_failing_windows_over_the_cadence():
    """Maliyet iddiası aynen duruyor: triyaj bir çağrı bile EKLEMİYOR.

    13 durgun pencere → `ceil(13 / 6)` = 3 görü çağrısı; periyodik nöbetin
    aynı gözlemlerde ürettiği sayı da 3.
    """
    energies = {float(10 * i): 1.0 - i / 100 for i in range(13)}
    triaged = _forced_timestamps(_quiet(130), _energy_map(energies))
    periodic = _forced_timestamps(_quiet(130), None)
    assert len(triaged) == math.ceil(13 / FORCED_SAMPLE_EVERY) == 3
    assert len(triaged) == len(periodic)


def test_the_top_k_set_grows_with_the_number_of_failing_windows():
    """Bütçe formülü tek bir noktada değil, ölçek boyunca doğru olmalı."""
    for windows_count in (1, 6, 7, 12, 13, 19):
        energies = {float(10 * i): 1.0 - i / 100
                    for i in range(windows_count)}
        seen = _forced_timestamps(_quiet(10 * windows_count),
                                  _energy_map(energies))
        assert len(seen) == math.ceil(windows_count / FORCED_SAMPLE_EVERY)


def test_windows_that_pass_the_floor_are_untouched_by_triage():
    """Triyaj yalnız tabandan geçemeyen pencerelere bakıyor.

    Tabandan geçen pencere eski yolunda kalıyor: önce yönlendirici, görü
    kademesi ancak karar gerektiriyorsa. Enerjisi ne olursa olsun."""
    routed, seen = [], []
    loop = _loop(Store(":memory:"),
                 lambda window: routed.append(window[0].ts) or RouterDecision(
                     decision="ignore", rationale="x", confidence=0.5),
                 interpret=lambda window: seen.append(window[0].ts) or None,
                 motion_for=lambda window: 1.0)
    list(loop.run([_observation(float(t), person_count=1) for t in range(60)]))
    assert routed == [float(10 * i) for i in range(6)]
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
