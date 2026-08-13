# Decision Log

This reconciles the team's original technical research document against the 2026-08-13 mentor call. Where the call confirmed, corrected, or overrode something in the original plan, that's marked explicitly. Treat this file as the plan of record — it supersedes the research doc wherever they conflict.

## Competitive positioning

- **Original framing (research doc + early call):** differentiate by producing maximally detailed, multi-theory, multi-line interpretive reports (e.g. bomb-blast severity estimation) vs. competitors' assumed single-line reports; also an early assumption that *all* teams the professor advises are direct competitors on the same approach.
- **Correction:** the "all teams = same approach" assumption was wrong — there are 3 competition categories, and only category-3 teams (video-in, report-out) are actually comparable competitors. See [00-overview/project-overview.md](../00-overview/project-overview.md#competition-category-clarification).
- **Correction:** "more detail = more advantage" is not a safe framing on its own. Doing maximally deep interpretation across an *unbounded* domain (bomb analysis one moment, forklift speed the next, a kitchen mishap after that) increases failure surface even on simple cases, because there's no defined scope. **Decision: narrow the domain for the competition submission**, most likely to industrial/factory workplace-safety incidents, and explicitly state in the writeup that broader generalization is planned future work rather than claiming the broad scope as a current capability.
- **Status:** open — team acknowledged even "factory workplace accident" alone is still fairly broad; exact scope boundary still needs to be nailed down. Track in [action-items.md](action-items.md).

## Memory as the innovation angle

- **Original framing:** batch per-minute summaries into 10-minute chunks, then summarize batches of 10-minute chunks, to build a long-horizon running context — enabling the system to connect a morning event to an evening consequence.
- **Professor's correction to a supporting assumption:** the premise "AI already has memory as good as or better than ours" is false — current LLMs have underdeveloped memory (bounded by attention/context-window length, nothing more).
- **Professor's validation of the plan itself:** *because* that memory doesn't already exist in off-the-shelf models, building it ourselves is genuinely innovative — this is confirmed as the innovation angle, not just an assumption the team invented. Confirmed independently by the professor as "quite innovative" ("bayağı inovatif bir şey").
- **Mechanism, precisely:** not vector search magic — see [02-architecture/system-design.md](../02-architecture/system-design.md#how-the-embeddingretrieval-mechanism-actually-works-professors-explanation). Chunk video → embed chunks into a vector DB → embed text queries into the same space for semantic comparison → decode retrieved vectors back to text via a **generative model from a compatible model family**.
- **Status:** confirmed direction. This is the headline differentiator to build and to lead with in the pitch.

## Object detection model choice

- **Original plan:** YOLO for object detection, open-source, standard choice.
- **Confirmed by professor:** YOLO is sufficient and recommended specifically because embedding/VLM models (Qwen, Gemini, etc.) can tell you *that* an object is present but not *where* (pixel-level localization) — YOLO fills that gap, which matters for downstream speed/trajectory calculations (e.g. computing a forklift's actual turn speed from frame-to-frame pixel displacement, near-100% accurate, vs. an LLM's unreliable guess).
- **Explicitly rejected:** using raw OpenCV as the primary detector. Too low-level/manual; YOLO and comparable detectors are already built on OpenCV internals specifically so we don't reimplement that layer from scratch.
- **Open question:** whether the Facebook segment-editing model the professor mentioned already does what YOLO does for us — if so, consolidate to one model. Action item to evaluate, see [action-items.md](action-items.md).

## Video/VLM model shortlist

- **Confirmed:** Qwen2.5-VL (prefer newer versions over the older LAVA-style approach) — strong Turkish support, multimodal embedding capability, vLLM-compatible.
- **Added per professor, not in the original research doc:** JEPA / JEPA 2 (Meta) — small (~300–400M params, runs even on phone-class hardware), add to the video-understanding shortlist as a first-section item.
- **Added per professor:** Facebook's segment-editing model — evaluate alongside YOLO for potential consolidation.
- **Uncertain, flagged by professor himself as "recalling, not certain":** the Qwen-vs-Gemini multimodal-embedding architecture comparison and chronology (Qwen believed to predate Gemini's multimodal embedding by about a month; Gemini claims a single fused vector across modalities, Qwen was recalled as using separate token streams per modality before fusion). Worth an independent verification pass before citing this as fact anywhere external-facing (jury docs, README).

## Agentic framework

- **Confirmed:** LangGraph for orchestration — no objection from the professor; matches the "no static rule-based solutions" competition requirement.
- **Confirmed:** most of the surrounding pipeline (frame extraction, detection, vector DB wiring) can and should be built manually — professor's view is this is "not particularly hard," not a reason to reach for extra frameworks beyond LangGraph.
- **Note:** the research doc's original phrase "LangCraft" was a mishearing/typo for LangGraph in the live call — corrected throughout this vault.

## Local-only serving

- **Confirmed, non-negotiable:** no cloud service dependency for the text/video LLMs, including at the level of "which model variant" (must be a local/offline release, not a cloud-bound one). Ollama or LM Studio (llama.cpp-family backends) are acceptable local-serving options alongside vLLM.
- **Confirmed:** JEPA's small footprint means VRAM is a non-issue for that model specifically; the constrained resource is really the LLM/VLM pair (see [03-planning/hardware.md](../03-planning/hardware.md)).

## Turkish video model (stretch goal)

- **New idea from professor, not in original scope:** attempt to produce a Turkish-specialized video model derived from Qwen's video model (adapting tokenizer + embeddings), drawing on the professor's own PhD-era model-building experience. Explicitly framed as "if time allows" — a stretch goal, not a committed deliverable. Tracked in [03-planning/roadmap.md](../03-planning/roadmap.md#stage-5-stretch-features).

## Roadmap sequencing

- **Original open question (from Üveys, on the call):** "where do we even start — jumping straight into LangGraph doesn't seem to make sense; what's the roadmap?"
- **Professor's answer, confirmed as the plan of record:** don't add pipeline complexity yet. First, quickly:
  1. Study embedding models (Qwen's embedding specifically) — how vectors are processed inside the model.
  2. Every team member runs at least one VLM locally on at least one image (video if possible) before the next meeting, and documents what the code is doing step by step.
  3. Establish **current baseline capability** — what can the system actually do *right now* — before planning what to build next. Explicit warning against skipping this: a system that appears to work brilliantly on one example is not evidence of anything if you don't know your baseline; a plausible failure could still lose the whole project.
  4. Keep the gap between meetings short — don't over-extend the research phase.
- **Status:** confirmed, supersedes jumping directly into Stage 1 of the original roadmap. See [action-items.md](action-items.md) for the literal checklist.
