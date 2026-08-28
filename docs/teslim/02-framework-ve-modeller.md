
# Bölüm 2 — Kullanılan agentic framework ve LLM'ler

**Gözcü** · Takım **FERASET** (`team37`) · Muğla Sıtkı Koçman Üniversitesi

Bu bölüm şartname §6'nın *"kullanılan agentic framework ve LLM'ler"*
kalemidir.

---

## 1. Framework: yok — düz Python, bilerek

Gözcü hiçbir agentic framework (LangGraph, CrewAI, AutoGen…) kullanmıyor.
Süpervizörün araç-çağırma döngüsü
([`gozcu/agents/supervisor.py::_turn_loop`](../../gozcu/agents/supervisor.py))
~30 satır düz Python; karar döngüsünün kendisi
([`gozcu/pipeline/loop.py::DecisionLoop`](../../gozcu/pipeline/loop.py)) bir
generator.

Bu bir eksiklik değil, ölçülmüş bir tercih. Takımın orijinal planı
LangGraph'tı; dört günlük yarışma sprintinin başında (22-23 Ağustos) iki
gerekçeyle terk edildi ([decision-log](../decisions/decision-log.md)):

1. **Puanlanan şey framework adı değil.** Şartname §7 *"Teknik İmplementasyon
   ve Mimari"* kalemini *"agentic çözümlerin temel bileşenlerinin (agent,
   tools, memory, prompt engineering) etkin kullanımı"* ve *"dinamik araç
   seçimi, bağlam yönetimi, çok adımlı karar zincirleri, hata işleme"* diye
   tarif ediyor — bunların hiçbiri bir framework'ün adını gerektirmiyor,
   hepsi düz Python'da doğrudan görülebiliyor.
2. **Öğrenme eğrisi riski.** Üç-dört günlük bir sprintte yeni bir framework'ü
   öğrenip hata ayıklamak, doğrudan iş mantığı yazmaktan daha pahalı çıkıyor.
   Okunabilir düz kod, kod kalitesi kaleminde de (aynı §7) daha kolay
   savunuluyor.

Kendi orkestrasyonumuzun somut karşılıkları:

| Framework kavramı | Gözcü'deki karşılığı |
|---|---|
| Agent | Her ajan bir Python fonksiyonu/sınıfı, kendi sistem promptu ve şeması ile — [gozcu/agents/](../../gozcu/agents/) |
| Tool / tool-calling | OpenAI uyumlu `tools=[...]` sözleşmesi, [gozcu/tools/registry.py](../../gozcu/tools/registry.py) tek meşru çağrı kapısı |
| Memory (uzun süreli) | Qdrant — [gozcu/memory/episodic.py](../../gozcu/memory/episodic.py) |
| Memory (kısa süreli) | `RunMemory` — [gozcu/memory/recall.py](../../gozcu/memory/recall.py) |
| Orchestration / handoff | Tipli `Handoff` kaydı, SQLite'a yazılıyor — [gozcu/core/models.py](../../gozcu/core/models.py) |
| Structured output | JSON Schema + `strict_schema()` sertleştirmesi — [gozcu/core/gateway.py](../../gozcu/core/gateway.py) |
| Durum makinesi / graf | `DecisionLoop` generator'ı — [gozcu/pipeline/loop.py](../../gozcu/pipeline/loop.py) |

Hafıza tarafında da aynı karar tekrarlandı: LangMem yerine Qdrant + gömme
+ kosinüs benzerliği (bkz. §3). Bir vardiyanın epizot sayısı birkaç yüzü
geçmiyor; kaba kuvvet arama zaten anlık.

---

## 2. Model servisleme: EVREN gateway, OpenAI uyumlu API

Şartname *"vLLM veya benzeri yerel model servisleme altyapıları tercih
edilmelidir"* diyor. Karşılığı: organizasyon **EVREN** adlı bir servis
işletiyor — 8 × NVIDIA H200 üzerinde **vLLM**, BF16, kuantizasyon yok —
ve modelleri OpenAI uyumlu bir API'nin arkasında sunuyor. Gözcü bu servise
tek bir istemci kütüphanesiyle (`openai` Python paketi) bağlanıyor; seçilme
sebebi OpenAI'a bağımlılık değil, yalnızca protokolü konuşması — `base_url`
yapılandırılabilir ve kod tabanında hiçbir ticari kapalı servis (OpenAI,
Anthropic, Google…) istemcisi yok.

```
gozcu/core/gateway.py::Gateway
        │
        │  openai.OpenAI(base_url=GATEWAY_BASE_URL, api_key=..., timeout=1800)
        ▼
https://evren-llmapi.ssyz.org.tr/v1     (organizasyonun vLLM sunucusu, 8×H200)
```

Model **kimlikleri** kod tabanında hiçbir yerde açık yazmıyor — yalnız
[`gozcu/core/config.py::MODELS`](../../gozcu/core/config.py) içinde,
organizasyonun verdiği takma adlar (`router`, `llm-fast`, `llm-large`,
`vlm`, `guard`, `bge-m3-embed`, `rerank`) üzerinden, `GOZCU_MODEL_*` ortam
değişkenleriyle ezilebilir hâlde. CLAUDE.md'nin *"model kimlikleri yalnızca
`gozcu/core/config.py`'da yaşar"* kuralı burada: organizasyon roster'ı
değişirse değişen tek dosya budur, ve **yanlış bir takma ad 404 vermiyor** —
gateway isteği sessizce `llm-fast`'e yönlendiriyor, yani bir görü çağrısı
bir metin modeline gidip çıktı sessizce çöp olabiliyor. Bu risk 24
Ağustos'ta gerçekten yaşandı (takma adlar önce tahmindi, hepsi yanlıştı) ve
adlar organizasyonun resmî belgesinden alınarak kapatıldı.

---

## 3. Kademeli model seçimi — her karar yeten en ucuz modele düşer

Yedi kademe var, her biri farklı bir işi görüyor. Doğrudan model adı
vermek yerine (CLAUDE.md kuralı) *rolü* tarif ediyoruz — gerçek isimler
`GOZCU_MODEL_*` ile takım tarafına özel:

| Kademe | İşi | Kim çağırıyor | Sıklık |
|---|---|---|---|
| `router` | "Bu pencere dikkat gerektiriyor mu, kime gitmeli" — **görüntü görmez**, yalnız sinyal özeti okur | `agents/orchestrator.py` | Pencere başına ≤1 |
| `vlm` | 10 sn'lik klibi okur, ciddiyet biçer (rutin/dikkat/olay), anları (beats) çıkarır | `agents/interpreter.py` | Yalnız tetikte (görü bütçesi dahilinde) |
| `fast` | Gözlem + yorum → Epizot (faz, Türkçe özet, ön risk) | `agents/anomaly_analyst.py` | Epizot başına |
| `main` | Diyalog (Nöbetçi), derin risk analizi (araç turlu), aksiyon planlama, kök neden raporu | `agents/supervisor.py`, `risk.py`, `action_planner.py`, `reporter.py` | Düşük sıklık, yüksek çıktı bütçesi |
| `guard` | Operatöre/jüriye giden metni güvenlik açısından süzer | `output/guard.py` | Çıktı başına |
| `embed` (`bge-m3-embed`, 1024 boyut) | Epizot/belge arşivinde anlamsal arama | `memory/episodic.py` | Sorgu başına |
| `rerank` | Sunuluyor ama **kullanılmıyor** — bkz. §4 | — | 0 |

Ölçülen gecikmeler (26 Ağustos canlı koşu, `config.py`'deki kayıt):
`router` 0,3–1,8 sn · `fast` 0,9–1,3 sn · `main` 0,8–2,6 sn · `guard` 0,1 sn ·
`vlm` 7,0–8,7 sn. Yalnız görü kademesi pahalı; mimarinin bütün maliyet
tasarrufu o çağrının *nereye harcanacağını* seçmekten geliyor
([01-mimari §4](01-mimari-ozeti-ve-diyagramlar.md#4-pencere-karar-akışı--mimarinin-çekirdeği)).

---

## 4. Yerel geliştirme yolu — VLM ailesi ve alternatif servisleme

EVREN yarışma günü için hazır, ama geliştirme sürecinde takım yerel bir
VLM yolu da doğruladı:

- **Model ailesi:** Qwen2.5-VL (`mlx-community/Qwen2.5-VL-3B-Instruct-4bit`,
  Apple Silicon'da `mlx-vlm` ile). [decision-log](../decisions/decision-log.md)'a
  göre bu seçim güçlü Türkçe desteği, multimodal gömme kapasitesi ve
  vLLM-uyumluluğu gerekçesiyle yapıldı; JEPA/JEPA2 ve SAM2 de değerlendirildi
  ama üretim yoluna girmedi (JEPA saf bir gömme modeli, video anlatımı
  üretmiyor; SAM2 segmentasyon, bizim ihtiyacımız tespit+izleme).
- **Yerel servisleme alternatifi:** `scripts/gen-litellm-config.py`, yedi
  kademeyi tek bir `litellm` proxy'sine (varsayılan arka uç: Ollama,
  `qwen2.5:7b`) yönlendiren bir yapılandırma üretir — EVREN'e erişimsiz bir
  ortamda offline demo/geliştirme için. Üretim yolu değil, `app.py` bugün
  `GOZCU_VLM_BASE_URL`'e bakıyor.

`rerank` kademesi organizasyon tarafından sunuluyor ama **kasıtlı olarak
çağrılmıyor**: organizasyonun kendi ölçümünde ilk-isabet oranını (R@1)
0,95'ten 0,55'e düşürüyor. `Gateway.rerank()` kod tabanında yerinde duruyor
(test edilmiş, zararsız) ama `gozcu/memory/episodic.py::search_timeline`
onu çağırmıyor — Qdrant'ın kendi kosinüs sıralaması nihai sıra.

---

## 5. Prompt mühendisliği — yapılandırılmış çıktı ve Türkçe enum disiplini

Üç mekanizma birlikte çalışıyor:

**(a) Strict JSON Schema.** Her ajan bir Pydantic modeli tanımlar (`extra
= "forbid"`); `Gateway.ask()` şemayı `strict_schema()`'den geçirip
OpenAI'nin *strict* structured-output moduna uygun hâle getirir — her alan
`required` olur, doğrulama anahtarları (`maxLength`, `minimum`,
`pattern`…) telden söker (arka uçlar bunları yaygın olarak reddediyor;
sınır Pydantic modelinde, kesme Python tarafında kalır), dizi alanlarına
`maxItems=8` koyar. Bu sertleştirme tek bir yerde: hiçbir ajan modülünün
"unutması" mümkün değil — bir zamanlar ayrı bir kural olarak üç görev
dosyası tarafından unutulmuştu (bkz. [05-zorluklar-ve-cozumler.md](05-zorluklar-ve-cozumler.md)).

**(b) Enum'lar şemadan türer, elle kopyalanmaz.** CLAUDE.md'nin *"prompt
bir enum sayıyorsa değerleri şemadakiyle birebir aynı olmalı"* kuralı, bu
kod tabanının bir kez sessizce ölmesine yol açan gerçek bir arızanın
karşılığı. Örnekler: `agents/anomaly_analyst.py`'deki `event_class` ve
`zone_id` listeleri `get_args(EventClass)` ve fikstür dosyasından; risk ve
planlayıcı ajanlarındaki araç kataloğu (`_describe_tool`) doğrudan araç
şemalarından; raportördeki alan kataloğu `RootCauseReport.model_json_schema()`'dan
üretiliyor. Elle yazılmış bir kopya ayrışabilir; türetilmiş bir kopya
ayrışamaz.

**(c) Çıktı Türkçe, kod İngilizce.** Bütün sistem promptları, alan
açıklamaları ve örnekler Türkçe; JSON anahtarları ve enum'ların *kod
tarafı* İngilizce, yalnız **risk seviyelerinin değerleri** (`"Düşük" |
"Orta" | "Yüksek" | "Kritik"`) Türkçe kalıyor — CLAUDE.md'nin değişmez
kuralı.

**(d) Kaçak tekrar koruması.** Şemalı isteklerde üst sınır yoksa strict-JSON
kod çözümü kaçak tekrara girip `max_tokens` tükenene kadar yineliyor, JSON
hiç kapanmıyor. `SCHEMA_MAX_TOKENS = 8192` her şemalı çağrıya varsayılan
bir tavan koyuyor (görü/risk/rapor gibi büyük çıktılar kendi tavanlarını
taşıyor: `RISK_MAX_TOKENS = 16384`, `REPORT_MAX_TOKENS = 16384`). Qwen3
ailesi modeller varsayılanda "düşünme" (`<think>`) modunu açık tutuyor —
`fast`/`router`/`guard`/`main` kademeleri için bu gereksiz gecikme
üretiyordu; `THINKING_DISABLED_TIERS` bu dört kademede `enable_thinking:
false` gönderiyor.

---

## 6. Bozulma sözleşmesi — modele değil, mimariye ait bir tasarım kararı

Hiçbir kademe kesintisi bir koşuyu düşürmüyor: `Gateway.ask()` kesintide
istisna atmak yerine boş içerikli, `degraded=True` bir yanıt döndürüyor
(ayrıntı: [01-mimari §10](01-mimari-ozeti-ve-diyagramlar.md#10-hata-ve-kesinti-mimarisi)).
Bu, "framework ve model" seçiminin doğrudan bir sonucu: paylaşımlı, uzak
bir gateway'e bağımlı bir sistemde kesinti *normal* bir durum sayılmak
zorunda, istisnai değil — CLAUDE.md'nin çıktı sözleşmesi kuralı (dört
anahtar her koşuda üretilir) da bunu gerektiriyor.
