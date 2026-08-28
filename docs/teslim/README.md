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

## Bilinen açıklar — dokümantasyon dışı teslim kalemleri

Bu klasördeki sekiz bölüm tamam. Şartname §6/§9/§10'un **depo ve teslim
paketi** tarafında bugün açık olanlar:

| # | Açık | Şartname dayanağı |
|---|---|---|
| 1 | **Depo `private`** — açık kaynak olarak yayımlanmadı | §10: açık kaynak lisansla paylaşım zorunlu |
| 2 | **Etiketler eksik**: `BilisimVadisi2026`, takım adı, "Türkiye Açık Kaynak Platformu" | §10 |
| 3 | **`LICENSE` dosyası yok** (Apache 2.0). §9 lisansı yarışma bitişinde otomatik kabul edilmiş sayıyor, yani diskalifiye riski değil — ama şeffaflık kalemi için repoda açıkça durması daha güçlü | §9, §7 |
| 4 | **Demo videosu (≤10 dk)** depoda yok | §6 |
| 5 | **Sunum materyali — PDF *ve* PPTX** depoda yok | §6, §11 |

§10'un üçüncü koşulu (**kullanılan veri setinin herkese açık indirilebilir
bağlantısı**) kapatıldı:
[references/veri-seti.md](../references/veri-seti.md).

Bkz. [01-mimari §16](01-mimari-ozeti-ve-diyagramlar.md#16-şartname-eşleştirmesi).
