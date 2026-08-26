# Web konsolu — Gradio'nun yerine özel arayüz (tasarım)

**Tarih:** 26 Ağustos 2026 · **Durum:** taslak → kör inceleme (3. tur)
**Kaynak:** `/Users/uveyscengiz/Downloads/ASDASD` altındaki görsel PoC
(FERÂSET arayüzü) ve depodaki `gozcu/ui/console.py`.

> **İncelemeciye not — bu belgedeki tarihlere dayanarak kapsam kararı
> verme.** Depodaki takvim satırları (`CLAUDE.md`, `docs/tasks/README.md`,
> `docs/00-overview/sartname.md`) **bayat**: 26 Ağustos 23:59 yazıyorlar,
> teslim tarihi kaydı. Doğru tarih bu belgenin sahibinde; bir bulgu "buna
> vakit yetmez" diyorsa dayanağı yanlış.

> **PoC'den hiçbir kod alınmıyor.** O paket bir görsel referans: kendi mock
> analiz katmanı, kendi şeması ve kendi uydurma metrikleri var. Alınan şey
> düzen ve tema; alınmayan şey veri modeli. Bu ayrım bu belgenin yarısını
> oluşturuyor, çünkü PoC'nin gösterdiği şeylerin bir kısmının bu sistemde
> **karşılığı yok** ve olduğu gibi taşınırsa arayüz olmayan bir yeteneği
> iddia eder.

## 0. Sorunun özeti

Gradio üç somut şeyi yapamıyor ve üçü de doğrudan puanlanan kalemlerde:

1. **Ekran, sistemin yaptığı işi anlatamıyor.** `SCREEN_SLOTS = 13`
   (`console.py:184`) — her olay işleyicisi tam 13 değer döndürmek zorunda ve
   eksik bir çıktı **hata vermiyor**, o bileşen sessizce tazelenmiyor
   (`console.py:180`). Bu protokol yüzünden ekran her tazelemede bütünüyle
   yeniden çiziliyor; kısmi güncelleme yok, video üzerine katman yok.
2. **Video ile karar aynı yüzeyde değil.** `gr.Video` bir oynatıcı; üzerine
   çerçeve çizilemiyor, zaman çizelgesine olay işaretçisi konamıyor. Tespit
   verisi bugün yalnız koşu SONRASI `annotate_run` ile ayrı bir mp4'e
   basılıyor. Jüri, tespitin olayla aynı anda olduğunu ekranda göremiyor.
3. **Besleme HTML'i sunucuda derleniyor.** `feed_html` bir dize üretiyor,
   `gr.HTML` basıyor. Kaydırma konumu korunamıyor (bkz. `_feed_slot`'un
   `gr.skip()` numarası), filtre yok, arama yok, olaya tıklayıp videoyu o
   saniyeye atlatmak yok.

## 1. Değişmeyenler

Bu iş bir **taşıma**, yeniden yazım değil:

- **Boru hattı.** `run_pipeline`, `DecisionLoop`, bütün ajanlar, `Store`,
  `Gateway`, `Supervisor` — hiçbiri bu işten haberdar olmuyor.
- **Dört anahtar.** `summary` · `events` · `risk` · `actions`.
- **Kararlar olay anında verilir.** `DecisionLoop.run()` generator kalıyor;
  `on_event` boru hattı iş parçacığında, olayın tam anında çağrılıyor
  (`run.py:447`). **Nüans:** `STEP_MODE_DEFAULT = False`
  (`console.py:141`) ve varsayılan akışta `on_event` bilerek
  BLOKLAMIYOR — müdahale anı bir kart olarak basılıp koşu sürüyor
  (25 Ağustos kararı). Bloklama `step_mode` açıkken devreye giriyor.
  Bu ayrım korunuyor; "video her olayda durur" diye bir garanti yok ve
  arayüz de öyle bir şey iddia etmiyor.
- **Kod İngilizce, insana görünen metin Türkçe.** Yeni HTML/JS için de
  geçerli: `id`/sınıf adları İngilizce, ekrandaki her kelime Türkçe.
- **Model kimlikleri yalnız `gozcu/config.py`'da.**

## 2. Dikiş

`gozcu/ui/console.py` docstring'i (`console.py:6-13`) katmanı zaten
anlatıyor: üst yarı saf fonksiyonlar, alt yarı Gradio bağlantısı.

**(a) Taşınan — taşıyıcıdan bağımsız veri/mantık.** `build_feed` →
`list[FeedEntry]`, `visible_dialogue`, `intervention_card`, `risk_color`,
`RISK_COLORS`, `apply_approval`, `STRESS_PROMPTS`, `Session`'ın iş
parçacığı düzeni.

`_wait_if_step_mode` bu kovada **değil**: §4.1 mekanizmasını yeniden
yazıyor, yani `run_state` gibi **yeniden kurulan** bir şey.

**(b) Ölen — Gradio yuva protokolünün kendisi.** `SCREEN_SLOTS`, `SLOT`,
`_refresh`'in 13'lü demeti, `_blank`, `_feed_slot`'un `gr.skip()` numarası,
`build()`, `feed_html`, `Session.last_feed`.

**(c) Göç eden — kuralı aynı, çıktısı Markdown/satır listesinden veriye
dönen.** `status_badges`, `kpi_markdown`, `root_cause_markdown`,
`tool_summary`, `perception_markdown`, `approval_text`, `handoff_rows`,
`tool_rows`.

Sınır durumlar: `_cut_link` / `_restore_link` / `_resume` / `_decide` /
`_stress` / `_set_step_mode` / `_analyse` **(a) DEĞİL**. Alan mantıkları
taşınıyor, kendileri taşınmıyor: hepsi `_refresh(...)` demeti döndüren
Gradio işleyicileri.

### 2.1 Test muhasebesi

Önceki taslak burada üç kovaya bölünmüş kesin sayılar veriyordu
(77/11/12). **O tablo yanlıştı ve kaldırıldı.** Doğrulanmış olgular:

| Olgu | Değer |
|---|---|
| `tests/test_console.py` test sayısı | **100** |
| `tests/test_feed.py` test sayısı | **40** (önceki taslak 34 diyordu — yanlış) |
| `test_feed.py` içinde `feed_html` çağrı yeri | **9** |
| `gozcu.ui.console`'u import eden konsol testi | **100'ün 100'ü** (`test_console.py:21`) |

Bundan çıkan iki düzeltme:

1. **"Dokunulmuyor" diye bir kova yok.** `console.py` siliniyor; her konsol
   testi en azından import'unu yeni eve çevirmek zorunda. Doğru soru
   "dokunuluyor mu" değil, **"iddiası hayatta kalıyor mu"**.
2. **`test_feed.py` de dokunuluyor.** `feed_html` (b) kategorisinde ve
   9 çağrı yeri var; `test_the_html_is_deterministic_so_the_skip_can_work`
   adıyla `gr.skip` protokolünü test ediyor ve onunla birlikte ölüyor.

**Sınıflandırma kuralı** (sayı değil, ölçüt — test başına triyaj plan
aşamasının açık bir kalemi):

> Bir testi silmek için, kaybolan şeyin **Gradio'nun protokolü** olduğu
> gösterilmeli. Test bir alan kuralını (Türkçe metin, risk rengi, onay
> durum makinesi, kesinti telafisi, yükseltme zinciri) koruyorsa
> **silinmiyor** — yeni taşıyıcıda yeniden kuruluyor.

Bu ölçüt bir testi silme listesinden geri aldı:
`the_streaming_generator_survives_a_skipped_feed_slot`
(`test_console.py:1028`) yalnız `gr.skip` testi değil; kendi docstring'inin
söylediği gibi `LoopEvent → Session.escalated_ids() → kart ekranda`
zincirinin **tek uçtan uca kanıtı**. SSE testi olarak yeniden kuruluyor.
Aynı şekilde `no_handler_refreshes_only_part_of_the_screen`'in değişmezi
"SSE her zaman tam durumu taşır" olarak yeniden kuruluyor.

**Plan üzerindeki bağlayıcı şart.** Ölçütü buraya, sayımı plana koymak
ancak plan sayımı gerçekten yaparsa dürüst olur. **Plan, 140 testin
(konsol 100 + besleme 40) her biri için tek satırlık bir triyaj tablosu
içermek zorunda:** test adı → `taşı` / `göç ettir` / `yeniden kur` /
`sil`, ve `sil` diyen her satırın yanında kaybolan şeyin neden Gradio
protokolü olduğu. Bu tablo olmadan plan onaylanmıyor; yoksa bu bölüm
yalnız ertelenmiş bir uydurma kesinliktir.

**Sayım birimi: test FONKSİYONU.** 140 = konsol 100 + besleme 40.
`pytest --collect-only` **143** topluyor; fark `test_console.py:225`'teki
4'lü `parametrize`. Parametrize edilmiş bir fonksiyon triyaj tablosunda
**tek satır**.

**Aynı bağlayıcılıkta iki tablo daha.** Bu turların bulgularının kökü hep
aynıydı: yeni `Session` durumu, yazarı ve ömrü belirtilmeden eklendi.

1. **`Session` durum tablosu:** alan → yazan → sıfırlayan/sonlandıran →
   hangi kilit altında. `run_state`, `resume_requested`, `version`,
   `thread`, `frames_dir`, `output_dir` en az bu satırları dolduruyor.
2. **Enum eşleme tablosu:** `run_state`'in yedi değeri ve `badges.run`'ın
   üç değeri için "teldeki değer = koddaki sabit". Bu depo bir
   prompt/şema ayrışmasından bir kez sessizce öldü; tel de bir şema.

## 3. Mimari

```
app.py
  └── gozcu/ui/server.py        FastAPI — statik servis + JSON/SSE uçları
        ├── gozcu/ui/session.py  Session + RunState (console.py'den çıkarıldı)
        ├── gozcu/ui/view.py     veri derleyicileri (eski Markdown'ın yerine)
        ├── gozcu/ui/feed.py     build_feed / FeedEntry — DEĞİŞMEDİ
        └── gozcu/ui/web/        statik varlıklar (HTML/CSS/JS)
```

`gozcu/ui/console.py` siliniyor. `_ensure_server_running` (yerel mlx-vlm
sunucusunu ayağa kaldıran fonksiyon) **silinmiyor**, `server.py`'ye
taşınıyor.

### Neden SSE

Akış tek yönlü: sunucu → tarayıcı. Komutlar sıradan `POST`. WebSocket iki
yönlü bir kanalın karmaşıklığını hiç kullanmadan getirirdi.

## 4. Koşu yaşam döngüsü

**Aynı anda tek koşu.** İkinci bir `POST /api/run`, canlı bir koşu varken
**`409` ile reddediliyor.** Önceki taslak "öncekini kapatır" diyordu; bu
uygulanamaz — `run_pipeline`/`DecisionLoop`'ta iptal mekanizması yok ve
koşan iş parçacığı durdurulamaz.

**`POST /api/run/{id}/abandon`** duraklamayı çözer, koşuyu bitirmez:
`step_mode = False` + `resume`'un serbest bırakılması, sonra iş parçacığı
bloklamadan sonuna kadar akar. Çıktısı atılır.

**409 iş parçacığı gerçekten ölene kadar sürer.** Önceki taslak "abandon
sonrası yeni koşuya izin verilir" ve ayrıca "gateway ikinci koşuyla
yarışmıyor" diyordu; **ikisi birden olamaz.** Terk edilmiş bir koşunun görü
çağrıları aynı uzak gateway'e (team37 kotası) gitmeye devam eder ve yeni
koşuyla yarışır. Bu yüzden `abandon` bir *bekleme çözücü*, bir *koşu
sonlandırıcı* değil: `Session` iş parçacığının canlılığını tutuyor ve
`POST /api/run` ancak `thread.is_alive()` yanlış olduğunda kabul ediyor.
Operatör beklemek zorunda kalabilir; alternatifi ölçümü sessizce bozan iki
eşzamanlı koşudur.

### 4.1 Bekleme deseni — `clear()`/`set()` yarışı

`_wait_if_step_mode` bugün şöyle (`console.py:592-595`): `step_mode`
kontrolü → `resume.clear()` → `resume.wait()`. Abandon araya, kontrol ile
`clear()` arasına düşerse, `set()` iş parçacığının kendi `clear()`'ı
tarafından silinir ve iş parçacığı **sonsuza dek bekler** — sonraki
olaylar `step_mode` kapalı olduğu için beklemeye hiç girmez, `resume`'u bir
daha kimse set etmez. Yani abandon tam da önlemeyi vaat ettiği sızıntıyı
üretir.

Yarış bugün de var ama zararsız: `_set_step_mode` tek iş parçacıklı bir
düğmeden çağrılıyor ve testi (`test_console.py:927`) onu yakalayamaz.
Sunucu bunu bir güvenlik mekanizmasına yükselttiği için desen
düzeltiliyor: `Event.clear()/wait()` yerine **`Condition` + yüklem**
(`wait_for(lambda: not session.step_mode or session.resume_requested)`).
Yüklem yeniden kontrol edildiği için kayıp uyandırma imkânsız.

**Jetonu bekleyen tüketiyor.** `resume_requested` yeni bir `Session`
alanı ve önceki taslak onu kimin sıfırladığını yazmıyordu — sıfırlanmazsa
ilk "Devam et"ten sonra yüklem hep doğru kalır ve **hiçbir olay bir daha
duraklamaz**; koşu duraklamamışken basılan bir "Devam et" ise bir sonraki
duraklamayı peşinen yer. Bugünkü `resume.clear()` tam olarak bu bayat-set
tüketimini yapıyordu ve desen sökülürken yerine bir şey konmamıştı.

Kural: `wait_for` döndükten hemen sonra, **aynı kilit altında**,
`resume_requested = False`. `POST /resume` da aynı kilit altında `True`
yazıp `notify_all()` çağırıyor.

§5 tablosundaki `POST /resume` satırı bu yüzden `session.resume.set()`
demiyor — o `Event` emekliye ayrıldı.

## 5. HTTP sözleşmesi

| Uç | İşlev | Kaynak |
|---|---|---|
| `POST /api/run` | Video yükler, koşuyu başlatır, `run_id` döner · canlı koşu varsa `409` | `Session` + `run_pipeline` |
| `POST /api/run/{id}/abandon` | Koşuyu bloklamadan bitmeye bırakır | §4 |
| `GET /api/run/{id}/events` | **SSE** — tam durum | §6 |
| `GET /api/run/{id}/video` | Yüklenen dosyayı `Range` destekli servis eder | §7.1 |
| `POST /api/run/{id}/resume` | Duraklamış döngüyü ilerletir | §4.1 (`resume_requested`) |
| `POST /api/run/{id}/approve` | `{action_id, approved}` | `apply_approval` |
| `POST /api/run/{id}/say` | `{text}` | `nobetci.talk()` |
| `POST /api/run/{id}/stress/{key}` | Zorlu koşul düğmesi | `STRESS_PROMPTS` |
| `POST /api/run/{id}/gateway/cut` · `/restore` | Kesinti / telafi | `inject_failure`, `catch_up` |
| `POST /api/run/{id}/step-mode` | `{enabled}` — **kapatmak bekleyen döngüyü serbest bırakır** | `_set_step_mode`'un kuralı |
| `GET /api/run/{id}/payload` | Dört anahtar + `detail` | `PipelineOutput` |
| `GET /api/run/{id}/kpi` | KPI blokları | `benchmark/kpi.py::collect` |
| `GET /api/run/{id}/handoffs` · `/actions` · `/windows` | Şeffaflık verisi | `Store` |
| `GET /api/run/{id}/detections?from=&to=` | Kutu katmanı + kare boyutu | §7.2 |
| `POST /api/run/{id}/annotate` | Açıklamalı mp4 | `annotate_run` |
| `POST /api/stt` | Ses → metin · `faster-whisper` yoksa `501` | §9 |
| `GET /api/status` | Ağ geçidi, hafıza arka ucu, model | §5.1 |

### 5.1 `step-mode` ve `status`, iki tuzak

`POST /step-mode {enabled: false}` **düz bir alan ataması değil.**
`console._set_step_mode:651-667`: anahtarı kapatan kişi o an bekleyen
döngüyü serbest bırakmak zorunda, yoksa koşu kilitli kalır. Kural aynen
taşınıyor (`test_console.py:927`'nin koruduğu değişmez).

`GET /api/status` **koşudan önce de cevap veriyor.** `Gateway` bugün
`Session` ile doğuyor; oturum yokken uç modül düzeyi bilgiyi
(`VLM_MODEL`, `memory_backend()`) döndürüyor, ağ geçidi sağlığı için
`null`. Boş bir 500 yerine eksik ama dürüst bir cevap.

## 6. SSE — durum yayını

Tek olay tipi, `event: state`, gövdesi tam durum:

```json
{ "version": 412,
  "run_state": "idle | running | paused | intervened | done | failed | abandoned",
  "feed": [ /* FeedEntry */ ],
  "pending": { "action_id": 7, "tool": "halt_production_line", "params": {} },
  "badges": { "gateway": "healthy", "memory": "qdrant", "run": "measured" },
  "processed_until_s": 41.2,
  "elapsed_s": 63.9 }
```

`badges.run` `run_status`'un döndürdüğü üç değerden biri —
`measured` · `degraded` · `unmeasured` (`kpi.py:124`). Önceki taslağın
örneği `"ok"` yazıyordu; şemada olmayan bir değer. Bu depoda bir enum'un
iki yerde ayrışması sistemi bir kez sessizce öldürdü, örnek de dahil.

`processed_until_s`'in kaynağı: **en yeni kayıt hariç** `WindowRecord`'ların
en büyük `end_ts`'i; koşu bittiğinde (`run_state == "done"`) hepsi.

Önceki taslak bunu `Store.set_window_outcome`'a bağlıyordu. **Çalışmaz:**
o metodun repodaki iki çağrı yeri de yalnız erteleme düzeltmesi ve ikisi de
`"deferred"` sabitini geçiyor (`loop.py:797`, `loop.py:813`). Sağlıklı bir
pencere akıbetini (`routed`/`forced`/`skipped`) `save_window` anında alıyor
(`loop.py:781-782`) ve bir daha güncellenmiyor — yani o mekanizmayla sınır
sağlıklı koşuda **sonsuza dek 0'da kalır** ve yalnız kesinti anlarında
sıçrardı. Sınırın en çok gerektiği akış tam da sağlıklı olan.

Kayıt işlemeden ÖNCE yazıldığı için en yeni kayıt "işlenmekte olan"
penceredir; onu dışarıda bırakmak doğru bir **alt sınır** veriyor. Alt
sınır olması isteniyor: sınırı abartmak, henüz karar verilmemiş bir
saniyeyi "karar verildi, olay yok" diye göstermek olurdu (§7.3).

### 6.1 Tüketici modeli — `queue.Queue` yetmiyor

`session.signals` **tek tüketicili** bir kuyruk; bugünkü tek tüketicisi
`_analyse` generator'ı. SSE'de yeniden bağlanma otomatik ve iki generator
aynı anda yaşayabilir; ikisi aynı kuyruğu yarıştırır ve `"done"` sinyali
bir kez tüketilir.

Kuyruk **yayın için kullanılmıyor.** `Session` tek bir
`threading.Condition` + monoton `version` sayacı taşıyor. Yazan taraf
(`on_event`, onay, `talk`, kalp atışı) `version += 1; notify_all()`
yapıyor; her SSE bağlantısı kendi gördüğü son sürümü tutup
`wait_for(version > seen)` ile uyanıyor. N bağlantı, sıfır yarış.

İki örtük yenilik, açıkça:

- **Kalp atışı bir iş parçacığı DEĞİL.** Önceki taslak "`Condition`
  modelinde zaman aşımı kimseyi uyandırmaz" diyip oturum başına bir kalp
  atışı iş parçacığı öneriyordu. **Yanlıştı:**
  `Condition.wait_for(pred, timeout=…)` zaman aşımında döner. Her SSE
  bağlantısı kendi `HEARTBEAT_S` zaman aşımında kendi kendine uyanıyor ve
  bağlantı canlı tutmak için durumsuz bir `:keepalive` yorum satırı
  gönderiyor — `version` artmıyor, besleme yeniden gönderilmiyor. Oturum
  başına iş parçacığı yok, dolayısıyla onu öldürecek bir yaşam döngüsü
  sorusu da yok.
- **Bağlanır bağlanmaz tam durum.** Koşusu bitmiş bir oturuma sonradan
  bağlanan istemci için `version` bir daha hiç artmaz; SSE üreteci ilk
  çerçeveyi beklemeden gönderiyor.

Bu düzeltme §6.3'ün maliyet kaydını da küçültüyor: tam durum yalnız
**gerçekten bir şey değiştiğinde** gidiyor, saniyede bir değil.

### 6.2 `run_state` nereden geliyor

Bugün `run_state` diye bir alan **yok**: durum `_analyse`'ın
generator-yerel kontrol akışında yaşıyor (`console.py:711-727`). Sunucuda
generator yok, dolayısıyla `Session` açık bir `run_state` alanı kazanıyor
ve onu yazan tek yer `Session`'ın kendi metotları oluyor. Bu, (b)
kategorisinde ölen bir kontrol akışının yerine konan **yeni alan** — plan
bunu böyle işlemeli, taşıma diye değil.

### 6.3 Tam durum, delta değil

Yeniden bağlanma bedavaya çözülüyor. `FeedEntry.seq` zaten var; tarayıcı
gördüğü en yüksek `seq`'i tutup yalnız yenileri DOM'a ekliyor — tel tam
durum taşıyor, çizim artımlı.

**Bilinen sınır:** her kalp atışı bütün beslemeyi yeniden gönderiyor,
`FeedEntry.card`'ın HTML'i dahil. Uzun bir koşunun sonunda saniyede yüzlerce
KB. Yerel tek-operatör demosunda sorun değil, kayda geçiyor.

**`FeedEntry.card` sunucuda derlenmiş HTML** (`feed.py:120-123`) —
"saf veri" iddiasının içindeki istisna. Kaçırma (`html.escape`) sorumluluğu
**sunucuda kalıyor**; tarayıcı `card`'ı olduğu gibi basıyor ve başka hiçbir
alanı `innerHTML` ile basmıyor.

## 7. Video ve kutu katmanı

Spec'in en görünür yeni özelliği; önceki taslakta en az tanımlanmış olan
buydu.

### 7.1 Dosya ve saat

Tarayıcı videoyu `GET /api/run/{id}/video`'dan alıyor (`Range` destekli,
aranabilir olması için). Boru hattının okuduğu dosyanın **aynısı**.

Oynatıcının saati boru hattının ilerleyişinden **bağımsız** ve öyle
kalıyor: operatör geri sarabilmeli. `run_state == "paused"` olduğunda
oynatıcı duraklıyor — duraklama iddiası ekranda görünmezse yoktur.

### 7.2 Koordinat uzayı — düzeltme

Önceki taslak "`Detection.box` 0–1 normalize" diyordu. **Yanlıştı.**
Kutular tam sayı **piksel**: `detect.py:36` (`int(v) for v in box.xyxy[0]`)
üretiyor, `track.py:99` aynen geçiriyor, `annotate.py:90` doğrudan
`cv2.rectangle`'a veriyor. Üstelik uzay orijinal video değil, **çıkarım
karesi**: `frames.py:38` kareyi `FRAME_WIDTH = 896`'ya ölçekliyor
(`config.py:88`).

Yani katman iki ölçek çeviriyor:

```
kutu_px (896-genişlikli kare uzayı)
  → /(kare_g, kare_y)                    → 0–1
  → ×(videonun object-fit: contain ile kapladığı gerçek alan)  → ekran px
```

Kare boyutu **kalıcı değil**: `_frame_size` `run_pipeline`'ın yereli
(`run.py:180`) ve atılıyor.

Önceki taslak boyutu `Session.frames_dir`'den okumayı öneriyordu.
**Çalışmaz:** `frames_dir` ancak `run_pipeline` BÜTÜNÜYLE bittikten sonra
atanıyor (`console.py:698`'deki demet açması) ve koşu boyunca `None`
kalıyor — deponun kendi testi bunu sabitliyor (`test_console.py:1070`:
`assert session.frames_dir is None`). Canlı katman boyutu tam da koşu
sürerken istiyor; öneri, özelliğin en çok gerektiği anda ölüydü.

Doğru mekanizma, ve boru hattı yine değişmiyor: **sunucu `output_dir`'i
kendisi seçip `run_pipeline`'a geçiyor** (parametre zaten var,
`run.py:315`). Kareler `extract_frames` biter bitmez orada
(`run.py:356`), yani yol koşunun ilk saniyesinden itibaren biliniyor.
Sunucu ilk kareyi bir kez okuyup boyutu önbelleğe alıyor; `GET /detections`
cevabı `frame_size: [w, h]` taşıyor ve tarayıcı ölçeği asla tahmin
etmiyor.

**Dizin koşu başına.** Sabit bir dizin kullanılamaz: `extract_frames` eski
koşunun karelerini siliyor (`frames.py`, `stale_frame.unlink()`) ve önceki
koşunun `/detections` ile `/annotate`'i altından kayardı. Silme sorumluluğu
sunucuda — `run_pipeline` bu dizini hiç silmiyor, bugünkü `mkdtemp` yolunu
da kimse silmiyordu.

### 7.3 İşlenmemiş bölge

Oynatıcı boru hattının önüne geçebilir — ama "işlenmemiş" burada iki ayrı
şey demek ve önceki taslak ikisini karıştırıyordu.

**Algı bütün videoyu koşu BAŞLAMADAN tarıyor.** Kareler çıkarılıyor,
izleniyor ve bütün `Observation`'lar tespitleriyle birlikte depoya
`DecisionLoop` hiç dönmeden yazılıyor (`run.py:366`). Yani
`processed_until_s`'in ötesindeki saniyeler için **kutu verisi vardır** ve
katman onları normal çiziyor.

İşlenmemiş olan **yorum katmanı**: yönlendirme, epizot, risk. Sınırın
ötesinde kutular görünür ama olay/risk göstergeleri "henüz karar
verilmedi" durumunda çiziliyor — boş değil, **belirsiz**. Boş bir gösterge
"olay yok" diye okunur ve bu, deponun kendi
`routed`/`forced`/`skipped`/`deferred` ayrımının (`WindowRecord`,
`models.py`) katmandaki karşılığıdır: **bakılmadı ile bakıldı-bir-şey-yoktu
aynı kelimeye düşemez.**

## 8. Üç görünüm

Üst bar + tam sayfa modül anahtarı (kısayollar `1` `2` `3`). Video DOM'da
kalıyor, sekme değişince oynatma kesilmiyor.

### 8.1 Operasyon

Sol: video sahnesi, zaman çizelgesi, aksiyon çubuğu, ajan diyaloğu.
Sağ: karar destek (risk + özet + aksiyonlar), olay günlüğü.

Yeni olanlar: canlı kutu katmanı (§7), zaman çizelgesi işaretçileri
(`Episode.start_ts`, `EventBeat.ts`; tıklayınca video atlıyor), olay
günlüğünde filtre/arama, ve **DURAKLADI bandı** — `run_state == "paused"`
olduğunda ekranın üstünde bant + **Devam et**. PoC'de böyle bir durum yok.

Risk göstergesi PoC'de 3 kademeli; `RiskLevel` 4 değerli
(`models.py:11`). Gösterge 4 kademeye genişliyor.

**Renk tek kaynak — mekanizma.** "CSS `RISK_COLORS`'tan okusun" derken
statik bir CSS dosyası bir Python sözlüğünü okuyamaz. Mekanizma: sunucu
rengi **veriyle birlikte** gönderiyor (`risk_color` zaten var,
`feed.py:96`); CSS'te risk rengi sabiti **yok**. İkinci bir renk tablosu
yazılmıyor.

Aynı gerekçeyle **Türkçe ondalık virgül sunucuda biçimleniyor**
(`test_console.py:907`'nin koruduğu kural), tarayıcıda değil — yoksa
kural test kapsamının dışına düşer.

### 8.2 Şeffaflık

Verisi zaten var: **devir defteri** (`Handoff{source_agent, target_agent,
reason, confidence}`, `perception → router → interpreter → synthesizer →
risk_analyst → supervisor` akış diyagramı), **araç çağrı günlüğü**
(`ActionRecord`; `caller` = hangi ajan ile `actor` = insan mı makine mi
**ayrı sütun**; `OUTCOME_KEYS` sırası korunuyor), **pencere defteri**
(`WindowRecord.outcome`'un dört dalı ayrı ayrı).

### 8.3 Performans

PoC'nin düzeni korunuyor, metrikleri tümüyle değişiyor. `collect`
(`kpi.py:369`) altı KPI döndürüyor: `decision_distribution`,
`vlm_trigger_rate`, `vision_tokens`, `correction_propagation`,
`timestamp_drift_s`, `turkish_output_rate`.

Üç düzeltme, üçü de önceki taslağın PoC'den ödünç aldığı alışkanlıkları
geri alıyor:

- **Ölçülemeyen KPI GİZLENMİYOR — "ölçülemedi" YAZILIYOR.** Önceki taslak
  PoC'nin kuralını ("uygulanamayan metrik tamamen gizlenir") taşımıştı;
  bu deponun kuralı **tersi** ve gerekçesi `_pct`'nin docstring'inde
  yazıyor (`console.py:356-361`): `0` "ölçtük, sıfır çıktı" demek, ve
  ölçülemeyen bir hücreyi gizlemek okuyanına o metriğin var olmadığını
  düşündürür. `KPI_UNMEASURED` metni basılıyor
  (`test_console.py:820, 836, 841` bunu sınıyor). §2(c) `kpi_markdown`'ı
  "kuralı aynı" diye göç ettiriyor; kural gerçekten aynı kalıyor.
- **Algı KPI'ları koşudan bağımsız** ve koşu başlamadan da görünüyor
  (çevrimdışı ölçülmüş, şartname §4; bugün `_blank` bile
  `perception_markdown()` basıyor).
- **Bozulmuş koşu KPI'ları gizlemiyor.** `kpi.py` bozulmuş koşuyu **ayrı
  kovada göstermek** için tasarlanmış (`run_status` → `measured` /
  `degraded` / `unmeasured`). Gizlemek kesinti hikâyesinin kendisini
  saklardı — ki o hikâye demo beat 6.

PoC'nin "ölçülen / temsilî" noktası korunuyor ama artık ölçtüğü şey
`run_status`; kare hızı, VRAM, GPU sıcaklığı gibi bu sistemin ölçmediği
hiçbir şey panelde yok.

## 9. Sesli komut

Mikrofon basılı tutuluyor, bırakılınca ses `POST /api/stt`'ye gidiyor,
`faster-whisper` ile **yerel** metne çevriliyor ve sohbet kutusuna
**yazılıyor, gönderilmiyor**: operatör göndermeden önce görüyor. Yanlış
duyulmuş bir komutun ajana sessizce gitmesi geri alınamaz.

`faster-whisper` yoksa uç `501`, mikrofon devre dışı çiziliyor. Örnek
transkript **dönmüyor** — PoC bunu yapıyor (`demo: true` bayrağıyla), bu
depo uydurulmuş çıktıyı ölçülmüş gibi göstermeme kuralını başka her
katmanda uyguluyor.

## 10. PoC'den alınmayanlar

| PoC özelliği | Neden |
|---|---|
| **Bağlam enjeksiyonu** (*Gece Vardiyası*, *Tatbikat* çipleri, riski 0.87→0.42 çeviren) | Karşılığı **yok**. Şartname §6'nın "bağlam değişimi denemesi"nin karşılığı `STRESS_PROMPTS["baglam"]` (`console.py:167`) — ajanı konudan saptırma probu (*"yarın hava nasıl olacak?"*), riski yeniden puanlayan bir dünya değişkeni değil. İsim benzerliği aldatıcı. Üç zorlu koşul düğmesi aynen kalıyor. |
| **RTSP / canlı akış** | `run_pipeline` dosya yolu alıyor. Kart ekranda **devre dışı**, üzerinde *"kapsam dışı — bu sürüm dosyadan çalışır"*. Önceki taslak *"final sürümde"* yazıyordu: tutulacağı belli olmayan bir vaat, deponun dürüstlük kuralının ihlali. Vaat kaldırıldı. |
| **Risk skoru ondalığı** (`0.87`) | `RiskLevel` bir enum; ondalık skor yok ve uydurulmuyor. |
| **Olay başına `confidence`** | `EventSummary`'de yok. Güven `RouterDecision`/`Handoff` üzerinde ve Şeffaflık'ta orada gösteriliyor. |
| PoC'nin `analyzer.py`, `mock.js`, `charts.js`, `bench.js` | Mock veri katmanı; hiçbiri taşınmıyor. Canvas ilkelleri yeniden yazılıyor. |

## 11. Bağımlılıklar

**Ana bağımlılığa eklenen — dördü:** `fastapi`, `uvicorn`,
`sse-starlette`, `python-multipart`.

Bugün venv'de olmaları yanıltıcı. `fastapi`/`uvicorn`/`python-multipart`
gradio üzerinden geliyor. ("Gradio kalkınca giderler" demek yanlış olurdu:
Apple Silicon'da `mlx-vlm` (`mac` ekstrası) `fastapi` ile `uvicorn`'u
doğrudan istiyor, yani o makinede kalırlar — ama `mac` ekstrası olmayan
bir kurulumda kalmazlar ve zaten bir ekstranın taşıdığı paket ana
bağımlılık sayılamaz.)
`sse-starlette` üretimde zaten **yok**: venv'e
`litellm[proxy] → mcp → sse-starlette` zinciriyle, yani **dev ekstrası**
üzerinden düşmüş. Dördü de doğrudan yazılıyor.

**İsteğe bağlı ekstra:** `stt = ["faster-whisper"]`. Ana bağımlılık
**değil** — §9 kurulu değilse `501` dönmeyi ve mikrofonu devre dışı
çizmeyi vaat ediyor; zorunlu bağımlılık olsaydı o dal ölü kod olurdu.
İkisi birden olamaz ve seçilen bu.

**`psutil` eklenmiyor.** Önceki taslak onu listeliyordu; depoda **sıfır**
çağrı yeri var ve bu spec'in hiçbir bölümü onu kullanmıyor — PoC'nin
CPU/RAM göstergelerinden kalma bir artık. Gerekçesiz bağımlılık
eklenmiyor.

**Kalkan:** `gradio>=6.0`.

Harici CDN, font ya da servis bağımlılığı yok.

## 12. Test stratejisi

TDD, depo kuralı.

- **`gozcu/ui/view.py`** — saf veri derleyicileri; (c) kategorisinin göç
  ettiği yer.
- **`gozcu/ui/server.py`** — `fastapi.testclient.TestClient`. Her uç,
  oturum yokken de çökmeden cevap veriyor
  (`every_button_handler_survives_a_missing_session`'ın HTTP karşılığı).
- **SSE** — üç test kritik ve üçü de var olan bir değişmezi taşıyor:
  (1) duraklama gerçekten blokluyor (`the_screen_streams_and_the_loop_really_pauses`);
  (2) `LoopEvent → escalated_ids → kart` zinciri (§2.1);
  (3) iki eşzamanlı bağlantı aynı durumu alıyor (§6.1'in yarış düzeltmesi).
- **Tarayıcı tarafı** — otomatik test yok. Bu bilinçli bir kapsam boşluğu,
  o yüzden **karar veren hiçbir şey tarayıcıya inmiyor**: renk sunucudan
  (§8.1), ondalık biçimi sunucudan (§8.1), risk seviyesi sunucudan.
  Tarayıcıda kalan: çizim, `fetch`, ölçek aritmetiği (§7.2).

Kapı: `.venv/bin/pytest tests/ -q` bütünüyle yeşil ve
`uv run python scripts/check-tasks.py` temiz.

## 13. Riskler

1. **İki iş parçacığı, tek depo.** `on_event` boru hattı iş parçacığında
   bloklamaya devam ediyor; SSE üreteci başka bir iş parçacığında. `Store`
   kilitli (`RLock`, `store.py:74`) ve sunucu **yeni bir yazar
   eklemiyor** — yalnız var olan `Session` metotlarını çağırıyor.
2. **Terk edilmiş koşu iş parçacığı** (§4) sonuna kadar akıyor ve gateway
   kotasını harcıyor. Bu yüzden 409 iş parçacığı ölene kadar sürüyor:
   operatör bekliyor, ölçüm bozulmuyor. Alternatifi iptal edilebilir bir
   boru hattı ve o bu işin kapsamı değil (§14).
3. **Demo videosu yeniden çekilmeli** — var olan çekim Gradio ekranını
   gösteriyor.

## 14. Kapsam dışı

Boru hattının kendisi, ajan promptları, algı kalitesi, çok kullanıcılı
oturum, kimlik doğrulama, dağıtım/konteynerleştirme, RTSP ingest,
iptal edilebilir `run_pipeline`.
