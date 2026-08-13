# Mentor Call Summary — 2026-08-13

Advising PhD professor, guidance call with the team (Üveys Cengiz and teammates). Raw transcript preserved at [transcript-raw.md](transcript-raw.md) (original Turkish). This file is the English synthesis, organized by topic rather than chronology.

## Context and expectations

- Professor's framing: the team is currently "the rabbit" in a tortoise-and-hare setup relative to at least one other team (which has only 1 developer among 4 members, vs. this team being all developers) — an advantage, but only if it doesn't turn into complacency. Explicit warning against coasting on that advantage.
- Offered close, frequent support ("could meet almost daily") *conditional on* the team showing seriousness/discipline/effort. This is a standing offer, not automatic.
- Team status at call time: awaiting a university budget decision (expected within 1–2 days) to fund stronger compute (Colab/Cloud), conceptual groundwork already done.

## Competition category — correction

- Üveys' teammate initially assumed all teams the professor advises are in the same competition category. **Corrected:** there are 3 categories. Category 1 = internal-enterprise text-only AI. Category 2 = finance. **Category 3 (ours)** = video-in, report-out. Only category-3 teams are actually building the same kind of system as us.
- This matters for competitive-positioning claims: "we're different from the others" is only meaningful relative to actual category-3 competitors, not the whole field.

## What "agentic" actually means here — the forklift narrative

The professor pushed the team to re-derive the system design from first principles rather than jumping to LangGraph:

- Exercise: imagine there is *no AI at all*. A human — a security guard — is doing this job manually. What are they actually doing?
- Answer (built collaboratively): the guard watches multiple camera feeds simultaneously, narrates events to themselves in real time (e.g., "forklift's driver got on, picked up the load, lifted it, then an accident happened while lifting"), logs this as it happens, and later synthesizes a report on request — covering not just *what* happened but *why* (driver error vs. mechanical failure vs. other) and *who/what* is at fault.
- Key clarification: a camera-only system **cannot** make definitive judgments — it can only offer an interpretive opinion ("I believe the cause was an incorrect steering maneuver"), same as a human guard would. The system's edge over a human isn't certainty, it's *better-calibrated estimates* — e.g., measuring an object's actual speed from frame-to-frame displacement (near-100% accuracy) rather than eyeballing it, whereas a generic LLM guess at "how fast was that" is just a guess and "will be wrong in some way."
- "Agent" in this context = an automated stand-in for that human role, not a separate video-vs-text-agent debate. The video analysis *is* the agent's job; it's not a mismatch with a "language agents" competition framing.

## Memory as the innovation angle

- Team's original framing (in the technical research doc and in the call) proposed long-context memory as the differentiating, innovative piece — batching per-minute/10-minute summaries into a longer running context so the system can connect a morning event to an evening consequence.
- Professor's correction to the underlying assumption, but validation of the plan: the premise "AI already has good memory, better than ours" is **false** — current LLMs have poorly developed memory. But **building this ourselves is exactly what makes it innovative** — if it already existed off-the-shelf, doing it wouldn't be innovative at all.
- Technical clarification on why current chat systems seem to "remember": there is no timestamp metadata and no vector-search mechanism involved in ordinary chat memory — the entire prior conversation is simply re-stuffed as plain text into the context window every turn. That's why asking a chatbot "what time did I send my last message" fails — that fact was never present in the text at all. Verify this by testing directly (open a past chat, ask it that question).
- Professor pointed to his own Hugging Face profile and dataset examples in this area, and referenced a lecture recording posted the preceding Tuesday (2026-08-11) covering this exact topic — team should watch it.

## How the embedding/retrieval mechanism works (technical deep-dive)

Captured precisely in [02-architecture/system-design.md](../02-architecture/system-design.md#how-the-embeddingretrieval-mechanism-actually-works-professors-explanation) — summary: chunk video into short segments (e.g. 10s), embed each into a vector database; embed a text query into the same space so semantically related content lands close together and becomes searchable; to go from a retrieved vector back to text/video/image, feed it to a **generative model from a compatible model family**. A vector is just a number array representing a meaning, decodable into whichever modality you attach a generative head for.

## Model recommendations

- **JEPA / JEPA 2** (Meta) — professor flagged this as a must-note item for the video-understanding model list. Small (~300–400M params), can run on a phone.
- **Qwen2.5-VL** — confirmed strong choice, especially for memory/embedding work via its multimodal embedding capability. Newer versions exist; prefer those over older approaches like LAVA.
- **Gemini vs. Qwen embeddings** — professor's recollection (flagged as uncertain, worth double-checking): Qwen's video-embedding approach came roughly a month before Gemini's multimodal embedding announcement. Architecturally: Gemini claims a single fused vector across audio/text/video/image; Qwen (per the professor's memory of reviewing its internals previously, though time has passed) represented audio and video as separate token streams before fusing with the text vector into a further output vector. End result is comparable either way for our purposes.
- **Facebook segment-editing model** — worth evaluating alongside YOLO; may already do what YOLO does for us, in which case we could consolidate.
- **YOLO** — sufficient and recommended for object detection specifically (pixel-level localization), which embedding-only models (Qwen, Gemini, etc.) cannot provide — a VLM can tell you "there's a forklift" but not which pixel it starts at; YOLO can.
- **OpenCV** — deliberately *not* recommended as the primary detection tool; it's too low-level/manual. YOLO and comparable detectors are already built on top of OpenCV internals specifically so teams don't have to reimplement that layer.

## Local serving

- Confirmed requirement: **no cloud service dependency** for the text/video LLMs — everything must run locally, no exceptions, even for the local model's variant selection (i.e., use Qwen's local/offline release, not anything cloud-bound).
- Ollama or LM Studio (built on llama.cpp-family backends) are reasonable local-serving options.
- JEPA's small size (~300–400M params) means it comfortably fits even constrained VRAM — confirmed to run even on phone-class hardware.

## Competitive positioning — correction

- Team initially framed their differentiation as "we do more detailed, multi-line, heavily interpretive reports vs. a single-line 'house exploded' from competitors" (using a bomb-explosion example: our system would report blast severity, likely injury given the blast size and known personnel proximity, etc., vs. a competitor's one-line report).
- **Professor's pushback:** this framing is risky, not clearly an advantage. Doing *maximally detailed* interpretation across an unbounded domain (bomb analysis one moment, forklift speed analysis the next, a cooking mishap after that) makes the system's job much harder and increases the odds of failing even on simple examples. There's no defined scope boundary in that framing.
- **Resolution reached on the call:** narrow the domain for the competition entry (a bounded, dry-run-able scenario), and explicitly note in the writeup/pitch that the system is designed to generalize/expand beyond that scope later. Team agreed a narrower scope (e.g. factory workplace-accident scenario) is more tractable, while acknowledging even "factory workplace accident" alone is still fairly broad.

## Homework before the next meeting

See [05-decisions/action-items.md](../05-decisions/action-items.md) for the concrete checklist — professor's explicit ask was to keep the gap between meetings short and to establish "where the system stands right now" (baseline capability) before adding complexity, rather than assuming capabilities that don't yet exist.

## Logistics

- Team fills in a form/questionnaire on the professor's behalf each time (the professor does not have direct form access) — teammate confirmed they'll keep creating/submitting these; professor's approval is what's authoritative once submitted.
- Standing cadence: async check-ins as needed, periodic Google Meet calls like this one.
