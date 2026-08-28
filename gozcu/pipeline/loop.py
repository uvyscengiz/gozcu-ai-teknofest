"""Olay anında karar döngüsü.

Projenin en önemli mimari tercihi burada kod oluyor: sistem videoyu baştan
sona işleyip sonunda özet yazmıyor, **videonun kendi saatinde** karar veriyor.
Bunun gerçekten olabilmesi için döngünün duraklayabilmesi gerekiyor — bu
yüzden `run` bir generator: yükseltme anında `yield` ediyor, çağıran taraf
operatörle konuşuyor, `next()` döngüyü kaldığı yerden sürdürüyor.

Bütün geri çağrılar dışarıdan enjekte ediliyor; modül hiçbir ajan olmadan
test edilebiliyor.
"""

import inspect
import math
from collections.abc import Callable, Iterator

import time

from gozcu.output import trace
from gozcu.core.models import (SEVERITY_LEVELS, Episode, Handoff, Interpretation,
                          LoopEvent, Observation, RouterDecision, WindowRecord)
from gozcu.core.store import Store

WINDOW_S = 10.0

#: `passes_floor()`'un hız kapısı — kare GENİŞLİĞİ/saniye biriminde (26
#: Ağustos, bkz. `gozcu.signals`'ın modül başı notu). Eskiden 1.0 PİKSEL/
#: saniyeydi ve ölçülen k04 verisinde bu, "hemen hemen her izlenen hareketi
#: geçirmek" anlamına geliyordu: genel medyan 7 px/s, yani eşik medyanın
#: ~%14'ü — eşiğin altında kalan hız neredeyse yoktu. Aynı esnekliği yeni
#: birimde korumak için aynı oran uygulandı: normalize medyan 0.008 (p90
#: 0.036, tepe 0.604), medyanın ~%14'ü ≈ 0.001. Bu taban zaten öncelikle
#: `person_count > 0` ile geçiliyor — hız kapısı kimliksiz kutu bile
#: izlenemediğinde tek başına devreye giriyor, o yüzden burada kritik olan
#: eski davranışı KORUMAK, yeni bir süzgeç icat etmek değil.
FLOOR_VELOCITY = 0.001

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

#: Açık bir epizot VARKEN yönlendiricinin (ya da kesintide her zaman
#: `ignore` döndüren `orchestrator._fallback`'ın) "ignore" demesine güvenilmeyen
#: dalın gerekçesi (26 Ağustos, ignore artık gerçek bir yol — bkz.
#: `gozcu.agents.orchestrator.SYSTEM_PROMPT`'un K5'i). Ayrı sabit, çünkü burada da
#: "taban geçilemedi" yanlış olurdu: pencere tabandan geçti, yönlendiriciye
#: gerçekten gidildi. `ROUTED_FORCED_REASON`'dan ayrı tutuluyor çünkü bu dal
#: `vision_budgeted`'dan BAĞIMSIZ tetikleniyor — açık bir olayın ortasında
#: bir anı kaybetmenin bedeli, o pencerenin enerji bütçesine seçilip
#: seçilmediğinden daha büyük.
OPEN_EPISODE_FORCED_REASON = (f"{FORCED_REASON_PREFIX} açık olay var; "
                              "yönlendirici sakin dedi ama pencere yine de "
                              "görü kademesine gönderildi")

#: Zorunlu devrin güveni. 1.0 çünkü kural deterministik — döngü bu deviri
#: yapmak konusunda kesin. Bilerek 0.0 DEĞİL: bu kod tabanında sıfır güven
#: "kesinti" demek (`route()._fallback`, `benchmark/kpi.py`) ve zorunlu bir
#: örnek arıza değil, planlı bir yoklamadır.
FORCED_CONFIDENCE = 1.0

#: `Handoff.reason`'ın şema sınırı. Önek eklendikten sonra taşan gerekçe
#: doğrulamayı patlatır ve zorunlu çağrı bütün koşuyu düşürürdü.
MAX_HANDOFF_REASON = 200

TARGET = {"inspect": "interpreter",
          "open_episode": "anomaly_analyst",
          "update_episode": "anomaly_analyst",
          "close_episode": "anomaly_analyst",
          "escalate": "supervisor"}

# Görü katmanına gerçekten soru soran kararlar. `close_episode` bilerek yok:
# kapanış penceresi yorumlanmıyor, dolayısıyla oradaki `None` bir kesinti
# kanıtı değil ve o pencere asla ertelenmemeli.
NEEDS_VISION = ("inspect", "open_episode", "update_episode", "escalate")

#: Sentezleyicinin ön riski bu seviyelerdeyse görü kademesinin gördüğü şey
#: operatöre ANINDA taşınıyor. Süpervizör de aynı eşiği kullanıyor
#: (`supervisor.escalate`'in `critical` bayrağı).
ESCALATING_RISKS = ("Yüksek", "Kritik")

#: Görü kademesinin biçtiği `severity` üçlüsünden (`gozcu.models.
#: SEVERITY_LEVELS`) "gerçekten bir şey OLDU" değeri — tek kaynak burası,
#: elle yeniden yazılmıyor (bkz. `gozcu.agents.interpreter`'ın aynı sabitten
#: okuyan promptu; bir prompt/şema ayrışması bu projeyi bir kez sessizce
#: öldürdü, decision-log).
EVENT_SEVERITY = SEVERITY_LEVELS[2]


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


def window_record(window: list[Observation], index: int, total: int,
                  floor_passed: bool, vision_budgeted: bool,
                  outcome: str) -> WindowRecord:
    """Pencerenin algı özeti — iz satırı da bu kayıttan yazılıyor.

    Toplama TEK yerde duruyor: `trace` satırı ile depo kaydı ayrışırsa ekran
    ile kayıt farklı şeyler söyler ve hangisinin doğru olduğu anlaşılamaz.
    """
    return WindowRecord(
        ts=window[0].ts, end_ts=window[-1].ts, index=index, total=total,
        frames=len(window),
        person_peak=max((o.signals.person_count for o in window), default=0),
        detections=sum(len(o.detections) for o in window),
        labels=sorted({d.label for o in window for d in o.detections}),
        floor_passed=floor_passed, vision_budgeted=vision_budgeted,
        outcome=outcome)


def window_span(record: WindowRecord) -> str:
    """İz satırının metni — `window_record`'dan türetiliyor, elle değil."""
    return (f"{record.ts:.0f}–{record.end_ts:.0f}s kişi≤{record.person_peak} "
            f"kutu={record.detections} "
            f"[{','.join(record.labels) or 'tespit yok'}]")


def _route_accepts_energy(route: Callable) -> bool:
    """`route`, pencerenin hareket enerjisini ikinci konumsal argüman olarak
    kabul ediyor mu.

    Geriye dönük uyumluluk buna dayanıyor: onlarca test hâlâ tek argümanlı
    `lambda window: RouterDecision(...)` şeklinde sahte bir yönlendirici
    veriyor. Enerjiyi HER ZAMAN geçmek bunların hepsini `TypeError`'a
    düşürürdü — `route()`'un imzasını gerçek enerji verisiyle genişletme
    hakkı, testin arayüzünü kırma bedeliyle satın alınmıyor. İmza bir kez,
    kurulumda okunuyor; her pencerede yeniden `inspect` etmek gereksiz.
    """
    try:
        params = list(inspect.signature(route).parameters.values())
    except (TypeError, ValueError):
        return False
    positional = [p for p in params
                 if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    return len(positional) >= 2


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
                 route: Callable[[list[Observation]], RouterDecision]
                 | Callable[[list[Observation], float | None], RouterDecision],
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
        periyodik nöbete düşmek demek. Aynı enerji artık `route`'a da
        geçiyor (26 Ağustos): `route` ikinci bir konumsal argüman
        kabul ediyorsa (`_route_accepts_energy`) `route(window, energy)`
        çağrılıyor, aksi hâlde eskisi gibi `route(window)` — geriye dönük
        uyumluluk için, bkz. `_route_accepts_energy`.
        """
        self.store = store
        self.route = route
        self._route_wants_energy = _route_accepts_energy(route)
        self.interpret = interpret
        self.synthesize = synthesize
        self.is_degraded = is_degraded
        self.motion_for = motion_for
        self.deferred: list[list[Observation]] = []

    def _handoff(self, target: str, ts: float, reason: str,
                 confidence: float, source: str = "orchestrator") -> None:
        """Deftere bir devir yazar.

        `source` varsayılan olarak yönlendirici, çünkü devirlerin çoğu onun
        kararı. Zorunlu örnekleme onu `"perception"` ile eziyor: o pencere
        yönlendiriciye hiç uğramadı ve defterin olmayan bir kararı iddia
        etmemesi gerekiyor. Ölçüm de buna dayanıyor — `benchmark/kpi.py`
        yönlendirici dağılımını `source_agent == "orchestrator"` ile ayıklıyor, yani
        zorunlu devirler manşet oranları kirletmeden defterde durabiliyor.
        """
        self.store.save_handoff(Handoff(ts=ts, source_agent=source,
                                        target_agent=target,
                                        reason=reason[:MAX_HANDOFF_REASON],
                                        confidence=confidence,
                                        payload_ref=f"window@{ts}"))

    def _may_open(self, interpretation: Interpretation | None) -> bool:
        """Bir epizot YENİ AÇILABİLİR mi karar verir — kaynaşmayı DEĞİL.

        Epizot doğurabilecek HER yol buradan geçer: `_routed` (inspect,
        open_episode/update_episode, escalate), `_forced_sample` ve
        `catch_up`. Ölçülen arıza (k04, 98.8 s forklift kazası klibi):
        epizot 00:00'da, park hâlindeki bir kamyonun yanından geçen biri
        yüzünden açıldı ve TEK açık epizot değişmezi yüzünden kazanın
        gerçekleştiği 40-50 s'yi de yuttu — teslim edilen özet "00:00
        tarihinde ... kamyon tamponuna çarptı" oldu, oysa 00:00'da hiçbir
        şey olmuyordu. Taban her kişi içeren pencereyi geçiriyor, yönlendirici
        kuralları her pencerede tetikleniyor; görüntüyü gerçekten gören TEK
        katman görü kademesi ve onun tek dereceli `notable_event` alanı
        "fabrika kamerası için ilginç" ile "kayda değer" arasındaki farkı
        taşıyamıyordu — bir kamyonun yanından yürüyen biri bile dolduruyordu.

        İki kural:
        - Açık bir epizot ZATEN varsa açılış sorusu yok: kaynaşma bugünkü
          gibi sürer, `True` döner — severity ne olursa olsun.
        - `interpretation` `None`'sa (görü kademesi kesintide, klip
          kesilemedi ya da yanıt ayrıştırılamadı) bugünkü davranışa
          düşülür ve açılışa izin verilir: bozuk bir görü kademesi
          bütün koşuyu susturmamalı — bu projenin değişmez kuralı.
        - Aksi hâlde açılış yalnız görü kademesi "olay" dediyse olur;
          "rutin" ve "dikkat" bir pencereyi epizota ÇEVİRMEZ.

        Sonuç (kasıtlı, gizlenmiyor): olaydan ÖNCEKİ pencereler artık
        hiçbir epizota girmiyor, yani onların anları (`beats`) teslim
        edilen `events[]`'e hiç ulaşmıyor. `events[]` olayı anlatmalı —
        olaydan önceki kırk saniyelik park hâlindeki kamyonu değil.
        """
        if self.store.open_episode() is not None:
            return True
        if interpretation is None:
            return True
        return interpretation.severity == "olay"

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

    @staticmethod
    def _fuses_a_notable_event(resolved: str,
                               interpretation: Interpretation | None) -> bool:
        """Bu kaynaşma operatöre bir gelişme bülteni hak ediyor mu.

        Ölçülen arıza (26 Ağustos canlı koşu, k04 forklift kazası klibi):
        yönlendirici HER pencerede `inspect` dedi (bkz. `orchestrator`'ın K1-K4
        arızası), epizot 00:40'ta açıldı ve `escalate` de sadece o AÇILIŞ
        anında yield etti. Sonraki ~50 saniye boyunca — insanlar toplandı,
        biri yere düştü — her pencere sessizce `update_episode`'a indi ve
        `DecisionLoop` bunu hiç yield ETMEDİ: döngü yalnız `escalate`
        kararında ve bir epizodun İLK açılışında (`inspect` dalı, yüksek
        risk) operatöre sesleniyordu. Aynı klibin önceki bir koşusu (kaynaşma
        yield etmeden ÖNCE) dört duyuru üretmişti: bir açılış + üç gelişme
        bülteni; canlı koşuda bu bire düştü.

        Seçicilik kasıtlı ve TEK ölçüt: yalnız görü kademesinin `EVENT_SEVERITY`
        ("olay") dediği pencere bir bülten üretir — "dikkat" ve "rutin"
        sessizce kaynaşır. Bu proje alarm yağmurunu bir kez düzeltti
        (`ESCALATING_RISKS` gate'i, aynı gerekçe: "kaynaşan her pencerede
        yeniden seslenmek 4 dakikalık sunumu alarm yağmuruna çevirir");
        her kaynaşmayı bültenletmek aynı arızayı geri getirirdi.
        `interpretation is None` (görü kademesi düştü, klip kesilemedi,
        yanıt ayrıştırılamadı) YENİ bir olayın kanıtı değildir — bülten
        üretilmez.

        `Supervisor.escalate` bu bültenleri ucuza mal ediyor: bir epizot bir
        kez tam müdahale görür (`self._escalated`), sonraki her çağrı
        `UPDATE_INSTRUCTION` ile depodaki değerlendirmeyi yeniden kullanır ve
        modele aracı TEKRAR ÇAĞIRMAMASI söylenir — yani bu bültenler ne saha
        aracını tekrarlar ne de operatörü doldurur, yalnız "hâlâ devam
        ediyor, işte gelişme" der.
        """
        return (resolved == "update_episode"
                and interpretation is not None
                and interpretation.severity == EVENT_SEVERITY)

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
        # Aynı enerji hem görü bütçesini (bkz. `_energy_indices`) hem artık
        # yönlendiriciyi nişanlıyor (26 Ağustos): yönlendirici görüntü görmez,
        # ama bu pencerenin koşunun geri kalanına göre ne kadar hareketli
        # olduğunu bilebilir. `motion_for` triyaj katmanı gibi asla
        # patlamamalı — bir istisna burada bütün koşuyu düşürmemeli.
        energy = None
        if self.motion_for is not None:
            try:
                energy = self.motion_for(window)
            except Exception:      # noqa: BLE001 — triyaj koşuyu düşürmez
                energy = None
        decision = (self.route(window, energy) if self._route_wants_energy
                   else self.route(window))
        self._handoff(TARGET.get(decision.decision, "perception"), ts,
                      decision.rationale, decision.confidence)

        if decision.decision == "ignore":
            # Açık bir epizot VARKEN yönlendiricinin (ya da kesintide her
            # zaman `ignore` döndüren `_fallback`'ın) "sakin" demesine
            # güvenilmiyor: `vision_budgeted`'dan bağımsız olarak pencere
            # yine görü kademesine gönderiliyor. Sebep `_may_open`'ın aynı
            # notu: olaydan ÖNCE bir pencereyi atlamanın bedeli yok, ama
            # olayın ORTASINDA atlamak o anı `events[]`'ten düşürür — ve bu,
            # `gozcu.agents.orchestrator.SYSTEM_PROMPT`'un K5'inin kod tarafındaki
            # güvencesi (model kuralı hep doğru uygulamayabilir).
            #
            # **Bu dal `DecisionLoop`'un enerji güvenlik ağına
            # (`_forced_indices`/`_energy_indices`) bağımlı.** O ağ bugüne
            # kadar `ignore`'un yönlendiriciden gerçekten hiç gelmediği bir
            # dünyada ölü koddu (K1-K4 her zaman `inspect`'e zorluyordu).
            # Yönlendirici artık gerçekten `ignore` diyebiliyor (K5) ve bu
            # ağ, o kararı güvenli kılan şey: biri "kullanılmıyor" diyip
            # `_forced_indices`/`_energy_indices`'i silerse `ignore`
            # kararları bir daha hiç doğrulanmaz.
            if self.store.open_episode() is not None:
                self._forced_sample(window, reason=OPEN_EPISODE_FORCED_REASON)
                return
            if vision_budgeted:
                # Yönlendirici sinyal özetine baktı ve "sakin" dedi; enerji
                # tersini söylüyor ve özet bir devrilmeyi taşıyamaz. Ölçülen
                # k05 arızası tam burada yaşandı: sekiz `ignore`, sıfır bakış.
                self._forced_sample(window, reason=ROUTED_FORCED_REASON)
            return

        needs_vision = decision.decision in NEEDS_VISION
        interpretation = self.interpret(window) if needs_vision else None

        # `inspect` = "bir şey var ama sinyalden ne olduğu anlaşılmıyor".
        # Yönlendirici GÖRÜNTÜ GÖRMÜYOR (`orchestrator.SYSTEM_PROMPT`) ve bu dalın
        # bütün amacı bakmak. Ama bakılan şey ATILIYORDU: `notable_event`
        # yalnız `_forced_sample` içinde okunuyordu, burada değil.
        #
        # Ölçülen bedel (26 Ağu canlı koşu): 00:05'te yorumlayıcı "bir
        # forklift başka bir forkliftin üstünde" dedi, görü çağrısının parası
        # ödendi ve sonuç çöpe gitti. Olay ancak 00:40'ta, sinyaller kendi
        # eşiğini geçtiğinde açıldı — yani kameranın gördüğü şeyin kararla
        # hiçbir ilgisi yoktu.
        #
        # Kapı artık `notable_event` metninin doluluğu DEĞİL, `_may_open` —
        # yani görü kademesinin biçtiği `severity`. Bir kamyonun yanından
        # yürüyen biri de "dikkat çekici" bir cümleye dönüşebiliyordu; "rutin"
        # / "dikkat" / "olay" ayrımı olmadan sistem bunu bir olaydan
        # ayıramıyordu (bkz. `_may_open`).
        if decision.decision == "inspect" and interpretation is not None:
            resolved = self._resolve("open_episode")
            if self._may_open(interpretation):
                episode = self.synthesize(window, interpretation, resolved)
                # Yükseltme YALNIZ olay açılırken ve yalnız yüksek riskte:
                # kaynaşan her pencerede yeniden seslenmek 4 dakikalık sunumu
                # alarm yağmuruna çevirir, düşük riskli her görüntüde
                # seslenmek ise operatörü uyarılara karşı sağırlaştırır.
                if (episode is not None and resolved == "open_episode"
                        and episode.preliminary_risk in ESCALATING_RISKS):
                    yield LoopEvent(episode=episode, late=False)
                # Açılış değil KAYNAŞMA — ve görü kademesi bu pencerede
                # gerçekten "olay" gördü: ölçülen arıza (bkz.
                # `_fuses_a_notable_event`) tam bu dalın sessiz kalmasıydı.
                elif episode is not None and self._fuses_a_notable_event(
                        resolved, interpretation):
                    yield LoopEvent(episode=episode, late=False)

        elif decision.decision in ("open_episode", "update_episode"):
            resolved = self._resolve(decision.decision)
            # `update_episode` depo boşken de gelebiliyor (Görev 06 notu) ve
            # o durumda sentezleyici kaynaşacak bir şey bulamayınca koşulsuz
            # yeni epizot AÇAR (`anomaly_analyst.synthesize`) — yani bu dal da bir
            # açılış yolu ve `_may_open` geçidinden geçmek zorunda.
            if self._may_open(interpretation):
                episode = self.synthesize(window, interpretation, resolved)
                # Aynı bülten kuralı burada da geçerli: yönlendirici doğrudan
                # `update_episode` dediğinde de görü kademesi "olay" gördüyse
                # operatör haberdar edilmeli (bkz. `_fuses_a_notable_event`).
                if episode is not None and self._fuses_a_notable_event(
                        resolved, interpretation):
                    yield LoopEvent(episode=episode, late=False)

        elif decision.decision == "close_episode":
            # Kapanış açılış değil; `_may_open` burada devre dışı — kapanacak
            # bir epizot yoksa `synthesize` zaten no-op (bkz. modül başı notu).
            self.synthesize(window, interpretation, decision.decision)

        elif decision.decision == "escalate":
            # Yükseltmenin tutunacağı bir epizot olmalı; yoksa risk
            # analizi hangi epizota yazacağını bilemez. Açık epizot varsa
            # `_resolve` bunu kaynaşmaya indirir.
            resolved = self._resolve("open_episode")
            episode = None
            if self._may_open(interpretation):
                episode = self.synthesize(window, interpretation, resolved)
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

        Kayda değerlik ölçütü artık `notable_event`in doluluğu DEĞİL,
        `_may_open` — yani görü kademesinin biçtiği `severity`. Yalnız
        "olay" epizot açar (açık epizot varsa `_resolve` kaynaşmaya
        indirir); "rutin" ve "dikkat" hiçbir şey uydurmaz.

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

        if self._may_open(interpretation):
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

        # `windows()` boş kova yield ETMİYOR (yalnız dolu kovaları veriyor),
        # bu yüzden burada bir boşluk koruması yok — ölü bir dal, çalıştığı
        # sanılan bir daldır.
        for index, window in enumerate(plan):
            # Ne GÖRÜLDÜĞÜ de kayda giriyor: "kaçıncı pencere" tek başına
            # katmanın o pencerede bir şey bulup bulmadığını söylemiyor.
            # Kayıt DEPOYA da yazılıyor — besleme algı satırını buradan
            # okuyor, ham gözlemden değil.
            budgeted = index in forced
            outcome = ("routed" if not failing[index]
                       else "forced" if budgeted else "skipped")
            record = window_record(window, index + 1, len(plan),
                                   not failing[index], budgeted, outcome)
            window_id = self.store.save_window(record)
            span = window_span(record)
            # Erteleme ancak görü kademesi düştükten SONRA biliniyor; kayıt
            # ise işleme başlamadan yazılıyor ki beslemede algı satırı
            # yönlendiriciden önce gelsin. Kuyruk büyüdüyse akıbet
            # düzeltiliyor — yoksa besleme, telafiye alınmış bir pencere için
            # "yönlendiriciye gitti" der ve kesintiyi tam da göstermesi
            # gereken anda gizler.
            deferred_before = len(self.deferred)
            if failing[index]:
                if index in forced:
                    with trace.step(f"pencere[{index + 1}/{len(plan)}]",
                                    f"{span} taban=HAYIR görü=zorunlu"):
                        self._forced_sample(window)
                    if len(self.deferred) > deferred_before:
                        self.store.set_window_outcome(window_id, "deferred")
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
                        f"görü={'bütçede' if budgeted else 'gerekirse'}")
            yield from self._routed(window, vision_budgeted=budgeted)
            if len(self.deferred) > deferred_before:
                self.store.set_window_outcome(window_id, "deferred")
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

        Telafi de bir açılış yolu — `_may_open` geçidinden geçer: kesinti
        sırasında biriken bir "rutin" pencere, bağlantı dönünce sessizce bir
        olaya dönüşmemeli.
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
            self._handoff("anomaly_analyst", window[0].ts, "telafi", 0.6)
            episode = None
            if self._may_open(interpretation):
                episode = self.synthesize(window, interpretation,
                                          self._resolve("open_episode"))
            if episode is not None:
                yield LoopEvent(episode=episode, late=True)
