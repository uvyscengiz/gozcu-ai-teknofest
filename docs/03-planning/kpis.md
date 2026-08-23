# KPI'lar

Şartname katılımcıların kendi metriklerini tanımlamasını istiyor ve **benchmark
kodunu** teslim kalemi sayıyor.

Önceki hedefler (yüzlerce olay için precision/recall) dört günde ulaşılamaz —
ground truth üretmek tek başına günler alır. Ölçülebilir üç aileye indirildi.
Uygulama: [docs/tasks/15-kpi.md](../tasks/15-kpi.md).

## A. Olay yakalama

~5 klip elle etiketleniyor (`benchmark/ground_truth.csv`).

| Metrik | Tanım |
|---|---|
| Kritik olay yakalama oranı | Etiketli olay penceresini kapsayan epizot açıldı mı |
| Zaman damgası sapması | Medyan \|tespit − etiket\|, saniye |
| Yanlış alarm oranı | Olaysız kliplerde açılan epizot |

## B. Ajan davranışı

Ground truth gerektirmiyor — defterlerden hesaplanıyor. **Rakiplerde olmayacak
kısım burası.**

| Metrik | Tanım | Hedef |
|---|---|---|
| Düzeltme yayılımı | Operatör düzeltmesinin epizot özetine yansıma oranı | 1.0 |
| Devir doğruluğu | Beklenen ajan zincirinin gerçekleşme oranı | — |
| Bağlam koruma | Bağlam değişimi sonrası açık olaya dönüş | — |

## C. Verimlilik

Tamamen otomatik — `devir` ve `yorum` tabloları zaten token ve gecikme yazıyor.

| Metrik | Tanım | Hedef |
|---|---|---|
| **Karar dağılımı** | Kararların yüzde kaçı yönlendiricide kapandı / yukarı çıktı | — |
| **VLM tetikleme oranı** | Karelerin yüzde kaçı görsel modele gitti | **<%5** |
| Olay başına token | Model kırılımıyla | — |
| Bozulmuş mod devamlılığı | Gateway kesintisinde uyarı üretmeye devam | — |

**Karar dağılımı sunumun manşet sayısı.** Mimarinin iddiası "her karar yetecek
en ucuz modele düşüyor" ve kanıtı bu tek grafik. 4 dakikalık sunuma giden tek
görsel bu olacak.
