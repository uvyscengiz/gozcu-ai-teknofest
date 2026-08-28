# Gözcü 0. Faz (algı) taban ölçümü

*Üretildi: 2026-08-25T18:12:55+00:00 · `benchmark/perception.py` · şema v1*

**Video:** `WhatsApp Video 2026-08-25 at 15.35.33.mp4` — 347 kare, 3 fps, 896 px genişlik.
**Model:** `yoloe-26s-seg.pt`, sınıflar `person,forklift,truck,vehicle`, eşik 0.03.

Bu tablo **algı katmanını tek başına** ölçer: gateway çağrısı yok, ajan katmanı yok. Uçtan uca KPI'lar için `benchmark/results/kpi.md`.

## Manşet

| Ölçüm | Değer | Ne demek |
| --- | --- | --- |
| Varlık duyarlılığı | **%99** | en az bir kişi görülen kare payı (etikete göre HER karede insan var) |
| Sayım duyarlılığı | **%93** | görülen kişi / gerçekte olan kişi, etiketli karelerde |
| Sıfır tespit oranı | **%2** | hiçbir kutu üretilmeyen kare payı |
| Kimlik atama oranı | %100 | kimlik alan kutu payı (510 ayrı kimlik) |
| Zirve kişi sayısı | 30 | tek karede sayılan en yüksek kişi (gerçek zirve: 22) |
| Gerçek zaman katsayısı | 0.35 | 1,0'ın altı canlı akışa yetişiyor demek |

## Olay anı

Etiketli kaza saniyesi **t=49 s**.

- Algı katmanının o karede saydığı kişi: **1**
- O karenin hareket enerjisindeki sırası: **13. / 347**

## Takip katmanının bedeli

`gozcu.track`'in sözleşmesi *tespit kayıttır, takip yalnız kimlik ekler*. Aşağıdaki `boxes_lost` sıfır değilse sözleşme tutmuyor demektir — kayıp, kimliksiz kutuyu düşüren süzgeçten değil, `model.track()`'in kendi içinden geliyor.

| | Takiple (boru hattı) | Takipsiz | Fark |
| --- | --- | --- | --- |
| Kutu | 3259 | 3259 | **−0** |
| Varlık duyarlılığı | %99 | %95 | değişmiyor |
| Sayım duyarlılığı | %93 | %77 | **iki katı** |
| Zirve kişi sayısı | 30 | 30 | |

Takip 0 karede kutu **eledi**, 0 karede ekledi.

## Etiketli kareler

Örneklem sistematik: her 8. saniye, seçilmiş değil. `±` sütunu kalabalık karelerde elle sayımın oynadığı payı gösterir.

| t (s) | Gerçek | Algının saydığı | Kaçırılan |
| ---: | ---: | ---: | ---: |
| 0 | 3 | 10 | -7 |
| 8 | 4 | 8 | -4 |
| 16 | 5 | 5 | 0 |
| 24 | 5 | 6 | -1 |
| 32 | 4 | 6 | -2 |
| 40 | 4 | 2 | 2 |
| 48 | 4 | 4 | 0 |
| 56 | 5 ±1 | 6 | -1 |
| 64 | 6 ±1 | 10 | -4 |
| 72 | 10 ±2 | 11 | -1 |
| 80 | 14 ±2 | 9 | 5 |
| 88 | 20 ±3 | 19 | 1 |
| 96 | 20 ±3 | 23 | -3 |
| 104 | 22 ±3 | 20 | 2 |
| 112 | 19 ±3 | 21 | -2 |

Ortalama mutlak sapma **2.3 kişi/kare**; en kötü tek kare **7 kişi**. Ortalama gerçek 9.7, ortalama sayılan 10.7.

## Süre

| Kademe | Saniye |
| --- | ---: |
| frames | 1.24 |
| motion | 0.84 |
| track | 38.35 |

---

Yeniden üretmek için:

```bash
uv run python -m benchmark.perception "WhatsApp Video 2026-08-25 at 15.35.33.mp4"
```
