# Görev 21 — Web konsolu (Gradio emekliye ayrıldı)

> ## ✅ TAMAMLANDI — 27 Ağustos 2026, `1c90b7f`…`d651abd`
>
> **Gradio operatör konsolu (`gozcu/ui/console.py`, 984 satır) silindi.**
> Yerine aynı boru hattını FastAPI + SSE + bağımlılıksız HTML/CSS/JS üzerinden
> sunan özel bir web konsolu geldi: `gozcu/ui/session.py`,
> `gozcu/ui/view.py`, `gozcu/ui/server.py` ve `gozcu/ui/web/` (statik kabuk,
> beş JS modülü, tek stil dosyası). **Boru hattı tek satır değişmedi** —
> `run_pipeline`, `DecisionLoop`, ajanlar, `Store`, `Gateway`, `Supervisor`
> bu işten haberdar olmadı.
>
> Depo genelinde **989 test** geçiyor; `scripts/check-tasks.py` temiz.
>
> **Sonraki göreve başlarken bilmen gerekenler**
> ([notlar](#tamamlanma-notları-gelecek-görevleri-bağlayan)): **SSE her
> zaman TAM durum taşır** (kısmi güncelleme yok), **koşu iptal edilemez —
> 409 iş parçacığı ölene kadar sürer**, ve **belirsizliği çözen şey
> `WindowRecord` değil, canlı döngü**.

**Spec:** [2026-08-26-web-konsolu-design.md](../superpowers/specs/2026-08-26-web-konsolu-design.md)
(beş kör inceleme turu) ·
**Plan:** [2026-08-26-web-konsolu.md](../superpowers/plans/2026-08-26-web-konsolu.md)
(11 görev, 140 satırlık test triyajı)

## Bağlam — Gradio neden kalktı

Üç somut şey, üçü de doğrudan puanlanan kalemlerde:

1. **Ekran, sistemin yaptığı işi anlatamıyordu.** `SCREEN_SLOTS = 13`: her
   olay işleyicisi tam 13 değer döndürmek zorundaydı ve **eksik bir çıktı
   hata vermiyordu** — o bileşen sessizce tazelenmiyor, jüri bayat veri
   görüyordu. Protokol yüzünden ekran her tazelemede bütünüyle yeniden
   çiziliyor; kısmi güncelleme yok, video üzerine katman yok.
2. **Video ile karar aynı yüzeyde değildi.** `gr.Video` bir oynatıcı;
   üzerine çerçeve çizilemiyor, zaman çizelgesine olay işaretçisi
   konamıyordu. Tespit yalnız koşu SONRASI ayrı bir mp4'e basılıyordu —
   tespitin olayla aynı anda olduğu ekranda hiç görünmüyordu.
3. **Besleme HTML'i sunucuda derleniyordu.** `feed_html` bir dize üretiyor,
   `gr.HTML` basıyordu. Kaydırma konumu korunamıyor (`_feed_slot`'un
   `gr.skip()` numarası tam olarak bunu telafi etmek içindi), filtre yok,
   arama yok, olaya tıklayıp videoyu o saniyeye atlatmak yoktu.

## Ne yapıldı

| Dosya | Sorumluluk |
|---|---|
| `gozcu/ui/session.py` | `Session`, `RunState`, `Condition`+`version` durum makinesi |
| `gozcu/ui/view.py` | Depodan **veri** derleyicileri (eski Markdown'ın yerine) |
| `gozcu/ui/server.py` | FastAPI: statik servis, JSON uçları, SSE, koşu yaşam döngüsü |
| `gozcu/ui/web/index.html` | Üç görünümün iskeleti |
| `gozcu/ui/web/css/styles.css` | Tema ve düzen |
| `gozcu/ui/web/js/sse.js` | SSE bağlantısı, `seq` artımlı çizim |
| `gozcu/ui/web/js/feed.js` | `FeedEntry` çizimi |
| `gozcu/ui/web/js/player.js` | Oynatıcı, zaman çizelgesi, kutu katmanı |
| `gozcu/ui/web/js/trace.js` | Şeffaflık görünümü |
| `gozcu/ui/web/js/bench.js` | Performans görünümü |
| `gozcu/ui/feed.py` | `build_feed`/`FeedEntry` değişmedi; `feed_html`/`_entry_html` **silindi** |
| `gozcu/ui/console.py` | **SİLİNDİ** |
| `app.py` | `gozcu.ui.server:baslat()` çağırıyor |
| `pyproject.toml` | `gradio` düştü; dört doğrudan bağımlılık girdi |

Bu son adım (Görev 11 / `d651abd`) yalnız emekliye ayırma işiydi: silme,
giriş noktası, bağımlılıklar, testlerin yeni evi ve bu belge.

## Test muhasebesi

Plan 140 test fonksiyonunu satır satır triyajdan geçirmişti
(konsol 100 + besleme 40). Son adımda `test_console.py`'de **67 fonksiyon**
(70 toplanan; fark `every_risk_level_has_its_own_colour`'ın 4'lü
`parametrize`'ı) kalmıştı:

| Karar | Sayı | Ne oldu |
|---|---|---|
| taşı | 31 | 29'u kaynak modülün evine taşındı, 2'si zaten aynı iddiaları kuran bir testle birleşti |
| yeniden kur | 27 | Karşılıkları önceki adımlarda kurulmuştu; karşılığı olmayan 4'ü bu adımda kuruldu |
| **sil** | **9** | Kaybolan şey **yalnız Gradio'nun protokolü** |

Ayrıca `test_feed.py`'nin `feed_html` çağıran **7 satırı** burada dönüştü —
`feed_html` bu adımda öldüğü için daha erken dönüştürülemezlerdi — ve
`gr.skip()` determinizmini sınayan **1 satırı** silindi.

**Silinen 10 testin tamamı `SCREEN_SLOTS`/`SLOT`/`gr.skip()`/`gr.Tabs`
protokolünü sınıyordu.** Ölçüt şu: kaybolan şey Gradio'nun protokolüyse
silinir, bir **alan kuralıysa** (Türkçe metin, risk rengi, onay durum
makinesi, telafi, yükseltme zinciri) **yeniden kurulur**. Bu ölçüt plan
yazılırken iki testi silme listesinden geri almıştı
(`test_console.py:370` → "SSE her zaman tam durum taşır",
`:1028` → `LoopEvent → escalated_ids → kart` zinciri) ve uygulama sırasında
iki test daha kurtardı: `_entry_html`'e bakan iki girinti/ayrım testi
triyajda `taşı` görünüyordu ama aslında ölen çiziciye bağlıydılar —
silinmediler, `js/feed.js` + `css/styles.css` üzerinde yeniden kuruldular.

Sayı: **1026 → 989**. `−70` (`test_console.py`) `+20` (test_feed.py)
`+11` (test_view.py) `+1` (test_session.py) `+1` (test_server.py).

## Kabul

- [x] `gozcu/ui/console.py` ve `tests/test_console.py` silindi
- [x] `feed_html`/`_entry_html` `gozcu/ui/feed.py`'den kalktı
- [x] `app.py` → `from gozcu.ui.server import baslat`
- [x] `pyproject.toml`: `gradio>=6.0` düştü; `fastapi`, `uvicorn`,
      `sse-starlette`, `python-multipart` doğrudan bağımlılık oldu
- [x] Temiz kurulum: `uv sync --extra dev` → `import gozcu.ui.server` çalışıyor
      (hem `dev` hem yalnız ana bağımlılık profilinde doğrulandı)
- [x] Silinen 10 testin her biri yalnız Gradio protokolü taşıyordu
- [x] `.venv/bin/pytest tests/ -q` → **989 geçiyor**
- [x] `uv run python scripts/check-tasks.py` → temiz
- [x] `README.md` çalıştırma adımları ve bağımlılık listesi güncellendi
- [x] `.claude/launch.json` doğru komutu ve portu (7860) gösteriyor

## Tamamlanma notları (gelecek görevleri bağlayan)

- **SSE her zaman TAM durum taşır.** Bir uç "yalnız değişeni gönderelim"
  diye kısmi çerçeve yollarsa, ekranın bir yarısı bayat kalır ve hata
  vermez — Gradio'nun 13 yuvasının sessizce yuttuğu arızanın aynısı, yeni
  taşıyıcıda. `tests/test_server.py::test_every_sse_frame_carries_the_full_
  state_not_a_partial_update` bunu koruyor. Yeni bir alan eklemek
  `_snapshot`'a eklemek demektir, ayrı bir olay türü açmak değil.
- **Koşu iptal EDİLEMEZ; `409` iş parçacığı ölene kadar sürer.**
  `run_pipeline`/`DecisionLoop`'ta iptal mekanizması yok. `abandon` bir
  *bekleme çözücü*, bir *koşu sonlandırıcı* değil: duraklamayı açar,
  çıktıyı atar, ama iş parçacığı sonuna kadar akmaya devam eder ve görü
  çağrıları aynı `team37` kotasına gitmeye devam eder. İkinci bir koşuyu
  erken kabul eden her değişiklik iki koşuyu aynı kotada yarıştırır ve
  ölçümü sessizce bozar.
- **Durumu değiştiren her yazım `_set_state_locked()`'tan geçmek zorunda.**
  `run_state`'i doğrudan atayan bir yol "her geçiş bildirilir" garantisini
  reklama çevirir; bağlı istemci sonsuza dek "koşuyor" gösterir. `set_state()`
  yalnız onun kilit alan sarmalayıcısı — tabloda kimin ne yazdığı
  [planın `Session` durum tablosunda](../superpowers/plans/2026-08-26-web-konsolu.md).
- **Belirsizliği çözen şey `WindowRecord` değil, canlı döngü.**
  `catch_up()` telafi ettiği pencerenin kaydına hiçbir şey yazmıyor
  (`loop.py:834`): kayıt "ertelendi" diyebiliyor ama "telafi edildi"
  diyemiyor. Bu yüzden `Session.pending_deferred_ts()` cevabı `loop.deferred`
  üzerinden veriyor. Belirsiz bölgeyi kayıttan türetmeye çalışan her
  değişiklik telafi edilmiş bir pencereyi hâlâ belirsiz gösterir.
- **Tarayıcı karar veren hiçbir tablo TUTMUYOR.** Risk renkleri, ajan
  rozetleri, Türkçe durum/rozet/akıbet etiketleri, proaktif rozet, karar
  kovaları, "ölçülemedi" sözcüğü — hepsi `GET /api/meta` ile telden geliyor
  ve kaynakları Python'da tek yerde. `js/` altına elle yazılmış ikinci bir
  tablo koyan her değişiklik, bu depoyu bir kez sessizce öldüren
  prompt/şema ayrışmasının tarayıcı sürümünü üretir.
- **`feed_html` öldü; çizim `js/feed.js`'te ve `entry.card` TEK istisna.**
  Model metnini taşıyan her alan `textContent` ile yazılıyor. `card` sunucuda
  `html.escape`'ten geçip geldiği için `innerHTML` ile basılıyor —
  `feed.js`'te `innerHTML`in ikinci bir kullanımı olamaz
  (`tests/test_feed.py::test_model_text_is_escaped_so_it_cannot_break_the_page`
  bunu satır satır sınıyor).
- **Dört bağımlılık artık DOĞRUDAN.** `fastapi`, `uvicorn`, `sse-starlette`,
  `python-multipart` bugüne kadar `gradio` (ve `sse-starlette` için
  `dev` ekstrasının `litellm[proxy] → mcp` zinciri) üzerinden transitif
  geliyordu. `gradio` düşünce temiz bir kurulumda hiçbiri kalmıyordu; dördü
  de `pyproject.toml`'a elle girdi. `python-multipart` özellikle ŞART —
  `POST /api/run` videoyu `multipart/form-data` ile alıyor ve o paket
  olmadan FastAPI import anında hata veriyor. `psutil` **eklenmedi**:
  depoda sıfır çağrı yeri var.
