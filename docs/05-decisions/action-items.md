# Action Items — Before Next Meeting

Assigned on the 2026-08-13 mentor call. Keep the gap to the next meeting short — professor's explicit instruction was not to over-extend this research phase.

## Everyone

- [ ] Study embedding models, specifically how Qwen's embedding works — understand how vectors are processed inside the model (see [02-architecture/system-design.md](../02-architecture/system-design.md#how-the-embeddingretrieval-mechanism-actually-works-professors-explanation) for the professor's explanation as a starting reference).
- [ ] Run at least one VLM locally on at least one image (video if feasible) — mandatory for every team member, no exceptions. If video interpretation isn't feasible yet, fall back to image interpretation.
- [ ] Be ready to show, step by step, what the code is doing during that run — this is more valuable to the professor than the demo output itself.
- [ ] Try running each of: a segmentation model, YOLO, JEPA, and a Qwen model, at least once, locally.
- [ ] Verify directly (don't just take it on faith) that ordinary chat memory has no timestamp/vector-search mechanism: open a past chat, ask it "what time did I send my last message" — confirm it can't answer, and understand why (see [decision-log.md](decision-log.md#memory-as-the-innovation-angle)).
- [ ] Watch the professor's lecture recording posted 2026-08-11 (Tuesday) on YouTube — covers this exact memory/context-window topic.
- [ ] Browse the professor's Hugging Face profile for relevant dataset examples in this space.

## Emre (per the call)

- [ ] Find a few example videos matching the discussed scenarios. Preference order:
  1. Real-world footage (strongly preferred) — e.g. search for "ant/rock" fall-type or comedic fall videos on YouTube as a stand-in category.
  2. Only if real footage isn't findable: game footage with realistic visual quality (factory-builder games, war games, drone-style overhead shots) — but see the explicit risk below.
  3. AI-generated video, if nothing suitable can be found or sourced.
- [ ] **Known risk with game footage, flagged directly by the professor:** real-world video is analog, game footage is digital/rendered — an object's rendered pixels behave deterministically (a forklift won't visually "leak" past its coded boundaries; whether an ant or a rock appears at all depends on whether it was programmed in). This analog-vs-digital mismatch is something a jury could specifically challenge. Prefer real footage for anything used in the actual submission/demo.

## System-wide checkpoint (highest priority item)

- [ ] **Establish where the system stands right now** — baseline capability — before adding any further pipeline complexity. Explicit warning from the professor: don't assume a capability exists without having verified it; a single impressive-looking output on one example proves nothing about the baseline, and an undetected failure mode there could sink the whole project. This checkpoint gates moving into [03-planning/roadmap.md](../03-planning/roadmap.md) Stage 1 in earnest.

## Open questions to resolve (not time-boxed to next meeting, but tracked)

- [ ] Nail down the exact scope boundary for the competition submission (see [decision-log.md](decision-log.md#competitive-positioning) — "factory workplace accident" alone was flagged as still fairly broad).
- [ ] Verify whether Facebook's segment-editing model duplicates YOLO's role for this use case (see [decision-log.md](decision-log.md#object-detection-model-choice)).
- [ ] Independently verify the Qwen-vs-Gemini multimodal-embedding chronology/architecture claim before using it in any external-facing material (professor flagged this as recalled-from-memory, not certain).
- [ ] Track university budget arrival (expected within 1–2 days of 2026-08-13) and its effect on compute plans (see [03-planning/hardware.md](../03-planning/hardware.md#budget-note-from-the-team)).
- [ ] Investigate Turkish-video-model feasibility (tokenizer/embedding adaptation of Qwen's video model) as time allows — stretch goal, not committed.
