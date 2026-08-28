
# ④ Projenin çalıştırılması için adım adım talimatlar

**Gözcü** · Takım **FERASET** (`team37`) · Muğla Sıtkı Koçman Üniversitesi

Bu bölüm şartname §6'nın *"projenin çalıştırılması için adım adım talimatlar
(kurulum, çalıştırma)"* kalemidir. Anlatılan her komut [README.md](../../README.md)
ile birebir aynı — burada tekrarlanmasının sebebi, jürinin şartnamenin
istediği sekiz bölümü tek bir dizinde bulabilmesi.

---

## 1. Ön koşullar

| Gereksinim | Sürüm / not |
|---|---|
| Python | ≥ 3.12 ([pyproject.toml](../../pyproject.toml)) |
| [uv](https://docs.astral.sh/uv/) | paket yöneticisi — `pip` değil |
| ffmpeg | sistem paketi, **binary olarak** çağrılıyor ([gozcu/perception/frames.py](../../gozcu/perception/frames.py)) |
| Linux: `libgl1`, `libglib2.0-0` | `opencv-python`'ın import edilebilmesi için |
| GPU | **gerekmez.** Algı katmanı (YOLO) CPU'da da çalışır; LLM/VLM/gömme çağrıları organizasyonun EVREN gateway'ine (uzak, 8×H200) gider — bkz. [01-mimari §12](01-mimari-ozeti-ve-diyagramlar.md#12-yerellik-ve-bağımsızlık) |

`uv` kurulu değilse:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## 2. Kurulum

```bash
git clone https://github.com/uvyscengiz/gozcu-ai-teknofest.git
cd gozcu-ai-teknofest
uv sync --extra dev
```

**Apple Silicon'daysan komut farklı:**

```bash
uv sync --extra dev --extra mac
```

Sebebi: `uv sync` yalnız verilen extra'ları tutar. `--extra mac` verilmezse
`mlx-vlm` (Apple Silicon'daki yerel VLM yolu) kurulmaz — kuruluysa hattâ
**silinir**. İki extra'yı birlikte vermek zorunludur.

Linux'ta sistem paketleri ayrıca gerekir:

```bash
sudo apt install ffmpeg libgl1 libglib2.0-0
```

### Ortam değişkenleri

```bash
cp .env.example .env
```

Takıma e-postayla gelen EVREN gateway ve Qdrant anahtarlarını `.env`
içine doldur — dosyanın kendisi commit edilmez (`.gitignore`). Aşağıdaki
§4'te her anahtarın ne işe yaradığı ayrıntılı listeleniyor.

### Bas-konuş (isteğe bağlı — STT)

Mikrofonla operatör kutusuna metin yazdırmak `faster-whisper` gerektirir;
ana bağımlılık değil, ayrı bir ekstra:

```bash
uv sync --extra dev --extra stt
```

Kurulu değilse `POST /api/stt` `501` döner ve mikrofon düğmesi arayüzde
devre dışı çizilir — uydurulmuş bir transkript asla dönmez.

Kuruluyken transkripsiyon **tamamen yerel** çalışır, ama bir ön koşulu var:
model ağırlıkları önbellekte olmalı. `gozcu/ui/server.py` modeli
`local_files_only=True` ile açıyor — final Bilişim Vadisi'nde fiziki, ağsız
bir salon olduğu için önbellek boşken varsayılan davranış (Hugging Face
Hub'a sessizce uzanmak) jürinin önünde ilk mikrofon basışını dondururdu.
Bu yüzden önbellek **kurulum sırasında, demo öncesinde** doldurulur:

```bash
uv run python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"
```

Model kimliği/cihaz/hesaplama tipi `gozcu/core/config.py::STT_MODEL` /
`STT_DEVICE` / `STT_COMPUTE_TYPE` — üçü de `GOZCU_STT_*` ortam
değişkenleriyle ezilebilir; değiştirilirse yukarıdaki pre-fetch komutu da
aynı değerlerle güncellenmelidir.

---

## 3. Testler

```bash
uv run pytest tests/ -v
```

---

## 4. Uygulamayı çalıştır

```bash
uv run --env-file .env python app.py
```

Konsol **http://localhost:7860** adresinde açılır. Tarayıcıda o adresi aç,
bir video yükle ve **Analizi başlat**'a bas; ekran koşu boyunca canlı akar
(SSE) — koşunun bitmesi beklenmez, kritik anlarda döngü kendiliğinden durur
ve operatöre seslenir (bkz. [01-mimari §5](01-mimari-ozeti-ve-diyagramlar.md#5-kritik-an--sekans-diyagramı)).

`--env-file` verilmezse `.env` **okunmaz**; dosya yoksa `uv` hata verir —
bu adımdan önce mutlaka `cp .env.example .env` çalıştırılmış olmalı.

### Üç görünüm

| Görünüm | Ne gösteriyor |
|---|---|
| **Operasyon** | Oynatıcı + kutu katmanı + zaman çizelgesi, olay günlüğü, onay çubuğu, operatör kutusu |
| **Şeffaflık** | Ajanlar arası devir zinciri, araç çağrı günlüğü, pencere defteri, teslim edilen dört anahtar |
| **Performans** | KPI'lar, karar dağılımı, algı ölçümü — ölçülemeyen hücre sıfır diye **gösterilmez**, boş bırakılır |

Konsol `gozcu/ui/server.py` (FastAPI) + `gozcu/ui/web/` (bağımlılıksız
statik HTML/CSS/JS) — CDN yok, harici font yok, analitik yok.

---

## 5. Gateway kurulumu — organizasyonun EVREN servisi

Varsayılan yapılandırma zaten organizasyonun uzak gateway'ine bakıyor
([.env.example](../../.env.example)):

```bash
GOZCU_GATEWAY_BASE_URL=https://evren-llmapi.ssyz.org.tr/v1
GOZCU_GATEWAY_API_KEY=      # takıma e-postayla gelen sk-evren-team37-... buraya
```

Bu adımdan sonra sistem çalışmaya hazırdır — ayrı bir model kurulumu
**gerekmez**. Gateway'i taklit eden yerel bir vekil (litellm proxy)
yalnızca geliştirme/offline demo için isteğe bağlı bir seçenektir:

```bash
uv run python scripts/gen-litellm-config.py
uv run litellm --config litellm-config.yaml --port 4000
```

Üretilen `litellm-config.yaml` varsayılan olarak **Ollama**'yı hedefler
(`http://localhost:11434/v1`, model `qwen2.5:7b`); proxy'yi çalıştırmadan
önce `ollama pull qwen2.5:7b` gerekir. Bu proxy terminali bloke eder, ayrı
bir terminalde çalıştırılmalı. `app.py`'nin model yolu bugün
`GOZCU_VLM_BASE_URL`'i okuyor (varsayılan `http://localhost:8000/v1`,
Apple Silicon'da yerel `mlx-vlm`); `GOZCU_GATEWAY_*` üretim yolu.

---

## 6. Ortam değişkenleri — tam liste

Tamamı [.env.example](../../.env.example) içinde, gerekçeleriyle. Özet:

| Grup | Anahtar | Varsayılan | Ne işe yarar |
|---|---|---|---|
| **Gateway** | `GOZCU_GATEWAY_BASE_URL` | EVREN URL'i | LLM/VLM/gömme uç noktası |
| | `GOZCU_GATEWAY_API_KEY` | *(boş)* | Bearer token — takıma özel |
| | `GOZCU_GATEWAY_TIMEOUT` | `1800` sn | Video çağrıları için — OpenAI istemcisinin 600 sn varsayılanı yetmiyor |
| | `GOZCU_GATEWAY_RETRIES` | `3` | Kademe bozulmuş sayılmadan önceki deneme sayısı |
| **Model kademeleri** | `GOZCU_MODEL_ROUTER` / `_FAST` / `_MAIN` / `_VLM` / `_GUARD` / `_EMBED` / `_RERANK` | organizasyonun resmî takma adları | Bkz. [02-framework-ve-modeller.md](02-framework-ve-modeller.md) |
| **Qdrant** | `GOZCU_QDRANT_URL` / `_PORT` / `_PREFIX` / `_API_KEY` / `_COLLECTION` | EVREN vektör servisi, `team37` | Epizodik hafıza — bkz. [06-ek-ozellikler.md](06-ek-ozellikler.md) |
| | `GOZCU_QDRANT_SCORE_THRESHOLD_RISK` / `_DIALOGUE` | `0.54` / `0.47` (kalibre edilmiş) | Emsal alaka eşikleri |
| **Kısa süreli hafıza** | `GOZCU_RECALL_WINDOW_N` | `4` | Kaç pencere tam detayla görü çağrısına taşınıyor |
| | `GOZCU_RECALL_VISION` | `1` | Bu blok görü çağrısına giriyor mu |
| **Algı** | `GOZCU_YOLO_CLASSES` | `person,forklift,truck,vehicle` | Açık sözlüklü tespit sınıfları |
| | `GOZCU_YOLO_CONFIDENCE` | `0.03` | Tespit eşiği — ölçülerek seçildi, bkz. [05-zorluklar-ve-cozumler.md](05-zorluklar-ve-cozumler.md) |
| | `GOZCU_FRAME_FPS` / `_WIDTH` | `3.0` / `640` | Algı katmanının kare çıkarım hızı/çözünürlüğü |
| **STT** | `GOZCU_STT_MODEL` / `_DEVICE` / `_COMPUTE_TYPE` | `base` / `cpu` / `int8` | Bas-konuş modeli |
| **Kütüphane** | `GOZCU_LIBRARY_DIR` | `var/library` | Yüklenen belgeler + koşu raporları |

`Onaylı_kapı`: `GOZCU_NEEDS_APPROVAL` boş bırakılırsa hiçbir araç operatör
onayı beklemez (26 Ağustos kararı — bkz. §5, §6); `halt_production_line`
adını vererek geri getirilebilir.

---

## 7. Donanım

| Bileşen | Gereksinim |
|---|---|
| **Bizim makinemiz** | Algı katmanı (YOLO+ByteTrack, CPU'da da çalışır), FastAPI konsolu, SQLite depo — GPU şart değil |
| **EVREN (organizasyon)** | LLM/VLM/gömme servisleme: 8 × NVIDIA H200, vLLM, BF16 — bkz. [01-mimari §12](01-mimari-ozeti-ve-diyagramlar.md#12-yerellik-ve-bağımsızlık) |
| **Ağ** | Yalnız EVREN'e (LLM gateway) ve EVREN'in Qdrant örneğine giden HTTPS — konsolun kendisi ağsız bir salonda da çalışır |

Minimum geliştirme makinesi: modern bir dizüstü, ~2 GB disk (`.venv` dahil),
ffmpeg. Final sunumu ağsız bir salonda geçtiği için konsolun kendisi hiçbir
CDN'e bağımlı değil; yalnız gateway çağrıları ağ ister.
