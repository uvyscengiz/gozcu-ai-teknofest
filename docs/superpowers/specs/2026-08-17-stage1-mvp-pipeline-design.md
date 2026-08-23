# Stage 1 MVP Pipeline — Design Spec

> **TAMAMLANDI — tarihsel kayıt.** Bu plan/spec uygulandı ve merge edildi;
> anlattığı yapı bugünkü donuk algı katmanının bir kısmı. **Yürütülecek iş
> değil.** Güncel görevler: [docs/tasks/](../../tasks/README.md).

Date: 2026-08-17
Status: draft, pending review

## Context

Zero pipeline code exists in this repo. The Day 1 checkpoint (see
[decision-log.md](../../05-decisions/decision-log.md)) confirmed baseline
capability of the four candidate models on real target-domain footage (a
factory fire video) and surfaced concrete failure modes each component must
account for:

- Qwen2.5-VL hallucinates specific facts (location, casualty counts) when
  given no grounding, and requires frame downscaling (~896px width) to avoid
  degenerate output.
- YOLOv11 reliably detects `person` but has no domain class for fire/smoke —
  it forces the hazard into the nearest COCO class ("train").
- No GPU box exists yet (university budget still pending as of this spec).
  vLLM is not viable on Mac. `mlx-vlm` is the confirmed local-serving
  substitute for this stage.

This spec covers **Stage 1 only**, per [roadmap.md](../../03-planning/roadmap.md):
a minimum system that takes one video and produces JSON output. It
deliberately does not include LangGraph orchestration, risk assessment, or
action recommendation — those are Stage 2/3 and depend on capabilities this
stage doesn't build yet.

## Goals

- Take a video file in, produce a structured JSON event log out.
- Ground VLM descriptions in YOLO detections to reduce (not just document)
  the hallucination problem found in the Day 1 checkpoint.
- Build the model-serving boundary so that swapping Mac (mlx-vlm) for the
  eventual GPU box (vLLM) is a config change, not a rewrite.
- Minimal Gradio UI: upload a video, see the JSON result and one annotated
  sample frame.

## Non-goals

- Risk-level classification or action recommendations (Stage 3 — no
  grounding logic exists yet to make these trustworthy; see the
  hallucination finding in decision-log.md).
- LangGraph orchestration (Stage 2 — this stage is plain functions Stage 2
  will later wrap as tool nodes).
- Multi-video / long-horizon memory (the vector-DB embedding mechanism —
  separate, larger piece of work, not part of Stage 1).
- Automated tests. Explicit decision for this stage: TDD applies to
  deterministic logic in principle, but Stage 1 is moving fast toward a demo
  under a 9-day deadline, and the team chose to defer automated tests
  entirely for now. Verification is manual, the same way the Day 1
  checkpoints were verified. Revisit once the pipeline shape stabilizes.
- Fine-tuned/domain-specific detection classes for fire/smoke (tracked as an
  open question in action-items.md, not solved here).

## Architecture

```
video file
   │
   ▼
frames.py    → ffmpeg: extract @1fps, downscale to 896px width → list[frame path, timestamp]
   │
   ▼
detect.py    → YOLOv11n per frame → list[DetectedObject{class_name, confidence, bbox}]
   │
   ▼
interpret.py → OpenAI-compatible client → mlx_vlm.server (Qwen2.5-VL-3B-4bit)
               prompt grounded with detect.py's output, response_format = FrameEvent schema
   │
   ▼
run.py       → orchestrates the three stages per frame → PipelineResult (list[FrameEvent])
   │
   ▼
app.py       → Gradio: upload → run.py → display JSON + one annotated sample frame
```

Each module is a plain function/class with no cross-dependencies beyond
what's listed — Stage 2 wraps these as LangGraph tool nodes without needing
to change their internals.

### `frames.py`

`extract_frames(video_path, fps=1.0, width=896) -> list[Frame]` where `Frame`
is `{path: Path, timestamp_s: float, index: int}`. Wraps the same
`ffmpeg -vf "fps=..,scale=..:-1"` invocation validated in the Day 1
checkpoint. Downscaling is mandatory here, not optional — the checkpoint
found native 4K/1440p input breaks VLM generation outright.

### `detect.py`

`detect_objects(frame_path) -> list[DetectedObject]` using stock
`yolo11n.pt` (no fine-tuning yet — flagged as a known gap in Non-goals).
`DetectedObject = {class_name: str, confidence: float, bbox: tuple[int,int,int,int]}`.

### `schema.py`

```python
class FrameEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timestamp_s: float
    detected_objects: list[str]      # class names from detect.py, deduplicated
    description: str = Field(max_length=300)

class PipelineResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    video_path: str
    events: list[FrameEvent]
```

`detected_objects` is populated directly from `detect.py`'s output (ground
truth, not model-guessed) — the VLM is not asked to invent this list, only
to describe what it sees given that list as context.

### `interpret.py`

`describe_frame(frame_path, detected_objects: list[str], client) -> str`.
Builds a chat completion request against the OpenAI-compatible client with:

- `response_format` = `FrameEvent.model_json_schema()` (guided decoding via
  mlx-vlm's `llguidance` support — same mechanism the repo's vLLM plan
  intended, different backend).
- A system/user prompt that (a) lists `detected_objects` as confirmed
  present, (b) explicitly instructs: describe only what is visible in the
  image; do not state locations, casualty counts, or statistics unless
  directly readable from the image. This directly targets the hallucination
  finding from the Day 1 VLM checkpoint (closes that open action item as
  part of building this, rather than as separate follow-up work).
- Per-frame calls, not whole-video mode — the checkpoint found whole-video
  mode collapses into repeated near-identical text across frames; per-frame
  calls stayed on-topic and distinct.
- `temperature=0.3`, `repetition_penalty=1.3`, `repetition_context_size=40` —
  the exact settings the checkpoint found necessary to avoid degenerate
  token-repetition output.

### `run.py`

`run_pipeline(video_path) -> PipelineResult`. Sequential: extract frames →
for each frame, detect then interpret → assemble `PipelineResult`. No
parallelism in Stage 1 — correctness and demoability first, speed later if
needed.

### `app.py`

Gradio `gr.Interface`: video upload → calls `run_pipeline` → outputs the
`PipelineResult` as formatted JSON plus one sample frame (first frame with
non-empty `detected_objects`) with YOLO boxes drawn on it, so the demo shows
grounding is actually happening, not just narrated.

### Model serving

`mlx_vlm.server` is started as a subprocess from `app.py` on startup if not
already reachable at the configured `base_url` (default
`http://localhost:8000/v1`), using `mlx-community/Qwen2.5-VL-3B-Instruct-4bit`
— same model validated in the Day 1 checkpoint. `base_url` and `model` are
both read from a small `config.py` module with environment-variable
overrides (`GOZCU_VLM_BASE_URL`, `GOZCU_VLM_MODEL`), so pointing this at a
vLLM server later (GPU box, `Qwen2.5-VL-7B-Instruct`) is a config change
only.

## Error handling

Stage 1 scope: fail loudly, no silent fallbacks. If ffmpeg extraction fails,
YOLO errors, or the VLM server is unreachable, the pipeline raises and
Gradio surfaces the error message as-is. No retry logic, no partial-result
recovery — those are Stage 2 concerns ("error handling and fallback
mechanisms" is explicitly listed there in roadmap.md, not here).

## Testing

Per the Non-goals section: no automated tests for Stage 1, by explicit team
decision. Verification is manual — run `run_pipeline` against the fire
video used throughout the Day 1 checkpoint, inspect the JSON output and
annotated frame by eye, same process as the checkpoint runs already
documented in decision-log.md.

## Open items carried forward (not solved by this spec)

- Fire/smoke has no dedicated detection class — `detected_objects` will
  include real "person" detections and the misleading "train" label found
  in the checkpoint. Not fixed here; tracked as an existing open item.
- MPS-vs-CPU device selection for any future segmentation work — unrelated
  to this pipeline (SAM2 isn't part of Stage 1).
- V-JEPA2 embedding validation — unrelated, belongs to the later
  memory/vector-DB piece, not Stage 1.
