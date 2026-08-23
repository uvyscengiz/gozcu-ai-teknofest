# Görev 18 — Paketleme ve teslim

**Sahip:** hepimiz · **Gün:** 26 Ağustos · **Süre:** ~1 kişi-günü
**Bağımlılık:** hepsi · **Kod dondurma: 26 Ağustos 12:00**

## Bağlam

Teslim edilmeyen kod, yazılmamış koddur. Ve bu görevin kalemleri **ayrıca
puanlanıyor** — Yenilikçilik kalemi açıkça *"sunumun ve dokümantasyonun
kalitesi"* diyor. Paketleme cila değil, notun bir parçası.

Son gün, saat 23:59'da kapanıyor. Bu yüzden bu görev bir kontrol listesi ve
sahipleri baştan belli.

## Sabah — kod dondurmaya kadar (12:00)

### Uçtan uca prova — `uvyscengiz` · **çekimden önce, atlanamaz**

Bütün görevlerin doğrulaması mock'lu `pytest`. **Sekiz demo anının gerçek
modellerle çalıştığını kimse görmedi.** Çekimden önce baştan sona bir tur:

- [ ] Klip yüklenir, zaman çizelgesi dolar
- [ ] Kritik anda döngü durur, Nöbetçi kendiliğinden konuşur
- [ ] Vardiya sorgusu konuşmadan **önce** yapılmış olur
- [ ] Ajan göremediğini sorar (uydurmaz)
- [ ] Operatör düzeltmesi epizot özetine ve rapora yansır
- [ ] İSG kaydı açılır, hat durdurma **izin ister**
- [ ] Bağlam değişiminde açık olaya kendiliğinden dönülür
- [ ] Bağlantı kesilir → sistem ayakta, dönünce atlananlar telafi edilir
- [ ] Kapanışta dört anahtarlı JSON + kök neden raporu çıkar

Tutmayan madde varsa **çekimden önce** düzeltilir; tutmuyorsa demo senaryosundan
çıkarılır. Çalışmayan bir şeyi çekmek en kötü seçenek.

### Ölçüm koşusu — `rumeysaoru`

- [ ] `uv run python -m benchmark.run` — etiketli beş klip
- [ ] `uv run python -m benchmark.report` → `bench/kpi.md` + `bench/decision-distribution.png`
- [ ] **Karar dağılımı grafiğindeki gerçek sayıyı not al** — sunumdaki manşet
      cümle bu sayıyla yazılacak. Tahmin edilmiş bir yüzdeyi slayta koyma.

> **Görev 15 indi (`b08fce8`) — `bench/` teslim edilecek.** Ölçüm çıktıları
> versiyonlanan `bench/` dizininde duruyor: `kpi.schema.json` (commit'li
> sözleşme), `kpi.json`, `kpi.md` ve `decision-distribution.png`. `runs/` değil
> — orası `.gitignore`'da ve ultralytics'in. Pakete `bench/` dahil edilmeli;
> dışarıda kalan tek şey klip başına SQLite deposu (`bench/stores/`).
>
> **Olay pencereleri hâlâ işaretsiz.** `benchmark/ground_truth.csv`'deki
> `start_s` / `end_s` alanlarını videoları izleyen bir insan doldurana kadar
> `timestamp_drift_s` `null` okur; bu, ölçüm koşusundan önce yapılacak el işi.

### Türkçe üslup turu — `beyzaalive`

Ekipten Türkçesi en iyi olan kişi, yarım saat. Üretilen ~20 çıktıyı oku:

- [ ] Kısa cümle mi, çeviri mi kokuyor?
- [ ] Saha terminolojisi doğru mu (`istif aracı`, `vardiya amiri`, `yerde hareketsiz kişi`)
- [ ] Edilgen çatı fazla mı?
- [ ] Özet operatörün **bir bakışta** karar almasına yarıyor mu?

Düzeltmeler prompt'lara işlenir. **12:00'den sonra sadece prompt metni değişir,
kod değişmez.**

## Öğleden sonra — teslim

### Demo videosu (≤10 dk) — `Xana-bit`

Sekiz an, sırayla. Ekran kaydı + sesli anlatım. Şartname *"zorlu koşulları
(örn: bağlam değişimi denemesi) nasıl yönettiğini"* ve *"metin tabanlı
etkileşimin net gösterilmesini"* istiyor — bu ikisi videoda **açıkça** görünmeli.

- [ ] An 00 yükleme → An 07 iki rapor
- [ ] Bağlam değişimi anı net
- [ ] Bağlantı kesme anı net
- [ ] Kapanışta JSON, şartnamenin §5 örneğiyle **yan yana** gösterilir

### Sunum videosu (1 dk) — `Xana-bit`

Ayrı dosya. Uzun videodan kesit değil, kendi kurgusu: olay → karar → aksiyon →
rapor.

### Dokümantasyon — `uvyscengiz` + `beyzaalive`

Şartnamenin istediği yedi bölüm, hepsi zorunlu:

- [ ] Sistem mimarisinin özeti ve **diyagramı**
- [ ] Kullanılan agentic framework ve LLM'ler → *"kendi ajan katmanımızı yazdık"*
      + bileşenler (süpervizör deseni, araç kayıt defteri, tipli devir
      protokolü, epizodik hafıza, kademeli model yönlendirme). Kütüphane adı
      yerine yeteneklerin kodda nerede olduğu gösterilir
- [ ] İmplemente edilen senaryolar ve mock fonksiyonlar
- [ ] Kurulum ve çalıştırma adımları — `git clone` → `uv sync --extra dev` → tek komut
- [ ] Karşılaşılan zorluklar ve çözümler
- [ ] **Bilinen sınırlar** — nesne tanıyıcıda yangın/duman sınıfı yok,
      açıklamalar genel geçer, canlı kamera girdisi kapsam dışı. Bunları
      saklamak yerine yazmak, açıklanabilirlik lehine puan
- [ ] Ölçümleme sonuçları (`bench/kpi.md`)
- [ ] Ölçekleme ihtiyaçları

### Sunum — `rumeysaoru`

- [ ] Slaytlar, **PDF ve PPTX** ikisi birden
- [ ] Tek grafik: karar dağılımı piramidi, **ölçülmüş gerçek sayıyla**
- [ ] 4 dakikaya sığdığı prova edilir

### GitHub — `uvyscengiz`

- [ ] Repo `public` yapılır
- [ ] `LICENSE` — Apache 2.0
- [ ] Topic'ler: `BilisimVadisi2026`, `Türkiye Açık Kaynak Platformu`
- [ ] `README.md`: bağımlılık listesi, çalıştırma adımları, veri seti linki
- [ ] Veri seti (`gozcu/fixtures/` + `benchmark/ground_truth.csv`) herkese açık
      indirilebilir bir linkte
- [ ] Demo videosu ve sunum repoya yüklenir
- [ ] Son commit atılır ve **23:59'dan önce** push edilir

## Doğrulama

Temiz bir makinede:

```bash
git clone https://github.com/uvyscengiz/gozcu-ai-teknofest.git
cd gozcu-ai-teknofest && uv sync --extra dev && uv run pytest tests/ -q
```

Jürinin yapacağı ilk şey bu. Kırılırsa geri kalan her şey konuşulmuyor bile.

## Takıldığında

Bu görevde takılmak yok — kalemler paralel ve bağımsız. Bir kalem yetişmiyorsa
**tamamlanmamış hâlini teslim et**, atlamaktansa eksik teslim iyidir.
