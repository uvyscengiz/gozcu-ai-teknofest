# Bölüm 7 — Ölçümleme sonuçları

**Gözcü** · Takım **FERASET** (`team37`) · Muğla Sıtkı Koçman Üniversitesi

Bu bölüm şartname §6'nın *"ölçümleme sonuçları"* kalemidir. Aşağıdaki
her sayının kaynağı [`benchmark/`](../../benchmark/) altındaki bir dosya
ya da bir kod yorumudur.

---

## 1. Ölçüm mimarisi — iki ayrı katman

```
┌─────────────────────────────────────────────────────────────────┐
│  KATMAN 1 — ALGI (model yok, gateway yok)                       │
│  benchmark/perception.py                                        │
│  girdi: elle etiketlenmiş TEK video (347 kare)                  │
│  çıktı: benchmark/results/perception.json + perception.md       │
│  durum: TAMAMLANDI, sayılar aşağıda                              │
└─────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────┐
│  KATMAN 2 — AJAN (gerçek gateway, uçtan uca koşu)                │
│  benchmark/run.py → benchmark/kpi.py → benchmark/report.py      │
│  girdi: gerçek klipler, ground_truth.csv                        │
│  çıktı: benchmark/results/kpi.json                              │
└─────────────────────────────────────────────────────────────────┘
```

İki katman bilerek ayrı: algı katmanı donuk ve model çağırmıyor (bkz.
CLAUDE.md), o yüzden tek başına, tekrar üretilebilir şekilde ölçülebiliyor.
Ajan katmanı canlı bir gateway'e bağımlı ve uçtan uca ajan davranışını
ölçüyor.

---

## 2. Katman 1 — Algı ölçümü

Kaynak: [`benchmark/results/perception.md`](../../benchmark/results/perception.md),
[`perception.json`](../../benchmark/results/perception.json). Video: tekstil
fabrikası kazası klibi, 347 kare, 3 fps, 640 px genişlik, `yoloe-26s-seg.pt`,
sınıflar `person,forklift,truck,vehicle`, eşik `0.03`. Üretim damgası:
`2026-08-25T18:12:55+00:00`.

| Ölçüm                                  | Değer                               | Ne anlama geliyor                                                             |
| -------------------------------------- | ----------------------------------- | ----------------------------------------------------------------------------- |
| Varlık duyarlılığı (`presence_recall`) | **%99,1**                           | Gerçekte insan olan karelerin ne kadarında en az bir tespit var               |
| Sayım duyarlılığı (`count_recall`)     | **%93,1**                           | Etiketli 15 örnek karede sayının ne kadar doğru                               |
| Sayım hatası (MAE)                     | **2,33 kişi/kare**                  | Ortalama mutlak sapma (en kötü fark: 7)                                       |
| Sıfır tespit oranı                     | **%1,7** (rapor metninde "%2")      | Bir insan varken hiç tespit üretilmeyen kare oranı                            |
| İz kimliği oranı (`track_id_rate`)     | **%100**                            | Her tespitin bir izleme kimliği aldığı oran                                   |
| Benzersiz iz sayısı                    | **510**                             | 347 karede toplam 3.259 kutu                                                  |
| Zirve kişi sayısı                      | rapor edilen **30** / gerçek **22** | Kalabalık sahnede aşırı sayım eğilimi                                         |
| Gerçek zaman katsayısı                 | **0,35**                            | 1,0 altı = canlı akışa yetişebilir (algı + izleme + hareket enerjisi toplamı) |
| Triyaj (kare farkı enerjisi) maliyeti  | **1,9 ms/kare**                     | 23 karelik bir klipte 44 ms — tek bir görü çağrısının (3.493 ms) **%1,3'ü**   |

---

## 3. Katman 2 — Ajan/KPI ölçümü

Kaynak: [`benchmark/results/kpi.json`](../../benchmark/results/kpi.json). Gerçek
bir klip üzerinde, canlı gateway'e karşı koşulan uçtan uca ajan koşusundan
alınan ölçümler:

| Alan                    | Değer                                                       |
| ----------------------- | ----------------------------------------------------------- |
| `decision_distribution` | `closed_at_router: 0.50 · escalated: 0.17 · degraded: 0.33` |
| `vlm_trigger_rate`      | `0.013`                                                     |
| `vision_tokens`         | `{"vlm": 7407}`                                             |
| `turkish_output_rate`   | `1.0`                                                       |

`decision_distribution`, yönlendiricinin pencerelerin yarısını yerelde
kapattığını, geri kalanının Yorumlayıcı'ya (görü) veya değerlendirmeye
taşındığını gösteriyor — mimarinin hedeflediği kademeli filtreleme canlı
koşuda da çalışıyor. `vlm_trigger_rate` (%1,3) görü çağrısının ne kadar
seçici tetiklendiğini, `turkish_output_rate` (1.0) operatöre giden bütün
metnin Türkçe üretildiğini doğruluyor.

---

## 4. Ölçülen ama ayrı bir dosyaya düşmeyen sayılar — model gecikmeleri

Kaynak: `gozcu/core/config.py`'nin yorum satırları, 26 Ağustos canlı koşu.
Bu sayılar bir `benchmark/results/*.json` dosyasında değil, kodun
kendisinde — çünkü zaman aşımı sabitlerinin gerekçesi:

| Kademe   | Ölçülen gecikme aralığı |
| -------- | ----------------------- |
| `router` | 0,3–1,8 sn              |
| `fast`   | 0,9–1,3 sn              |
| `main`   | 0,8–2,6 sn              |
| `guard`  | 0,1 sn                  |
| `vlm`    | 7,0–8,7 sn              |

Aynı koşuda bir aykırı değer de ölçüldü ve zaman aşımı tasarımını
belirledi: `fast.ask` bir seferinde **1106 saniye** asılı kaldı — bu yüzden
metin kademeleri için ayrı, 90 saniyelik bir zaman aşımı var (ayrıntı:
[05-zorluklar-ve-cozumler.md](05-zorluklar-ve-cozumler.md)).

---

## 5. Şartnamenin istediği KPI'lar — karşılığı

| Şartname örneği             | Karşılığı bu kod tabanında                                                  |
| --------------------------- | --------------------------------------------------------------------------- |
| Olay tespit doğruluğu       | `presence_recall` / `count_recall` (algı katmanı) — §2                      |
| Kritik olay yakalama oranı  | `decision_distribution.escalated` — §3                                      |
| İşlem süresi / video süresi | `real_time_factor` — algı katmanı için 0,35 (3× gerçek zamandan hızlı) — §2 |
| Model inference süresi      | Kademe gecikmeleri (`router`/`fast`/`main`/`guard`/`vlm`) — §4              |
| Türkçe çıktı oranı          | `turkish_output_rate` — §3                                                  |

---

## 6. Ölçüm harness'inin kendisi — test kapsamı

Ölçüm kodunun doğruluğu ayrıca test ediliyor (rakamların kendisinden
bağımsız bir güvence): [`tests/test_benchmark.py`](../../tests/test_benchmark.py),
[`tests/test_kpi.py`](../../tests/test_kpi.py),
[`tests/test_perception_bench.py`](../../tests/test_perception_bench.py).
Kilitlenen kurallardan örnekler:

- Ölçülemeyen bir değer her zaman `None`, **asla `0.0`** — sıfır ile
  "ölçülmedi" karıştırılırsa bir kesinti mükemmel bir sonuç gibi görünür.
- `aggregate()` yalnız `measured` klipleri ortalıyor; `degraded`/`unmeasured`
  klipler ortalamaya sessizce karışmıyor.
- Türkçe tespiti kelime sınırlı (regex), alt dize değil — `"risk"`, `"at"`,
  `"on"` gibi İngilizce/Türkçe ortak dizeler yanlış pozitif üretmiyor.
- `kpi.schema.json` kodun ürettiği anahtarlarla **birebir** eşleşiyor
  (`test_the_schema_names_exactly_the_kpis_the_code_produces`).
