"""Ajan katmanının paylaşılan sözleşmesi.

Modül sınırını geçen her kayıt burada tanımlı. Hiçbir görev kendi tipini
uydurmaz — eksik bir tip varsa buraya eklenir.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RiskLevel = Literal["Düşük", "Orta", "Yüksek", "Kritik"]
AgentName = Literal["perception", "router", "interpreter", "synthesizer",
                    "risk_analyst", "supervisor", "reporter"]


class Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Detection(Base):
    label: str
    confidence: float
    box: tuple[float, float, float, float]
    track_id: int | None = None


class Signals(Base):
    velocities: dict[int, float] = Field(default_factory=dict)
    vanished_tracks: list[int] = Field(default_factory=list)
    person_count: int = 0
    person_count_delta: int = 0
    gathering: bool = False


class Observation(Base):
    id: int | None = None
    ts: float
    detections: list[Detection] = Field(default_factory=list)
    signals: Signals = Field(default_factory=Signals)


class RouterDecision(Base):
    decision: Literal["ignore", "inspect", "open_episode",
                      "update_episode", "close_episode", "escalate"]
    rationale: str = Field(max_length=200)
    confidence: float = Field(ge=0.0, le=1.0)


class Interpretation(Base):
    id: int | None = None
    observation_ts: float
    description: str = Field(max_length=300)
    notable_event: str | None = Field(default=None, max_length=200)
    model: str
    latency_ms: int = 0
    tokens: int = 0


class Episode(Base):
    id: int | None = None
    start_ts: float
    end_ts: float | None = None
    phase: Literal["onset", "development", "outcome"]
    summary_tr: str = Field(max_length=600)
    participants: list[str] = Field(default_factory=list)
    preliminary_risk: RiskLevel
    state: Literal["open", "closed"] = "open"


class ProposedAction(Base):
    description_tr: str = Field(max_length=200)
    tool_name: str
    params: dict = Field(default_factory=dict)


class RiskAssessment(Base):
    id: int | None = None
    episode_id: int
    level: RiskLevel
    rationale_tr: str = Field(max_length=800)
    preventable: bool
    proposed_actions: list[ProposedAction] = Field(default_factory=list)


class Handoff(Base):
    id: int | None = None
    ts: float
    source_agent: AgentName
    target_agent: AgentName
    reason: str = Field(max_length=200)
    confidence: float = Field(ge=0.0, le=1.0)
    payload_ref: str


class ActionRecord(Base):
    id: int | None = None
    ts: float
    tool_name: str
    params: dict = Field(default_factory=dict)
    result: dict = Field(default_factory=dict)
    actor: Literal["agent", "operator"]
    approval: Literal["not_required", "pending", "approved", "rejected"]


class Correction(Base):
    id: int | None = None
    ts: float
    episode_id: int
    field: str
    old: str
    new: str
    rationale: str = Field(max_length=300)


class DialogueTurn(Base):
    id: int | None = None
    ts: float
    role: Literal["operator", "supervisor", "system"]
    text: str


class EventSummary(Base):
    time: str = Field(pattern=r"^\d{2}:\d{2}$")
    event: str = Field(max_length=200)


class Detail(Base):
    episodes: list[Episode] = Field(default_factory=list)
    risk_assessments: list[RiskAssessment] = Field(default_factory=list)
    handoff_chain: list[Handoff] = Field(default_factory=list)
    action_ledger: list[ActionRecord] = Field(default_factory=list)
    root_cause_report: dict | None = None


class PipelineOutput(Base):
    summary: str
    events: list[EventSummary] = Field(default_factory=list)
    risk: RiskLevel
    actions: list[str] = Field(default_factory=list)
    detail: Detail | None = None
