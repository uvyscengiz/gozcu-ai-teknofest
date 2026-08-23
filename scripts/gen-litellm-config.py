import os
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
# pyproject `package = false` diyor: `gozcu` sadece pytest'in rootdir eklemesiyle
# import edilebiliyor. Script doğrudan koşturulduğunda sys.path[0] `scripts/`
# olur ve düz bir `from gozcu.config import ...` ModuleNotFoundError verir.
sys.path.insert(0, str(REPO_ROOT))

from gozcu.config import MODELS  # noqa: E402 — sys.path yukarıda kuruluyor

text = os.environ.get("GOZCU_LOCAL_MODEL", "qwen2.5:7b")
vision = os.environ.get("GOZCU_LOCAL_VLM", text)
base = os.environ.get("GOZCU_LOCAL_BASE", "http://localhost:11434/v1")
# Kademe adları gozcu/config.py'daki MODELS'ten geliyor — model kimlikleri
# CLAUDE.md gereği yalnızca orada yaşıyor. Yerel yedekte sadece `vlm` görü
# modeline gider, gerisi metin modeline.
tiers = {alias: (vision if tier == "vlm" else text)
         for tier, alias in MODELS.items()}
lines = ["model_list:"]
for alias, target in tiers.items():
    lines.append(f"  - model_name: {alias}")
    lines.append(f"    litellm_params: {{model: openai/{target}, "
                 f"api_base: {base}, api_key: none}}")
(REPO_ROOT / "litellm-config.yaml").write_text("\n".join(lines) + "\n")
print("litellm-config.yaml yazıldı:", len(tiers), "adet")
