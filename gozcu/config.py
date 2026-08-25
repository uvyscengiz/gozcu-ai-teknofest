import os

VLM_BASE_URL = os.environ.get("GOZCU_VLM_BASE_URL", "http://localhost:8000/v1")
VLM_MODEL = os.environ.get("GOZCU_VLM_MODEL", "mlx-community/Qwen2.5-VL-3B-Instruct-4bit")
YOLO_MODEL_PATH = os.environ.get("GOZCU_YOLO_MODEL", "yoloe-26s-seg.pt")
# Open-vocabulary tespit sınıfları ve eşiği.
#
# ## 25 Ağustos, birinci ölçüm: kelime seçimi
#
# Öncesi `person,vehicle` @ 0.35 idi ve gerekçesi makuldü ("her kurulum
# tipinde evrensel"). Gerçek görüntüde sonucu şuydu: raf çökmesi klibinde
# **23 karenin 23'ünde sıfır tespit.** Forklift de operatör de gözle apaçık
# görünüyordu. Sebep eşik değil, **kelime seçimiydi** — aynı forklift
# "vehicle" olarak 0,25, "forklift" olarak 0,30 puan alıyor. Sınıfı adıyla
# çağırmak güveni eşiğin üstüne çıkarıyor.
#
# ## 25 Ağustos, ikinci ölçüm: eşiğin kendisi (0.20 → 0.03)
#
# İlk ölçüm eşiği hiç sorgulamadı ve 0.20'yi "yanlış pozitif yok" diye
# seçti. Elle etiketlenmiş bir kayıtla (tekstil fabrikası kazası, 116 kare,
# `benchmark/perception.py`) bakıldığında o seçim **duyarlılığı katlediyordu.**
#
# 20 kişinin bulunduğu tek bir karede modele conf=0.01 ile sorulduğunda
# **60 kişi adayı** dönüyor: 14'ü 0,05 üstünde, 10'u 0,10 üstünde, yalnız
# 5'i 0,20 üstünde. Yani model kalabalığı BULUYOR; boru hattı onu eşikte
# atıyordu. Bu bir tespit kapasitesi sorunu değil, kalibrasyon sorunu:
# COCO ile eğitilmiş modeller seyrek ve iyi aydınlatılmış insanlarda
# kalibre, kapalı/küçük/loş örnekleri sistematik olarak düşük puanlıyor.
#
# Uçtan uca ölçüm (gerçek boru hattı, aynı 116 kare):
#
#   conf   varlık duyarlılığı   sayım duyarlılığı   zirve kişi   t=49'da kişi
#   0.20         %72,4                %11,0             6             0
#   0.05         %92,2                %22,8            16             1
#   0.03         %97,4                %31,0            21             1   ← seçilen
#
# (Sayım duyarlılığı takip vetosu kaldırıldıktan sonra 0.03'te %83,4'e
# çıkıyor — bkz. `gozcu/track.py`. İki değişiklik birbirini çarpıyor.)
#
# **Bedeli ölçüldü ve saklanmıyor:** olaysız kontrol klibinde (12 kare,
# gerçek 0 kişi) yanlış pozitif 0'dan **3 kutu / 3 kare**'ye çıkıyor.
# Kabul edildi: bir güvenlik sisteminde 12 karede 3 fazladan kutu, 20
# kişilik bir kalabalığı 1 kişi saymaktan iyidir. Zamansal tutarlılık
# (ByteTrack'in düşük güven aşaması) bunların bir kısmını ayıklıyor.
#
# ## Ölçülüp ELENEN yollar — tekrar denenmesin
#
#   çözünürlük 896/1280   → TERS ETKİ. Kişi güveni 640'ta 0,647; 896'da
#                           0,159; 1280'de sıfır tespit. Kaynak 960x720 ve
#                           gerçek optik detay o kadar; büyütmek gürültüyü
#                           esnetip nesneyi modelin kalibre olduğu ölçek
#                           dağılımının dışına itiyor.
#   daha büyük model      → TERS ETKİ. conf 0,05'te sayım duyarlılığı:
#                           11n %89,7 · 11s %79,3 · 11l %64,1 · 11m %56,6.
#   YOLO26 / NMS'siz      → yolo11n'i geçemedi.
#   NMS iou 0,3–0,4       → YÖN YANLIŞ. `iou` bastırma eşiği; düşük = daha
#                           çok bastır. F1: 0,3 %72,2 · 0,7 %82,4 · 0,8 %82,8.
#
# Tehlike tanıma (yangın, duman) hâlâ VLM'in işi — bkz. decision-log.
YOLO_CLASSES = os.environ.get(
    "GOZCU_YOLO_CLASSES", "person,forklift,truck,vehicle").split(",")
YOLO_CONFIDENCE = float(os.environ.get("GOZCU_YOLO_CONFIDENCE", "0.03"))
# Kare hızı. 25 Ağustos'a kadar 1.0 idi ve gerekçesi "görü bütçesini
# koruma"ydı — ama o gerekçe YANLIŞTI: görü kademesine giden şey bizim
# çıkardığımız kareler değil, `run.py:_clip_for`'un kaynak videodan kestiği
# mp4. Kare hızı ile VLM maliyeti zaten ayrık; 1 fps hiçbir bütçeyi
# korumuyordu, yalnız kaynak karelerin %96,6'sını atıyordu.
#
# Ölçüm (tekstil kazası, saniye bazlı — bkz. aşağıdaki uyarı):
#
#   fps   varlık   sayım   t=49'da kişi   gerçek zaman katsayısı
#    1     %97,4   %83,4        1                 0,13
#    2     %99,1   %91,0        1                 0,22
#    3     %99,1   %93,1        1                 0,33   ← seçilen
#    5     %99,1   %96,6        2                 1,03
#
# 3 seçildi: 5'in kazandığı 3,5 puan, gerçek zaman katsayısını 0,33'ten
# 1,03'e çıkarıyor — yani işleme videodan uzun sürmeye başlıyor ve geriye
# görü çağrıları için bütçe kalmıyor.
#
# **UYARI — kare hızları arası karşılaştırma saniye bazlı yapılmalı.**
# ffmpeg'in `fps` filtresi farklı hızlarda aynı kaynak karesini SEÇMİYOR:
# 1 fps'teki t=8 ile 5 fps'teki t=8 farklı görüntüler (ölçüldü, ortalama
# mutlak fark 3–13 gri seviye). Kare bazlı karşılaştırıldığında yükselen
# kare hızı sahte bir GERİLEME gibi göründü ve bir ölçüm turu buna gitti.
# `benchmark/perception.py:per_second` bu yüzden var.
FRAME_FPS = float(os.environ.get("GOZCU_FRAME_FPS", "3.0"))
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

# **Metin kademeleri o 1800 saniyeyi PAYLAŞMIYOR.** 26 Ağustos'ta canlı
# koşuda ölçüldü: `fast.ask` **1106 saniye** asılı kaldı ve hâlâ sürüyordu.
# Tek bir deneme bile bitmediği için yeniden deneme hiç tetiklenmedi ve
# konsol dondu — kullanıcının "rastgele takılıyor" dediği şey buydu.
#
# Yukarıdaki 1800 s VİDEO çağrıları için seçilmişti ama her kademeye
# uygulanıyordu. Aynı koşuda ölçülen normal gecikmeler:
#
#     router 0,3–1,8 s · fast 0,9–1,3 s · main 0,8–2,6 s · guard 0,1 s
#     vlm    7,0–8,7 s   ← uzun olan yalnız bu
#
# 90 s, ölçülen en yavaş metin çağrısının (2,6 s) otuz katı: sağlıklı hiçbir
# çağrıyı kesmeyecek kadar geniş, asılan bir çağrıyı kesintiye çevirecek
# kadar dar. Kesinti koşuyu düşürmüyor (bkz. `Gateway.ask`) — donma
# düşürüyordu.
GATEWAY_TEXT_TIMEOUT_S = float(
    os.environ.get("GOZCU_GATEWAY_TEXT_TIMEOUT", "90"))

#: Uzun zaman aşımını hak eden kademeler. Geri kalan her şey metin.
LONG_TIMEOUT_TIERS = frozenset({"vlm"})

GATEWAY_RETRIES = int(os.environ.get("GOZCU_GATEWAY_RETRIES", "3"))

# Şemalı her çağrının varsayılan token tavanı.
#
# `Gateway.ask` bu arızayı zaten tarif ediyordu: üst sınır olmadan strict-JSON
# kod çözümü kaçak tekrara girip `max_tokens` tükenene kadar yineliyor. Ama
# tavan yalnız GÖRÜ çağrısına konmuştu; sentezleyici, yönlendirici, risk
# analisti ve raportör tavansızdı. Ölçülen bedel (26 Ağu, canlı koşu): aynı
# koşuda `fast.ask` **91,9 s** ve **183,2 s**, 0,01 MB'lık isteklerde. Aynı
# koşuda router 0,4 s, guard 0,2 s — sorun ne bağlantıda ne ağ geçidinde,
# yalnız şemalı kod çözümündeydi.
#
# **Zaman aşımı bunu yakalayamaz:** httpx'in `timeout`'u işlem başına, toplam
# değil. Model token üretmeye devam ettikçe okuma zaman aşımı tetiklenmiyor —
# bağlantı ölü değil, yavaş. Tavan zaman aşımının YERİNE değil, yanına.
#
# 2048 bilerek geniş: 128, 256 ve 512 ölçüldü ve üçü de **boş dize** üretti
# (akıl yürütme izi bütçeyi yiyor, bkz. `interpreter.MAX_TOKENS`). Dar bir
# tavan kaçak kod çözümünü değil, çıktının kendisini öldürür.
SCHEMA_MAX_TOKENS = int(os.environ.get("GOZCU_SCHEMA_MAX_TOKENS", "2048"))

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
