# Kaynaklar

Projede fiilen kullanılan veya doğrudan dayandığımız dış kaynaklar.

## Yarışma

- **2026 Şartnamesi (3. Senaryo)** — teknik şartname. Repodaki karşılığı: [sartname.md](../sartname.md)
- [EVREN çıkarım servisi — katılımcı dokümantasyonu](https://evren-teknofest.ssyz.org.tr) — organizasyonun gateway'i. Saha notlarımız: [evren-gateway.md](evren-gateway.md)

## Kullandığımız modeller (EVREN üzerinde)

- [Qwen/Qwen3-VL-32B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-32B-Instruct) — `vlm` kademesi, video analizi
- [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3) — `bge-m3-embed` kademesi, epizodik hafıza gömmeleri
- Metin modelleri (`llm-fast`, `llm-large`, `router`, `guard`) — EVREN'in kendi takma adları, arka plandaki ağırlıklar organizasyon tarafından açıklanmadı

## Kullandığımız kütüphaneler

- [ultralytics/ultralytics](https://github.com/ultralytics/ultralytics) — YOLO nesne tespiti (`gozcu/pipeline/detect.py`)
- [qdrant/qdrant-client](https://github.com/qdrant/qdrant-client) — vektör veritabanı istemcisi (`gozcu/memory/episodic.py`)
- [openai/openai-python](https://github.com/openai/openai-python) — EVREN gateway'e OpenAI uyumlu istemci (`gozcu/core/gateway.py`)
- [microsoft/markitdown](https://github.com/microsoft/markitdown) — belge gömme için ikili dosya dönüştürücü (`gozcu/memory/library.py`)
- [pydantic](https://docs.pydantic.dev) — yapılandırılmış çıktı doğrulama
- [FastAPI](https://fastapi.tiangolo.com) — web konsol sunucusu (`gozcu/ui/server.py`)
- [OpenCV](https://docs.opencv.org) — kare işleme, video okuma

## EVREN altyapısı

- [vLLM](https://docs.vllm.ai) — EVREN'in model servisleme altyapısı. Biz doğrudan kullanmıyoruz; gateway arkasında çalışıyor
- [Qdrant](https://qdrant.tech/documentation/) — takım başına izole vektör veritabanı
