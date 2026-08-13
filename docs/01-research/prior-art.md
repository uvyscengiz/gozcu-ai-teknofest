# Prior Art & Reference Projects

## Industry examples

### NVIDIA VSS (Video Search & Summarization) — Public Safety Blueprint

One of the most mature references for real-time video stream processing + agentic decision support. Two main components:

- **Real-time streaming component:** ingests camera feeds, processes via computer vision + streaming analytics + VLM techniques
- **Agentic component:** interprets user requests, coordinates sub-agents, produces natural-language responses

Models used: NVIDIA Nemotron Nano 9B v2 (LLM), Cosmos3 Nano Reasoner (VLM). Directly relevant inspiration: real-time detection + VLM analysis + LLM orchestration layers, same shape as our design.

Source: [NVIDIA VSS Public Safety Blueprint](https://docs.nvidia.com/vss/3.2.1/publicsafety-docs/Blueprint-deep-dive.html)

### SafetyCommander Agent — Factory Safety Monitoring

Open-source AI agent (HumphreySun98) that watches factory-floor camera feeds and reasons about safety risks. Notable from the Zapdos Labs hackathon (June 2026): it reads written safety policies and cross-references them against camera footage — directly parallel to our scenario.

Source: [SafetyCommander Agent](https://letsdatascience.com/news/safetycommander-agent-provides-autonomous-factory-safety-mon-d96c13fa)

### Hub — Agentic Computer Vision Platform

Multi-agent architecture providing comprehensive security monitoring; each plugin runs as an independent agent, giving modular extensibility. Aligns with the competition's "dynamic tool selection" requirement.

Source: [Hub: Agentic Computer Vision Platform](https://app.readytensor.ai/publications/hub-an-agentic-computer-vision-platform-for-intelligent-video-analytics-TwkX2eUe8HJU)

### SafeZone — Real-Time Video Analytics for Industrial Safety

SmartInternz team project. Real-time industrial safety video analytics: workplace accidents, PPE (personal protective equipment) detection, hazardous-situation detection.

Source: [SafeZone GitHub](https://github.com/smartinternz02/SBSPS-Challenge-10024-SafeZone-Real-time-Video-Analytics-for-Industrial-Safety)

### YOLO-VLM Pattern (Roboflow)

Now an industry-standard pattern: a lightweight YOLO model processes every frame in real time; only flagged frames (unusual object, unusual scene) get routed to the VLM/LLM layer. Gives both speed and depth.

> "Build the YOLO-VLM pattern: a lightweight YOLO front-end processes every frame in real time, and a deeper LLM layer reasons over what the front-end found."
> — [yolovlm.com](https://yolovlm.com/)

## GitHub reference projects

### Video understanding & multimodal agents

| Project | Description | License | Link |
|---|---|---|---|
| **VideoAgent (HKUDS)** | All-in-one agentic framework. Storyboard Agent, video summarization, insight extraction. Multi-agent architecture. | — | [github.com/HKUDS/VideoAgent](https://github.com/HKUDS/VideoAgent) |
| **VideoAgent (YueFan1014)** | ECCV 2024. Memory-augmented multimodal agent. Structured memory + 4 tools (video segment localization, object memory query, etc.) | Apache 2.0 | [github.com/YueFan1014/VideoAgent](https://github.com/YueFan1014/VideoAgent) |
| **vLLM** | High-performance LLM inference/serving. Multimodal video support, structured output (guided decoding). | Apache 2.0 | [github.com/vllm-project/vllm](https://github.com/vllm-project/vllm) |
| **LLaVA-NeXT / LLaVA-Video** | Open-source large multimodal model. Video understanding, LLaVA-Video-178K dataset. | Apache 2.0 | [github.com/LLaVA-VL/LLaVA-NeXT](https://github.com/LLaVA-VL/LLaVA-NeXT) |
| **Qwen2.5-VL** | Alibaba multimodal LLM. 20+ min video understanding, Turkish support, agentic capabilities. | Apache 2.0 | [github.com/QwenLM/Qwen2.5-VL](https://github.com/QwenLM/Qwen2.5-VL) |
| **Video-LLaVA (PKU)** | EMNLP 2024. Unified image+video representation. LLM-based video reasoning. | — | [github.com/PKU-YuanGroup/Video-LLaVA](https://github.com/PKU-YuanGroup/Video-LLaVA) |
| **SlowFast-LLaVA (Apple)** | Training-free baseline for video LLMs. | — | [github.com/apple/ml-slowfast-llava](https://github.com/apple/ml-slowfast-llava) |
| **mattsvlm** | VLM-based video processing POC. Frame extraction → temporal decomposition → multimodal LLM analysis. | — | [github.com/vast-data/mattsvlm](https://github.com/vast-data/mattsvlm) |

### Object detection & workplace safety

| Project | Description | Link |
|---|---|---|
| **Ultralytics YOLO** | State-of-the-art object detection. YOLOv8/11/12, pose estimation, tracking. | [github.com/ultralytics/ultralytics](https://github.com/ultralytics/ultralytics) |
| **FallSafe (YOLO11)** | Real-time fall detection. YOLO-based, health/safety applications. | [github.com/FallSafe/FallSafe-yolo11](https://github.com/FallSafe/FallSafe-yolo11) |
| **Fall Detection (YOLOv8)** | Abnormal-posture detection with YOLOv8, real-time alerting. | [github.com/AAC-Open-Source-Pool/Fall-Detection](https://github.com/AAC-Open-Source-Pool/Fall-Detection-and-Human-Activity-Recognition) |
| **SafeZone** | Real-time industrial safety video analytics. | [github.com/smartinternz02/...SafeZone](https://github.com/smartinternz02/SBSPS-Challenge-10024-SafeZone-Real-time-Video-Analytics-for-Industrial-Safety) |

### Agentic frameworks

| Project | Description | Link |
|---|---|---|
| **LangGraph** | LangChain's agentic orchestration framework. Graph-based, memory, tool use, multi-step reasoning. | [github.com/langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) |
| **LangMem** | Long-term memory management for LangGraph. Hot-path memory tools + background memory manager. | [github.com/langchain-ai/langmem](https://github.com/langchain-ai/langmem) |
| **LlamaIndex** | Data framework, agentic workflows, multimodal support. | [github.com/run-llama/llama_index](https://github.com/run-llama/llama_index) |

### Turkish LLM models

| Project | Description | Link |
|---|---|---|
| **Turkish-LLM** | Turkey's first comprehensive open-source Turkish LLM family (1.5B–32B). Qwen2.5-based, SFT+DPO. Scores 61.33 on TurkishMMLU. | [github.com/ogulcanaydogan/Turkish-LLM](https://github.com/ogulcanaydogan/Turkish-LLM) |
| **TURNA** | 1.1B-parameter Turkish encoder-decoder model. NLU and generation. | [ACL Anthology](https://aclanthology.org/2024.findings-acl.600.pdf) |
| **TurkishMMLU** | Turkish massive multitask language understanding benchmark. | [github.com/ArdaYueksel/TurkishMMLU](https://github.com/ArdaYueksel/TurkishMMLU) |
| **Awesome Turkish LLMs** | Curated list of Turkish language models. | [github.com/kesimeg/awesome-turkish-language-models](https://github.com/kesimeg/awesome-turkish-language-models) |

## Additional models flagged by the professor (not yet in the original research doc)

- **JEPA / JEPA 2** (Meta) — ~300–400M parameters, small enough to run on-device (even phone-class hardware). Add to video-understanding model shortlist alongside Qwen2.5-VL.
- **Facebook segment-editing model** — a segmentation/editing model worth evaluating for whether it subsumes what YOLO does for our use case (see [decision-log.md](../05-decisions/decision-log.md#object-detection-model-choice)).
- Gemini multimodal embedding vs. Qwen embedding — professor's recollection (unconfirmed, worth verifying): Qwen's video-embedding work predates Gemini's multimodal embedding by roughly a month; architecturally Gemini claims to fuse audio+text+video+image into one vector, while Qwen (per professor's memory of having reviewed its internals previously) represents audio and video as separate token streams before fusing with the text vector. For our purposes both produce a comparable end result — must-check either way, Qwen is the safer default given local-serving and Turkish-support requirements.

See [06-references/sources.md](../06-references/sources.md) for the full flat link list.
