# 26 Ağustos canlı koşusu — dürüstlük ve akış onarımları (tasarım)

**Tarih:** 26 Ağustos 2026 · **Durum:** taslak → kör inceleme
**Kanıt:** 26 Ağustos sabahı, forklift devrilme klibiyle yapılan canlı koşu
(konsol beslemesi, teslim JSON'u ve `trace` günlüğü). Bu belgedeki her sayı o
koşudan okunmuştur.

## 0. Sorunun özeti — koşunun beş yalanı

Aynı koşuda beş ayrı arıza zinciri ölçüldü:

1. **"Sentez hattı durdu" diye bir olay yaşanmadı.** Sentezleyicinin arıza
   metni ("Sentez üretilemedi; ham gözlemler kayıtlı") bir sonraki pencerenin
   prompt'una OLAY TARİFİ olarak girdi; model onu fabrikada duran bir "sentez
   hattı"na çevirdi, risk analisti o hattın kesintisine "Kritik" biçti ve
   var olmayan hat için `halt_production_line("sentez-hatti")` önerildi.
2. **Hiçbir siren çalmadı, hiçbir ekip yola çıkmadı.** 6 `dispatch_medical` ve
   6 `site_alarm` çağrısının HEPSİ `zone_unresolved` döndü; 6
   `open_safety_incident` çağrısının hepsi uydurma `episode_id` ile
   `_incident_guard` tarafından reddedildi. (Korumanın kendisi bir ÖNCEKİ
   koşunun ölçümüyle konmuştu — o koşuda uydurma kimlikler kabul edilip dört
   kayıt açılmıştı; bugünkü koşu korumanın öbür yüzünü ölçtü: artık kayıt hiç
   açılmıyor.) Gerçek bir devrilme için sahaya tek bir mock müdahale bile
   ulaşmadı.
3. **Aynı olay 6 kez yükseltildi, 18 saha çağrısı üretildi.** Yönlendirici her
   `escalate` dediğinde süpervizör aynı olaya baştan müdahale etti; 7 risk
   değerlendirmesi, kopya dolu bir `actions[]` listesi ve pencere başına
   30–60 saniyelik gereksiz maliyet doğdu.
4. **Teslim edilen `events[]` kazayı içermiyor.** Liste 00:19'da bitiyor —
   çarpma (≈00:35) ve devrilme (≈00:45) şartnamenin puanladığı anahtardan
   düştü. Sebep: 12'lik `MAX_EPISODE_BEATS` tavanı İLK anları koruyor ve
   epizot 00:00'da (sakin sahnede) açıldığı için tavan sıradan anlarla doldu.
5. **`summary` anahtarı bir arıza kaydı olarak teslim edildi.** Raportör 2048
   token'da tükendi, 4096'lık tek genişletme de tükendi, içerik boş döndü ve
   jürinin okuduğu ilk cümle "Rapor katmanı boş yanıt döndürdü" oldu —
   `risk: "Kritik"`in hemen yanında.

Ek iki küsur: risk analistinin defter ve devir damgaları epizodun BAŞINA
(00:00) yazılıyor (882f3b3 süpervizörü onardı, analisti onarmadı) ve hızlı
kademe pencerelerin ~%60'ında 2048'i tüketip 20–50 saniyelik ikinci denemeye
düşüyor (koşu ≈8× gerçek zaman).

## 0b. Ürün sahibi kararları (26 Ağustos)

Uveys'in bu tasarıma bağlayan üç kararı:

- **Saha araçları mock'tur ve her girdiyi kabul eder.** Bölge/kimlik
  doğrulaması İSTENMİYOR; her aksiyon aracı sabit bir başarı cevabı döndürür.
- **Operatörün cevap vermemesi beklenen davranış.** "Adım adım" kapalıyken
  konsolun beklememesi (`konsol.bekle 0 ms`) tasarımın kendisi; değişmeyecek.
- **Token tavanı + genişletme-tekrarı mekanizması istenmiyor.** (Aşağıda
  5. bölümde gerekçeli karşılığı: tek cömert sigorta, tekrar yok.)

---

## 1. Arıza metni karantinası — yedek özet hiçbir katmana "olay" olarak girmez

**Kök neden.** `Episode.summary_source == "fallback"` ayrımı var ama yalnız
`Supervisor.escalate` okuyor (`NO_DESCRIPTION_NOTE`). Altı tüketici okumuyor:

- `synthesizer._digest` — `DEVAM EDEN OLAY: {previous.summary_tr}` satırı
  arıza metnini bir sonraki pencerenin modeline olay diye anlatıyor.
  Ölçülen zincir: 00:49 yedek özet → 00:59 GERÇEK sentez "sentez üretimi
  durmuş" → 01:09 "sentez hattı durdu".
- `risk.assess_risk` — `OLAY: {episode.summary_tr}` satırı aynı metni
  analiste veriyor (3. değerlendirmenin gerekçesi doğrudan "sentez üretiminin
  durması") ve `search_timeline` arşivi arıza metniyle arıyor (günlükteki
  `embed.ask 43 karakter` satırları o metnin gömülmesi).
- `memory.embed_episode` — yedek özetli bir epizot kapanırsa arıza metni
  kalıcı arşive gömülür ve gelecek koşuların emsal aramasını zehirler.
- `Supervisor.talk` — her diyalog turuna eklenen `Açık olay: episode {id} —
  {summary_tr}` hatırlatması arıza metnini, "sentez hattı"nı bir kez uydurmuş
  olan katmana olay diye yeniden anlatır.
- `reporter._prompt` — OLAY ZİNCİRİ bölümü her epizodun `summary_tr`'ını
  kanıt dosyasına koyar; uydurma, §1 uygulanmış hâliyle bile teslim edilen
  kök neden raporunda yeniden doğabilirdi.
- `report._events` — anı olmayan epizotta `summary_tr` olduğu gibi
  şartnamenin `events[]` anahtarına düşer: arıza metninin jüri anahtarına
  ulaşan tek doğrudan yolu.

**Tasarım.**

- `_digest`: `previous.summary_source == "fallback"` iken satır şu sabite
  döner: `DEVAM EDEN OLAY: (tarif üretilemedi — önceki pencerenin sentezi
  arızalandı; olayı aşağıdaki gözlemlerden yeniden kur)`. Arıza metninin
  kendisi prompt'a girmez.
- `assess_risk`: aynı bayrakta `OLAY:` satırı `OLAY: (olay tarifi
  üretilemedi; aşağıdaki ham anlara dayan)` olur ve prompt'a epizodun
  `beats` listesi eklenir (anlar yorumlayıcının GERÇEK çıktısı, arıza değil).
  `search_timeline` sorgusu özet yerine anların metninden kurulur; an da
  yoksa arama atlanır (boş sorgu emsal getirmez, arıza metni yanlış emsal
  getirir).
- `embed_episode`: `summary_source == "fallback"` olan epizot gömülmez
  (`False` döner, mevcut "vektörü yok, sonra yeniden gömülebilir"
  sözleşmesinin aynısı).
- `Supervisor.talk`: açık olay yedek özetliyse hatırlatma metni özet yerine
  `(tarif üretilemedi — sentez arızası)` der; kimlik ve varlık bilgisi kalır.
- `reporter._prompt`: yedek özetli epizot satırı `summary_tr` yerine
  `(tarif üretilemedi — sentez arızası; ham anlar epizot kaydında)` yazar ve
  varsa epizodun anları satırın altına eklenir — rapor gerçek gözleme dayanır,
  arıza metnine değil.
- `report._events`: anı olmayan VE yedek özetli epizot için olay metni sabit
  `Olay tespit edildi; tarifi üretilemedi (sentez arızası).` olur — jüri
  anahtarına arıza metni de uydurma da girmez.
- **Yedek, model özetinin üstüne yazmaz (kaynaşma koruması).** `synthesize`
  güncelleme dalı bugün geçerli pencerenin sentezini koşulsuz yazıyor: son
  penceresi arızalanan bir epizot, ömrü boyunca taşıdığı model özetini
  kapanış anında bir arıza metnine kaybeder — ve yukarıdaki gömme koruması o
  epizodu arşivden tamamen düşürür. Kural: geçerli sentez `fallback` ve
  epizodun mevcut kaydı `model` ise `summary_tr` ve `summary_source`
  DEĞİŞMEZ; `end_ts`, an kaynaşması, faz ve kapanış durumu normal işler.
  İyileşme yönü aynen kalır: model sentezi her zaman yazar.

**Neden düzeltme değil karantina:** yedek özet mekanizması doğru — pencere
kaybolmuyor, arıza türü ayırt ediliyor. Yanlış olan tek şey, arıza metninin
`summary_tr` alanında dolaşıp ayrımı bilmeyen tüketicilere ulaşması. Ayrımı
her tüketiciye öğretmek, metni değiştirmekten daha sağlam: `summary_source`
zaten yapısal olarak taşınıyor.

## 2. Saha araçları: her çağrı başarır (ürün sahibi kararı)

**Kök neden.** Geçerli bölge adları yalnız fikstürde yaşıyor (`B-Hattı`,
`C-Hattı`, sevkiyat, montaj, Ambar) ve hiçbir prompt onları modele
söylemiyor; model tek yapabildiğini yapıp gördüğünü tarif ediyor ("kırmızı
kamyon önü", "362"). `_incident_guard` da depoda olmayan `episode_id`'yi
reddediyor ve `escalate()`'in sistem mesajı gerçek kimliği hiç söylemiyor
(`talk()` söylüyor — asimetri).

**Karar (Uveys):** bunlar mock; doğrulama kaldırılır, her aksiyon sabit
başarıyla döner. Ajanın işi müdahaleyi BAŞLATMAK; mock'un işi başarıyı
oynamak.

**Tasarım.**

- `field_systems.dispatch_medical`: bölge çözülürse fikstürdeki ekip/ETA
  kullanılmaya devam eder (bedava gerçekçilik); çözülmezse sabit varsayılan
  ekip ve ETA ile döner. `state` her iki dalda da `"dispatched"`;
  `zone_unresolved` durumu silinir.
- `field_systems.site_alarm`: `siren_state` her zaman `"active"`; bölge
  çözülmezse `affected_zone` verilen adı yankılar. `zone_unresolved` silinir.
- `field_systems.halt_production_line`: `line_unresolved` ve
  `zone_has_no_line` durumları silinir; çözülmeyen `line_id` olduğu gibi
  yankılanır. İki fazlı onay makinesi (`awaiting_approval`/`halted`) ve
  `NEEDS_APPROVAL` mekanizması AYNEN kalır — kapı zaten varsayılanda boş,
  bu tasarım ona dokunmuyor.
- `registry._incident_guard`: `NO_SUCH_EPISODE` reddi silinir — uydurma
  kimlik de kabul edilir. **Yineleme kısa devresi kalır** (aynı epizoda
  ikinci kayıt ilk `record_no`'yu `duplicate: True` ile döndürür): bu bir
  ret değil başarı biçimli bir cevap. Dürüst sınırı yazılsın: kısa devre
  `episode_id` üzerinden anahtarlanır, yani mükerrer kaydı tek başına
  engelleyen o değil — modelin doğru kimliği kullanması (aşağıdaki satır)
  ve §3'ün gelişme kipidir; kısa devre yalnız kalan artığı süpürür.
- `supervisor.escalate`: sistem mesajına `Olay kimliği (episode_id): {id}.`
  satırı eklenir — `talk()` ile asimetri kapanır ve İSG kaydı gerçek epizodu
  referanslar. (Mock her kimliği kabul edecek; doğru kimliği vermek defteri
  dürüst tutmanın ucuz yolu.)
- `supervisor.ESCALATION_INSTRUCTION`: `zone_unresolved` paragrafı ölü metne
  dönüşüyor, silinir. "ARAÇ SONUCUNU OKU; yalnız gerçekten yapılanı rapor
  et" ilkesi genel biçimiyle kalır (`refused`/`duplicate` hâlâ mümkün).
- Okuma araçları (`query_shift_personnel`, `query_equipment_history`)
  DEĞİŞMEZ: onlar başarı/başarısızlık değil VERİ döndürüyor; bilinmeyen
  bölgeye boş personel listesi doğru cevap.

**Elenen alternatif — bölge adlarını şemaya `enum` olarak koymak.**
`_describe_tool` enum değerlerini prompta zaten türetiyor; fikstür bölgeleri
`_TOOL_SPECS`'e enum girse model yalnız geçerli ad seçebilirdi. Reddedildi:
katı şema modeli bölgeyi BİLMEDİĞİNDE de geçerli bir ad seçmeye zorlar —
"kırmızı kamyon önü" yerine rastgele ama geçerli görünen bir "B-Hattı"
yazılır, yani serbest metnin dürüstlüğü (ajan neyi bilmiyordu, defterden
okunuyor) uydurma-ama-geçerli bir sevke dönüşür. Mock'un her adı kabul
etmesi hem müdahaleyi hem dürüstlüğü korur.

**Kayıt yükümlülüğü:** bölge çözümü reddi bir zamanlar bilinçli bir karardı
("serbest metne siren çaldırmak olmayan bir bölge uydurmaktır" —
`field_systems` docstring'i). Bu kararın geri alınışı ve gerekçesi
(`mock'ta müdahalenin engellenmesi uydurma bölge adından pahalı`)
`docs/05-decisions/decision-log.md`'ye işlenir.

## 3. Yükseltme fırtınası: olay başına BİR tam müdahale, gerisi gelişme bildirimi

**Kök neden.** `DecisionLoop._routed`'ın `escalate` dalı aynı açık epizot
için her seferinde `LoopEvent` üretiyor (sönümleme yalnız `inspect` dalında
var) ve `ESCALATION_INSTRUCTION` her yükseltmede "ÖNCE saha araçlarını
çağır" diye emrediyor. Model kendi geçmişinde 15 başarılı çağrı dururken
tekrar çağırıyor, çünkü talimat açıkça öyle diyor. Her yükseltme ayrıca
`assess_risk`'i baştan koşturuyor (7 değerlendirme → şişkin `actions[]`).

**Tasarım — süpervizör tarafında iki kip; döngü değişmez.**

- `Supervisor` epizot başına yükseltme sayısını tutar
  (`self._escalated: set[int]`).
- **İlk yükseltme** bugünkü davranış: `assess_risk` + araç turu + duyuru.
- **Sonraki yükseltmeler** "gelişme" kipi:
  - `assess_risk` YENİDEN KOŞMAZ; epizodun depodaki son değerlendirmesi
    okunur (`store.risks()`). Yoksa (teorik dal) ilk-yükseltme kipine düşer.
  - Talimat `UPDATE_INSTRUCTION` olur: "Bu olay için saha araçları ZATEN
    çağrıldı ve defterde duruyor; aynı aracı aynı gerekçeyle TEKRAR ÇAĞIRMA.
    Gelişmeyi 1–2 cümleyle bildir. Yalnız YENİ doğan bir ihtiyaç için yeni
    araç çağırabilirsin."

**Neden döngüde bastırmak değil:** ilk düşünülen tasarım (aynı epizot için
ikinci `yield`'i bastırmak, risk yükselmedikçe) bu koşuda kazayı operatörden
SAKLARDI — ilk yükseltme 00:19'da, yakın-temas anında geliyor; çarpma ve
devrilme sonraki yükseltmelerde. Sentezleyicinin ön riski koşu boyunca
Orta/Yüksek bandında kaldı, yani "risk yükselince yeniden seslen" kuralı hiç
tetiklenmezdi. Operatör her kritik gelişmeyi duymalı; duymaması gereken şey
aynı ambulansın altıncı kez çağrılması. Karar bu yüzden davranış katmanında:
seslenme sıklığı korunur, mükerrer müdahale ve mükerrer analiz kesilir.

**Ölçülü beklenti:** bu koşuda 18 saha çağrısı → ~3; 7 risk değerlendirmesi
→ 2 — ilk yükseltme + kapanış (`_on_close`'un koşulsuz `assess_risk`'i;
epizot hiç kapanmazsa koşu sonu süpürmesi, ki o zaten değerlendirilmişleri
ATLAR, yenisini eklemez). `nöbetçi.duyur` süresi gelişme kipinde tek model
çağrısına iner (7–42 s → ~5–15 s). `actions[]` kopyaları kaynağında kurur
(`build_output`'a ayrı tekilleştirme eklenmez — YAGNI).

## 4. Anlar (`beats`): baş+son tutma, tavan 12 → 48

**Kök neden.** `_merge_beats` taşımada `merged[:MAX_EPISODE_BEATS]` ile İLK
12 anı tutuyor. Gerekçesi ("olayın başlangıcı en pahalı bilgidir") epizot
erken açıldığında tersine dönüyor: 00:00'da açılan epizotta tavan park
hâlindeki kamyonla doldu ve kaza anları (`00:35` çarpma, `00:45` devrilme)
şartnamenin `events[]` anahtarından düştü.

**Tasarım.**

- `MAX_EPISODE_BEATS` 12 → **48**. Gerekçe: pencere başına ~6 an üretiliyor
  (ölçüldü); 48, 98 saniyelik bu koşunun TAMAMINI tutar ve 10 dakikalık en
  kötü senaryoda (60 pencere × 6 ≈ 360 an) hâlâ gerekli bir tavandır.
- Taşma kuralı: **ilk 24 + son 24** (`merged[:HALF] + merged[-HALF:]` —
  kural yalnız `len > 48`'te tetiklendiği için iki dilim çakışamaz; ek bir
  ayıklama dalı YAZILMAZ, ölü olur). Baş, olayın nasıl başladığını korur; son,
  epizot NE KADAR uzarsa uzasın en güncel gelişmenin — yani kazanın —
  listede olmasını YAPISAL olarak garanti eder. Yalnız-baş kuralının
  ölçülen arızası tam olarak bu garantinin yokluğuydu.
- `report._events` değişmez: an başına bir satır üretmeye devam eder; 48
  satırlık bir `events[]` gürültülü ama eksiksizdir ve şartname eksikliği
  cezalandırır, uzunluğu değil.

**Bilinçli kapsam dışı:** epizodun 00:00'da (sakin sahnede) hiç açılmaması —
yani `notable_event` eşiğinin sıkılaştırılması — algı/yorum kalitesi işidir;
kod dondurmadan saatler önce ölçüsüz prompt ayarı yapılmaz. Bu tasarım erken
açılmanın İKİ zararını (an kaybı, 00:00 damgalı müdahale kartı) başka yoldan
kapatıyor; eşik işi decision-log'a "ölçülecek borç" olarak yazılır.

## 5. Token politikası: tek cömert sigorta; genişletme-tekrarı silinir

**Uveys'in itirazı:** "neden hem sınırlıyoruz hem tekrar deniyoruz?"

**Tarihçe (ölçümleriyle):** tavansız şemalı çağrı kaçak kod çözümüne girip
asılıyor — canlıda 1106 saniye ölçüldü ve httpx zaman aşımı bunu YAKALAMIYOR
(bağlantı ölü değil, yavaş). Tavan bu yüzden kondu; 2048 dar gelince de
(akıl yürütme izi bütçeyi yiyor) genişletme-tekrarı eklendi. Sonuç iki
mekanizmanın en kötü bileşimi: pencerelerin ~%60'ında ilk deneme boşa
gidiyor (14–31 s), tekrar bir o kadar sürüyor ve raportörde 4096 da yetmeyip
`summary` arıza kaydına düşüyor.

**Tasarım.**

- `SCHEMA_MAX_TOKENS` 2048 → **8192**. Bu bir bütçe değil SİGORTA:
  `max_tokens` tükenmedikçe maliyeti sıfırdır. 4096 bu koşuda her sentez
  çağrısına yetti; 8192 iki kat pay bırakır.
- Gateway'deki genişletme-tekrarı dalı (`finish == "length"` → `widened`)
  ve `SCHEMA_WIDEN_FACTOR` **silinir**. Tek deneme, tek sigorta.
- Raportör çağrısı `max_tokens=16384` geçer — `generate_root_cause_report`
  İÇİNDE, `run.py`'da değil: böylece boru hattı VE süpervizörün
  `GENERATE_ROOT_CAUSE_REPORT` iç aracı, iki çağıran da aynı tavanı alır.
  Koşu başına bir kez çalışır, girdisi en büyük prompt (epizotlar + riskler +
  defter + diyalog) ve 4096'yı aştığı ölçüldü. En kötü hâl maliyeti tek
  çağrıya sınırlı.
- Tavanı TAMAMEN kaldırmak reddedildi: 1106 saniyelik asılma ölçülmüş bir
  arıza ve zaman aşımı onu yakalayamıyor. Sigortasız sadelik, donan bir
  demo demek.

**Beklenen etki:** pencere başına 20–50 saniyelik ikinci deneme yok olur —
koşunun ~8× gerçek zaman katsayısının en büyük tek kalemi. Raportör boş
dönmez, `summary` gerçek rapor olur (bkz. §7).

## 6. Saat hâlâ bir yerde yalan söylüyor: risk analisti ve müdahale kartı

**Kök neden A.** `assess_risk` devir kaydını ve okuma araçlarının defter
damgasını `episode.start_ts` ile yazıyor. Epizot 00:00'da başladığı için
yedi değerlendirmenin yedisi beslemede "00:00 ⚖️ risk_analyst" görünüyor —
01:38'de yapılmış analiz dâhil. 882f3b3 aynı arızayı süpervizörde onardı,
analistte kaldı.

**Kök neden B.** Beslemenin "⚠ MÜDAHALE ANI" kartı `episode.event_ts`
kullanıyor (ilk anın damgası). Erken açılan epizotta ilk an 00:00 ve kart
"ajan 00:00'da müdahale ederdi" diyor — oysa müdahale (yükseltme) 00:19'da
oldu. `event_ts` epizot SATIRLARI için doğru; müdahale KARTI için doğru
sayı yükseltmenin kendi anıdır.

**Kök neden C (kör incelemenin bulgusu).** Beslemedeki "00:00 ⚖️
risk_analyst" satırının İKİNCİ kaynağı feed'in kendisi: `RiskAssessment`
hiç zaman damgası TAŞIMADIĞI için feed risk satırını `episode.event_ts` ile
damgalıyor. Yalnız A'yı onarmak besleme içinde yeni bir tutarsızlık doğurur:
analistin defter satırları 01:38, hemen yanındaki risk satırı 00:00.

**Tasarım.**

- `assess_risk` içindeki iki damga (`save_handoff` ve `_run_tool_calls`'a
  giden `ts`) `episode.end_ts or episode.start_ts` olur — videonun
  "şimdi"si; `Supervisor.escalate`'in 882f3b3'te geçtiği kuralın aynısı.
- `RiskAssessment` bir `ts: float = 0.0` alanı kazanır; `assess_risk` onu
  aynı "şimdi" değeriyle doldurur. Feed'in risk satırı `episode.event_ts`
  yerine `assessment.ts`'i basar (0.0 ise eski davranışa düşer — arşivden
  tohumlanan eski kayıtlar damgasız). Devir, defter ve besleme böylece tek
  saati söyler.
- Müdahale kartı yükseltme anının damgasını basar. Yükseltme anında
  epizodun `end_ts`'i son kaynaşan pencerenin sonu, yani tam o an; kartın
  render'ına giden değer `event_ts` yerine bu olur. Epizot satırlarının
  `event_ts` kullanımı DEĞİŞMEZ (feed.py'nin gerekçesi orada geçerli).

## 7. Raportör düşerse `summary` arıza kaydı olmasın

**Kök neden.** `run_pipeline` `summary = root_cause.what_happened`'i koşulsuz
kullanıyor; rapor yedeğe düştüğünde şartnamenin ilk cümlesi arıza metni
oluyor. §5 bu düşüşü büyük ölçüde önlüyor ama sigortanın arkasında da dürüst
bir cümle durmalı.

**Tasarım.**

- `RootCauseReport` sentezleyicideki desenin aynısını kazanır:
  `PrivateAttr _source` + `report_source` özelliği (`"model"` /
  `"fallback"`). Metin karşılaştırmasıyla ayırt etme yasağı burada da
  geçerli — o yol bir kez yanılttı.
- `run_pipeline`: rapor `fallback` ise `summary` için sırayla —
  son epizodun `summary_tr`'ı (yalnız `summary_source == "model"` ise),
  o da yoksa raporun arıza metni (bugünkü davranış; dürüst son çare).
- `detail.root_cause_report` her iki dalda da aynen teslim edilir; değişen
  yalnız dört anahtardan `summary`'nin seçimi.

## 8. Kapsam dışı (bilinçli)

- **Operatör beklemesi** — ürün sahibi kararı: demo kipinde beklenmiyor.
- **`notable_event` / epizot açma eşiği** — ölçüm ister; §4'e not düşüldü.
- **Algı katmanı kalitesi** — bu koşuda taban her pencerede geçti; dokunulmaz.
- **`build_output` aksiyon tekilleştirmesi** — §3 kaynağı kuruttuğu için
  gereksiz.

## 9. Test stratejisi (TDD — önce kırmızı)

Her madde kendi başarısız testiyle başlar; mevcut testlerden
`zone_unresolved` / `NO_SUCH_EPISODE` / genişletme-tekrarı bekleyenler bu
tasarımla bilinçli olarak kırılır ve davranışın yeni sözleşmesine çevrilir.

| Madde | Kırmızı test |
|---|---|
| §1 | Yedek özetli epizotla `_digest` çıktısında arıza metni GEÇMEZ; `assess_risk` prompt'unda geçmez ve arama anlardan kurulur; `embed_episode` `False` döner; `talk` hatırlatması ve `reporter._prompt` satırı arıza metni taşımaz; anı olmayan yedek epizotta `events[]` metni sabit nötr cümle; yedek sentez, `model` kaydının özetini/kaynağını EZMEZ (kaynaşma koruması) |
| §2 | Bilinmeyen bölgeyle `dispatch_medical` → `state="dispatched"`; `site_alarm` → `siren_state="active"`; bilinmeyen `line_id` ile `halt_production_line` → onay makinesi normal işler (`line_unresolved`/`zone_has_no_line` yok); uydurma `episode_id` → kayıt açılır; aynı epizoda ikinci kayıt → `duplicate` + ilk `record_no`; `escalate` mesajında gerçek `episode_id` |
| §3 | Aynı epizoda ikinci `escalate` çağrısı `assess_risk`'i ÇAĞIRMAZ ve mesaja `UPDATE_INSTRUCTION` girer; ilk çağrı bugünkü davranışını korur |
| §4 | 60 anlık kaynaşmada son pencerenin anları listede; ilk anlar da listede; tavan 48 |
| §5 | Gateway `finish="length"`te İKİNCİ deneme yapmaz; şemalı çağrının varsayılan tavanı 8192; raportör çağrısı 16384 geçer |
| §6 | `assess_risk` devri ve defter satırları `end_ts` damgalı; `RiskAssessment.ts` dolu ve feed risk satırı onu basıyor; kartın damgası yükseltme anı |
| §7 | Yedek rapor + model özetli epizot → `summary` epizot özeti; ikisi de yedek → arıza metni |

Bilerek kırılacak mevcut testler (davranışın yeni sözleşmesine çevrilir):
`tests/test_tools.py`'daki `zone_unresolved` / `line_unresolved` /
`zone_has_no_line` beklentileri, `NO_SUCH_EPISODE` ret testi,
gateway genişletme-tekrarı testleri, `tests/test_risk.py`'daki
`record.ts == e.start_ts` beklentisi ve `tests/test_feed.py`'daki
`zone_unresolved` ayrıntı beklentisi.

Uçtan uca doğrulama: `uv run pytest tests/ -v` ve aynı klip ile bir canlı
koşu — başarı ölçütü: sıfır `zone_unresolved`, olay başına ≤2 risk
değerlendirmesi, `events[]` içinde 00:35/00:45 anları, `summary` gerçek
rapor, koşu süresinde pencere başına genişletme-tekrarı kalemi yok.

## 10. Belgeleme

- `docs/05-decisions/decision-log.md`: bölge doğrulamasının kaldırılışı
  (§2), token politikası değişimi (§5), yükseltme kipleri (§3) — üçü de
  ölçümleriyle.
- İlgili görev dosyaları (`docs/tasks/`) ve README durum tablosu işin
  ilerleyişiyle güncellenir.
