# Gözcü — TEKNOFEST Yapay Zekâ Dil Ajanları, 3. senaryo

Fabrika kamera kaydını izleyip olayları fark eden, riski değerlendiren ve
operatörle Türkçe konuşan bir karar destek sistemi. Video yüklenir, sistem onu
baştan sona işler ve **kritik ana geldiğinde orada durup karar verir** — video
bitmeden operatöre seslenir, saha sistemlerini arar.

**Teslim: 26 Ağustos 2026, 23:59. Kod dondurma: 26 Ağustos 12:00.**

## Nereden başlanır

Bütün iş **[docs/tasks/](docs/tasks/README.md)** altında, görev başına bir dosya.
Her dosya kendi içinde tam: bağlam, kurulum, bağımlı olduğu imzalar, TDD
adımları, doğrulama komutu. Bir göreve başlarken o dosyayı oku — başka bir yere
bakman gerekmez.

- **Plan-of-record:** [tasarım spec'i](docs/superpowers/specs/2026-08-22-agentic-gozcu-design.md)
- **Karar günlüğü:** [decision-log](docs/05-decisions/decision-log.md)
- `docs/00-overview`, `01-research`, `02-architecture`, `03-planning` altındaki
  bazı dosyalar yarışma öncesi araştırma dönemine ait ve **bayat** — başlarında
  uyarı bandı var. Çelişkide spec ve görev dosyaları geçerlidir.

## Değişmez kurallar

- **Kod İngilizce.** Sınıf, fonksiyon, alan, JSON anahtarı, tool adı, SQL tablo
  adı — hepsi İngilizce.
- **İnsana görünen metin Türkçe.** Promptlar, operatör mesajları, özetler,
  yorumlar/docstring'ler ve **risk seviyesi değerleri** (`"Düşük" | "Orta" |
  "Yüksek" | "Kritik"`) Türkçe kalır.
- **Prompt bir enum sayıyorsa değerleri şemadakiyle birebir aynı olmalı.**
  Bunlar bir kez birbirinden ayrıldı ve sistem sessizce ölü hâle geldi.
- **Çıktı sözleşmesi:** `summary` · `events` · `risk` · `actions` — şartnamenin
  dört anahtarı, genişletilmiş katmanlar çökse bile üretilir. Fazlası
  `detail` altında, yerine değil.
- **Algı katmanı donuk.** `gozcu/frames.py`, `detect.py`, `track.py`,
  `signals.py` yarışma boyunca değişmiyor.
- **Model kimlikleri sadece `gozcu/config.py`'da.** Başka hiçbir dosyada model
  adı yazılmaz.
- **Kararlar olay anında verilir.** Tool çağrıları videonun zaman çizelgesi
  içinde, kritik anda gerçekleşir — kapanış raporundan sonra değil. Bu
  mimarinin omurgası; `DecisionLoop.run()` bu yüzden bir generator.
- **TDD.** Önce test, kırmızı olduğunu gör, sonra minimum kod.

## Komutlar

Kurulum, gateway ve sistem paketi ayrıntıları için [README.md](README.md) —
insan onboarding'i orada, burada sadece günlük komutlar.

```bash
uv sync --extra dev              # Apple Silicon'da --extra mac de ekle, yoksa mlx-vlm silinir
cp .env.example .env             # app.py çalıştırılmadan önce gerekli
uv run pytest tests/ -v
uv run --env-file .env python app.py
```

## Ekip

`uvyscengiz` (çekirdek + Nöbetçi + entegrasyon) · `Xana-bit` (tesis dünyası +
saha araçları) · `beyzaalive` (raportör + denetim) · `rumeysaoru` (konsol +
ölçüm). Gün bazlı çizelge [docs/tasks/README.md](docs/tasks/README.md) içinde.
