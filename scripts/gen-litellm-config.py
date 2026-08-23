import os
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

text = os.environ.get("GOZCU_LOCAL_MODEL", "qwen2.5:7b")
vision = os.environ.get("GOZCU_LOCAL_VLM", text)
base = os.environ.get("GOZCU_LOCAL_BASE", "http://localhost:11434/v1")
# Bu yedi kademe adı docs/tasks/03-gateway.md'deki MODELS bloğuyla birebir aynı
# kalmalı. Görev 03 gozcu/config.py'a MODELS'i eklediğinde bu script listeyi
# burada tekrar tanımlamak yerine oradan import etmeli.
tiers = {"Qwen3-8B": text, "Qwen3.6-35B-A3B": text, "Qwen3.5-122B-A10B": text,
         "Qwen3-VL-30B-A3B": vision, "Qwen3Guard-Gen-4B": text,
         "Qwen3-Embedding-4B": text, "Qwen3-Reranker-4B": text}
lines = ["model_list:"]
for alias, target in tiers.items():
    lines.append(f"  - model_name: {alias}")
    lines.append(f"    litellm_params: {{model: openai/{target}, "
                 f"api_base: {base}, api_key: none}}")
(REPO_ROOT / "litellm-config.yaml").write_text("\n".join(lines) + "\n")
print("litellm-config.yaml yazıldı:", len(tiers), "adet")
