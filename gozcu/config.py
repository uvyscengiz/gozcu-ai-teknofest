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
