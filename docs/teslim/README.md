# Teslim dokümantasyonu

Şartname §6 *"Proje dokümantasyonu"* başlığı altında **sekiz zorunlu bölüm**
sayıyor. Bu klasör o sekiz bölümün karşılığı.

Tam liste ve kaynağı: [sartname.md §7](../sartname.md#7-teslim-edilecekler-6).

| # | Bölüm | Dosya | Durum |
|---|---|---|---|
| ① | Mimari özeti ve diyagramı | [01-mimari-ozeti-ve-diyagramlar.md](01-mimari-ozeti-ve-diyagramlar.md) | ✅ yazıldı, güncel kodla doğrulandı |
| ② | Agentic framework ve LLM'ler | [02-framework-ve-modeller.md](02-framework-ve-modeller.md) | ✅ yazıldı |
| ③ | Senaryolar ve mock fonksiyonlar | [03-senaryolar-ve-mock.md](03-senaryolar-ve-mock.md) | ✅ yazıldı |
| ④ | Kurulum/çalıştırma adımları | [04-kurulum-calistirma.md](04-kurulum-calistirma.md) | ✅ yazıldı |
| ⑤ | Zorluklar ve çözümler | [05-zorluklar-ve-cozumler.md](05-zorluklar-ve-cozumler.md) | ✅ yazıldı |
| ⑥ | Ek özellikler | [06-ek-ozellikler.md](06-ek-ozellikler.md) | ✅ yazıldı |
| ⑦ | Ölçümleme sonuçları | [07-olcumleme.md](07-olcumleme.md) | ✅ yazıldı |
| ⑧ | Ölçekleme ihtiyaçları | [08-olcekleme.md](08-olcekleme.md) | ✅ yazıldı |

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
