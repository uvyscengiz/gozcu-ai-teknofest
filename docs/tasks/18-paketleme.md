# Görev 18 — Paketleme ve teslim

**Bağımlılık:** hepsi · **Kod dondurma: 26 Ağustos 12:00**

## Bağlam

Teslim edilmeyen kod, yazılmamış koddur. Ve bu görevin kalemleri **ayrıca
puanlanıyor** — Yenilikçilik kalemi açıkça *"sunumun ve dokümantasyonun
kalitesi"* diyor. Paketleme cila değil, notun bir parçası.

Son gün, saat 23:59'da kapanıyor. Bu yüzden bu görev bir kontrol listesi ve
sahipleri baştan belli.

## Sabah — kod dondurmaya kadar (12:00)

> **Görev 08 Qdrant'a taşındı (`7d6a473`) — paketlemeyi üç yerden ilgilendiriyor.**
>
> 1. **`qdrant-client` yeni bir ÇALIŞMA ZAMANI bağımlılığı.** Dev ekstrası
>    değil; `pyproject.toml`'daki ana bağımlılık listesinde olmalı ve README'nin
>    bağımlılık bölümünde görünmeli. Temiz makinede `uv sync --extra dev`
>    sonrası import edilemiyorsa jüri sistemi hiç çalıştıramaz.
> 2. **`.env` artık İKİ anahtar taşıyor:** `GOZCU_GATEWAY_API_KEY` (LLM ağ
>    geçidi) ve `GOZCU_QDRANT_API_KEY` (vektör veritabanı, ayrı adres ve ayrı
>    anahtar). `.env.example` ikisini de **boş** olarak listelemeli.
> 3. **Hiçbiri repoya girmez.** Repo `public` yapılıyor; commit'lenmiş bir
>    anahtar geri alınamaz. Push öncesi `.env`'in `.gitignore`'da olduğunu ve
>    geçmişte hiçbir anahtarın bulunmadığını doğrula.
>
> Anahtarsız koşu **patlamaz**, sessizce süreç içi bir Qdrant'a düşer ve
> hafıza koşuyla birlikte yok olur. `gozcu.memory.memory_backend()` tek kelime
> döndürüyor (`"qdrant"` / `"local"`) — provada ve ölçüm koşusunda `"qdrant"`
> okumalı, yoksa epizodik hafıza demosu bir şey kanıtlamıyor.

> **Görev 17 indi (`4e1a979`) — pakete giren dosya listesi değişti.**
> `gozcu/interpret.py` ve `gozcu/schema.py` **silindi**: tek çağıranları
> `run.py`'dı ve yeniden yazımla öksüz kaldılar. Dokümantasyonda ya da mimari
> diyagramında onlara atıf yapan bir kutu kaldıysa artık bayat.
>
> Buna karşılık **Görev 08'in gömme defteri hâlâ canlı**: `Store.save_embedding`
> / `Store.embeddings`, `episode_embedding` tablosu ve `gozcu/fixtures/loader.py`
> içindeki tekrarsızlık okuması. Hafıza Qdrant'a taşındı ama yükleyici hangi
> epizodun zaten gömüldüğünü hâlâ `store.embeddings()` üzerinden okuyor. Bu üçü
> **tek bir birim**; ancak yükleyicinin kontrolü Qdrant'a taşındığında birlikte
> emekli olurlar — üçünü ayrı ayrı silme.

> **Görev 16 indi (`0ce9e86`) — pakete giren giriş yüzeyi değişti.**
>
> 1. **Konsolun giriş noktası `gozcu/ui/console.py:baslat()`.** `app.py` artık
>    **üç satır**; `baslat()`'ı çağırmaktan başka bir şey yapmıyor ve 1. Aşama
>    PoC'sinin kare galerisi kaldırıldı. Çalıştırma komutu yine
>    `uv run --env-file .env python app.py`, ama dokümantasyonda "ekran nerede"
>    sorusunun cevabı `gozcu/ui/console.py`.
> 2. **Test edilmiş Gradio sürümü 6.24.0.** `pyproject.toml` hâlâ `gradio>=5.0`
>    diyor, oysa 5.x'te konsol hiç açılmıyor: `Chatbot(type=…)` 6'da yok ve
>    `theme` `Blocks()`'tan `launch()`'a taşındı. README'nin bağımlılık bölümü
>    `qdrant-client`'ın yanında bu sürümü de yazmalı — temiz makinede 5.x
>    çözülürse jüri ekranı hiç göremez.
> 3. **`tests/test_smoke.py` yeniden yazıldı**, artık `gozcu.ui.console`
>    üzerine sınıyor: modül temiz import edilebiliyor mu, `app.py` gerçekten
>    yalnız `baslat()`'ı mı açıyor, mlx-vlm kurulu değilken alt süreç açmadan
>    okunur hata veriliyor mu. Ekranın kendi mantığı `tests/test_console.py`
>    altında, 49 test.
>
> **Konsolun on kabul kriterinin hepsi mock'lu testlerle karşılanıyor —
> hiçbiri gerçek modelle izlenmedi.** Aşağıdaki uçtan uca prova bu yüzden
> hâlâ açık ve bu görevin en riskli kalemi.

### Uçtan uca prova — `uvyscengiz` · **çekimden önce, atlanamaz**

Bütün görevlerin doğrulaması mock'lu `pytest`. **Sekiz demo anının gerçek
modellerle çalıştığını kimse görmedi** — konsol ([Görev 16](16-konsol.md))
25 Ağustos'ta indi, ama onu gerçek modelleri uçtan uca sürerken izleyen
olmadı. Aşağıdaki her madde konsolda bir düğmeye karşılık geliyor. Çekimden
önce baştan sona bir tur:

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
- [ ] `README.md`: bağımlılık listesi (`qdrant-client` ve **Gradio 6.24**
      dâhil), çalıştırma adımları, veri seti linki
- [ ] `.env` repoda **yok**; `.env.example` `GOZCU_GATEWAY_API_KEY` ve
      `GOZCU_QDRANT_API_KEY` alanlarını boş olarak listeliyor
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
