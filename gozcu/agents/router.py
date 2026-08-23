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

# `RouterDecision.rationale`'ın sınırı. Şema sertleştirmesi `maxLength`'i telden
# söküyor (bkz. `gozcu.gateway.strict_schema`), yani modelin sınırı aşması
# mümkün; kesme bu yüzden Python tarafında.
MAX_RATIONALE = 200

SYSTEM_PROMPT = """Sen bir fabrika güvenlik kontrol odasının yönlendiricisisin.
Sana 10 saniyelik bir pencerenin sinyal özeti verilir. Görüntü görmezsin.
Görevin: bu pencere dikkat gerektiriyor mu, gerekiyorsa kime gitmeli.

Kararlar (tam olarak bu değerlerden birini döndür):
- ignore: olağan hareket, ilgilenmeye değmez
- inspect: bir şey var ama ne olduğu sinyalden anlaşılmıyor
- open_episode: yeni bir olay başlıyor
- update_episode: açık olay devam ediyor
- close_episode: açık olay sonuçlandı
- escalate: can güvenliği riski, operatör derhal haberdar edilmeli

Açık bir olay yokken update_episode veya close_episode verme.
Sadece JSON döndür."""


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
    ], schema=RouterDecision)

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
