# Web konsolu — Gradio'nun yerine özel arayüz (tasarım)

**Tarih:** 26 Ağustos 2026 · **Durum:** taslak → kör inceleme
**Kaynak:** `/Users/uveyscengiz/Downloads/ASDASD` altındaki görsel PoC
(FERÂSET arayüzü) ve depodaki `gozcu/ui/console.py`.

> **PoC'den hiçbir kod alınmıyor.** O paket yalnız bir görsel referans:
> kendi mock analiz katmanı, kendi şeması ve kendi uydurma metrikleri var.
> Alınan şey düzen ve tema; alınmayan şey veri modeli. Bu ayrım bu belgenin
> yarısını oluşturuyor, çünkü PoC'nin gösterdiği şeylerin bir kısmının bu
> sistemde **karşılığı yok** ve olduğu gibi taşınırsa arayüz olmayan bir
> yeteneği iddia eder.

## 0. Sorunun özeti

Gradio üç somut şeyi yapamıyor ve üçü de doğrudan puanlanan kalemlerde:

1. **Ekran, sistemin yaptığı işi anlatamıyor.** `SCREEN_SLOTS = 13` — her
   olay işleyicisi tam 13 değer döndürmek zorunda ve eksik bir çıktı
   **hata vermiyor**, o bileşen sessizce tazelenmiyor. Bu protokol yüzünden
   ekran her tazelemede bütünüyle yeniden çiziliyor; kısmi güncelleme yok,
   animasyon yok, video üzerine katman yok.
2. **Video ile karar aynı yüzeyde değil.** `gr.Video` bir oynatıcı; üzerine
   çerçeve çizilemiyor, zaman çizelgesine olay işaretçisi konamıyor. Sistem
   `Detection.box`'ları 0–1 normalize üretiyor (`gozcu/models.py`) ve bu veri
   bugün yalnız koşu SONRASI `annotate_run` ile ayrı bir mp4'e basılıyor.
   Jüri, tespitin olayla aynı anda olduğunu ekranda göremiyor.
3. **Besleme HTML'i sunucuda derleniyor.** `feed_html` bir dize üretiyor,
   `gr.HTML` basıyor. Kaydırma konumu korunamıyor (bkz. `_feed_slot`'un
   `gr.skip()` numarası), filtre yok, arama yok, olaya tıklayıp videoyu o
   saniyeye atlatmak yok.

Şartname §7'nin %35'i "teknik implementasyon ve mimari", %20'si "otonomi ve
zekâ", %10'u açıkça **"sunumun ve dokümantasyonun kalitesi"**. Final 4
dakikalık bir sunum ve içinde 1 dakikalık demo videosu — jürinin sistemi
gördüğü tek yüzey bu ekran.

## 1. Değişmeyenler

Bu iş bir **taşıma**, yeniden yazım değil. Aşağıdakiler tek satır
değişmiyor:

- **Boru hattı.** `run_pipeline`, `DecisionLoop`, bütün ajanlar, `Store`,
  `Gateway`, `Supervisor` — hiçbiri bu işten haberdar olmuyor.
- **Dört anahtar.** `summary` · `events` · `risk` · `actions`; fazlası
  `detail` altında.
- **Kararlar olay anında verilir.** `DecisionLoop.run()` generator kalıyor,
  `on_event` olayın tam anında çağrılıyor ve **bloklamaya devam ediyor**.
  Duraklamayı arayüz taklit etmiyor; generator gerçekten duruyor.
- **Kod İngilizce, insana görünen metin Türkçe.** Yeni HTML/JS için de
  geçerli: `id`/sınıf adları İngilizce, ekrandaki her kelime Türkçe.
- **Model kimlikleri yalnız `gozcu/config.py`'da.**

## 2. Dikiş — neden ucuz

`gozcu/ui/console.py` **zaten ikiye bölünmüş** ve docstring'i bunu böyle
anlatıyor: üst yarı saf fonksiyonlar, alt yarı Gradio bağlantısı. Yeni
arayüz yalnız alt yarıyı değiştiriyor.

Üç kategori, ve bu ayrım testlerin kaderini belirliyor:

**(a) Olduğu gibi taşınan — taşıyıcıdan bağımsız veri/mantık.**
`build_feed` → `list[FeedEntry]` (zaten saf Pydantic verisi, doğrudan JSON),
`visible_dialogue`, `intervention_card`, `risk_color`, `RISK_COLORS`,
`apply_approval`, `STRESS_PROMPTS`, `Session` ve onun iş parçacığı
düzeni, `_wait_if_step_mode`, `_cut_link`/`_restore_link`, `_annotate`.

**(b) Ölenler — Gradio yuva protokolünün kendisi.**
`SCREEN_SLOTS`, `SLOT`, `_refresh`'in 13'lü demeti, `_blank`, `_feed_slot`'un
`gr.skip()` numarası, `build()`, `feed_html`. Bunların hiçbirinin HTTP
karşılığı yok; bir JSON API'de "yuva sayısı" diye bir kavram yoktur.

**(c) Göç edenler — kuralı aynı, çıktısı Markdown'dan veriye dönen.**
`status_badges`, `kpi_markdown`, `root_cause_markdown`, `tool_summary`,
`perception_markdown`, `approval_text`, `handoff_rows`, `tool_rows`.
Bunlar `gr.Markdown`/`gr.Dataframe` beslemek için Markdown dizesi ve satır
listesi üretiyor. Tarayıcı çizecekse **veri** üretmeleri gerekiyor.

### Testler üzerindeki gerçek etki

Bu belge daha önce sözlü olarak "testler yeşil kalır" diye özetlendi; **bu
yanlıştı ve burada düzeltiliyor.** `tests/test_console.py`'de 100 test var:

| | Sayı | Ne oluyor |
|---|---|---|
| Taşınan (a) | ~77 | Dokunulmuyor, yeşil kalıyor |
| Ölen (b) | ~11 | Siliniyor — test ettikleri kavram artık yok |
| Göç eden (c) | ~12 | Kural korunuyor, iddia Markdown yerine veriye bakıyor |

Ölenler adıyla sayılabilir: `no_handler_refreshes_only_part_of_the_screen`,
`the_refresh_and_blank_screens_have_the_same_shape`,
`screen_slot_names_match_the_slot_count`,
`refresh_returns_exactly_the_declared_slots`,
`every_slot_has_a_name_and_the_count_matches`,
`the_blank_screen_fills_every_slot`,
`the_refresh_fills_every_slot_and_draws_the_feed`,
`the_feed_slot_is_skipped_when_nothing_changed`,
`the_streaming_generator_survives_a_skipped_feed_slot`,
`the_console_has_exactly_two_tabs`,
`the_perception_drawing_stays_outside_the_screen_slots`.

Bir testi silmek gümrükten geçmesi gereken bir karardır. Ölçüt: **test
edilen kural mı yoksa Gradio'nun protokolü mü kayboluyor?** Yukarıdaki
11'inde kaybolan protokol. `tests/test_feed.py`'nin 34 testi bütünüyle (a)
kategorisinde ve hiç dokunulmuyor.

## 3. Mimari

```
app.py
  └── gozcu/ui/server.py        FastAPI — statik servis + JSON/SSE uçları
        ├── gozcu/ui/session.py  Session (console.py'den çıkarıldı)
        ├── gozcu/ui/view.py     veri derleyicileri (eski Markdown'ın yerine)
        ├── gozcu/ui/feed.py     DEĞİŞMEDİ — build_feed, FeedEntry
        └── gozcu/ui/web/        statik varlıklar
              ├── index.html
              ├── css/styles.css
              └── js/{app,feed,timeline,overlay,trace,bench,sse}.js
```

`gozcu/ui/console.py` **siliniyor**. `app.py` `gozcu.ui.server:baslat()`
çağırıyor.

### Neden SSE, WebSocket değil

Akış tek yönlü: sunucu → tarayıcı. Komutlar (onay, devam, konuş) sıradan
`POST`. SSE bunun için yeterli, `sse_starlette` **zaten venv'de** (gradio
üzerinden geldi) ve otomatik yeniden bağlanma tarayıcıda hazır geliyor.
WebSocket iki yönlü bir kanalın karmaşıklığını hiç kullanmadan getirirdi.

## 4. HTTP sözleşmesi

| Uç | İşlev | Kaynak |
|---|---|---|
| `POST /api/run` | Yüklenen videoyla koşuyu başlatır, `run_id` döner | `Session` + `run_pipeline` iş parçacığı |
| `GET /api/run/{id}/events` | **SSE** — besleme girdileri, durum, bekleyen onay | `build_feed`, `_pending` |
| `POST /api/run/{id}/resume` | Duraklamış döngüyü ilerletir | `session.resume.set()` |
| `POST /api/run/{id}/approve` | `{action_id, approved}` | `apply_approval` |
| `POST /api/run/{id}/say` | `{text}` — operatör turu | `nobetci.talk()` |
| `POST /api/run/{id}/stress/{key}` | Zorlu koşul düğmesi | `STRESS_PROMPTS` |
| `POST /api/run/{id}/gateway/cut` · `/restore` | Kesinti enjekte / telafi | `inject_failure`, `catch_up` |
| `POST /api/run/{id}/step-mode` | `{enabled}` | `session.step_mode` |
| `GET /api/run/{id}/payload` | Dört anahtar + `detail` | `PipelineOutput` |
| `GET /api/run/{id}/kpi` | KPI blokları | `benchmark/kpi.py::collect` |
| `GET /api/run/{id}/handoffs` · `/actions` · `/windows` | Şeffaflık verisi | `Store` |
| `GET /api/run/{id}/detections?from=&to=` | Kutu katmanı | `Store.observations()` |
| `POST /api/run/{id}/annotate` | Açıklamalı mp4 üretir | `annotate_run` |
| `POST /api/stt` | Ses → metin | `faster-whisper` |
| `GET /api/status` | Ağ geçidi sağlığı, hafıza arka ucu, model, gecikme | `Gateway`, `memory_backend`, `config` |

Tek koşu aynı anda: `run_id` bir sözlükte tutuluyor, ikinci bir `POST /api/run`
öncekini kapatıyor. Çok kullanıcılı bir sunucu değil — jüri önünde tek
operatör var ve oturum havuzu uydurma bir gereksinim olurdu.

## 5. SSE olay akışı

Tek bir olay tipi, `event: state`, gövdesi tam durum:

```json
{
  "run_state": "running | paused | intervened | done | failed",
  "feed": [ /* FeedEntry, olduğu gibi */ ],
  "pending": { "action_id": 7, "tool": "halt_production_line",
               "params": { "line_id": "hat-3" } },
  "badges": { "gateway": "healthy", "memory": "qdrant", "run": "ok" },
  "elapsed_s": 41.2
}
```

Tazeleme tetikleyicisi **bugünküyle aynı**: `session.signals` kuyruğuna
düşen her sinyal + saniyede bir kalp atışı (`HEARTBEAT_S`). Daha sık
yoklama okuma tarafını yarıştırır, daha seyreği "zaman çizelgesi doluyor"
sözünü tutmaz — bu ölçü `console.py`'de zaten alınmış, tekrar aranmıyor.

Tam durum gönderiliyor, delta değil: besleme koşu boyunca birkaç yüz girdi
ve bir yeniden bağlanmada delta'ları toparlamak sıra numarası defteri
gerektirirdi. `FeedEntry.seq` zaten var; tarayıcı gördüğü en yüksek `seq`'i
tutup yalnız yenileri DOM'a ekliyor, yani tel tam durum taşıyor ama çizim
artımlı oluyor.

## 6. Üç görünüm

PoC'nin üst bar + tam sayfa modül anahtarı düzeni korunuyor (kısayollar
`1` `2` `3`). Video DOM'da kalıyor, sekme değişince oynatma kesilmiyor.

### 6.1 Operasyon

Sol sütun: video sahnesi, zaman çizelgesi, aksiyon çubuğu, ajan diyaloğu.
Sağ sütun: karar destek (risk + özet + aksiyonlar), olay günlüğü.

Bugüne göre **yeni** olanlar:

- **Canlı kutu katmanı.** `Detection.box` 0–1 normalize; `object-fit: contain`
  yüzünden videonun gerçekten kapladığı alan hesaplanıp ölçekleniyor.
  Tespitler `GET /detections?from=&to=` ile 10 saniyelik dilimler hâlinde
  önden çekiliyor — SSE'ye bindirmek koşu başına ~3 fps × video süresi kadar
  kutu demektir ve durum yayınını şişirir.
- **Zaman çizelgesi işaretçileri.** `Episode.start_ts` ve `EventBeat.ts`'ten;
  tıklayınca video o saniyeye atlıyor.
- **DURAKLADI bandı.** `run_state == "paused"` olduğunda ekranın üstünde
  kırmızı bant + **Devam et**. PoC'de böyle bir durum **yok** — sistemin
  ana iddiası bu ve arayüzün en görünür öğesi olmak zorunda.
- **Olay günlüğünde filtre/arama** ve olaya tıklayıp videoyu atlatma.

Risk göstergesi PoC'de **3 kademeli**; `RiskLevel` **4 değerli**
(`Düşük` · `Orta` · `Yüksek` · `Kritik`). Gösterge 4 kademeye genişletiliyor
ve renkler `RISK_COLORS`'tan okunuyor — ikinci bir renk tablosu yazılmıyor.
Bir kez ayrışan prompt/şema çifti bu depoyu sessizce öldürdü; aynı hatanın
CSS'teki hâli bu.

### 6.2 Şeffaflık

PoC'nin en yüksek sadakatli sayfası, çünkü verisi zaten var:

- **Devir defteri** — `Handoff{source_agent, target_agent, reason,
  confidence, payload_ref}`; `perception → router → interpreter →
  synthesizer → risk_analyst → supervisor` zinciri akış diyagramı olarak.
- **Araç çağrı günlüğü** — `ActionRecord`; `caller` (hangi ajan) ile `actor`
  (insan mı makine mi) **ayrı sütun**. PoC'de bu ayrım yok; risk analistinin
  kendi soruşturma araçlarını süpervizöre yazmak zincir hakkında yalan olur.
  `OUTCOME_KEYS` sırası korunuyor — bir aracın çalışmadığını gizleyen şerit,
  çalıştığını iddia eder.
- **Pencere defteri** — `WindowRecord.outcome` dört dalı
  (`routed`/`forced`/`skipped`/`deferred`) ayrı ayrı gösteriliyor.
  "Bakılmadı" ile "bakıldı, bir şey yoktu" aynı kelimeye düşemez.

### 6.3 Performans

PoC'nin düzeni korunuyor, **metrikleri tümüyle değişiyor.** PoC kare/sn,
VRAM, GPU sıcaklığı gösteriyor; bu sistemin ölçtüğü şeyler bunlar değil.
`benchmark/kpi.py::collect` altı KPI döndürüyor: `decision_distribution`,
`vlm_trigger_rate`, `vision_tokens`, `correction_propagation`,
`timestamp_drift_s`, `turkish_output_rate`.

**Ölçülemeyen değer uydurulmuyor.** `collect` uygulanamayan KPI için `None`
döndürüyor; panel o kartı **gizliyor**, sıfır yazmıyor. PoC'nin
"ölçülen / temsilî" noktası korunuyor ve gerçek anlamını buluyor: `psutil`
ile okunan CPU/RAM ölçülen, `run_status` yeşil değilken hiçbir KPI
gösterilmiyor.

## 7. PoC'den alınmayanlar

| PoC özelliği | Neden alınmıyor |
|---|---|
| **Bağlam enjeksiyonu** (*Gece Vardiyası*, *Zemin Kaygan*, *Tatbikat* çipleri, riski 0.87→0.42 çeviren) | Bu sistemde karşılığı **yok**. Şartname §6'nın "bağlam değişimi denemesi"nin karşılığı `STRESS_PROMPTS["baglam"]` — ajanı konudan saptırma denemesi (*"yarın hava nasıl olacak?"*), riski yeniden puanlayan bir dünya değişkeni değil. İsim benzerliği aldatıcı; ikisi ayrı şey. Üç zorlu koşul düğmesi olduğu gibi kalıyor. |
| **RTSP / canlı akış** | `run_pipeline` dosya yolu alıyor. Kart ekranda **devre dışı** duruyor, üzerinde *"yerel akış — final sürümde"* notuyla: düzen eksik görünmüyor, olmayan bir yetenek de iddia edilmiyor. |
| **Risk skoru ondalığı** (`0.87`) | `RiskLevel` bir enum; ondalık bir skor yok ve uydurulmuyor. |
| **Olay başına `confidence`** | `EventSummary`'de yok. Güven `RouterDecision` ve `Handoff` üzerinde ve Şeffaflık sayfasında orada gösteriliyor. |
| PoC'nin `analyzer.py`, `mock.js`, `charts.js`, `bench.js` dosyaları | Mock veri katmanı; hiçbiri taşınmıyor. `charts.js`'in canvas ilkelleri yeniden yazılıyor (kütüphane yok, PoC'nin kodu da yok). |

## 8. Sesli komut (bas-konuş)

Mikrofon basılı tutuluyor, bırakılınca ses `POST /api/stt`'ye gidiyor,
`faster-whisper` ile **yerel** metne çevriliyor ve sohbet kutusuna
yazılıyor — gönderilmiyor, **yazılıyor**: operatör göndermeden önce görüyor.
Yanlış duyulmuş bir komutun ajana sessizce gitmesi 4 dakikalık bir sunumda
geri alınamaz.

`faster-whisper` kurulu değilse uç `501` dönüyor ve mikrofon düğmesi devre
dışı çiziliyor. Örnek transkript **dönmüyor** — PoC bunu yapıyor
(`demo: true` bayrağıyla) ama bu depo uydurulmuş çıktıyı ölçülmüş gibi
göstermeme kuralını başka her katmanda uyguluyor.

## 9. Bağımlılıklar

**Eklenen:** `fastapi`, `uvicorn`, `sse-starlette`, `python-multipart`
(dosya yükleme), `faster-whisper`. İlk dördü **zaten venv'de** — gradio
üzerinden transitif geldiler; gradio kalkınca doğrudan bağımlılık olarak
`pyproject.toml`'a yazılmaları gerekiyor, yoksa temiz makinede import
edilemezler.

**Kalkan:** `gradio>=6.0`.

Harici CDN, font ya da servis bağımlılığı **yok** — sistem tamamen yerel
çalıştığını iddia ediyor ve arayüzün bunu bozmaması gerekiyor.

## 10. Test stratejisi

TDD, depo kuralı. Katman katman:

- **`gozcu/ui/view.py`** — saf veri derleyicileri, doğrudan test edilir.
  (c) kategorisindeki 12 testin göç ettiği yer.
- **`gozcu/ui/server.py`** — `fastapi.testclient.TestClient`. Uçların
  sözleşmesi: sahte bir `Session` ile her uç, oturum yokken de çökmeden
  cevap veriyor (`every_button_handler_survives_a_missing_session`'ın HTTP
  karşılığı).
- **SSE** — `TestClient` akışı okuyup ilk `state` olayının şemasını
  doğruluyor; duraklama testi (`the_screen_streams_and_the_loop_really_pauses`)
  HTTP üzerinden yeniden kuruluyor ve **bu test kritik**: duraklamanın
  gerçek olduğunun tek kanıtı o.
- **Tarayıcı tarafı** — otomatik test yok. JS mantığı ince tutuluyor
  (çizim + fetch); karar veren hiçbir şey tarayıcıya inmiyor.

Kapı: `.venv/bin/pytest tests/ -q` bütünüyle yeşil ve
`uv run python scripts/check-tasks.py` temiz.

## 11. Riskler

1. **Duraklama semantiği HTTP'ye geçerken bozulabilir.** `on_event` boru
   hattı iş parçacığında bloklamaya devam ediyor; SSE üreteci **başka** bir
   iş parçacığında. İkisi `session.signals` üzerinden konuşuyor ve `Store`
   kilitli (`RLock`, 26 Ağustos). Yeni bir yazar eklenmiyor — sunucu yalnız
   var olan `Session` metotlarını çağırıyor.
2. **Gradio'nun kalkması `_ensure_server_running`'i etkiliyor.** O fonksiyon
   yerel mlx-vlm sunucusunu ayağa kaldırıyor ve `console.py`'de yaşıyor;
   `server.py`'ye taşınması gerekiyor, silinmesi değil.
3. **Demo videosu yeniden çekilmeli.** Var olan çekim Gradio ekranını
   gösteriyor. Bu iş bittiğinde geçersiz.

## 12. Kapsam dışı

Boru hattının kendisi, ajan promptları, algı kalitesi, çok kullanıcılı
oturum, kimlik doğrulama, dağıtım/konteynerleştirme.
