# System Design

## High-level architecture

```
Video Input (MP4/RTSP)
        │
        ▼
┌──────────────────────────────┐
│  1. VIDEO PROCESSING PIPELINE│
│  ├─ FFmpeg decode            │
│  ├─ PySceneDetect scene      │
│  │  detection                 │
│  ├─ Keyframe extraction      │
│  └─ Scene segmentation       │
│     (start, end, keyframes)  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  2. PERCEPTION LAYER         │
│  (Low-level)                 │
│  ├─ YOLOv11: object/person   │
│  │  detection (every frame)  │
│  ├─ YOLOv11-Pose: posture,   │
│  │  fall detection           │
│  ├─ ByteTrack: object        │
│  │  tracking                  │
│  └─ Anomaly detection        │
│     (motion, density, etc.)  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  3. MULTIMODAL ANALYSIS      │
│  (High-level understanding)  │
│  ├─ Qwen2.5-VL scene         │
│  │  interpretation            │
│  ├─ Event identification     │
│  ├─ Contextual inference     │
│  └─ Temporal relationship    │
│     building                  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  4. EVENT TIMELINE BUILDER   │
│  ├─ Merge events with        │
│  │  timestamps                │
│  ├─ Deduplication            │
│  ├─ Event classification     │
│  │  (accident, risk, normal) │
│  └─ Critical-moment flagging │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  5. AGENT ORCHESTRATOR       │
│  (LangGraph)                 │
│  ├─ Risk assessment          │
│  ├─ Action recommendation    │
│  │  generation                │
│  ├─ Turkish summary writing  │
│  └─ Dynamic tool selection   │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  6. STRUCTURED OUTPUT        │
│  ├─ Pydantic schema via      │
│  │  vLLM guided JSON         │
│  ├─ Human-readable summary   │
│  └─ JSON API output           │
└──────────────────────────────┘
```

## Data flow detail

```
Video.mp4
    │
    ├─→ [FFmpeg] → Frame extraction (2 fps)
    │         → PySceneDetect → Scene list: [(00:00-00:14), (00:15-00:22), ...]
    │
    ├─→ [YOLO] → Per frame:
    │         {timestamp, objects: [person(x,y), forklift(x,y)], poses: [...]}
    │         → Anomaly flags: {fall_detected, crowd_detected, ...}
    │
    ├─→ [Qwen2.5-VL] → Per scene:
    │         {scene_id, start, end, description_tr, events: [...]}
    │         "00:15-00:22: forklift tipping over, personnel falling to the ground"
    │
    ├─→ [Timeline Builder] → Merge & deduplicate:
    │         events: [
    │           {time: "00:15", event: "Forklift tipped over", severity: "high"},
    │           {time: "00:20", event: "Person motionless on ground", severity: "critical"}
    │         ]
    │
    └─→ [LLM Agent] → Structured JSON:
              {
                summary: "...", events: [...], risk: "High",
                actions: ["Call medical team", ...]
              }
```

## Why LangGraph for orchestration

The competition spec emphasizes agentic architecture: "static, rule-based-only solutions will score low." LangGraph provides:

- **Graph-based control flow:** node-edge structure for complex decision chains
- **Dynamic tool selection:** the agent decides which tool to use based on perception results
- **Memory integration:** LangMem for working memory (retaining context during video analysis)
- **Error handling:** conditional edges enable fallback mechanisms
- **State management:** the video-analysis pipeline's state is tracked at every stage

## Agent tool definitions

```python
# Conceptual tool definitions

TOOL_EXTRACT_FRAMES = {
    "name": "extract_frames",
    "description": "Extracts frames from a video within a given time range",
    "params": {"video_path": str, "start_time": float, "end_time": float, "fps": int}
}

TOOL_DETECT_OBJECTS = {
    "name": "detect_objects",
    "description": "Detects objects/people in frames using YOLO",
    "params": {"frames": list, "confidence": float}
}

TOOL_ANALYZE_SCENE = {
    "name": "analyze_scene",
    "description": "Interprets scene content in Turkish using the VLM",
    "params": {"video_segment_path": str, "context": str}
}

TOOL_DETECT_ANOMALY = {
    "name": "detect_anomaly",
    "description": "Detects anomalies based on motion/posture analysis",
    "params": {"poses": list, "objects": list}
}

TOOL_BUILD_TIMELINE = {
    "name": "build_timeline",
    "description": "Merges detected events into a timestamped timeline",
    "params": {"scene_analyses": list, "detections": list}
}

TOOL_ASSESS_RISK = {
    "name": "assess_risk",
    "description": "Determines risk level from the event list (Low/Medium/High/Critical)",
    "params": {"events": list, "context": str}
}

TOOL_GENERATE_ACTIONS = {
    "name": "generate_actions",
    "description": "Produces operator action recommendations based on risk assessment",
    "params": {"risk_level": str, "events": list, "context": str}
}

TOOL_GENERATE_SUMMARY = {
    "name": "generate_summary",
    "description": "Produces a Turkish summary of the video content",
    "params": {"timeline": list, "risk_assessment": dict}
}
```

## Agent decision flow (ReAct pattern)

```
User: "analyze video.mp4"
    │
    ▼
Agent: "Extract frames first" → extract_frames()
    │
    ▼
Agent: "Detect scenes" → detect_scenes()
    │
    ▼
Agent: "Detect objects per scene" → detect_objects()
    │
    ▼
Agent: "Check for anomalies" → detect_anomaly()
    │
    ▼
Agent: "Interpret scenes with VLM" → analyze_scene()
    │
    ▼
Agent: "Merge events into timeline" → build_timeline()
    │
    ▼
Agent: "Assess risk" → assess_risk()
    │
    ▼
Agent: "Risk is high, generate action recommendations" → generate_actions()
    │
    ▼
Agent: "Write Turkish summary" → generate_summary()
    │
    ▼
Agent: → Structured JSON output
```

## Structured output design

### Pydantic schema

```python
from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum

class RiskLevel(str, Enum):
    LOW = "Düşük"
    MEDIUM = "Orta"
    HIGH = "Yüksek"
    CRITICAL = "Kritik"

class VideoEvent(BaseModel):
    time: str = Field(description="Event time (MM:SS format)")
    event: str = Field(description="Turkish description of the event")
    event_type: Optional[str] = Field(
        default=None,
        description="Event type: accident, risk, anomaly, normal"
    )
    confidence: Optional[float] = Field(
        default=None,
        description="Detection confidence score (0-1)"
    )

class VideoAnalysisResult(BaseModel):
    summary: str = Field(
        description="Turkish summary of the video content (2-3 sentences)"
    )
    events: List[VideoEvent] = Field(
        description="Timestamped event list"
    )
    risk: RiskLevel = Field(description="Overall risk level")
    risk_assessment: Optional[str] = Field(
        default=None,
        description="Detailed risk assessment (Turkish)"
    )
    actions: List[str] = Field(
        description="Operator action recommendations (Turkish)"
    )
    critical_moments: Optional[List[str]] = Field(
        default=None,
        description="Timestamps of critical moments"
    )
```

### vLLM structured output usage

vLLM supports guided decoding to produce JSON-schema-conformant output — directly satisfies the spec's "structured JSON-like output is mandatory" requirement.

```bash
# Start vLLM server with structured output
vllm serve Qwen/Qwen2.5-VL-7B-Instruct \
  --port 8000 \
  --dtype bfloat16 \
  --guided-decoding-backend xgrammar \
  --limit-mm-per-prompt '{"image": 10, "video": 1}'
```

```python
# Guided JSON via OpenAI-compatible API
from openai import OpenAI
from pydantic import BaseModel

client = OpenAI(base_url="http://localhost:8000/v1", api_key="dummy")

response = client.chat.completions.create(
    model="Qwen/Qwen2.5-VL-7B-Instruct",
    messages=[
        {"role": "system", "content": "You are a video analysis assistant..."},
        {"role": "user", "content": video_analysis_prompt}
    ],
    extra_body={
        "guided_json": VideoAnalysisResult.model_json_schema()
    }
)

result = VideoAnalysisResult.model_validate_json(
    response.choices[0].message.content
)
```

vLLM offers three guided-decoding backends ([vLLM Structured Outputs docs](https://docs.vllm.ai/en/latest/features/structured_outputs/)):
- **xgrammar** (default, recommended) — fastest
- **outlines** — flexible, multi-model
- **lm-format-enforcer** — for compatibility

Source: [Red Hat Developer — Structured outputs in vLLM](https://developers.redhat.com/articles/2025/06/03/structured-outputs-vllm-guiding-ai-responses)

## Local serving with vLLM

### Installation

```bash
# Python 3.12 virtual environment
python3.12 -m venv venv
source venv/bin/activate

# vLLM install
pip install vllm
pip install flash-attn --no-build-isolation  # optional, for performance

# transformers for Qwen2.5-VL (if needed)
pip install "git+https://github.com/huggingface/transformers"
```

### Starting the vLLM servers

```bash
# VLM service (for video analysis)
vllm serve Qwen/Qwen2.5-VL-7B-Instruct \
  --host 0.0.0.0 \
  --port 8000 \
  --dtype bfloat16 \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.85 \
  --max-model-len 32768 \
  --limit-mm-per-prompt '{"image": 10, "video": 1}' \
  --mm-processor-kwargs '{"max_pixels": 1003520}' \
  --guided-decoding-backend xgrammar \
  --allowed-local-media-path /workspace/videos

# LLM service (for decision support + NLG) — second GPU
vllm serve ogulcanaydogan/Turkish-LLM-14B-Instruct \
  --host 0.0.0.0 \
  --port 8001 \
  --dtype bfloat16 \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.85 \
  --max-model-len 8192 \
  --guided-decoding-backend xgrammar
```

### Video input via vLLM

vLLM supports video input through the OpenAI-compatible API ([vLLM multimodal_inputs docs](https://github.com/vllm-project/vllm/blob/main/docs/source/usage/multimodal_inputs.md)):

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="dummy")

response = client.chat.completions.create(
    model="Qwen/Qwen2.5-VL-7B-Instruct",
    messages=[{
        "role": "user",
        "content": [
            {"type": "video_url", "video_url": {"url": "file:///workspace/videos/scene1.mp4"}},
            {"type": "text", "text": "List the events in this video in Turkish, in chronological order."}
        ]
    }],
    max_tokens=1024
)
```

> **Performance tip:** per vLLM forum discussion, `limit_mm_per_prompt={"video": 1}` plus `mm_processor_kwargs` constraints on `max_pixels` and `nframes` significantly reduce VRAM usage ([vLLM Forum](https://discuss.vllm.ai/t/qwen-2-5-vl-for-videos/1460)).

### Offline operation guarantees

Mapping against the spec's "no external API, closed service, or cloud dependency accepted":

| Component | Offline Status | Note |
|---|---|---|
| vLLM | Fully local | Model weights stored locally |
| YOLO (Ultralytics) | Fully local | Model weights local |
| FFmpeg/OpenCV | Fully local | System binaries |
| LangGraph | Fully local | Python library |
| Model weights | Downloaded once from HuggingFace | No internet needed at runtime |
| Docker | Fully local | Isolated as a container |

## How the embedding/retrieval mechanism actually works (professor's explanation)

This underpins the memory layer, so it's captured here precisely rather than paraphrased loosely:

- Chunk the video (e.g. 10-second segments), embed each chunk, store the vectors in a vector database.
- When you ask a text question ("a forklift is lifting a load"), that sentence is *also* embedded into the same vector space. Because it's semantically related, it lands close to the relevant video-chunk vectors in that shared space — that's what makes the two comparable/searchable together.
- Retrieval: your query vector is compared against however many thousands of stored video-chunk vectors (10-second chunks over a few days of footage adds up fast) and the nearest ones are pulled back.
- Going from a retrieved vector back to text requires a **generative** model from a **compatible model family** — feed the vector to that model and ask it to turn the vector into text; it decodes the vector's meaning into a language description of what's in that chunk.
- Key mental model: a vector is just a number array representing a *meaning*. That meaning can be decoded back into video, image, or text — whichever generative head you attach. This is why chunking/embedding the raw video directly (rather than only a text summary) means we don't lose detail that a lossy summary step might discard.

This is distinct from a naive assumption Üveys initially raised ("this must be because of vector store retrieval") — professor's correction: a normal chat's "memory" isn't vector search at all, it's the entire prior conversation being stuffed as plain text into context on every turn, with no timestamp metadata — which is why asking a chat "what time did I send my last message" fails; that fact was simply never in the text. Today's VLMs/LLMs have essentially no built-in mechanism like the one described above — building it is exactly the innovation.
