# Görev 19 — Canlı akış konsolu (`gozcu/ui/feed.py`, `gozcu/ui/console.py`)

> ## ✅ TAMAMLANDI — 26 Ağustos 2026, `42dca41`
>
> **Konsol beş sekmeden ikiye indi.** `gozcu/ui/feed.py` (yeni) besleme
> katmanını, `Store.journal()` küresel yazma sırasını, `WindowRecord` algının
> pencere özetini taşıyor. `tests/test_feed.py` 30, `tests/test_console.py`
> 98, `tests/test_store.py` 14 test ile yeşil; depo genelinde **830 test**
> geçiyor. Bu dosyayı yeniden uygulama — aşağısı ne yapıldığının kaydı.
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

`gozcu/ui/feed.py` — saf, Gradio bilmiyor. `build_feed(store,
escalated_ids, archived)` defteri `seq` sırasında gezip `FeedEntry`'lere
çeviriyor; `feed_html` çiziyor.

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

## Tamamlanma notları (gelecek görevleri bağlayan)

- **`Store` kilitli.** Yeni bir yazma ya da okuma metodu eklerken gövdeyi
  `with self._lock:` altına al. Unutulursa çift `lastrowid` geri gelir ve
  beslemenin sırası sessizce karışır — arıza testte değil, ekranda çıkar.
- **Beslemeye yeni bir kayıt türü eklemek = `build_feed`'e bir dal.**
  Tanınmayan `source` **susarak** atlanıyor (uydurmaktan iyidir), yani dal
  eklenmezse yeni tablo ekranda hiç görünmez ve hiçbir test kırmızıya
  dönmez. Yeni tablo eklerken `tests/test_feed.py`'ye de bir satır ekle.
- **`update_episode(..., origin=...)` çağıranın sorumluluğu.** Varsayılan
  `"synthesizer"`. Operatörün sözüyle yazan her yol `origin="supervisor"`
  geçmek zorunda, yoksa insan müdahalesi beslemede model çıktısı gibi
  görünür — %20'lik otonomi kriteri tam olarak bu ayrımı soruyor.
- **`SLOT` ile `build()`'deki `screen` listesi aynı sırayı paylaşıyor.** Yeni
  yuva **ikisine birden** eklenecek ve `SCREEN_SLOTS` artırılacak. Testler
  yuvayı **adıyla** okuyor; sayıyla indeksleyen bir iddia araya bileşen
  girdiğinde sessizce başka bir yuvayı sınamaya başlar (26 Ağustos'ta 15 →
  13 indi ve iki test bu yüzden yanlış yuvayı okuyordu).
- **`feed_html` deterministik olmak ZORUNDA.** `_feed_slot` dizeyi bir
  öncekiyle karşılaştırıp değişmemişse `gr.skip()` döndürüyor. Çizim anı ya
  da duvar saati dizeye girerse atlama hiç çalışmaz ve jürinin geçmişi
  okumak için yaptığı her kaydırma saniyede bir bozulur.
- **Inline stilde kısayol sırası önemli.** `margin:.25rem 0` kendinden
  **önceki** `margin-left`i sıfırlıyor; operatör girintisi bu yüzden bir kez
  sessizce kayboldu (tarayıcıda ölçüldü, bütün satırlarda `marginLeft: 0px`).
  Ayırt edici stil dize sonunda duruyor.
- **`visible_dialogue`, `intervention_card`, `risk_color` ve renkler
  `feed.py`'de.** `console.py` onları yeniden dışa veriyor. Ters yön dairesel
  import demek: `console` başında `feed`i çağırıyor, `feed` de yarı kurulmuş
  `console`u isterdi ve konsol her açılışta `ImportError` ile ölürdü.
- **Müdahale kartı epizodun SON defter satırında.** Yükseltilen bir epizot
  birden çok satır taşıyor (açılış, sonra her kaynaşma) ve hepsini
  işaretlemek aynı kartı iki üç kez bastırıyordu.
- **Epizodun anları anlık görüntüde.** Kaynaşma her pencerede yeni an
  ekliyor; canlı okunursa koşunun başındaki bir girdi olayın sonunda
  öğrenilen anları gösterir.
- **Kartın araç eşlemesi epizodun zaman aralığına dayanıyor** ve doğru
  çalışması `Supervisor.escalate`'in `self.ts = episode.start_ts` yapmasına
  bağlı. O satır değişirse kart "hiçbir araç çağrılmadı" der ve yalan söyler.
