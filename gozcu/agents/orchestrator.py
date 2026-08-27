"""Yönlendirici ajanı — sistemin dikkat mekanizması.

10 saniyelik bir pencerenin sinyal özetine bakıp "burada dikkat gerektiren bir
şey var mı, varsa kime gider" kararını veriyor. **Görüntü görmüyor:** yalnızca
yapılandırılmış sinyal özeti alıyor. Küçük ve hızlı bir modelin yetmesinin
sebebi bu — kararların büyük çoğunluğu burada, en ucuz kademede kapanıyor.

Tetikleyicinin sabit bir sinyal eşiği değil de model kararı olması kasıtlı:
şartname "sabit kurallara dayalı basit bir pipeline yerine ... model tabanlı
karar mekanizmaları içeren bir mimari" istiyor.

Tek açık epizot değişmezi burada DEĞİL, `DecisionLoop._resolve()`'da korunuyor:
prompt açık bir epizot varken `open_episode` demeyi bilerek yasaklamıyor, karar
döngüde `update_episode`'a indiriliyor.
"""

import json
import math
from statistics import median

from gozcu.adapter import COUNT_DELTA_FACTOR, GATHERING_FACTOR, VANISHED_FACTOR
from gozcu.models import Observation, RouterDecision

# `EventSummary.time` deseni (`^\d{2}:\d{2}$`) iki haneli dakika istiyor ve
# `mmss`'in saat devri yok. Demo klipleri dakikalarla ölçülüyor; saat desteği
# kapsam dışı, ama geçersiz bir damga üretmek de seçenek değil — tavana
# yapıştırılıyor.
MAX_MINUTES = 99
_CLAMPED_STAMP = "99:59"

# Yönlendirici yanıtının token tavanı. Canlı ölçüm (25 Ağustos, altı pencerelik
# prob): tavansız istekler altı çağrının dördünde ~243 saniye sürdü ve
# ayrıştırılamayan içerikle döndü — strict-JSON kod çözümü kaçak tekrara girip
# `max_tokens` tükenene kadar yineliyor, JSON hiç kapanmıyor (bkz.
# `gozcu.gateway.Gateway.ask`'in aynı ölçümü). Ayrıştırılamayan yanıt
# `_fallback` üzerinden `ignore`'a çöküyor, yani kaçak tekrar doğrudan
# eksik-tetikleme demek. 200 karakterlik bir gerekçeyi taşıyan JSON en kötü
# hâlde ~150 token; 256 hem sığdırıyor hem kaçağı erken kesiyor.
MAX_DECISION_TOKENS = 256

# `RouterDecision.rationale`'ın sınırı. Şema sertleştirmesi `maxLength`'i telden
# söküyor (bkz. `gozcu.gateway.strict_schema`), yani modelin sınırı aşması
# mümkün; kesme bu yüzden Python tarafında.
MAX_RATIONALE = 200

# K3'ün "yürüyüşten hızlı" sınırı — kare GENİŞLİĞİ/saniye biriminde (26
# Ağustos; bkz. `gozcu.signals`'ın modül başı notu, `compute_signals` artık
# bu birimde üretiyor). Eskiden 1.0 PİKSEL/saniyeydi ve ölçülen k04 verisi
# (98.8 sn, 10 pencere, 896x434 kare) genel medyanın 7 px/s olduğunu
# gösterdi — eşik medyanın çok altında, yani K3 HER pencerede tetikleniyordu.
# Yeni birimde pencere başına en yüksek hız ölçüldü: 0.238, 0.157, 0.100,
# 0.604, 0.293, 0.218, 0.149, 0.082, 0.193, 0.115 — en yüksek İKİSİ (0.604,
# 0.293) forkliftin çarptığı ve devrildiği pencereler. 0.25 ikisini üstünde,
# geri kalan sekizini altında bırakıyor: verinin gerçekten ayırdığı çizgi bu.
WALK_SPEED = 0.25
# "Koşma ya da savrulma" — yalnız betimleyici, K3'ün karar sınırı hâlâ
# `WALK_SPEED`. Ölçülen tek tepe değer (0.604, devrilme anının kendisi) bu
# sınırın üstünde kalsın diye seçildi.
RUN_SPEED = 0.45

# K1/K2/K4 pencere-düzeyi eşiği (26 Ağustos, "her pencere inspect" arızası).
#
# `gathering` / `vanished_unusual` / `count_change_unusual` `gozcu.adapter.
# build_observations`'ta ZATEN koşunun kendi KARE medyanına göre türetiliyor
# — ama K1/K2/K4 onları "herhangi bir SATIRDA" okuyordu: bir pencerede ~30
# kareden BİRİ bile bayrağı taşısa kural tetikleniyordu. Ölçüldü (k04, 98.8
# sn, 10 pencere, ~30 kare/pencere — bkz. decision-log): koşunun HER
# penceresi en az bir `kaybolanYoğun` VE en az bir `değişimYoğun` kareli
# taşıyordu, yönlendirici 10/10 pencerede `inspect` döndü. Kare-düzeyinde
# eşiği sıkılaştırmak çözmüyor: pencere başına 30 karenin 1'inden azını
# tetikleyecek kadar sıkılaştırmak o kareyi per-kare sinyal olarak işe
# yaramaz hâle getirir.
#
# Çözüm aynı disiplinin bir kademe YUKARISI: bu pencerede bayrağı taşıyan
# kare SAYISI, koşunun DİĞER pencerelerine göre olağandışı mı? Aynı
# medyan×faktör deseni — `gozcu.adapter`'ın GATHERING_FACTOR / VANISHED_FACTOR
# / COUNT_DELTA_FACTOR'ü yeniden kullanılıyor (yeni bir sabit YOK, aynı üç
# sayı bir kademe yukarıda tekrar uygulanıyor) — ve `max(1, ceil(...))`
# tabanı: medyan sıfırsa eşik de sıfıra düşüp HER pencereyi tetiklemesin diye.
#
# k04 tablosuyla (pencere başına toplanma/kaybolanYoğun/değişimYoğun taşıyan
# kare sayısı: 14,4,0,1,0,2,15,24,30,26 · 4,6,2,4,7,1,4,15,16,8 ·
# 5,2,3,5,5,1,14,18,15,9) hesaplanan medyanlar 9.0 / 5.0 / 5.0, eşikler
# sırasıyla 14 / 10 / 8. Sonuç: 30-40s ve 40-50s (çarpışma/devrilme) K3'ten
# (hız) tetikleniyor; 60-98s (kalabalıklaşan sonrası) K1/K2/K4'ten
# tetikleniyor; 10-20s, 20-30s, 50-60s HİÇBİRİNDEN tetiklenmiyor — artık
# gerçekten ignore edilebiliyorlar.
_WINDOW_FLAG_FACTORS = {
    "toplanma": GATHERING_FACTOR,
    "kaybolanYoğun": VANISHED_FACTOR,
    "değişimYoğun": COUNT_DELTA_FACTOR,
}

#: Pencere-düzeyi bayrağın prompt'taki adı. Kare-düzeyi kelimeyle aynı kökü
#: taşıyor ama "Olağandışı" ekiyle: model "bu satırda X var" ile "bu PENCERE
#: diğerlerine göre X'te olağandışı" arasındaki farkı harfiyen görmeli — aynı
#: kelime iki düzeyde de kullanılırsa model ikisini karıştırıp yeniden
#: "herhangi bir satırda" okumasına geri döner.
_WINDOW_VERDICT_LABELS = {
    "toplanma": "toplanmaOlağandışı",
    "kaybolanYoğun": "kaybolanYoğunOlağandışı",
    "değişimYoğun": "değişimYoğunOlağandışı",
}


def _window_flag_counts(window: list[Observation]) -> dict[str, int]:
    """Pencerede üç bayrağı TAŞIYAN kare sayısı — satırların DOLULUĞU değil,
    SAYISI. K1/K2/K4'ün artık sorduğu şeyin girdisi bu."""
    return {
        "toplanma": sum(1 for o in window if o.signals.gathering),
        "kaybolanYoğun": sum(1 for o in window if o.signals.vanished_unusual),
        "değişimYoğun": sum(1 for o in window if o.signals.count_change_unusual),
    }


def window_signal_verdict(
        window: list[Observation],
        run_windows: list[list[Observation]] | None = None,
) -> dict[str, bool]:
    """Bu pencerenin K1/K2/K4 bayrakları koşunun DİĞER pencerelerine göre
    olağandışı mı — "herhangi bir satırda" değil.

    Eşik `median(pencere başına bayrak sayısı) * faktör` — `gozcu.adapter`'ın
    kare-düzeyi kuralıyla AYNI desen, bir kademe yukarıda. `max(1, ...)`
    tabanı medyan sıfırken eşiğin de sıfıra düşüp HER pencereyi (sayı >= 0
    hep doğru olurdu) tetiklemesini önlüyor.

    `run_windows` verilmezse ya da boşsa pencere KENDİ başına taban alınır;
    tek pencerelik bir taban `median * faktör >= sayı` üretmeye eğilimlidir
    (faktör > 1), yani sonuç genelde `False`'a düşer — koşunun geri kalanını
    hiç GÖRMEDEN "olağandışı" iddia etmektense sessizce ölçülememiş saymak
    daha güvenli (bkz. `gozcu.motion.build_motion_for`'un aynı "kanıt yoksa
    iddia etme" kuralı).
    """
    baseline_windows = run_windows if run_windows else [window]
    counts_per_window = [_window_flag_counts(w) for w in baseline_windows]
    counts = _window_flag_counts(window)
    verdict: dict[str, bool] = {}
    for key, factor in _WINDOW_FLAG_FACTORS.items():
        values = [c[key] for c in counts_per_window]
        baseline = median(values) if values else 0
        threshold = max(1, math.ceil(baseline * factor))
        verdict[key] = counts[key] >= threshold
    return verdict


def _window_signal_line(verdict: dict[str, bool] | None) -> str:
    """Pencere-düzeyi K1/K2/K4 kanıtının tek satırlık özeti — `_energy_line`
    ile AYNI desende: `verdict` `None`'sa (koşunun diğer pencereleri
    bilinmiyor) satır hiç eklenmiyor. Sessizce "yok" yazmak "ölçülemedi"yi
    "olağan" diye okurdu; ikisi aynı şey değil.
    """
    if verdict is None:
        return ""
    words = [label for key, label in _WINDOW_VERDICT_LABELS.items()
            if verdict.get(key)]
    return "pencereBayrakları=" + (",".join(words) if words else "yok")


SYSTEM_PROMPT = f"""Sen bir fabrika güvenlik kontrol odasının yönlendiricisisin.
Sana 10 saniyelik bir pencerenin sinyal özeti verilir. Görüntü görmezsin.
Görevin: bu pencere dikkat gerektiriyor mu, gerekiyorsa kime gitmeli.

Satırlar şöyle okunur:
kişi=N o anda görülen insan sayısı.
değişim=±N bir önceki ana göre insan sayısındaki fark; sayım gürültüsü
yüzünden her karede birkaç birim oynayabilir, tek başına kanıt değildir.
değişimYoğun bu değişimin bu KOŞUNUN kendi gürültü tabanına göre belirgin
şekilde fazla olduğu anlamına gelir.
hızlar=3:{WALK_SPEED + 0.05:.2f} üç numaralı izlenen nesnenin hızı saniyede
kendi KARE GENİŞLİĞİNİN {WALK_SPEED + 0.05:.2f} katıdır (kare genişliği/
saniye — sahne ve çözünürlükten bağımsız bir oran, piksel değil);
{WALK_SPEED:.2f} üstü yürüyüşten hızlı, {RUN_SPEED:.2f} üstü koşma ya da
savrulma demektir.
kaybolan=[7] yedi numaralı izlenen nesne kareden aniden çıktı; bu TEK
BAŞINA kanıt değildir — düşük eşikli tespit izleri sık parçalanır ve tek
bir kaybolan iz neredeyse her karede görülür.
kaybolanYoğun bu karedeki kaybolan iz SAYISININ bu KOŞUNUN kendi olağan
seviyesine göre belirgin şekilde fazla olduğu anlamına gelir.
toplanma kişi sayısı bu sahnenin kendi olağan seviyesine göre alışılmadık
kalabalık — sabit bir sayı değil, bu koşunun kendi tabanına göre ölçülüyor.
pencereBayrakları=toplanmaOlağandışı,... (varsa) bu PENCEREDE yukarıdaki üç
bayrağı (toplanma/kaybolanYoğun/değişimYoğun) TAŞIYAN kare SAYISININ, bu
KOŞUNUN DİĞER PENCERELERİNE göre olağandışı olduğunu gösterir — yukarıdaki
satırlardan FARKLI bir düzey. Tek bir karede görülen bir bayrak TEK BAŞINA
kanıt değildir: düşük eşikli sinyaller sık görülür ve 30 karelik bir
pencerede en az biri neredeyse HER ZAMAN görülür; K1/K2/K4 bu yüzden
yukarıdaki tek tek satırlara değil bu satıra bakar. pencereBayrakları=yok
ise pencere kendi türünün diğer pencerelerinden ayırt edilemiyor demektir;
satır hiç yoksa (koşunun diğer pencereleri bilinmiyor) K1/K2/K4
uygulanamaz.
enerji=0.97 (varsa) bu pencerenin bu koşunun GERİ KALANINA göre HAREKET
ENERJİSİ; 1.0 koşunun en hareketli penceresi demek, 0'a yakın değerler
görece durağan demektir. Bu satır yoksa o pencere için kanıt üretilememiş
demektir — "hareket yok" değil.

Kararlar (tam olarak bu değerlerden birini döndür):
- ignore: olağan hareket, ilgilenmeye değmez
- inspect: bir şey var ama ne olduğu sinyalden anlaşılmıyor
- open_episode: yeni bir olay başlıyor
- update_episode: açık olay devam ediyor
- close_episode: açık olay sonuçlandı
- escalate: can güvenliği riski, operatör derhal haberdar edilmeli

Karar kuralı — sırayla uygula, ilk uyan kural kazanır:
K1. pencereBayrakları içinde toplanmaOlağandışı varsa: inspect ver.
K2. pencereBayrakları içinde kaybolanYoğunOlağandışı varsa ve pencerede en
    az bir kişi varsa: inspect ver.
K3. hızlar içinde {WALK_SPEED:.2f}'ten büyük bir hız varsa ve pencerede en
    az bir kişi varsa: inspect ver.
K4. pencereBayrakları içinde değişimYoğunOlağandışı varsa: inspect ver.
K5. Hiçbiri uymuyorsa: açık bir olay YOKSA ignore ver. AÇIK BİR OLAY VARSA
    ignore VERME — en azından update_episode ver; olay senin
    görebildiğin kadarıyla bittiyse close_episode ver.

K5'in gerekçesi: olaydan ÖNCE sessiz bir pencereyi atlamanın hiçbir bedeli
yoktur (bir görü çağrısı ve bir sentez çağrısı tasarrufu); ama olayın
ORTASINDA bir pencereyi atlamak o anı teslim edilen olay listesinden
düşürür. Kişi sayısının az olması, hareketin sana sakin görünmesi ya da
açık bir tehlike okuyamaman K1-K4'ü düşürmez: sinyal zaten neyin olduğunu
söylemiyor, üst kademe tam bunun için var. Olayın ne olduğu sana açıksa
inspect yerine open_episode veya escalate verebilirsin.

enerji satırı da bir kanıttır: K1-K4'ün hiçbiri net değilse ama enerji bu
koşunun tepe değerine yakınsa, bunu ignore yerine inspect lehine bir işaret
say.

Açık bir olay yokken update_episode veya close_episode verme.

Örnekler:
Girdi: 00:00 kişi=1 hızlar=2:{WALK_SPEED + 0.05:.2f}
Çıktı: {{"decision": "inspect", "rationale": "{WALK_SPEED + 0.05:.2f} hızı yürüyüşün üstünde ve yakında bir kişi var (K3).", "confidence": 0.8}}
Girdi: pencereBayrakları=kaybolanYoğunOlağandışı
00:10 kişi=2 değişim=-1 kaybolan=[4] kaybolanYoğun
Çıktı: {{"decision": "inspect", "rationale": "Bu pencerede kaybolan iz yoğunluğu koşunun diğer pencerelerine göre olağandışı, pencerede insan var (K2).", "confidence": 0.8}}
Girdi: 00:20 kişi=0
Çıktı: {{"decision": "ignore", "rationale": "Kimse yok, hareket yok, açık olay da yok (K5).", "confidence": 0.9}}
Girdi: (açık bir olay var) 00:30 kişi=0
Çıktı: {{"decision": "update_episode", "rationale": "Hiçbir kural uymuyor ama olay hâlâ açık, pencere atlanmıyor (K5).", "confidence": 0.6}}

Yalnızca tek bir JSON nesnesi döndür, öncesinde ve sonrasında hiçbir metin
yazma. Biçim: {{"decision": "...", "rationale": "...", "confidence": 0.0}}
Gerekçe tek cümle Türkçe ve en çok 200 karakter olsun; kapanış süslü
parantezini yazdıktan sonra DUR, aynı şeyi tekrar yazma."""


def mmss(ts: float) -> str:
    """Video saniyesini "DD:SS" damgasına çevirir; 99:59'da tavana oturur.

    Tek kopya bilerek burada: Görev 07, 14 ve 17 bunu import ediyor.
    """
    minutes, seconds = divmod(int(ts), 60)
    if minutes > MAX_MINUTES:
        return _CLAMPED_STAMP
    return f"{minutes:02d}:{seconds:02d}"


def window_digest(window: list[Observation]) -> str:
    """Pencereyi modele gidecek düz metne çevirir — gözlem başına bir satır.

    Hız `.2f` ile basılıyor (eskiden `.1f`): birim artık kare genişliği/
    saniye ve tipik değerler 0.01-0.6 aralığında (bkz. `gozcu.signals`) —
    tek ondalık basamak medyan hareketi hep "0.0"a yuvarlayıp modele
    okuyacağı hiçbir şey bırakmazdı.
    """
    lines = []
    for observation in window:
        signals = observation.signals
        parts = [f"kişi={signals.person_count}"]
        if signals.person_count_delta:
            parts.append(f"değişim={signals.person_count_delta:+d}")
        if signals.count_change_unusual:
            parts.append("değişimYoğun")
        if signals.velocities:
            parts.append("hızlar=" + ",".join(
                f"{track_id}:{speed:.2f}"
                for track_id, speed in signals.velocities.items()))
        if signals.vanished_tracks:
            parts.append(f"kaybolan={signals.vanished_tracks}")
        if signals.vanished_unusual:
            parts.append("kaybolanYoğun")
        if signals.gathering:
            parts.append("toplanma")
        lines.append(f"{mmss(observation.ts)} " + " ".join(parts))
    return "\n".join(lines)


def _energy_line(energy: float | None) -> str:
    """Pencerenin bu koşu içindeki göreli hareket enerjisi satırı.

    `None` — triyaj katmanı (`gozcu.motion.build_motion_for`) bu pencere
    için kanıt üretemedi ya da hiç enjekte edilmedi — boş dizeye düşüyor ve
    `route()` bu satırı prompt'a HİÇ eklemiyor. Sessizce "enerji=0.0" yazmak
    "kanıt yok"u "durağan" diye okurdu; ikisi aynı şey değil.
    """
    if energy is None:
        return ""
    return f"enerji={energy:.2f}"


def _fallback(rationale: str) -> RouterDecision:
    """Karar okunamadığında pencere sessizce geçilir.

    Bozuk bir JSON'da patlayan yönlendirici tek bir kötü yanıtta bütün koşuyu
    düşürür; güven sıfır veriliyor ki ölçümde gerçek bir kararla karışmasın.
    """
    return RouterDecision(decision="ignore", rationale=rationale, confidence=0.0)


def _sanitize(data: dict) -> dict:
    """Modelin döndürdüğü değerleri doğrulamadan ÖNCE sınırlara sokar.

    Sertleştirme `maxLength`/`minimum`/`maximum`'u telden söküyor, yani model
    200 karakteri aşan bir gerekçe ya da 0..1 dışında bir güven döndürebilir.
    Ham hâliyle `RouterDecision(**…)`'a verilirse doğrulama patlar ve gerçek
    bir karar — belki bir `escalate` — `ignore`'a çöker. Sınıra çekmek kararı
    korur, uydurmaz.
    """
    rationale = data.get("rationale")
    if isinstance(rationale, str) and len(rationale) > MAX_RATIONALE:
        data["rationale"] = rationale[:MAX_RATIONALE]

    confidence = data.get("confidence")
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        data["confidence"] = min(1.0, max(0.0, float(confidence)))
    return data


def route(gw, window: list[Observation], has_open_episode: bool, *,
          energy: float | None = None,
          run_windows: list[list[Observation]] | None = None) -> RouterDecision:
    """Pencereyi yönlendirici kademesine sorar; okunamayan her şey `ignore`.

    Kesinti guard'ı açık: `router` kademesi kesintide istisna atmıyor,
    `content=""`, `degraded=True` bir `Response` döndürüyor. Boş içeriğin
    ayrıştırmada tesadüfen patlamasına güvenilmiyor — bozuk yanıt bir gün
    dolu gövdeyle gelirse (ör. önbellekten dönen bayat karar) o tesadüf
    çalışmaz ve bayat karar canlı karar gibi işlenir.

    `energy` (26 Ağustos) pencerenin `gozcu.motion.build_motion_for`'dan gelen,
    bu koşunun geri kalanına göre normalize hareket enerjisi. `None` —
    enjekte edilmemiş ya da bu pencere için kanıt yok — satırı sessizce
    prompt'tan düşürüyor (`_energy_line`); yönlendirici görüntü görmediği
    için bu satır olmadan da çalışabilmeli.

    `run_windows` (26 Ağustos, K1/K2/K4'ün "herhangi bir satırda" arızası)
    koşunun BÜTÜN pencereleri — `gozcu.loop.windows()`'ın ürettiğiyle aynı
    şekilde gruplanmış. Verilirse `window_signal_verdict` bu pencerenin
    toplanma/kaybolanYoğun/değişimYoğun bayraklarını koşunun DİĞER
    pencerelerine göre tartıp `pencereBayrakları=` satırını üretir; K1/K2/K4
    artık buna bakıyor. `None` — enjekte edilmemiş — satırı `_energy_line`
    ile aynı desende sessizce prompt'tan düşürüyor: yönlendirici koşunun
    geri kalanını bilmeden de çağrılabilmeli.

    **`ignore` artık gerçek bir yol** (K5, açık olay yokken). Bunun güvenli
    olmasının sebebi burada değil `gozcu.loop.DecisionLoop`'ta: enerji
    güvenlik ağı (`_forced_indices`/`_energy_indices`) en yüksek enerjili
    pencerelere yönlendiriciden BAĞIMSIZ bir görü çağrısı garanti ediyor ve
    `_routed` açık bir olay varken `ignore`'a hiç güvenmiyor. Bu fonksiyon
    o ağı bilmeden çağrılabilir olmalı — bağımlılık `loop.py`'da, burada
    değil.
    """
    state = "Açık bir olay var." if has_open_episode else "Açık olay yok."
    content = f"{state}\n\n{window_digest(window)}"
    if run_windows is not None:
        signal_line = _window_signal_line(window_signal_verdict(window, run_windows))
        if signal_line:
            content += f"\n\n{signal_line}"
    energy_line = _energy_line(energy)
    if energy_line:
        content += f"\n\n{energy_line}"
    response = gw.ask("router", [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ], schema=RouterDecision, max_tokens=MAX_DECISION_TOKENS)

    if response.degraded:
        return _fallback("yönlendirici kademesi yanıt vermiyor")

    try:
        data = json.loads(response.content)
    except (ValueError, TypeError):
        return _fallback("yönlendirici yanıtı okunamadı")
    if not isinstance(data, dict):
        return _fallback("yönlendirici yanıtı okunamadı")

    try:
        return RouterDecision(**_sanitize(data))
    except Exception:  # noqa: BLE001 — kötü bir karar koşuyu durdurmamalı
        return _fallback("yönlendirici yanıtı okunamadı")
