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
# İlk onarım bu pencereleri yönlendiriciye gönderiyordu. Canlı koşu
# (24 Ağustos, aynı klip) onun da yetmediğini ÖLÇTÜ: 1 yönlendirici çağrısı,
# güven 0,90, 0 epizot. Sebep basit — yönlendirici görüntü görmez, yalnız
# sinyal özetini okur; sıfır tespitte o özet boştur ve modelin verebileceği
# tek dürüst cevap "sakin"dir. Boru hattı sessizce kör olmaktan ölçülebilir
# şekilde kör olmaya geçti, o kadar.
#
# Bu yüzden tabandan geçemeyen pencerelerin her N'incisi artık yönlendiriciyi
# ATLAYIP doğrudan görü kademesine gidiyor (bkz. `DecisionLoop._forced_sample`).
# N=6 kasıtlı: 10 dakikalık bir video 10 s'lik pencerelerle 60 pencere eder,
# en kötü hâlde ~10 ek çağrı.
#
# ## Maliyet — rakamlar burada dursun
#
# Zorunlu pencere başına BİR görü çağrısı: 10 dakikalık videoda ~10 çağrı,
# canlı ölçümde ~11 s/çağrı, yani ~110 s ek süre. Ucuz değil ve öyleymiş gibi
# yazılmıyor. Karşılığında alınan şey şu: **YOLO'nun göremediği bir olayı
# yakalayan tek yol budur.** `YOLO_CLASSES` = `person,vehicle`, algı katmanı
# yarışma boyunca donuk ve bu veri kümesinde `data/clips/yangin` etiketli bir
# kategori var — yangının ne sınıfı, ne izi, ne hızı vardır; yalnız görünür.
# Zorunlu pencere görü kademesine gitmezse o klipler sessiz kalır.
#
# Buradaki tasarrufu "optimize etmek" isteyen biri şunu bilerek yapsın: bu
# yola bir yönlendirici çağrısı EKLEMEK de (önce sor, sonra gerekiyorsa bak)
# maliyeti azaltmaz, artırır — boş özete sorulan soru her seferinde "sakin"
# döner, yani bir çağrı ödenir ve hiçbir şey öğrenilmez.
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

#: Zorunlu devrin tam gerekçesi. Modelden gelen bir gerekçe YOK: bu devir bir
#: model kararı değil, döngünün kendi kuralı.
FORCED_REASON = (f"{FORCED_REASON_PREFIX} taban geçilemedi; pencere "
                 "yönlendirici atlanarak görü kademesine gönderildi")

#: Zorunlu devrin güveni. 1.0 çünkü kural deterministik — döngü bu deviri
#: yapmak konusunda kesin. Bilerek 0.0 DEĞİL: bu kod tabanında sıfır güven
#: "kesinti" demek (`route()._fallback`, `benchmark/kpi.py`) ve zorunlu bir
#: örnek arıza değil, planlı bir yoklamadır.
FORCED_CONFIDENCE = 1.0

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
                 confidence: float, source: str = "router") -> None:
        """Deftere bir devir yazar.

        `source` varsayılan olarak yönlendirici, çünkü devirlerin çoğu onun
        kararı. Zorunlu örnekleme onu `"perception"` ile eziyor: o pencere
        yönlendiriciye hiç uğramadı ve defterin olmayan bir kararı iddia
        etmemesi gerekiyor. Ölçüm de buna dayanıyor — `benchmark/kpi.py`
        yönlendirici dağılımını `source_agent == "router"` ile ayıklıyor, yani
        zorunlu devirler manşet oranları kirletmeden defterde durabiliyor.
        """
        self.store.save_handoff(Handoff(ts=ts, source_agent=source,
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

    def _routed(self, window: list[Observation]) -> Iterator[LoopEvent]:
        """Tabandan geçen pencerenin yolu: önce yönlendirici, sonra gerekirse
        görü kademesi. Bu dal Görev 05'ten beri aynı — zorunlu örnekleme
        buraya dokunmuyor."""
        ts = window[0].ts
        decision = self.route(window)
        self._handoff(TARGET.get(decision.decision, "perception"), ts,
                      decision.rationale, decision.confidence)

        if decision.decision == "ignore":
            return

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

    def _forced_sample(self, window: list[Observation]) -> None:
        """Zorunlu periyodik örnek: pencere doğrudan görü kademesine gider.

        **Yönlendirici bilerek atlanıyor.** Yönlendirici görüntü görmez;
        elindeki tek şey sinyal özetidir ve sıfır tespitte o özet boştur.
        Ölçülen sonuç bu: raf çökmesi klibinde zorunlu çağrı yönlendiriciye
        gitti, model 0,90 güvenle "sakin" dedi ve görü kademesi hiç
        çalışmadı — doğru cevaptı, çünkü soru okunacak bir kanıt taşımıyordu.
        Kanıtı yalnız VLM görebiliyor, o hâlde soru ona sorulur.

        **Epizot yorumla açılıyor, ikinci bir yönlendirici çağrısıyla değil.**
        İki seçenek vardı: (a) yorumu elde ettikten sonra yönlendiriciye geri
        dönüp karar sormak, (b) doğrudan sentezleyiciye gitmek. (b) seçildi,
        iki sebeple. Birincisi maliyet: (a) zorunlu pencereyi bir görü + bir
        yönlendirici çağrısına çıkarır, oysa sözleşme pencere başına TEK
        çağrı. İkincisi dürüstlük: yönlendiricinin girdisi hâlâ o boş sinyal
        özeti olurdu — yorumu okumaz — yani ikinci çağrı da aynı "sakin"i
        döndürür ve yeni öğrenilen şeyi çöpe atardı.

        Kayda değerlik ölçütü `notable_event`: yorumlayıcının promptu "dikkat
        çekici bir şey yoksa null olsun" diyor ve yer tutucu metinler orada
        temizleniyor. Dolu ise epizot açılır (açık epizot varsa `_resolve`
        kaynaşmaya indirir), boşsa hiçbir şey uydurulmaz.

        **Yükseltme yield EDİLMİYOR.** Operatörü çağırmak yönlendiricinin ya
        da süpervizörün kararı; burada verilecek böyle bir karar yok. Epizot
        açılır, riski `assess_risk` biçer (kapanışta ya da koşu sonundaki
        süpürmede) ve şartnamenin dört anahtarı dolar — sessizlik biter, ama
        her sıradan pencere canlı krize dönüşmez.
        """
        ts = window[0].ts
        self._handoff("interpreter", ts, FORCED_REASON, FORCED_CONFIDENCE,
                      source="perception")

        interpretation = self.interpret(window)
        if interpretation is None:
            # `None`'ın dört anlamı var (bkz. `interpret`) ve yalnız biri
            # kesinti. Diğerlerinde pencere sessizce atlanır: ertelemek onu
            # her `catch_up`'ta yeniden VLM'e sordurur ve hiç kurtulmaz.
            if self.is_degraded():
                self.deferred.append(window)
            return

        if interpretation.notable_event:
            self.synthesize(window, interpretation,
                            self._resolve("open_episode"))

    def run(self, observations: list[Observation]) -> Iterator[LoopEvent]:
        """Videonun zaman çizelgesinde ilerler. Yükseltme gerektiren her anda
        `LoopEvent` yield eder ve ORADA DURUR — çağıran taraf operatörle
        konuşup döngüyü devam ettirir. §3a tam olarak budur.

        Canlı yükseltmeler `late=False`; kesinti telafisinden gelen her şey
        `late=True` ile işaretlenir.

        İki ayrı yol var ve ayrımı taban yapıyor:

        - **Tabandan geçen pencere** eski yolunda: önce yönlendirici, görü
          kademesi ancak karar gerektiriyorsa. Davranışı değişmedi.
        - **Tabandan geçemeyen pencere** her `FORCED_SAMPLE_EVERY`'de bir
          doğrudan görü kademesine gider (`_forced_sample`); yönlendirici
          atlanır, çünkü boş bir sinyal özetinde okuyacağı hiçbir şey yok.

        Sayaç model HER çağrıldığında sıfırlanıyor — tabandan geçen pencereler
        de sayılıyor — ve koşuya `_PRIMED` ile dolu başlıyor.
        """
        skipped = _PRIMED
        for window in windows(observations):
            if not passes_floor(window):
                skipped += 1
                if skipped < FORCED_SAMPLE_EVERY:
                    continue
                skipped = 0
                self._forced_sample(window)
                continue
            skipped = 0
            yield from self._routed(window)

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
