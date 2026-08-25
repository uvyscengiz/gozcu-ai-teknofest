"""Çıktı sözleşmesinin derleyicisi — jürinin okuduğu dört anahtar.

Şartnamenin puanladığı çıktı şu dört anahtardan oluşuyor: `summary`,
`events`, `risk`, `actions`. **Dördü diğer her şey çökse bile üretilir.**
Eklediğimiz her katman — fazlı epizotlar, devir defteri, risk gerekçeleri,
aksiyon defteri, kök neden raporu — `detail` altında onların YANINDA duruyor,
yerine değil.

Bu modül hiçbir model çağırmıyor: elindeki tek malzeme depo. Bozulmuş bir
koşuda da tam olarak aynı işi yapıyor, sadece daha az veriyle.
"""

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


def build_output(store, summary: str, root_cause=None) -> PipelineOutput:
    """Şartnamenin dört anahtarını üretir; her şey `detail` altında yanına
    eklenir, yerine değil.

    `risk` gerçek değerlendirmelerin en yükseği; hiç değerlendirme yoksa
    epizotların ÖN riskine düşülüyor. İkisi de yoksa `"Düşük"` — bir olay
    yaşanmadığı için, riski bilmediğimiz için değil.

    `actions[]` yalnızca **gerçek bir araca bağlanmış** adaylardan türetiliyor.
    `gozcu.agents.risk` uydurma araç adlarını zaten düşürüyor; buradaki ikinci
    süzgeç, depoya başka bir yoldan (arşiv tohumlaması, elle yazılmış bir
    fikstür) girmiş bir öneriyi de kapsıyor. Sistemin çalıştıramayacağı bir
    öneri sadece bir cümledir: insanın okuduğu liste ile makinenin aksiyon
    defteri ayrışamaz.
    """
    episodes = store.episodes()
    risks = store.risks()

    events = [EventSummary(time=mmss(episode.start_ts),
                           event=episode.summary_tr[:MAX_EVENT])
              for episode in episodes]

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
