# Tesis dünyası — kurgusal veri seti

> **Bu dizindeki veriler yarışma demosu için uydurulmuştur.** Kurgusal bir
> savunma sanayi üretim tesisini tanımlar. Hiçbir gerçek kişiyi, ekipmanı veya
> olayı temsil etmez. Personel isimleri baş harflerdir ve rastgeledir.

Gözcü'nün "tesis dünyası": operatör *"bu araçla ilgili daha önce bir olay olmuş
muydu?"* diye sorduğunda ve kapanış raporu kök nedeni yazdığında okunan veri.
Yayınlanacak açık veri setinin parçasıdır.

## Senaryo

Olay **15 Ağustos 2026, 03:12**'de geçiyor: B-Hattı sevkiyat alanında `IST-04`
istif aracı devriliyor, yerde hareketsiz bir kişi var, personel toplanıyor.

**Bütün tarihler dosyalarda sabittir.** Hiçbir değer "bugün"den hesaplanmaz —
aksi hâlde demo gerçek zaman ilerledikçe kayar.

## Dosyalar

| Dosya | Üst düzey anahtarlar | Ne var içinde |
|---|---|---|
| `facility.json` | `facility` · `production_lines` · `zones` · `shifts` | Tesis, hatlar (`B`, `C`), bölgeler ve vardiya saat aralıkları |
| `personnel.json` | `personnel` | Kararlı `PRS-00N` kimlikleriyle personel, roller, yetki belgeleri, vardiya |
| `equipment.json` | `equipment` | `IST-04` / `IST-07` envanteri, bakım geçmişi (`next_due` ile), arıza defteri |
| `prior_incidents.json` | `incidents` | Üç önceki olay; her biri bir `Episode` gövdesi + makine okunur üst veri |

Kimlikler İngilizce (`zone_id`, `line_id`, `personnel_id`), insana görünen
metinler Türkçe.

## Kök neden zinciri — `IST-04`

Kök neden **tamamen mekaniktir.** Operatörün istif aracı belgesi tamdır
(`PRS-001`, `forklift_licence`); hikâye bakım zincirinde:

| Tarih | Ne oldu |
|---|---|
| 2025-10-08 | Periyodik bakım yapıldı, vade **2026-04-08** |
| 2026-01-08 | Fren balata kontrolü: *"balata aşınma sınırında"* uyarısı, vade **2026-04-08** |
| 2026-04-08 | Her iki bakımın da vadesi doldu — **yapılmadı** |
| 2026-04-19 | Fren pedalı sertleşti; bakım talebi açıldı, iş emri kapanmadı |
| 2026-08-12 | Fren mesafesi uzadı, ramak kala (`OLY-2026-0812`) — hem arıza defterinde hem olay arşivinde, aynı olay |
| 2026-08-15 | Devrilme |

**Gecikme dosyada yazmaz, türetilir:** en son bakım kaydının `next_due`
tarihiyle senaryo tarihi arasındaki tam ay sayısı. 2026-04-08 → 2026-08-15
arası **4 ay**. Hesabı `loader.overdue_maintenance_months("IST-04")` yapar.

`IST-07` bilerek temizdir (bakımı güncel, arıza kaydı yok) — karşılaştırma
noktası olsun diye.

## Kullanım

```python
from gozcu.fixtures.loader import (load_fixture, load_history,
                                   overdue_maintenance_months,
                                   resolve_shift, resolve_zone)

overdue_maintenance_months("IST-04")   # 4
resolve_zone("B")["zone_id"]           # "line_b"
resolve_shift("03:12")                 # "night"
load_history(gw, store)                # arşivi tohumlar, gömülen sayısını döner
```
