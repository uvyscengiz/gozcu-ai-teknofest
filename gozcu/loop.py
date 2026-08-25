"""Olay anında karar döngüsü.

Projenin en önemli mimari tercihi burada kod oluyor: sistem videoyu baştan
sona işleyip sonunda özet yazmıyor, **videonun kendi saatinde** karar veriyor.
Bunun gerçekten olabilmesi için döngünün duraklayabilmesi gerekiyor — bu
yüzden `run` bir generator: yükseltme anında `yield` ediyor, çağıran taraf
operatörle konuşuyor, `next()` döngüyü kaldığı yerden sürdürüyor.

Bütün geri çağrılar dışarıdan enjekte ediliyor; modül hiçbir ajan olmadan
test edilebiliyor.
"""

import math
from collections.abc import Callable, Iterator

import time

from gozcu import trace
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
#
# ## 25 Ağustos — bütçe aynı, NİŞAN değişti (Görev 16)
#
# Yukarıdaki kural boşluğu doldurdu ama bir şeyi çözmedi: HANGİ pencerenin
# bakılacağını bir sayaç seçiyordu, kanıt değil. Aynı klipte ölçüldü:
#
#     saniye başına kare farkı enerjisi  t=11–13 s'de zirve (9,34/9,09/9,13)
#     klip ortalaması                     3,75
#     pencere ortalamaları                W1 2,48 · W2 5,45 · W3 1,59
#
# Olay W2'de. Sayaç W1'i seçti. Tek pahalı bakış yanlış yere gitti ve koşu
# yine "Kayda değer olay tespit edilmedi." dedi. Bu enerjiyi hesaplamak yerel,
# modelsiz ve neredeyse bedava: bu makinede 896 piksel genişliğindeki
# karelerde 1,9 ms/kare, 23 karelik klibin tamamı 44 ms — aynı klipte tek bir
# görü çağrısı 3.493 ms sürüyor, yani triyajın tamamı o çağrının %1,3'ü.
#
# Bu yüzden `FORCED_SAMPLE_EVERY` artık bir PERİYOT değil bir BÜTÇE PAYDASI:
# pencerelerden `ceil(n / FORCED_SAMPLE_EVERY)` tanesi — en yüksek enerjili
# olanlar — görü kademesine gidiyor.
#
# Sayacın kapattığı ikinci delik de burada onarılıyor: sayaç model her
# çağrıldığında sıfırlanıyordu, yani tabandan geçen HAREKETLİ bir açılış
# penceresi kendisinden sonraki bütün örneklemeyi bastırıyordu. Ölçüldü:
# 10 saniye sonra sessizleşen 60 saniyelik bir klipte SIFIR zorunlu örnek.
# Top-K'da böyle bir sayaç yok; taban geçemeyen 5 pencere `ceil(5/6)` = 1
# çağrı hak ediyor ve o çağrı yapılıyor.
#
# ## 25 Ağustos — bütçe TABANDAN ayrıldı (görü nişanı ≠ algı tabanı)
#
# Yukarıdaki top-K yalnız **taban geçemeyen** pencereler arasında sıralama
# yapıyordu. Bu, iki ayrı kararın yanlışlıkla birbirine bağlanmasıydı:
#
#     taban          → bu pencereyi yönlendiriciye SORAYIM MI?
#     hareket enerji → pahalı BAKIŞI nereye harcayayım?
#
# İkincisi birincisinin artığı olarak yazılmıştı, yani tabandan GEÇEN ama
# yönlendiricinin `ignore` dediği bir pencereye hiçbir katman bakmıyordu.
# Ölçüldü (`forklift-compilation--N9bG-sOU6LE-k05.mp4`, forklift devrilmesi):
# izleme artık tespiti zenginleştirdiği için (`205052f`) 61 tespit 82'ye çıktı,
# taban deseni `++--++++`'ten `++++++++`'e döndü — ve tam da bu yüzden zorunlu
# örnek YOK OLDU: taban geçemeyen pencere kalmamıştı. Yönlendirici sekiz kez
# `ignore` dedi, 1 epizot (Yüksek, 00:30) 0'a düştü, 3 aksiyon 0'a. Algı
# katmanı DAHA İYİ gördükçe sistem DAHA KÖR oldu; bir bütçe kuralının bir
# taban kuralına yapışık olmasının bedeli budur.
#
# Bu yüzden sıralama artık koşunun BÜTÜN pencereleri üzerinde yapılıyor ve
# bütçe `ceil(n_windows / FORCED_SAMPLE_EVERY)`. `ceil(taban_geçemeyen / N)`
# de bir seçenekti ve reddedildi: k05'te taban_geçemeyen = 0, yani bütçe 0 —
# tam onarılmak istenen arıza.
#
# ## Maliyet — pencere başına EN FAZLA bir görü çağrısı (Yönerge 3)
#
# 10 dakikalık video, 10 s pencere → n = 60. `p` tabandan geçen, `f` geçemeyen
# pencere sayısı (`p + f = 60`).
#
#     ÖNCE:  görü ≤ p            (yönlendirici görü isteyen bir karar verirse)
#                 + ceil(f / 6)  (zorunlu örnek)
#            en kötü hâl: f = 0 → 60 + 0 = 60 çağrı
#     SONRA: görü ≤ p + |seçilenler ∩ (yönlendirici görü istemeyenler)|
#            seçim pencere başına TEK çağrıyı garantiliyor (aşağıya bak)
#            en kötü hâl: hâlâ 60 çağrı — pencere başına bir taneden fazlası
#            yapısal olarak imkânsız
#
# Yani üst sınır DEĞİŞMEDİ: her iki kuralda da 10 dakikalık bir video en kötü
# hâlde 60 görü çağrısı eder. Değişen şey belirli bir koşunun ortalaması:
# yönlendiricinin her yerde "sakin" dediği bir koşu ÖNCE 0 çağrı ödüyordu,
# ŞİMDİ en fazla `ceil(60 / 6)` = 10 ödüyor. Bu artış saklanmıyor — k05'te
# kaybedilen epizodu geri getiren şey tam olarak o 10 çağrının biri.
#
# Pencere başına tek çağrı nasıl garanti ediliyor: seçilmiş bir pencere tabandan
# geçiyorsa önce yönlendiriciye gidiyor (davranış aynı). Yönlendirici görü
# isteyen bir karar verdiyse bakış zaten yapılmış olur ve bütçe orada harcanır;
# İKİNCİ bir çağrı yapılmaz. Yalnız `ignore` dalında — yani hiç kimsenin
# bakmayacağı dalda — ayrılmış bakış harcanır (`_routed`, `vision_budgeted`).
# `close_episode` bilerek dışarıda: yönlendirici o pencereyle bir epizodu
# kapatmışken aynı pencereden yeni bir epizot açmak aynı olayı iki kez sayardı.
#
# **Bu numaranın sınırı dürüstçe yazılsın: top-K bütün videonun önceden
# bilinmesine dayanıyor.** `run()` gözlemlerin tamamını baştan alıyor, o
# yüzden enerjileri sıralayıp en yükseklerini seçebiliyoruz. Gerçek bir canlı
# yayında böyle bir liste yok: orada kayan bir eşik (ör. son N pencerenin
# enerji dağılımına göre uyarlanan bir kesme) ya da bir rezervuar örneklemesi
# gerekirdi. Bu tasarım genelleşmiyor ve genelleşiyormuş gibi yazılmıyor.
#
# Enerji verisi yoksa — `motion_for` enjekte edilmemişse ya da hiçbir pencere
# için sayı üretemiyorsa — eski periyodik nöbet aynen devrede kalıyor
# (`_periodic_indices`). Silinmedi: triyaj katmanı koşunun sigortası değil,
# nişancısı.
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

#: Tabandan GEÇEN ama yönlendiricinin `ignore` dediği, yüksek enerjili bir
#: pencereye harcanan bakışın gerekçesi. Ayrı bir sabit, çünkü defter olanı
#: yazmalı: burada taban geçildi ve yönlendirici gerçekten karar verdi —
#: "taban geçilemedi" demek düpedüz yanlış olurdu. Önek aynı: ölçüm (Görev 15)
#: bunu da tabandan geçmiş gerçek bir karardan değil, döngünün kendi
#: kuralından gelen bir yoklama olarak sayıyor.
ROUTED_FORCED_REASON = (f"{FORCED_REASON_PREFIX} yönlendirici sakin dedi; "
                        "yüksek enerjili pencere yine de görü kademesine "
                        "gönderildi")

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
                 is_degraded: Callable[[], bool] = lambda: False,
                 motion_for: Callable[[list[Observation]], float | None]
                 | None = None) -> None:
        """`is_degraded` bağlanırken `lambda: gw.is_degraded("vlm")` yazılacak.

        Çıplak `gw.is_degraded` "**herhangi bir** kademe bozuk" demek;
        `rerank`'ın 400'ü ise beklenen davranış, kesinti değil. Onu da sayan
        bir bayrak her pencereyi sonsuza dek erteletir ve `catch_up()` hiç
        çalışmaz.

        `motion_for(window)` pencerenin yerel hareket enerjisini veriyor
        (`gozcu.motion.build_motion_for`); model çağırmıyor, ağa çıkmıyor.
        `None` — ya enjekte edilmemiş, ya o pencere için kanıt yok — eski
        periyodik nöbete düşmek demek.
        """
        self.store = store
        self.route = route
        self.interpret = interpret
        self.synthesize = synthesize
        self.is_degraded = is_degraded
        self.motion_for = motion_for
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

    def _routed(self, window: list[Observation],
                vision_budgeted: bool = False) -> Iterator[LoopEvent]:
        """Tabandan geçen pencerenin yolu: önce yönlendirici, sonra gerekirse
        görü kademesi. Yönlendiricinin kararı her şeyi sürüyor — bu dal Görev
        05'ten beri aynı.

        `vision_budgeted`, bu pencerenin hareket enerjisiyle görü bütçesine
        seçildiğini söyler. Kararı DEĞİŞTİRMEZ; yalnız `ignore` dalında —
        kimsenin bakmayacağı tek dalda — ayrılmış bakışı harcar. Karar görü
        isteyen bir şeyse (`NEEDS_VISION`) bakış zaten aşağıda yapılıyor ve
        bütçe orada harcanmış sayılır: **pencere başına ikinci bir görü
        çağrısı yok.**
        """
        ts = window[0].ts
        decision = self.route(window)
        self._handoff(TARGET.get(decision.decision, "perception"), ts,
                      decision.rationale, decision.confidence)

        if decision.decision == "ignore":
            if vision_budgeted:
                # Yönlendirici sinyal özetine baktı ve "sakin" dedi; enerji
                # tersini söylüyor ve özet bir devrilmeyi taşıyamaz. Ölçülen
                # k05 arızası tam burada yaşandı: sekiz `ignore`, sıfır bakış.
                self._forced_sample(window, reason=ROUTED_FORCED_REASON)
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

    def _forced_sample(self, window: list[Observation],
                       reason: str = FORCED_REASON) -> None:
        """Zorunlu örnek: pencere doğrudan görü kademesine gider.

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

        **İki çağıranı var.** Tabandan geçemeyen seçilmiş pencere (yukarıdaki
        gerekçe) ve tabandan geçmiş ama yönlendiricinin `ignore` dediği
        seçilmiş pencere (`_routed`, `ROUTED_FORCED_REASON`). İkisinde de
        pencereye bakacak başka hiçbir katman kalmamıştır; gerekçe metni
        hangisi olduğunu deftere yazar.

        **Yükseltme yield EDİLMİYOR.** Operatörü çağırmak yönlendiricinin ya
        da süpervizörün kararı; burada verilecek böyle bir karar yok. Epizot
        açılır, riski `assess_risk` biçer (kapanışta ya da koşu sonundaki
        süpürmede) ve şartnamenin dört anahtarı dolar — sessizlik biter, ama
        her sıradan pencere canlı krize dönüşmez.
        """
        ts = window[0].ts
        self._handoff("interpreter", ts, reason, FORCED_CONFIDENCE,
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

    @staticmethod
    def _budget(window_count: int) -> int:
        """Koşunun görü bütçesi: `ceil(n_windows / FORCED_SAMPLE_EVERY)`.

        Payda TABAN geçemeyen pencere sayısı değil, TOPLAM pencere sayısı —
        bütçe bir algı kararına değil videonun uzunluğuna bağlı. `ceil(taban
        geçemeyen / N)` de denenebilirdi ve reddedildi: k05'te taban her
        pencerede geçiyor, yani o formül bütçeyi sıfırlıyor ve onarılmak
        istenen arızayı aynen üretiyor (bkz. dosya başındaki maliyet notu).

        Üst sınır yine de büyümüyor, çünkü seçilmiş bir pencere yönlendirici
        zaten bakmışsa ikinci kez bakmıyor: pencere başına en fazla bir görü
        çağrısı.
        """
        return math.ceil(window_count / FORCED_SAMPLE_EVERY)

    @staticmethod
    def _periodic_indices(failing: list[bool]) -> set[int]:
        """Eski kural, olduğu gibi: her `FORCED_SAMPLE_EVERY`'inci durgun
        pencere, sayaç `_PRIMED` ile dolu başlayarak ve tabandan geçen her
        pencerede sıfırlanarak.

        Enerji verisi olmadığında düşülen yer burası — bu dal silinmedi.
        """
        chosen, skipped = set(), _PRIMED
        for index, floor_failed in enumerate(failing):
            if not floor_failed:
                skipped = 0
                continue
            skipped += 1
            if skipped < FORCED_SAMPLE_EVERY:
                continue
            skipped = 0
            chosen.add(index)
        return chosen

    def _energy_indices(self,
                        plan: list[list[Observation]]) -> set[int] | None:
        """Koşunun BÜTÜN pencereleri arasından en yüksek enerjili `K` tanesi.

        Taban buraya hiç girmiyor ve bu kasıtlı: taban "soralım mı" sorusunun
        cevabı, enerji "nereye bakalım" sorusununki. İkisi bir kez birbirine
        yapıştı ve `205052f` algı katmanını iyileştirdiğinde k05'in epizodu
        buharlaştı — taban geçemeyen pencere kalmayınca bakılacak pencere de
        kalmamıştı.

        Kanıtsız pencere (enerjisi `None`) sıralamaya hiç girmiyor: `None`
        "burada kanıt yok" demek, "sıfır hareket" değil, ve bütçeyi kör bir
        pencereye harcamanın anlamı yok. Bütün pencereler kanıtsızsa `None`
        dönüyor ve çağıran taraf periyodik nöbete düşüyor.

        Bütçe `len(plan)` üzerinden hesaplanıyor — kanıtlı pencere sayısı
        üzerinden değil — yoksa okunamayan kareler bütçeyi sessizce kısardı.

        Eşitlikte küçük indeks kazanıyor: sıralama deterministik olmalı, yoksa
        aynı video iki koşuda farklı pencereye bakar ve ölçüm karşılaştırılamaz
        hâle gelir.
        """
        energies: dict[int, float] = {}
        for index, window in enumerate(plan):
            try:
                energy = self.motion_for(window)
            except Exception:       # noqa: BLE001 — triyaj koşuyu düşürmez
                return None
            if energy is not None:
                energies[index] = energy
        if not energies:
            return None
        ranked = sorted(energies, key=lambda index: (-energies[index], index))
        return set(ranked[:self._budget(len(plan))])

    def _forced_indices(self, plan: list[list[Observation]],
                        failing: list[bool]) -> set[int]:
        """Zorunlu görü çağrısı alacak pencerelerin indeksleri.

        Döngüden ÖNCE hesaplanıyor, çünkü top-K sıralama gerektiriyor ve
        sıralama bütün pencereleri görmeyi gerektiriyor. `run()` bundan sonra
        eskisi gibi baştan sona ilerliyor — yield sırası videonun zaman
        çizelgesi, seçim sırası değil.

        Enerji dalı bütün pencerelere bakıyor; periyodik yedek ise eskisi gibi
        yalnız taban geçemeyenlere. Yedek bilerek genişletilmedi: enerji yoksa
        "hangi pencere ilginç" sorusunun cevabı da yok ve bir sayacın tabandan
        geçmiş pencerelere de bakması, hiçbir kanıta dayanmadan maliyeti
        artırmak olurdu.
        """
        if self.motion_for is not None:
            chosen = self._energy_indices(plan)
            if chosen is not None:
                return chosen
        return self._periodic_indices(failing)

    def run(self, observations: list[Observation]) -> Iterator[LoopEvent]:
        """Videonun zaman çizelgesinde ilerler. Yükseltme gerektiren her anda
        `LoopEvent` yield eder ve ORADA DURUR — çağıran taraf operatörle
        konuşup döngüyü devam ettirir. §3a tam olarak budur.

        Canlı yükseltmeler `late=False`; kesinti telafisinden gelen her şey
        `late=True` ile işaretlenir.

        İki ayrı yol var ve ayrımı taban yapıyor:

        - **Tabandan geçen pencere** eski yolunda: önce yönlendirici, görü
          kademesi ancak karar gerektiriyorsa. Kararı hâlâ yönlendirici
          veriyor. Tek fark: pencere görü bütçesine seçildiyse ve karar
          `ignore` ise, ayrılmış bakış orada harcanır — yoksa yüksek enerjili
          o pencereye hiçbir katman bakmamış olurdu.
        - **Tabandan geçemeyen pencere** yalnız bütçeye seçilmişse doğrudan
          görü kademesine gider (`_forced_sample`); yönlendirici atlanır,
          çünkü boş bir sinyal özetinde okuyacağı hiçbir şey yok.

        Bütçe (`ceil(n / FORCED_SAMPLE_EVERY)` pencere) tabandan bağımsız,
        koşunun BÜTÜN pencereleri arasında hareket enerjisine göre dağıtılır.

        Seçim döngüden önce yapılıyor (`_forced_indices`) — top-K sıralama
        istiyor — ama **işleme sırası değişmiyor**: pencereler baştan sona,
        videonun kendi saatinde geziliyor ve yükseltmeler geldikleri anda
        yield ediliyor. "Kararlar olay anında verilir" değişmezi burada
        duruyor; seçim bir ön hesap, akış değil.
        """
        plan = list(windows(observations))
        failing = [not passes_floor(window) for window in plan]
        forced = self._forced_indices(plan, failing)

        trace.event("döngü.plan",
                    f"{len(plan)} pencere, {sum(failing)} tabandan geçemiyor, "
                    f"{len(forced)} görü bütçesinde")

        for index, window in enumerate(plan):
            span = (f"{window[0].ts:.0f}–{window[-1].ts:.0f}s"
                    if window else "boş")
            # Ne GÖRÜLDÜĞÜ de kayda giriyor: "kaçıncı pencere" tek başına
            # katmanın o pencerede bir şey bulup bulmadığını söylemiyor.
            peak = max((o.signals.person_count for o in window), default=0)
            boxes = sum(len(o.detections) for o in window)
            labels = sorted({d.label for o in window for d in o.detections})
            span = (f"{span} kişi≤{peak} kutu={boxes} "
                    f"[{','.join(labels) or 'tespit yok'}]")
            if failing[index]:
                if index in forced:
                    with trace.step(f"pencere[{index + 1}/{len(plan)}]",
                                    f"{span} taban=HAYIR görü=zorunlu"):
                        self._forced_sample(window)
                else:
                    trace.event(f"pencere[{index + 1}/{len(plan)}]",
                                f"{span} taban=HAYIR atlandı")
                continue
            # `trace.step()` BURADA kullanılamaz: bağlam yöneticisi bir
            # `yield from`'u kapsarsa ve tüketici generator'ı yarıda bırakırsa
            # `__exit__` çöp toplama anında, rastgele bir noktada koşar ve
            # girinti sayacını bozar. Başlangıç/bitiş olayları yeterli —
            # asılma zaten `gw.ask` içinde ve orada kalp atışı var.
            started = time.monotonic()
            trace.event(f"pencere[{index + 1}/{len(plan)}]",
                        f"{span} taban=EVET "
                        f"görü={'bütçede' if index in forced else 'gerekirse'}")
            yield from self._routed(window, vision_budgeted=index in forced)
            trace.event(f"pencere[{index + 1}/{len(plan)}]",
                        f"bitti, {(time.monotonic() - started) * 1000:.0f} ms")

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
