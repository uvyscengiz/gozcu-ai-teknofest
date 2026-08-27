# Gözcü AI — TEKNOFEST Docs

TEKNOFEST Yapay Zekâ Dil Ajanları Yarışması, **3. senaryo.**

Gözcü, fabrika kamera kaydını izleyip olayları fark eden, riski değerlendiren ve
operatörle Türkçe konuşan bir karar destek sistemi. Video yüklenir, sistem onu
baştan sona işler ve **kritik ana geldiğinde orada durup karar verir** — video
bitmeden operatöre seslenir, saha sistemlerini arar. Kapanışta hem şartnamenin
istediği JSON'u hem kök neden raporunu üretir.

**GitHub teslimi: 26 Ağustos 2026, 23:59** (kod dondurma 26 Ağustos 12:00) ·
**Final: 27–28 Ağustos, Bilişim Vadisi — Kocaeli, fiziki.**

## Nereden başlamalı

| Ne arıyorsun | Nereye bak |
|---|---|
| **Bugün ne yapacağım** | **[tasks/README.md](tasks/README.md)** — 18 görev, sahipleri, takvim |
| **Yarışma ne istiyor** | **[00-overview/sartname.md](00-overview/sartname.md)** — şartname, takvim, final, teslim listesi, puan cetveli |
| **Jüriye giden doküman** | **[teslim/](teslim/README.md)** — şartname §6'nın sekiz zorunlu bölümü |
| Sistem nasıl çalışıyor | [tasarım spec'i](superpowers/specs/2026-08-22-agentic-gozcu-design.md) · [mimari özeti + diyagramlar](teslim/01-mimari-ozeti-ve-diyagramlar.md) |
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
- **Algı katmanının dondurması 25 Ağustos'ta kaldırıldı.** Gerçek görüntüyle
  ilk koşuda katmanın çalışmadığı ölçüldü; bozuk bir sistemi dondurmak onu
  bozuk tutar. Değişiklikler ölçüye dayanır ve karar günlüğüne yazılır.
- **Çıktı sözleşmesi:** `summary` · `events` · `risk` · `actions` — diğer her
  şey `ayrintili` altında, yerine değil.

## Klasörler

| Klasör | Durum |
|---|---|
| [teslim](teslim/) | **Güncel.** Jüriye giden dokümantasyon — şartname §6'nın sekiz bölümü |
| [tasks](tasks/) | **Güncel.** Uygulama görevleri, her biri kendi içinde tam |
| [superpowers/specs](superpowers/specs/) | **Güncel.** Tasarım spec'i — plan-of-record |
| [05-decisions](05-decisions/) | **Güncel.** Karar günlüğü ve açık kalemler |
| [04-mentor-guidance](04-mentor-guidance/) | Tarihsel kayıt — 2026-08-13 hoca görüşmesi |
| [06-references](06-references/) | **Güncel.** [EVREN saha notları](06-references/evren-gateway.md) ölçülmüş; dış kaynaklar |
| [00-overview/sartname.md](00-overview/sartname.md) | **Güncel.** Şartname, takvim, final etabı, teslim listesi — yarışma kurallarının tek kaynağı |
| [00-overview](00-overview/) (kalanı), [01-research](01-research/), [02-architecture](02-architecture/), [03-planning](03-planning/) | **Büyük ölçüde bayat.** Yarışma öncesi araştırma dönemine ait; dosyaların başında uyarı var |

## Puan cetveli

| Ağırlık | Kalem |
|---|---|
| %35 | Fonksiyonellik ve senaryo kapsamı |
| %35 | Teknik implementasyon ve mimari |
| %20 | Otonomi ve zekâ (operatör diyalogu) |
| %10 | Yenilikçilik |

Puanın %70'i ajan mimarisi ve senaryo bütünlüğünde. Görüntü işleme kalitesi
cetvelde **ayrı bir kalem değil.** Alt başlıklarıyla birlikte:
[sartname.md §8](00-overview/sartname.md#8-değerlendirme-kriterleri-7).
