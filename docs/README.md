# Gözcü AI — TEKNOFEST Docs

TEKNOFEST Yapay Zekâ Dil Ajanları Yarışması, **3. senaryo.**

Gözcü, fabrika kamera kaydını izleyip olayları fark eden, riski değerlendiren ve
operatörle Türkçe konuşan bir karar destek sistemi. Video yüklenir, sistem onu
baştan sona işler ve **kritik ana geldiğinde orada durup karar verir** — video
bitmeden operatöre seslenir, saha sistemlerini arar. Kapanışta hem şartnamenin
istediği JSON'u hem kök neden raporunu üretir.

**Teslim: 26 Ağustos 2026, 23:59. Kod dondurma: 26 Ağustos 12:00.**

## Nereden başlamalı

| Ne arıyorsun | Nereye bak |
|---|---|
| **Bugün ne yapacağım** | **[tasks/README.md](tasks/README.md)** — 18 görev, sahipleri, takvim |
| Sistem nasıl çalışıyor | [tasarım spec'i](superpowers/specs/2026-08-22-agentic-gozcu-design.md) |
| Ekibe anlatacağım | [Gözcü Nöbet Planı](https://claude.ai/code/artifact/d9aed59e-7a2e-45c0-b3e3-047e03edb7d6) — teknik olmayan özet |
| Neden böyle karar verdik | [05-decisions/decision-log.md](05-decisions/decision-log.md) |

**Plan-of-record: tasarım spec'i.** Bu klasördeki başka bir doküman onunla
çelişiyorsa spec geçerlidir.

## Kilitlenmiş kararlar

- **Girdi: yüklenen video dosyası.** Canlı kamera / RTSP kapsamda değil.
- **Kararlar olay anında.** Saha sistemleri videonun ortasında aranıyor, rapor
  sonrasında değil.
- **Alan: savunma sanayi tesisi iş güvenliği.** Şartnamenin kendi örneği
  (forklift devrilmesi + yaralı personel) bir üretim tesisi senaryosu.
- **Modeller organizasyonun gateway'inde**, OpenAI uyumlu API üzerinden. Yerel
  GPU yok. Model kimlikleri sadece `gozcu/config.py`'da.
- **Topoloji: süpervizör + uzman alt-ajanlar.** Operatörle konuşan tek bir
  Nöbetçi var; risk analizi, arşiv araması ve rapor üretimi onun çağırdığı
  uzmanlar.
- **Algı katmanı donuk.** `frames.py`, `detect.py`, `track.py`, `signals.py`
  değişmiyor.
- **Çıktı sözleşmesi:** `summary` · `events` · `risk` · `actions` — diğer her
  şey `ayrintili` altında, yerine değil.

## Klasörler

| Klasör | Durum |
|---|---|
| [tasks](tasks/) | **Güncel.** Uygulama görevleri, her biri kendi içinde tam |
| [superpowers/specs](superpowers/specs/) | **Güncel.** Tasarım spec'i — plan-of-record |
| [05-decisions](05-decisions/) | **Güncel.** Karar günlüğü ve açık kalemler |
| [04-mentor-guidance](04-mentor-guidance/) | Tarihsel kayıt — 2026-08-13 hoca görüşmesi |
| [06-references](06-references/) | Dış kaynaklar |
| [00-overview](00-overview/), [01-research](01-research/), [02-architecture](02-architecture/), [03-planning](03-planning/) | **Büyük ölçüde bayat.** Yarışma öncesi araştırma dönemine ait; dosyaların başında uyarı var |

## Puan cetveli

| Ağırlık | Kalem |
|---|---|
| %35 | Fonksiyonellik ve senaryo kapsamı |
| %35 | Teknik implementasyon ve mimari |
| %20 | Otonomi ve zekâ (operatör diyalogu) |
| %10 | Yenilikçilik |

Puanın %70'i ajan mimarisi ve senaryo bütünlüğünde. Görüntü işleme kalitesi
cetvelde **ayrı bir kalem değil.**
