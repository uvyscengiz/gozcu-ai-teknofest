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
    "GOZCU_GATEWAY_BASE_URL", "https://evren-llmapi.ssyz.org.tr/v1")
GATEWAY_API_KEY = os.environ.get("GOZCU_GATEWAY_API_KEY", "not-needed")

# Model kimliklerinin yaşadığı tek yer (CLAUDE.md). scripts/gen-litellm-config.py
# bu tabloyu kendi içinde tekrar tanımlamak yerine buradan import ediyor.
#
# 24 Ağustos: adlar organizasyonun resmî belgelerinden alındı; öncesinde
# tahmindiler ve **hepsi yanlıştı**. Bu, sanıldığından çok daha tehlikeliydi:
# gateway bilinmeyen bir model adına 404 DÖNMÜYOR, isteği sessizce `llm-fast`'e
# yönlendiriyor. Yani yanlış adlarla sistem "çalışacak", görü çağrıları bir
# metin modeline gidecek ve çıktı sessizce çöp olacaktı.
MODELS = {
    "router": os.environ.get("GOZCU_MODEL_ROUTER", "router"),
    "fast": os.environ.get("GOZCU_MODEL_FAST", "llm-fast"),
    "main": os.environ.get("GOZCU_MODEL_MAIN", "llm-large"),
    "vlm": os.environ.get("GOZCU_MODEL_VLM", "vlm"),
    "guard": os.environ.get("GOZCU_MODEL_GUARD", "guard"),
    # bge-m3-embed: R@1 0,95, çıktı boyutu 1024 — ilk isabeti en yüksek getirici.
    "embed": os.environ.get("GOZCU_MODEL_EMBED", "bge-m3-embed"),
    # `rerank` sunuluyor ama organizasyon ÖNERMİYOR: R@1 0,95'ten 0,55'e düşüyor.
    # Görev 08 bu yüzden onu çağırmıyor; alias yalnız bütünlük için burada.
    "rerank": os.environ.get("GOZCU_MODEL_RERANK", "rerank"),
}

# Video çağrıları uzun sürüyor ve sistem 1800 s'ye kadar çalışıyor; OpenAI
# istemcisinin 600 s varsayılanı bağlantıyı modelden önce kesiyor, istek
# sunucuda işlenmeye devam ediyor ama sonuç alınamıyor.
GATEWAY_TIMEOUT_S = float(os.environ.get("GOZCU_GATEWAY_TIMEOUT", "1800"))
GATEWAY_RETRIES = int(os.environ.get("GOZCU_GATEWAY_RETRIES", "3"))
