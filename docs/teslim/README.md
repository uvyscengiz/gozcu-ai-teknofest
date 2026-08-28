# Teslim dokümantasyonu

Şartname §6 *"Proje dokümantasyonu"* başlığı altında **sekiz zorunlu bölüm**
sayıyor. Bu klasör o sekiz bölümün karşılığı.

Tam liste ve kaynağı: [sartname.md §7](../sartname.md#7-teslim-edilecekler-6).

| # | Bölüm | Dosya | Durum |
|---|---|---|---|
| 1 | Mimari özeti ve diyagramı | [01-mimari-ozeti-ve-diyagramlar.md](01-mimari-ozeti-ve-diyagramlar.md) | Yazıldı, güncel kodla doğrulandı |
| 2 | Agentic framework ve LLM'ler | [02-framework-ve-modeller.md](02-framework-ve-modeller.md) | Yazıldı |
| 3 | Senaryolar ve mock fonksiyonlar | [03-senaryolar-ve-mock.md](03-senaryolar-ve-mock.md) | Yazıldı |
| 4 | Kurulum/çalıştırma adımları | [04-kurulum-calistirma.md](04-kurulum-calistirma.md) | Yazıldı |
| 5 | Zorluklar ve çözümler | [05-zorluklar-ve-cozumler.md](05-zorluklar-ve-cozumler.md) | Yazıldı |
| 6 | Ek özellikler | [06-ek-ozellikler.md](06-ek-ozellikler.md) | Yazıldı |
| 7 | Ölçümleme sonuçları | [07-olcumleme.md](07-olcumleme.md) | Yazıldı |
| 8 | Ölçekleme ihtiyaçları | [08-olcekleme.md](08-olcekleme.md) | Yazıldı |

## Tek PDF

Sekiz bölüm jüri için tek bir PDF'e birleştirilir (kapak + İçindekiler +
bölümler arası çalışan linkler). Kaynak `.md` dosyaları değişmez, script
yalnız render eder:

```bash
uv sync --extra docs                              # ilk kurulumda bir kere
uv run --extra docs python scripts/build_teslim_pdf.py
```

Çıktı: `docs/teslim/gozcu-teslim-dokumani.pdf`. macOS'ta `weasyprint` için
Homebrew'den `pango`, `gdk-pixbuf`, `glib` gerekir (`brew install pango
gdk-pixbuf glib`) — script `DYLD_LIBRARY_PATH`'i kendi ayarlıyor.

## Kural

**Ölçülmemiş hiçbir şey ölçülmüş gibi yazılmaz.** Şartname §16 veri
sahteciliğini ve sonuç manipülasyonunu diskalifiye sebebi sayıyor; bu
klasördeki her sayının ya bir ölçüm dosyasında (`benchmark/results/`) ya
da bir kod yorumunda kaynağı olmalı.

## Bilinen açık

Repo kök dizininde henüz ayrı bir `LICENSE` dosyası yok. Şartname §9
Apache 2.0 lisansını yarışma bitişinde Türkiye Açık Kaynak Platformu
üzerinden otomatik kabul edilmiş sayıyor, yani bu bir diskalifiye riski
değil — ama şartname §7'nin açık kaynak/şeffaflık kalemi için repoya
açıkça bir `LICENSE` dosyası eklemek daha güçlü bir sunum olur
(bkz. [01-mimari §16](01-mimari-ozeti-ve-diyagramlar.md#16-şartname-eşleştirmesi)).
