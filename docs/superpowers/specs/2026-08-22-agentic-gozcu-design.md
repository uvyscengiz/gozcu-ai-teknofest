# Agentic Gözcü — Design Spec

**Date:** 2026-08-22 · **Revised:** 2026-08-23
**Deadline:** 2026-08-26 23:59 (GitHub upload). Code freeze 2026-08-26 12:00.
**Status:** approved design, pending implementation plan.

Prose is English per repo convention; domain identifiers stay Turkish, matching
the codebase and the required Turkish-language output.

## 1. Context

TEKNOFEST Yapay Zekâ Dil Ajanları Yarışması, 3rd scenario. We have a working
perception pipeline (`gozcu/`), two solo build days and two team days. This spec covers
what we build in those three days and — just as importantly — what we do not.

### What the şartname actually asks for

Four things in the team's earlier reading needed correcting. They shape every
decision below.

1. **The reference scenario is file upload, not a live stream.** *"Operasyon
   sahasında bir video sisteme yüklenir."* Expected output is static: a
   timestamped event list, an overall summary, a risk assessment, and action
   recommendations. Functionality (35%) scores *"belirtilen senaryoların ne
   kadar eksiksiz (uçtan uca) implemente edildiği."* **The input is an uploaded
   video file, full stop.** Live camera input is cut entirely — see §3a for why
   we lose nothing by cutting it.

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

### 3a. Decision timing — in flight, not post-hoc

The single most consequential choice in this design. Processing an uploaded
video admits two shapes:

**Watch, then summarize.** Run the video end to end, emit a report, discuss
actions afterwards. This is a *summarization* system. There is no decision
moment in it — only a finished text — so it cannot demonstrate multi-step
decision chains, dynamic tool selection, or initiative. Three scored criteria,
all unreachable.

**Decide on the video's own clock.** The system advances along the video's
timeline and, when it reaches a critical moment, **stops there**: it assesses
risk, queries shift records and equipment history, addresses the operator,
proposes an action and — on approval — calls the field system. The video has
not finished. This is a *decision support* system, which is what the şartname
asks for by name.

We take the second. Tool calls fire at the moment of the event inside the
video's timeline, not after the report. The operator sits inside that loop and
can interject, correct, approve or refuse mid-run. The closing JSON and
root-cause report are the *conclusion* of that loop, not a substitute for it.

This is also why cutting live camera input costs us nothing: the decision loop
already runs on a moving clock. The only thing a live source would change is
where frames come from.

### Components

**① Perception pipeline — not an agent.** `FrameSource` → `Gözlem`. Runs
locally. Emits timestamp, detections (class, bbox, track_id, confidence) and
signals (per-track velocity, vanished tracks, person count, gathering). We do
not market this as an agent; it is deterministic data production and is
described that way in the documentation.

**② Router — Qwen3-8B.** The attention mechanism. It sees a structured signal
digest, never images — that is why 8B suffices and why it is fast. Output:

```json
{ "karar": "yoksay | gorsel_incele | epizot_ac | epizot_guncelle | epizot_kapat | acil_yukselt",
  "gerekce": "...",
  "guven": 0.0 }
```

**It runs on 10-second windows, not on frames.** Per-frame routing would mean
roughly 600 model calls for a 10-minute video and would sink the throughput
claim on its own; windowed, the same video costs about 60. Local signals apply
a floor beneath that — a window in which nothing moved never reaches the model
at all.

That floor is not a rule deciding what matters. It decides *when to ask*; the
model decides *what is important*. Every physical alarm system is built this
way and nobody calls a motion sensor rule-based AI. Making the escalation
judgment a model decision rather than a threshold is what answers *"sabit
kurallara dayalı basit bir pipeline yerine ... model tabanlı karar
mekanizmaları içeren bir mimari."*

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
the vehicle did not tip over, the load fell", it does not evaporate as a chat
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
forklift clip from `data/`. Eight beats, in the order the demo video shows them.

0. **Upload — the input.** The night's footage is uploaded. The timeline begins
   filling. The system stays quiet, because nothing yet warrants attention.
1. **Proactive alert — initiative.** Router escalates on velocity plus track
   loss. Nöbetçi speaks first, having already called
   `vardiya_personel_sorgula`: incident, risk level, who is on shift, proposed
   actions.
2. **Asking the right question — knowing its own limits.** *"Is the person on
   the ground moving? I cannot tell from this camera angle."* A camera-only
   system cannot rule on consciousness; the agent asks instead of fabricating,
   then assumes worst case and calls `saglik_ekibi_cagir`.
3. **Operator correction — context management.** *"The vehicle did not tip
   over, the load fell."* A distinction a camera genuinely can confuse.
   `gozlem_duzelt` → `duzeltme` → İSG classification changes → risk
   re-assessed → `ekipman_gecmisi_sorgula` re-run. The correction propagates
   all the way to the final report.

   The correction must be one the system could plausibly have gotten wrong. An
   operator overriding the system with something the footage plainly
   contradicts would demo the opposite of what we want — that the operator can
   corrupt the record — and a sharp juror will ask exactly that.
4. **Field system called mid-video — the decision moment.** Nöbetçi opens the
   İSG record itself (`isg_olay_kaydi_ac`), pulls maintenance history
   (`ekipman_gecmisi_sorgula` → brake service four months overdue), and then
   **asks permission** before `uretim_hatti_durdur`. The video has not
   finished. This is the beat that separates decision support from
   summarization, and it is the reason §3a exists.
5. **Context switch — the şartname's named hard condition.** "Drop that — has
   there been an earlier incident with this vehicle?" Nöbetçi answers via
   `zaman_cizelgesi_ara` and returns to the open incident unprompted. One beat,
   three criteria.
6. **Error injection — response to the unexpected.** We cut the gateway
   deliberately during the demo. The system reports the degradation, keeps the
   local perception layer running, defers the skipped windows, continues
   signal-based critical alerts, and replays the deferred windows on
   reconnection (`DecisionLoop.catch_up`). Scores under both Architecture and
   Autonomy.
7. **Closure — two reports.** The structured JSON lands first, shown side by
   side with the şartname's own mock example to make the key match visible
   (§4b). Then the root-cause report: timestamped chain, probable cause from
   equipment history, actions taken from the ledger, prevention
   recommendations, **and a statement of the system's own confidence limits** —
   a calibrated estimate, not a verdict, written into the deliverable.

These eight beats become `tests/test_dialog_senaryo.py`: scripted operator turns
asserting tool order, correction propagation, and that the open episode
survives the context switch. Demo script and regression suite are one artifact.

**Beats 4, 5 and 7 depend on a seeded facility world** — personnel with
certifications, an equipment inventory, maintenance history with the overdue
brake service, and at least one prior incident in the archive. Without it beat
5 has nothing to retrieve and beat 7's root cause comes back empty. This is
assigned work (§8), not a fixture that appears by itself, and it doubles as
part of the published open dataset.

### Presentation thesis

Four minutes cannot carry four claims. The headline is one sentence:

> **The system decides while it watches — it does not summarize after
> watching.**

Supported by a single number: **the share of decisions that close at the 8B
router** (target ~89%), from the efficiency KPIs below. Memory, degraded mode
and the root-cause report stay as supporting arguments — offered if asked,
never in the headline.

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

**Live camera / RTSP input** · V-JEPA2 · vector DB / video embeddings ·
Turkish-LLM-14B migration · YOLO fine-tuning · Whisper/audio · multi-video sync
· voice interaction (şartname says *"varsa"*, optional) · PDF export ·
configuration panel.

RTSP is cut outright rather than shipped untested. The `FrameSource`
abstraction still exists — it is how the decision loop reads frames — so the
documentation may state that a live source would plug into the same interface.
It may not claim a tested live mode, because there will not be one.

## 8. Work split

Not three days with four people. **Two solo days, then two team days.**

Task numbers below refer to [docs/tasks/](../../tasks/README.md), where each
task is a self-contained mini-PRD. That directory is the executable form of this
section; if the two ever disagree, the task files win.

| Day | Üveys (`uvyscengiz`) | `Xana-bit` | `beyzaalive` | `rumeysaoru` |
|---|---|---|---|---|
| **23 Aug** | 00 test harness · 01 contract · 02 store · 03 gateway · 05 decision loop | — | — | — |
| **24 Aug** | 04 interpreter · 06 router · 07 synthesizer · console skeleton · wire `run.py` | — | — | — |
| **25 Aug** | 08 memory · 11 risk analyst · 14 **Nöbetçi** | 09 facility world · 10 field tools | 12 reporter · 13 guard | 16 operator console |
| **26 Aug am** | 17 output contract · end-to-end rehearsal | demo filming | Turkish style pass | 15 KPIs · benchmark run |
| **26 Aug pm** | **18 packaging — everyone.** Code freeze 12:00 | | | |

**The 24 August exit criterion is the whole plan's hinge:** by the end of the
second solo day, one uploaded video must run end to end and produce the
four-key JSON, visible in the UI. If that does not hold, three people arrive on
the 25th to an empty scaffold instead of a working system, and there is no
recovery from that with one day left.

**Load cannot be equal and pretending otherwise would be a planning error.**
Üveys works four days, everyone else two. What is balanced is the *team days* —
each of the other three gets roughly two person-days of work on the 25th–26th.

**Task selection for the three who arrive on the 25th is deliberate.** Tasks 09,
10, 12, 13 and 15 sit entirely off the integration path: the field tools are
plain Python functions that call no model, the fixtures are JSON, the KPIs are
pure functions over the store, the guard is fifteen lines. Each is verified by a
single test command and none blocks anyone else. Nöbetçi (14) and integration
(17) stay with Üveys because they require knowing the system.

**File ownership prevents conflicts.** `gateway.py` is touched by Tasks 03 and 08, `config.py` by 03, `run.py` and
`app.py` by 17 — all Üveys. Everyone arriving on
the 25th works in files that do not yet exist. Fully async, no coordination
needed beyond the interface reference in the plan.

**26 August:** ≤10-minute demo video (the eight beats); a separate 1-minute demo
for the live presentation; documentation (architecture diagram, setup, agentic
framework and LLM list, implemented scenarios and mock functions, challenges
encountered, measurement results, scaling needs); slides in **PDF and PPTX**;
GitHub made public with Apache 2.0, the `BilisimVadisi2026` tag, the "Türkiye
Açık Kaynak Platformu" tag, an open dataset link, and a dependency list.

## 9. Risks

| Risk | Mitigation |
|---|---|
| Final model roster not confirmed | All model ids in one config module |
| Unknown whether Qwen3-VL accepts video or frames | Frames first (existing code works); upgrade on the 24th if video is supported |
| 122B latency unknown | The console renders each tool call as it happens ("querying the shift roster…"), so the operator sees progress rather than a blank screen. Token-level streaming is not implemented |
| Shared gateway contention | Degraded mode is a designed feature, demonstrated in beat 6 |
| Gateway vs. *"tamamen yerel ortamda çalışmalıdır"* | The organizers host and mandate the gateway, so the models are local to the sanctioned setup; our own perception layer runs locally too. Argued in the documentation, not escalated |
| Demo depends on the seeded facility world | Task 09, assigned to `Xana-bit` on 25 Aug; beats 4, 5 and 7 fail without it |
| **Onboarding, not code, is the biggest risk** | Three people join on 25 Aug, one day before the deadline, on a codebase they have never seen. Mitigations: the 24 Aug exit criterion gives them a running system; their tasks are off the integration path; every issue carries a cold-start context block and a single verification command |
| A solo day slips and 24 Aug closes with no working slice | Cut Task 07 (synthesizer) before cutting integration. A thin slice with crude episodes still gives the team something to plug into; six polished modules that do not run together do not |

## 10. Open items

Nothing here blocks implementation; the design absorbs either answer.

| Item | How the design absorbs it |
|---|---|
| Whether the gateway's vision model accepts video or single frames | Frames first — that is the path that works today. If video is supported, upgrade on the 24th; the interpreter's interface does not change |
| Large-model response latency | The console surfaces tool calls live while the supervisor works; no token-level streaming, and none is claimed |
| Track owners and the exact headcount | The grid assumes three tracks. At two people, benchmark slips to the 25th and the handoff-ledger view is dropped — the lowest-scoring item on the list |
