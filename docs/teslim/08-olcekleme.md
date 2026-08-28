
# Bölüm 8 — Ölçekleme noktasında gerekli ihtiyaçlar

**Gözcü** · Takım **FERASET** (`team37`) · Muğla Sıtkı Koçman Üniversitesi

Bu bölüm şartname §6'nın *"ölçekleme noktasında gerekli ihtiyaçlar"*
kalemidir. Kaynaklar: [`docs/references/evren-gateway.md`](../references/evren-gateway.md)
(organizasyonun gateway'i üzerine takımın kendi ölçümleri) ve
[`docs/decisions/decision-log.md`](../decisions/decision-log.md).

---

## 1. Mimarinin ölçeklemeye hazır tasarım kararları

Gözcü'nün mimarisi baştan **katmanlı ayrışma** ilkesiyle kuruldu. Bu kararlar
ölçekleme için sıfırdan yazılmayı değil, yapılandırma değişikliklerini
gerektiren bir zemin sağlıyor.

### (a) Algı katmanı tamamen yerel ve bağımsız

Algı (YOLOE + ByteTrack + sinyal çıkarımı) **hiçbir ağ çağrısı yapmıyor**.
Ölçülen gerçek zaman katsayısı **0,35** — yani algı katmanı videonun 3 katı
hızında koşuyor. Bu, birden fazla kamera akışını **tek bir makinede paralel**
işlemeye yetecek bir bant genişliği. Algı katmanı ölçeklenirken ağ, model
servisi veya API kotası devreye girmiyor — darboğaz yalnız CPU/GPU ve bellek.

### (b) Kademeli model yönlendirme — kaynak optimizasyonu

Her karar **yeten en ucuz modele** düşürülür:

| Kademe | Gecikme | Ne yapar |
|---|---|---|
| `router` (8B) | 0,3–1,8 sn | Dikkat mekanizması — "burada bir şey var mı?" |
| `fast` | 0,9–1,3 sn | Sentez, JSON üretimi |
| `main` | 0,8–2,6 sn | Risk değerlendirmesi, aksiyon planı |
| `vlm` (32B) | 7,0–8,7 sn | Video klip yorumlama — sadece tetiklenenler |
| `guard` (4B) | 0,1 sn | İçerik denetimi |

Pencere başına **en fazla bir görü çağrısı** yapılır ve bu çağrı **hareket
enerjisi triyajıyla** nişanlanır (1,9 ms/kare — görü çağrısının %1,3'ü).
10 dakikalık bir videoda 60 pencereden tipik olarak yalnız ~10'u görü
kademesine gider. **Bu, ölçeklemenin temel kolaylaştırıcısı:** model
kapasitesinin %83'ünü bedelsiz geri kazanır.

### (c) Tek yapılandırma noktası — model değiştirme tek satır

Model kimlikleri yalnızca [`gozcu/core/config.py`](../../gozcu/core/config.py)'da
yaşar; `base_url` ortam değişkeniyle yapılandırılabilir. Organizasyonun
EVREN servisi yerine **kendi vLLM dağıtımına** geçiş tek bir `.env`
değişikliğidir. Bu, aşağıdaki yerel dağıtım ve çoklu servis mimarilerinin
temelini oluşturur.

### (d) Durumsuz ajan mimarisi

Her koşu kendi deposuyla (`:memory:` SQLite) izole çalışır — iki koşunun
durumu karışmaz. Ajanlar arası iletişim tipli `Handoff` kayıtlarıyla
gerçekleşir; serbest metin geçmez. Bu tasarım **yatay ölçeklemenin ön
koşulu**: bağımsız koşular birbirini etkilemeden paralel çalışabilir.

---

## 2. Yerel dağıtım — model seçimi ve donanım planlaması

Şartname *"offline ve yerel ortamda çalışmalı, vLLM benzeri yerel model
servisleme kullanılmalı"* diyor. Bugün EVREN'e bağlı olan sistem, aşağıdaki
yapılandırmayla tamamen yerel çalışmaya geçirilebilir.

### Üç katmanlı yerel dağıtım mimarisi

```
┌─────────────────────────────────────────────────────────────────────┐
│  KATMAN 1 — ALGI (zaten yerel)                                      │
│  YOLOE-26s + ByteTrack + sinyal çıkarımı                           │
│  CPU/GPU: Apple M serisi veya NVIDIA RTX 3060+                     │
│  Bellek: ~2 GB (model + çerçeve havuzu)                            │
│  Gerçek zaman katsayısı: 0,35 (3x gerçek zamandan hızlı)           │
└─────────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────────┐
│  KATMAN 2 — METİN MODELLERİ (vLLM ile yerelleştirilir)            │
│                                                                     │
│  Seçenek A (24 GB VRAM — RTX 4090 / A5000):                       │
│   · Qwen3-8B-AWQ (4-bit)     → router + fast + main + guard        │
│   · bge-m3 (gömme)           → embed                               │
│                                                                     │
│  Seçenek B (48+ GB VRAM — 2×RTX 4090 / A100):                     │
│   · Qwen3-30B-A3B-AWQ (MoE) → main (daha yüksek kalite)           │
│   · Qwen3-8B-AWQ             → router + fast + guard               │
│   · bge-m3                   → embed                               │
│                                                                     │
│  Seçenek C (Apple Silicon — M2 Pro/Max/Ultra):                     │
│   · mlx-community/Qwen2.5-VL-3B-Instruct-4bit (zaten config'de)   │
│   · MLX ile yerel çıkarım, vLLM gereksiz                           │
└─────────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────────┐
│  KATMAN 3 — GÖRÜ MODELİ (ayrı GPU veya paylaşımlı)                │
│                                                                     │
│  · Qwen2.5-VL-7B-AWQ (4-bit, 8 GB VRAM)  → düşük donanımlı       │
│  · Qwen3-VL-32B-AWQ (4-bit, 20 GB VRAM)  → yüksek kaliteli       │
│  · Video klipler 10 sn, 4 fps, 480p — yük zaten optimize          │
└─────────────────────────────────────────────────────────────────────┘
```

**Yapılandırma değişikliği — tamamı `.env` dosyasında:**

```bash
GOZCU_GATEWAY_BASE_URL=http://localhost:8000/v1   # yerel vLLM
GOZCU_VLM_BASE_URL=http://localhost:8001/v1       # ayrı VLM servisi
GOZCU_MODEL_MAIN=Qwen3-8B-AWQ
GOZCU_MODEL_VLM=Qwen2.5-VL-7B-AWQ
```

Kod tabanında başka hiçbir şey değişmez — `Gateway` sınıfı OpenAI uyumlu
herhangi bir uç noktayla çalışır.

### Yerel Qdrant (vektör veritabanı)

Epizodik hafıza bugün EVREN'in Qdrant'ına bağlı. Anahtar tanımlı değilse
kod **otomatik olarak süreç içi Qdrant'a düşer** (`memory_backend() → "local"`).
Üretim ortamında tek bir `docker run qdrant/qdrant` ile tamamen yerel bir
vektör veritabanı ayağa kalkar.

---

## 3. Yatay ölçekleme — çok kameralı mimari

### Hedef: 10 eşzamanlı kamera

Mevcut mimari tek video = tek izole koşu varsayımı üzerine kurulu. Bu
bilinçli bir tasarım kararıdır ve çok kameralı bir mimariye genişletilmek
üzere tasarlanmıştır.

### Mikroservis mimarisi

```
                    ┌──────────────────────────────┐
                    │         OPERATÖR              │
                    │     (tarayıcı / mobil)        │
                    └─────────────┬────────────────┘
                                  │ HTTP / SSE
                    ┌─────────────▼────────────────┐
                    │       API GATEWAY             │
                    │    (nginx / traefik)          │
                    │    yük dengeleme + TLS         │
                    └─────┬───────────┬────────────┘
                          │           │
           ┌──────────────▼──┐  ┌─────▼──────────────┐
           │  KONSOL SERVİSİ │  │  KUYRUK SERVİSİ     │
           │  (FastAPI)       │  │  (Redis / RabbitMQ)  │
           │  SSE + diyalog   │  │  kamera başına kanal │
           │  Replika: 2      │  │  adil öncelik        │
           └─────────────────┘  └────────┬────────────┘
                                         │
                ┌────────────────────────┼───────────────────────┐
                │                        │                       │
     ┌──────────▼──────────┐  ┌─────────▼──────────┐  ┌────────▼──────────┐
     │  ALGI İŞÇİSİ #1    │  │  ALGI İŞÇİSİ #2   │  │  ALGI İŞÇİSİ #N  │
     │  YOLOE + ByteTrack  │  │  YOLOE + ByteTrack │  │  YOLOE + ByteTrack│
     │  kamera_id: cam-01  │  │  kamera_id: cam-02 │  │  kamera_id: cam-N │
     │  CPU/GPU: ayrılmış  │  │  CPU/GPU: ayrılmış │  │  CPU/GPU: ayrılmış│
     └──────────┬──────────┘  └─────────┬──────────┘  └────────┬──────────┘
                │                        │                       │
     ┌──────────▼────────────────────────▼───────────────────────▼──────────┐
     │                      KARAR DÖNGÜSÜ HAVUZU                            │
     │   DecisionLoop instance'ları — kamera başına bir döngü               │
     │   paylaşımlı model servisi, kota yöneticisi ile korunan              │
     └──────────────────────────────┬───────────────────────────────────────┘
                                    │
     ┌──────────────────────────────▼───────────────────────────────────────┐
     │                      MODEL SERVİSİ KATMANI                           │
     │   ┌─────────────┐  ┌─────────────┐  ┌──────────────┐                │
     │   │ vLLM — metin │  │ vLLM — VLM  │  │ Qdrant       │                │
     │   │ Replika: 2   │  │ Replika: 1  │  │ (vektör DB)  │                │
     │   │ HPA: CPU %70 │  │ GPU bağımlı │  │ Replika: 1   │                │
     │   └─────────────┘  └─────────────┘  └──────────────┘                │
     └─────────────────────────────────────────────────────────────────────┘
```

### Kubernetes ile Horizontal Pod Autoscaler (HPA)

Algı işçileri ve karar döngüsü bağımsız pod'lar olarak dağıtılır. HPA
kuralları:

| Bileşen | Ölçekleme metriği | Hedef | Min | Maks |
|---|---|---|---|---|
| Algı işçisi | CPU kullanımı | %70 | 1 | 10 |
| Konsol servisi | Eşzamanlı bağlantı | 50 | 2 | 5 |
| Karar döngüsü | Kuyruk derinliği | 3 pencere | 1 | 10 |
| vLLM metin | İstek gecikmesi (p95) | 3 sn | 1 | 4 |
| vLLM VLM | GPU kullanımı | %80 | 1 | 2 |

**Neden çalışır:** algı katmanı 0,35 gerçek zaman katsayısıyla çalışır —
tek bir algı işçisi 3 kamerayı gerçek zamanda besleyebilir. 10 kamera
için **3-4 algı pod'u** yeterlidir. Model servisi katmanında darboğaz
görü kademesidir (7-8 sn/çağrı); ama hareket enerjisi triyajı çağrıların
~%83'ünü eleyerek bu yükü yönetilebilir tutar.

### Kamera başına izolasyon — bugünkü avantaj

Mevcut "koşu ömürlü SQLite" tasarımı aslında bir **ölçekleme avantajı**:
her kamera kendi izole deposuyla çalışır, koşular arası kirlenme riski
sıfır. Çok kameralı geçişte yapılacak değişiklik küçük:

| Bileşen | Bugün | Çok kameralı |
|---|---|---|
| SQLite | `:memory:` (koşu ömürlü) | `cam-{id}.db` (kamera başına kalıcı dosya) |
| Epizodik hafıza | `team37/episodes` koleksiyonu | `team37/episodes` — **değişmez** (nokta kimliği video içeriğinden türetiliyor, çakışma yok) |
| Gateway kotası | Sınırsız tüketim | Kamera başına token bucket + adil paylaşım |

---

## 4. Dikey ölçekleme — ölçülerek seçilen sınırlar

Daha büyük model, daha yüksek çözünürlük ve daha uzun klip seçenekleri
**ölçüldü ve bilinçli olarak reddedildi** — bu bir eksiklik değil, veri
odaklı mühendislik kararıdır.

### Model boyutu — küçük daha doğru

Algı katmanında daha büyük YOLO varyantları test edildi:

| Model | Sayım duyarlılığı (conf=0,05) |
|---|---|
| YOLOE-11n (seçilen) | **%89,7** |
| YOLOE-11s | %79,3 |
| YOLOE-11l | %64,1 |
| YOLOE-11m | %56,6 |

Büyük modelin daha iyi olacağı sezgisi **ölçümle çürütüldü**: küçük model
fabrika kamerası çözünürlüğünde (960×720) daha iyi kalibre. Bu, ölçekleme
açısından bir kazanç — daha düşük hesaplama maliyetiyle daha yüksek doğruluk.

### Çözünürlük — optik sınır ölçüldü

| Çözünürlük | Kişi güveni |
|---|---|
| 640 px (seçilen) | **0,647** |
| 896 px | 0,159 |
| 1280 px | 0,000 |

Kaynak görüntü 960×720; büyütmek gürültüyü esnetip nesneyi modelin kalibre
olduğu ölçek dağılımının dışına itiyor. Düşük çözünürlük = düşük bant
genişliği = daha fazla eşzamanlı akış.

### Video klip süresi — doğruluk ile verim dengesi

10 saniyelik pencere kararı organizasyonun ölçtüğü çözünürlük ölçeği
tablosuna dayanır (15 sn: 0,95 → 180 sn: 0,28). Kısa pencereler yüksek
doğruluk getirir ve **paralel işlemeyi kolaylaştırır** — birden fazla
kameranın pencereleri model servisine bağımsızca gönderilebilir.

---

## 5. Canlı akışa geçiş stratejisi

Mevcut sistemde videonun tamamını bilmeye dayanan üç tasarım kararı var.
Bunlar canlı akışa geçişte değiştirilecek bileşenlerdir — her birinin
çözüm yolu bellidir:

| Mevcut tasarım | Canlı akış çözümü | Karmaşıklık |
|---|---|---|
| Top-K görü bütçesi (videonun tamamı önceden biliniyor) | **Kayan eşik / rezervuar örneklemesi** — son N dakikanın hareket enerjisi ortalamasına göre dinamik eşik | Orta |
| Medyan tabanlı sinyal kalibrasyonu (koşunun tamamı biliniyor) | **Kayan pencere istatistiği** — son N dakikanın medyanı, sürekli güncellenen | Düşük |
| Emsal alaka eşikleri (mevcut arşiv kapsamına kalibre) | **Periyodik yeniden kalibrasyon** — arşiv büyüdükçe eşikler otomatik güncellenir | Düşük |

### RTSP/canlı kamera entegrasyonu

```
  RTSP kamera ──► GStreamer / ffmpeg ──► kare tamponu (ring buffer)
                                              │
                   mevcut algı katmanı ◄──────┘
                   (değişiklik YOK)
```

Algı katmanı (`extract_frames`) bugün bir dosya yolu alıyor. Canlı kaynak
için **tek bir soyutlama katmanı** gerekir: RTSP akışını ring buffer'a alan
bir adaptör. Algı katmanının kendisi (`detect.py`, `track.py`, `signals.py`)
**hiç değişmez** — zaten kare bazlı çalışıyor.

---

## 6. Kaynak hesaplama — 10 kamera senaryosu

### Donanım gereksinimi

| Bileşen | 1 kamera | 10 kamera | Not |
|---|---|---|---|
| Algı (CPU/GPU) | 0,35 RTF | 3,5 RTF toplam | 4 algı işçisi (her biri ~3 kamerayı karşılar) |
| Metin modeli (GPU VRAM) | 8 GB | 8 GB (paylaşımlı) | vLLM batched inference — yük doğrusal artmaz |
| VLM (GPU VRAM) | 20 GB | 20 GB (paylaşımlı) | Triyaj sayesinde çağrıların ~%83'ü eleniyor |
| Qdrant | 256 MB | 256 MB | Epizot sayısı "birkaç yüz" ölçeğinde |
| SQLite | ~5 MB/koşu | ~50 MB | Kamera başına izole dosya |

### VLM darboğaz analizi — 10 kamera

- 10 kamera × 6 pencere/dk = 60 pencere/dk
- Triyajla eleme: %83 → 10 pencere/dk görü çağrısı
- Görü gecikmesi: ~8 sn/çağrı
- Tek VLM replika kapasitesi: 60/8 = 7,5 çağrı/dk
- **10 kamera için 2 VLM replikası yeterli**

### Kota yönetimi (EVREN gateway'i için)

EVREN'in paylaşımlı video yolu dakikada ~6,4 tam uzunlukta video isteği
kapasitesinde. Bu, bütün takımlar arasında paylaşımlı ve takımın kontrol
edemeyeceği bir tavan. Yerel dağıtımda bu sınır ortadan kalkar.

---

## 7. Konteynerizasyon ve dağıtım

### Docker Compose — geliştirme ve demo

```yaml
# docker-compose.yml (kavramsal)
services:
  gozcu-api:          # FastAPI konsolu
    build: .
    ports: ["8080:8080"]
    depends_on: [vllm-text, vllm-vlm, qdrant]

  gozcu-worker:       # Algı + karar döngüsü
    build: .
    command: worker
    deploy:
      replicas: 3     # 10 kamera için 3-4 işçi

  vllm-text:          # Metin modelleri (router, fast, main, guard)
    image: vllm/vllm-openai
    deploy:
      resources:
        reservations:
          devices: [{capabilities: [gpu]}]

  vllm-vlm:           # Görü modeli (ayrı GPU)
    image: vllm/vllm-openai
    deploy:
      resources:
        reservations:
          devices: [{capabilities: [gpu]}]

  qdrant:             # Vektör veritabanı
    image: qdrant/qdrant
    volumes: ["qdrant_data:/qdrant/storage"]
```

### Kubernetes — üretim

Helm chart ile dağıtım; HPA kuralları §3'teki tabloda. Algı işçileri
**Deployment**, karar döngüsü **StatefulSet** (kamera başına kalıcı depo),
model servisleri **GPU-affinity** ile planlanır.

---

## 8. Gözlemlenebilirlik — ölçeklenen sistemi izlemek

Mevcut `gozcu/output/trace.py` konsola özel iz kaydı sunuyor. Üretim
ortamında bunu genişletecek katmanlar:

| Katman | Araç | Ne izler |
|---|---|---|
| Metrikler | Prometheus + Grafana | Pencere/sn, model gecikmesi (p50/p95/p99), kuyruk derinliği, triyaj eleme oranı |
| Loglar | Fluentd → Elasticsearch | Yapılandırılmış JSON log (her `Handoff` kaydı) |
| İzleme | OpenTelemetry | Uçtan uca istek izi — algıdan teslime |
| Alarmlar | Alertmanager | `is_degraded` oranı > %20, kuyruk taşması, model zaman aşımı |

Mevcut iz kaydı (`trace.py`) zaten her ajan devri, her araç çağrısı ve her
model isteği için yapılandırılmış kayıt üretiyor — OpenTelemetry span'larına
çevirmek bir sarmalayıcı yazma işidir.

---

## 9. Özet — ölçekleme yol haritası

| Aşama | Değişiklik | Kolaylaştıran mevcut tasarım |
|---|---|---|
| **Aşama 1 — Yerel dağıtım** | `.env` ile vLLM'e bağlanma, Docker Compose ile ayağa kaldırma | Model kimlikleri tek dosyada, `base_url` yapılandırılabilir |
| **Aşama 2 — Çok kameralı** | Kuyruk servisi + algı işçileri + kamera başına kalıcı SQLite | Koşular zaten izole, epizodik hafıza çakışma riski yok |
| **Aşama 3 — Canlı akış** | RTSP adaptörü + kayan eşik + kayan pencere istatistiği | Algı katmanı kare bazlı, model servisi klipler üzerinden |
| **Aşama 4 — Kubernetes + HPA** | Helm chart, HPA kuralları, GPU pod planlaması | Katmanlı ayrışma (algı / model / depo) doğal pod sınırları |
| **Aşama 5 — Gözlemlenebilirlik** | Prometheus, OpenTelemetry, Alertmanager | `trace.py` zaten yapılandırılmış iz kaydı üretiyor |

**Mimarinin temel güvencesi:** algı katmanı 3× gerçek zamandan hızlı,
kademeli model yönlendirme çağrıların %83'ünü eliyor, koşular arası
izolasyon sağlam. Bu üç özellik, yukarıdaki beş aşamanın her birinde
yeniden yazma yerine **yapılandırma ve katman ekleme** ile ilerlemeyi
mümkün kılıyor.
