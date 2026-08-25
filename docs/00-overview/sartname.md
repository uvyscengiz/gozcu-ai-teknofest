# Şartname ve yarışma kuralları — tek kaynak

> **Bu dosya, şartnamenin repodaki karşılığıdır.** Yarışma kurallarını, takvimi,
> teslim listesini ve puan cetvelini bir daha dışarıdan yapıştırmaya gerek yok;
> bir soru "yarışma ne istiyor?" diye başlıyorsa cevabı burada.
>
> Kaynaklar: **2026 Şartnamesi (3. Senaryo)** PDF'i (yürütücü: Bilişim Vadisi,
> 26 Haziran 2026 sürümü) ve organizasyonun 24–25 Ağustos 2026 tarihli
> bilgilendirme e-postaları. Her satırın hangi kaynaktan geldiği aşağıda
> işaretli. Şartname ile e-posta çelişirse **e-posta daha yenidir.**

## 1. Kimlik

| | |
|---|---|
| Yarışma | TEKNOFEST 2026 Yapay Zekâ Dil Ajanları Yarışması |
| Yürütücü | Bilişim Vadisi |
| Senaryo | **3 — Video Analiz ve Karar Destek Sistemi** |
| Takım | **FERASET** · takım kimliği `team37` |
| Üniversite | Muğla Sıtkı Koçman Üniversitesi — 4 yazılım mühendisliği öğrencisi |
| Teslim kanalı | GitHub — `BilisimVadisi2026` etiketiyle |
| Proje | Gözcü — [proje özeti](project-overview.md) |

Şartname takımların **4 üyeden** oluşmasını şart koşuyor; ulaşım-konaklama
desteği de en fazla 4 kişi için (danışman dâhil).

## 2. Takvim

Şartname §8 ve `Takvim.png`. Geçmiş satırlar tarihsel kayıt olarak duruyor.

| Aşama | Tarih |
|---|---|
| Son başvuru / ön değerlendirme sunumu | 12.07.2026 |
| Ön değerlendirme sonuçları | 17.07.2026 |
| Teknik değerlendirme sınavı | 21.07.2026 |
| Finalistlerin açıklanması | 24.07.2026 |
| Kick-off | 27.07.2026 |
| **Yarışma çevrimiçi süreci** | **27.07.2026 – 26.08.2026** |
| **FİNAL — fiziki** | **27–28 Ağustos 2026** |
| TEKNOFEST Şanlıurfa (ödül töreni) | 30 Eylül – 4 Ekim |

Şartnamedeki tabloda final yalnız "AĞUSTOS" yazıyordu; kesin tarih 25 Ağustos
tarihli e-postayla geldi.

## 3. Final etabı — 27–28 Ağustos, Kocaeli

Kaynak: organizasyonun 24 ve 25 Ağustos 2026 tarihli e-postaları. Şartname §11
bunu *"yarışmanın son 24 saati fiziki ortamda gerçekleştirilecektir"* diye
kuruyor.

| | |
|---|---|
| Yer | **Bilişim Vadisi, Kocaeli kampüsü** |
| Tarih | **27–28 Ağustos 2026** |
| Katılım | Takımın **tüm üyeleriyle** fiziken hazır bulunması zorunlu |
| Yurda giriş | 26 Ağustos (KYK yurtlarına giriş 25 Ağustos 08:00'den itibaren açık) |
| Servis | Yarışma günü sabahı yurtlardan Bilişim Vadisi'ne servis var |
| Yurttan çıkış | 30 Ağustos, en geç 17:00 |
| Konaklama | Gebze Yurt Müdürlüğü (erkek) · Nilüfer Hatun Yurt Müdürlüğü (kız) — yalnız Ulaşım-Konaklama Formu'nda **konaklama talebinde bulunanlar** için |

> **Takvim uyarısı.** 24 Ağustos tarihli e-posta yarışma gününü *"27 Ağustos
> Çarşamba"* diye yazıyor, ama 27 Ağustos 2026 **Perşembe**; Çarşamba olan
> 26 Ağustos. Tarih iki ayrı e-postada **27–28 Ağustos** olarak geçtiği için
> tarihi esas aldık, gün adını değil. Çelişki organizasyondan doğrulanmalı.

## 4. Problem tanımı (§3)

Savunma sanayi tesisleri veya saha operasyonları için bir **video analiz ve
karar destek sistemi**. Sistemin karşılaması gerekenler:

- Video girdisi almak ve içeriği analiz etmek
- Olayları, kişileri ve riskli durumları tespit etmek
- **Kritik anları zaman bilgisiyle** belirlemek
- Video içeriğinin kısa ve anlaşılır **Türkçe özetini** üretmek
- Olaylara göre operatöre **aksiyon önerileri** sunmak
- Çıktıları **yapılandırılmış formatta** (JSON) üretmek

Ve ayrıca:

- **Offline ve yerel ortamda** çalışmak
- **Dış API veya kapalı servis bağımlılığı olmamak**
- **vLLM** veya benzeri yerel model servisleme altyapısı kullanmak

### Şartnamenin kendi örneği

```
00:15 — Forklift devrilmesi
00:20 — Yerde hareketsiz kişi
00:35 — Personel toplanması

Sonuç: Olası iş kazası · Yüksek yaralanma riski
Öneriler: sağlık ekibi, güvenlik, kayıt
```

Kapsamı **savunma sanayi tesisi iş güvenliği** olarak daraltma kararımızın
dayanağı bu örnek — bkz. [karar günlüğü](../05-decisions/decision-log.md).

## 5. Temel beklentiler (§4)

Şartname *"yalnızca temel bir video işleme pipeline'ı sunması yeterli
görülmemekte"* diyor. On iki başlık:

| Beklenti | Özü |
|---|---|
| **Çoklu ortam anlama** | Kare bazlı analizle sınırlı kalmamak; sahne bütünlüğü, zamansal ilişkiler, olay akışı |
| **Olay tespiti ve anlamsal yorumlama** | Olayın türü, önemi, olası etkileri. Düşük seviyeli algı ile yüksek seviyeli çıkarım arasında **köprü** |
| **Zamansal farkındalık** | Olayın **başlangıç, gelişim ve sonuç** süreçlerini ayırt etmek; kritik anları vurgulamak |
| **Türkçe üretim ve özetleme** | Gereksiz detaydan arınmış, **operatörün hızlı karar almasını destekleyecek** yapıda, anlam bütünlüğü korunmuş |
| **Aksiyon önerisi ve karar destek** | Yalnız analiz eden değil, **karar destek** sistemi: risk değerlendirmesi + uygulanabilir, bağlamla tutarlı öneriler |
| **Yapılandırılmış ve açıklanabilir çıktı** | JSON zorunlu; olaylar, zaman damgaları, risk seviyeleri ve aksiyonlar **açıkça ayrıştırılmış** |
| **Yerel çalışma ve bağımsızlık** | Harici API / kapalı servis / bulut bağımlılığı **kabul edilmez** |
| **Model servisleme** | vLLM benzeri altyapı; düşük gecikme, kaynak optimizasyonu, gerçek zamana yakın çalışma |
| **Performans ve ölçeklenebilirlik** | Video işleme süresi, inference süresi, bellek/donanım kullanımı, yüksek hacim altında davranış |
| **Ölçümleme ve KPI** | Takım **kendi metriklerini tanımlar**: olay tespit doğruluğu, özet kalitesi, aksiyon doğruluğu, kritik olay yakalama oranı, işlem süresi |
| **Minimum statik yapı** | Dinamik analiz, bağlama göre farklı çıktı, model tabanlı karar. **"Statik, yalnızca kural tabanlı çözümler düşük puanlanacaktır."** |
| **Açık kaynak ve şeffaflık** | Açık kaynak teknolojiler, **tekrar üretilebilirlik**, kurulum/çalıştırma dokümantasyonu |

## 6. Zorunlu çıktı biçimi (§5)

Şartnamenin verdiği mock:

```json
{
  "summary": "Videoda forklift kazası ve yaralanma riski gözlenmiştir.",
  "events": [
    {"time": "00:15", "event": "Forklift devrildi"},
    {"time": "00:20", "event": "Yerde hareketsiz kişi"}
  ],
  "risk": "Yüksek",
  "actions": [
    "Sağlık ekibini çağır",
    "Alanı güvenlik altına al"
  ]
}
```

Bu dört anahtar — `summary` · `events` · `risk` · `actions` — **sözleşmedir.**
Genişletilmiş katmanlarımız çökse bile üretilir; fazlası `detail` altında,
yerine değil. Risk seviyesi değerleri Türkçe kalır
(`"Düşük" | "Orta" | "Yüksek" | "Kritik"`).

## 7. Teslim edilecekler (§6)

- [ ] **Çalışan proje kodu** — agent, mock fonksiyonlar, arayüz, benchmark
      kodu. Kurulum adımları (gereksinimler, çevre değişkenleri) net
- [ ] **Demo videosu** — en fazla **10 dakika**. Seçilen senaryoları ve zorlu
      koşulları (örn. **bağlam değişimi denemesi**) nasıl yönettiğini
      göstermeli; metin tabanlı etkileşim **net** görünmeli
- [ ] **Proje dokümantasyonu** — sekiz zorunlu bölüm:
      ① mimari özeti ve **diyagramı** ② kullanılan agentic framework ve LLM'ler
      ③ implemente edilen senaryolar ve mock fonksiyonlar ④ adım adım
      kurulum/çalıştırma ⑤ karşılaşılan zorluklar ve çözümleri ⑥ eklenen ek
      özellikler ⑦ **ölçümleme sonuçları** ⑧ ölçekleme noktasında gerekli
      ihtiyaçlar
- [ ] **Sunum materyali** — **PDF ve PPTX ikisi birden**

Ayrıca §10 ve §9'dan gelen teslim koşulları:

- [ ] GitHub deposu **açık kaynak**, `BilisimVadisi2026` etiketiyle ve
      **takım adı** eklenerek; "Türkiye Açık Kaynak Platformu" da etiketlenir
- [ ] Depo şunları içermeli: **(1)** bağımlılıkların eksiksiz listesi
      **(2)** çalıştırma adımlarının tamamı **(3)** kullanılan veri setinin
      **herkese açık indirilebilir bağlantısı**
- [ ] **Apache License 2.0** — şartname §9 bunu kabul edilmiş sayıyor
- [ ] Jüriye yapılan sunum GitHub hesabına da yüklenir

Yürütme kontrol listesi: [görev 18 — paketleme](../tasks/18-paketleme.md).

## 8. Değerlendirme kriterleri (§7)

100'lük sistem (§12).

| Ağırlık | Kalem | Alt başlıklar |
|---|---|---|
| **%35** | Fonksiyonellik ve senaryo kapsamı | Senaryoların **uçtan uca** implementasyonu · mock fonksiyonların **ajanın araçları olarak** kullanımı · sistemin kararlı çalışması |
| **%35** | Teknik implementasyon ve mimari | **agent, tools, memory, prompt engineering** · dinamik araç seçimi, bağlam yönetimi, **çok adımlı karar zincirleri**, hata işleme · kod kalitesi, okunabilirlik, modülerlik · mock sistem entegrasyonu |
| **%20** | Otonomi ve zekâ | Niyeti anlama ve **akıl yürütme** · diyalogda **inisiyatif alma ve doğru soruları sorma** · beklenmedik durumlara tepki · doğal ve insansı akış |
| **%10** | Yenilikçilik ve yaratıcılık | Ek senaryolar · beklenti ötesi özellikler · özgün mimari yaklaşımlar · **sunumun ve dokümantasyonun kalitesi** |

**Puanın %70'i ajan mimarisi ve senaryo bütünlüğünde.** Görüntü işleme kalitesi
cetvelde ayrı bir kalem **değil** — algı katmanı ancak yukarıdaki kalemleri
besleyecek kadar iyi olmak zorunda. Kalem kalem eşleştirme:
[evaluation-mapping.md](../03-planning/evaluation-mapping.md).

## 9. Sunum kuralları (§11)

| | |
|---|---|
| **Sunum süresi** | **4 dakika** |
| **Demo videosu (sunumda)** | **1 dakika** |
| Demo gösterimi | **Zorunlu.** Aksaklığa karşı ayrıca demo videosu hazırlanmalı |
| Jüri | İki farklı jüri grubu değerlendirebilir |
| Format | Sunum başlıkları yarışma süresi içinde e-postayla bildirilir; **o başlıklara sadık kalınmalı** |
| Kayıt | Sunumlar kayıt altına alınır (KVKK metni web sitesinde) |

> **İki farklı video var, karıştırma.** §6'nın **≤10 dakikalık** demo videosu
> teslim paketine girer; **1 dakikalık** olan sunum içinde oynatılır. İkisi
> ayrı kurgu.

## 10. Katılım ve açık kaynak kuralları (§9)

Sürece etkisi olan maddeler:

- Kodların, veri kümelerinin ve bileşenlerin GitHub'da **açık kaynak lisansla**
  paylaşımı **zorunlu**; yarışma bitişinde **Apache 2.0** ile Türkiye Açık
  Kaynak Platformu GitHub hesabında paylaşılacağı kabul edilmiş sayılır
- Geliştirmelerin **en az haftalık** olarak sisteme yüklenmesi zorunlu
- Projenin bağımlı olduğu **ücretli hiçbir yazılım** kullanılamaz
- Yarışma süresince **üçüncü taraflardan hizmet/ürün satın alınamaz**
- **Hâlihazırda devam eden veya önceden tamamlanmış projeler sunulamaz;**
  önceki yarışma projelerinin üzerine geliştirme de uygun değil. Başvuru
  dosyası Turnitin'e yüklenir
- Belirtilen tarihte proje yüklenmezse **değerlendirmeye alınmaz**

## 11. Ödüller (§13)

| Derece | Ödül |
|---|---|
| 1. Takım | 120.000 TL |
| 2. Takım | 100.000 TL |
| 3. Takım | 80.000 TL |

Takıma verilir, üyelere eşit bölüştürülür. Dereceye giren takımlar Şanlıurfa'daki
TEKNOFEST ödül törenine katılır.

## 12. Etik kurallar (§16)

Diskalifiyeye kadar giden yaptırımları olan başlıklar: **intihal** (kaynak
göstermeden başkasının kodu/çalışması), **veri sahteciliği ve sonuçların
manipülasyonu**, jüriyi yanıltıcı bilgi sunumu, jüri/hakem/görevlilerle
uygunsuz iletişim, diğer takımların sistemlerine yetkisiz erişim. Gizli
işaretlenen veri ve senaryoların ifşası da yasak.

Bunun kod tabanındaki karşılığı somut: **ölçülmemiş hiçbir şey ölçülmüş gibi
yazılmıyor.** Karar günlüğü ve KPI dosyaları doğrulanmamış satırları açıkça
işaretler.

## 13. Model altyapısı — EVREN

Organizasyon (SSB) 25 Ağustos'ta tüm takımlara **EVREN yapay zekâ çıkarım
servisini** açtı:

- Yarışmaya tahsis edilmiş **8 × NVIDIA H200** üzerinde çalışan **10 model**
  (metin, video/VLM ve gömme modelleri) — **vLLM · BF16, kuantizasyon yok**
- Takım başına **izole Qdrant** vektör veritabanı
- **Kota, senaryo kısıtı ve takım başına model listesi yok;** on modelin
  tamamı bütün takımlara açık
- Organizasyonun tavsiyesi: video isteklerinde **kısa klip** tercih edilmeli ve
  aynı bağlam üzerinden tekrarlı soru sorulmalı (ön ek önbelleği) — sistem tüm
  takımlarca ortak kullanılıyor

Bu, şartnamenin *"yerel ortam, dış API bağımlılığı yok"* koşulunun
organizasyon tarafından sağlanmış hâli: modeller yarışmanın kendi altyapısında,
OpenAI uyumlu bir API'nin arkasında.

**Adresler, model takma adları, ölçülmüş gecikmeler ve tuzaklar:**
[06-references/evren-gateway.md](../06-references/evren-gateway.md).
Anahtarlar `.env` içinde yaşar ve **repoya girmez** — e-postayla gelen LLM
bearer token'ı ile Qdrant anahtarı ayrı ayrı.

## 14. Kaynak dosyalar

Orijinaller repoda **değil**; bu dosya onların yerine geçer.

| Dosya | Ne | Tarih |
|---|---|---|
| `2026 Şartname.pdf` | Teknik şartname, 3. senaryo — 17 bölüm | 26.06.2026 |
| `Takvim.png` · `Hakkında.png` · `Ödüller.png` | Web sitesi ekran görüntüleri | 26.06.2026 |
| `Mailler/` | Final etabı, ulaşım-konaklama ve EVREN duyuruları | 24–25.08.2026 |
| `Test Videoları.docx` | Test video listesi → repoda [`data/sources.tsv`](../../data/sources.tsv) | 22.08.2026 |

> **E-posta ekran görüntüleri repoya konmaz.** İçlerinde takımın LLM bearer
> token'ı, Qdrant anahtarı ve arayüz parolası açık hâlde duruyor. Depo `public`
> yapıldığı için commit'lenmiş bir anahtar geri alınamaz.
