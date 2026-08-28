"""Konsolun iki canlı grafiğini besleyen zaman serileri (Görev raporu §1).

Video oynarken ekranın altında iki çizgi grafik videonun kendi saatiyle
ilerliyor: kadrajdaki **varlık sayısı** ve **piksel entropisi**. Bu modül o
grafiklerin arkasındaki veriyi kuruyor — çizim tarayıcıda
(`gozcu/ui/web/js/charts.js`), karar burada.

Modül **saf**: model çağırmıyor, dosya okumuyor, ağa çıkmıyor. Girdisi zaten
hesaplanmış olan iki şey — algı katmanının gözlemleri ve triyaj katmanının
kare skorları — çıktısı JSON'a doğrudan dökülebilen sözlükler.

## İki kural, ikisi de depodan devralındı

**Ölçülmemiş kare sıfır DEĞİL.** `gozcu.motion` kanıtsız kareyi `None`
veriyor (bozuk dosya, tek kare, okunamayan JPEG). `frame_energy` kolaylık
olsun diye onu 0,0'a düşürüyor ama grafik o kolaylığı kaldıramaz: 0,0
"burada hiç hareket yoktu" diye okunur, oysa doğrusu "burayı ölçemedik".
`None` tel üzerinde `null` olarak gidiyor ve çizgi orada kopuyor. Konsolun
Performans sayfasındaki kural da aynı — ölçülemeyen hücre sıfır diye
gösterilmiyor.

**Zirve eşiği koşuya GÖRELİ.** `gozcu.motion`'ın docstring'i sabit bir eşiği
açıkça yasaklıyor: skorlar koşu içinde normalize ediliyor, yani baştan sona
durgun bir klipte de bir kare 1,0 alır. "Enerji > 0,8 ise alarm" kuralı bu
yüzden yanlış olurdu. Kırmızı çizgi bunun yerine koşunun KENDİ dağılımından
çıkıyor (`PEAK_QUANTILE`'inci yüzdelik) ve koşudan koşuya kayıyor.
"""

import math
from collections import Counter, defaultdict
from collections.abc import Container, Sequence

from gozcu.core.models import Observation

__all__ = ["MAX_NAMED_LABELS", "OTHER_LABEL", "PEAK_QUANTILE",
           "energy_series", "entity_series", "peak_threshold", "risk_track"]

#: Kendi çizgisiyle gösterilecek en fazla tür sayısı. Görev raporunun
#: kuralı: ekranda çok fazla nesne türü olabileceği için grafiğin
#: karmaşıklaşmasını istemiyoruz.
MAX_NAMED_LABELS = 3

#: Geri kalan türlerin toplandığı kova. **İnsana görünen metin Türkçe**
#: (CLAUDE.md) — bu bir etiket, bir anahtar değil.
OTHER_LABEL = "Diğer"

#: Zirve eşiğinin oturduğu yüzdelik. Koşunun en hareketli %10'u zirve
#: sayılıyor.
#:
#: **Ortalama + k·standart sapma DENENDİ ve reddedildi.** Aradığımız şey tam
#: da bir aykırı değer ve aykırı değer kendi sapmasını şişiriyor: `[0,1 0,1
#: 0,1 0,1 0,9]` serisinde ortalama 0,26, sapma 0,32, yani eşik 0,90 — zirve
#: 0,9 kendi eşiğinin ALTINDA kalıyor ve hiç işaretlenmiyor (ölçüldü,
#: `test_energy_series_marks_the_peaks_above_the_threshold`). Kısa klipte
#: tek zirve kuralın kör noktası; bizim manşet olayımız tam olarak o.
#: Yüzdelik böyle bir geri besleme taşımıyor: zirvenin ne kadar yüksek
#: olduğu eşiği yukarı itmiyor.
#:
#: 0,90 seçildi: kırmızı çizgi "üstteki onda bir" diye okunuyor, tek
#: cümleyle açıklanabiliyor. Bedeli dürüstçe yazılsın — baştan sona sakin
#: bir klipte de bir onda bir vardır, yani orada işaretlenen şey olay değil
#: o koşunun en yüksek gürültüsüdür. `gozcu.motion`'ın normalizasyon
#: uyarısının aynısı burada da geçerli: bu grafik SIRALAMA gösteriyor,
#: mutlak bir alarm eşiği değil.
PEAK_QUANTILE = 0.90


def _quantile(sorted_values: Sequence[float], quantile: float) -> float:
    """`sorted_values`'ın `quantile`'inci yüzdeliği, doğrusal ara değerle.

    `statistics.quantiles` kullanılmadı: o veriyi n eşit kovaya bölüp
    kesme noktalarının LİSTESİNİ veriyor, tek bir yüzdelik istemek kova
    sayısını eşiğe göre seçmeyi gerektirirdi (0,90 için `n=10`) — eşiği
    değiştiren biri o bağı fark etmeden kırar.
    """
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = quantile * (len(sorted_values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    return (sorted_values[lower] * (upper - position)
            + sorted_values[upper] * (position - lower))


def entity_series(observations: Sequence[Observation]) -> dict:
    """Zaman damgası başına, türe ayrılmış tespit sayısı.

    Dönen yapı::

        {"ts": [0.0, 1.0, ...],
         "series": [{"label": "insan", "values": [2, 1, ...]}, ...]}

    Türler koşu boyunca toplam tespit sayısına göre sıralanıyor; ilk
    `MAX_NAMED_LABELS` tanesi kendi çizgisini alıyor, geri kalanların
    **toplamı** tek bir `OTHER_LABEL` çizgisine düşüyor. "Diğer" bir örnek
    tür değil, gerçekten geri kalanın toplamı — üç ya da daha az tür varsa
    hiç üretilmiyor, boş bir çizgi ekranda yer kaplamasın.

    Her çizgi zaman ekseniyle **hizalı**: o saniyede o türden tespit yoksa
    değer 0. Burada 0 dürüst — kare ölçüldü ve o türden bir şey görülmedi;
    `energy_series`'in `None`'ıyla karıştırılmamalı.
    """
    counts_at: dict[float, Counter] = defaultdict(Counter)
    totals: Counter = Counter()
    for observation in observations:
        timestamp = float(observation.ts)
        counts_at[timestamp]                     # boş kare de eksene girsin
        for detection in observation.detections:
            counts_at[timestamp][detection.label] += 1
            totals[detection.label] += 1

    timestamps = sorted(counts_at)
    if not timestamps:
        return {"ts": [], "series": []}

    # Sıralama toplam sayıya göre azalan; eşitlikte etiket adına göre artan.
    # İkinci terim olmasaydı sıra `Counter`'ın ekleme düzenine bağlı kalır,
    # yani aynı videoda kare sırası değişince çizgiler yer değiştirirdi.
    ranked = sorted(totals, key=lambda label: (-totals[label], label))
    named = ranked[:MAX_NAMED_LABELS]
    rest = ranked[MAX_NAMED_LABELS:]

    series = [{"label": label,
               "values": [counts_at[ts][label] for ts in timestamps]}
              for label in named]
    if rest:
        series.append({
            "label": OTHER_LABEL,
            "values": [sum(counts_at[ts][label] for label in rest)
                       for ts in timestamps]})
    return {"ts": timestamps, "series": series}


def risk_track(risks, archived: Container[int] = ()) -> list[dict]:
    """Video saatine bağlı risk izi: `[{"ts": 12.4, "level": "Yüksek"}, ...]`.

    Operasyon ekranındaki dikey durum çubuğu (Görev raporu §2) bunu okuyor:
    çubuk `video.currentTime`'a kadarki SON değerlendirmeyi yakıyor.

    **Seviye dört kademe kalıyor** (`RiskLevel`: Düşük/Orta/Yüksek/Kritik).
    Çubuğun raporda istenen üç bölmesi bir ÇİZİM kararı; seviyenin adı ise
    sistemin kararı ve tel onu fakirleştirmiyor. "Kritik"i "Yüksek"e
    katlamak, ekranın en ağır sözcüğünü sessizce yutardı.

    `archived` koşu BAŞLAMADAN önce belleğe tohumlanan epizotların
    kimlikleri (`Session.archived`). Onların riski bu videonun riski değil;
    izde bırakılsalardı video daha başlamadan çubuk kırmızı yanardı.

    `RiskAssessment.ts` damgasız kayıtlarda 0,0 olabiliyor (modelin kendi
    notu). Burada ayıklanmıyor: 0,0 videonun başı demek ve çubuğun oradan
    başlaması yanlış değil — yanlış olan, o kaydın başka bir videoya ait
    olmasıdır ve onu eleyen şey `archived`.
    """
    rows = [{"ts": float(risk.ts), "level": risk.level}
            for risk in risks if risk.episode_id not in archived]
    return sorted(rows, key=lambda row: row["ts"])


def peak_threshold(values: Sequence[float]) -> float | None:
    """Koşunun kendi dağılımından çıkan zirve eşiği; yoksa `None`.

    Ölçülmüş karelerin `PEAK_QUANTILE`'inci yüzdeliği. `None` iki durumda
    döner ve ikisi de "kırmızı çizgi çizilmesin" demek:

    - **İki noktadan az** — bir dağılım değil, bir nokta.
    - **Hiçbir kare eşiği AŞMIYOR** — düz bir seride hiçbir kare
      diğerlerinden ayrılmıyor. Çizgiyi yine de çizmek her kareyi zirve
      ilan ederdi ve "hepsi zirve" hiçbir şey demek.
    """
    measured = sorted(float(value) for value in values if value is not None)
    if len(measured) < 2:
        return None
    threshold = _quantile(measured, PEAK_QUANTILE)
    if measured[-1] <= threshold:
        return None
    return threshold


def energy_series(timestamps: Sequence[float],
                  scores: Sequence[float | None]) -> dict:
    """Kare başına piksel entropisi + zirve eşiği + zirvelerin saniyeleri.

    Dönen yapı::

        {"ts": [...], "values": [...], "threshold": 0.71, "peaks": [11.0]}

    `scores` `gozcu.motion.combine_with_anomaly`'nin çıktısı: girdiyle
    hizalı, kanıtsız konumlarda `None`. `None`'lar **korunuyor** (modül
    docstring'i) ve eşik hesabına girmiyor — birkaç okunamayan kareyi 0,0
    saymak ortalamayı aşağı çeker, eşiği düşürür ve olmayan zirveler
    uydururdu.

    Hizasız girdi sessizce eşleştirilmiyor: `zip`'in kısa olanda durması
    kalan kareleri kaybettirir, kaydırma ise yanlış saniyeye yanlış skor
    yazardı — ikisi de grafiği sessizce yalancı yapar.
    """
    timestamps = [float(timestamp) for timestamp in timestamps]
    scores = list(scores)
    if len(timestamps) != len(scores):
        raise ValueError(
            f"Hizasız seri: {len(timestamps)} zaman damgası, "
            f"{len(scores)} skor.")
    if not timestamps:
        return {"ts": [], "values": [], "threshold": None, "peaks": []}

    values = [None if score is None else float(score) for score in scores]
    threshold = peak_threshold(values)
    peaks = ([timestamp
              for timestamp, value in zip(timestamps, values, strict=True)
              if value is not None and value > threshold]
             if threshold is not None else [])
    return {"ts": timestamps, "values": values,
            "threshold": threshold, "peaks": peaks}
