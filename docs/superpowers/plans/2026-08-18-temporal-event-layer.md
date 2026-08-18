# Temporal Event/Tracking Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give each detected object a persistent identity across frames, compute domain-general motion/count signals from that (velocity, sudden disappearance, person-count trend), and let the VLM interpret those signals — alongside the image — into a new `notable_event` field, without hardcoding any install-specific category.

**Architecture:** A new `gozcu/track.py` runs Ultralytics' built-in tracker (`persist=True`) once over the full ordered frame sequence, producing per-frame lists of `TrackedObject` (detections with a stable `track_id`). A new `gozcu/signals.py` derives `FrameSignals` (velocities, vanished tracks, person-count deltas) purely by computation — no model calls. `gozcu/interpret.py`'s `describe_frame` gains a `signals` parameter and folds a short text summary of them into the existing single VLM call's prompt, so this stays one VLM call per frame, not two. `gozcu/schema.py`'s `FrameEvent` gains `notable_event: str | None`, held to the same anti-hallucination discipline as `description`.

**Tech Stack:** Same as Stage 1 — Python 3.12, `ultralytics` (now also its tracking mode, not just `predict()`), `pydantic`, `openai` client against local `mlx_vlm.server`.

**Spec:** [docs/superpowers/specs/2026-08-18-temporal-event-layer-design.md](../specs/2026-08-18-temporal-event-layer-design.md)

## Global Constraints

- No automated tests for this stage — same explicit team decision as Stage 1. Every task's "verify" step is a manual run with printed/inspected output.
- `.track()` runs against the already-extracted, downscaled frame images (896px width) — the same frames the rest of the pipeline uses — one call per frame path in a loop with `persist=True`, not by pointing `.track()` at the raw video file. Confirmed via current Ultralytics docs: `model.track(frame, persist=True)` called repeatedly across a frame sequence is the documented pattern for maintaining track identity manually, not just a single call against a video source.
- Each call to `track_video()` must create its own fresh `YOLO` model instance — never reuse `gozcu.detect`'s cached module-level model. `persist=True`'s tracker state lives on the model object; sharing one long-lived model across different pipeline runs/videos would leak track IDs between unrelated videos.
- `detected_objects` and `timestamp_s` on the returned `FrameEvent` continue to be force-overwritten with ground truth after parsing (existing Stage 1 behavior, unchanged). `notable_event` is NOT overwritten — it is the VLM's own interpretive judgment, and there is no other ground-truth source to overwrite it with.
- `notable_event` must appear in the JSON schema's `required` list passed to the VLM (same pattern Stage 1 already uses for nullable-but-required fields under strict JSON-schema mode) and the prompt must explicitly instruct "set to null if unsure" — same hallucination discipline as `description`.
- Manual verification video: `~/Downloads/6186411-uhd_3840_2160_30fps.mp4` (same video used throughout this project). Do not commit this video file to git.
- `gozcu/detect.py` is NOT modified by this plan — it remains the stateless single-frame detection path already used by `app.py`'s gallery annotation. Tracking is additive in a new file, not a replacement.

---

## Task 1: Object tracking (`gozcu/track.py`)

**Files:**
- Create: `gozcu/track.py`

**Interfaces:**
- Consumes: `gozcu.config.YOLO_MODEL_PATH`, `gozcu.detect.DetectedObject`.
- Produces: `gozcu.track.TrackedObject` (dataclass extending `DetectedObject` with `track_id: int`), `gozcu.track.track_video(frame_paths: list[str | Path]) -> list[list[TrackedObject]]` — Task 5 (`run.py`) calls this.

- [ ] **Step 1: Write `gozcu/track.py`**

```python
from dataclasses import dataclass
from pathlib import Path

from ultralytics import YOLO

from gozcu.config import YOLO_MODEL_PATH
from gozcu.detect import DetectedObject


@dataclass
class TrackedObject(DetectedObject):
    track_id: int


def track_video(frame_paths: list[str | Path]) -> list[list[TrackedObject]]:
    # A fresh model instance per call, not gozcu.detect's cached one — persist=True
    # carries tracker state on the model object across calls, and reusing a
    # long-lived model across different videos would leak track IDs between them.
    model = YOLO(YOLO_MODEL_PATH)

    all_tracked = []
    for frame_path in frame_paths:
        results = model.track(source=str(frame_path), persist=True, verbose=False)
        result = results[0]

        tracked = []
        if result.boxes is not None:
            for box in result.boxes:
                if box.id is None:
                    continue
                class_id = int(box.cls.item())
                class_name = result.names[class_id]
                confidence = float(box.conf.item())
                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
                track_id = int(box.id.item())
                tracked.append(
                    TrackedObject(
                        class_name=class_name,
                        confidence=confidence,
                        bbox=(x1, y1, x2, y2),
                        track_id=track_id,
                    )
                )
        all_tracked.append(tracked)
    return all_tracked
```

- [ ] **Step 2: Verify against real extracted frames**

```bash
uv run python -c "
from gozcu.frames import extract_frames
from gozcu.track import track_video

frames = extract_frames('$HOME/Downloads/6186411-uhd_3840_2160_30fps.mp4', '/tmp/gozcu_track_test')
tracked = track_video([f.path for f in frames])
print(f'{len(tracked)} frames tracked')
for i in [0, 10, 20, 21, 30]:
    ids = [t.track_id for t in tracked[i]]
    print(f'frame {i}: track_ids={ids}, classes={[t.class_name for t in tracked[i]]}')
"
```

Expected: `31 frames tracked`. The real thing to check — not just that it runs, but that identity is actually stable — is whether the same `track_id` appears in two adjacent frames that both detect a person (e.g. compare frame 20's and frame 21's printed `track_ids`). If no `track_id` ever repeats across adjacent frames, tracking is not actually working and needs debugging before continuing to Task 2 — do not treat "it ran without an exception" alone as success.

- [ ] **Step 3: Commit**

```bash
git add gozcu/track.py
git commit -m "feat: add multi-frame object tracking via Ultralytics persist=True"
```

---

## Task 2: Motion/count signals (`gozcu/signals.py`)

**Files:**
- Create: `gozcu/signals.py`

**Interfaces:**
- Consumes: `gozcu.track.TrackedObject`.
- Produces: `gozcu.signals.FrameSignals` (dataclass: `velocities: dict[int, float]`, `vanished_tracks: list[int]`, `person_count: int`, `person_count_delta: int`), `gozcu.signals.compute_signals(tracked_frames: list[list[TrackedObject]], frame_timestamps: list[float]) -> list[FrameSignals]` — Task 4 (`interpret.py`) and Task 5 (`run.py`) both use this.

- [ ] **Step 1: Write `gozcu/signals.py`**

```python
import math
from dataclasses import dataclass, field

from gozcu.track import TrackedObject


@dataclass
class FrameSignals:
    velocities: dict[int, float] = field(default_factory=dict)
    vanished_tracks: list[int] = field(default_factory=list)
    person_count: int = 0
    person_count_delta: int = 0


def _bbox_center(bbox: tuple[int, int, int, int]) -> tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def compute_signals(
    tracked_frames: list[list[TrackedObject]],
    frame_timestamps: list[float],
) -> list[FrameSignals]:
    signals: list[FrameSignals] = []
    prev_by_id: dict[int, TrackedObject] = {}
    prev_person_count = 0

    for i, frame_objects in enumerate(tracked_frames):
        current_by_id = {obj.track_id: obj for obj in frame_objects}
        person_count = sum(1 for obj in frame_objects if obj.class_name == "person")

        if i == 0:
            signals.append(FrameSignals(person_count=person_count))
            prev_by_id = current_by_id
            prev_person_count = person_count
            continue

        dt = frame_timestamps[i] - frame_timestamps[i - 1]
        velocities: dict[int, float] = {}
        if dt > 0:
            for track_id, obj in current_by_id.items():
                if track_id in prev_by_id:
                    prev_center = _bbox_center(prev_by_id[track_id].bbox)
                    curr_center = _bbox_center(obj.bbox)
                    distance = math.hypot(
                        curr_center[0] - prev_center[0],
                        curr_center[1] - prev_center[1],
                    )
                    velocities[track_id] = distance / dt

        vanished_tracks = [tid for tid in prev_by_id if tid not in current_by_id]

        signals.append(
            FrameSignals(
                velocities=velocities,
                vanished_tracks=vanished_tracks,
                person_count=person_count,
                person_count_delta=person_count - prev_person_count,
            )
        )

        prev_by_id = current_by_id
        prev_person_count = person_count

    return signals
```

- [ ] **Step 2: Verify with real tracked output**

```bash
uv run python -c "
from gozcu.frames import extract_frames
from gozcu.track import track_video
from gozcu.signals import compute_signals

frames = extract_frames('$HOME/Downloads/6186411-uhd_3840_2160_30fps.mp4', '/tmp/gozcu_track_test')
tracked = track_video([f.path for f in frames])
signals = compute_signals(tracked, [f.timestamp_s for f in frames])
print(f'{len(signals)} signal entries')
print('frame 0:', signals[0])
for i in [5, 10, 20, 21]:
    print(f'frame {i}:', signals[i])
"
```

Expected: `31 signal entries`, matching `len(tracked)`. Frame 0 has empty `velocities`, empty `vanished_tracks`, `person_count_delta=0`. If Task 1's verification found a repeated `track_id` between frames 20 and 21, frame 21 here should show a non-empty `velocities` dict containing that same `track_id` — confirming the two modules agree, not just that each runs independently without error.

- [ ] **Step 3: Commit**

```bash
git add gozcu/signals.py
git commit -m "feat: add velocity/vanish/person-count signal computation"
```

---

## Task 3: Add `notable_event` field (`gozcu/schema.py`)

**Files:**
- Modify: `gozcu/schema.py`

**Interfaces:**
- Produces: `gozcu.schema.FrameEvent.notable_event: str | None` (new field, default `None`, `max_length=200`) — Task 4 (`interpret.py`) sets this, Task 6 (`app.py`) reads it.

- [ ] **Step 1: Modify `gozcu/schema.py`**

```python
from pydantic import BaseModel, ConfigDict, Field


class FrameEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp_s: float
    detected_objects: list[str]
    description: str = Field(max_length=300)
    notable_event: str | None = Field(default=None, max_length=200)


class PipelineResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    video_path: str
    events: list[FrameEvent]
```

- [ ] **Step 2: Verify schema shape**

```bash
uv run python -c "
from gozcu.schema import FrameEvent
import json
print(json.dumps(FrameEvent.model_json_schema(), indent=2))
event = FrameEvent(timestamp_s=1.0, detected_objects=['person'], description='A person stands near smoke.', notable_event='A person appears to be running away from the fire.')
print(event.model_dump_json(indent=2))
event2 = FrameEvent(timestamp_s=2.0, detected_objects=[], description='Nothing notable.')
print(event2.model_dump_json(indent=2))
"
```

Expected: the printed schema shows `notable_event` accepting both a string (with `maxLength: 200`) and `null`. `event2`, constructed without passing `notable_event` at all, prints `"notable_event": null` — confirming the default actually works, not just that the field exists.

- [ ] **Step 3: Commit**

```bash
git add gozcu/schema.py
git commit -m "feat: add notable_event field to FrameEvent"
```

---

## Task 4: Ground the VLM prompt in tracking signals (`gozcu/interpret.py`)

**Files:**
- Modify: `gozcu/interpret.py`

**Interfaces:**
- Consumes: `gozcu.signals.FrameSignals`.
- Produces: `gozcu.interpret.describe_frame(frame_path, detected_objects, signals, timestamp_s, client=None) -> FrameEvent` — **signature changes**: a new `signals` parameter is inserted as the third positional argument. Task 5 (`run.py`) calls this with the new signature.

- [ ] **Step 1: Replace `gozcu/interpret.py`**

```python
from pathlib import Path

from openai import OpenAI

from gozcu.config import VLM_BASE_URL, VLM_MODEL
from gozcu.schema import FrameEvent
from gozcu.signals import FrameSignals

_client = None

_SENTENCE_END = (".", "!", "?")
# How close to the schema's maxLength (in characters) counts as "cut off at the
# boundary" for word-trimming purposes. The decoder doesn't always land on the
# exact limit before forcing the string closed (observed: one frame cut at
# exactly 300 chars, another at 296) — a fixed 1-char tolerance misses the
# looser case, so this uses a small window instead.
_BOUNDARY_SLACK = 10


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=VLM_BASE_URL, api_key="not-needed")
    return _client


def _sanitize_description(text: str, max_length: int) -> str:
    """Clean up a `description` that may have been forcibly cut off by the VLM's
    strict-JSON-schema decoder enforcing `maxLength` character-by-character
    during generation (not just at validation time).

    Two symptoms observed empirically on real frames, both of which still pass
    pydantic validation silently:
    - a raw trailing control character padded onto the string right before the
      closing quote (e.g. frame 0011: "...roof of the building. There\\x01")
    - a hard cutoff mid-word at exactly `max_length` characters, no error
      (e.g. frame 0005: "...a building in the")

    This sanitizes the already-parsed value in place; it does not retry or
    re-request generation.
    """
    original_length = len(text)

    cleaned = text
    while cleaned and not cleaned[-1].isprintable():
        cleaned = cleaned[:-1]
    cleaned = cleaned.rstrip()

    # If the raw text landed at (or essentially at) the schema's length limit
    # and doesn't already end on a sentence boundary, it was very likely cut
    # off mid-word/mid-sentence by the decoder — trim back to the last whole
    # word rather than leave a dangling fragment.
    at_boundary = original_length >= max_length - _BOUNDARY_SLACK
    if at_boundary and not cleaned.endswith(_SENTENCE_END):
        trimmed, _, _ = cleaned.rpartition(" ")
        if trimmed:
            cleaned = trimmed.rstrip()

    return cleaned


def _signals_summary(signals: FrameSignals) -> str:
    parts = []
    if signals.velocities:
        moving = ", ".join(
            f"object #{track_id} moving ~{velocity:.0f}px/s"
            for track_id, velocity in signals.velocities.items()
        )
        parts.append(moving)
    if signals.vanished_tracks:
        parts.append(
            f"object(s) {signals.vanished_tracks} present in the previous frame "
            "are no longer detected"
        )
    if signals.person_count_delta > 0:
        parts.append(
            f"person count rose by {signals.person_count_delta} to "
            f"{signals.person_count} since the last frame"
        )
    elif signals.person_count_delta < 0:
        parts.append(
            f"person count fell by {abs(signals.person_count_delta)} to "
            f"{signals.person_count} since the last frame"
        )
    if not parts:
        return "no significant motion or count changes detected"
    return "; ".join(parts)


def describe_frame(
    frame_path: str | Path,
    detected_objects: list[str],
    signals: FrameSignals,
    timestamp_s: float,
    client: OpenAI | None = None,
) -> FrameEvent:
    client = client or _get_client()

    objects_line = ", ".join(detected_objects) if detected_objects else "none"
    signals_line = _signals_summary(signals)
    prompt = (
        f"Confirmed objects detected in this frame by a separate detector: {objects_line}.\n"
        f"Computed motion data for this frame, from object tracking across the video "
        f"(not guaranteed to be meaningful on its own): {signals_line}.\n"
        "Describe only what is visible in the image. Do not state a location, "
        "casualty count, or any statistic unless it is directly and unambiguously "
        "readable from the image itself. If you are not sure, do not guess.\n"
        "Separately, in 'notable_event': if the image and/or the motion data together "
        "indicate a specific notable event — a collision, a gathering of people, a new "
        "person or vehicle arriving, an object stopping suddenly — describe it briefly. "
        "Only report an event with real evidence in the image or the motion data. If "
        "nothing notable is happening, or you are not sure, set 'notable_event' to null. "
        "Do not invent an event type this data doesn't support."
    )

    schema = FrameEvent.model_json_schema()
    schema["required"] = [
        "timestamp_s",
        "detected_objects",
        "description",
        "notable_event",
    ]
    # Without an upper bound, the local VLM's strict-JSON-schema decoding gets stuck
    # in a runaway repetition loop inside the detected_objects array (observed
    # empirically: it repeats invented labels until max_tokens is exhausted and the
    # JSON never closes, so `description` is never reached). detected_objects is
    # discarded and overwritten with the YOLO ground truth below regardless of what
    # the model emits here, so bounding it to the true count (min 1, since the array
    # can't be required-but-empty) only constrains filler the model throws away.
    schema["properties"]["detected_objects"]["maxItems"] = max(1, len(detected_objects))

    response = client.chat.completions.create(
        model=VLM_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": str(frame_path)}},
                ],
            }
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "FrameEvent", "strict": True, "schema": schema},
        },
        max_tokens=300,
        temperature=0.3,
        # NOTE: the spec mandates repetition_penalty=1.3, repetition_context_size=40
        # in addition to temperature. This was tried via extra_body={"repetition_penalty":
        # 1.3, "repetition_context_size": 40} and mlx_vlm.server's OpenAI-compatible
        # endpoint accepts it without a 400 error — but empirically it makes output
        # *worse* under this strict-JSON-schema decoding path: A/B tested across 8 real
        # frames, every single response came back with the description wrapped in stray
        # "[...]" brackets, and one frame that was clean English without these params
        # leaked Chinese characters ("烟雾") with them. Reverted; see
        # docs/05-decisions/action-items.md (2026-08-18 entry) for the escalated finding.
    )

    event = FrameEvent.model_validate_json(response.choices[0].message.content)
    max_description_length = schema["properties"]["description"].get("maxLength", 300)
    event.description = _sanitize_description(event.description, max_description_length)
    event.timestamp_s = timestamp_s
    event.detected_objects = detected_objects
    return event
```

Note: `notable_event` is intentionally **not** overwritten after parsing, unlike `timestamp_s`/`detected_objects` — it is the VLM's own interpretive judgment, not ground truth from another source, so there is nothing to overwrite it with.

- [ ] **Step 2: Start the local VLM server for verification, if not already running**

```bash
curl -sf http://localhost:8000/v1/models > /dev/null || (uv run mlx_vlm.server --model mlx-community/Qwen2.5-VL-3B-Instruct-4bit --port 8000 &)
```

Wait for it to become reachable (poll `curl -sf http://localhost:8000/v1/models` every 2s, up to 60s) before continuing to Step 3.

- [ ] **Step 3: Verify against real frames with real signals**

```bash
uv run python -c "
from gozcu.frames import extract_frames
from gozcu.track import track_video
from gozcu.signals import compute_signals
from gozcu.interpret import describe_frame

frames = extract_frames('$HOME/Downloads/6186411-uhd_3840_2160_30fps.mp4', '/tmp/gozcu_track_test')
tracked = track_video([f.path for f in frames])
signals = compute_signals(tracked, [f.timestamp_s for f in frames])

for i in [5, 15, 25]:
    class_names = sorted({t.class_name for t in tracked[i]})
    event = describe_frame(frames[i].path, class_names, signals[i], frames[i].timestamp_s)
    print(f'--- frame {i} ---')
    print(event.model_dump_json(indent=2))
"
```

Expected: valid `FrameEvent` JSON for each of the three frames, `timestamp_s`/`detected_objects` matching ground truth exactly (unchanged from before this task). `notable_event` is either a plausible short string grounded in what's actually visible/computed, or `null`. Read every non-null `notable_event` by eye: it must not contain an invented location, casualty count, or statistic — the same hallucination check applied throughout this project. If one does, the prompt in Step 1 needs strengthening before moving on (e.g. make the "only report with real evidence" instruction more forceful), the same way Stage 1's original hallucination check required iteration.

- [ ] **Step 4: Commit**

```bash
git add gozcu/interpret.py
git commit -m "feat: ground VLM prompt in tracking signals, add notable_event"
```

---

## Task 5: Wire tracking into the pipeline (`gozcu/run.py`)

**Files:**
- Modify: `gozcu/run.py`

**Interfaces:**
- Consumes: `gozcu.track.track_video`, `gozcu.signals.compute_signals`, `gozcu.interpret.describe_frame` (new signature from Task 4).
- Produces: `gozcu.run.run_pipeline` — external signature unchanged (`(video_path, output_dir=None) -> tuple[PipelineResult, Path]`), internals changed.

- [ ] **Step 1: Replace `gozcu/run.py`**

```python
import tempfile
from pathlib import Path

from gozcu.frames import extract_frames
from gozcu.interpret import describe_frame
from gozcu.schema import PipelineResult
from gozcu.signals import compute_signals
from gozcu.track import track_video


def run_pipeline(
    video_path: str | Path,
    output_dir: str | Path | None = None,
) -> tuple[PipelineResult, Path]:
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="gozcu_frames_")
    output_dir = Path(output_dir)

    frames = extract_frames(video_path, output_dir)
    tracked_frames = track_video([frame.path for frame in frames])
    signals = compute_signals(tracked_frames, [frame.timestamp_s for frame in frames])

    events = []
    for frame, tracked, frame_signals in zip(frames, tracked_frames, signals):
        class_names = sorted({t.class_name for t in tracked})
        event = describe_frame(frame.path, class_names, frame_signals, frame.timestamp_s)
        events.append(event)

    return PipelineResult(video_path=str(video_path), events=events), output_dir
```

Note: `gozcu.detect.detect_objects` is no longer imported or used here — per-frame detections now come from `track_video`'s output instead. `gozcu/detect.py` itself is unmodified and still used by `app.py`'s gallery annotation, a separate stateless use case.

- [ ] **Step 2: Verify end-to-end on the real checkpoint video**

Ensure the VLM server from Task 4 Step 2 is still running.

```bash
uv run python -c "
from gozcu.run import run_pipeline
result, frame_dir = run_pipeline('$HOME/Downloads/6186411-uhd_3840_2160_30fps.mp4')
print(f'{len(result.events)} events, frames in {frame_dir}')
notable = [e for e in result.events if e.notable_event]
print(f'{len(notable)} frames with a notable_event')
for e in notable:
    print(f't={e.timestamp_s}s: {e.notable_event}')
print(result.model_dump_json(indent=2)[:1500])
"
```

Expected: `31 events`. Read through every non-null `notable_event` by eye — same hallucination check as always: no invented casualty count, location, or statistic. It's fine, even expected, if most or all frames on this particular video come back with `notable_event: null` — this video doesn't have an obvious crash/gathering moment, and the real test of whether this feature adds value is the before/after accident video once it's available, not this one. This run's job is to confirm the plumbing is correct end to end and nothing hallucinates — not to prove the feature is useful yet.

- [ ] **Step 3: Commit**

```bash
git add gozcu/run.py
git commit -m "feat: wire object tracking and signals into run_pipeline"
```

---

## Task 6: Surface `notable_event` in the demo UI (`app.py`)

**Files:**
- Modify: `app.py`

**Interfaces:**
- Consumes: `gozcu.schema.FrameEvent.notable_event` (new field from Task 3).
- Produces: nothing further — last task in this plan.

- [ ] **Step 1: Modify `app.py`'s `_annotate_all_frames`**

Replace the function with:

```python
def _annotate_all_frames(
    result, frame_dir: Path
) -> tuple[list[tuple[Image.Image, str]], list[str]]:
    thumbnails = []
    details = []
    for index, event in enumerate(result.events):
        frame_path = frame_dir / f"frame_{index + 1:04d}.jpg"
        if not frame_path.exists():
            continue
        image = _annotate_frame(frame_path)
        thumbnails.append((image, f"t={event.timestamp_s}s"))
        detail_text = (
            f"**t={event.timestamp_s}s**\n\n"
            f"**Detected objects:** {event.detected_objects}\n\n"
            f"**Description:** {event.description}"
        )
        if event.notable_event:
            detail_text += f"\n\n**Notable event:** {event.notable_event}"
        details.append(detail_text)
    return thumbnails, details
```

This is the only change in `app.py` — `process_video`, `show_frame_details`, and the `gr.Blocks` layout are unaffected, since `notable_event` flows through the existing `details` list of strings with no new UI component needed.

- [ ] **Step 2: Verify**

```bash
uv run python -c "
from gozcu.run import run_pipeline
from app import _annotate_all_frames

result, frame_dir = run_pipeline('$HOME/Downloads/6186411-uhd_3840_2160_30fps.mp4')
thumbnails, details = _annotate_all_frames(result, frame_dir)
print(f'{len(thumbnails)} thumbnails, {len(details)} details')
found = [d for d in details if 'Notable event' in d]
print(f'{len(found)} details contain a Notable event line')
for d in found:
    print('---')
    print(d)
"
```

Expected: `31 thumbnails, 31 details`. If Task 5's run on this video produced any non-null `notable_event`, its detail text now includes a "**Notable event:**" line — confirm at least one printed block actually shows it, don't just trust the count. If Task 5's run had zero notable events on this video, this step will correctly find zero too — that's expected, not a failure; if you want positive confirmation the wiring works regardless, construct one `FrameEvent` by hand with a non-null `notable_event` and confirm `_annotate_all_frames`'s output for it includes the line.

- [ ] **Step 3: Restart the running app**

```bash
pkill -f "python3 app.py" || true
```

```bash
uv run python app.py > /tmp/gozcu_app.log 2>&1 &
```

Poll `curl -sf http://127.0.0.1:7860` every 2s up to 30s to confirm it comes back up. This is a UI change — note in your report that visual confirmation in an actual browser is still an open gap, the same way Stage 1's original Gradio task flagged it; do not claim it as verified.

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: surface notable_event in the frame detail panel"
```

---

## Post-plan note

This plan deliberately stops at "the signal layer computes and the VLM interprets it, without hallucinating." It does not build the Stage 2 LangGraph agent, risk assessment, or action recommendation — those stay separate, later work per the spec's Non-goals. It also does not fix YOLO's missing hazard class (fire/smoke) — that's tracked independently in `docs/05-decisions/action-items.md` and is orthogonal to tracking (tracking works the same whether or not the class label is right). If something here needs one of those capabilities to do properly, log it as a new action item instead of expanding this plan's scope.
