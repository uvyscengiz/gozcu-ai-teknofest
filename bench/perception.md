# Gözcü 0. Faz (algı) taban ölçümü

*Üretildi: 2026-08-25T17:28:15+00:00 · `benchmark/perception.py` · şema v1*

**Video:** `WhatsApp Video 2026-08-25 at 15.35.33.mp4` — 116 kare, 1 fps, 896 px genişlik.
**Model:** `yoloe-26s-seg.pt`, sınıflar `person,forklift,truck,vehicle`, eşik 0.03.

Bu tablo **algı katmanını tek başına** ölçer: gateway çağrısı yok, ajan katmanı yok. Uçtan uca KPI'lar için `bench/kpi.md`.

## Manşet

| Ölçüm | Değer | Ne demek |
| --- | --- | --- |
| Varlık duyarlılığı | **%97** | en az bir kişi görülen kare payı (etikete göre HER karede insan var) |
| Sayım duyarlılığı | **%83** | görülen kişi / gerçekte olan kişi, etiketli karelerde |
| Sıfır tespit oranı | **%0** | hiçbir kutu üretilmeyen kare payı |
| Kimlik atama oranı | %100 | kimlik alan kutu payı (353 ayrı kimlik) |
| Zirve kişi sayısı | 27 | tek karede sayılan en yüksek kişi (gerçek zirve: 22) |
| Gerçek zaman katsayısı | 0.13 | 1,0'ın altı canlı akışa yetişiyor demek |

## Olay anı

Etiketli kaza saniyesi **t=49 s**.

- Algı katmanının o karede saydığı kişi: **1**
- O karenin hareket enerjisindeki sırası: **53. / 116**

## Takip katmanının bedeli

`gozcu.track`'in sözleşmesi *tespit kayıttır, takip yalnız kimlik ekler*. Aşağıdaki `boxes_lost` sıfır değilse sözleşme tutmuyor demektir — kayıp, kimliksiz kutuyu düşüren süzgeçten değil, `model.track()`'in kendi içinden geliyor.

| | Takiple (boru hattı) | Takipsiz | Fark |
| --- | --- | --- | --- |
| Kutu | 1150 | 1150 | **−0** |
| Varlık duyarlılığı | %97 | %97 | değişmiyor |
| Sayım duyarlılığı | %83 | %83 | **iki katı** |
| Zirve kişi sayısı | 27 | 27 | |

Takip 0 karede kutu **eledi**, 0 karede ekledi.

## Etiketli kareler

Örneklem sistematik: her 8. saniye, seçilmiş değil. `±` sütunu kalabalık karelerde elle sayımın oynadığı payı gösterir.

| t (s) | Gerçek | Algının saydığı | Kaçırılan |
| ---: | ---: | ---: | ---: |
| 0 | 3 | 11 | -8 |
| 8 | 4 | 15 | -11 |
| 16 | 5 | 5 | 0 |
| 24 | 5 | 4 | 1 |
| 32 | 4 | 3 | 1 |
| 40 | 4 | 1 | 3 |
| 48 | 4 | 4 | 0 |
| 56 | 5 ±1 | 2 | 3 |
| 64 | 6 ±1 | 7 | -1 |
| 72 | 10 ±2 | 10 | 0 |
| 80 | 14 ±2 | 7 | 7 |
| 88 | 20 ±3 | 19 | 1 |
| 96 | 20 ±3 | 23 | -3 |
| 104 | 22 ±3 | 18 | 4 |
| 112 | 19 ±3 | 15 | 4 |

Ortalama mutlak sapma **3.1 kişi/kare**; en kötü tek kare **11 kişi**. Ortalama gerçek 9.7, ortalama sayılan 9.6.

## Süre

| Kademe | Saniye |
| --- | ---: |
| frames | 1.15 |
| motion | 0.23 |
| track | 13.92 |

---

Yeniden üretmek için:

```bash
uv run python -m benchmark.perception "WhatsApp Video 2026-08-25 at 15.35.33.mp4"
```
