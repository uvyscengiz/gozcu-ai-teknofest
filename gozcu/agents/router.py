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
K1. Herhangi bir satırda toplanma yazıyorsa: inspect ver.
K2. Herhangi bir satırda kaybolanYoğun yazıyorsa ve pencerede en az bir kişi
    varsa: inspect ver.
K3. hızlar içinde {WALK_SPEED:.2f}'ten büyük bir hız varsa ve pencerede en
    az bir kişi varsa: inspect ver.
K4. Herhangi bir satırda değişimYoğun yazıyorsa: inspect ver.
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
Girdi: 00:10 kişi=2 değişim=-1 kaybolan=[4] kaybolanYoğun
Çıktı: {{"decision": "inspect", "rationale": "Kaybolan iz sayısı bu koşu için olağandışı, pencerede insan var (K2).", "confidence": 0.8}}
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
          energy: float | None = None) -> RouterDecision:
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
