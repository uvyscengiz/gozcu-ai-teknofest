# Web konsolu — Gradio'nun yerine özel arayüz (tasarım)

**Tarih:** 26 Ağustos 2026 · **Durum:** taslak → kör inceleme (2. tur)
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
  (`run.py:443`). **Nüans:** `STEP_MODE_DEFAULT = False`
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
`RISK_COLORS`, `apply_approval`, `STRESS_PROMPTS`, `_wait_if_step_mode`,
`Session`'ın iş parçacığı düzeni.

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
(`test_console.py:1050`) yalnız `gr.skip` testi değil; kendi docstring'inin
söylediği gibi `LoopEvent → Session.escalated_ids() → kart ekranda`
zincirinin **tek uçtan uca kanıtı**. SSE testi olarak yeniden kuruluyor.
Aynı şekilde `no_handler_refreshes_only_part_of_the_screen`'in değişmezi
"SSE her zaman tam durumu taşır" olarak yeniden kuruluyor.

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
koşan iş parçacığı durdurulamaz. `step_mode` açıkken `resume.wait()`'te
asılı bir koşuyu terk etmek iş parçacığı sızıntısıdır.

Kaçış yolu açık bir uç: **`POST /api/run/{id}/abandon`** →
`step_mode = False` + `resume.set()`, koşu bloklamadan sonuna kadar akar,
`Session` "terk edildi" işaretlenir ve yeni koşuya izin verilir. Terk edilen
koşunun çıktısı atılıyor, ama iş parçacığı sızmıyor ve gateway ikinci
koşuyla yarışmıyor.

## 5. HTTP sözleşmesi

| Uç | İşlev | Kaynak |
|---|---|---|
| `POST /api/run` | Video yükler, koşuyu başlatır, `run_id` döner · canlı koşu varsa `409` | `Session` + `run_pipeline` |
| `POST /api/run/{id}/abandon` | Koşuyu bloklamadan bitmeye bırakır | §4 |
| `GET /api/run/{id}/events` | **SSE** — tam durum | §6 |
| `GET /api/run/{id}/video` | Yüklenen dosyayı `Range` destekli servis eder | §7.1 |
| `POST /api/run/{id}/resume` | Duraklamış döngüyü ilerletir | `session.resume.set()` |
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
  "badges": { "gateway": "healthy", "memory": "qdrant", "run": "ok" },
  "processed_until_s": 41.2,
  "elapsed_s": 63.9 }
```

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
Kutular tam sayı **piksel**: `detect.py:35` (`int(v) for v in box.xyxy[0]`)
üretiyor, `track.py:98` aynen geçiriyor, `annotate.py:88` doğrudan
`cv2.rectangle`'a veriyor. Üstelik uzay orijinal video değil, **çıkarım
karesi**: `frames.py` kareyi `FRAME_WIDTH = 896`'ya ölçekliyor
(`config.py:88`).

Yani katman iki ölçek çeviriyor:

```
kutu_px (896-genişlikli kare uzayı)
  → /(kare_g, kare_y)                    → 0–1
  → ×(videonun object-fit: contain ile kapladığı gerçek alan)  → ekran px
```

Kare boyutu **kalıcı değil**: `_frame_size` `run_pipeline`'ın yereli
(`run.py:180`) ve atılıyor. Boru hattı değiştirilmiyor — `Session.frames_dir`
zaten duruyor (`console.py:562`) ve sunucu ilk kareyi oradan okuyup boyutu
bir kez hesaplıyor. `GET /detections` cevabı `frame_size: [w, h]` taşıyor;
tarayıcı ölçeği asla tahmin etmiyor.

### 7.3 İşlenmemiş bölge

Oynatıcı boru hattının önüne geçebilir. O saniyeler için katman **boş
çizmiyor** — ayrı bir "bu bölge henüz işlenmedi" durumu gösteriyor.
Boş bir katman "tespit yok" diye okunur; bu, deponun kendi
`routed`/`forced`/`skipped`/`deferred` ayrımının (`models.py`
`WindowRecord`) katmandaki karşılığıdır: **bakılmadı ile bakıldı-bir-şey-
yoktu aynı kelimeye düşemez.** Sınır `processed_until_s` ile SSE'den
geliyor.

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
`timestamp_drift_s`, `turkish_output_rate`. Uygulanamayan KPI `None`
döndürüyor; panel o kartı **gizliyor**, sıfır yazmıyor.

İki düzeltme:

- **Algı KPI'ları koşudan bağımsız** ve koşu başlamadan da görünüyor
  (çevrimdışı ölçülmüş, şartname §4; bugün `_blank` bile
  `perception_markdown()` basıyor).
- **Bozulmuş koşu KPI'ları gizlemiyor.** Önceki taslak "`run_status`
  yeşil değilken hiçbir KPI gösterilmiyor" diyordu; `kpi.py` bozulmuş
  koşuyu **ayrı kovada göstermek** için tasarlanmış. Gizlemek kesinti
  hikâyesinin kendisini saklardı — ki o hikâye demo beat 6.

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

**Eklenen, doğrudan bildirilecek:** `fastapi`, `uvicorn`, `sse-starlette`,
`python-multipart`, `faster-whisper`, `psutil`.

Bugün venv'de olmaları yanıltıcı ve önceki taslağın gerekçesi yanlıştı:
`fastapi`/`uvicorn`/`python-multipart` gradio üzerinden geliyor,
**`sse-starlette` gelmiyor** — venv'e `litellm[proxy]` (dev ekstrası)
üzerinden düşmüş, yani temiz bir üretim kurulumunda bugün **yok**.
`psutil` ultralytics üzerinden transitif. Dördü de doğrudan bağımlılık
olarak `pyproject.toml`'a yazılıyor.

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
   kotasını harcıyor. Kabul edilen bedel; alternatifi iptal edilebilir bir
   boru hattı ve o bu işin kapsamı değil.
3. **Demo videosu yeniden çekilmeli** — var olan çekim Gradio ekranını
   gösteriyor.

## 14. Kapsam dışı

Boru hattının kendisi, ajan promptları, algı kalitesi, çok kullanıcılı
oturum, kimlik doğrulama, dağıtım/konteynerleştirme, RTSP ingest,
iptal edilebilir `run_pipeline`.
