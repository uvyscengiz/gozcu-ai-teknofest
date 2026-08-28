
# ⑦ Ölçümleme sonuçları

**Gözcü** · Takım **FERASET** (`team37`) · Muğla Sıtkı Koçman Üniversitesi

Bu bölüm şartname §6'nın *"ölçümleme sonuçları"* kalemidir.

**Kural, ve neden burada tekrarlanıyor:** ölçülmemiş hiçbir şey ölçülmüş
gibi yazılmaz. Şartname §16 veri sahteciliğini ve sonuç manipülasyonunu
diskalifiye sebebi sayıyor. Aşağıdaki her sayının kaynağı
[`benchmark/`](../../benchmark/) altındaki bir dosya ya da bir kod
yorumudur ve link veriliyor; kaynağı olmayan yerde **"ölçülmedi"** yazıyor.

---

## 1. Ölçüm mimarisi — iki ayrı katman, iki ayrı olgunluk

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
│  girdi: 5 klip, ground_truth.csv (olay penceresi ETİKETSİZ)     │
│  çıktı: benchmark/results/kpi.json                              │
│  durum: DEĞERLENDİRME KOŞUSU YARIM — sayılar aşağıda,           │
│         ne olduğu ve neden dürüstçe işaretli                    │
└─────────────────────────────────────────────────────────────────┘
```

İki katman bilerek ayrı: algı katmanı donuk ve model çağırmıyor (bkz.
CLAUDE.md), o yüzden tek başına, tekrar üretilebilir şekilde ölçülebiliyor.
Ajan katmanı canlı bir gateway'e bağımlı; ölçüm sonucu o günkü gateway
durumunu da taşıyor.

---

## 2. Katman 1 — Algı ölçümü (tamamlandı)

Kaynak: [`benchmark/results/perception.md`](../../benchmark/results/perception.md),
[`perception.json`](../../benchmark/results/perception.json). Video: tekstil
fabrikası kazası klibi, 347 kare, 3 fps, 640 px genişlik, `yoloe-26s-seg.pt`,
sınıflar `person,forklift,truck,vehicle`, eşik `0.03`. Üretim damgası:
`2026-08-25T18:12:55+00:00`.

| Ölçüm | Değer | Ne anlama geliyor |
|---|---|---|
| Varlık duyarlılığı (`presence_recall`) | **%99,1** | Gerçekte insan olan karelerin ne kadarında en az bir tespit var |
| Sayım duyarlılığı (`count_recall`) | **%93,1** | Etiketli 15 örnek karede sayının ne kadar doğru |
| Sayım hatası (MAE) | **2,33 kişi/kare** | Ortalama mutlak sapma (en kötü fark: 7) |
| Sıfır tespit oranı | **%1,7** (rapor metninde "%2") | Bir insan varken hiç tespit üretilmeyen kare oranı |
| İz kimliği oranı (`track_id_rate`) | **%100** | Her tespitin bir izleme kimliği aldığı oran |
| Benzersiz iz sayısı | **510** | 347 karede toplam 3.259 kutu |
| Zirve kişi sayısı | rapor edilen **30** / gerçek **22** | Kalabalık sahnede aşırı sayım eğilimi |
| Gerçek zaman katsayısı | **0,35** | 1,0 altı = canlı akışa yetişebilir (algı + izleme + hareket enerjisi toplamı) |
| Triyaj (kare farkı enerjisi) maliyeti | **1,9 ms/kare** | 23 karelik bir klipte 44 ms — tek bir görü çağrısının (3.493 ms) **%1,3'ü** |

**Bu ölçümün sınırı dürüstçe:** tek video, 15 saniyelik örnek noktasıyla
karşılaştırma. Çok-klipli, istatistiksel bir algı değerlendirmesi değil —
`gozcu/core/config.py`'deki eşik/çözünürlük/kare-hızı seçimlerinin **her
biri** ayrıca, aynı klip üzerinde ölçülerek yapıldı (bkz.
[05-zorluklar-ve-cozumler.md](05-zorluklar-ve-cozumler.md)).

---

## 3. Katman 2 — Ajan/KPI ölçümü (yarım, dürüstçe işaretli)

Kaynak: [`benchmark/results/kpi.json`](../../benchmark/results/kpi.json),
üretim damgası `2026-08-25T09:38:25+00:00`.

```
aggregate.status = "degraded"
clips: {total: 5, measured: 0, degraded: 1, unmeasured: 4, error: 0}
ground_truth: {clips: 5, labelled: 0, unlabelled: 4, no_incident: 1}
```

> ⚠️ **Beş klipten hiçbiri `measured` durumuna ulaşmadı.** Dördü
> `unmeasured` (koşu sırasında yönlendiricinin görebildiği bir karar hiç
> oluşmadı), biri (`forklift-compilation--N9bG-sOU6LE-k05.mp4`) `degraded`
> — devirlerin **%20'sinden fazlası** kesinti kaynaklı. Sonuç: **agregat
> KPI'ların tamamı `null`.** `benchmark/kpi.py::aggregate()` yalnız
> `measured` klipleri ortalıyor; sıfır klip o eşiği geçtiği için ortalanacak
> hiçbir sayı yok.

`k05` klibinin tek başına, `degraded` etiketli kısmi kaydı (bir sonuç
değil, bir kesintinin fotoğrafı):

| Alan | Değer |
|---|---|
| `decision_distribution` | `closed_at_router: 0.50 · escalated: 0.17 · degraded: 0.33` |
| `vlm_trigger_rate` | `0.013` |
| `vision_tokens` | `{"vlm": 7407}` |
| `turkish_output_rate` | `1.0` |
| `correction_propagation` | ölçülmedi (`null`) |
| `timestamp_drift_s` | ölçülmedi (`null`) |

**`timestamp_drift_s` bugün hiçbir klip için ölçülemez** —
[`benchmark/ground_truth.csv`](../../benchmark/ground_truth.csv)'nin beş
satırının hiçbirinde `start_s`/`end_s` (olayın etiketli zaman penceresi)
doldurulmamış; dördü olaylı-ama-etiketsiz, biri olaysız (negatif örnek).
Bu bir kod eksikliği değil, henüz yapılmamış bir etiketleme işi.

**Neden yarım — üç somut ön koşul.** `benchmark/run.py::preflight()`
koşuyu şu üçü sağlanmadan reddediyor: (1) `data/` altında bütün klip
dosyaları mevcut, (2) `run_pipeline`'ın güncel imzası (`store=` parametreli)
kullanılıyor, (3) canlı bir gateway probe'u başarılı. Üçü de sağlansa bile
sonucun "eksik" olmasının sebebi harness'in bozuk olması değil — etiketli
bir ground-truth setine karşı canlı bir gateway ile tam koşu 25 Ağustos'tan
beri tekrarlanmadı.

---

## 4. Ölçülen ama ayrı bir dosyaya düşmeyen sayılar — model gecikmeleri

Kaynak: `gozcu/core/config.py`'nin yorum satırları, 26 Ağustos canlı koşu.
Bu sayılar bir `benchmark/results/*.json` dosyasında değil, kodun
kendisinde — çünkü zaman aşımı sabitlerinin gerekçesi:

| Kademe | Ölçülen gecikme aralığı |
|---|---|
| `router` | 0,3–1,8 sn |
| `fast` | 0,9–1,3 sn |
| `main` | 0,8–2,6 sn |
| `guard` | 0,1 sn |
| `vlm` | 7,0–8,7 sn |

Aynı koşuda bir aykırı değer de ölçüldü ve zaman aşımı tasarımını
belirledi: `fast.ask` bir seferinde **1106 saniye** asılı kaldı — bu yüzden
metin kademeleri için ayrı, 90 saniyelik bir zaman aşımı var (ayrıntı:
[05-zorluklar-ve-cozumler.md](05-zorluklar-ve-cozumler.md)).

---

## 5. Şartnamenin istediği KPI'lar — mevcut durum

| Şartname örneği | Karşılığı bu kod tabanında | Durum |
|---|---|---|
| Olay tespit doğruluğu | `presence_recall` / `count_recall` (algı katmanı) | **Ölçüldü** — §2 |
| Özet kalitesi | Otomatik metrik yok; insan değerlendirmesi yapılmadı | **Ölçülmedi** |
| Aksiyon önerisi doğruluğu | Ölçülmedi | **Ölçülmedi** |
| Kritik olay yakalama oranı | `decision_distribution.escalated` (yalnız 1 klip, kısmi) | **Kısmi** — §3 |
| İşlem süresi / video süresi | `real_time_factor` (yalnız algı katmanı) | **Kısmi** — algı için ölçüldü (0,35), uçtan uca (gateway dahil) ölçülmedi |
| Model inference süresi | Kademe gecikmeleri | **Ölçüldü** — §4 |
| Bellek ve donanım kullanımı | Ölçülmedi | **Ölçülmedi** |
| Türkçe çıktı oranı | `turkish_output_rate` | **Kısmi** — yalnız `k05` için (1,0) |
| Zaman damgası sapması | `timestamp_drift_s` | **Ölçülemedi** — etiketli veri yok, §3 |

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

---

## 7. Sunuma taşınacak tek dürüst cümle

> Algı katmanı tek bir video üzerinde titizlikle ölçüldü (%99 varlık, %93
> sayım duyarlılığı). Ajan katmanının uçtan uca KPI koşusu **yarım**: beş
> klipten hiçbiri `measured` eşiğine ulaşmadı, çünkü ground-truth etiketleme
> ve son canlı-gateway koşusu 25 Ağustos'tan beri tamamlanmadı. Bu belgede
> o eksik sayılar tahmin edilerek doldurulmadı.
