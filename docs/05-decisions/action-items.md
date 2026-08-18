# Action Items — Before Next Meeting

Assigned on the 2026-08-13 mentor call. Keep the gap to the next meeting short — professor's explicit instruction was not to over-extend this research phase.

## Everyone

- [ ] Study embedding models, specifically how Qwen's embedding works — understand how vectors are processed inside the model (see [02-architecture/system-design.md](../02-architecture/system-design.md#how-the-embeddingretrieval-mechanism-actually-works-professors-explanation) for the professor's explanation as a starting reference).
- [x] Run at least one VLM locally on at least one image (video if feasible) — mandatory for every team member, no exceptions. If video interpretation isn't feasible yet, fall back to image interpretation. **Done (Üveys, 2026-08-17):** Qwen2.5-VL-3B-Instruct-4bit via mlx-vlm on real factory-fire footage — see [decision-log.md](decision-log.md#day-1-checkpoint--local-vlm-run-2026-08-17) for findings (resolution bug, hallucinated casualty/location specifics).
- [ ] Be ready to show, step by step, what the code is doing during that run — this is more valuable to the professor than the demo output itself.
- [x] Try running each of: a segmentation model, YOLO, JEPA, and a Qwen model, at least once, locally. **All done (Üveys, 2026-08-17):** Qwen2.5-VL-3B ([decision-log.md](decision-log.md#day-1-checkpoint--local-vlm-run-2026-08-17)), yolo11n ([decision-log.md](decision-log.md#day-1-checkpoint--local-yolo-run-2026-08-17)), SAM2.1-tiny ([decision-log.md](decision-log.md#day-1-checkpoint--local-sam2-run-2026-08-17)), V-JEPA2-ViT-L ([decision-log.md](decision-log.md#day-1-checkpoint--local-v-jepa-2-run-2026-08-17)) — all run once on the same factory-fire video.
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

- [x] **Establish where the system stands right now** — baseline capability — before adding any further pipeline complexity. Explicit warning from the professor: don't assume a capability exists without having verified it; a single impressive-looking output on one example proves nothing about the baseline, and an undetected failure mode there could sink the whole project. This checkpoint gates moving into [03-planning/roadmap.md](../03-planning/roadmap.md) Stage 1 in earnest. **Done (Üveys, 2026-08-17):** all four models run locally on the same real video — see the four Day 1 checkpoint entries in [decision-log.md](decision-log.md), starting at [local VLM run](decision-log.md#day-1-checkpoint--local-vlm-run-2026-08-17). Headline results: VLM hallucinates specific facts (casualty counts, location) when not grounded; YOLO reliably detects people but has no domain class for the hazard itself; SAM2 segments but ran on CPU not MPS; JEPA produces embeddings but their retrieval-usefulness is unvalidated. Clear to move into Stage 1 skeleton work.

## Open questions to resolve (not time-boxed to next meeting, but tracked)

- [ ] Nail down the exact scope boundary for the competition submission (see [decision-log.md](decision-log.md#competitive-positioning) — "factory workplace accident" alone was flagged as still fairly broad).
- [ ] Verify whether Facebook's segment-editing model duplicates YOLO's role for this use case (see [decision-log.md](decision-log.md#object-detection-model-choice)).
- [ ] Independently verify the Qwen-vs-Gemini multimodal-embedding chronology/architecture claim before using it in any external-facing material (professor flagged this as recalled-from-memory, not certain).
- [ ] Track university budget arrival (expected within 1–2 days of 2026-08-13) and its effect on compute plans (see [03-planning/hardware.md](../03-planning/hardware.md#budget-note-from-the-team)).
- [ ] Investigate Turkish-video-model feasibility (tokenizer/embedding adaptation of Qwen's video model) as time allows — stretch goal, not committed.
- [ ] Test whether an explicit "describe only what's visible, don't invent counts/locations/statistics" prompt constraint suppresses the hallucination behavior found in the 2026-08-17 VLM checkpoint (see [decision-log.md](decision-log.md#day-1-checkpoint--local-vlm-run-2026-08-17)) — not yet tested, deferred in favor of moving to YOLO.
- [ ] Investigate why Ultralytics defaulted to CPU instead of MPS for SAM2 inference on Mac (41.8s/frame) — see [decision-log.md](decision-log.md#day-1-checkpoint--local-sam2-run-2026-08-17). Matters for feasibility of any Mac-side segmentation work.
- [ ] Validate that V-JEPA2 embeddings are actually useful for the planned retrieval mechanism (semantically similar chunks should land close together in embedding space) — running the model once only confirmed it loads and produces output, not that the output is fit for purpose. See [decision-log.md](decision-log.md#day-1-checkpoint--local-v-jepa-2-run-2026-08-17).

## 2026-08-18 — Stage 1 final-review fix wave

Findings deferred or escalated out of the Stage 1 MVP pipeline final code review (see `gozcu/frames.py`, `gozcu/interpret.py`, `gozcu/run.py`, `app.py`).

- [ ] **Escalated — VLM decoding artifact, needs real attention soon.** A frame-level VLM call leaked Chinese characters into an English-language `description` field during Stage 1 testing (`"烟雾"`, i.e. "smoke", instead of English). The spec mandates `repetition_penalty=1.3`/`repetition_context_size=40` alongside `temperature=0.3` in `describe_frame`'s decode settings as "the exact settings the checkpoint found necessary to avoid degenerate token-repetition output," but only `temperature` had actually made it into `gozcu/interpret.py`. Tried adding `extra_body={"repetition_penalty": 1.3, "repetition_context_size": 40}` to the `client.chat.completions.create(...)` call — `mlx_vlm.server`'s OpenAI-compatible endpoint accepts the params without a 400 error, but it made things *worse*, not better: A/B tested across 8 real frames, every single response came back with `description` wrapped in stray `"[...]"` brackets, and the one frame that produced clean English without these params (`"smoke rising from a chimney"`) leaked Chinese with them (`"[烟雾]"`). Reverted the change (comment left in `gozcu/interpret.py` explaining why). The Chinese-leak risk is therefore still open and unresolved — needs real investigation (different decode params, a different repetition-avoidance mechanism, or accepting occasional non-English output and adding a post-hoc language filter) before this is relied on for a real submission.
- [ ] **Tracked refactor — do before Stage 2 builds on it.** `gozcu.run.run_pipeline` returns `tuple[PipelineResult, Path]`, and callers (`app.py`'s `_annotate_sample_frame`) reconstruct each frame's filename from the event's list index plus a hardcoded 1-based-numbering assumption (`frame_{index + 1:04d}.jpg`) to find the frame file on disk. This only works because two off-by-one conventions happen to cancel out (`Frame.index` is 0-based, ffmpeg's output filenames are 1-based). Cleaner: have `run_pipeline` return the actual `list[Frame]` (or attach `frame_path` directly onto `FrameEvent`) so no caller ever has to reconstruct a filename from a number.
- [ ] **Tracked — operator docs.** No README exists documenting that `ffmpeg` is a required system dependency (not installable via `pyproject.toml`), that first run downloads several GB of model weights, or the `GOZCU_VLM_BASE_URL`/`GOZCU_VLM_MODEL` env vars — needed before anyone else on the team can run this.
- [ ] **Tracked — repo hygiene.** `yolo11n.pt` (5.6MB model weights) was committed in commit `7d08912` ("docs: Day 1 checkpoint findings + Stage 1 MVP spec and plan") one commit before `35b715f` ("chore: scaffold gozcu package and Stage 1 config") started excluding `*.pt` via `.gitignore` — inconsistent, worth cleaning up while branch history is still easy to rewrite (not urgent).
- [ ] **Minor, no action needed unless revisited:**
  - `api_key="not-needed"` is hardcoded in `app.py`/`gozcu/interpret.py` rather than configurable — a real vLLM deployment might require a real key.
  - `FrameEvent.description`'s `max_length=300` currently does double duty as both a storage constraint and (indirectly, via the strict-JSON-schema decoder) a generation-time constraint that `_sanitize_description` works around — cleaner long-term fix is decoupling the two.
  - `_sanitize_description` can lose the final word of a legitimate description that happens to land in the 290-300 char range without ending in punctuation.
  - `Frame.index` being 0-based while output filenames are 1-based is confusing and undocumented.
  - `event.detected_objects = detected_objects` in `describe_frame` aliases the caller's list rather than copying it — safe today, could bite a future caller that reuses one list across frames.
  - the `mkdtemp()` temp frame directory created by `run_pipeline` when no `output_dir` is given is never cleaned up.
