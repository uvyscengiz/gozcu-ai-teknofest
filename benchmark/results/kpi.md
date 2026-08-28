# Gözcü — ölçüm sonuçları

**Durum: ÖLÇÜLDÜ.** Kararların büyük çoğunluğu gerçek model kararı; aşağıdaki sayılar okunabilir.

Üretim: 2026-08-28T08:22:29+00:00 · şema sürümü 1

Klipler: 5 toplam · 5 ölçüldü · 0 bozuk · 0 ölçülemedi · 0 hata

Etiketler: 4 işaretli pencere · 0 olaylı ama etiketsiz · 1 negatif örnek. Etiketsiz klipler zaman sapmasına girmez.

## Karar dağılımı

Ortalamaya yalnız `measured` klipler girer; bozulmuş klip manşet sayıyı sulandırır.

| Kova | Pay |
| --- | --- |
| Yönlendiricide kapandı | 0.255 |
| Yorumlayıcıya | 0.338 |
| Sentezleyiciye | 0.408 |
| Yükseltildi | 0.000 |
| Kesinti (ölçüm dışı) | 0.000 |

## KPI özeti

| KPI | Değer | Hedef |
| --- | --- | --- |
| Görü tetikleme oranı | 0.026 | %5'in altı |
| Zaman sapması (medyan, sn) | 5.000 | düşük |
| Türkçe kalma oranı | 1.000 | 1.0 |
| Düzeltme yayılımı | ölçülemedi | 1.0 |
| Proaktivite oranı | ölçülemedi | yüksek |
| Görü kademesi token'ları | vlm: 327093 | — |

> Token muhasebesi **yalnız görü kademesini** kapsıyor: `tokens` sistemde bir tek `Interpretation` kaydında kalıcı hâle geliyor. Koşu geneli bir maliyet tablosu bu veriden üretilemez.

## Gecikme ve kaynak kullanımı

| Ölçüm | Değer |
| --- | --- |
| Toplam boru hattı süresi | 1456.1 sn |
| Ortalama boru hattı süresi | 291.2 sn |
| Zirve bellek kullanımı | ölçülemedi |
| Görü çağrısı gecikmesi (toplam) | 466831 ms |
| Görü çağrısı gecikmesi (ortalama) | 5822.5 ms |
| Görü çağrısı gecikmesi (p50) | 5683 ms |
| Görü çağrısı gecikmesi (p95) | 6668 ms |

## Özet kalitesi (LLM-as-judge)

| Boyut | Ortalama (1–5) |
| --- | --- |
| **Genel ortalama** | 5.000 |
| Klip sayısı | 3 |

## Pencere dağılımı

| Sonuç | Pay |
| --- | --- |
| Yönlendirici gördü | 1.000 |
| Periyodik örneklem | 0.000 |
| Atlandı | 0.000 |
| Telafi kuyruğu | 0.000 |

## Klip başına

| Klip | Durum | En ucuz kademe | Görü tetikleme | Sapma (sn) | Türkçe | Süre (sn) | Risk | Hata |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| video2.mp4 | measured | 0.333 | 0.024 | 0.00 | 1.000 | 154.9 | ✓ | — |
| video10.mp4 | measured | 0.500 | 0.019 | ölçülemedi | ölçülemedi | 401.0 | — | — |
| video1.mp4 | measured | 0.417 | 0.020 | ölçülemedi | ölçülemedi | 106.2 | — | — |
| vbideo11.mp4 | measured | 0.024 | 0.033 | 10.00 | 1.000 | 532.6 | ✓ | — |
| f13efb67-fd11-47a0-bd08-fbc66383c109.mp4 | measured | 0.000 | 0.033 | ölçülemedi | 1.000 | 261.4 | — | — |
