# Donanım

**Yerel GPU planı iptal edildi.** Organizasyon bütün modelleri kendi
sunucularında vLLM ile ayağa kaldırıp OpenAI uyumlu bir gateway üzerinden
veriyor. RTX 3090/4090 gereksinimleri, VRAM hesapları ve bulut GPU bütçesi
tartışması artık geçersiz.

## Ne nerede çalışıyor

| Katman | Nerede | Neden |
|---|---|---|
| Algı — YOLOE, ByteTrack, sinyaller | **Yerel** (ekibin makinesi, CPU yeter) | Yüksek hacim, gecikmeye duyarlı, gateway'e bağımlı olmamalı |
| Yorumlama — görsel model | Gateway | Sadece tetiklendiğinde çağrılıyor |
| Ajan muhakemesi — yönlendirici, sentez, risk, diyalog, rapor | Gateway | Düşük hacim, kaliteye duyarlı |
| Gömme ve sıralama | Gateway | Sorgu başına |

Bu sınır kasıtlı: gateway düşerse algı katmanı yerelde çalışmaya devam ediyor ve
sistem bozulmuş modda uyarı vermeyi sürdürüyor. Şartname *hata işleme* ve
*beklenmedik durumlara tepki* kalemlerini ayrı ayrı puanlıyor.

## Model kademeleri

Her karar, yetecek en ucuz modele düşüyor.

| Kademe | Model | Kullanım |
|---|---|---|
| `router` | Qwen3-8B | Yönlendirme kararları — en yüksek hacim |
| `hizli` | Qwen3.6-35B-A3B | Epizot sentezi |
| `ana` | Qwen3.5-122B-A10B | Operatör diyalogu, risk, kök neden raporu |
| `vlm` | Qwen3-VL-30B-A3B | Tetiklenen karenin yorumu |
| `guard` | Qwen3Guard-Gen-4B | Operatöre giden metnin denetimi |
| `embed` | Qwen3-Embedding-4B | Epizot gömme |
| `rerank` | Qwen3-Reranker-4B | Arama sonucu sıralama |

Model kimlikleri **sadece `gozcu/config.py`'da.** Organizasyon farklı adlar
deploy ederse tek düzenlenecek yer orası.

## Geliştirme makinesi

Herhangi bir dizüstü yeter. `uv sync --extra dev` + gateway adresi:

```bash
export GOZCU_GATEWAY_BASE_URL="http://<adres>:4000/v1"
export GOZCU_GATEWAY_API_KEY="<anahtar>"
```

Gateway erişimi olmadan da görev 09, 10, 12, 13 ve 15 tamamen çalışır —
hiçbiri gerçek model çağırmıyor.
