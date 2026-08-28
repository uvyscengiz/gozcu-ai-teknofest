
# ⑧ Ölçekleme noktasında gerekli ihtiyaçlar

**Gözcü** · Takım **FERASET** (`team37`) · Muğla Sıtkı Koçman Üniversitesi

Bu bölüm şartname §6'nın *"ölçekleme noktasında gerekli ihtiyaçlar"*
kalemidir. Kaynaklar: [`docs/references/evren-gateway.md`](../references/evren-gateway.md)
(organizasyonun gateway'i üzerine takımın kendi ölçümleri) ve
[`docs/decisions/decision-log.md`](../decisions/decision-log.md).

> **Not:** aşağıdaki bazı sayılar için organizasyonun kendi referans
> belgesiyle kodun kendisi arasında küçük bir tutarsızlık bulundu ve bu
> belgede kod tarafı esas alındı — örneğin referans belge Aksiyon
> Planlayıcı'yı `fast` kademesine bağlıyor, ama
> [`gozcu/agents/action_planner.py`](../../gozcu/agents/action_planner.py)
> doğrudan okunduğunda iki çağrının da `main` kademesini kullandığı
> görülüyor. Bu belge her zaman **çalışan kodu** esas alıyor.

---

## 1. Mevcut darboğazlar

### (a) Paylaşımlı gateway kapasitesi — takım-dışı bir sınır

Organizasyonun EVREN servisi sekiz H200 üzerinde çalışıyor ve takımın
kendi anahtarında bir hız sınırı yok (`max_parallel_requests: null`). Ama
**video yolu bütün takımlar arasında paylaşımlı**: ölçülen kapasite
dakikada **~6,4 tam uzunlukta video isteği**. Bu, tek bir takımın kontrol
edemeyeceği bir tavan — final günü bütün takımlar aynı anda demo
çalıştırırsa kuyruklama beklenmeli (organizasyonun kendi notu: bütün
takımlar aynı anda 3 dakikalık klip gönderse kuyruk ~7 dakikada boşalır).

### (b) Görü kademesinin maliyeti — tek pencere darboğazı

Ölçülen gecikmeler arasında yalnız `vlm` uzun: 7,0-8,7 sn/çağrı (bkz.
[07-olcumleme.md](07-olcumleme.md)). Mimarinin bütün maliyet tasarrufu
(pencere başına en fazla bir görü çağrısı, hareket-enerjisi triyajı) bu
tek darboğazı **nereye harcayacağını seçmekten** geliyor. 10 dakikalık bir
video en kötü hâlde 60 pencere × 1 görü çağrısı = 60 çağrı; ölçülen ortalama
gecikmeyle (~8 sn) bu tek başına ~8 dakika demek.

### (c) Şema kod çözümü — ölçülüp kapatılan bir darboğaz

26 Ağustos'ta canlı ölçülen bir arıza: üst sınırsız şemalı bir istek 183
saniye sürebiliyordu (kaçak tekrar). `SCHEMA_MAX_TOKENS=8192` bunu kapattı,
ama bu, **büyüyen çıktı boyutunun** (daha uzun raporlar, daha çok araç
turu) gelecekte yeniden karşılaşılabilecek bir sınır olduğunu gösteriyor.

### (d) Eş zamanlılık — sıfıra yakın

Boru hattı (`run_pipeline`) tek bir iş parçacığında koşuyor; konsol bir
koşuyu **iptal edemiyor** — `abandon` yalnız operatörün beklemesini
serbest bırakıyor, arka plan iş parçacığı koşmaya devam edip paylaşımlı
`team37` kotasını tüketmeye devam ediyor
([decision-log, Görev 21](../decisions/decision-log.md)). Bugünkü
demo/tekli-video kullanım biçiminde sorun değil, ama birden fazla video
aynı anda işlenmek istendiğinde (§2) bu tasarım kararı yeniden ele
alınmalı.

---

## 2. Yatay ölçekleme — birden fazla kamera / video akışı

Bugünkü mimari **açıkça tek video = tek izole koşu** varsayımı üzerine
kurulu ve bu bilinçli bir tasarım kararı, kaza değil:

- **Depo koşu ömürlü.** `Store()` varsayılan olarak `:memory:` SQLite
  açıyor; iki koşu arasında hiçbir satır paylaşılmıyor. Kalıcı, koşular
  arası tek bir SQLite denendi ve **reddedildi**
  ([decision-log, Görev 22](../decisions/decision-log.md)): ikinci bir
  videonun açık epizodu birincinin açık epizoduyla kaynaşabiliyor, defter
  sınırsız büyüyor, ve arşiv kayıtları koşunun kendi `events[]` listesine
  sızıp şartnamenin dört anahtarını kirletiyor.
- **Epizodik hafıza (Qdrant) takım başına tek bir izole örnek.** Birden
  fazla eşzamanlı video/kamera aynı `team37` koleksiyonuna yazarsa
  epizot hacmi artar (bugün "bir vardiya birkaç yüz epizot" ölçeğinde,
  organizasyonun kendi notu) ama mimari **doğru** kalır — nokta kimliği
  zaten video içeriğinden türetiliyor, çakışma riski yok.
- **Gateway kotası paylaşımlı ve dakika başına video sayısıyla sınırlı**
  (§1a). Birden fazla kamera aynı anda işlenmek istenirse asıl darboğaz
  organizasyonun 6,4 istek/dakika tavanı olur, bizim kodumuz değil.

**Çok kameralı bir kuruluma geçmek için gereken somut değişiklikler:**

1. Depo koşu-ömürlü olmaktan çıkarılmalı — kamera/video kimliğine göre
   isimlendirilmiş kalıcı bir SQLite dosyası (`gozcu/core/store.py`'nin
   bugünkü tek değişikliği: `Store(path=...)`), epizot izolasyonu bir
   `run_id`/`camera_id` sütunuyla korunarak.
2. Eş zamanlı koşuların paylaşımlı gateway kotasını **adil paylaşacağı**
   bir sıra/öncelik mekanizması eklenmeli — bugün her koşu kotayı
   sınırsızca tüketiyor.
3. `run_pipeline`'ın tek-iş-parçacığı varsayımı bir kuyruk/worker havuzuna
   dönüşmeli; iptal edilebilirlik (bugün eksik, §1d) gerçek hâle
   getirilmeli.

---

## 3. Dikey ölçekleme — daha büyük modeller, daha yüksek çözünürlük

**Daha büyük model, ters etki ölçüldü.** Algı katmanında (§2,
[05-zorluklar-ve-cozumler.md](05-zorluklar-ve-cozumler.md)) daha büyük
YOLO varyantları test edildi ve sayım duyarlılığı **düştü** (11n %89,7,
11m %56,6, conf=0,05'te). Görü kademesinde de organizasyonun sunduğu tek
`vlm` modeli (`Qwen3-VL-32B`) sabit; büyütme takımın elinde değil.

**Çözünürlük artırmak da ölçülüp reddedildi.** Kare genişliği 896px'te
kişi güveni 0,159'a, 1280px'te sıfıra düşüyor — kaynak görüntü 960×720 ve
gerçek optik detay o kadar; büyütmek gürültüyü esnetip nesneyi modelin
kalibre olduğu ölçek dağılımının dışına itiyor. `FRAME_WIDTH=640` bu
yüzden ölçülerek seçildi, varsayılan olarak büyütülmemeli.

**Video klip süresi uzatmak da bir maliyet-doğruluk takası.** Organizasyonun
ölçtüğü tablo:

| Klip süresi | Çözünürlük ölçeği |
|---|---|
| 15 sn | 0,95 |
| 30 sn | 0,65 |
| 60 sn | 0,47 |
| 120 sn | 0,33 |
| 180 sn | 0,28 |

10 saniyelik pencere kararı (`WINDOW_S`) bu tablonun iyi ucunda kalmak
için seçildi — "yerde hareketsiz kişi" gibi küçük, düşük kontrastlı bir
hedef, iki token'ın altında kalırsa modelin çözemediği bir nesneye dönüşür.
Daha uzun pencereler (daha az görü çağrısı = daha ucuz) doğrudan tespit
kalitesini düşürür; bu bir mühendislik ayarı değil, ölçülmüş bir taban.

**vlm'in kendi tavanları:** 2,0 fps örnekleme, en fazla 520 kare, süre
tavanı 260 sn, kodlayıcı piksel bütçesi 140 MP — bunlar organizasyon
tarafında sabit, dikey ölçeklemenin doğal sınırı.

---

## 4. Yazılım ihtiyaçları — üretime geçiş için eksik katmanlar

Bugünkü sistem bir **demo/yarışma** kurulumu; üretime (sürekli çalışan,
çok kameralı bir saha operasyonu) geçiş için eksik olan somut katmanlar:

| İhtiyaç | Bugünkü durum | Neden gerekli |
|---|---|---|
| Kuyruk sistemi | Yok — her koşu kendi iş parçacığı | Paylaşımlı gateway kotasını (§1a) adil paylaştırmak, aşırı yüklenmeyi önlemek |
| Dağıtık orkestrasyon | Yok — tek süreç, tek makine | Çok kameralı kuruluma geçişte iş parçacığı başına bir video ölçeklenmez |
| Kalıcı depolama | Koşu-ömürlü SQLite | Koşular arası devamlılık, denetim izi, kamera başına geçmiş |
| İzleme/gözlemlenebilirlik | `gozcu/output/trace.py` — konsola özel iz kaydı | Üretimde merkezi log toplama, alarm eşikleri (ör. `is_degraded` oranı) |
| Canlı kaynak soyutlaması | Yok — `extract_frames` yalnız dosya yolu alıyor | RTSP/canlı kamera desteği için yeni bir katman gerekir (bkz. [01-mimari §15](01-mimari-ozeti-ve-diyagramlar.md#15-bilinen-sınırlar)) |

---

## 5. Canlı akışa genelleşmeyen tasarım kararları — açıkça işaretli

Şartname *"yüksek hacimli veri altında sistem davranışı"*nı puanlıyor;
burada dürüstçe yazılması gereken şey **hangi optimizasyonların bugünkü
haliyle canlı bir kameraya taşınamayacağı**:

- **Top-K görü bütçesi videonun tamamının önceden bilinmesine dayanıyor**
  (`_energy_indices`, [01-mimari §4c](01-mimari-ozeti-ve-diyagramlar.md#4-pencere-karar-akışı--mimarinin-çekirdeği)).
  Gerçek bir canlı yayında böyle bir liste yok; kayan bir eşik ya da
  rezervuar örneklemesi gerekir.
- **"Toplanma" ve K2/K4 sinyalleri koşunun kendi medyanına göre
  kalibre ediliyor** (`gozcu/agents/orchestrator.py::window_signal_verdict`,
  `gozcu/output/adapter.py`). Bu, koşunun tamamının bilinmesini
  gerektiriyor — canlı bir akışta bunun yerine kayan bir pencere
  istatistiği (ör. son N dakikanın medyanı) gerekir.
- **Emsal alaka eşikleri (0,54 / 0,47) mevcut arşiv kapsamına göre
  kalibre edildi.** Arşiv büyüdükçe/daraldıkça bu bant yeniden ölçülmeli —
  diyalog eşiğinin payı zaten dar (en yüksek alakasız 0,457 ile en düşük
  gerçek diyalog sorgusu 0,482 arasında yalnız 0,025 var).

Bu üçü de kod yorumlarında **"bu tasarım genelleşmiyor ve genelleşiyormuş
gibi anlatılmıyor"** diye işaretli — ölçekleme planının ilk maddesi bu
üçünü canlı-akış-uyumlu bir sürüme çevirmek olmalı.

---

## 6. Özet — ölçekleme yol haritası

| Öncelik | Değişiklik | Tetikleyen darboğaz |
|---|---|---|
| 1 | Koşu-ömürlü SQLite → kalıcı, `run_id`'li depo | §2 çok kameralı kullanım |
| 2 | Top-K görü bütçesi → kayan eşik/rezervuar örneklemesi | §5 canlı akış |
| 3 | Medyan tabanlı sinyaller → kayan pencere istatistiği | §5 canlı akış |
| 4 | Kuyruk/öncelik mekanizması | §1a paylaşımlı gateway kotası |
| 5 | İptal edilebilir koşular | §1d eş zamanlılık |
| 6 | Emsal eşiklerinin periyodik yeniden kalibrasyonu | §5 arşiv büyümesi |

Bu yol haritasının hiçbir maddesi bugün ölçülmedi — hepsi mevcut kod
yorumlarındaki dürüst sınır notlarından ve organizasyonun kapasite
rakamlarından türetildi. Ölçekleme çalışması başladığında önce §1-3'teki
sayılar yeni koşullarda yeniden ölçülmeli.
