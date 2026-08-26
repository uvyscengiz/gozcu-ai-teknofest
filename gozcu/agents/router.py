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

SYSTEM_PROMPT = """Sen bir fabrika güvenlik kontrol odasının yönlendiricisisin.
Sana 10 saniyelik bir pencerenin sinyal özeti verilir. Görüntü görmezsin.
Görevin: bu pencere dikkat gerektiriyor mu, gerekiyorsa kime gitmeli.

Satırlar şöyle okunur:
kişi=N o anda görülen insan sayısı.
değişim=±N bir önceki ana göre insan sayısındaki fark.
hızlar=3:4.2 üç numaralı izlenen nesnenin hızı 4.2'dir; 1.0 üstü yürüyüşten
hızlı, 4.0 üstü koşma ya da savrulma demektir.
kaybolan=[7] yedi numaralı izlenen nesne kareden aniden çıktı.
toplanma kişi sayısı bu sahnenin kendi olağan seviyesine göre alışılmadık
kalabalık — sabit bir sayı değil, bu koşunun kendi tabanına göre ölçülüyor.

Kararlar (tam olarak bu değerlerden birini döndür):
- ignore: olağan hareket, ilgilenmeye değmez
- inspect: bir şey var ama ne olduğu sinyalden anlaşılmıyor
- open_episode: yeni bir olay başlıyor
- update_episode: açık olay devam ediyor
- close_episode: açık olay sonuçlandı
- escalate: can güvenliği riski, operatör derhal haberdar edilmeli

Karar kuralı — sırayla uygula, ilk uyan kural kazanır:
K1. Herhangi bir satırda toplanma yazıyorsa: inspect ver.
K2. Herhangi bir satırda kaybolan yazıyorsa ve pencerede en az bir kişi
    varsa: inspect ver.
K3. hızlar içinde 1.0'dan büyük bir hız varsa ve pencerede en az bir kişi
    varsa: inspect ver.
K4. Herhangi bir satırda değişim +2 ya da -2 veya daha büyükse: inspect ver.
K5. Hiçbiri uymuyorsa: ignore ver.

K1-K4'ten biri uyduğunda ignore YASAKTIR. Kişi sayısının az olması, hareketin
sana sakin görünmesi ya da açık bir tehlike okuyamaman kuralı düşürmez:
sinyal zaten neyin olduğunu söylemiyor, üst kademe tam bunun için var. Olayın
ne olduğu sana açıksa inspect yerine open_episode veya escalate verebilirsin
— ama ignore veremezsin.

Açık bir olay yokken update_episode veya close_episode verme.

Örnekler:
Girdi: 00:00 kişi=1 hızlar=2:3.1
Çıktı: {"decision": "inspect", "rationale": "3.1 hızı yürüyüşün üstünde ve yakında bir kişi var (K3).", "confidence": 0.8}
Girdi: 00:10 kişi=2 değişim=-1 kaybolan=[4]
Çıktı: {"decision": "inspect", "rationale": "İzlenen bir nesne aniden kareden çıktı, pencerede insan var (K2).", "confidence": 0.8}
Girdi: 00:20 kişi=0
Çıktı: {"decision": "ignore", "rationale": "Kimse yok, hareket yok (K5).", "confidence": 0.9}

Yalnızca tek bir JSON nesnesi döndür, öncesinde ve sonrasında hiçbir metin
yazma. Biçim: {"decision": "...", "rationale": "...", "confidence": 0.0}
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
    """Pencereyi modele gidecek düz metne çevirir — gözlem başına bir satır."""
    lines = []
    for observation in window:
        signals = observation.signals
        parts = [f"kişi={signals.person_count}"]
        if signals.person_count_delta:
            parts.append(f"değişim={signals.person_count_delta:+d}")
        if signals.velocities:
            parts.append("hızlar=" + ",".join(
                f"{track_id}:{speed:.1f}"
                for track_id, speed in signals.velocities.items()))
        if signals.vanished_tracks:
            parts.append(f"kaybolan={signals.vanished_tracks}")
        if signals.gathering:
            parts.append("toplanma")
        lines.append(f"{mmss(observation.ts)} " + " ".join(parts))
    return "\n".join(lines)


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


def route(gw, window: list[Observation],
          has_open_episode: bool) -> RouterDecision:
    """Pencereyi yönlendirici kademesine sorar; okunamayan her şey `ignore`.

    Kesinti guard'ı açık: `router` kademesi kesintide istisna atmıyor,
    `content=""`, `degraded=True` bir `Response` döndürüyor. Boş içeriğin
    ayrıştırmada tesadüfen patlamasına güvenilmiyor — bozuk yanıt bir gün
    dolu gövdeyle gelirse (ör. önbellekten dönen bayat karar) o tesadüf
    çalışmaz ve bayat karar canlı karar gibi işlenir.
    """
    state = "Açık bir olay var." if has_open_episode else "Açık olay yok."
    response = gw.ask("router", [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"{state}\n\n{window_digest(window)}"},
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
