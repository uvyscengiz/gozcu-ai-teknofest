# Stage 1 MVP Pipeline Implementation Plan

> **TAMAMLANDI — tarihsel kayıt.** Bu plan/spec uygulandı ve merge edildi;
> anlattığı yapı bugünkü donuk algı katmanının bir kısmı. **Yürütülecek iş
> değil.** Güncel görevler: [docs/tasks/](../../tasks/README.md).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a video-in/JSON-out MVP pipeline: extract frames, detect objects with YOLO, ground a VLM's per-frame description in those detections, emit a structured event log, and show it through a minimal Gradio UI.

**Architecture:** Six small, single-responsibility modules under a new `gozcu/` package (frames → detect → schema → interpret → run), wired together by `run_pipeline()`, fronted by `app.py` (Gradio). The VLM is reached exclusively through the standard `openai` Python client against a local `mlx_vlm.server` process, so swapping in vLLM on a future GPU box is a `config.py` env-var change, not a rewrite.

**Tech Stack:** Python 3.12, `uv` (env/deps), `mlx-vlm` (local VLM serving, OpenAI-compatible), `ultralytics` (YOLOv11), `pydantic` v2, `openai` Python client, `gradio`, `ffmpeg` (subprocess).

**Spec:** [docs/superpowers/specs/2026-08-17-stage1-mvp-pipeline-design.md](../specs/2026-08-17-stage1-mvp-pipeline-design.md)

## Global Constraints

- No automated tests for this stage — explicit decision in the spec's Non-goals. Every task's "verify" step is a manual run with printed/inspected output, not a pytest assertion.
- Frame downscaling to ~896px width is mandatory before any VLM call — native 4K/1440p input was confirmed (Day 1 checkpoint) to break generation outright.
- Per-frame VLM calls only — whole-video mode was confirmed to collapse into repeated near-identical text across frames.
- VLM decoding requires `temperature=0.3` — confirmed necessary to avoid degenerate repeated-token output at default settings.
- `detected_objects` in the output schema must come from YOLO's actual output, never from the VLM guessing — this is the grounding mechanism that mitigates the hallucination finding.
- `base_url`/`model` for the VLM client must be configurable via `GOZCU_VLM_BASE_URL` / `GOZCU_VLM_MODEL` env vars (default to the local mlx_vlm.server + Qwen2.5-VL-3B-4bit) — this is the Mac→GPU-box migration seam.
- Manual verification video: `~/Downloads/6186411-uhd_3840_2160_30fps.mp4` (the same factory-fire video used throughout the Day 1 checkpoint). Do not commit this video file to git — reference it by path only.

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `gozcu/__init__.py` (empty)
- Create: `gozcu/config.py`
- Modify: `.gitignore` (add `.venv/`, `runs/`, `*.pt`, `__pycache__/` if not already present)

**Interfaces:**
- Produces: `gozcu.config.VLM_BASE_URL: str`, `gozcu.config.VLM_MODEL: str`, `gozcu.config.YOLO_MODEL_PATH: str`, `gozcu.config.FRAME_FPS: float`, `gozcu.config.FRAME_WIDTH: int` — every later task imports these instead of hardcoding values.

- [ ] **Step 1: Check current repo root state**

Run: `ls -la` at repo root, and `cat .gitignore` if it exists.
Expected: confirms whether a `.gitignore` exists yet and what's already ignored. There is currently a `poc/` directory (throwaway exploration, Day 1 checkpoint) and a `runs/` directory (YOLO/SAM2 output) at repo root from earlier exploratory work — do not delete either, they're the prior checkpoint's evidence referenced from decision-log.md.

- [ ] **Step 2: Create the venv and pyproject.toml**

```bash
uv venv --python 3.12
```

Write `pyproject.toml`:

```toml
[project]
name = "gozcu"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "mlx-vlm>=0.6.13",
    "ultralytics>=8.4.121",
    "pydantic>=2.13",
    "openai>=1.0",
    "gradio>=5.0",
    "pillow",
]

[tool.uv]
package = false
```

```bash
uv pip install -e .
```

- [ ] **Step 3: Reuse already-downloaded model weights instead of re-downloading**

The Day 1 checkpoint already downloaded `yolo11n.pt` and `sam2.1_t.pt` into
`poc/day1-checkpoint/`. Copy the one Stage 1 needs to the new repo root so
`ultralytics` finds it locally instead of re-fetching:

```bash
cp poc/day1-checkpoint/yolo11n.pt ./yolo11n.pt
```

`mlx-vlm`'s Qwen2.5-VL-3B-4bit weights are cached in the global Hugging Face
cache (`~/.cache/huggingface/hub`) from the checkpoint run — this is
automatic and requires no action; `mlx_vlm.server` will find them there
without re-downloading regardless of which venv/directory it's launched
from.

- [ ] **Step 4: Write `gozcu/config.py`**

```python
import os

VLM_BASE_URL = os.environ.get("GOZCU_VLM_BASE_URL", "http://localhost:8000/v1")
VLM_MODEL = os.environ.get("GOZCU_VLM_MODEL", "mlx-community/Qwen2.5-VL-3B-Instruct-4bit")
YOLO_MODEL_PATH = os.environ.get("GOZCU_YOLO_MODEL", "yolo11n.pt")
FRAME_FPS = float(os.environ.get("GOZCU_FRAME_FPS", "1.0"))
FRAME_WIDTH = int(os.environ.get("GOZCU_FRAME_WIDTH", "896"))
```

Create empty `gozcu/__init__.py`.

- [ ] **Step 5: Update `.gitignore`**

Ensure it contains (add any missing lines):

```
.venv/
__pycache__/
*.pt
runs/
```

- [ ] **Step 6: Verify**

Run: `uv run python -c "from gozcu.config import VLM_BASE_URL, VLM_MODEL, YOLO_MODEL_PATH, FRAME_FPS, FRAME_WIDTH; print(VLM_BASE_URL, VLM_MODEL, YOLO_MODEL_PATH, FRAME_FPS, FRAME_WIDTH)"`
Expected output: `http://localhost:8000/v1 mlx-community/Qwen2.5-VL-3B-Instruct-4bit yolo11n.pt 1.0 896.0` (note: `896.0` since `FRAME_WIDTH` prints as float only if you mistyped — confirm it prints `896` as an int; if it prints `896.0`, fix the cast in config.py).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml gozcu/__init__.py gozcu/config.py .gitignore
git commit -m "chore: scaffold gozcu package and Stage 1 config"
```

---

## Task 2: Frame extraction (`gozcu/frames.py`)

**Files:**
- Create: `gozcu/frames.py`

**Interfaces:**
- Consumes: `gozcu.config.FRAME_FPS`, `gozcu.config.FRAME_WIDTH`.
- Produces: `gozcu.frames.Frame` (dataclass: `path: Path`, `timestamp_s: float`, `index: int`), `gozcu.frames.extract_frames(video_path: str | Path, output_dir: str | Path, fps: float = FRAME_FPS, width: int = FRAME_WIDTH) -> list[Frame]` — Task 6 (`run.py`) calls this directly.

- [ ] **Step 1: Write `gozcu/frames.py`**

```python
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Frame:
    path: Path
    timestamp_s: float
    index: int


def extract_frames(
    video_path: str | Path,
    output_dir: str | Path,
    fps: float = None,
    width: int = None,
) -> list[Frame]:
    from gozcu.config import FRAME_FPS, FRAME_WIDTH

    fps = FRAME_FPS if fps is None else fps
    width = FRAME_WIDTH if width is None else width

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pattern = str(output_dir / "frame_%04d.jpg")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"fps={fps},scale={width}:-2",
            pattern,
        ],
        check=True,
        capture_output=True,
    )

    frame_paths = sorted(output_dir.glob("frame_*.jpg"))
    return [
        Frame(path=p, timestamp_s=i / fps, index=i)
        for i, p in enumerate(frame_paths)
    ]
```

- [ ] **Step 2: Verify against the real checkpoint video**

```bash
uv run python -c "
from gozcu.frames import extract_frames
frames = extract_frames('$HOME/Downloads/6186411-uhd_3840_2160_30fps.mp4', '/tmp/gozcu_frames_test')
print(f'{len(frames)} frames')
print(frames[0])
print(frames[-1])
"
```

Expected: `31 frames` (31-second video at 1fps), first frame `timestamp_s=0.0`, last frame `timestamp_s=30.0`. Then confirm resolution:

```bash
uv run python -c "from PIL import Image; print(Image.open('/tmp/gozcu_frames_test/frame_0000.jpg').size)"
```

Expected: width `896`, height even and close to `896 * (1440/2560) ≈ 504` (exact value depends on ffmpeg's `-2` rounding — any even height near 504 is correct; 4K/1440p-scale garbage-output bug from the Day 1 checkpoint is what this guards against, so the key check is that width is exactly 896, not the source's native 2560).

- [ ] **Step 3: Commit**

```bash
git add gozcu/frames.py
git commit -m "feat: add frame extraction module"
```

---

## Task 3: Output schema (`gozcu/schema.py`)

**Files:**
- Create: `gozcu/schema.py`

**Interfaces:**
- Produces: `gozcu.schema.FrameEvent` (Pydantic model: `timestamp_s: float`, `detected_objects: list[str]`, `description: str`), `gozcu.schema.PipelineResult` (Pydantic model: `video_path: str`, `events: list[FrameEvent]`) — Task 5 (`interpret.py`) and Task 6 (`run.py`) both import these.

- [ ] **Step 1: Write `gozcu/schema.py`**

```python
from pydantic import BaseModel, ConfigDict, Field


class FrameEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp_s: float
    detected_objects: list[str]
    description: str = Field(max_length=300)


class PipelineResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    video_path: str
    events: list[FrameEvent]
```

- [ ] **Step 2: Verify schema shape**

```bash
uv run python -c "
from gozcu.schema import FrameEvent, PipelineResult
import json
print(json.dumps(FrameEvent.model_json_schema(), indent=2))
event = FrameEvent(timestamp_s=1.0, detected_objects=['person'], description='A person stands near smoke.')
result = PipelineResult(video_path='test.mp4', events=[event])
print(result.model_dump_json(indent=2))
"
```

Expected: the printed JSON schema has `\"additionalProperties\": false` and `\"required\": [\"timestamp_s\", \"detected_objects\", \"description\"]` (from `extra=\"forbid\"`); the `PipelineResult` JSON prints with the one nested event correctly.

- [ ] **Step 3: Commit**

```bash
git add gozcu/schema.py
git commit -m "feat: add FrameEvent/PipelineResult schema"
```

---

## Task 4: Object detection (`gozcu/detect.py`)

**Files:**
- Create: `gozcu/detect.py`

**Interfaces:**
- Consumes: `gozcu.config.YOLO_MODEL_PATH`.
- Produces: `gozcu.detect.DetectedObject` (dataclass: `class_name: str`, `confidence: float`, `bbox: tuple[int, int, int, int]`), `gozcu.detect.detect_objects(frame_path: str | Path) -> list[DetectedObject]` — Task 6 (`run.py`) and Task 7 (`app.py`, for drawing boxes) both call this.

- [ ] **Step 1: Write `gozcu/detect.py`**

```python
from dataclasses import dataclass
from pathlib import Path

from ultralytics import YOLO

from gozcu.config import YOLO_MODEL_PATH

_model = None


@dataclass
class DetectedObject:
    class_name: str
    confidence: float
    bbox: tuple[int, int, int, int]


def _get_model() -> YOLO:
    global _model
    if _model is None:
        _model = YOLO(YOLO_MODEL_PATH)
    return _model


def detect_objects(frame_path: str | Path) -> list[DetectedObject]:
    model = _get_model()
    results = model.predict(source=str(frame_path), verbose=False)
    result = results[0]

    detections = []
    for box in result.boxes:
        class_id = int(box.cls.item())
        class_name = result.names[class_id]
        confidence = float(box.conf.item())
        x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
        detections.append(
            DetectedObject(
                class_name=class_name,
                confidence=confidence,
                bbox=(x1, y1, x2, y2),
            )
        )
    return detections
```

- [ ] **Step 2: Verify against a real extracted frame**

Re-uses the frames extracted in Task 2's verification step (`/tmp/gozcu_frames_test/frame_0000.jpg`) — if that directory no longer exists, re-run Task 2's Step 2 first.

```bash
uv run python -c "
from gozcu.detect import detect_objects
detections = detect_objects('/tmp/gozcu_frames_test/frame_0015.jpg')
for d in detections:
    print(d)
"
```

Expected: a list of `DetectedObject(...)` lines. Per the Day 1 checkpoint's YOLO run on this same video, frames from roughly the second half of the clip should show `class_name='person'` and/or `class_name='train'` (the known mislabel for the fire/smoke structure) — either is a correct result for this task; an empty list on this specific frame is also possible and not a failure (per-frame detection is not guaranteed non-empty, only that the function runs and returns well-formed objects).

- [ ] **Step 3: Commit**

```bash
git add gozcu/detect.py
git commit -m "feat: add YOLO detection wrapper"
```

---

## Task 5: VLM interpretation (`gozcu/interpret.py`)

**Files:**
- Create: `gozcu/interpret.py`

**Interfaces:**
- Consumes: `gozcu.config.VLM_BASE_URL`, `gozcu.config.VLM_MODEL`, `gozcu.schema.FrameEvent`.
- Produces: `gozcu.interpret.describe_frame(frame_path: str | Path, detected_objects: list[str], timestamp_s: float, client=None) -> FrameEvent` — Task 6 (`run.py`) calls this per frame.

- [ ] **Step 1: Write `gozcu/interpret.py`**

```python
from pathlib import Path

from openai import OpenAI

from gozcu.config import VLM_BASE_URL, VLM_MODEL
from gozcu.schema import FrameEvent

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=VLM_BASE_URL, api_key="not-needed")
    return _client


def describe_frame(
    frame_path: str | Path,
    detected_objects: list[str],
    timestamp_s: float,
    client: OpenAI | None = None,
) -> FrameEvent:
    client = client or _get_client()

    objects_line = ", ".join(detected_objects) if detected_objects else "none"
    prompt = (
        f"Confirmed objects detected in this frame by a separate detector: {objects_line}.\n"
        "Describe only what is visible in the image. Do not state a location, "
        "casualty count, or any statistic unless it is directly and unambiguously "
        "readable from the image itself. If you are not sure, do not guess."
    )

    schema = FrameEvent.model_json_schema()
    schema["required"] = ["timestamp_s", "detected_objects", "description"]

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
    )

    event = FrameEvent.model_validate_json(response.choices[0].message.content)
    event.timestamp_s = timestamp_s
    event.detected_objects = detected_objects
    return event
```

Note: `timestamp_s` and `detected_objects` are overwritten after parsing rather than trusted from the model's own JSON output — the model has no reliable way to know the true frame timestamp, and `detected_objects` must stay ground-truth from YOLO (Task 4), not the VLM's own guess, per the spec's grounding requirement. Forcing them into the schema's `required` list is still useful: it makes the model produce *some* value in the right shape/type before we overwrite it, which keeps the JSON well-formed under strict mode.

- [ ] **Step 2: Start the local VLM server for manual verification**

In a separate terminal (or background process), start the server once:

```bash
uv run mlx_vlm.server --model mlx-community/Qwen2.5-VL-3B-Instruct-4bit --port 8000
```

Wait for it to print that it's listening before proceeding to Step 3. Leave it running for this task and Tasks 6-7's verification steps too.

- [ ] **Step 3: Verify against a real frame with real detections**

```bash
uv run python -c "
from gozcu.detect import detect_objects
from gozcu.interpret import describe_frame

detections = detect_objects('/tmp/gozcu_frames_test/frame_0015.jpg')
class_names = sorted({d.class_name for d in detections})
event = describe_frame('/tmp/gozcu_frames_test/frame_0015.jpg', class_names, timestamp_s=15.0)
print(event.model_dump_json(indent=2))
"
```

Expected: valid `FrameEvent` JSON prints, `timestamp_s` is exactly `15.0`, `detected_objects` exactly matches what `detect_objects` returned (not something the VLM invented), and `description` is a single plausible sentence about smoke/fire/a person **without** a specific city/country name or a specific casualty count or dollar figure — if the description does contain an invented specific (matching the Day 1 checkpoint's hallucination pattern, e.g. "Güney Kore", a death toll, a dollar amount), the prompt in Step 1 needs strengthening before moving on: try making the constraint more forceful (e.g. add "If a location or number is not directly visible as text in the image, never mention one") and re-run this verification until it stops happening on at least 3 different frames from this video.

- [ ] **Step 4: Commit**

```bash
git add gozcu/interpret.py
git commit -m "feat: add grounded VLM frame interpretation"
```

---

## Task 6: Pipeline orchestration (`gozcu/run.py`)

**Files:**
- Create: `gozcu/run.py`

**Interfaces:**
- Consumes: `gozcu.frames.extract_frames`, `gozcu.detect.detect_objects`, `gozcu.interpret.describe_frame`, `gozcu.schema.PipelineResult`.
- Produces: `gozcu.run.run_pipeline(video_path: str | Path, output_dir: str | Path | None = None) -> PipelineResult` — Task 7 (`app.py`) calls this.

- [ ] **Step 1: Write `gozcu/run.py`**

```python
import tempfile
from pathlib import Path

from gozcu.detect import detect_objects
from gozcu.frames import extract_frames
from gozcu.interpret import describe_frame
from gozcu.schema import PipelineResult


def run_pipeline(
    video_path: str | Path,
    output_dir: str | Path | None = None,
) -> PipelineResult:
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="gozcu_frames_")

    frames = extract_frames(video_path, output_dir)

    events = []
    for frame in frames:
        detections = detect_objects(frame.path)
        class_names = sorted({d.class_name for d in detections})
        event = describe_frame(frame.path, class_names, frame.timestamp_s)
        events.append(event)

    return PipelineResult(video_path=str(video_path), events=events)
```

- [ ] **Step 2: Verify end-to-end on the real checkpoint video**

Ensure `mlx_vlm.server` from Task 5 Step 2 is still running.

```bash
uv run python -c "
from gozcu.run import run_pipeline
result = run_pipeline('$HOME/Downloads/6186411-uhd_3840_2160_30fps.mp4')
print(f'{len(result.events)} events')
print(result.model_dump_json(indent=2)[:2000])
"
```

Expected: `31 events` (one per extracted frame), and the printed JSON is well-formed `PipelineResult` output. Read through the descriptions by eye: confirm none of them contain an invented specific location/casualty/statistic (same check as Task 5 Step 3, now across the whole video). This will take a few minutes to run (31 sequential VLM calls) — that's expected for Stage 1's sequential, non-parallel scope.

- [ ] **Step 3: Commit**

```bash
git add gozcu/run.py
git commit -m "feat: add pipeline orchestration"
```

---

## Task 7: Gradio demo UI (`app.py`)

**Files:**
- Create: `app.py` (repo root)
- Modify: `gozcu/run.py` (change `run_pipeline`'s return type to also hand back the frame directory, so the UI can locate frame files for annotation)

**Interfaces:**
- Consumes: `gozcu.run.run_pipeline`, `gozcu.detect.detect_objects`, `gozcu.config.VLM_BASE_URL`, `gozcu.config.VLM_MODEL`.
- Produces: a runnable Gradio app (`python app.py`) — this is the final, user-facing deliverable of Stage 1, nothing later in this plan depends on it. Note: this task changes `run_pipeline`'s return type from `PipelineResult` to `tuple[PipelineResult, Path]` — the last change to a shared interface in this plan.

- [ ] **Step 1: Modify `gozcu/run.py` to also return the frame directory**

Replace `run_pipeline`'s body in `gozcu/run.py` with:

```python
def run_pipeline(
    video_path: str | Path,
    output_dir: str | Path | None = None,
) -> tuple[PipelineResult, Path]:
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="gozcu_frames_")
    output_dir = Path(output_dir)

    frames = extract_frames(video_path, output_dir)

    events = []
    for frame in frames:
        detections = detect_objects(frame.path)
        class_names = sorted({d.class_name for d in detections})
        event = describe_frame(frame.path, class_names, frame.timestamp_s)
        events.append(event)

    return PipelineResult(video_path=str(video_path), events=events), output_dir
```

Re-run Task 6 Step 2's verification command, updated for the new return
shape, to confirm nothing broke:

```bash
uv run python -c "
from gozcu.run import run_pipeline
result, frame_dir = run_pipeline('$HOME/Downloads/6186411-uhd_3840_2160_30fps.mp4')
print(f'{len(result.events)} events, frames in {frame_dir}')
"
```

Expected: `31 events, frames in /tmp/gozcu_frames_...`.

- [ ] **Step 2: Write `app.py`**

```python
import subprocess
import time
from pathlib import Path

import gradio as gr
from openai import OpenAI
from PIL import Image, ImageDraw

from gozcu.config import VLM_BASE_URL, VLM_MODEL
from gozcu.detect import detect_objects
from gozcu.run import run_pipeline

_server_process = None


def _ensure_server_running():
    global _server_process
    client = OpenAI(base_url=VLM_BASE_URL, api_key="not-needed")
    try:
        client.models.list()
        return
    except Exception:
        pass

    port = VLM_BASE_URL.rstrip("/").split(":")[-1].split("/")[0]
    _server_process = subprocess.Popen(
        ["uv", "run", "mlx_vlm.server", "--model", VLM_MODEL, "--port", port]
    )

    for _ in range(60):
        try:
            client.models.list()
            return
        except Exception:
            time.sleep(2)
    raise RuntimeError(
        f"mlx_vlm.server did not become reachable at {VLM_BASE_URL} within 120s"
    )


def _annotate_sample_frame(result, frame_dir: Path) -> Image.Image | None:
    for index, event in enumerate(result.events):
        if not event.detected_objects:
            continue
        frame_path = frame_dir / f"frame_{index:04d}.jpg"
        if not frame_path.exists():
            continue
        image = Image.open(frame_path).convert("RGB")
        draw = ImageDraw.Draw(image)
        for detection in detect_objects(frame_path):
            draw.rectangle(detection.bbox, outline="red", width=3)
            draw.text(
                (detection.bbox[0], max(0, detection.bbox[1] - 12)),
                detection.class_name,
                fill="red",
            )
        return image
    return None


def process_video(video_path):
    _ensure_server_running()
    result, frame_dir = run_pipeline(video_path)
    annotated = _annotate_sample_frame(result, frame_dir)
    return result.model_dump_json(indent=2), annotated


demo = gr.Interface(
    fn=process_video,
    inputs=gr.Video(label="Upload a video"),
    outputs=[
        gr.Textbox(label="Pipeline JSON output", lines=30),
        gr.Image(label="Sample annotated frame"),
    ],
    title="gözcü-ai — Stage 1 MVP",
)

if __name__ == "__main__":
    demo.launch()
```

- [ ] **Step 3: Verify the app launches and processes a video**

Stop any `mlx_vlm.server` left running from Task 5/6 (so this step tests the
auto-start path too):

```bash
pkill -f mlx_vlm.server || true
```

```bash
uv run python app.py &
sleep 5
curl -sf http://127.0.0.1:7860 > /dev/null && echo "Gradio is up"
```

Then, since this is a UI, do a real manual check in a browser (this step
cannot be done by an automated subagent — the orchestrating session or the
user should do it): open `http://127.0.0.1:7860`, upload
`~/Downloads/6186411-uhd_3840_2160_30fps.mp4`, and confirm:

- The server auto-starts (first request takes a while — this is expected,
  it includes launching `mlx_vlm.server` and waiting for it to become
  reachable, then running the full 31-frame pipeline).
- The JSON output textbox populates with a well-formed `PipelineResult`.
- The annotated-frame image shows at least one red bounding box.

Stop the app afterward: `kill %1` (or find and kill the `python app.py`
process).

- [ ] **Step 4: Commit**

```bash
git add app.py gozcu/run.py
git commit -m "feat: add Gradio demo UI"
```

---

## Post-plan note

This plan deliberately stops at a working, manually-verified demo. Stage 2
(LangGraph orchestration, error handling/fallback mechanisms, working
memory) and Stage 3 (risk assessment, action recommendation) are separate,
later specs — do not fold their scope into fixes made while executing this
plan. If something here needs a Stage 2/3 capability to fix properly (e.g.
"retry the VLM call on server disconnect"), note it as a new action item in
`docs/05-decisions/action-items.md` instead of expanding this plan's scope.
