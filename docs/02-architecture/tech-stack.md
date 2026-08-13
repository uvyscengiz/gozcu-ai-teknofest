# Technology Stack

## System overview

```
┌─────────────────────────────────────────────────────┐
│                  USER INTERFACE                       │
│            (Gradio / Streamlit / FastAPI)             │
├─────────────────────────────────────────────────────┤
│               AGENT ORCHESTRATOR                     │
│              (LangGraph / LangChain)                 │
├──────────┬──────────┬──────────┬─────────────────────┤
│  VIDEO   │PERCEPTION│  VLM     │  DECISION SUPPORT   │
│  INPUT   │  LAYER   │  LAYER   │  LAYER               │
│ (ffmpeg) │ (YOLO)  │(Qwen2.5 │ (LLM + structured   │
│          │         │  -VL)   │  JSON output)        │
├──────────┴──────────┴──────────┴─────────────────────┤
│            MODEL SERVING (vLLM)                       │
├─────────────────────────────────────────────────────┤
│         INFRASTRUCTURE (Docker / CUDA / Linux)       │
└─────────────────────────────────────────────────────┘
```

## Layer-by-layer choices

### Video processing layer

| Technology | Use | Why |
|---|---|---|
| **FFmpeg** | Video decode, frame extraction, scene detection | Industry standard, fast, handles every format |
| **OpenCV** | Frame manipulation, video I/O, image processing | Python integration, rich function set |
| **PySceneDetect** | Scene boundary detection | Content-aware scene detection, integrates with ffmpeg |
| **Katna** | Keyframe extraction | Smart keyframe selection, video summarization |

### Perception layer (low-level)

| Technology | Use | Why |
|---|---|---|
| **Ultralytics YOLOv11** | Object/person detection, pose estimation | Real-time, low latency, TensorRT support |
| **YOLOv8-Pose** | Human posture analysis, fall detection | 17-keypoint output, proven in safety scenarios |
| **DeepSORT / ByteTrack** | Object tracking | Integrates with YOLO, multi-object tracking |

Note on OpenCV vs. YOLO for detection: raw OpenCV is too algorithmic/manual for this; YOLO (and comparable models) are built on top of OpenCV internals specifically to avoid reimplementing that from scratch. Use YOLO as the detector; OpenCV stays as the video I/O layer underneath.

### Multimodal analysis layer (high-level understanding)

| Technology | Use | Why |
|---|---|---|
| **Qwen2.5-VL-7B-Instruct** | Video/frame understanding, scene interpretation | 20+ min video, Turkish support, agentic capabilities, full vLLM compatibility |
| **Qwen2.5-VL-3B (alternative)** | Low-VRAM scenarios | Runs in ~4GB VRAM, fast inference |
| **JEPA / JEPA 2** (professor-flagged, see [prior-art.md](../01-research/prior-art.md)) | Lightweight video embedding | ~300–400M params, runs on phone-class hardware |

### Decision support & NLG layer

| Technology | Use | Why |
|---|---|---|
| **Qwen2.5-7B-Instruct** (or Turkish-LLM-14B) | Turkish summary, risk assessment, action recommendation | Strong Turkish, vLLM-compatible, structured output support |
| **vLLM guided decoding** | JSON-schema-constrained structured output | Guided JSON (xgrammar backend), Pydantic model support |

### Agentic orchestration

| Technology | Use | Why |
|---|---|---|
| **LangGraph** | Agent orchestration, tool routing, multi-step reasoning | Graph-based, memory integration, dynamic tool selection |
| **LangMem** | Working memory (during video analysis) | Hot-path memory, automatic information extraction |
| **Pydantic** | Structured output schema definition | Compatible with vLLM guided decoding, type safety |

### Serving & infrastructure

| Technology | Use | Why |
|---|---|---|
| **vLLM** | Model serving (LLM + VLM) | OpenAI-compatible API, paged attention, quantization support |
| **Docker** | Containerization | Reproducibility, ease of setup |
| **FastAPI** | API backend | Fast, async, auto-generated docs |
| **Gradio / Streamlit** | Demo UI | Fast prototyping, ideal for jury demo |

See [model-strategy.md](model-strategy.md) for which model runs where and VRAM tradeoffs, and [system-design.md](system-design.md) for the full pipeline and data flow.
