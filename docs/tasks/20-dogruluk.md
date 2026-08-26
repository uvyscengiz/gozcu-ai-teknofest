# Görev 20 — Doğruluk onarımı (canlı koşunun ortaya çıkardığı beş yalan)

> ## ✅ TAMAMLANDI — 26 Ağustos 2026, `69b68c8`
>
> **Gerçek bir video koşusu, testlerin göremediği beş arıza gösterdi.** Beşi
> de onarıldı: `gozcu/annotate.py` (yeni), `gateway.py`, `loop.py`,
> `supervisor.py`, `synthesizer.py`, `tools/registry.py`, `ui/feed.py`.
> `tests/test_annotate.py` 6, `test_gateway.py` 41, `test_loop.py` 56,
> `test_tools.py` 30, `test_supervisor.py` 53 test ile yeşil; depo genelinde
> **872 test** geçiyor.
>
> **Sonraki göreve başlarken bilmen gerekenler**
> ([notlar](#tamamlanma-notları-gelecek-görevleri-bağlayan)): **arıza metni
> asla prompt'a olay tarifi olarak girmez** (`Episode.summary_source`), ve
> **`inspect` dalı artık görü sonucunu tüketiyor** — yorumlayıcının gördüğü
> şey kararı etkiliyor.

## Bağlam — testler neden görmedi

872 test yeşildi ve sistem yine de dört ayrı yerde olmamış şeyler söylüyordu.
Sebep tek: **testler benim kurduğum dünyayı sınıyordu, sistemin gerçek çağrı
grafiğini değil.** Her katman kendi başına doğru davranıyordu; yanlış olan,
katmanların birbirine ne verdiğiydi.

Arızalar ancak elle etiketli olmayan, gerçek bir fabrika videosu koşturulup
besleme okunduğunda göründü.

## 1. Bütçe tükenmesi "susma" gibi görünüyordu

`Gateway.ask` `finish_reason`'ı **hiç okumuyordu** (`content = msg.content or
""`). Model `max_tokens`'ı akıl yürütme izine harcayıp hiç konuşamadığında
sonuç boş dize oluyor ve her katman "boş yanıt döndürdü" diyordu — gerçek
sebep hiçbir yerde görünmüyordu. `config.SCHEMA_MAX_TOKENS` yorumu bu arızayı
zaten ölçmüştü (128/256/512 → boş dize) ama ayrım yapılmadığı için ölçüm
kullanılamıyordu.

**Onarım:** `Response.finish_reason` ve `Response.truncated`. Boş dönen
şemalı bir çağrı **bir kez** `SCHEMA_WIDEN_FACTOR` katı bütçeyle
tekrarlanıyor. Sonsuza kadar büyütmek asılı bir çağrıyı saatlerce asılı
tutar ve zaman aşımı bunu yakalayamaz.

## 2. Arıza metni fabrikada olmuş bir olay sanıldı

Sentezleyici boş döndü → epizot özeti `"Sentez katmanı boş yanıt döndürdü"`
oldu → `Supervisor.escalate` bu metni prompt'a **`kritik olay:`** diye soktu →
model bunu fabrikada olmuş bir şey sanıp **var olmayan bir bölge** uydurdu
(`Sentez Hattı`), oraya alarm çaldırdı, telsizle operatör aradı, sağlık ekibi
çağırdı. Hiçbiri yaşanmamıştı.

Gerçek bölgeler yalnız: `B-Hattı`, `B-Hattı sevkiyat alanı`, `C-Hattı`,
`C-Hattı montaj alanı`, `Ambar`. Araçlar dürüsttü — hepsi
`zone_unresolved` döndürdü — ve süpervizör okumadı.

**Onarım:** `Episode.summary_source` (`"model" | "fallback"`). Arıza metni
metne bakarak ayırt edilemez; yapısal işaret şart. `escalate()` arıza
metnini prompt'a **sokmuyor**, yerine `NO_DESCRIPTION_NOTE` koyuyor: "ne
olduğunu BİLMİYORSUN, bölge/ekipman adı UYDURMA". Yükseltme iptal
edilmiyor — yönlendiricinin sinyallere dayanan kararı hâlâ gerçek bilgi.

Süpervizöre ayrıca araç sonucunu okuma emri verildi: `zone_unresolved`,
`refused` ve `duplicate` **başarısızlıktır** ve yapılmış gibi anlatılamaz.

## 3. Tek olaya dört kayıt

`open_safety_incident` modelin verdiği `episode_id`'yi olduğu gibi kabul
ediyor ve her çağrıda yeni `record_no` üretiyordu. Koşuda **tek** epizot
vardı; süpervizör `episode_id` 1, 2, 3, 4 ile **dört** kayıt açtı — üçü hiç
var olmayan olaylar, sayıyı model kendi artırmıştı.

**Onarım:** `registry._incident_guard`. Olmayan epizoda kayıt açılmıyor
(`refused`), aynı epizoda ikinci kayıt açılmıyor (ilk kaydın numarası
`duplicate` ile dönüyor). Reddedilen çağrı **deftere yazılmıyor**: olmamış
bir aksiyon defterde görünmemeli ve defterdeki sayı jürinin saydığı şey.

## 4. Görü kademesinin gördüğü şey kararı etkilemiyordu

Yönlendirici **görüntü görmüyor** (`router.SYSTEM_PROMPT`: "Görüntü
görmezsin") — yalnız sinyal özeti. Kuralları K1–K4 hep `inspect` veriyor. Ve
`_routed`'ın `inspect` dalı görüyü çağırıp, parasını ödeyip **sonucu
atıyordu**: `notable_event` yalnız `_forced_sample` içinde okunuyordu.

Ölçülen bedel: 00:05'te yorumlayıcı *"bir forklift başka bir forkliftin
üstünde"* dedi ve hiçbir şey olmadı. Olay ancak 00:40'ta, sinyaller kendi
eşiğini geçtiğinde açıldı — yani kameranın gördüğü şeyin kararla hiçbir
ilgisi yoktu.

**Onarım:** `inspect` + `notable_event` → epizot açılır/kaynaşır. Ön risk
`ESCALATING_RISKS` içindeyse ve epizot **yeni açılıyorsa** operatöre o anda
seslenilir. Kaynaşmada seslenilmiyor (sunumu alarm yağmuruna çevirirdi),
düşük riskte seslenilmiyor (operatörü uyarılara sağırlaştırırdı).

## 5. Saat yalan söylüyordu

Besleme 01:13'ten sonra 00:40 gösteriyordu. Sıra doğruydu (yazma sırası);
damgalar yanlıştı:

- Kaynaşma satırı epizodun **ilk** anını basıyordu → artık kaynaştığı
  pencereyi basıyor. Açılış hâlâ olayın başladığı anı gösteriyor.
- `escalate()` ve `talk()` saati olayın **başına** kuruyordu → 01:16'ya kadar
  süren bir olayın 18 araç çağrısının hepsi 00:40 yazıyordu. Artık `end_ts`,
  yani videonun "şimdi"si.
- Besleme araç sonucunun **akıbetini öne alıyor**: ekranda
  `alarm_id=…, zone_id=None …` yazıyordu ve gerçek cevap
  (`siren_state=zone_unresolved`, siren hiç çalmadı) üç noktanın arkasında
  kalmıştı.

## 6. Algı katmanı görülemiyordu (`gozcu/annotate.py`)

Katmanın kalitesi yalnız **sayı** olarak görülebiliyordu. Bir sayı "neyi
kaçırdı"yı cevaplamıyor.

**Onarım:** kutular, iz kimlikleri, güven ve **pencere başına yönlendirme
kararı** karelere çiziliyor; taban geçemeyen pencere **kırmızı** yazılıyor,
yani hiçbir katmanın bakmadığı anlar bakışta görünüyor. Kaynak depo —
modelden yeniden sorulmuyor, yoksa tanı aracı ikinci bir gerçeklik üretir.
`libx264` ile kodlanıyor (cv2'nin `mp4v`'si tarayıcıda oynamıyor). RAPOR
sekmesinde kendi düğmesiyle.

## Kabul

- [x] Bütçe tükenmesi ile susma ayrı; boş şemalı çağrı geniş bütçeyle tekrar
- [x] Arıza metni prompt'a olay tarifi olarak girmiyor
- [x] Olmayan/yinelenen olay kaydı açılmıyor
- [x] Süpervizör başarısız araç sonucunu başarı gibi anlatmıyor
- [x] `inspect` dalı görü sonucunu tüketiyor
- [x] Kaynaşma ve yükseltme kendi anını taşıyor
- [x] Algı çizimi üretiliyor ve konsolda görünüyor
- [x] `.venv/bin/pytest tests/ -q` → 872 geçiyor
- [x] Konsol açılıyor; çizim düğmesi tarayıcıda doğrulandı

## Tamamlanma notları (gelecek görevleri bağlayan)

- **Bir katmanın arıza metni ASLA başka bir katmana veri olarak geçmez.**
  `Episode.summary_source` bunu yapısal olarak taşıyor. Yeni bir yedek metin
  eklerken onu üreten yol `summary_source="fallback"` işaretlemek zorunda;
  işaretlemezse metin bir sonraki prompt'a olay tarifi olarak girer ve model
  üstüne bir dünya kurar. Bu bir kez oldu ve sistem var olmayan bir bölgeye
  sağlık ekibi çağırdı.
- **`Response.truncated` ile `degraded` ayrı şeyler.** `degraded` bağlantı
  öldü, `truncated` modelin bütçesi bitti. İkincisi KURTARILABİLİR ve
  gateway bir kez geniş bütçeyle yeniden soruyor. Yeni bir katman bunları
  aynı dala koyarsa kurtarılabilir arıza yeniden kalıcı görünür.
- **Yönlendirici görüntü GÖRMÜYOR.** Kararının kalitesini artırmak isteyen
  her değişiklik bunu bilmeli: `inspect` "bilmiyorum, bakın" demek ve o
  dalın sonucunu tüketen tek yer `_routed`. Görüye dayalı yeni bir karar
  eklenecekse yeri orası.
- **Yeni bir saha aracı yazarken başarısızlık durumu ADIYLA dönmeli**
  (`zone_unresolved`, `refused`, `line_unresolved` gibi) ve
  `feed.OUTCOME_KEYS`'e eklenmeli — yoksa besleme onu üç noktanın arkasına
  atar ve ekran aracın çalıştığını iddia eder.
- **`escalate()` ve `talk()` saati `end_ts`'e kuruyor**, `start_ts`'e değil.
  `intervention_card` araçları epizodun aralığına göre eşliyor; `self.ts`'i
  aralığın dışına taşıyan bir değişiklik kartı boşaltır ve "hiçbir araç
  çağrılmadı" dedirtir.
- **Algı çizimi ekranın 13 yuvasının DIŞINDA.** Kodlama koşu başına bir kez
  yapılacak iş; `_refresh`'e bağlanırsa her kalp atışında yeniden kodlanır.
  `tests/test_console.py` bunu "ekrana dokunan işleyici hepsine dokunur"
  değişmeziyle koruyor — yuva sayısıyla değil.
