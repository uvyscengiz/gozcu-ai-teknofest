# Gözcü

Fabrika kamera kaydını izleyip olayları fark eden, riski değerlendiren ve
operatörle Türkçe konuşan bir karar destek sistemi. Video yüklenir, sistem onu
baştan sona işler ve **kritik ana geldiğinde orada durup karar verir** — video
bitmeden operatöre seslenir, saha sistemlerini arar.

Bu belge `git clone`'dan çalışan uygulamaya kadar tek başına yeterli olacak
şekilde yazıldı; başka bir dosyaya bakman gerekmiyor.

## Kurulum

`uv` kurulu değilse önce onu kur:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```bash
git clone https://github.com/uvyscengiz/gozcu-ai-teknofest.git
cd gozcu-ai-teknofest
uv sync --extra dev
```

**Apple Silicon'daysan** komut farklı:

```bash
uv sync --extra dev --extra mac
```

Sebebi: `uv sync` varsayılan olarak *tam* eşitler. Yalnız `--extra dev`
verirsen `mlx-vlm` **kurulu değilse kurulmaz / kuruluysa silinir**, çünkü
sync sadece verdiğin extra'ları tutar — Apple Silicon'daki yerel VLM yolu
bu paket olmadan çalışmaz. İki extra'yı birden ver.

### Bas-konuş (isteğe bağlı, STT)

Mikrofonla operatör kutusuna metin yazdırmak için `faster-whisper`
gerekiyor — ana bağımlılık değil, ayrı bir ekstra (`stt`):

```bash
uv sync --extra dev --extra stt
```

Kurulu değilse `POST /api/stt` `501` döner ve mikrofon düğmesi devre dışı
çizilir — örnek/uydurulmuş bir transkript asla dönmez.

Kuruluyken transkripsiyon TAMAMEN yerel çalışır, ama bunun bir ÖN KOŞULU
var: **model ağırlıkları önbellekte olmalı.** `gozcu/ui/server.py` modeli
`local_files_only=True` ile açıyor — final Bilişim Vadisi'nde fiziki, ağsız
bir salon; önbellek boşken varsayılan davranış (Hugging Face Hub'a sessizce
uzanmak) jürinin önünde ilk mikrofon basışını dondururdu/hata verdirirdi.
Bunun yerine önbellek eksikse uç açıkça `503` döner. Bu yüzden önbelleği
**kurulum sırasında, demo öncesinde** doldur:

```bash
uv run python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"
```

Model kimliği/cihaz/hesaplama tipi `gozcu/config.py::STT_MODEL` /
`STT_DEVICE` / `STT_COMPUTE_TYPE` — üçü de `GOZCU_STT_*` ortam
değişkenleriyle ezilebilir. Onları değiştirirsen yukarıdaki pre-fetch
komutunu da AYNI değerlerle güncelle — farklı bir modelle doldurulmuş
önbellek, sunucunun aradığı modeli bulamaz ve yine `503` döner.

### Linux sistem paketleri

Aşağıdaki iki paket Python wheel'leriyle gelmiyor ve ikisi de zorunlu:

```bash
sudo apt install ffmpeg libgl1 libglib2.0-0
```

- `ffmpeg` — `gozcu/frames.py` kare çıkarmak için bunu bir *binary* olarak
  çağırıyor (subprocess), Python paketi olarak değil.
- `libgl1`, `libglib2.0-0` — `opencv-python`'ın import edilebilmesi için
  gereken sistem kütüphaneleri; olmadan `import cv2` patlar.

## Gateway kurulumu

`GOZCU_GATEWAY_*`, Görev 03'ün tüketeceği bir sözleşme — bugün onu okuyan
kod yok. `app.py`'nin model yolu şu an `GOZCU_VLM_BASE_URL`'i okuyor
(varsayılan `http://localhost:8000/v1`, Apple Silicon'da yerel mlx). Aşağıdaki
`litellm` proxy'sini kurabilirsin ama `--env-file .env` verdiğinde bugün
`app.py`'yi ona yönlendirmez.

```bash
cp .env.example .env
uv run python scripts/gen-litellm-config.py
```

Üretilen `litellm-config.yaml` varsayılan olarak **Ollama**'yı hedefler
(`http://localhost:11434/v1`, model `qwen2.5:7b`) — proxy'yi çalıştırmadan
önce `ollama pull qwen2.5:7b` gerekir, yoksa `/v1/models` yanıt verir ama her
tamamlama isteği başarısız olur.

Sonra proxy'yi **ayrı bir terminalde** çalıştır — bu komut terminali bloke
eder, arka planda bırakma:

```bash
uv run litellm --config litellm-config.yaml --port 4000
```

## Testler

```bash
uv run pytest tests/ -v
```

## Uygulamayı çalıştır

```bash
uv run --env-file .env python app.py
```

Konsol **http://localhost:7860** adresinde açılıyor. Tarayıcıda o adresi aç,
bir video yükle ve **Analizi başlat**'a bas; ekran koşu boyunca canlı akıyor
(SSE), koşunun bitmesi beklenmiyor.

Üç görünüm var:

| Görünüm | Ne gösteriyor |
|---|---|
| **Operasyon** | Oynatıcı + kutu katmanı + zaman çizelgesi, olay günlüğü, onay çubuğu, operatör kutusu |
| **Şeffaflık** | Ajanlar arası devir zinciri, araç çağrı günlüğü, pencere defteri, teslim edilen dört anahtar |
| **Performans** | KPI'lar, karar dağılımı, algı ölçümü — ölçülemeyen hücre sıfır diye GÖSTERİLMİYOR |

`--env-file` verilmezse `.env` **okunmaz**; `.env` dosyası yoksa da `uv` hata
verir — bu yüzden bu adımdan önce mutlaka `cp .env.example .env`
çalıştırılmış olmalı (yukarıdaki Gateway kurulumu adımı). `GOZCU_GATEWAY_*`
bugün hiçbir kod tarafından okunmuyor; model yolu `GOZCU_VLM_BASE_URL`'e
bakıyor.

Konsol **`gozcu/ui/server.py`** (FastAPI) + **`gozcu/ui/web/`** (statik
HTML/CSS/JS). 27 Ağustos 2026'ya kadar burada bir Gradio konsolu vardı
(`gozcu/ui/console.py`); emekliye ayrıldı, sebepleri
[docs/tasks/21-web-konsolu.md](docs/tasks/21-web-konsolu.md) içinde.

## Bağımlılıklar

Hepsi `pyproject.toml` içinde; burada yalnız **niçin** oldukları:

| Paket | Niçin |
|---|---|
| `fastapi` · `uvicorn` | Konsolun HTTP sunucusu |
| `sse-starlette` | Durum yayını (`GET /api/run/{id}/events`) |
| `anyio` | Bloklayan işi olay döngüsünün dışına atma (`anyio.to_thread.run_sync`) |
| `python-multipart` | Video yüklemesi (`multipart/form-data`) — yoksa FastAPI import anında hata veriyor |
| `openai` | Gateway istemcisi (OpenAI uyumlu uçlar) |
| `pydantic` | Paylaşılan sözleşme (`gozcu/models.py`) |
| `ultralytics` · `lap` · `opencv-python` · `pillow` · `numpy` | Algı katmanı: YOLO tespiti, iz eşleme, kare çıkarma/çizim |
| `clip` | Kare-metin benzerliği |
| `qdrant-client` | Epizodik hafıza (kurulu/erişilir değilse yerel yedeğe düşüyor) |
| `matplotlib` | Benchmark grafikleri |

Ekstralar: `dev` (pytest + yerel gateway için `litellm[proxy]`) ·
`mac` (`mlx-vlm`, Apple Silicon'da yerel VLM) · `stt` (`faster-whisper`,
bas-konuş).

**Harici ağ bağımlılığı yok.** Konsol hiçbir CDN, font ya da analitik
servisine çıkmıyor; `gozcu/ui/web/` altındaki her şey depodan servis
ediliyor.

## Daha fazlası

Görev bazlı iş bölümü ve her görevin bağımsız kurulum/doğrulama adımları için
[docs/tasks/README.md](docs/tasks/README.md) içine bak.
