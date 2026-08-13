# Hardware Requirements

## Minimum requirements

| Component | Minimum | Recommended | Ideal |
|---|---|---|---|
| GPU | 1x RTX 3090 (24GB) | 1x RTX 4090 (24GB) | 2x RTX 4090 or A100 |
| VRAM | 16GB | 24GB | 48GB+ |
| RAM | 32GB | 64GB | 128GB |
| Disk | 50GB SSD | 100GB NVMe SSD | 500GB NVMe SSD |
| CPU | 8 cores | 16 cores | 32 cores |

## Model combination vs. VRAM

| Model combination | VRAM usage | Fits on single 24GB GPU? |
|---|---|---|
| Qwen2.5-VL-3B (single model) | ~6–8GB | Yes |
| Qwen2.5-VL-7B (single model) | ~16–18GB | Yes |
| Qwen2.5-VL-7B + Qwen2.5-7B | ~32–36GB | No (2 GPUs) |
| Qwen2.5-VL-7B (AWQ) + Qwen2.5-7B (AWQ) | ~18–22GB | Yes (feasible) |
| Qwen2.5-VL-7B + Turkish-LLM-14B | ~40–44GB | No (2 GPUs) |

## Budget note from the team

As of 2026-08-13, the team was awaiting a university budget allocation (expected within 1–2 days of the call) to fund GPU compute (e.g. Google Colab/Cloud) for a more solid technical entry. Track actual budget arrival and resulting hardware decision in [05-decisions/decision-log.md](../05-decisions/decision-log.md).
