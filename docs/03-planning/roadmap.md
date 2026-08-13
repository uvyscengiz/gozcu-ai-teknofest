# Development Roadmap

## Stage 1: MVP (1–2 weeks)

- [ ] vLLM setup, serve Qwen2.5-VL-7B
- [ ] FFmpeg-based video → frame extraction pipeline
- [ ] Basic object detection with YOLOv11
- [ ] Scene interpretation with Qwen2.5-VL (frame-based)
- [ ] Basic JSON output generation (guided decoding)
- [ ] Basic demo UI with Gradio

**MVP goal:** a minimum system that takes one video and produces JSON output.

## Stage 2: Agentic pipeline (2–3 weeks)

- [ ] LangGraph agent orchestration setup
- [ ] Tool definitions and agent routing
- [ ] Scene segmentation with PySceneDetect
- [ ] Event timeline builder (merge + dedup)
- [ ] Risk assessment module
- [ ] Action recommendation module
- [ ] Working memory (LangMem) integration
- [ ] Error handling and fallback mechanisms

## Stage 3: Quality and optimization (1–2 weeks)

- [ ] Turkish LLM (Turkish-LLM-14B) integration
- [ ] Prompt engineering and fine-tuning
- [ ] Benchmark dataset preparation (test videos)
- [ ] KPI metric implementation
- [ ] Performance optimization (quantization, batching)
- [ ] Anomaly detection (falls, crowding, stillness)

## Stage 4: Documentation and demo (1 week)

- [ ] System architecture diagram
- [ ] Setup documentation
- [ ] Challenges encountered and solutions
- [ ] Benchmark results report
- [ ] Demo video (max 10 min)
- [ ] Presentation slides (PDF + PPTX)
- [ ] Code cleanup and modularity pass

## Stage 5: Stretch features (innovation — 10% of score)

- [ ] Multi-video synchronized analysis
- [ ] Audio analysis (transcription via Whisper)
- [ ] Real-time streaming mode (RTSP)
- [ ] Web dashboard (live monitoring)
- [ ] Event report export (PDF)
- [ ] Configuration panel (risk thresholds)
- [ ] Turkish video model feasibility investigation (tokenizer/embedding adaptation of Qwen's video model) — see [02-architecture/model-strategy.md](../02-architecture/model-strategy.md#turkish-video-model-as-a-stretch-goal)

## Immediate next step (before Stage 1 really starts)

Per the professor's guidance on 2026-08-13, don't jump straight into building the LangGraph pipeline. First: **assess where the system actually stands today** with the simplest possible checks (run a VLM on a single image/video locally, run YOLO/JEPA/Qwen once each) before adding complexity. See [05-decisions/action-items.md](../05-decisions/action-items.md) for the concrete pre-next-meeting checklist — that list supersedes jumping ahead into Stage 1 tasks until it's done.
