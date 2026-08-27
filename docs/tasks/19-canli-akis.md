# Görev 19 — Canlı akış konsolu (`gozcu/ui/feed.py`, `gozcu/ui/console.py`)

> ## ✅ TAMAMLANDI — 26 Ağustos 2026, `42dca41`
>
> **Konsol beş sekmeden ikiye indi.** `gozcu/ui/feed.py` (yeni) besleme
> katmanını, `Store.journal()` küresel yazma sırasını, `WindowRecord` algının
> pencere özetini taşıyor. `tests/test_feed.py` 34, `tests/test_console.py`
> 99, `tests/test_store.py` 14 test ile yeşil; depo genelinde **839 test**
> geçiyor. Bu dosyayı yeniden uygulama — aşağısı ne yapıldığının kaydı.
>
> **`gozcu/ui/console.py` ve `tests/test_console.py` 27 Ağustos'ta
> SİLİNDİ** ([Görev 21](21-web-konsolu.md)): Gradio emekliye ayrıldı,
> arayüz `gozcu/ui/server.py` + `gozcu/ui/web/` oldu. Aşağıdaki gövde o
> günün kaydı ve `console.py`'ye yapılan satır atıfları artık ölü — kayıt
> olarak bırakıldı. **Tamamlanma notları güncellendi**: geleceği bağlayan
> her madde yeni taşıyıcıyı gösteriyor.
>
> **Sonraki göreve başlarken bilmen gerekenler**
> ([notlar](#tamamlanma-notları-gelecek-görevleri-bağlayan)): **`Store` artık
> kilitli** ve yeni bir yazma metodu `with self._lock:` altına alınmazsa çift
> `lastrowid` geri gelir. **Beslemeye yeni bir kayıt türü eklemek =
> `build_feed`'e bir dal**; dal eklenmezse tür sessizce görünmez.

## Bağlam — neden

Beş sekme (`Canlı izleme` · `Müdahaleler` · `Nöbetçi` · `Çıktı` · `Ölçüm`)
sistemin yaptığı işi **kaynağına göre** bölüyordu: devirler bir sekmede, araç
çağrıları başkasında, süpervizörün konuşması üçüncüde, epizotlar dördüncüde.
Hepsi aynı on saniyede olup bitmiş şeylerdi ve **hiçbir ekran onları birlikte
göstermiyordu.** Jüri, ajanların birbirine ne devrettiğini görmek için sekme
değiştirmek ve iki tabloyu zaman damgasından elle eşleştirmek zorundaydı.

Şartname §7 puanın %35'ini "teknik implementasyon ve mimari" kalemine
veriyor ve alt başlıklarında **"çok adımlı karar zincirleri"** açıkça yazıyor.
O zincir — `perception → router → interpreter → synthesizer → risk_analyst →
supervisor` — sistemde vardı ama ekranda hiçbir yerde bir arada yoktu.

Yeni eksen **zaman**: `CANLI` olan biteni oluş sırasında akıtıyor, `RAPOR`
teslim edileni ve tam kaydı tutuyor.

## Ne yapıldı

### 1. `Store` kilidi (`c8ceed7`)

Konsolda **iki yazar iş parçacığı** var ve uzun süre görülmedi: boru hattı
(`run_pipeline`, kendi thread'i) ve Gradio olay iş parçacığı
(`nobetci.talk()` — `console.py:973`, `988`; onay kararı; `catch_up` —
`console.py:953`).

Ölçüldü: kilitsiz 400+400 yazmada **aynı `lastrowid` iki kez dağıtıldı** ve
`InterfaceError: bad parameter or other API misuse` atıldı. Kilitle 800
yazma, 800 benzersiz, sıfır hata.

`sqlite3.threadsafety == 3` (serialized) tek bir `execute`i güvenli kılıyor
ama **iki ardışık `execute` + `lastrowid` okumasını kılmıyor.** `RLock`, düz
`Lock` değil: `create_episode` `_insert`i, `open_episode` `_read`i çağırıyor.

`console.py`'nin *"Depoda kilit yok"* docstring'i düzeltildi.

### 2. Sıra defteri (`ddea61f`)

Satır kimlikleri **tablo başına** artıyor ve bir pencerenin bütün üretimi
aynı `ts` civarına düşüyor — `ts` ile sıralamak beraberlik veriyor ve
beraberliği çözecek alan yok. `journal` tablosu (`AUTOINCREMENT`) küresel
yazma sırasını taşıyor.

**Anlık görüntü** (`snapshot`), değişen kayıtlarda: epizot ve aksiyon onayı.
Defter satırını canlı satıra çözmek, koşunun başındaki bir girdiye epizodun
**sonundaki** özetini bastırırdı.

**Gözlem defterlenmiyor** — 3 fps'te on saniyelik pencere ~30 satır eder ve
gözlem bir ajan sınırını geçmiyor. `save_embedding` da defterlenmiyor: bir
gömme ajan olayı değil.

### 3. `WindowRecord` (`0e9f945`)

`loop.run()` pencere başına kişi/kutu/etiket topluyordu ve **yalnız
`trace`e** yazıyordu; ekranda "sistem bu on saniyede ne gördü" sorusunun
cevabı yoktu. Toplama tek yardımcıya (`window_record`) çekildi — iz satırı ve
depo kaydı ondan doğuyor.

`outcome` üç dalı ayırıyor: `routed` · `forced` · `skipped`. "Bakılmadı" ile
"bakıldı, bir şey yoktu" aynı kelimeye düşemez.

### 4. Besleme katmanı (`67110be`)

`gozcu/ui/feed.py` — saf, arayüz bilmiyor. `build_feed(store,
escalated_ids, archived)` defteri `seq` sırasında gezip `FeedEntry`'lere
çeviriyor. Çizim o gün `feed_html`'deydi;
[Görev 21](21-web-konsolu.md)'de tarayıcıya (`js/feed.js`) taşındı ve
`feed_html` silindi — `build_feed`/`FeedEntry` değişmedi.

### 5. İki sekme (`ea22896`, `42dca41`)

`CANLI` tek kolon: video (sabit 260 px) · kontroller · §6 zorlu koşullar ·
operatör kutusu · onay kutusu · **besleme**. `RAPOR`: dört anahtarın JSON'u ·
kök neden · §4 KPI · araç tablosu · devir defteri.

## Kabul

- [x] Konsol tam olarak iki sekme: `CANLI`, `RAPOR`
- [x] Besleme oluş sırasında (`seq`), video damgasıyla
- [x] Her satır üreten ajanı söylüyor; devirler ok olarak
- [x] Araç çağrıları, onaylar, konuşma ve algı aynı akışta
- [x] Müdahale kartı beslemenin içinde, olduğu anda
- [x] `RAPOR` denetim tablolarını koruyor (§7 sayılabilir kayıt)
- [x] `.venv/bin/pytest tests/ -q` → 830 geçiyor
- [x] Konsol gerçekten açılıyor; iki sekme de tarayıcıda doğrulandı

### 6. Kör incelemenin bulduğu üç yalan

Uygulama bittikten ve testler yeşile döndükten SONRA koşan kör bir inceleme,
beslemenin **üç ayrı yerde** olmamış bir şey söylediğini buldu:

1. **Ajan atfı.** `assess_risk` soruşturma araçlarını `Supervisor.escalate`
   İÇİNDE, süpervizör daha ağzını açmadan çağırıyor (`risk.py:249`) ve
   besleme hepsini süpervizöre yazıyordu. `ActionRecord.caller` eklendi:
   `actor` "insan mı makine mi", `caller` **hangi ajan**.
2. **Kendiliğinden rozeti.** Komşuluktan türetiliyordu ve iş parçacıkları
   arasında kırılıyor: `talk()` operatör satırını yazıp saniyelerce modelde
   kalıyor, o boşlukta düşen bir yükseltme sırayı operatör → yükseltme →
   cevap yapıyor ve rozet YANLIŞ satıra takılıyor.
   `DialogueTurn.proactive` artık yazma anında kaydediliyor.
3. **Kartın DEDİĞİ'si.** `talk()` sohbet cevabını açık epizodun `start_ts`'ine
   sabitliyor, yani `ts` anahtarlı arama yükseltmeden ÖNCEKİ bir cevabı
   "ajanın o an dediği" diye basabiliyordu. Artık defter sırasından okunuyor.

Ayrıca **ertelenen pencere** "yönlendiriciye gitti" demeyi bıraktı: kayıt
işleme başlamadan yazılıyor ama erteleme sonradan öğreniliyor, yani besleme
kesintiyi tam da göstermesi gereken demo anında gizliyordu.

## Tamamlanma notları (gelecek görevleri bağlayan)

- **`Store` kilitli.** Yeni bir yazma ya da okuma metodu eklerken gövdeyi
  `with self._lock:` altına al. Unutulursa çift `lastrowid` geri gelir ve
  beslemenin sırası sessizce karışır — arıza testte değil, ekranda çıkar.
- **Beslemeye yeni bir kayıt türü eklemek = `build_feed`'e bir dal.**
  Tanınmayan `source` **susarak** atlanıyor (uydurmaktan iyidir), yani dal
  eklenmezse yeni tablo ekranda hiç görünmez ve hiçbir test kırmızıya
  dönmez. Yeni tablo eklerken `tests/test_feed.py`'ye de bir satır ekle.
- **Yeni bir araç çağrı yeri `caller=` geçmek zorunda.** Varsayılan
  `"supervisor"` ve sessizce yanlış olabilir: `call_tool`'un üç çağıranı var
  (`supervisor.py:327`, `supervisor.py:473`, `risk.py:249`) ve üçüncüsü risk
  analisti.
- **Mutasyona uğrayan HER tablo anlık görüntü taşımak zorunda.**
  `window_record` "değişmez" sayılmıştı; `set_window_outcome` eklenince ilk
  satır geriye dönük düzeltilmiş akıbeti göstermeye başladı ve bunu ancak
  kendi testi yakaladı. Bugün üç tablo mutasyona uğruyor: `episode`,
  `action`, `window_record`. Dördüncüsünü eklerken `snapshot=` de ekle.
- **`update_episode(..., origin=...)` çağıranın sorumluluğu.** Varsayılan
  `"synthesizer"`. Operatörün sözüyle yazan her yol `origin="supervisor"`
  geçmek zorunda, yoksa insan müdahalesi beslemede model çıktısı gibi
  görünür — %20'lik otonomi kriteri tam olarak bu ayrımı soruyor.
- **Ekrana giden her şey TAM durum olarak gidiyor.** O gün bunun taşıyıcısı
  Gradio'nun 13 yuvalı çıktı demetiydi ve kural "yeni yuva `SLOT` ile
  `build()`'e birden eklenir, `SCREEN_SLOTS` artırılır"dı.
  [Görev 21](21-web-konsolu.md)'de yuvalar emekliye ayrıldı; kural taşıyıcı
  değiştirdi ve **sertleşti**: her SSE çerçevesi `_snapshot`'ın tamamını
  taşıyor. Yeni bir alan `_snapshot`'a eklenir — ayrı bir olay türü açmak
  ekranın bir yarısını bayat bırakır ve hata vermez, yani 13 yuvanın
  sessizce yuttuğu arızanın aynısı. `tests/test_server.py::test_every_sse_
  frame_carries_the_full_state_not_a_partial_update` bunu koruyor.
- **Besleme artımlı çiziliyor, yeniden çizilmiyor.** O gün `feed_html`
  bütün beslemeyi her kalp atışında yeniden çiziyordu ve `_feed_slot`
  değişmemiş dizeyi `gr.skip()` ile atlayarak jürinin kaydırmasını
  koruyordu — determinizm bu yüzden ZORUNLUydu. Artık `js/feed.js` yalnız
  yeni girdileri ekliyor; ön koşul, beslemenin eskiden yeniye sıralı olması
  ve her girdinin monoton bir `seq` taşıması. `seq`'i bozan bir değişiklik
  istemcinin "nereye kadar çizdim"ini bozar.
- **Operatör satırının girintisi kaskada bağlı.** O gün inline stildeydi ve
  `margin:.25rem 0` kısayolu kendinden **önceki** `margin-left`i sıfırlıyordu;
  girinti bir kez sessizce kayboldu (tarayıcıda ölçüldü, bütün satırlarda
  `marginLeft: 0px`). Artık `css/styles.css`'te: `.feed-entry`'nin kısayolu
  `.feed-entry.is-operator`'ın girintisinden **önce** gelmek zorunda.
- **`visible_dialogue`, `intervention_card`, `risk_color` ve renkler
  `feed.py`'de — ve TEK evleri orası.** O gün `console.py` onları yeniden
  dışa veriyordu; [Görev 21](21-web-konsolu.md)'de `console.py` silindi ve
  yeniden dışa veren kimse kalmadı. Korunan şey artık ikinci bir TANIMIN
  doğmaması (`tests/test_feed.py::test_the_audit_rule_has_exactly_one_home`
  `gozcu/` ağacını tarıyor). Ters yön o gün dairesel import demekti:
  `console` başında `feed`i çağırıyor, `feed` de yarı kurulmuş
  `console`u isterdi ve konsol her açılışta `ImportError` ile ölürdü.
- **Müdahale kartı epizodun SON defter satırında.** Yükseltilen bir epizot
  birden çok satır taşıyor (açılış, sonra her kaynaşma) ve hepsini
  işaretlemek aynı kartı iki üç kez bastırıyordu.
- **Epizodun anları anlık görüntüde.** Kaynaşma her pencerede yeni an
  ekliyor; canlı okunursa koşunun başındaki bir girdi olayın sonunda
  öğrenilen anları gösterir.
- **Kalp atışı maliyeti ölçüldü, tahmin edilmedi.** 10 dakikalık bir koşunun
  ölçeğinde (60 pencere, 190 defter satırı, 190 besleme girdisi, 77 KB HTML):
  `build_feed` **1,6 ms**, `feed_html` **0,3 ms** — 1000 ms'lik bütçenin
  binde ikisi. Eşzamanlı yükte 1 saniyede 55 besleme çizimi ve 3086 yazma,
  sıfır hata; kilit çekişmesi sorun değil. Besleme uzunlukla doğrusal
  büyüyor, yani çok daha uzun bir videoda önce **HTML boyutu** sıkışır,
  hesaplama değil.
- **Kartın araç eşlemesi epizodun zaman aralığına dayanıyor** ve doğru
  çalışması `Supervisor.escalate`'in `self.ts = episode.start_ts` yapmasına
  bağlı. O satır değişirse kart "hiçbir araç çağrılmadı" der ve yalan söyler.
