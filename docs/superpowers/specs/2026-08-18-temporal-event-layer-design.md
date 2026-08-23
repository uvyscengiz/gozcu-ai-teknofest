# Temporal Event/Tracking Layer — Design Spec

> **TAMAMLANDI — tarihsel kayıt.** Bu plan/spec uygulandı ve merge edildi;
> anlattığı yapı bugünkü donuk algı katmanının bir kısmı. **Yürütülecek iş
> değil.** Güncel görevler: [docs/tasks/](../../tasks/README.md).

Date: 2026-08-18
Status: draft, pending review

## Context

Stage 1 MVP shipped (video-in/JSON-out, per-frame independent detection +
VLM description). Watching real output surfaced a quality gap beyond what
Stage 1 was scoped to fix: VLM descriptions are correctness-safe (no
hallucinated specifics) but generic, because every frame is interpreted in
complete isolation — nothing in the pipeline knows what changed between
frame N and frame N+1.

The requirement then broadened during brainstorming: not just "less
generic text," but genuine cross-installation generality. The same system
should work at a factory (forklift speed, collision, a crowd gathering,
visible injuries, medical response arriving), a farm, a police HQ, etc.,
without hardcoding a taxonomy per install type. An earlier proposal to add
a `hazard_type` enum field was explicitly rejected for exactly this reason
— a fixed category list doesn't generalize across installation types.

Resolution reached: keep perception domain-general (YOLO tracks physical
entities, the VLM describes in open vocabulary — neither needs to know the
install type), and add a domain-general **temporal** reasoning layer.
Almost everything in the broadened requirement — speed, crash, gathering,
a new entity arriving — is a pattern over generic low-level signals
(object position over time, entity counts over time), not a
classification problem. Compute those signals generically, then let the
VLM interpret them in natural language rather than mapping them to a fixed
category.

This doesn't slot cleanly into `roadmap.md`'s existing Stage 2/3
numbering (it overlaps Stage 2's "Event timeline builder" and is partly
Stage 1 quality work) — built as its own initiative per explicit request,
not derived from the roadmap's stage sequence.

**Scope tension, flagged and resolved:** `decision-log.md`'s "Competitive
positioning" section records the professor's guidance to narrow the
*competition submission's* scope — avoid claiming unbounded breadth in the
pitch, since that increases failure surface without being a safe framing.
This spec keeps that guidance intact: it narrows what gets *demoed*
(still one scenario, one video, for the actual submission), while
building the underlying signal computation to be genuinely
install-agnostic underneath. The two aren't in conflict, but the
resolution is deliberate, not accidental — general system, narrow demo.

## Goals

- Give each detected object a persistent identity across frames, via
  Ultralytics' built-in tracker (fully local, no network dependency, same
  as the rest of the pipeline).
- Compute domain-general per-frame signals from tracked positions:
  velocity, sudden bbox disappearance/deformation (collision/crash
  candidate), person-count trend (gathering candidate).
- Feed those signals into the existing per-frame VLM call as additional
  grounding, and add a `notable_event` field to the output schema for the
  VLM to describe (or explicitly say none) any significant change — same
  hallucination discipline as the existing `description` field.
- Stay within one VLM call per frame — no doubling of runtime versus
  today's pipeline.

## Non-goals

- Not building the full Stage 2 LangGraph agentic pipeline (orchestration,
  risk assessment module, action recommendation module). This spec is the
  signal-computation layer underneath that, not the agent itself.
- Not fixing YOLO's missing hazard-class problem (fire/smoke has no COCO
  class) — tracked separately in action-items.md, orthogonal to this work.
  Tracking works the same whether or not the class label is correct.
- Not adding automated tests — same explicit project-wide decision carried
  forward from Stage 1.
- Not solving "injuries visible" or "medical response arrived" by
  computation. These rely on the VLM's own visual judgment; the signal
  layer only gives it better cues (where to look, what changed) — it does
  not replace VLM judgment with a formula for these.

## Architecture

```
frames (ordered, from frames.py)
   │
   ▼
track.py    → model.track(persist=True) over the whole sequence
               → per-frame: list[TrackedObject{track_id, class_name, confidence, bbox}]
   │
   ▼
signals.py  → per-frame: FrameSignals{
                 velocities: dict[track_id, float]   # px/s, consecutive-frame bbox centers
                 vanished_tracks: list[track_id]      # present last frame, missing now
                 person_count: int
                 person_count_delta: int              # vs previous frame
               }
   │
   ▼
interpret.py (extended) → describe_frame(frame_path, detected_objects, signals, timestamp_s)
               prompt includes signals as grounding text alongside YOLO's object list
               schema gains `notable_event: str | None`
   │
   ▼
run.py (extended) → same orchestration shape: track once over all frames,
               then per-frame loop combines tracked detections + signals + VLM call
```

### `gozcu/track.py`

`track_video(frame_paths: list[Path]) -> list[list[TrackedObject]]` — one
list per frame, in frame order. Wraps `YOLO(...).track(persist=True, ...)`.
`TrackedObject` extends `detect.py`'s `DetectedObject` with a
`track_id: int`. `gozcu/detect.py` is unchanged — it stays the stateless
single-frame path already used by `app.py`'s gallery annotation; tracking
is additive, not a replacement.

Two things explicitly left open for implementation time, not assumed here:

- The exact `.track()` call signature/kwargs for the installed
  `ultralytics` version — check `yolo track --help` or the equivalent
  Python API docs before locking exact arguments.
- Whether tracking should run against the already-extracted, downscaled
  frame images (consistent with the rest of the pipeline, and what avoided
  the earlier VLM resolution bug) or the original video file. `source`
  accepts a list of image paths as well as a video — running against the
  same downscaled frames the rest of the pipeline uses is the default
  assumption, but needs confirming that tracking quality doesn't degrade
  meaningfully at 896px width versus the source resolution.

### `gozcu/signals.py`

`compute_signals(tracked_frames: list[list[TrackedObject]], frame_timestamps: list[float]) -> list[FrameSignals]`.
Pure computation, no model calls, no I/O. For frame index `i > 0`: match
`track_id`s present in both frame `i-1` and frame `i`, compute bbox-center
displacement divided by `timestamps[i] - timestamps[i-1]` as velocity;
`track_id`s present in `i-1` but absent in `i` go into `vanished_tracks`;
count `class_name == "person"` for `person_count` and its delta versus the
previous frame. Frame 0 gets zeroed/empty signals (no prior frame to
compare against).

### `gozcu/schema.py` (extended)

```python
class FrameEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timestamp_s: float
    detected_objects: list[str]
    description: str = Field(max_length=300)
    notable_event: str | None = Field(default=None, max_length=200)
```

### `gozcu/interpret.py` (extended)

`describe_frame` gains a `signals: FrameSignals` parameter. The prompt
gets a new grounding block summarizing the signals in short text (e.g.
"object #3 (person) moved ~40px in the last second; person count rose
from 2 to 5 since the last frame; object #7, present last frame, is no
longer detected"), followed by an instruction to describe a notable event
in `notable_event` only if the image and/or the motion data genuinely
support one — collision, a gathering, a new entity arriving, an object
stopping suddenly — and to set it to `null` if nothing notable is
happening or the model isn't sure. This is the same anti-hallucination
discipline as the existing `description` prompt, extended to the new
field rather than relaxed for it.

## Data flow (full picture)

```python
def run_pipeline(video_path, output_dir=None):
    frames = extract_frames(video_path, output_dir)                              # unchanged
    tracked_frames = track_video([f.path for f in frames])                       # new
    signals = compute_signals(tracked_frames, [f.timestamp_s for f in frames])   # new

    events = []
    for frame, tracked, sig in zip(frames, tracked_frames, signals):
        class_names = sorted({t.class_name for t in tracked})
        event = describe_frame(frame.path, class_names, sig, frame.timestamp_s)  # extended signature
        events.append(event)

    return PipelineResult(video_path=str(video_path), events=events), output_dir
```

## Error handling

Same as Stage 1: fail loudly, no silent fallback. If `.track()` errors,
`run_pipeline` raises — it does not fall back to independent per-frame
detection silently.

## Testing

No automated suite — same explicit project decision carried forward from
Stage 1's spec. Manual verification: run against real footage with an
actual state change (ideally the before/after accident clip currently
being sourced) and confirm by inspection — a moving object gets a
plausible non-zero velocity, a real disappearance or gathering gets
flagged in `notable_event`, and nothing gets invented on calm frames with
no real change (same hallucination-check discipline as the Stage 1
checkpoint: read the actual output, don't trust a summary).

## Open questions carried forward, not resolved here

- Exact `.track()` call signature/args for the installed ultralytics
  version.
- Whether tracking should run against the downscaled frames or the
  original video — needs an implementation-time check, not assumed here.
- How `notable_event` interacts with the still-open, unrelated YOLO
  hazard-class gap and VLM genericness/model-size experiments
  (action-items.md, 2026-08-18 section) — this spec doesn't fix those, and
  isn't expected to make them worse either.
