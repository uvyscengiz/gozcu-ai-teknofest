"""Çıktı sözleşmesinin derleyicisi — jürinin okuduğu dört anahtar.

Şartnamenin puanladığı çıktı şu dört anahtardan oluşuyor: `summary`,
`events`, `risk`, `actions`. **Dördü diğer her şey çökse bile üretilir.**
Eklediğimiz her katman — fazlı epizotlar, devir defteri, risk gerekçeleri,
aksiyon defteri, kök neden raporu — `detail` altında onların YANINDA duruyor,
yerine değil.

Bu modül hiçbir model çağırmıyor: elindeki tek malzeme depo. Bozulmuş bir
koşuda da tam olarak aynı işi yapıyor, sadece daha az veriyle.
"""

from dataclasses import dataclass

from gozcu.agents.router import mmss
from gozcu.models import Detail, EventSummary, PipelineOutput, RiskLevel
from gozcu.tools.registry import TOOLS

#: Risk seviyelerinin şiddet sırası. Değerler Türkçe kalır (CLAUDE.md) ve
#: `RiskLevel`'ın kendisiyle birebir aynı olmak zorunda.
ORDER: list[RiskLevel] = ["Düşük", "Orta", "Yüksek", "Kritik"]

#: `EventSummary.event`'in sınırı. `Episode.summary_tr` 600'e kadar
#: uzayabiliyor; kesilmezse doğrulama patlar ve olay listesinin tamamı
#: kaybolur.
MAX_EVENT = 200

DEFAULT_RISK: RiskLevel = "Düşük"

#: Kare farkı zirvesinin "burada belirgin bir hareket var" sayıldığı eşik —
#: gri seviye cinsinden ORTALAMA mutlak fark (`gozcu.motion.raw_scores`'un
#: birinci terimi), koşu içi normalizasyondan ÖNCEKİ ham hâli.
#:
#: Normalize edilmiş enerji burada kullanılamaz: `combine()` her koşuyu kendi
#: zirvesine bölüyor, yani normalize zirve tanım gereği hep 1,0 — sabit bir
#: sayı hiçbir şeyi ayırt etmez. `motion.py` bunu zaten yazıyor ("kimse
#: buradan 'enerji > 0,8 ise alarm' kuralı çıkarmasın"); o uyarıya uyulan yer
#: burası.
#:
#: 25 Ağustos ölçümü (896 px kare, ham kare farkı zirvesi):
#:
#:   forklift k03 (raf çökmesi)    9,4
#:   forklift k05 (demo)          12,9
#:   yangın k03 (sıfır tespit)   102,2
#:
#: 30,0 seçildi: sıradan saha hareketinin (9–13) belirgin şekilde üstünde,
#: ölçülen kör koşunun (102) çok altında. Bu eşik yalnız **epizot üretmemiş**
#: bir koşunun özetini seçiyor; alarm üretmiyor, riski yükseltmiyor.
HIGH_MOTION_ENERGY = 30.0

#: Kör koşunun operatöre giden metni. `EMPTY_SUMMARY`'nin ("Kayda değer olay
#: tespit edilmedi.") yerine geçmiyor — onun YANINDA duruyor ve aralarındaki
#: seçim `PerceptionHealth.blind` ile yapılıyor.
BLIND_TEMPLATE = (
    "Algı katmanı bu kayıtta güvenilir tespit üretemedi ({reasons}); "
    "olay olup olmadığı DOĞRULANAMADI. Bu bir \"olay yok\" hükmü değildir — "
    "kaydı bir operatör gözden geçirmeli.")

#: Anı olmayan yedek-özetli epizodun `events[]` metni. Arıza metni jüri
#: anahtarına girmez; uydurma da girmez — olan şey dürüstçe söylenir (spec §1).
FALLBACK_EVENT = "Olay tespit edildi; tarifi üretilemedi (sentez arızası)."


@dataclass(frozen=True)
class PerceptionHealth:
    """Algı katmanının bir koşuda ne kadar görebildiği.

    `gozcu.motion` "veri yok" (`None`) ile "sıfır" arasındaki farkı zaten
    tutuyor; teslim katmanı o farkı düşürüp "hiçbir şey olmadı" diye
    iddia ediyordu. Bu kayıt farkı `build_output`'a kadar taşıyor.

    - `detections` — koşu boyunca ajan katmanına ulaşan tespit sayısı.
    - `frames` — işlenen kare sayısı; metinde "kaç karede" diye geçiyor.
    - `peak_motion_energy` — ham kare farkı zirvesi; `None` **kanıt yok**
      demek (okunamayan kareler, tek kare, boş liste), sıfır hareket değil.
    """

    detections: int = 0
    frames: int = 0
    peak_motion_energy: float | None = None

    @property
    def blind(self) -> bool:
        """Bu koşuda "olay yok" denebilir mi, denemez mi.

        İki dal da körlüktür ve ikisi de ayrı ölçüldü:

        - **Hiç tespit yok.** Üzerinde akıl yürütülecek hiçbir kanıt
          üretilmedi; sessiz bir sahne ile kör bir katman ayırt edilemez.
        - **Belirgin hareket var ama hiçbiri doğrulanmadı.** Kareler
          değişiyor, epizot yok — görülen ile anlaşılan arasındaki bu boşluk
          bir "olay yok" hükmüne çevrilemez.
        """
        if self.detections == 0:
            return True
        return (self.peak_motion_energy is not None
                and self.peak_motion_energy >= HIGH_MOTION_ENERGY)

    def blind_summary(self) -> str:
        """Kör koşunun Türkçe özeti — gerekçesini de yazarak."""
        reasons: list[str] = []
        if self.detections == 0:
            reasons.append(f"{self.frames} karenin hiçbirinde nesne "
                           f"tespit edilemedi")
        if (self.peak_motion_energy is not None
                and self.peak_motion_energy >= HIGH_MOTION_ENERGY):
            peak = f"{self.peak_motion_energy:.1f}".replace(".", ",")
            reasons.append(f"buna karşılık kare farkı zirvesi {peak} — "
                           f"görüntüde belirgin hareket var")
        return BLIND_TEMPLATE.format(reasons=", ".join(reasons))


def _events(episodes: list) -> list[EventSummary]:
    r"""Epizotları şartnamenin `events[]` listesine çevirir — **an başına bir
    olay**.

    Eskiden epizot başına tek bir satır üretiliyordu ve damgası PENCERENİN
    başlangıcıydı: 10 saniyelik bir pencerede yaşanan darbe, devrilme ve toz
    üçü de aynı `00:10` ile teslim ediliyordu, oysa görü kademesinin kendi
    yanıtı çökmenin klibin 3. saniyesinde başladığını söylüyordu. Şartnamenin
    örneği de birden çok ana işaret ediyor ("00:15 istif aracı devrildi",
    "00:20 yerde hareketsiz kişi").

    An listesi boş olan epizot eski davranışına düşüyor — tek satır, pencere
    başlangıcı damgasıyla. Bozulmuş bir görü kademesi hiç an üretmez ve o
    koşuda `events[]` bugünküyle birebir aynı kalır.

    Damga HER ZAMAN `mmss()` ile kuruluyor, hiçbir zaman modelin yazdığı
    metinden: `EventSummary.time` deseni (`^\d{2}:\d{2}$`) bunun mekanik
    güvencesi.
    """
    events: list[EventSummary] = []
    for episode in episodes:
        if not episode.beats:
            text = (FALLBACK_EVENT if episode.summary_source == "fallback"
                    else episode.summary_tr[:MAX_EVENT])
            events.append(EventSummary(time=mmss(episode.start_ts),
                                       event=text))
            continue
        events.extend(
            EventSummary(time=mmss(beat.ts), event=beat.text[:MAX_EVENT])
            for beat in sorted(episode.beats, key=lambda beat: beat.ts))
    return events


def build_output(store, summary: str, root_cause=None,
                 perception: PerceptionHealth | None = None) -> PipelineOutput:
    """Şartnamenin dört anahtarını üretir; her şey `detail` altında yanına
    eklenir, yerine değil.

    `risk` gerçek değerlendirmelerin en yükseği; hiç değerlendirme yoksa
    epizotların ÖN riskine düşülüyor. İkisi de yoksa `"Düşük"` — bir olay
    yaşanmadığı için, riski bilmediğimiz için değil.

    `perception` verildiğinde ve koşu **hiç epizot üretmediğinde** özet
    yeniden seçiliyor: kör bir koşu "kayda değer olay tespit edilmedi"
    diyemez, çünkü o cümle bir gözlem iddiasıdır ve gözlem yapılmamıştır.
    `risk` bu daldan etkilenmiyor — körlük bir alarm değil, bir itiraftır.

    `actions[]` yalnızca **gerçek bir araca bağlanmış** adaylardan türetiliyor.
    `gozcu.agents.risk` uydurma araç adlarını zaten düşürüyor; buradaki ikinci
    süzgeç, depoya başka bir yoldan (arşiv tohumlaması, elle yazılmış bir
    fikstür) girmiş bir öneriyi de kapsıyor. Sistemin çalıştıramayacağı bir
    öneri sadece bir cümledir: insanın okuduğu liste ile makinenin aksiyon
    defteri ayrışamaz.
    """
    episodes = store.episodes()
    risks = store.risks()

    # Sıfır epizot İKİ farklı şey olabilir ve ikisi aynı cümleyle
    # anlatılamaz: sahne gerçekten sakindi, ya da katman göremedi.
    # `perception` verilmemişse eski davranış aynen sürüyor.
    if not episodes and perception is not None and perception.blind:
        summary = perception.blind_summary()

    events = _events(episodes)

    levels = [r.level for r in risks] or [e.preliminary_risk for e in episodes]
    risk = max(levels, key=ORDER.index) if levels else DEFAULT_RISK

    actions: list[str] = []
    for assessment in risks:
        for action in assessment.proposed_actions:
            if action.tool_name in TOOLS and action.description_tr not in actions:
                actions.append(action.description_tr)

    return PipelineOutput(
        summary=summary, events=events, risk=risk, actions=actions,
        detail=Detail(
            episodes=episodes,
            risk_assessments=risks,
            handoff_chain=store.handoffs(),
            action_ledger=store.actions(),
            root_cause_report=(root_cause.model_dump() if root_cause is not None
                               else None)))
