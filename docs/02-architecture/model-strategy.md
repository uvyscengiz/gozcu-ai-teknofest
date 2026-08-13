# Model Strategy

## Selection matrix

| Scenario | VLM Model | LLM Model | VRAM Needed | Turkish Quality | Speed |
|---|---|---|---|---|---|
| **MVP (limited hardware)** | Qwen2.5-VL-3B-Instruct | Qwen2.5-3B-Instruct | ~8GB | Medium | Fast |
| **Recommended (balanced)** | Qwen2.5-VL-7B-Instruct | Qwen2.5-7B-Instruct | ~16–20GB | Good | Medium |
| **Strong (final demo)** | Qwen2.5-VL-7B + Turkish-LLM-14B | Turkish-LLM-14B-Instruct | ~32GB | Very good | Medium-slow |
| **Max quality** | Qwen3-VL (MoE) | Qwen3-VL | ~80GB+ | Very good | Slow |

## Recommended approach: two-model strategy

**VLM (visual/video understanding):** Qwen2.5-VL-7B-Instruct
- Video input support (vLLM `video_url` API)
- Scene interpretation, object identification, event description
- Can produce Turkish output directly

**LLM (decision support + NLG):** Turkish-LLM-14B-Instruct (Qwen2.5-14B based)
- Turkish summary generation (61.33 on TurkishMMLU)
- Risk assessment and action recommendation
- Structured JSON output (via vLLM guided decoding)

> **Note:** If VRAM-constrained, a single model (Qwen2.5-VL-7B) can take both roles — it can both understand video and produce Turkish text.

## Quantization options

For constrained hardware:

| Method | VRAM Savings | Quality Loss | Compatibility |
|---|---|---|---|
| **AWQ (Activation-aware Weight Quantization)** | ~50% | Low | vLLM native support |
| **GPTQ** | ~50% | Low-medium | vLLM native support |
| **GGUF (llama.cpp)** | ~60–70% | Medium | Ollama (not vLLM) |
| **FP8** | ~50% | Very low | Requires H100+ |

## Turkish video model as a stretch goal

The professor's suggestion, drawing on his own PhD-era model-building work: if time allows, attempt to produce a Turkish-specialized video model derived from Qwen's video model — adapting the tokenizer and embeddings for Turkish. This is explicitly framed as something to *investigate feasibility of*, not a committed deliverable — "see whether time allows." Tracked as a stretch item in [03-planning/roadmap.md](../03-planning/roadmap.md#stage-5-stretch-features).

## Open question flagged for follow-up

Whether the Facebook segment-editing model referenced by the professor duplicates YOLO's role for our use case — if so, we can collapse detection + segmentation into one model rather than running both. See [05-decisions/action-items.md](../05-decisions/action-items.md).
