# Gözcü 0. Faz (algı) taban ölçümü

*Üretildi: 2026-08-25T16:38:06+00:00 · `benchmark/perception.py` · şema v1*

**Video:** `WhatsApp Video 2026-08-25 at 15.35.33.mp4` — 116 kare, 1 fps, 896 px genişlik.
**Model:** `yoloe-26s-seg.pt`, sınıflar `person,forklift,truck,vehicle`, eşik 0.2.

Bu tablo **algı katmanını tek başına** ölçer: gateway çağrısı yok, ajan katmanı yok. Uçtan uca KPI'lar için `bench/kpi.md`.

## Manşet

| Ölçüm | Değer | Ne demek |
| --- | --- | --- |
| Varlık duyarlılığı | **%72** | en az bir kişi görülen kare payı (etikete göre HER karede insan var) |
| Sayım duyarlılığı | **%11** | görülen kişi / gerçekte olan kişi, etiketli karelerde |
| Sıfır tespit oranı | **%28** | hiçbir kutu üretilmeyen kare payı |
| Kimlik atama oranı | %67 | kimlik alan kutu payı (19 ayrı kimlik) |
| Zirve kişi sayısı | 6 | tek karede sayılan en yüksek kişi (gerçek zirve: 22) |
| Gerçek zaman katsayısı | 0.14 | 1,0'ın altı canlı akışa yetişiyor demek |

## Olay anı

Etiketli kaza saniyesi **t=49 s**.

- Algı katmanının o karede saydığı kişi: **0**
- O karenin hareket enerjisindeki sırası: **53. / 116**

## Takip katmanının bedeli

`gozcu.track`'in sözleşmesi *tespit kayıttır, takip yalnız kimlik ekler*. Aşağıdaki `boxes_lost` sıfır değilse sözleşme tutmuyor demektir — kayıp, kimliksiz kutuyu düşüren süzgeçten değil, `model.track()`'in kendi içinden geliyor.

| | Takiple (boru hattı) | Takipsiz | Fark |
| --- | --- | --- | --- |
| Kutu | 159 | 266 | **−107** |
| Varlık duyarlılığı | %72 | %72 | değişmiyor |
| Sayım duyarlılığı | %11 | %22 | **iki katı** |
| Zirve kişi sayısı | 6 | 10 | |

Takip 41 karede kutu **eledi**, 0 karede ekledi.

## Etiketli kareler

Örneklem sistematik: her 8. saniye, seçilmiş değil. `±` sütunu kalabalık karelerde elle sayımın oynadığı payı gösterir.

| t (s) | Gerçek | Algının saydığı | Kaçırılan |
| ---: | ---: | ---: | ---: |
| 0 | 3 | 1 | 2 |
| 8 | 4 | 1 | 3 |
| 16 | 5 | 2 | 3 |
| 24 | 5 | 0 | 5 |
| 32 | 4 | 0 | 4 |
| 40 | 4 | 0 | 4 |
| 48 | 4 | 0 | 4 |
| 56 | 5 ±1 | 0 | 5 |
| 64 | 6 ±1 | 2 | 4 |
| 72 | 10 ±2 | 1 | 9 |
| 80 | 14 ±2 | 1 | 13 |
| 88 | 20 ±3 | 1 | 19 |
| 96 | 20 ±3 | 2 | 18 |
| 104 | 22 ±3 | 2 | 20 |
| 112 | 19 ±3 | 3 | 16 |

Ortalama mutlak sapma **8.6 kişi/kare**; en kötü tek kare **20 kişi**. Ortalama gerçek 9.7, ortalama sayılan 1.1.

## Süre

| Kademe | Saniye |
| --- | ---: |
| frames | 1.51 |
| motion | 0.24 |
| track | 14.63 |

---

Yeniden üretmek için:

```bash
uv run python -m benchmark.perception "WhatsApp Video 2026-08-25 at 15.35.33.mp4"
```
