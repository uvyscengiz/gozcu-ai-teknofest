
# ⑤ Karşılaşılan zorluklar ve bu zorluklara getirilen çözümler

**Gözcü** · Takım **FERASET** (`team37`) · Muğla Sıtkı Koçman Üniversitesi

Bu bölüm şartname §6'nın *"karşılaşılan zorluklar ve bu zorluklara
getirilen çözümler"* kalemidir. Kaynak
[`docs/decisions/decision-log.md`](../decisions/decision-log.md) — takımın
gün gün tuttuğu, 3400+ satırlık karar günlüğü. Aşağıdaki her hikâye orada
tarih ve ölçümle kayıtlı; burada seçilen, en somut sayıyı taşıyanlar.

---

## 1. Prompt–şema ayrışması — bu projenin en çok tekrarlanan hatası

**Tek bir arıza sınıfı, beş farklı görevde, hep aynı şekilde.** CLAUDE.md'nin
şimdi adıyla yazdığı kural (*"bir prompt bir enum sayıyorsa değerleri
şemadakiyle birebir aynı olmalı"*) beş ayrı yerde bağımsız olarak kırıldı:

| # | Nerede | Ne oldu |
|---|---|---|
| 1 | Görev 04 | Şemadaki `required` geçersiz kılması unutuldu → strict-JSON 400 → yorumlayıcı her pencerede sessizce `None` döndü, sistem "çalışıyor" göründü, hiçbir şey üretmedi |
| 2 | Görev 06 | Aynı sertleştirme kuralı iki görev dosyasında daha unutulmuştu — kural "hatırlanması gereken" olduğu sürece kırılgan |
| 3 | Görev 12 | Prompt `guven_sinirlari` diyordu, şema alanı `confidence_limits` — raporun dürüstlük bölümü sessizce boş kalıyordu |
| 4 | Görev 14 | Prompt modele `gozlem_duzelt` çağırmasını söylüyordu, gerçek araç adı `correct_observation` — operatör düzeltme akışı hiç tetiklenmiyordu |
| 5 | Görev 06 (`agents/orchestrator.py`) | Yönlendiricinin çağrı kataloğu elle kopyalanmıştı |

**Kalıcı çözüm bir kural değil, bir yapı.** Beşinci tekrardan sonra karar
netleşti: *"unutulabilir bir kural, kural değildir."* Artık her prompt
kataloğu (araç listesi, enum değerleri, alan uzunlukları) doğrudan
Pydantic şemasından **türetiliyor** — `_describe_tool()`,
`FIELD_CATALOGUE = "\n".join(_describe_field(...) for ... in
_SCHEMA["properties"].items())` gibi. Şema sertleştirmesi de tek bir yere,
`Gateway.ask()`'in içine taşındı — hiçbir çağıranın "hatırlaması" gereken
bir adım kalmadı. Bu değişikliği doğrulayan bir regresyon testi de eklendi:
her prompt'un andığı aracın gerçekten şemada var olduğunu kontrol ediyor.

---

## 2. Algı katmanı — donduruldu, sonra gerçek görüntüde kör çıktı

**İlk karar (23 Ağustos): algı donduruluyor.** Zaman baskısı altında
`frames.py`, `detect.py`, `track.py`, `signals.py` sabitlendi; gerekçe
puanın %70'inin ajan mimarisinde olması ve üç günde ikisine birden
odaklanmanın riskli olması.

**25 Ağustos, gerçek görüntüyle ilk koşu: ölçülen sonuç donmuş sistemin
bozuk olduğuydu.** Raf çökmesi klibinde forklift ve operatör kamerada
apaçık görünürken **23 karenin 23'ünde sıfır tespit**. Üç filtre art arda
suçluydu:

1. `YOLO_CLASSES="person,vehicle"` — aynı forklift "vehicle" etiketiyle
   0,25, "forklift" etiketiyle 0,30 güven alıyordu; kelime seçimi eşiğin
   üstüne/altına düşmeyi tek başına belirliyordu.
2. `YOLO_CONFIDENCE=0,35` — gerçek tespitler 0,11–0,34 aralığında
   puanlanıyordu, hepsi eşikte eleniyordu.
3. İzleyici `if box.id is None: continue` — `model.track()` kendi içinde
   düşük güvenli kutuları sessizce eliyordu; izleyici katmanı tespit
   katmanının **üstüne** ikinci bir görünmez filtre koyuyordu.

**Karar: dondurma kaldırıldı** — "bozuk bir sistemi dondurmak onu bozuk
tutar." CLAUDE.md'nin güncel kuralı ("Algı katmanı artık donuk DEĞİL") bu
kararın doğrudan sonucu.

**Sistematik ölçüm — beş düzeltme, dördü kaldı biri reddedildi:**

| Ölçüm | Önce | Sonra |
|---|---:|---:|
| Varlık duyarlılığı | %72,4 | **%99,1** |
| Sayım duyarlılığı | %11,0 | **%93,1** |
| Kaza anındaki kişi sayısı | 0 | **1** |
| Kaza anının hareket-enerji yüzdelik dilimi | %45,2 | **%3,5** |
| Kutu kaybı | %40 | **%0** |

- **D1 — eşik 0,20→0,03.** conf=0,01'de model 20 kişilik bir karede **60
  aday** buluyordu; sorun modelin kapasitesi değil, boru hattının eşiğiydi.
- **D2 — `model.track()` bırakıldı.** Ultralytics'in izleyicisi
  onaylanmış bir iz üretemediğinde `results.boxes`'ı **sessizce**
  değiştiriyordu — bir ayar değil, görünmez bir postprocess. Kendi
  40 satırlık açgözlü IoU eşleştiricimizle değiştirildi.
- **D3 — kare hızı 1→3 fps**, ama önce yanlış bir ölçüm düzeltildi:
  ffmpeg'in `fps` filtresi farklı hızlarda **aynı kaynak kareyi
  seçmiyor** (kare bazlı karşılaştırma sahte bir gerileme gösteriyordu);
  saniye bazlı karşılaştırma doğru sonucu verdi.
- **D4 — triyaj, mutlak değil yerel sapma.** Kaza anı ham enerjide
  347 karenin 45. yüzdelik diliminde kalıyordu çünkü sahne zaten
  yoğundu; 6×8 ızgara + hücre başına z-skoru kaza anını 3,5. yüzdelik
  dilime çekti.
- **D5 — REDDEDİLDİ.** "Makineye kapılan işçi" sinyali (hızlanıp kadraj
  kenarına değmeden kaybolan iz) test edildi ve hiçbir eşikte gürültüden
  ayrışmadı (25 kişi 500+ parça ize bölünüyordu) — ölçüldü ve atıldı.

**Reddedilen/yanlış ölçülen popüler teknikler — tekrar denenmesin diye
kod yorumunda kayıtlı:** daha yüksek çözünürlük (**ters etki** — 896px'te
güven 0,159, 1280px'te sıfır), daha büyük model (**ters etki** — 11n
%89,7, 11m %56,6 sayım duyarlılığı), YOLO26/NMS'siz (yolo11n'i geçemedi).

---

## 3. Yönlendirici hiç "ignore" diyemiyordu — birim hatası iki ondalık basamak

**26 Ağustos, canlı koşuda ölçüldü:** yönlendirici **her pencerede**
`inspect`/`escalate` dedi, yapısal olarak `ignore` diyemiyordu. Dört
sinyal aynı anda bozuktu:

- **Hız birimi iki ondalık basamak kayıktı.** `signals.py` piksel/saniye
  hesaplıyordu (genel medyan 7 px/s), prompt "1,0 üstü yürüyüşten hızlı"
  diyordu — eşik gürültü tabanının çok altındaydı, K3 her pencerede
  tetikleniyordu.
- **Kaybolan izler tespit gürültüsüydü, olay sinyali değildi.** Pencere
  başına 41-121 kaybolan iz — **en kalabalık** pencerelerde en yüksek
  (conf=0,03'te iz parçalanması nesne sayısıyla ölçekleniyor), olayla değil.
- **Kişi sayısı değişimi** her pencerede ±3-9 oynuyordu; K4'ün sabit ±2
  eşiği gürültü tabanının içindeydi.
- Gerçekten ayırt edici tek sinyal **hareket enerjisiydi** (kaza
  penceresinde 0,97, diğerlerinde 0,35-0,62) — ama yönlendiriciye hiç
  verilmiyordu.

**Sonuç:** enerji güvenlik ağı (görü bütçesini `ignore` diyen pencerelere
harcayan mekanizma) **hiç devreye girmemişti**, çünkü yönlendirici zaten
hiç `ignore` demiyordu.

**Çözüm — birim normalize edildi, K2/K4 koşunun kendi medyanına göreceli
hâle getirildi, enerji prompt'a eklendi:**

| Ölçüm | Önce | Sonra |
|---|---:|---:|
| Koşu süresi | 821 sn | **290 sn** |
| Yönlendirici kararı | 10/10 "bak" | 9 bak / **1 ignore** (güvenlik ağı yakaladı) |
| Epizot açılışı | 00:00 (yanlış) | **00:30** (doğru) |
| `events[]` | 12 an, kaza YOK | **42 an, kaza dahil** |
| Saha çağrıları | 18 (12× `zone_unresolved`) | **4, hepsi başarılı** |

---

## 4. Yerel çalışma kısıtı — GPU'suz, paylaşımlı bir gateway'e uyum

Şartnamenin *"offline ve yerel ortamda çalışmalı"* şartı, plan-of-record'ın
ilk hâlinde yerel GPU (RTX 3090/4090 sınıfı donanım) ve kendi vLLM
kurulumu anlamına geliyordu. 22-23 Ağustos'ta gerçek durum netleşti:
**organizasyon bütün modelleri kendi sunucusunda (EVREN) ayağa kaldırıp
OpenAI uyumlu bir gateway veriyor** — takımın kendi GPU'suna ya da vLLM
kurulumuna gerek yok.

Bunun getirdiği asıl zorluk GPU eksikliği değil, **paylaşımlı, uzak bir
kaynağa bağımlılıktı:**

- Her model çağrısı ağ üzerinden gidiyor — kare başına görsel modele
  sormak imkânsız hâle geldi, tetiklemeli yorumlama (§4, mimari belgesi)
  zorunluluk oldu.
- Video-yolu kapasitesi **bütün takımlar arasında paylaşımlı**: dakikada
  ~6,4 tam uzunlukta video isteği (bkz.
  [08-olcekleme.md](08-olcekleme.md)).
- Bozulma modu tasarımın parçası hâline geldi: hiçbir kademe kesintisi
  bir koşuyu düşürmüyor (`Gateway.ask()` istisna atmak yerine
  `degraded=True` dönüyor) — çünkü paylaşımlı bir kaynakta kesinti
  istisnai değil, beklenen bir durum.
- 24 Ağustos'ta yedi model takma adının **hepsi yanlış çıktı** (organizasyon
  belgesinden alınmadan önce tahmindi) ve gateway bilinmeyen bir ada 404
  **vermiyor** — sessizce `llm-fast`'e yönlendiriyor. Yani yanlış adlarla
  sistem "çalışırdı", görü çağrıları bir metin modeline giderdi ve çıktı
  sessizce çöp olurdu. Model kimliklerinin tek dosyada
  (`gozcu/core/config.py`) toplanması bu riski kapatan yapısal çözüm.

---

## 5. Zaman baskısı — dört günlük sprintte iki büyük mimari pivot

**22-23 Ağustos, yarışma sprinti başlarken üç kararla önceki üç haftalık
planın büyük kısmı geçersiz kılındı** ([decision-log](../decisions/decision-log.md)):

1. **LangGraph → düz Python.** Süpervizör döngüsü ~30-60 satır. Gerekçe:
   üç-dört günde yeni bir framework'ü öğrenip hata ayıklamak riskli;
   şartnamenin puanladığı şey framework adı değil *dinamik araç seçimi*,
   *bağlam yönetimi*, *çok adımlı karar zincirleri* — bunlar düz Python'da
   da doğrudan görülüyor.
2. **Canlı RTSP → yüklenen video.** Şartnamenin senaryosu zaten net:
   *"operasyon sahasında bir video sisteme yüklenir."* Test edilmemiş bir
   canlı mod iddia etmek yerine kapsam daraltıldı.
3. **Kapsam: geniş "kaza analizi" → fabrika iş güvenliği.** Danışman
   hocanın "kapsam çok geniş" uyarısının kapanışı; şartnamenin verdiği tek
   somut örnek zaten bir üretim tesisi kazası.

**27 Ağustos'ta ikinci bir pivot: mikro-ajan yeniden tasarımı.** Takımın
kendi mimari önerisi (`Feraset_Guncel_Ajan_Mimarisi.pdf`) sekiz mikro-ajan
sayıyordu; kod tabanıyla karşılaştırıldığında altısı zaten farklı isimlerle
vardı. Ürün sahibi kararları: "ajan" tanımı *model çalıştıran aktör*
olarak sabitlendi (mock araç kaydı ve `benchmark/kpi.py` ajan sayılmıyor),
`router`→`orchestrator` ve `synthesizer`→`anomaly_analyst` adları modül
adı/iz paneli genelinde birleştirildi, ve Risk Analisti'nin tek çağrıda
yaptığı iki iş (değerlendirme + öneri) yeni bir ajana (**Aksiyon
Planlayıcı**) ayrıldı. Bu geçiş sırasında iki plan-metni hatası (plan
metninin şartnameyle çelişen iki cümlesi) canlı olarak yakalanıp
düzeltildi — ayrıntı: [01-mimari-ozeti-ve-diyagramlar.md §3](01-mimari-ozeti-ve-diyagramlar.md#3-ajan-topolojisi-ve-model-kademeleri).

**28 Ağustos, son büyük düzeltme — teslimden bir gün önce bulunan sessiz
bir hata:** operatör belgelerini **yazan** yol ve **okuyan** üç ajan farklı
Qdrant istemcilerine bağlanıyordu (biri `_documents_handle` üzerinden,
üçü `store` üzerinden) — `.env.example`'ın kendi varsayılan (boş) anahtar
değeriyle iki **ayrı, birbirini görmeyen** süreç-içi Qdrant örneği
oluşuyordu. Belge yükleniyor, "gömüldü" diye işaretleniyor, ama
`search_documents` her zaman boş dönüyordu — sessizce. CLAUDE.md'nin
kendi kurulum adımı (`cp .env.example .env`) tam olarak bu bozuk yolu
tetikliyordu. Düzeltme: belge yazma/okuma artık tek bir tutamaktan geçiyor.

---

## 6. Ölçüm kültürü — "ölçüldü" demeden önce ölçmek

Bu belgedeki her sayı gerçek bir koşudan geliyor çünkü ekip birkaç kez
tersini yaşadı: bir sayının "mantıklı görünmesi" onu doğru yapmıyor.
İki örnek, gelecekte tekrar düşülmesin diye:

- **Kare hızı karşılaştırması ilk turda ters çıktı** — 5 fps'in 1 fps'ten
  "daha kötü" göründüğü ölçüm, aslında ffmpeg'in farklı kare hızlarında
  aynı kaynak kareyi seçmemesinden kaynaklanan bir ölçüm hatasıydı
  (bkz. §2). Saniye bazlı karşılaştırmaya geçilince sonuç tersine döndü.
- **`ultrafast` ffmpeg preset'i "hızlı" görünüyordu ama ölçülünce
  kaynaktan bile büyük bir dosya ürettiği görüldü** (0,31 sn ama 3,78 MB) —
  kazanılan saniye base64 yükünde ve token sayısında geri veriliyor.
  `veryfast` hem hızlı hem küçük çıktı.

Kural buradan çıktı ve bu belgenin tamamına uygulandı: **bir sayı
kaynağını göstermeden bu dokümana girmiyor.**
