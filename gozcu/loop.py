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

# Taban *ne zaman soracağını* belirlemek için tasarlandı; sıfır tespitte
# sessizce *hiç sorma* diyor. Ölçülen arıza: raf çökmesi klibinde
# (`forklift-compilation--N9bG-sOU6LE-k03`, "depoda raf/yük çökmesi") algı
# katmanı 23 gözlem üretti, hiçbirinde tespit yok — `YOLO_CLASSES` yalnız
# `person,vehicle` ve çöken bir raf ikisi de değil. Üç pencerenin üçü de
# `passes_floor()`'dan geçemedi, `route()` hiç çağrılmadı, epizot açılmadı ve
# şartnamenin dört anahtarı boş döndü. Algı katmanı donuk, genişletilemiyor.
#
# Bu yüzden tabandan geçemeyen pencerelerin her N'incisi yine yönlendiriciye
# gönderiliyor: karar hâlâ modelin, taban yalnızca sıklığı seyreltiyor.
# N=6 kasıtlı: 10 dakikalık bir video 10 s'lik pencerelerle 60 pencere eder,
# en kötü hâlde ~10 ek çağrı — hepsi en ucuz 8B `router` kademesinde — ve
# yönlendiricinin ~%90 maliyet filtrelemesi iddiası ayakta kalır.
FORCED_SAMPLE_EVERY = 6

# Sayaç koşuya **dolu** başlıyor: ilk pencere tabandan geçemezse hemen
# soruluyor. Yine ölçümden gelen bir zorunluluk — o klip 22,9 saniye, yani
# yalnız üç pencere. Sayaç sıfırdan başlasa altıncı pencere hiç gelmez ve
# arızayı ortaya çıkaran klip aynen sessiz kalırdı. Kural şöyle okunur:
# koşunun başlangıcı da bir sessizliktir ve hiçbir koşu tek bir soru bile
# sormadan bitmemeli.
_PRIMED = FORCED_SAMPLE_EVERY - 1

#: Zorunlu örneklemeyle gelen devrin gerekçesine eklenen önek. Ölçüm (Görev
#: 15) böylece zorunlu bir çağrıyı tabandan geçmiş gerçek bir karardan ayırt
#: edebiliyor — `Handoff` zaten `reason` taşıyor, `gozcu/models.py` değişmiyor.
FORCED_REASON_PREFIX = "[periyodik]"

#: `Handoff.reason`'ın şema sınırı. Önek eklendikten sonra taşan gerekçe
#: doğrulamayı patlatır ve zorunlu çağrı bütün koşuyu düşürürdü.
MAX_HANDOFF_REASON = 200

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
                                        target_agent=target,
                                        reason=reason[:MAX_HANDOFF_REASON],
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

        Tabandan geçemeyen pencereler tamamen atılmıyor: her
        `FORCED_SAMPLE_EVERY` pencerede bir yine yönlendiriciye gidiyor
        (bkz. sabitin başındaki ölçüm notu). Sayaç yönlendirici HER
        çağrıldığında sıfırlanıyor — tabandan geçen pencereler de sayılıyor —
        koşuya `_PRIMED` ile dolu başlıyor ve zorunlu pencere bu noktadan
        sonra hiçbir özel dala girmiyor.
        """
        skipped = _PRIMED
        for window in windows(observations):
            ts = window[0].ts
            forced = False
            if not passes_floor(window):
                skipped += 1
                if skipped < FORCED_SAMPLE_EVERY:
                    continue
                forced = True
            skipped = 0

            decision = self.route(window)
            reason = (f"{FORCED_REASON_PREFIX} {decision.rationale}" if forced
                      else decision.rationale)
            self._handoff(TARGET.get(decision.decision, "perception"), ts,
                          reason, decision.confidence)

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
