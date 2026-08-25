import os

VLM_BASE_URL = os.environ.get("GOZCU_VLM_BASE_URL", "http://localhost:8000/v1")
VLM_MODEL = os.environ.get("GOZCU_VLM_MODEL", "mlx-community/Qwen2.5-VL-3B-Instruct-4bit")
YOLO_MODEL_PATH = os.environ.get("GOZCU_YOLO_MODEL", "yoloe-26s-seg.pt")
# Open-vocabulary tespit sınıfları ve eşiği.
#
# 25 Ağustos'ta ÖLÇÜLDÜ ve değiştirildi. Öncesi `person,vehicle` @ 0.35 idi ve
# gerekçesi makuldü ("her kurulum tipinde evrensel"). Gerçek görüntüde sonucu
# şuydu: raf çökmesi klibinde **23 karenin 23'ünde sıfır tespit.** Forklift de
# operatör de gözle apaçık görünüyordu.
#
# Sebep eşik değil, **kelime seçimiydi.** Açık sözlüklü bir model için
# "vehicle" fazla soyut bir istem: aynı forklift "vehicle" olarak 0,25,
# "forklift" olarak 0,30 puan alıyor. Sınıfı adıyla çağırmak güveni eşiğin
# üstüne çıkarıyor — eşiği düşürmeden.
#
# Ölçüm (aynı klip / boş hat kontrolü, 896 px):
#
#   person,vehicle                  @0.35 →  0/23  ·  0/12
#   person,vehicle                  @0.20 →  2/23  ·  0/12
#   person,forklift,truck,vehicle   @0.35 →  2/23  ·  0/12
#   person,forklift,truck,vehicle   @0.20 →  6/23  ·  0/12   ← seçilen
#   person,forklift,truck,vehicle   @0.10 → 12/23  ·  1/12   ← ilk yanlış pozitif
#
# 0.20 seçildi: olay klibinde altı kare yakalanıyor, boş hat kontrolünde hâlâ
# tek bir yanlış pozitif yok. Demo klibinde (k05) tespit 7'den 19'a çıkıyor ve
# 12'si kişi — boğulma değil, zenginleşme.
#
# **Bu bir algı katmanı DEĞİŞİKLİĞİ değil, yapılandırma değişikliğidir.**
# `detect.py` donuk ve dokunulmadı; tek argümanlı `set_classes(names)` çağrısı
# iki argümanlı `get_text_pe` biçimiyle birebir aynı sonucu veriyor (ölçüldü).
#
# Tehlike tanıma (yangın, duman) hâlâ VLM'in işi — bkz. decision-log.
YOLO_CLASSES = os.environ.get(
    "GOZCU_YOLO_CLASSES", "person,forklift,truck,vehicle").split(",")
YOLO_CONFIDENCE = float(os.environ.get("GOZCU_YOLO_CONFIDENCE", "0.20"))
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

# --- Qdrant (epizodik hafıza, Görev 08) -------------------------------------
#
# Takım başına **izole örnek**; LLM ağ geçidinden GEÇMİYOR — ayrı adres, ayrı
# anahtar. Erişim yolu `{QDRANT_URL}/{QDRANT_PREFIX}/`.
QDRANT_URL = os.environ.get("GOZCU_QDRANT_URL", "https://evren-vektor.ssyz.org.tr")

# **`port=443` ZORUNLU.** Verilmezse `qdrant-client` `https://` şemasını yok
# sayıp kendi varsayılan portuna düşüyor ve istek `Connection refused` ile
# ölüyor — mesaj nedeni hiç göstermiyor, saatler buna gider.
QDRANT_PORT = int(os.environ.get("GOZCU_QDRANT_PORT", "443"))

# Her takıma port değil **yol ön eki** veriliyor. Bunun doğrudan sonucu: yalnız
# REST çalışıyor, gRPC bir ön ek üzerinden yönlendirilemez — `prefer_grpc=True`
# hiçbir yerde geçilmemeli.
QDRANT_PREFIX = os.environ.get("GOZCU_QDRANT_PREFIX", "team37")

# Anahtar LLM bearer token'ından AYRI ve **yalnız ortamdan** gelir; koda
# yazılmaz. Boşsa modül yerel süreç içi bir Qdrant'a düşer (bkz. gozcu/memory.py).
QDRANT_API_KEY = os.environ.get("GOZCU_QDRANT_API_KEY", "")

QDRANT_COLLECTION = os.environ.get("GOZCU_QDRANT_COLLECTION", "episodes")

# Koleksiyonu organizasyon değil biz kuruyoruz, yani boyutu da biz veriyoruz.
# 1024 = `bge-m3-embed`'in çıktı boyutu (canlı doğrulandı, bkz. MODELS["embed"]).
# Gömme modeli değişirse burası da değişmeli; yanlış boyutlu vektör yazılmıyor.
QDRANT_VECTOR_SIZE = int(os.environ.get("GOZCU_QDRANT_VECTOR_SIZE", "1024"))

QDRANT_TIMEOUT_S = int(os.environ.get("GOZCU_QDRANT_TIMEOUT", "600"))
