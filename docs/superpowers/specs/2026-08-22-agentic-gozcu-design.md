# Agentic Gözcü — Design Spec

**Date:** 2026-08-22
**Deadline:** 2026-08-26 23:59 (GitHub upload). Code freeze 2026-08-25 20:00.
**Status:** approved design, pending implementation plan.

Prose is English per repo convention; domain identifiers stay Turkish, matching
the codebase and the required Turkish-language output.

## 1. Context

TEKNOFEST Yapay Zekâ Dil Ajanları Yarışması, 3rd scenario. We have a working
perception pipeline (`gozcu/`) and roughly three build days. This spec covers
what we build in those three days and — just as importantly — what we do not.

### What the şartname actually asks for

Four things in the team's earlier reading needed correcting. They shape every
decision below.

1. **The reference scenario is file upload, not a live stream.** *"Operasyon
   sahasında bir video sisteme yüklenir."* Expected output is static: a
   timestamped event list, an overall summary, a risk assessment, and action
   recommendations. Functionality (35%) scores *"belirtilen senaryoların ne
   kadar eksiksiz (uçtan uca) implemente edildiği."* Live streaming belongs to
   Innovation (10%), as a second input adapter — never as the primary path.

2. **20% of the score is operator dialogue.** The Autonomy criteria are
   verbatim: understanding intent and reasoning, *taking initiative and asking
   the right questions*, *responding to unexpected situations (context switch,
   errors)*, and *natural, human-like dialogue flow*. The demo video
   requirement repeats it: *"zorlu koşullar (örn: bağlam değişimi denemesi)"*
   and *"metin tabanlı etkileşim net olarak gösterilmelidir."* This is not a
   feature bolted onto a pipeline. It is a fifth of the grade.

3. **Mock functions are an explicitly scored deliverable.** Listed under
   deliverables (*"agent, mock fonksiyonlar, arayüz kodu, benchmark kodu"*),
   scored under Functionality (*"mock fonksiyonların ajanın araçları olarak
   başarıyla kullanılması"*) and again under Architecture (*"mock sistem
   entegrasyonunun başarısı"*, *"dinamik araç seçimi"*). Action recommendations
   must be tool calls the agent makes, not sentences an LLM writes.

4. **Domain: a defense-industry facility, which is a factory.** The şartname
   says *"savunma sanayi tesisleri veya saha operasyonları"* and the only
   concrete example it gives is a forklift tipping over with an injured worker
   and personnel gathering. A defense-industry *facility* is a production
   plant. We take the first branch of that "veya", not the second. Technical
   scope equals industrial workplace safety; the vocabulary, mock systems and
   presentation are dressed as a defense facility (vardiya amiri, saha telsizi,
   İSG kaydı, üretim hattı). This resolves the professor's standing
   scope-narrowing action item.

### Serving constraint

The organizers host all models on their own GPUs behind a LiteLLM gateway; we
reach them over an OpenAI-compatible API. `gozcu/interpret.py` already uses the
`openai` client with a configurable `base_url`, so this is a config change, not
a rewrite.

Two consequences drive the architecture:

- Every model call crosses the network onto a shared resource. Sending every
  frame to a VLM is not viable. Triggered interpretation is mandatory, not an
  optimization.
- The gateway is a dependency that can be slow or absent. Graceful degradation
  is scored twice — Architecture (*"hata işleme"*) and Autonomy (*"beklenmedik
  durumlara karşı tepki"*).

## 2. Model roster and tiering

Selections submitted to the organizers' survey. Where we diverge from their
recommendation (★) the reason is throughput on a shared gateway.

| Slot | Choice | Rationale |
|---|---|---|
| A — Main LLM | ★ Qwen3.5-122B-A10B | 10B active, 262K context, native VLM fallback |
| B — VLM | Qwen3-VL-30B-A3B (not ★) | Hot path; 3B active beats dense 32B on throughput. Interpretation is already grounded by YOLO detections and signals, so depth comes from Slot A, not here |
| C — Fast LLM | Qwen3.6-35B-A3B (not ★) | ★Qwen3.8-27B spends ~2× tokens — wrong trade in a slot named "fast" |
| D — Router | ★ Qwen3-8B | Tool-call support; our dispatch layer |
| D — Embedding | ★ Qwen3-Embedding-4B | 8B's marginal gain is not worth the latency |
| D — Reranker | ★ Qwen3-Reranker-4B | Same |
| D — Guard | ★ Qwen3Guard-Gen-4B | Cheap check on operator-facing text; answers the ethics clause |

All model ids live in a single config module. If the organizers deploy the ★
options instead, nothing but that file changes.

**Every decision falls to the cheapest model that suffices.**

| Layer | Model | Job | Frequency |
|---|---|---|---|
| Perception | YOLOE + ByteTrack (**local**) | Detection, tracking, velocity/vanish/count signals | Every frame |
| Router | Qwen3-8B | Is this important? Who handles it? Send to VLM? | High |
| Interpreter | Qwen3-VL-30B-A3B | Describe the triggered frame | On trigger |
| Synthesizer | Qwen3.6-35B-A3B | Observations → episode with phases, preliminary risk | Per episode |
| Memory | Embedding-4B + Reranker-4B | Semantic search over the episode timeline | Per query |
| Reasoning | Qwen3.5-122B-A10B | Operator dialogue, deep risk, root-cause report | Low |
| Guard | Qwen3Guard-4B | Screen operator-facing text | Per output |

This tiering is also the answer to *"Performans, Ölçeklenebilirlik ve
Verimlilik"*: cost-per-incident becomes measurable and presentable (§6).

## 3. Architecture — supervisor with expert sub-agents

Topology chosen over (a) a single ReAct agent and (b) four independent agents.
The deciding argument: 20% of the grade is dialogue, and in this topology the
dialogue agent is the centre of the system rather than a consumer at the end of
a chain. It also keeps all of (b)'s architectural claims — specialization,
multi-step chains, handoffs — with one fewer moving part.

### Components

**① Perception pipeline — not an agent.** `FrameSource` → `Gözlem`. Runs
locally. Emits timestamp, detections (class, bbox, track_id, confidence) and
signals (per-track velocity, vanished tracks, person count, gathering). We do
not market this as an agent; it is deterministic data production and is
described that way in the documentation.

**② Router — Qwen3-8B.** The attention mechanism. Input is a sliding window of
recent observations plus open-episode state. It sees the structured signal
summary, never images — that is why 8B suffices and why it is fast. Output:

```json
{ "karar": "yoksay | gorsel_incele | epizot_ac | epizot_guncelle | epizot_kapat | acil_yukselt",
  "gerekce": "...",
  "guven": 0.0 }
```

Making the trigger a model decision rather than a signal threshold is what
answers *"sabit kurallara dayalı basit bir pipeline yerine ... model tabanlı
karar mekanizmaları içeren bir mimari."*

**③ Interpreter — Qwen3-VL-30B-A3B.** Invoked only on `gorsel_incele`. Reuses
the existing `interpret.py` pattern: prompt grounded in detections and signals,
structured output.

**④ Synthesizer — Qwen3.6-35B-A3B.** Invoked on `epizot_kapat`. Observations
and interpretations become one `Epizot` record with başlangıç/gelişim/sonuç
phases, participants, a Turkish summary and a preliminary risk. This is where
frame independence is broken — the şartname's *"yalnızca kare bazlı analiz
etmekle sınırlı kalmamalı"* requirement, which today's `run.py` violates by
calling `describe_frame` per frame.

**⑤ Nöbetçi (supervisor) — Qwen3.5-122B-A10B.** The agent the operator talks
to. Proactive (surfaces Router escalations itself) and reactive. Tools:
`zaman_cizelgesi_ara`, `epizot_detay`, `risk_analizi_iste`,
`kok_neden_raporu_uret`, `gozlem_duzelt`, plus the seven mock system tools.
Dynamic tool selection is observable here.

**⑥ Risk Analisti (expert sub-agent) — Qwen3.5-122B.** Episode plus historical
context it retrieves itself. Output: seviye (Düşük/Orta/Yüksek/Kritik),
gerekçe, preventability, and candidate actions **each mapped to a tool**.

**⑦ Raportör (expert sub-agent) — Qwen3.5-122B.** Episode chain, risk
assessments, dialogue transcript and action ledger become a Turkish root-cause
report.

**Guard — Qwen3Guard-4B** wraps operator-facing text.

### Handoff protocol

Nothing crosses an agent boundary as free text. Every handoff is a typed record
written to the event store: `kaynak_ajan`, `hedef_ajan`, `neden`, `guven`,
`zaman`, `payload_ref`.

Three payoffs: concrete evidence for *"bağlam yönetimi"* and *"çok adımlı karar
zincirleri"*; a test assertion point at every boundary; and explainability —
the handoff ledger renders in the UI, so *"sistem çıktıları mümkün olduğunca
açıklanabilir olmalıdır"* is answered by a traceable decision chain on screen
rather than a claim in a slide.

## 4. Data model and memory

**Store: SQLite, single file.** No setup, reproducible, `git clone` and one
command.

| Table | Contents |
|---|---|
| `gozlem` | ts, detections, signals |
| `yorum` | gozlem_id, description, notable_event, model, latency_ms, tokens |
| `epizot` | start/end ts, phase, Turkish summary, participants, preliminary risk, state |
| `epizot_embedding` | epizot_id, vector |
| `risk_degerlendirme` | epizot_id, level, rationale, preventability, candidate actions |
| `devir` | source, target, reason, confidence — the decision-chain ledger |
| `aksiyon_defteri` | tool, params, result, actor (agent/operator), approval state |
| `diyalog` | role, text |
| `duzeltme` | operator corrections: target, field, old, new, rationale |

**`zaman_cizelgesi_ara(sorgu, zaman_araligi)`:** embed query → cosine over
`epizot_embedding` → top-20 → Qwen3-Reranker-4B → top-5.

No vector database. A shift produces a few hundred episodes; brute-force cosine
in numpy is instantaneous. A FAISS or Chroma dependency is install risk for
zero gain on this data size.

**On the memory claim.** We embed *episode records* (text), not video segments.
Each record already contains the VLM description, detections and signals — a
distilled multimodal representation. We do not have API access to a video
encoder and will not claim one. This still delivers the professor-validated
thesis: connecting a morning event to an evening consequence, past what fits in
a context window.

**`duzeltme` is the core of the 20% criterion.** When the operator says "that
is not a forklift, it is a stacker crane", it does not evaporate as a chat
message — it is recorded, and subsequent retrievals and reports reflect it.
Context management that can be demonstrated, not asserted.

## 4b. Primary output contract

The upload path is the scenario the jury scores under Functionality (35%), so
its top-level JSON must match the şartname's own example shape exactly —
`summary`, `events[].time`, `events[].event`, `risk`, `actions[]`. A grader
comparing our output to their mock example should see the same keys.

```json
{
  "summary": "B-Hattı sevkiyat alanında istif aracı devrilmesi ve yaralanma riski gözlenmiştir.",
  "events": [
    {"time": "00:15", "event": "İstif aracı devrildi"},
    {"time": "00:20", "event": "Yerde hareketsiz kişi"}
  ],
  "risk": "Yüksek",
  "actions": ["Sağlık ekibini çağır", "Alanı güvenlik altına al"]
}
```

Everything this spec adds — episodes with phases, handoff ledger, risk
rationale, action ledger, root-cause report — is served **alongside** that
contract under an `ayrintili` key, never in place of it:

```json
{ "summary": "...", "events": [...], "risk": "...", "actions": [...],
  "ayrintili": { "epizotlar": [...], "risk_degerlendirmeleri": [...],
                 "devir_zinciri": [...], "aksiyon_defteri": [...],
                 "kok_neden_raporu": {...} } }
```

Two rules follow. The four required keys are produced even when the extended
layers fail or are skipped — a degraded run still returns a valid, gradeable
result. And `actions[]` strings are rendered from the tool calls the Risk
Analisti actually mapped, so the human-readable list and the machine action
ledger cannot drift apart.

## 5. Mock systems — seven tools

Typed parameters, structured mock responses, automatically logged to
`aksiyon_defteri`. Fixture databases are small JSON files and form part of the
published dataset.

**Read tools — these feed reasoning:**

| Tool | Returns | Why it matters |
|---|---|---|
| `vardiya_personel_sorgula(bolge, zaman)` | Personnel on shift, roles, **certifications** | Enables "this person is not licensed for a forklift" |
| `ekipman_gecmisi_sorgula(ekipman_id)` | Maintenance and fault history | The backbone of root-cause: "brake service is 4 months overdue" |

**Action tools:**

| Tool | Returns |
|---|---|
| `saha_telsiz_cagrisi(birim, mesaj)` | `{cagri_id, durum, yanit_bekleniyor}` |
| `saglik_ekibi_cagir(konum, aciliyet, aciklama)` | `{talep_id, tahmini_varis_dk, ekip}` |
| `saha_alarmi(bolge, seviye)` | `{alarm_id, etkilenen_bolge, siren_durumu}` |
| `isg_olay_kaydi_ac(epizot_id, siniflandirma, aciklama)` | `{kayit_no, durum}` |
| `uretim_hatti_durdur(hat_id, gerekce)` | **requires operator approval** → `{onay_bekliyor}` → `{durum}` |

Two deliberate choices. Mixing read and action tools makes tool selection a
real decision — query first or act first is a genuine judgment call, and that
is where *"dinamik araç seçimi"* becomes visible. And `uretim_hatti_durdur`
requires operator approval: the agent does not take a costly, hard-to-reverse
action alone.

## 6. Dialogue scenario, KPIs and benchmark

### The scenario is simultaneously the demo script and the acceptance test

Setting: defense-industry production facility, B-Hattı dispatch area; the
forklift clip from `data/`.

1. **Proactive alert — initiative.** Router escalates on velocity plus track
   loss. Nöbetçi speaks first, having already called
   `vardiya_personel_sorgula`: incident, risk level, who is on shift, proposed
   actions.
2. **Asking the right question — knowing its own limits.** *"Is the person on
   the ground moving? I cannot tell from this camera angle."* A camera-only
   system cannot rule on consciousness; the agent asks instead of fabricating,
   then assumes worst case and calls `saglik_ekibi_cagir`.
3. **Operator correction — context management.** "That is a stacker crane, not
   a forklift." `gozlem_duzelt` → `duzeltme` → risk re-assessed under a
   different İSG classification → `ekipman_gecmisi_sorgula` re-run for the new
   equipment. The correction propagates to the final report.
4. **Context switch — the şartname's named hard condition.** "Drop that — did
   something similar happen on C-Hattı last night?" Nöbetçi answers via
   `zaman_cizelgesi_ara` and returns to the open incident unprompted. One beat,
   three criteria.
5. **Error injection — response to the unexpected.** We cut the gateway
   deliberately during the demo. The system reports the degradation, keeps the
   local perception layer running, queues interpretation, continues
   signal-based critical alerts, and catches up on reconnection. Scores under
   both Architecture and Autonomy.
6. **Closure — root-cause report.** Timestamped chain, probable cause from
   equipment history, actions taken from the ledger, prevention
   recommendations, **and a statement of the system's own confidence limits** —
   the professor's "calibrated estimate, not a verdict" written into the
   deliverable.

These six beats become `tests/test_dialog_senaryo.py`: scripted operator turns
asserting tool order, correction propagation, and that the open episode
survives the context switch. Demo script and regression suite are one artifact.

### KPIs

The existing `kpis.md` targets are unreachable in three days (they assume
ground truth for hundreds of events). Replaced by three families:

**A. Event capture** — ~15 clips hand-labelled (incident yes/no, start_s,
end_s, type); about one person-hour. Critical-event capture rate, median
timestamp deviation, false alarm rate.

**B. Agent behaviour** — no ground truth needed, computed from the ledgers.
Handoff accuracy against expected chains; **correction propagation** (target
100%, asserted automatically); context retention after a switch; tool-selection
match.

**C. Efficiency** — free, because `devir` and `yorum` already record tokens and
latency. Decision distribution across the 8B/35B/122B tiers; **VLM trigger rate
(target <5% of frames)**, the numeric proof that we do not send every frame to
a model; tokens and latency per incident by model; local perception FPS;
alerting continuity in degraded mode.

Deliverable: `benchmark/run.py` and `benchmark/report.py` producing markdown
plus charts. One chart goes on a slide — the decision-distribution pyramid.

## 7. Scope

### Frozen — no new features in the perception layer

`frames.py`, `detect.py`, `track.py`, `signals.py`, `interpret.py` stay as they
are. The known quality gaps (no hazard class in YOLO, generic VLM descriptions)
are **accepted and documented as known limits**. The rubric has no separate
line for vision quality; 70% of it is agent architecture and scenario
completeness, and that is where every remaining hour goes.

### Cut

V-JEPA2 · vector DB / video embeddings · Turkish-LLM-14B migration · YOLO
fine-tuning · Whisper/audio · multi-video sync · voice interaction (şartname
says *"varsa"*, optional) · PDF export · configuration panel.

### Streaming mode

The `FrameSource` abstraction is built regardless. "Streaming mode" is a
timer-driven file source — roughly two hours, and it makes the demo feel live.
**We do not claim RTSP without testing it.** Documentation says "file-backed
streaming mode; an RTSP adapter uses the same interface."

## 8. Work split

Three build days, 2–3 people. **Code freeze 2026-08-25 20:00** — after that,
bug fixes and packaging only.

| | Track 1 — Core | Track 2 — Agents & Tools | Track 3 — UI & Deliverables |
|---|---|---|---|
| **23 Aug** | Event store; gateway client (tiering config, retry/timeout, **degraded mode**); `FrameSource`; Router | Seven mock tools, fixture DBs, action ledger | Operator console: video, live timeline, chat panel |
| **24 Aug** | Synthesizer and `Epizot`; memory search (embedding + reranker) | Nöbetçi supervisor (tool-call loop, proactive channel); Risk Analisti | Benchmark harness; ~15-clip ground truth |
| **25 Aug** | Integration; error-injection mode; stability | Raportör and root-cause report; Guard wrapper | Handoff-ledger view; KPI report; demo filming |
| **26 Aug** | Packaging — everyone | | |

**26 August:** ≤10-minute demo video (the six beats); a separate 1-minute demo
for the live presentation; documentation (architecture diagram, setup, agentic
framework and LLM list, implemented scenarios and mock functions, challenges
encountered, measurement results, scaling needs); slides in **PDF and PPTX**;
GitHub with Apache 2.0, the `BilisimVadisi2026` tag, the "Türkiye Açık Kaynak
Platformu" tag, an open dataset link, and a dependency list.

**If only two people:** benchmark slips to the 25th and the handoff-ledger
visualization is sacrificed — the lowest-scoring item on the list.

## 9. Risks

| Risk | Mitigation |
|---|---|
| Final model roster not confirmed | All model ids in one config module |
| Unknown whether Qwen3-VL accepts video or frames | Frames first (existing code works); upgrade on the 24th if video is supported |
| 122B latency unknown | Nöbetçi streams its response; the operator never watches a blank screen |
| Shared gateway contention | Degraded mode is a designed feature, demonstrated in beat 5 |
| Gateway vs. *"tamamen yerel ortamda çalışmalıdır"* | Written confirmation requested from the competition group; local perception layer strengthens the argument |

## 10. Open questions for the organizers

1. Does the gateway serve a vision model, and what is the exact model list?
2. Rate limits, concurrency caps, token quotas?
3. Is the gateway reachable during the physical final at Bilişim Vadisi
   Kocaeli, and what is the fallback if not?
4. Written confirmation that gateway use satisfies the local-operation clause.

None of these block implementation — the architecture's local/gateway boundary
holds under either answer to (1).
