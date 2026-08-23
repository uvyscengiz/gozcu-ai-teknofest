# Görev 01 — Paylaşılan sözleşme (`gozcu/models.py`)

> ## ✅ TAMAMLANDI — 23 Ağustos 2026, `fdfd393`
>
> **Sözleşme indi.** `gozcu/models.py` var, `tests/test_models.py` 4 test ile
> yeşil. Bu dosyayı yeniden uygulama — aşağısı ne yapıldığının kaydı.
>
> **Sonraki göreve başlarken bilmen gerekenler**
> ([kararlar](#tamamlanma-notları-gelecek-görevleri-bağlayan) bölümüne bak):
> beşinci anahtar `ayrintili` değil **`detail`**; `Detection` alan adları donuk
> algı katmanınınkilerle aynı değil, Görev 17 çevirecek.

**Sahip:** `uvyscengiz` · **Gün:** 23 Ağustos · **Süre:** ~1.5 saat
**Bağımlılık:** [00](00-test-altyapisi.md)

## Bağlam

Sistemdeki her modül birbirine tipli kayıtlar geçiriyor — serbest metin değil.
Bu dosya o kayıtların tamamını tanımlıyor. Diğer 17 görev bu tiplere karşı kod
yazacak, o yüzden **ilk bu iniyor** ve sonradan değişmiyor.

Bir tip eksik çıkarsa buraya eklenir; hiçbir görev modül sınırını geçen kendi
tipini uydurmaz.

## Kurulum

```bash
uv sync --extra dev
```

## Ne yapacaksın

`gozcu/models.py` dosyasını oluştur. Pydantic v2, hepsi `extra="forbid"`.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_models.py`

```python
import pytest
from pydantic import ValidationError

from gozcu.models import Episode, PipelineOutput, RouterDecision, Signals


def test_router_decision_rejects_unknown_decision():
    with pytest.raises(ValidationError):
        RouterDecision(decision="belki", rationale="x", confidence=0.5)


def test_episode_requires_known_risk_level():
    with pytest.raises(ValidationError):
        Episode(start_ts=0.0, phase="onset", summary_tr="x",
               preliminary_risk="High", state="open")


def test_pipeline_output_has_the_four_sartname_keys():
    c = PipelineOutput(summary="özet", events=[], risk="Yüksek", actions=[])
    assert set(c.model_dump(exclude_none=True)) == {
        "summary", "events", "risk", "actions"}


def test_signals_defaults_are_empty_not_none():
    s = Signals()
    assert s.velocities == {} and s.vanished_tracks == [] and s.person_count == 0
```

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_models.py -v
```
Beklenen: `ModuleNotFoundError: No module named 'gozcu.models'`

### 3. `gozcu/models.py` yaz

```python
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
```

`person_count_delta` mevcut `signals.py`'daki `person_count_delta`'nın karşılığı —
donuk algı katmanı bunu zaten hesaplıyor, kaybetmeyelim. `gathering` ise
`signals.py`'da **hesaplanmıyor**; Görev 17'deki adaptör onu
`person_count >= 3` kuralıyla türetecek.

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_models.py -v
```
Beklenen: 4 passed

### 5. Commit

```bash
git add gozcu/models.py tests/test_models.py
git commit -m "feat: shared Pydantic contract for the agent layer"
```

## Doğrulama

```bash
uv run pytest tests/test_models.py -v
```
Beklenen: **4 passed**

## Tamamlanma notları (gelecek görevleri bağlayan)

- **Beşinci anahtar `detail`, `ayrintili` değil.** Bu dosya ve Görev 17 önce
  `ayrintili` yazıyordu; sınıf adı (`Detail`) ve bütün alt anahtarlar
  (`episodes`, `risk_assessments`, …) zaten İngilizceydi. CLAUDE.md'nin
  değişmez kuralı JSON anahtarlarının İngilizce olmasını istiyor ve anahtarı
  adıyla `detail` diye anıyor — yarım kalmış bir geçişti, tamamlandı. Görev 17
  buna göre güncellendi.
- **`Detection` alan adları donuk algı katmanınınkilerle aynı değil.**
  `detect.DetectedObject` / `track.TrackedObject` `class_name`, `bbox`
  (`tuple[int, ...]`) kullanıyor; sözleşme `label`, `box` (`tuple[float, ...]`)
  diyor. Algı katmanı donuk olduğu için **çeviri Görev 17'nin adaptöründe**
  yapılacak: `class_name→label`, `bbox→box`, int→float. `confidence` ve
  `track_id` birebir.
- **`Signals` alan adları `signals.FrameSignals` ile birebir**
  (`velocities`, `vanished_tracks`, `person_count`, `person_count_delta`) —
  adaptörde düz kopya. Tek istisna `gathering`: algı katmanı hesaplamıyor,
  Görev 17 `person_count >= 3` kuralıyla türetiyor.
- **Testler tamamen İngilizce adlandırıldı.** Bu dosyadaki taslak
  `test_router_karari_…` gibi karışık adlar taşıyordu; CLAUDE.md fonksiyon
  adlarının İngilizce olmasını istiyor. Doğrulama sayısı değişmedi: 4 passed.
- **`extra="forbid"` her tipte.** `Base`'den miras alınıyor; yeni bir tip
  eklerken `Base`'i genişlet, `BaseModel`'i değil — yoksa şema sessizce
  gevşer.
