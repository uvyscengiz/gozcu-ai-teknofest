# Görev 17 — Çıktı sözleşmesi ve entegrasyon (`gozcu/report.py`, `gozcu/run.py`)

> ## ✅ TAMAMLANDI — 25 Ağustos 2026, `4e1a979`
>
> **Boru hattı uçtan uca bağlandı.** `gozcu/adapter.py`, `gozcu/report.py` ve
> baştan yazılmış `gozcu/run.py` var; `tests/test_report.py` ile
> `tests/test_run.py` birlikte 33 test ile yeşil. Bu dosyayı yeniden uygulama —
> aşağısı ne yapıldığının kaydı.
>
> **Sonraki göreve başlarken bilmen gerekenler**
> ([kararlar](#tamamlanma-notları-gelecek-görevleri-bağlayan) bölümüne bak):
> **`assess_risk` artık kapanışta gerçekten çağrılıyor** — `on_close` onu
> `embed_episode`'un yanına aldı. Daha önce yalnızca belgelenmişti, hiç
> çağrılmıyordu: `store.risks()` her headless koşuda boş kalıyor, `actions[]`
> kalıcı olarak `[]` oluyor ve `risk` sessizce ön riske düşüyordu — dört
> anahtarın ikisi içi boş, hiçbir şey de patlamıyordu. **Çöken genişletilmiş yol
> `detail=None` dönüyor**: dört anahtar yine üretiliyor, ama dolu bir `detail`
> yalnız o katmanlar gerçekten koştuğunda görünüyor. **`app.py` [Görev
> 16](16-konsol.md)'ya bırakıldı** (`84286e8`) — şimdilik yeni
> `EventSummary(time, event)` şekline asgari uyarlama; üç satırlık giriş noktası
> ve konsol 16'nın işi.

**Bağımlılık:** hepsi
**Puanın %35'i tek bir dosyada — projedeki en yüksek getirili teslim**

## Bağlam

Şartnamenin puanladığı senaryo şu: video yüklenir, sistem **zaman damgalı olay
listesi, genel özet, risk değerlendirmesi ve aksiyon önerileri** üretir.
Verdikleri örnek JSON'un anahtarları `summary`, `events`, `risk`, `actions`.

**Bu dört anahtar, diğer her şey çökse bile üretilmek zorunda.** Jüri çıktımızı
kendi örnekleriyle karşılaştıracak; aynı anahtarları görmeli. Bozulmuş bir koşu
bile geçerli, notlandırılabilir bir sonuç döndürmeli.

Eklediğimiz her şey — fazlı epizotlar, devir defteri, risk gerekçeleri, aksiyon
defteri, kök neden raporu — o sözleşmenin **yanında**, `detail` anahtarı
altında duruyor. Yerine değil.

İkinci kural: `actions[]` metinleri Risk Analisti'nin **gerçekten bir araca
eşlediği** adaylardan türetiliyor. İnsanın okuduğu liste ile makinenin aksiyon
defteri birbirinden ayrışamaz.

## Kurulum

```bash
uv sync --extra dev
uv run pytest tests/ -v      # her şey yeşil olmalı
```

> **Gerçek koşu için `.env` içinde İKİ anahtar gerekiyor** (24 Ağustos,
> [Görev 08](08-hafiza.md) `7d6a473`): LLM ağ geçidi için
> `GOZCU_GATEWAY_API_KEY` ve epizodik hafızanın Qdrant'ı için
> `GOZCU_QDRANT_API_KEY` — ikincisi birincisinden **ayrı** bir anahtar
> (`qdr-team37-…`) ve vektör veritabanı ağ geçidinden geçmiyor. İkincisi
> tanımlı değilse hiçbir şey patlamaz: istemci süreç içi bir Qdrant'a düşer ve
> hafıza koşuyla birlikte yok olur. `gozcu.memory.memory_backend()` bunu tek
> kelimeyle söylüyor (`"qdrant"` / `"local"`); teslim koşusundan önce
> `"qdrant"` okuduğunu doğrula.

> **Devralınan borç — `episode_embedding` tablosu ölmeye hazır ama HENÜZ ÖLÜ
> DEĞİL.** Hafıza Qdrant'a taşındıktan sonra `Store.save_embedding` /
> `Store.embeddings` kullanılmıyor sanıldı; değil. `gozcu/fixtures/loader.py`
> hangi epizodun zaten gömüldüğünü hâlâ `store.embeddings()` üzerinden okuyor —
> tekrarsızlık (idempotency) kümesi o. Bu yüzden `embed_episode` başarılı bir
> Qdrant upsert'inden **sonra** o satırı bir **defter** olarak yazmaya devam
> ediyor; satır artık arama indeksi değil ve `search_timeline` ona hiç bakmıyor.
> Yükleyicinin kontrolü Qdrant'a taşındığında defter yazımı, iki `Store` metodu
> ve `episode_embedding` tablosu **birlikte** ölür — üçünü ayrı ayrı silme.

## Ne yapacaksın

Üç parça.

### A. `gozcu/report.py` — sözleşme derleyicisi

```python
build_output(store, summary: str, root_cause=None) -> PipelineOutput
```

### B. `gozcu/adapter.py` — donuk algı katmanını modellere bağlar

Mevcut `signals.py` `FrameSignals(velocities, vanished_tracks, person_count,
person_count_delta)` üretiyor; bizim `Signals` tipimizin bir de `gathering`
alanı var ve **algı katmanı onu hesaplamıyor.** Burada türetiyoruz.

```python
to_observation(frame_ts, detections, frame_signals) -> Observation
GATHERING_THRESHOLD = 3
```

### C. `gozcu/run.py` — uçtan uca akış

```python
run_pipeline(video_path, store=None, gw=None, nobetci=None, on_message=None,
             output_dir=None) -> tuple[PipelineOutput, Path]
```

Akış: kare çıkar → `Observation` üret → depoya yaz → `DecisionLoop` kur →
videonun kendi saatinde koştur → kapanan her epizodu gömüp **riskini biç** →
kök neden raporunu yaz → dört anahtarı derle → teslimden hemen önce bir kez
denetle. Kareler algı katmanının (tespit/takip) girdisi; **görü kademesine
giden şey pencere başına kesilen bir mp4 klibi** ve onu kesen kapanışı da bu
dosya kuruyor (`_clip_for`, aşağıda).

`store` ve `gw` verilmezse burada kuruluyor; `nobetci` verilmezse koşu
**headless** — yükseltmeler duyurulmaz ama epizotlar, riskler ve aksiyonlar
aynen üretilir. `on_message` operatöre giden metni dışarı veren tek kanal.

> **Görev 05 bağlama uyarısı (iki tuzak).**
> 1. `run()` `Episode` değil **`LoopEvent(episode, late)`** yield ediyor —
>    `event.episode` okunacak, `event.late` ise operatöre giden metni
>    değiştirmeli: geç telafi edilmiş bir epizot duyurulur ama canlı kriz gibi
>    sunulmaz.
> 2. **`is_degraded` mutlaka geçilecek:** `is_degraded=lambda: gw.is_degraded("vlm")`.
>    Varsayılan `lambda: False` ile `deferred` hiç dolmaz, `catch_up()` ölü kod
>    olur ve kesinti telafisi demosu sessizce hiçbir şey yapmaz. Çıplak
>    `gw.is_degraded` de olmaz: "herhangi bir kademe" demek ve `rerank`'ın
>    beklenen 400'ü her pencereyi sonsuza dek erteletir.
> 3. `synthesize` döngüye üç argümanlı geçiyor `(window, interpretation,
>    decision)`; Görev 07'nin gerçek imzası `synthesize(gw, store, window,
>    interpretation, decision, on_close=None)` — aradaki farkı bir `lambda`
>    kapatıyor.

> **Görev 07 bağlama uyarısı.** Gerçek imza
> `synthesize(gw, store, window, interpretation, decision, on_close=None)`:
> `gw` ve `store` önden, `on_close` adıyla bağlanır; döngü geriye kalan üç
> argümanı veriyor. Ve **`None` dönüşü bir hata değil** — `synthesize` boş
> pencerede ve açık epizot yokken gelen bir `close_episode`'da bilerek `None`
> döndürüyor (hayalet epizot yazmamak için, [Görev
> 07](07-sentezleyici.md)). `DecisionLoop` bunu zaten `if episode is not None`
> ile eliyor; bağlama kodu da `None`'ı bir başarısızlık işareti sayıp `try`
> bloğunu düşürmemeli.

> **Görev 08 bağlama uyarısı.** `on_close=lambda e: embed_episode(gw, store, e)`
> **`try/except` ile sarılmayacak.** `embed_episode` tasarım gereği istisna
> atmıyor; her arızayı kendi içinde yutup `bool` döndürüyor ([Görev
> 08](08-hafiza.md)). Buraya konan bir `except` ölü koddur ve gerçek bir arızayı
> yakaladığı yanılsamasını verir.

> **Görev 04 bağlama uyarısı (beş madde). Klip üretimi bu görevin işi.**
> 1. `interpret` da aynı şekilde bağlanıyor:
>    `interpret=partial(interpret, gw, store, clip_for=_clip_for(video_path))`.
>    Döngü ona tek argüman (`window`) veriyor.
> 2. **Kapanış artık kare değil klip veriyor:**
>    `clip_for(start_ts, end_ts) -> pathlib.Path | None`. Yorumlayıcı onu
>    pencere başına BİR kez, `window[0].ts` ve `window[-1].ts` ile çağırıyor;
>    dönen şey o aralığı kapsayan, okunabilir bir **H.264 mp4** dosyasının yolu
>    olmalı — kesilemediyse `None`. Kesme reçetesi ve tuzakları için aşağıdaki
>    [`_clip_for`](#6-gozcurunpy-yeniden-yaz) tanımına bak.
> 3. **`None` bir kesinti DEĞİL.** Klip kesilemediğinde yorumlayıcı gateway'i
>    hiç çağırmadan `None` dönüyor ve `DecisionLoop` o pencereyi
>    **ertelememeli** — erteleme yalnızca `gw.is_degraded("vlm")` için. Klip
>    yokken metin-only bir istek gönderip sonucu "video analizi" diye kaydetmek
>    sessizce uydurma üretmek olurdu; o yüzden istek hiç gitmiyor.
> 4. **Pencere başına bir klip; pencereler birleştirilmiyor.** Videonun tamamını
>    tek seferde yükleyip ön ek önbelleğinden (4,8×) yararlanmak cazip ama
>    reddedildi: çözünürlük ölçeği klip süresine bağlı (15 s → 0,95 ·
>    30 s → 0,65 · 60 s → 0,47 · 180 s → 0,28) ve iki tokenin altında kalan bir
>    nesne hiç çözülemiyor. `WINDOW_S` = 10 s bu cetvelin iyi ucunda.
> 5. `run.py` yeniden yazıldığı an `gozcu/interpret.py` ve `gozcu/schema.py`
>    tek çağıranlarını kaybediyor. Bugünkü `run.py` hâlâ onları kullandığı için
>    Görev 04'te bilerek yerinde bırakıldılar; **bu görev ikisini de siler** ve
>    ardından `uv run pytest tests/ -q` ile takımın yeşil kaldığını doğrular.

> **Görev 03/06 şema uyarısı.** Şema sertleştirmesi **gateway'in içinde**.
> `Gateway.ask()`'e düz bir pydantic modeli ver; `strict_schema()`'i kimse elle
> çağırmıyor. Sonucu: `maxLength`, `minimum`/`maximum` ve `pattern` artık tele
> hiç çıkmıyor — yani **her ajan doğrulamadan ÖNCE kendi değerlerini temizlemek
> zorunda**. Ayrıca `ask()` şemalı istek tükendiğinde şemasız bir son deneme
> yapıyor, dolayısıyla dönen içerik iyi biçimli JSON olmayabilir;
> ayrıştırıcılar bunu varsaymamalı.
>
> Burada somut karşılığı: **`EventSummary.time`'ın `^\d{2}:\d{2}$` deseni artık
> tele zorlanmıyor.** Damgayı her zaman `gozcu.agents.router.mmss()` ile kur,
> asla model çıktısından alma — `mmss` tek kopya, `"99:59"`de tavana oturuyor
> ve geçersiz bir damganın `EventSummary` doğrulamasını patlatmasını
> engelliyor. Aynı sebeple `EventSummary.event` (200) ve raporun diğer
> uzunluk sınırlı alanları doğrulamadan önce kesilmiş olmalı.

> **Görev 10 bağlama uyarısı.** `detail.action_ledger` satırlarının `ts`'i
> **videonun zamanı**, duvar saati değil: `call_tool(..., ts=...)` çağıranın
> verdiği olay anını yazıyor ([Görev 10](10-saha-araclari.md), `198801e`).
> Defteri gösteren hiçbir şey — `actions[]`'ı işleyen kod, konsol paneli,
> KPI'lar — onu bir tarih/saat sanmamalı; insana görünecekse `mmss()` ile
> biçimlendirilir. Tersi de doğru: bir satır `0.0` damgalıysa bu "videonun
> başı" demek değil, **çağıran zamanı geçmemiş** demektir.

> **Görev 11 bağlama uyarısı (`dd803fd`).** Epizot kapanışında
> `assess_risk(gw, store, episode)` çağrılır. Analist sonucu kendi kaydediyor
> ve devri de kendisi yazıyor: `risk_analyst → supervisor`, `ts=episode.start_ts`,
> `payload_ref=f"risk:{id}"`. Analistin araştırma sırasında çağırdığı okuma
> araçları **aynı damgayı** taşıyor, yani `detail.action_ledger`'da
> değerlendirmeyle aynı saniyede görünüyorlar — defterdeki sıra "önce araştırdı,
> sonra biçti" hikâyesini bozmaz. `actions[]` metinleri yine analistin gerçek
> bir araca eşlediği `proposed_actions`'tan türetilir.

> **Görev 12 bağlama uyarısı (`a8cf363`).** `what_happened` şartnamenin
> **`summary`** anahtarı olur; raporun tamamı `detail.root_cause_report` altına
> **`.model_dump()`** ile düz bir `dict` olarak konur —
> `Detail.root_cause_report` `dict | None` tipli, model nesnesi oraya girmez.
> Rapor **döndürülür, kaydedilmez**: onu depodan aramak boşuna. Üç arıza dalı da
> (kademe sustu / boş yanıt / okunamayan yanıt) tam beş alanlı bir rapor
> döndürüyor, yani gateway kesintisi dört anahtarlı sözleşmeyi düşürmez.
> **Bağlam bütçesi burada:** aksiyon defteri sonuçları rapora **budanmadan**
> giriyor — budama, raporun atıf vermesi gereken türetilmiş rakamı düşürebilir.
> Bağlam baskısı çıkarsa bu boru hattında yönetilecek, raportörde değil.

> **Görev 13 bağlama uyarısı (`ec0eca6`) — teslim edilen paket de denetleniyor.**
> Denetim artık yalnız operatör diyaloğunun önünde değil: jüriye giden düzyazı da
> taranıyor. `build_output(...)` ile teslim arasına **tek bir çağrı** giriyor —
> `screen_delivery(gw, output)` bir `DeliveryScreening` döndürür ve teslim edilen
> şey `result.output`'tur.
>
> Tek çağrı `summary`'yi, `actions[]`'ın tamamını ve `detail.root_cause_report`
> içindeki her metni ve metin listesini kapsıyor. Rapor alan adlarıyla değil,
> **biçimiyle** taranıyor — elle yazılmış bir alan listesi
> [Görev 12](12-raportor.md)'nin raporundan ayrışırdı, CLAUDE.md'nin adıyla
> uyardığı hata. Rapora yeni bir anlatı alanı eklendiğinde burada yapılacak bir
> iş yok.
>
> **Yapısal kanıta dokunulmuyor:** `events[]`, `risk`, `detail.action_ledger` ve
> epizotlar ne okunuyor ne değiştiriliyor. Uygunsuz hükmünde bile yük
> boşaltılmıyor — `summary`'ye bir denetim notu ekleniyor, dört anahtar ve
> bütün kanıt yerinde kalıyor. Kesintide ya da okunamayan hükümde paket
> **bitine kadar aynı** dönüyor ve `result.screened` `False` olur; denetim
> teslimi hiçbir koşulda engellemez.

> **Görev 14 bağlama uyarısı (`463a74c`) — süpervizörün dışa açık yüzeyi.**
> `Supervisor(gw, store)`; alanlar `.ts`, `.history`, `.last_screening`;
> `.escalate(episode) -> str`, `.talk(operator_text) -> str`,
> `.pending_approval() -> ActionRecord | None`,
> `.approve(action_id, approved) -> dict`. Modül seviyesinde ayrıca
> `uncertainty_note(signals) -> str`.
>
> `escalate` bir `Episode` alıyor, `LoopEvent` değil: döngüden gelen olayda
> **`event.episode`** geçilecek. **`event.late` de operatöre giden metni
> değiştirmeli** — geç telafi edilmiş bir epizot duyurulur ama canlı kriz gibi
> sunulmaz; `escalate` bunu kendisi bilmiyor, sarmalayan taraf yazıyor.
>
> **`approve()` İÇ İÇE bir sonuç döndürüyor:**
> `{"state": "approved" | "rejected" | "unknown_action" | "not_pending",
> "action_id": int, "result": {...}}`. Aracın kendi durumu `result` altında —
> `halt_production_line`'ın `state: "halted"` değeri düz birleştirmede onayın
> `"approved"`ünü eziyordu. Fonksiyon istisna atmıyor; bilinmeyen kimlik de
> karara bağlanmış satır da okunur bir `state` ile dönüyor.

> **Görev 15 indi (`b08fce8`) — benchmark `run_pipeline`'ın YENİ imzasını
> bekliyor.** `benchmark/run.py`'ın ön koşul kontrolü
> `run_pipeline(video_path, store=...)` arıyor; depodaki `gozcu/run.py` hâlâ
> donmuş 1. Aşama PoC'si (`run_pipeline(video_path, output_dir)`) ve o imzayla
> koşu hiç başlamıyor — çıkış kodu 2 ile Türkçe bir mesaj basıyor. 17 indiği
> anda benchmark hiçbir değişiklik gerektirmeden koşar.
>
> **`vlm_trigger_rate`'i ölçülebilir kılan şey 17'nin bu yeniden yazımı.**
> `save_observation`'ı başka çağıran yok; kareler depoya düşmedikçe oranın
> paydası boş kalır ve KPI `null` okur.

**Genişletilmiş yolun tamamı `try` içinde.** Çöktüğünde bile dört anahtarlı
geçerli bir `PipelineOutput` dönmeli, `detail=None` ile.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_report.py`

```python
"""Görev 17 — şartnamenin dört anahtarı ve donuk algı katmanının adaptörü.

Burada korunan tek cümle şu: `summary`, `events`, `risk`, `actions` **her
koşuda** üretilir. Genişletilmiş katmanların hepsi çökse bile jüri
notlandırılabilir bir sonuç görür; eklediğimiz her şey `detail` altında
onların YANINDA durur, yerine değil.
"""

from gozcu.adapter import GATHERING_THRESHOLD, to_observation
from gozcu.agents.reporter import RootCauseReport
from gozcu.models import (ActionRecord, Episode, ProposedAction,
                          RiskAssessment)
from gozcu.report import build_output
from gozcu.store import Store


class _FS:
    """`gozcu.signals.FrameSignals`'ın test ikizi — `gathering` alanı YOK."""

    def __init__(self, **kw):
        self.velocities = kw.get("velocities", {})
        self.vanished_tracks = kw.get("vanished_tracks", [])
        self.person_count = kw.get("person_count", 0)
        self.person_count_delta = kw.get("person_count_delta", 0)


class _Tracked:
    """`gozcu.track.TrackedObject`'in test ikizi."""

    def __init__(self, class_name="person", confidence=0.9,
                 bbox=(0, 0, 10, 10), track_id=1):
        self.class_name = class_name
        self.confidence = confidence
        self.bbox = bbox
        self.track_id = track_id


# -- dört anahtar -------------------------------------------------------------

def test_four_keys_exist_even_with_a_completely_empty_run():
    c = build_output(Store(":memory:"), summary="Kayda değer olay yok.")
    d = c.model_dump(exclude_none=True)
    assert {"summary", "events", "risk", "actions"} <= set(d)
    assert d["risk"] == "Düşük"


def test_events_use_mmss_and_come_from_episodes():
    store = Store(":memory:")
    store.create_episode(Episode(start_ts=15.0, phase="onset",
                                 summary_tr="İstif aracı devrildi",
                                 preliminary_risk="Yüksek"))
    c = build_output(store, summary="ö")
    assert c.events[0].time == "00:15"
    assert c.events[0].event == "İstif aracı devrildi"


def test_a_long_episode_summary_is_trimmed_to_the_event_limit():
    """`Episode.summary_tr` 600, `EventSummary.event` 200 — kesilmezse
    doğrulama patlar ve olay listesi tamamen kaybolur."""
    store = Store(":memory:")
    store.create_episode(Episode(start_ts=0.0, phase="onset",
                                 summary_tr="a" * 600,
                                 preliminary_risk="Orta"))
    assert len(build_output(store, summary="ö").events[0].event) == 200


def test_overall_risk_is_the_highest_assessed_level():
    store = Store(":memory:")
    for level in ("Düşük", "Kritik", "Orta"):
        store.save_risk(RiskAssessment(episode_id=1, level=level,
                                       rationale_tr="g", preventable=True))
    assert build_output(store, summary="ö").risk == "Kritik"


def test_risk_falls_back_to_episode_preliminary_when_no_assessment_exists():
    store = Store(":memory:")
    store.create_episode(Episode(start_ts=0.0, phase="development",
                                 summary_tr="x", preliminary_risk="Yüksek"))
    assert build_output(store, summary="ö").risk == "Yüksek"


# -- aksiyonlar ---------------------------------------------------------------

def test_actions_are_rendered_from_tool_backed_candidates_only():
    """Süzgeç silinirse uydurma araç adı taşıyan öneri de jüriye giden
    listeye düşer — o yüzden aday listesi karışık.

    İnsanın okuduğu liste ile makinenin aksiyon defteri ayrışamaz: sistemin
    çalıştıramayacağı bir öneri sadece bir cümledir.
    """
    store = Store(":memory:")
    store.save_risk(RiskAssessment(
        episode_id=1, level="Kritik", rationale_tr="g", preventable=True,
        proposed_actions=[
            ProposedAction(description_tr="Sağlık ekibini çağır",
                           tool_name="dispatch_medical"),
            ProposedAction(description_tr="Helikopter gönder",
                           tool_name="send_helicopter")]))
    assert build_output(store, summary="ö").actions == ["Sağlık ekibini çağır"]


def test_duplicate_actions_are_not_repeated():
    store = Store(":memory:")
    for _ in range(3):
        store.save_risk(RiskAssessment(
            episode_id=1, level="Orta", rationale_tr="g", preventable=True,
            proposed_actions=[
                ProposedAction(description_tr="Alanı güvenlik altına al",
                               tool_name="site_alarm")]))
    assert build_output(store, summary="ö").actions == [
        "Alanı güvenlik altına al"]


# -- detail -------------------------------------------------------------------

def test_detail_block_is_attached_but_never_replaces_the_four_keys():
    store = Store(":memory:")
    store.save_action(ActionRecord(ts=1.0, tool_name="site_alarm",
                                   params={}, result={}, actor="agent",
                                   approval="not_required"))
    c = build_output(store, summary="ö")
    assert c.detail is not None and len(c.detail.action_ledger) == 1
    assert c.summary == "ö"


def test_the_root_cause_report_is_stored_as_a_plain_dict():
    """`Detail.root_cause_report` `dict | None`; model nesnesi oraya girmez."""
    report = RootCauseReport(what_happened="Yük düştü.",
                             probable_root_cause="Olası fren arızası.",
                             confidence_limits="Kamera sesi duymuyor.")
    c = build_output(Store(":memory:"), summary="ö", root_cause=report)
    assert isinstance(c.detail.root_cause_report, dict)
    assert c.detail.root_cause_report["what_happened"] == "Yük düştü."


# -- adaptör ------------------------------------------------------------------

def test_adapter_derives_gathering_from_person_count():
    g = to_observation(1.0, [], _FS(person_count=GATHERING_THRESHOLD))
    assert g.signals.gathering is True
    assert to_observation(
        1.0, [], _FS(person_count=GATHERING_THRESHOLD - 1)
    ).signals.gathering is False


def test_adapter_keeps_the_person_count_delta():
    g = to_observation(1.0, [], _FS(person_count=4, person_count_delta=2))
    assert g.signals.person_count_delta == 2


def test_adapter_maps_velocities_and_vanished_tracks():
    g = to_observation(2.0, [], _FS(velocities={7: 3.1}, vanished_tracks=[9]))
    assert g.signals.velocities == {7: 3.1}
    assert g.signals.vanished_tracks == [9]
    assert g.ts == 2.0


def test_adapter_carries_the_track_id_into_the_detection():
    """Takip kimliği düşerse yönlendiricinin hız satırları kimsenin olmayan
    hızları gösterir."""
    g = to_observation(3.0, [_Tracked(track_id=7, bbox=(1, 2, 3, 4))], _FS())
    assert g.detections[0].track_id == 7
    assert g.detections[0].label == "person"
    assert g.detections[0].box == (1.0, 2.0, 3.0, 4.0)
```

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_report.py -v
```
Beklenen: `ModuleNotFoundError`

### 3. `gozcu/adapter.py` yaz

```python
"""Donuk algı katmanını ajan katmanının tiplerine bağlayan ince adaptör.

`gozcu/frames.py`, `detect.py`, `track.py` ve `signals.py` yarışma boyunca
değişmiyor (CLAUDE.md). Onların ürettiği `TrackedObject` ve `FrameSignals`
dataclass'ları ile ajanların konuştuğu `Observation` / `Detection` /
`Signals` pydantic modelleri arasındaki çeviri bu yüzden BURADA yaşıyor:
donuk tarafa dokunmadan iki dünya birbirine bakabiliyor.
"""

from gozcu.models import Detection, Observation, Signals

#: Kaç kişi bir "toplanma" sayılır. Üç, bir kalabalığın en küçük hâli — iki
#: kişi bir sohbet, üç kişi bir olayın etrafı.
GATHERING_THRESHOLD = 3


def to_observation(frame_ts: float, detections, frame_signals) -> Observation:
    """Donuk algı katmanının çıktısını ajan katmanının tipine çevirir.

    `gathering` `signals.py`'da hesaplanmıyor — burada kişi sayısından
    türetiliyor. Eşiği aşan kişi sayısı `gathering` sayılıyor; bu bir
    heuristik ve yönlendiriciye sadece bir sinyal olarak gidiyor, karar
    olarak değil.

    `confidence` ve `track_id` `getattr` ile okunuyor: `detect_objects`
    takipsiz `DetectedObject` üretiyor, `track_video` ise `track_id` taşıyan
    `TrackedObject`. İkisi de aynı kapıdan geçebilmeli.
    """
    return Observation(
        ts=frame_ts,
        detections=[
            Detection(label=tracked.class_name,
                      confidence=getattr(tracked, "confidence", 1.0),
                      box=tuple(float(v) for v in tracked.bbox),
                      track_id=getattr(tracked, "track_id", None))
            for tracked in detections],
        signals=Signals(
            velocities=dict(frame_signals.velocities),
            vanished_tracks=list(frame_signals.vanished_tracks),
            person_count=frame_signals.person_count,
            person_count_delta=frame_signals.person_count_delta,
            gathering=frame_signals.person_count >= GATHERING_THRESHOLD))
```

### 4. `gozcu/report.py` yaz

```python
"""Çıktı sözleşmesinin derleyicisi — jürinin okuduğu dört anahtar.

Şartnamenin puanladığı çıktı şu dört anahtardan oluşuyor: `summary`,
`events`, `risk`, `actions`. **Dördü diğer her şey çökse bile üretilir.**
Eklediğimiz her katman — fazlı epizotlar, devir defteri, risk gerekçeleri,
aksiyon defteri, kök neden raporu — `detail` altında onların YANINDA duruyor,
yerine değil.

Bu modül hiçbir model çağırmıyor: elindeki tek malzeme depo. Bozulmuş bir
koşuda da tam olarak aynı işi yapıyor, sadece daha az veriyle.
"""

from gozcu.agents.router import mmss
from gozcu.models import Detail, EventSummary, PipelineOutput, RiskLevel
from gozcu.tools.registry import TOOLS

#: Risk seviyelerinin şiddet sırası. Değerler Türkçe kalır (CLAUDE.md) ve
#: `RiskLevel`'ın kendisiyle birebir aynı olmak zorunda.
ORDER: list[RiskLevel] = ["Düşük", "Orta", "Yüksek", "Kritik"]

#: `EventSummary.event`'in sınırı. `Episode.summary_tr` 600'e kadar
#: uzayabiliyor; kesilmezse doğrulama patlar ve olay listesinin tamamı
#: kaybolur.
MAX_EVENT = 200

DEFAULT_RISK: RiskLevel = "Düşük"


def build_output(store, summary: str, root_cause=None) -> PipelineOutput:
    """Şartnamenin dört anahtarını üretir; her şey `detail` altında yanına
    eklenir, yerine değil.

    `risk` gerçek değerlendirmelerin en yükseği; hiç değerlendirme yoksa
    epizotların ÖN riskine düşülüyor. İkisi de yoksa `"Düşük"` — bir olay
    yaşanmadığı için, riski bilmediğimiz için değil.

    `actions[]` yalnızca **gerçek bir araca bağlanmış** adaylardan türetiliyor.
    `gozcu.agents.risk` uydurma araç adlarını zaten düşürüyor; buradaki ikinci
    süzgeç, depoya başka bir yoldan (arşiv tohumlaması, elle yazılmış bir
    fikstür) girmiş bir öneriyi de kapsıyor. Sistemin çalıştıramayacağı bir
    öneri sadece bir cümledir: insanın okuduğu liste ile makinenin aksiyon
    defteri ayrışamaz.
    """
    episodes = store.episodes()
    risks = store.risks()

    events = [EventSummary(time=mmss(episode.start_ts),
                           event=episode.summary_tr[:MAX_EVENT])
              for episode in episodes]

    levels = [r.level for r in risks] or [e.preliminary_risk for e in episodes]
    risk = max(levels, key=ORDER.index) if levels else DEFAULT_RISK

    actions: list[str] = []
    for assessment in risks:
        for action in assessment.proposed_actions:
            if action.tool_name in TOOLS and action.description_tr not in actions:
                actions.append(action.description_tr)

    return PipelineOutput(
        summary=summary, events=events, risk=risk, actions=actions,
        detail=Detail(
            episodes=episodes,
            risk_assessments=risks,
            handoff_chain=store.handoffs(),
            action_ledger=store.actions(),
            root_cause_report=(root_cause.model_dump() if root_cause is not None
                               else None)))
```

### 5. Başarısız testi yaz — `tests/test_run.py`

Ağ yok, ffmpeg yok: sahte ağ geçidi kademe başına senaryo döndürüyor,
klip kesici ve algı katmanı `monkeypatch` ile değiştiriliyor.

```python
"""Görev 17 — uçtan uca boru hattı.

Bu dosyanın koruduğu üç cümle:

1. **Bozulmuş bir koşu da notlandırılabilir.** Genişletilmiş katman çökerse
   dört anahtar yine döner — ama `detail=None` ile, çünkü dolu bir `detail`
   o katmanların gerçekten koştuğu anlamına gelir.
2. **Nöbetçisiz (headless) koşuda da `risk` ve `actions[]` doludur.** İkisi de
   risk analistinin çıktısından türüyor; analist hiç çağrılmazsa şartnamenin
   iki anahtarı sessizce boşalır.
3. **Geç telafi edilmiş bir epizot canlı kriz gibi duyurulmaz.** `LoopEvent.late`
   operatöre giden metni değiştirmek zorunda.

Ağ yok: sahte ağ geçidi kademe başına senaryo döndürüyor, ffmpeg de sahte.
"""

import inspect
import json
import subprocess
import tempfile
from pathlib import Path

import pytest

from gozcu import run as run_module
from gozcu.config import FRAME_FPS
from gozcu.frames import Frame
from gozcu.gateway import Response
from gozcu.guard import DELIVERY_FLAG_NOTICE
from gozcu.models import Episode, LoopEvent, PipelineOutput
from gozcu.run import LATE_NOTICE, _clip_for, run_pipeline
from gozcu.signals import FrameSignals
from gozcu.store import Store

# -- senaryolar ---------------------------------------------------------------

VLM_JSON = json.dumps({"description": "İstif aracı sallanıyor ve devriliyor.",
                       "notable_event": "Araç devrildi, sürücü yere düştü."})

SYNTHESIS_JSON = json.dumps({"phase": "onset",
                             "summary_tr": "İstif aracı devrildi.",
                             "participants": ["IST-04"],
                             "preliminary_risk": "Yüksek"})

RISK_JSON = json.dumps({
    "level": "Kritik",
    "rationale_tr": "Yerde hareketsiz kişi olabilir; olası fren arızası.",
    "preventable": True,
    "proposed_actions": [{"description_tr": "Sağlık ekibini çağır",
                          "tool_name": "dispatch_medical",
                          "params": {"location": "B-Hattı",
                                     "urgency": "critical"}}]})

REPORT_JSON = json.dumps({
    "what_happened": "B-Hattında istif aracı devrildi.",
    "probable_root_cause": "Olası fren arızası.",
    "actions_taken": ["Sağlık ekibi çağrıldı."],
    "prevention_recommendations": ["Fren bakımı öne alınmalı."],
    "confidence_limits": "Kamera sesi duymuyor."})


class _FakeGateway:
    """Ağa hiç çıkmayan ağ geçidi ikizi; kademe başına senaryo döndürür.

    `heal_after_checks` kesinti telafisi içindir: görü kademesi ilk
    `is_degraded` sorgusunda bozuk, sonrasında sağlam görünür — `catch_up()`
    tam olarak bu geçişte çalışıyor.
    """

    def __init__(self, router=("escalate",), vlm_broken=False,
                 rerank_broken=False, heal_after_checks=0, guard="uygun"):
        self.router = list(router)
        self.vlm_broken = vlm_broken
        self.rerank_broken = rerank_broken
        self.heal_after_checks = heal_after_checks
        self.guard = guard
        self.asked: list[str] = []
        self.messages: list[list[dict]] = []
        self.degraded_checks: list[str | None] = []

    def _next_router(self) -> str:
        return self.router.pop(0) if len(self.router) > 1 else self.router[0]

    def ask(self, tier, messages, schema=None, tools=None, max_tokens=None,
            temperature=None, _retries=None) -> Response:
        self.asked.append(tier)
        self.messages.append(messages)
        if tier == "router":
            return Response(content=json.dumps(
                {"decision": self._next_router(), "rationale": "sinyal var",
                 "confidence": 0.9}))
        if tier == "vlm":
            if self.vlm_broken:
                return Response(model="vlm", degraded=True)
            return Response(content=VLM_JSON, model="vlm", tokens=8285)
        if tier == "fast":
            return Response(content=SYNTHESIS_JSON)
        if tier == "guard":
            return Response(content=self.guard)
        if tier == "main":
            report = getattr(schema, "__name__", "") == "RootCauseReport"
            return Response(content=REPORT_JSON if report else RISK_JSON)
        return Response(degraded=True)

    def embed(self, text):
        return []

    def is_degraded(self, tier=None) -> bool:
        self.degraded_checks.append(tier)
        if (self.heal_after_checks
                and len(self.degraded_checks) > self.heal_after_checks):
            self.vlm_broken = False
        if tier is None:
            return self.vlm_broken or self.rerank_broken
        return {"vlm": self.vlm_broken,
                "rerank": self.rerank_broken}.get(tier, False)


class _FakeSupervisor:
    """Nöbetçi ikizi; kendisine hangi tipin geçildiğini kaydeder."""

    REPLY = "Operatöre haber verildi."

    def __init__(self):
        self.seen: list = []

    def escalate(self, episode):
        self.seen.append(episode)
        return self.REPLY


def _perception(monkeypatch, tmp_path, count=4, person_count=2):
    """Donuk algı katmanını sahte kare/sinyal üretimiyle değiştirir.

    Gerçek ffmpeg ve YOLO burada koşamaz; adaptörün ve depoya yazmanın
    doğrulanması için gerekli olan tek şey doğru şekilli girdi.
    """
    frames = [Frame(path=tmp_path / f"frame_{i:04d}.jpg", timestamp_s=float(i),
                    index=i) for i in range(count)]
    tracked = [[] for _ in frames]
    signals = [FrameSignals(person_count=person_count,
                            velocities={1: 4.0}) for _ in frames]
    monkeypatch.setattr(run_module, "extract_frames", lambda *a, **k: frames)
    monkeypatch.setattr(run_module, "track_video", lambda *a, **k: tracked)
    monkeypatch.setattr(run_module, "compute_signals", lambda *a, **k: signals)
    return frames


def _fake_clip(monkeypatch, tmp_path):
    """Klip kesiciyi gerçek bir dosyayla değiştirir; ffmpeg çalışmaz."""
    clip = tmp_path / "window.mp4"
    clip.write_bytes(b"\x00fake-mp4")
    monkeypatch.setattr(run_module, "_clip_for", lambda *a, **k:
                        lambda start, end: clip)
    return clip


# -- klip kesici --------------------------------------------------------------

class _FakeRun:
    """`subprocess.run` ikizi: argv'yi kaydeder ve istenirse dosyayı yazar."""

    def __init__(self, returncode=0, write=True, error=None):
        self.returncode, self.write, self.error = returncode, write, error
        self.argv: list[str] = []

    def __call__(self, argv, **kwargs):
        if self.error is not None:
            raise self.error
        self.argv = argv
        if self.write:
            Path(argv[-1]).write_bytes(b"\x00mp4")
        return subprocess.CompletedProcess(argv, self.returncode)


def _cut(monkeypatch, fake, tmp_path, start=10.0, end=20.0):
    monkeypatch.setattr(run_module.subprocess, "run", fake)
    return _clip_for("video.mp4", out_dir=tmp_path)(start, end)


def test_the_clip_recipe_is_the_one_measured_against_the_live_gateway(
        monkeypatch, tmp_path):
    """`-c:v libx264` olmadan gateway `data:video/mp4;base64,…` yükünü
    çözemez; `-an` ses akışını atar, model sesi kullanmıyor."""
    fake = _FakeRun()
    assert _cut(monkeypatch, fake, tmp_path) is not None
    assert fake.argv[:3] == ["ffmpeg", "-y", "-ss"]
    assert "scale=1280:-2" in fake.argv
    assert fake.argv[fake.argv.index("-c:v") + 1] == "libx264"
    assert "-an" in fake.argv


def test_a_single_observation_window_still_asks_for_one_whole_frame(
        monkeypatch, tmp_path):
    """Tek gözlemlik pencerede `start == end`; sıfır süreli kesit ffmpeg'den
    boş dosya döndürür."""
    fake = _FakeRun()
    _cut(monkeypatch, fake, tmp_path, start=7.0, end=7.0)
    assert float(fake.argv[fake.argv.index("-t") + 1]) == pytest.approx(
        1.0 / FRAME_FPS, abs=0.01)


def test_a_failed_cut_is_a_skipped_window_not_an_outage(monkeypatch, tmp_path):
    assert _cut(monkeypatch, _FakeRun(returncode=1), tmp_path) is None


def test_an_empty_clip_file_is_treated_as_no_clip(monkeypatch, tmp_path):
    fake = _FakeRun()
    monkeypatch.setattr(run_module.subprocess, "run", fake)
    cut = _clip_for("video.mp4", out_dir=tmp_path)
    fake.write = False
    assert cut(1.0, 2.0) is None


def test_a_missing_ffmpeg_binary_does_not_bring_the_run_down(monkeypatch,
                                                             tmp_path):
    """`subprocess.run` kurulu olmayan ikili için `FileNotFoundError` atar;
    o istisna yorumlayıcıdan döngüye kaçarsa bütün koşu düşer."""
    fake = _FakeRun(error=FileNotFoundError("ffmpeg"))
    assert _cut(monkeypatch, fake, tmp_path) is None


def test_clips_are_temporary_artefacts_outside_the_repository(monkeypatch):
    """Klipler yeniden üretilebilir ikili dosyalar; depo ağacına yazılmaz."""
    fake = _FakeRun()
    monkeypatch.setattr(run_module.subprocess, "run", fake)
    clip = _clip_for("video.mp4")(1.0, 2.0)
    assert Path(tempfile.gettempdir()) in clip.parents
    assert Path(__file__).resolve().parent.parent not in clip.parents


# -- imza ve bağımlılıklar ----------------------------------------------------

def test_the_benchmark_signature_is_honoured():
    """Görev 15'in ön koşul kontrolü `store` parametresini arıyor."""
    assert "store" in inspect.signature(run_pipeline).parameters


def test_the_pipeline_builds_its_own_store_and_gateway(monkeypatch, tmp_path):
    """`benchmark/run.py` `gw` geçmiyor; varsayılan `None` dereference edilirdi."""
    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)
    built: list = []

    def _gateway(store=None):
        built.append(store)
        return _FakeGateway(router=("ignore",))

    monkeypatch.setattr(run_module, "Gateway", _gateway)
    output, _ = run_pipeline("video.mp4")
    assert isinstance(output, PipelineOutput)
    # Ağ geçidi depoyla kuruldu ve gözlemler o depoya yazıldı.
    assert built and len(built[0].observations()) == 4


def test_every_observation_is_written_to_the_store(monkeypatch, tmp_path):
    """`vlm_trigger_rate`'in paydası bu — başka hiçbir yer gözlem yazmıyor."""
    _perception(monkeypatch, tmp_path, count=6)
    _fake_clip(monkeypatch, tmp_path)
    store = Store(":memory:")
    run_pipeline("video.mp4", store=store, gw=_FakeGateway(router=("ignore",)))
    assert len(store.observations()) == 6


# -- dört anahtar -------------------------------------------------------------

def test_a_headless_run_fills_risk_and_actions(monkeypatch, tmp_path):
    """Nöbetçi yokken risk analisti hiç çağrılmazsa `actions[]` kalıcı olarak
    boş kalır ve `risk` ön riske düşer — dört anahtarın ikisi içi boş."""
    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)
    store = Store(":memory:")
    output, _ = run_pipeline("video.mp4", store=store,
                             gw=_FakeGateway(router=("open_episode",
                                                     "close_episode")))
    assert output.risk == "Kritik"          # ön risk "Yüksek" idi
    assert output.actions == ["Sağlık ekibini çağır"]
    assert store.risks() and store.risks()[0].episode_id == store.episodes()[0].id


def test_a_closed_episode_is_assessed_at_the_moment_it_closes(monkeypatch,
                                                              tmp_path):
    """Kararlar olay anında verilir (CLAUDE.md).

    Üç pencere: olay açılır, kapanır, sonra yeni bir olay açılır. Kapanan
    epizodun riski videonun geri kalanı işlenmeden BİÇİLMİŞ olmalı — koşu
    sonuna toplanan bir analiz, defterin "önce oldu, sonra karar verildi"
    hikâyesini kapanış raporuna erteler.
    """
    _perception(monkeypatch, tmp_path, count=24)
    _fake_clip(monkeypatch, tmp_path)
    store = Store(":memory:")
    run_pipeline("video.mp4", store=store,
                 gw=_FakeGateway(router=("open_episode", "close_episode",
                                         "open_episode")))
    handoffs = store.handoffs()
    first_risk = next(i for i, h in enumerate(handoffs)
                      if h.source_agent == "risk_analyst")
    last_synthesis = max(i for i, h in enumerate(handoffs)
                         if h.source_agent == "synthesizer")
    assert first_risk < last_synthesis
    assert len(store.episodes()) == 2
    # Kapanmayan ikinci epizot da değerlendirmesiz kalmıyor.
    assert {r.episode_id for r in store.risks()} == {e.id for e
                                                     in store.episodes()}


def test_the_summary_comes_from_the_root_cause_report(monkeypatch, tmp_path):
    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)
    output, _ = run_pipeline("video.mp4", store=Store(":memory:"),
                             gw=_FakeGateway(router=("open_episode",)))
    assert output.summary == "B-Hattında istif aracı devrildi."
    assert output.detail.root_cause_report["probable_root_cause"] == (
        "Olası fren arızası.")


def test_a_run_without_a_single_episode_reports_no_incident(monkeypatch,
                                                            tmp_path):
    """Hiçbir olay yokken kök neden raporu üretmek yaşanmamış bir olayı
    anlatmak olurdu."""
    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)
    gw = _FakeGateway(router=("ignore",))
    output, _ = run_pipeline("video.mp4", store=Store(":memory:"), gw=gw)
    assert output.summary == run_module.EMPTY_SUMMARY
    assert output.events == [] and output.actions == []
    assert output.risk == "Düşük"
    assert "main" not in gw.asked


def test_a_crashed_extended_pipeline_still_returns_the_four_keys(monkeypatch,
                                                                tmp_path):
    """Bozulmuş bir koşu da geçerli, notlandırılabilir bir sonuç döndürmeli."""
    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)

    def _explode(*args, **kwargs):
        raise RuntimeError("yönlendirici çöktü")

    monkeypatch.setattr(run_module, "route", _explode)
    output, _ = run_pipeline("video.mp4", store=Store(":memory:"),
                             gw=_FakeGateway())
    assert set(output.model_dump()) >= {"summary", "events", "risk", "actions"}
    assert output.risk == "Düşük"
    # Dolu bir `detail` "genişletilmiş katmanlar koştu" demek; koşmadılar.
    assert output.detail is None


def test_the_delivered_payload_passes_through_the_delivery_screening(
        monkeypatch, tmp_path):
    """Görev 13: `build_output` ile teslim arasında tek bir denetim çağrısı."""
    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)
    gw = _FakeGateway(router=("open_episode",), guard="uygunsuz")
    output, _ = run_pipeline("video.mp4", store=Store(":memory:"), gw=gw)
    assert gw.asked.count("guard") == 1
    assert DELIVERY_FLAG_NOTICE in output.summary
    # Yük boşaltılmıyor: kanıt yerinde kalıyor.
    assert output.events and output.actions


# -- olay anında karar --------------------------------------------------------

def test_the_vision_tier_is_asked_with_a_clip_not_a_frame(monkeypatch,
                                                          tmp_path):
    """Yorumlayıcıya klip kesici bağlanmazsa görü kademesi hiç çağrılmaz."""
    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)
    gw = _FakeGateway(router=("inspect",))
    store = Store(":memory:")
    run_pipeline("video.mp4", store=store, gw=gw)
    assert "vlm" in gw.asked
    parts = gw.messages[gw.asked.index("vlm")][-1]["content"]
    assert any(p.get("type") == "video_url" for p in parts)
    assert store.interpretations()


def test_only_the_vision_tier_can_defer_a_window(monkeypatch, tmp_path):
    """Çıplak `gw.is_degraded` 'herhangi bir kademe' demek; `rerank`'ın
    beklenen 400'ü her pencereyi sonsuza dek erteletirdi."""
    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)
    captured: dict = {}
    real_loop = run_module.DecisionLoop

    def _spy(store, **kwargs):
        captured.update(kwargs)
        return real_loop(store, **kwargs)

    monkeypatch.setattr(run_module, "DecisionLoop", _spy)
    gw = _FakeGateway(router=("ignore",), rerank_broken=True)
    run_pipeline("video.mp4", store=Store(":memory:"), gw=gw)
    assert captured["is_degraded"]() is False


# -- geç telafi ---------------------------------------------------------------

def _late_run(monkeypatch, tmp_path, **kwargs):
    """Görü kademesi ilk pencerede bozuk, telafi turunda sağlam.

    Karar `inspect`: canlı yükseltme hiç doğmuyor, dolayısıyla operatöre
    giden TEK metin telafi turundan geliyor.
    """
    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)
    gw = _FakeGateway(router=("inspect",), vlm_broken=True,
                      heal_after_checks=1)
    nobetci = _FakeSupervisor()
    said: list[str] = []
    run_pipeline("video.mp4", store=Store(":memory:"), gw=gw,
                 nobetci=nobetci, on_message=said.append, **kwargs)
    return nobetci, said


def test_a_live_escalation_is_announced_without_a_catch_up_marker(monkeypatch,
                                                                  tmp_path):
    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)
    nobetci = _FakeSupervisor()
    said: list[str] = []
    run_pipeline("video.mp4", store=Store(":memory:"),
                 gw=_FakeGateway(router=("escalate",)), nobetci=nobetci,
                 on_message=said.append)
    assert said == [_FakeSupervisor.REPLY]


def test_a_backfilled_episode_is_announced_but_not_as_a_live_crisis(
        monkeypatch, tmp_path):
    """Geç keşfedilen bir olayı saklamak kabul edilemez; onu canlı kriz gibi
    duyurmak da yanıltıcı. `LoopEvent.late` bu ikisini ayırır."""
    nobetci, said = _late_run(monkeypatch, tmp_path)
    assert nobetci.seen, "telafi turundan hiç epizot çıkmadı"
    assert len(said) == 1
    assert said[0].startswith(LATE_NOTICE)
    assert _FakeSupervisor.REPLY in said[0]
    # Canlı yükseltmenin metniyle aynı olsaydı ayrım hiç yapılmamış olurdu.
    assert said[0] != _FakeSupervisor.REPLY


def test_the_supervisor_receives_an_episode_not_a_loop_event(monkeypatch,
                                                             tmp_path):
    """Görev 14: `escalate` bir `Episode` alıyor, `LoopEvent` değil."""
    nobetci, _ = _late_run(monkeypatch, tmp_path)
    assert isinstance(nobetci.seen[0], Episode)
    assert not isinstance(nobetci.seen[0], LoopEvent)
```

### 6. `gozcu/run.py` yeniden yaz

```python
"""Uçtan uca boru hattı — bütün ajanların tek bir koşuda birleştiği yer.

Akış: kare çıkar → `Observation` üret → depoya yaz → `DecisionLoop` kur →
videonun kendi saatinde koştur → kapanan her epizodu gömüp riskini biç →
kök neden raporunu yaz → şartnamenin dört anahtarını derle → teslimden hemen
önce bir kez denetle.

Üç değişmez bu dosyada kod oluyor:

**Dört anahtar her koşuda üretilir.** Genişletilmiş yolun tamamı bir `try`
içinde; çöktüğünde `summary` · `events` · `risk` · `actions` yine döner —
ama `detail=None` ile. Dolu bir `detail` "o katmanlar gerçekten koştu"
demektir ve çöken bir koşuda öyle bir şey iddia edilmez.

**Kararlar olay anında verilir.** `DecisionLoop.run()` bir generator: kritik
anda duruyor, operatöre sesleniliyor, sonra videodan devam ediliyor. Kapanış
raporu bu akışın sonucu, yerine geçen şey değil.

**Görü kademesine giden şey klip.** Pencere başına bir mp4 kesiliyor
(`_clip_for`); yorumlayıcı ffmpeg'i hiç görmüyor. Kesme reçetesi canlı
ölçülen biçimin aynısı (`docs/06-references/evren-gateway.md`).
"""

import subprocess
import tempfile
from functools import partial
from pathlib import Path

from gozcu.adapter import to_observation
from gozcu.agents.interpreter import interpret
from gozcu.agents.reporter import generate_root_cause_report
from gozcu.agents.risk import assess_risk
from gozcu.agents.router import route
from gozcu.agents.synthesizer import synthesize
from gozcu.config import FRAME_FPS
from gozcu.frames import extract_frames
from gozcu.gateway import Gateway
from gozcu.guard import screen_delivery
from gozcu.loop import DecisionLoop
from gozcu.memory import embed_episode
from gozcu.models import DialogueTurn, Episode, PipelineOutput
from gozcu.report import build_output
from gozcu.signals import compute_signals
from gozcu.store import Store
from gozcu.track import track_video

__all__ = ["EMPTY_SUMMARY", "LATE_NOTICE", "run_pipeline"]

#: Hiç epizot üretilmemiş koşunun özeti. Kök neden raporu çağrılmıyor: olay
#: yokken rapor yazmak yaşanmamış bir olayı anlatmak olurdu.
EMPTY_SUMMARY = "Kayda değer olay tespit edilmedi."

#: Kesinti telafisinden gelen epizodun operatöre giden metnine eklenen damga.
#: Geç keşfedilen bir olayı saklamak bir güvenlik sistemi için kabul edilemez,
#: ama onu canlı bir kriz gibi duyurmak da yanıltıcı — o yüzden duyuruluyor,
#: ama damgalanıyor. `Supervisor.escalate` bunu kendisi bilmiyor; farkı
#: `LoopEvent.late` taşıyor ve sarmalayan taraf, yani burası yazıyor.
LATE_NOTICE = "[Telafi — kesinti sırasında atlanmıştı; canlı bir uyarı değil.]"

#: Klip çözünürlüğü. Algı katmanının `FRAME_WIDTH`'i ile ilgisi yok: o kare
#: genişliği, bu görü kademesine giden videonun ölçeği (canlı ölçüldü).
CLIP_SCALE = "scale=1280:-2"


def _clip_for(video_path, out_dir=None):
    """Bir `(start_ts, end_ts)` aralığını kısa bir mp4 klibine kesen kapanış.

    Yorumlayıcı (Görev 04) bunu pencere başına BİR kez çağırıyor ve dönen
    yolu base64 data-URI olarak gateway'e gömüyor; kesilemezse `None`.

    **`None` bir kesinti değil.** Klip yokken yorumlayıcı gateway'i hiç
    çağırmıyor ve `DecisionLoop` o pencereyi ertelemiyor — erteleme yalnızca
    `gw.is_degraded("vlm")` için. Bu yüzden ffmpeg'in kurulu olmaması da,
    okunamayan bir video da, boş çıkan bir kesit de aynı sessiz dala düşüyor.

    `-c:v libx264` H.264 üretiyor: `data:video/mp4;base64,…` yükünün
    çözülebilmesi için gereken şey bu. `-an` ses akışını atıyor — model sesi
    kullanmıyor, taşımak yalnız base64 boyutunu şişirir.

    Klipler tıpkı kareler gibi **geçici artefakt**: varsayılan
    `tempfile.mkdtemp` depo ağacının dışına düşer. Hiçbir klip commit edilmez.
    """
    workdir = Path(out_dir or tempfile.mkdtemp(prefix="gozcu-clips-"))
    workdir.mkdir(parents=True, exist_ok=True)

    def cut(start_ts: float, end_ts: float) -> Path | None:
        # Tek gözlemlik pencerede `start_ts == end_ts`; sıfır süreli bir kesit
        # ffmpeg'den boş dosya döndürür. Taban en az bir kare.
        span = max(end_ts - start_ts, 1.0 / FRAME_FPS)
        out = workdir / f"{start_ts:08.2f}-{end_ts:08.2f}.mp4"
        if out.exists() and out.stat().st_size > 0:
            return out
        try:
            done = subprocess.run(
                ["ffmpeg", "-y", "-ss", f"{start_ts:.2f}", "-t", f"{span:.2f}",
                 "-i", str(video_path), "-vf", CLIP_SCALE,
                 "-c:v", "libx264", "-an", str(out)],
                capture_output=True)
        except OSError:
            return None            # ffmpeg yok — atlanan pencere, kesinti değil
        if done.returncode != 0 or not out.exists() or out.stat().st_size == 0:
            return None
        return out

    return cut


def _on_close(gw, store, episode: Episode) -> None:
    """Kapanan epizodun iki işi: arşive gömülür, sonra riski biçilir.

    `embed_episode` bilerek `try/except` ile sarılmıyor: tasarım gereği
    istisna atmıyor, her arızayı yutup `bool` döndürüyor (Görev 08). Buraya
    konan bir `except` ölü koddur.

    Risk analisti burada çağrılıyor çünkü **kararlar olay anında veriliyor**:
    değerlendirme ve analistin çağırdığı okuma araçları epizodun kendi
    damgasıyla deftere düşüyor (Görev 11), kapanış raporundan sonra değil.
    `actions[]` ve `risk` de buradan doğuyor — analist hiç çağrılmazsa
    şartnamenin iki anahtarı sessizce boşalır.
    """
    embed_episode(gw, store, episode)
    assess_risk(gw, store, episode)


def _announce(store, nobetci, event, on_message) -> str:
    """Yükseltmeyi operatöre duyurur; geç telafiyi damgalar.

    `escalate` bir `Episode` alıyor, `LoopEvent` değil (Görev 14) — geçilen
    şey `event.episode`. Damga diyalog dökümüne de düşüyor: konsol kapalıyken
    bile kök neden raporunun DİYALOG bölümü hangi uyarının telafiden geldiğini
    görebilmeli.
    """
    message = nobetci.escalate(event.episode)
    if event.late:
        message = f"{LATE_NOTICE} {message}"
        store.save_dialogue(DialogueTurn(ts=event.episode.start_ts,
                                         role="system", text=LATE_NOTICE))
    if on_message is not None:
        on_message(message)
    return message


def _sweep_unassessed(gw, store, fresh: list[Episode]) -> None:
    """Koşu bittiğinde değerlendirmesiz kalan epizotları biçer.

    Kapanmayan bir epizot `on_close`'a hiç uğramaz — video bitene kadar açık
    kalan bir olay tam olarak budur. Değerlendirmesi olmayan epizot
    `actions[]`'a hiçbir şey vermez ve `risk`'i ön riske düşürür.

    Arşivden gelen epizotlar (`load_history`) bilerek dışarıda: onlar bu
    videonun olayı değil, geçmişin kaydı.
    """
    assessed = {assessment.episode_id for assessment in store.risks()}
    for episode in fresh:
        if episode.id not in assessed:
            assess_risk(gw, store, episode)


def _degraded_output(store, summary: str) -> PipelineOutput:
    """Genişletilmiş katman çöktüğünde teslim edilen dört anahtar.

    `detail` bilerek `None`: dolu bir `detail` epizotların, devir defterinin
    ve risk gerekçelerinin gerçekten üretildiği anlamına gelir. Çöken bir
    koşuda o iddia edilemez — kanıt depoda duruyor, ama teslim edilen paket
    kendini ölçülmüş gibi göstermiyor.
    """
    output = build_output(store, summary=summary)
    output.detail = None
    return output


def run_pipeline(video_path, store=None, gw=None, nobetci=None,
                 on_message=None,
                 output_dir=None) -> tuple[PipelineOutput, Path]:
    """Videoyu baştan sona işler ve şartnamenin dört anahtarını döndürür.

    `store` ve `gw` verilmezse burada kuruluyor: `benchmark/run.py` yalnız
    `store` geçiyor ve `gw=None` bir dereference olurdu.

    `nobetci` verilmezse koşu **headless**: yükseltme anları operatöre
    duyurulmaz ama epizotlar, riskler ve aksiyonlar aynen üretilir — ölçüm
    koşusu (Görev 15) tam olarak böyle koşuyor.

    Algı katmanı bilerek `try`'ın DIŞINDA: okunamayan bir video bozulmuş bir
    koşu değil, hiç koşu değildir. Benchmark o çöküşü klip kaydına yazıyor.
    """
    store = store if store is not None else Store()
    gw = gw if gw is not None else Gateway(store)
    output_dir = Path(output_dir or tempfile.mkdtemp(prefix="gozcu-frames-"))

    frames = extract_frames(video_path, output_dir)
    tracked = track_video([frame.path for frame in frames])
    signals = compute_signals(tracked, [frame.timestamp_s for frame in frames])

    observations = [to_observation(frame.timestamp_s, frame_tracks,
                                   frame_signals)
                    for frame, frame_tracks, frame_signals
                    in zip(frames, tracked, signals, strict=True)]
    for observation in observations:
        store.save_observation(observation)

    # Arşiv tohumlaması koşudan ÖNCE yapılıyor; o epizotlar bu videonun
    # tespiti değil ve ne risk analizine ne de kök neden raporu kararına girer.
    archived = {episode.id for episode in store.episodes()}
    summary = EMPTY_SUMMARY
    root_cause = None
    try:
        loop = DecisionLoop(
            store,
            route=lambda window: route(gw, window,
                                       store.open_episode() is not None),
            # Klip pencere başına bir kez kesiliyor; kapanış döngü kurulurken
            # bir kez üretilir.
            interpret=partial(interpret, gw, store,
                              clip_for=_clip_for(video_path)),
            synthesize=lambda window, interpretation, decision: synthesize(
                gw, store, window, interpretation, decision,
                on_close=lambda episode: _on_close(gw, store, episode)),
            # Çıplak `gw.is_degraded` değil: o "herhangi bir kademe" demek ve
            # `rerank`'ın beklenen 400'ü her pencereyi sonsuza dek erteletir.
            is_degraded=lambda: gw.is_degraded("vlm"))

        for event in loop.run(observations):
            if nobetci is not None:
                _announce(store, nobetci, event, on_message)

        fresh = [episode for episode in store.episodes()
                 if episode.id not in archived]
        _sweep_unassessed(gw, store, fresh)
        if fresh:
            root_cause = generate_root_cause_report(gw, store)
            summary = root_cause.what_happened
    except Exception:  # noqa: BLE001 — bozulmuş koşu da geçerli çıktı vermeli
        return (screen_delivery(gw, _degraded_output(store, summary)).output,
                output_dir)

    # Teslimden hemen önceki tek denetim çağrısı (Görev 13). Denetim yükü
    # hiçbir koşulda boşaltmıyor; uygunsuz hükmünde bile yalnız bir not
    # ekleniyor ve teslim asla engellenmiyor.
    output = build_output(store, summary=summary, root_cause=root_cause)
    return screen_delivery(gw, output).output, output_dir
```

`_clip_for(video_path, out_dir=None)` Görev 04'ün beklediği kapanış — **klip
üretimi bu görevin sorumluluğu**, tıpkı eskiden kare üretimi olduğu gibi.
Yorumlayıcı ffmpeg'i hiç görmüyor, o yüzden orası ffmpeg olmadan test
edilebiliyor.

Kesme reçetesi, canlı ölçülen biçimin aynısı
([EVREN saha notları](../06-references/evren-gateway.md)):

```bash
ffmpeg -y -ss "$start" -t "$span" -i "$video" \
       -vf scale=1280:-2 -c:v libx264 -an "$out"
```

`-c:v libx264` H.264 üretiyor — gateway'e giden `data:video/mp4;base64,…`
yükünün çözülebilmesi için gereken şey bu. `-an` ses akışını atıyor: model
sesi kullanmıyor, taşımak yalnız base64 boyutunu şişirir. Ölçek klibin kendi
işi; `FRAME_WIDTH` algı katmanının kare genişliği, klibe karışmıyor.

Klipler tıpkı kareler gibi **geçici artefakt**: varsayılan `tempfile.mkdtemp`
depo ağacının dışına, `out_dir` verilirse çağıranın verdiği dizine düşer.
**Hiçbir klip commit edilmez** — yeniden üretilebilir ikili dosyalar. Kesme
başarısız olduğunda dönen `None` bir **atlanan pencere**, kesinti değil:
ffmpeg'in kurulu olmaması (`OSError`), sıfır olmayan çıkış kodu ve boş çıkan
dosya aynı sessiz dala düşüyor.

**Tavanlar bir pencereyi asla ıskalamıyor.** `vlm` videoyu 2,0 fps ile ve en
fazla 520 kare örnekliyor, süre tavanı 260 s. 10 saniyelik bir pencere bunların
çok içinde kalıyor (20 kare, 10 s) — yani pencere başına kesilen bir klip hiçbir
tavana çarpmaz. Çarpma riski yalnızca birisi pencereleri birleştirmeye kalkarsa
doğar; o da zaten çözünürlük gerekçesiyle reddedildi.

**`app.py` bu görevde yeniden yazılmadı.** 17'nin `events`'i artık kare başına
değil epizot başına ve `EventSummary(time, event)` şeklinde; `app.py` yalnızca
o yeni şekle uyarlandı ki arayüz çalışır kalsın (`84286e8`). Dosyanın tamamını
[Görev 16](16-konsol.md) değiştiriyor ve sonunda üç satır kalıyor:

```python
from gozcu.ui.console import baslat

if __name__ == "__main__":
    baslat()
```

### 7. Yeşil olduğunu gör

```bash
uv run pytest tests/ -v
```
Beklenen: hepsi yeşil.

### 8. Uçtan uca dene

```bash
uv run python app.py
```

Bir klip yükle. Dört anahtarlı JSON çıkmalı.

### 9. Commit

```bash
git add gozcu/adapter.py gozcu/report.py gozcu/run.py \
        tests/test_report.py tests/test_run.py
git rm gozcu/interpret.py gozcu/schema.py
git commit -m "feat: wire the pipeline end to end behind the four-key contract"
```

## Doğrulama

```bash
uv run pytest tests/test_report.py tests/test_run.py -q && uv run pytest tests/ -q
```
Beklenen: **33 passed** ve tüm suite yeşil. (Dosya başına: `test_report.py` on
üç, `test_run.py` yirmi test.)

## Tamamlanma notları (gelecek görevleri bağlayan)

- **İmza:** `run_pipeline(video_path, store=None, gw=None, nobetci=None,
  on_message=None, output_dir=None) -> tuple[PipelineOutput, Path]`. `store` ve
  `gw` verilmezse fonksiyon kendi `Store()`'unu ve `Gateway(store)`'unu kuruyor
  — `benchmark/run.py` yalnız `store=` geçiyor, `gw` geçmiyor ve varsayılan
  `None` bir dereference olurdu.
- **`assess_risk` epizot kapanışında, `on_close` üzerinden çağrılıyor.** Önceki
  taslakta yalnızca belgelenmişti; kod onu hiç çağırmıyordu. Sonucu: `store.risks()`
  her headless koşuda boş kalıyor, `actions[]` kalıcı olarak `[]` oluyor ve `risk`
  sessizce `preliminary_risk`'e düşüyordu — şartnamenin dört anahtarından ikisi
  içi boş, üstelik hiçbir test ve hiçbir koşu bunu bildirmeden. Koşu sonunda
  ayrıca bir **süpürme** var: video bitene kadar açık kalmış epizotlar da
  değerlendirmesiz bırakılmıyor. Koşudan önce tohumlanmış **arşiv epizotları
  ikisinin de dışında** — onlar bu videonun tespiti değil.
- **Bozulma ile çöküş ayrı şeyler.** Tamamen bozulmuş (`degraded`) bir koşu dört
  anahtarı **dolu bir `detail` ile** döndürüyor: o katmanlar koştu ve hiçbir şey
  bulamadı. Çöken genişletilmiş yol ise dört anahtarı `detail=None` ile
  döndürüyor. Yani **dolu bir `detail` "genişletilmiş katmanlar gerçekten koştu"
  demek** ve çöken bir koşuda bu iddia edilmiyor.
- **`_clip_for(video_path, out_dir=None)`** kesme reçetesi:
  `ffmpeg -y -ss -t -i -vf scale=1280:-2 -c:v libx264 -an`. Sıfır süreli pencere
  `1.0 / FRAME_FPS` tabanına oturtuluyor. Klipler depo ağacının dışındaki geçici
  bir dizine düşüyor ve **hiçbir zaman commit edilmiyor**. `OSError`, sıfır
  olmayan çıkış kodu ve boş dosya `None` veriyor; `None` bir **atlanan
  penceredir, kesinti değil** — erteleme yalnız `gw.is_degraded("vlm")` için.
- **`store.save_observation` sistemdeki tek gözlem yazıcısı** ve
  `kpi.vlm_trigger_rate` paydasını oradan alıyor ([Görev 15](15-kpi.md)).
  Kaldırılırsa oran sessizce `null` okur.
- **`Episode.start_ts` video saniyesi olarak kalıyor.** Benchmark epoch
  ölçeğindeki bir damgayı ölçmek yerine hataya düşürüyor ([Görev
  15](15-kpi.md)).
- **`gozcu/interpret.py` ve `gozcu/schema.py` silindi.** Tek çağıranları
  `run.py`'dı; yeniden yazımla birlikte öksüz kaldılar.
- **`build_output` `actions[]`'ı `TOOLS`'a karşı ikinci kez süzüyor.** Risk
  analisti uydurma araç adlarını zaten düşürüyor; buradaki süzgeç depoya başka
  bir yoldan (arşiv tohumlaması, elle yazılmış fikstür) girmiş bir öneriyi de
  kapsıyor — eşlenmemiş bir aksiyon jüriye giden listeye giremez.
- **`app.py` [Görev 16](16-konsol.md)'nın.** Şu an yalnızca yeni
  `EventSummary(time, event)` şekline asgari uyarlanmış hâlde (`84286e8`), tek
  amacı arayüzün çalışır kalması. 16 dosyayı **bütünüyle** değiştiriyor: üç
  satırlık giriş noktası, `PipelineOutput` üzerine kurulu konsol, `on_message`
  tüketimi (geç telafi edilen olaylar `run.LATE_NOTICE` ile **önceden**
  damgalanmış geliyor) ve `nobetci` olarak geçilen bir `Supervisor`.
