# Görev 05 — Olay anında karar döngüsü (`gozcu/loop.py`)

**Sahip:** `uvyscengiz` · **Gün:** 23 Ağustos · **Süre:** ~2.5 saat
**Bağımlılık:** [01](01-sozlesme.md), [02](02-olay-deposu.md)

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
  .run(observations) -> Iterator[Episode]      # yükseltmede yield eder
  .catch_up() -> Iterator[Episode]             # bozulma bitince atlananları işler
  .deferred: list[list[Observation]]           # bozulma sırasında atlananlar
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
from gozcu.loop import DecisionLoop, windows, passes_floor
from gozcu.models import Episode, Observation, RouterDecision, Signals, Detection
from gozcu.store import Store


def _obs(ts, person_count=0, velocities=None):
    return Observation(ts=ts,
                  detections=[Detection(label="person", confidence=0.9,
                                    box=(0, 0, 1, 1), track_id=1)] * person_count,
                  signals=Signals(person_count=person_count,
                                  velocities=velocities or {}))


def _ep(ts=0.0):
    return Episode(start_ts=ts, phase="development", summary_tr="x", preliminary_risk="Kritik")


def _turn_loop(store, route, synthesize=None, interpret=None):
    return DecisionLoop(store, route=route,
                        interpret=interpret or (lambda p: None),
                        synthesize=synthesize or (lambda p, y, k: _ep(p[0].ts)))


def test_pencereler_groups_by_ten_seconds():
    g = [_obs(float(t)) for t in range(25)]
    assert [len(p) for p in windows(g)] == [10, 10, 5]


def test_taban_blocks_a_completely_still_window():
    assert passes_floor([_obs(float(t)) for t in range(10)]) is False
    assert passes_floor([_obs(float(t), person_count=2) for t in range(10)]) is True


def test_router_is_not_called_for_windows_below_the_floor():
    calls = []
    d = _turn_loop(Store(":memory:"),
               lambda p: calls.append(p) or RouterDecision(
                   decision="ignore", rationale="x", confidence=0.5))
    list(d.run([_obs(float(t)) for t in range(20)]))
    assert calls == []


def test_escalation_yields_an_episode_before_the_video_ends():
    """§3a'nın bekçisi. Biri döngüyü 'topla-sonra-karar-ver' haline
    çevirirse bu test kırmızıya döner."""
    observations = [_obs(float(t), person_count=2) for t in range(30)]

    def route(p):
        return RouterDecision(
            decision="escalate" if p[0].ts < 10 else "ignore",
            rationale="x", confidence=0.9)

    d = _turn_loop(Store(":memory:"), route)
    ilk = next(d.run(observations))
    assert isinstance(ilk, Episode)
    assert ilk.start_ts < observations[-1].ts


def test_escalation_synthesises_an_episode_first():
    """Yükseltilecek bir epizot yoksa risk analizi tutunacak bir şey bulamaz."""
    calls = []
    d = _turn_loop(Store(":memory:"),
               lambda p: RouterDecision(decision="escalate", rationale="x",
                                      confidence=0.9),
               synthesize=lambda p, y, k: calls.append(k) or _ep(p[0].ts))
    next(d.run([_obs(float(t), person_count=2) for t in range(10)]))
    assert calls == ["open_episode"]


def test_the_decision_is_passed_through_to_the_synthesiser():
    decisions = []
    sequence = iter(["open_episode", "update_episode", "close_episode"])
    d = _turn_loop(Store(":memory:"),
               lambda p: RouterDecision(decision=next(sequence), rationale="x",
                                      confidence=0.9),
               synthesize=lambda p, y, k: decisions.append(k) or _ep(p[0].ts))
    list(d.run([_obs(float(t), person_count=1) for t in range(30)]))
    assert decisions == ["open_episode", "update_episode", "close_episode"]


def test_every_routing_decision_is_written_to_the_handoff_ledger():
    store = Store(":memory:")
    d = _turn_loop(store, lambda p: RouterDecision(decision="ignore", rationale="sakin",
                                             confidence=0.8))
    list(d.run([_obs(float(t), person_count=1) for t in range(20)]))
    assert len(store.handoffs()) == 2
    assert store.handoffs()[0].source_agent == "router"


def test_windows_skipped_while_degraded_are_deferred_and_replayed():
    """Beat 6: bağlantı kesikken atlanan pencereler kaybolmuyor, dönünce
    yeniden işleniyor."""
    down = {"v": True}
    d = DecisionLoop(
        Store(":memory:"),
        route=lambda w: RouterDecision(decision="inspect", rationale="x",
                                       confidence=0.9),
        interpret=lambda w: None if down["v"] else object(),
        synthesize=lambda w, i, k: _ep(w[0].ts),
        is_degraded=lambda: down["v"])

    list(d.run([_obs(float(t), person_count=1) for t in range(20)]))
    assert len(d.deferred) == 2

    down["v"] = False
    replayed = list(d.catch_up())
    assert len(replayed) == 2 and d.deferred == []


def test_catch_up_is_a_no_op_while_still_degraded():
    d = DecisionLoop(Store(":memory:"),
                     route=lambda w: RouterDecision(decision="inspect",
                                                    rationale="x",
                                                    confidence=0.9),
                     interpret=lambda w: None,
                     synthesize=lambda w, i, k: _ep(w[0].ts),
                     is_degraded=lambda: True)
    list(d.run([_obs(float(t), person_count=1) for t in range(10)]))
    assert list(d.catch_up()) == [] and len(d.deferred) == 1


def test_ledger_timestamps_are_video_relative_not_wall_clock():
    store = Store(":memory:")
    d = _turn_loop(store, lambda p: RouterDecision(decision="ignore", rationale="x",
                                             confidence=0.8))
    list(d.run([_obs(float(t), person_count=1) for t in range(20)]))
    assert [dv.ts for dv in store.handoffs()] == [0.0, 10.0]
```

Son test önemsiz görünüyor ama değil: defterdeki zaman damgaları süreç
uptime'ı olursa (`time.monotonic()`), jüri kanıt defterini açtığında anlamsız
sayılar görür. Video-göreli olmalı.

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_loop.py -v
```
Beklenen: `ModuleNotFoundError: No module named 'gozcu.loop'`

### 3. `gozcu/loop.py` yaz

```python
from collections.abc import Callable, Iterator

from gozcu.models import Handoff, Episode, Observation, RouterDecision
from gozcu.store import Store

WINDOW_S = 10.0
FLOOR_VELOCITY = 1.0

TARGET = {"inspect": "interpreter",
         "open_episode": "synthesizer",
         "update_episode": "synthesizer",
         "close_episode": "synthesizer",
         "escalate": "supervisor"}


def windows(observations: list[Observation],
               window_s: float = WINDOW_S) -> Iterator[list[Observation]]:
    if not observations:
        return
    start, bucket = observations[0].ts, []
    for g in observations:
        if g.ts - start >= window_s:
            yield bucket
            start, bucket = g.ts, []
        bucket.append(g)
    if bucket:
        yield bucket


def passes_floor(window: list[Observation]) -> bool:
    """Ucuz yerel taban: *ne zaman soracağını* belirler, *neyin önemli
    olduğunu* değil. Hareket sensörü kuralı, alarm kararı değildir."""
    for g in window:
        s = g.signals
        if s.person_count > 0 or s.vanished_tracks or s.gathering:
            return True
        if any(h >= FLOOR_VELOCITY for h in s.velocities.values()):
            return True
    return False


class DecisionLoop:
    def __init__(self, store: Store,
                 route: Callable[[list[Observation]], RouterDecision],
                 interpret: Callable[[list[Observation]], object],
                 synthesize: Callable[[list[Observation], object, str], Episode | None],
                 is_degraded: Callable[[], bool] = lambda: False) -> None:
        self.store = store
        self.route = route
        self.interpret = interpret
        self.synthesize = synthesize
        self.is_degraded = is_degraded
        self.deferred: list[list[Observation]] = []

    def _handoff(self, target: str, ts: float, reason: str, confidence: float) -> None:
        self.store.save_handoff(Handoff(ts=ts, source_agent="router",
                                      target_agent=target, reason=reason,
                                      confidence=confidence, payload_ref=f"window@{ts}"))

    def run(self, observations: list[Observation]) -> Iterator[Episode]:
        """Videonun zaman çizelgesinde ilerler. Yükseltme gerektiren her anda
        epizotu yield eder ve ORADA DURUR — çağıran taraf operatörle konuşup
        döngüyü devam ettirir. §3a tam olarak budur."""
        for window in windows(observations):
            ts = window[0].ts
            if not passes_floor(window):
                continue

            decision = self.route(window)
            self._handoff(TARGET.get(decision.decision, "perception"), ts,
                        decision.rationale, decision.confidence)

            if decision.decision == "ignore":
                continue

            interpretation = self.interpret(window) if decision.decision in (
                "inspect", "open_episode", "update_episode",
                "escalate") else None

            if decision.decision in ("open_episode", "update_episode", "close_episode"):
                self.synthesize(window, interpretation, decision.decision)

            elif decision.decision == "escalate":
                # Yükseltmenin tutunacağı bir epizot olmalı; yoksa risk
                # analizi hangi epizota yazacağını bilemez.
                episode = self.synthesize(window, interpretation, "open_episode")
                if episode is not None:
                    # Video bitmedi. Çağıran taraf burada operatörle konuşuyor.
                    yield episode

            # Görsel katman bozulmuşken atlanan pencereler kaybolmuyor.
            if interpretation is None and self.is_degraded():
                self.deferred.append(window)

        # Bağlantı döndüyse atlananları telafi et.
        yield from self.catch_up()

    def catch_up(self) -> Iterator[Episode]:
        """Bozulma sırasında atlanan pencereleri yeniden işler. Demo beat 6'nın
        'bağlantı gelince açığı kapatıyor' sözünü tutan yer burası."""
        if not self.deferred or self.is_degraded():
            return
        pending, self.deferred = self.deferred, []
        for window in pending:
            interpretation = self.interpret(window)
            if interpretation is None:
                self.deferred.append(window)
                continue
            self._handoff("synthesizer", window[0].ts, "telafi", 0.6)
            episode = self.synthesize(window, interpretation, "open_episode")
            if episode is not None:
                yield episode
```

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_loop.py -v
```
Beklenen: 10 passed

### 5. Commit

```bash
git add gozcu/loop.py tests/test_loop.py
git commit -m "feat: in-flight decision loop that pauses at escalation"
```

## Doğrulama

```bash
uv run pytest tests/test_loop.py -v
```
Beklenen: **10 passed**

## Çağıran taraf nasıl kullanacak (Görev 16 ve 17 için)

```python
for episode in loop.run(observations):
    nobetci.escalate(episode)      # operatör burada konuşuyor, döngü duruyor
    # operatör "devam" deyince for döngüsü kendiliğinden ilerliyor
```
