# Teslim dokümantasyonu

Şartname §6 *"Proje dokümantasyonu"* başlığı altında **sekiz zorunlu bölüm**
sayıyor. Bu klasör o sekiz bölümün karşılığı — jüriye giden metin burada,
geliştirme notları [docs/](../README.md)'nin geri kalanında.

Tam liste ve kaynağı: [sartname.md §7](../00-overview/sartname.md#7-teslim-edilecekler-6).

| # | Bölüm | Dosya | Durum |
|---|---|---|---|
| ① | Mimari özeti ve **diyagramı** | [01-mimari-ozeti-ve-diyagramlar.md](01-mimari-ozeti-ve-diyagramlar.md) · [PDF](01-mimari-ozeti-ve-diyagramlar.pdf) | ✅ yazıldı |
| ② | Agentic framework ve LLM'ler | — | bekliyor |
| ③ | İmplemente edilen senaryolar ve mock fonksiyonlar | — | bekliyor |
| ④ | Adım adım kurulum/çalıştırma | [README.md](../../README.md) devralıyor | ✅ mevcut |
| ⑤ | Karşılaşılan zorluklar ve çözümleri | — | bekliyor |
| ⑥ | Eklenen ek özellikler | — | bekliyor |
| ⑦ | Ölçümleme sonuçları | [bench/](../../bench/) — kısmî | ⚠️ uçtan uca koşu eksik |
| ⑧ | Ölçekleme noktasında gerekli ihtiyaçlar | — | bekliyor |

## PDF üretimi

Markdown **kaynaktır**, PDF ondan türer. Bir bölümü düzelttikten sonra PDF'i
yeniden üret; elle PDF düzenleme yok, yoksa iki sürüm ayrışır.

```bash
uv run --with markdown --with reportlab --with pypdf \
    python scripts/build-doc-pdf.py docs/teslim/01-mimari-ozeti-ve-diyagramlar.md
```

Dizgi tarayıcıya (Chrome/Edge, headless) yapılıyor: diyagramlar ASCII kutu
çizimi ve tek kritik şey **sütunların kaymaması** — Consolas bunu garanti
ediyor. Sayfa numarası ikinci geçişte reportlab ile basılıyor, çünkü Chrome
CSS'in `@bottom-center` kenar kutusunu desteklemiyor. Ayrıntı:
[`scripts/build-doc-pdf.py`](../../scripts/build-doc-pdf.py).

Depo içi göreli bağlantılar PDF'te otomatik olarak GitHub URL'lerine
çevriliyor — jüri PDF'ten dosyaya tıklayabiliyor.

## Bu klasörün kuralı

**Ölçülmemiş hiçbir şey ölçülmüş gibi yazılmaz.** Şartname §16 veri
sahteciliğini ve sonuç manipülasyonunu diskalifiye sebebi sayıyor; bu
klasördeki her sayının ya bir ölçüm dosyasında (`bench/`) ya da bir kod
yorumunda kaynağı var. Kaynağı olmayan yerde "ölçülmedi" yazar.

Yürütme kontrol listesi: [görev 18 — paketleme](../tasks/18-paketleme.md).
