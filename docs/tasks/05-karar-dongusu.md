# Görev 05 — Olay anında karar döngüsü (`gozcu/loop.py`)

> ## ✅ TAMAMLANDI — 23 Ağustos 2026, `cf7b81e`
>
> **Karar döngüsü indi.** `gozcu/loop.py` var, `tests/test_loop.py` 17 test ile
> yeşil. Bu dosyayı yeniden uygulama — aşağısı ne yapıldığının kaydı.
>
> **Sonraki göreve başlarken bilmen gerekenler**
> ([kararlar](#tamamlanma-notları-gelecek-görevleri-bağlayan) bölümüne bak):
> `run()` artık `Episode` değil **`LoopEvent(episode, late)`** yield ediyor;
> **tek açık epizot değişmezini döngü koruyor** — açıkken gelen ikinci
> `open_episode` kararı `update_episode`'a iniyor; **erteleme yalnızca gerçek
> kesintide** oluyor, her `None` yorumda değil.

**Bağımlılık:** [01](01-sozlesme.md), [02](02-olay-deposu.md), [03](03-gateway.md)

## Bağlam

**Bu dosya projenin en önemli mimari tercihini kod haline getiriyor.**

Yüklenen bir videoyu işlemenin iki yolu var:

- **Önce izle, sonra özetle.** Video baştan sona işlenir, sonunda rapor çıkar,
  aksiyonlar rapordan sonra konuşulur. Bu bir *özetleme* sistemidir — ortada
  karar anı yoktur, sadece bitmiş bir metin vardır. Şartnamenin puanladığı
  *çok adımlı karar zincirleri*, *dinamik araç seçimi* ve *inisiyatif alma*
  kalemlerinin üçü de bu şekilde ulaşılamaz.
- **Videonun kendi saatinde karar ver.** Sistem zaman çizelgesinde ilerler,
  kritik ana geldiğinde **orada durur**: riski biçer, sorgular yapar, operatöre
  seslenir, aksiyonu çağırır. Video henüz bitmemiştir.

İkincisini yapıyoruz. Ve bunun gerçekten olması için döngünün **duraklayabilmesi**
gerekiyor — senkron bir `for` döngüsü baştan sona koşarsa, diyalog yine olaydan
sonra gerçekleşmiş olur ve reddettiğimiz şeklin aynısına düşeriz.

Çözüm: `run` bir **generator**. Yükseltme anında `yield` ediyor, çağıran
taraf operatörle konuşup `next()` ile devam ettiriyor. Tek iş parçacığı, kilit
yok, ~15 satır.

### Depodan devraldığın iki boşluk (Görev 02)

- **`open_episode()` tek açık epizot garantisi vermiyor.** `state="open"` olan
  satırların *sonuncusunu* döndürüyor ve depo aynı anda birden çok açık epizota
  seve seve izin veriyor. Bu değişmezi karar döngüsü koruyacak: yeni bir epizot
  açmadan önce mevcut açığı kapat ya da yeniden kullan — altındaki hiçbir katman
  ihlali yakalamaz.
- **`update_episode(episode_id, ...)` bilinmeyen id'de çıplak `TypeError`
  atıyor** — `fetchone()[0]` yapıyor, `None` kontrolü yok. Bayat bir epizot
  id'si geçirirsen okunabilir bir hata değil, bunu alırsın.

### Gateway'den devraldığın kural (Görev 03)

`is_degraded` geri çağrısı bu modüle dışarıdan enjekte ediliyor ve **bağlarken
`lambda: gw.is_degraded("vlm")` yazılacak** — çıplak `gw.is_degraded` değil.
Çıplak biçim artık "**herhangi bir** kademe bozuk" demek; `rerank`'ın 400'ü ise
beklenen bir davranış, kesinti değil. Onu da sayan bir bayrak döngüye her
pencereyi sonsuza dek erteletir ve `catch_up()` hiç çalışmaz. Burada önemli olan
tek kademe `vlm`.

## Kurulum

```bash
uv sync --extra dev
uv run pytest tests/test_store.py -v      # Görev 02 yeşil olmalı
```

## Bağımlı olduğun imzalar

```python
# gozcu/models.py
Observation(id, ts, detections, signals)
Signals(velocities, vanished_tracks, person_count, person_count_delta, gathering)
RouterDecision(decision, rationale, confidence)   # decision: ignore|inspect|open_episode|
                                      #           update_episode|close_episode|escalate
Episode(id, start_ts, end_ts, phase, summary_tr, participants, preliminary_risk, state)
Interpretation(id, observation_ts, description, notable_event, model, latency_ms, tokens)
LoopEvent(episode, late)                          # run()/catch_up() bunu yield eder
Handoff(id, ts, source_agent, target_agent, reason, confidence, payload_ref)

# gozcu/store.py
Store.save_handoff(d) -> int
```

## Ne yapacaksın

```python
WINDOW_S = 10.0
FLOOR_VELOCITY = 1.0

windows(observations, window_s=WINDOW_S) -> Iterator[list[Observation]]
passes_floor(window: list[Observation]) -> bool
DecisionLoop(store, route, interpret, synthesize, is_degraded=lambda: False)
  .run(observations) -> Iterator[LoopEvent]    # yükseltmede yield eder
  .catch_up() -> Iterator[LoopEvent]           # kesinti bitince atlananları işler
  .deferred: list[list[Observation]]           # kesinti sırasında atlananlar
```

Bütün geri çağrılar dışarıdan enjekte ediliyor — bu modül hiçbir ajan olmadan
test edilebiliyor.

**Sentezleyici geri çağrısının imzası:** `synthesize(window, interpretation, decision) -> Episode | None`.
`decision` parametresi zorunlu: `open_episode` yeni epizot açar, `update_episode`
açık epizota kaynaşır, `close_episode` kapatır. Bu olmadan üç karar da yeni
epizot açar ve tek bir kaza N kopya epizot olur.

**Dispeçer karelere değil pencerelere bakıyor.** 10 dakikalık videoda kare başına
yönlendirme ~600 model çağrısı demek; pencerelerle ~60. Altında da yerel bir
taban var: hiçbir şeyin kıpırdamadığı pencere modele hiç gitmiyor.

Bu tabanın "kural tabanlı" olmadığının savunması net: **hareket sensörü kuralı,
alarm kararı değildir.** Taban *ne zaman soracağını* belirliyor; *neyin önemli
olduğuna* model karar veriyor.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_loop.py`

```python
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
```

`test_ledger_timestamps_are_video_relative_not_wall_clock` önemsiz görünüyor
ama değil: defterdeki zaman damgaları süreç uptime'ı olursa
(`time.monotonic()`), jüri kanıt defterini açtığında anlamsız sayılar görür.
Video-göreli olmalı.

Son dört test tek başına bir sözleşme: tek açık epizot değişmezi, `late`
damgası ve "erteleme yalnızca kesintide" kuralı burada kilitleniyor.

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_loop.py -v
```
Beklenen: `ModuleNotFoundError: No module named 'gozcu.loop'`

### 3. `gozcu/loop.py` yaz

```python
"""Olay anında karar döngüsü.

Projenin en önemli mimari tercihi burada kod oluyor: sistem videoyu baştan
sona işleyip sonunda özet yazmıyor, **videonun kendi saatinde** karar veriyor.
Bunun gerçekten olabilmesi için döngünün duraklayabilmesi gerekiyor — bu
yüzden `run` bir generator: yükseltme anında `yield` ediyor, çağıran taraf
operatörle konuşuyor, `next()` döngüyü kaldığı yerden sürdürüyor.

Bütün geri çağrılar dışarıdan enjekte ediliyor; modül hiçbir ajan olmadan
test edilebiliyor.
"""

from collections.abc import Callable, Iterator

from gozcu.models import (Episode, Handoff, Interpretation, LoopEvent,
                          Observation, RouterDecision)
from gozcu.store import Store

WINDOW_S = 10.0
FLOOR_VELOCITY = 1.0

TARGET = {"inspect": "interpreter",
          "open_episode": "synthesizer",
          "update_episode": "synthesizer",
          "close_episode": "synthesizer",
          "escalate": "supervisor"}

# Görü katmanına gerçekten soru soran kararlar. `close_episode` bilerek yok:
# kapanış penceresi yorumlanmıyor, dolayısıyla oradaki `None` bir kesinti
# kanıtı değil ve o pencere asla ertelenmemeli.
NEEDS_VISION = ("inspect", "open_episode", "update_episode", "escalate")


def windows(observations: list[Observation],
            window_s: float = WINDOW_S) -> Iterator[list[Observation]]:
    """Gözlemleri `window_s` saniyelik pencerelere böler.

    Dispeçer karelere değil pencerelere bakıyor: 10 dakikalık videoda kare
    başına yönlendirme ~600 model çağrısı, pencerelerle ~60.
    """
    if not observations:
        return
    start, bucket = observations[0].ts, []
    for observation in observations:
        if observation.ts - start >= window_s:
            yield bucket
            start, bucket = observation.ts, []
        bucket.append(observation)
    if bucket:
        yield bucket


def passes_floor(window: list[Observation]) -> bool:
    """Ucuz yerel taban: *ne zaman soracağını* belirler, *neyin önemli
    olduğunu* değil. Hareket sensörü kuralı, alarm kararı değildir."""
    for observation in window:
        signals = observation.signals
        if signals.person_count > 0 or signals.vanished_tracks or signals.gathering:
            return True
        if any(speed >= FLOOR_VELOCITY for speed in signals.velocities.values()):
            return True
    return False


class DecisionLoop:
    def __init__(self, store: Store,
                 route: Callable[[list[Observation]], RouterDecision],
                 interpret: Callable[[list[Observation]], Interpretation | None],
                 synthesize: Callable[
                     [list[Observation], Interpretation | None, str],
                     Episode | None],
                 is_degraded: Callable[[], bool] = lambda: False) -> None:
        """`is_degraded` bağlanırken `lambda: gw.is_degraded("vlm")` yazılacak.

        Çıplak `gw.is_degraded` "**herhangi bir** kademe bozuk" demek;
        `rerank`'ın 400'ü ise beklenen davranış, kesinti değil. Onu da sayan
        bir bayrak her pencereyi sonsuza dek erteletir ve `catch_up()` hiç
        çalışmaz.
        """
        self.store = store
        self.route = route
        self.interpret = interpret
        self.synthesize = synthesize
        self.is_degraded = is_degraded
        self.deferred: list[list[Observation]] = []

    def _handoff(self, target: str, ts: float, reason: str,
                 confidence: float) -> None:
        self.store.save_handoff(Handoff(ts=ts, source_agent="router",
                                        target_agent=target, reason=reason,
                                        confidence=confidence,
                                        payload_ref=f"window@{ts}"))

    def _resolve(self, decision: str) -> str:
        """Tek açık epizot değişmezini korur — depo korumuyor, burası koruyor.

        `Store.open_episode()` açık satırların sonuncusunu döndürüyor ve depo
        aynı anda birden çok açık epizota seve seve izin veriyor. Açık bir
        epizot varken ikinci bir `open_episode` rakip epizot doğurur: ilki
        sonsuza dek açık kalır ve şartnamenin `events[]` listesi aynı olayı
        iki kez sayar. Bu yüzden karar `update_episode`'a indiriliyor —
        gözlem yeni bir epizot açmak yerine mevcuda kaynaşıyor.
        """
        if decision == "open_episode" and self.store.open_episode() is not None:
            return "update_episode"
        return decision

    def run(self, observations: list[Observation]) -> Iterator[LoopEvent]:
        """Videonun zaman çizelgesinde ilerler. Yükseltme gerektiren her anda
        `LoopEvent` yield eder ve ORADA DURUR — çağıran taraf operatörle
        konuşup döngüyü devam ettirir. §3a tam olarak budur.

        Canlı yükseltmeler `late=False`; kesinti telafisinden gelen her şey
        `late=True` ile işaretlenir.
        """
        for window in windows(observations):
            ts = window[0].ts
            if not passes_floor(window):
                continue

            decision = self.route(window)
            self._handoff(TARGET.get(decision.decision, "perception"), ts,
                          decision.rationale, decision.confidence)

            if decision.decision == "ignore":
                continue

            needs_vision = decision.decision in NEEDS_VISION
            interpretation = self.interpret(window) if needs_vision else None

            if decision.decision in ("open_episode", "update_episode",
                                     "close_episode"):
                self.synthesize(window, interpretation,
                                self._resolve(decision.decision))

            elif decision.decision == "escalate":
                # Yükseltmenin tutunacağı bir epizot olmalı; yoksa risk
                # analizi hangi epizota yazacağını bilemez. Açık epizot varsa
                # `_resolve` bunu kaynaşmaya indirir.
                episode = self.synthesize(window, interpretation,
                                          self._resolve("open_episode"))
                if episode is not None:
                    # Video bitmedi. Çağıran taraf burada operatörle konuşuyor.
                    yield LoopEvent(episode=episode, late=False)

            # Erteleme YALNIZCA kesintide. `interpret` bozuk JSON'da veya
            # eksik karede de `None` döndürüyor; onu ertelemek pencereyi her
            # `catch_up`'ta yeniden VLM'e sordurur ve hiç kurtulmaz.
            if needs_vision and interpretation is None and self.is_degraded():
                self.deferred.append(window)

        # Bağlantı döndüyse atlananları telafi et.
        yield from self.catch_up()

    def catch_up(self) -> Iterator[LoopEvent]:
        """Bozulma sırasında atlanan pencereleri yeniden işler. Demo beat 6'nın
        'bağlantı gelince açığı kapatıyor' sözünü tutan yer burası.

        Buradan çıkan her epizot `late=True`: geç keşfedilen bir olayı
        saklamak güvenlik sistemi için kabul edilemez, ama onu canlı bir kriz
        gibi duyurmak da yanıltıcı — o yüzden duyuruluyor, ama damgalanıyor.
        """
        if not self.deferred or self.is_degraded():
            return
        pending, self.deferred = self.deferred, []
        for window in pending:
            interpretation = self.interpret(window)
            if interpretation is None and self.is_degraded():
                # Kesinti telafi sırasında geri geldi; pencere kuyrukta kalır.
                self.deferred.append(window)
                continue
            self._handoff("synthesizer", window[0].ts, "telafi", 0.6)
            episode = self.synthesize(window, interpretation,
                                      self._resolve("open_episode"))
            if episode is not None:
                yield LoopEvent(episode=episode, late=True)
```

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_loop.py -v
```
Beklenen: 17 passed

### 5. Commit

```bash
git add gozcu/loop.py tests/test_loop.py
git commit -m "feat: in-flight decision loop that pauses at escalation"
```

## Doğrulama

```bash
uv run pytest tests/test_loop.py -v
```
Beklenen: **17 passed**

## Çağıran taraf nasıl kullanacak (Görev 16 ve 17 için)

```python
loop = DecisionLoop(store, route=route_fn, interpret=interpret_fn,
                    synthesize=synthesize_fn,
                    is_degraded=lambda: gw.is_degraded("vlm"))   # çıplak hâli değil

for event in loop.run(observations):
    supervisor.escalate(event.episode)   # operatör konuşuyor, döngü duruyor
    if event.late:
        pass   # kesinti telafisinden geldi: duyur, ama canlı kriz gibi değil
    # operatör "devam" deyince for döngüsü kendiliğinden ilerliyor
```

Kesinti bitince (`gw.inject_failure(set())`) `loop.catch_up()` ayrıca
çağrılabilir; `run()` zaten sonunda bir kez telafi ediyor.

## Tamamlanma notları (gelecek görevleri bağlayan)

- **`run()` ve `catch_up()` `LoopEvent(episode, late)` yield ediyor, `Episode`
  değil.** Tek kanaldan iki anlam akıyordu ve çağıran taraf bayat bir epizotu
  taze kriz gibi duyuruyordu. `late=True` "bu epizot kesinti sonrası geri
  dolduruldu" demek: **duyurulacak, ama canlı bir kriz gibi değil.** Çağrı
  yerleri `event.episode` okuyacak (Görev 16 ve 17).
- **Tek açık epizot değişmezini döngü koruyor, depo değil.** `_resolve()` açık
  bir epizot varken gelen `open_episode` kararını `update_episode`'a indiriyor.
  `Store.open_episode()` bu garantiyi vermiyor ve yönlendirici promptu ikinci
  bir açılışı yasaklamıyor — tek bekçi burası. Bu, Görev 07'nin kuralına
  dayanıyor: `open_episode` **koşulsuz** yeni epizot açar, `update_episode`
  `store.open_episode()` üzerine kaynaşır. Sentezleyici bu ayrımı bozarsa
  değişmez de bozulur.
- **Erteleme yalnızca görü kademesi gerçekten bozukken oluyor.** `interpret`
  bozuk JSON'da ve eksik karede de `None` döndürüyor; bunları ertelemek
  pencereyi her `catch_up`'ta yeniden VLM'e sordurup hiç kurtarmıyordu.
  `close_episode` penceresi ise **bilerek hiç yorumlanmıyor** (`NEEDS_VISION`
  içinde yok) — oradaki `None` bir kesinti kanıtı değil.
- **`is_degraded` sıfır argümanlı bir geri çağrı**, varsayılanı
  `lambda: False`. Bağlayan taraf **`is_degraded=lambda: gw.is_degraded("vlm")`
  yazmak zorunda.** Çıplak `gw.is_degraded` "herhangi bir kademe" demek;
  `rerank`'ın beklenen 400'ü de sayılırsa her pencere sonsuza dek ertelenir ve
  `catch_up()` hiç çalışmaz. Varsayılanla bırakılırsa da tersi olur: `deferred`
  hiç dolmaz, telafi demosu sessizce hiçbir şey yapmaz.
- **`synthesize` üç argümanlı enjekte ediliyor:**
  `(window, interpretation, decision) -> Episode | None`. Görev 07'nin gerçek
  imzası ise `synthesize(gw, store, window, interpretation, decision,
  on_close=None)` — bağlama yerinde bir `partial` (ya da `lambda`) gerekiyor.
- **`passes_floor` şu dördünden biriyle tetikleniyor:** `person_count > 0`,
  herhangi bir `vanished_tracks`, `gathering`, ya da `FLOOR_VELOCITY`'yi (1.0)
  aşan bir hız. Bunların hiçbiri yoksa pencere modele hiç gitmiyor — yönlendirici
  de çağrılmıyor.
