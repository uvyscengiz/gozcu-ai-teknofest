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
- **Algı katmanı artık donuk DEĞİL** (25 Ağustos'ta kaldırıldı). Dondurma bir
  takvim kararıydı: üç gün içinde algı kalitesiyle uğraşmak yerine ajan
  mimarisine odaklanmak için konmuştu. Gerçek görüntüyle ilk koşuda katmanın
  **çalışmadığı ölçüldü** — raf çökmesi klibinde forklift de operatör de gözle
  apaçık görünürken 23 karenin 23'ünde sıfır tespit. Bozuk bir sistemi
  dondurmak onu bozuk tutar. Değişiklikler ölçüye dayanacak ve
  `docs/05-decisions/decision-log.md`'ye kaydedilecek.
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

`uvyscengiz` · `Xana-bit` · `beyzaalive` · `rumeysaoru`

Görev başına sahiplik ve gün bazlı çizelge **kaldırıldı**: iş o sırayla
ilerlemedi ve duran bir çizelge, bitmiş bir görevi "seninki, başla" diye
göstererek zarar veriyor. Güncel durum
[docs/tasks/README.md](docs/tasks/README.md) içinde.
