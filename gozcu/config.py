import os

VLM_BASE_URL = os.environ.get("GOZCU_VLM_BASE_URL", "http://localhost:8000/v1")
VLM_MODEL = os.environ.get("GOZCU_VLM_MODEL", "mlx-community/Qwen2.5-VL-3B-Instruct-4bit")
YOLO_MODEL_PATH = os.environ.get("GOZCU_YOLO_MODEL", "yoloe-26s-seg.pt")
# Open-vocabulary detection classes. Deliberately narrow: "person" and "vehicle"
# are universal across install types (factory, farm, police HQ, ...) and feed
# gozcu.signals's velocity/gathering computation. Hazard identification (fire,
# smoke, whatever it is per install) stays the VLM's job, not YOLO's — tested
# and confirmed unreliable for a small/occluded flame at this frame resolution,
# see docs/05-decisions/decision-log.md.
YOLO_CLASSES = os.environ.get("GOZCU_YOLO_CLASSES", "person,vehicle").split(",")
YOLO_CONFIDENCE = float(os.environ.get("GOZCU_YOLO_CONFIDENCE", "0.35"))
FRAME_FPS = float(os.environ.get("GOZCU_FRAME_FPS", "1.0"))
FRAME_WIDTH = int(os.environ.get("GOZCU_FRAME_WIDTH", "896"))

GATEWAY_BASE_URL = os.environ.get(
    "GOZCU_GATEWAY_BASE_URL", "http://localhost:4000/v1")
GATEWAY_API_KEY = os.environ.get("GOZCU_GATEWAY_API_KEY", "not-needed")

# Model kimliklerinin yaşadığı tek yer (CLAUDE.md). scripts/gen-litellm-config.py
# bu tabloyu kendi içinde tekrar tanımlamak yerine buradan import ediyor;
# organizasyon başka adlar deploy ederse düzenlenecek tek yer bu sözlük ya da
# GOZCU_MODEL_* ortam değişkenleri.
MODELS = {
    "router": os.environ.get("GOZCU_MODEL_ROUTER", "Qwen3-8B"),
    "fast": os.environ.get("GOZCU_MODEL_FAST", "Qwen3.6-35B-A3B"),
    "main": os.environ.get("GOZCU_MODEL_MAIN", "Qwen3.5-122B-A10B"),
    "vlm": os.environ.get("GOZCU_MODEL_VLM", "Qwen3-VL-30B-A3B"),
    "guard": os.environ.get("GOZCU_MODEL_GUARD", "Qwen3Guard-Gen-4B"),
    "embed": os.environ.get("GOZCU_MODEL_EMBED", "Qwen3-Embedding-4B"),
    "rerank": os.environ.get("GOZCU_MODEL_RERANK", "Qwen3-Reranker-4B"),
}

GATEWAY_TIMEOUT_S = float(os.environ.get("GOZCU_GATEWAY_TIMEOUT", "60"))
GATEWAY_RETRIES = int(os.environ.get("GOZCU_GATEWAY_RETRIES", "3"))
