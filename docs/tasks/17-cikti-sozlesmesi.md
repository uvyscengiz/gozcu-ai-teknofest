# Görev 17 — Çıktı sözleşmesi ve entegrasyon (`gozcu/report.py`, `gozcu/run.py`)

**Sahip:** `uvyscengiz` · **Gün:** 26 Ağustos sabahı · **Süre:** ~3 saat
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

`run_pipeline(video_path)` artık: kare çıkar → `Observation` üret → `DecisionLoop`
kur → koştur → `build_output` döndür.

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

> **Görev 04 bağlama uyarısı (üç madde).**
> 1. `interpret` da aynı şekilde bağlanıyor:
>    `interpret=partial(interpret, gw, store, frame_for=_frame_for(frames))`.
>    Döngü ona tek argüman (`window`) veriyor.
> 2. `frame_for` bir zaman damgasını `frames.py`'ın ürettiği bir kareye
>    çözmek zorunda. Adaptör artık pencere başına **üç** zaman damgası soruyor
>    (ilk / orta / son), tek kare değil — kapanış her üçü için de çalışmalı,
>    bulunamayanı `None` dönmeli.
> 3. `run.py` yeniden yazıldığı an `gozcu/interpret.py` ve `gozcu/schema.py`
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
from gozcu.adapter import to_observation
from gozcu.models import (ProposedAction, ActionRecord, Episode, RiskAssessment)
from gozcu.report import build_output
from gozcu.store import Store


class _FS:
    def __init__(self, **kw):
        self.velocities = kw.get("velocities", {})
        self.vanished_tracks = kw.get("vanished_tracks", [])
        self.person_count = kw.get("person_count", 0)
        self.person_count_delta = kw.get("person_count_delta", 0)


def test_four_keys_exist_even_with_a_completely_empty_run():
    c = build_output(Store(":memory:"), summary="Kayda değer olay yok.")
    d = c.model_dump(exclude_none=True)
    assert {"summary", "events", "risk", "actions"} <= set(d)
    assert d["risk"] == "Düşük"


def test_events_use_mmss_and_come_from_episodes():
    store = Store(":memory:")
    store.create_episode(Episode(start_ts=15.0, phase="onset",
                           summary_tr="İstif aracı devrildi", preliminary_risk="Yüksek"))
    c = build_output(store, summary="ö")
    assert c.events[0].time == "00:15"
    assert c.events[0].event == "İstif aracı devrildi"


def test_overall_risk_is_the_highest_assessed_level():
    store = Store(":memory:")
    for level in ("Düşük", "Kritik", "Orta"):
        store.save_risk(RiskAssessment(episode_id=1, level=level,
                                            rationale_tr="g", preventable=True))
    assert build_output(store, summary="ö").risk == "Kritik"


def test_risk_falls_back_to_episode_preliminary_when_no_assessment_exists():
    store = Store(":memory:")
    store.create_episode(Episode(start_ts=0.0, phase="development", summary_tr="x",
                           preliminary_risk="Yüksek"))
    assert build_output(store, summary="ö").risk == "Yüksek"


def test_actions_are_rendered_from_tool_backed_candidates_only():
    store = Store(":memory:")
    store.save_risk(RiskAssessment(
        episode_id=1, level="Kritik", rationale_tr="g", preventable=True,
        proposed_actions=[ProposedAction(description_tr="Sağlık ekibini çağır",
                                     tool_name="dispatch_medical")]))
    assert build_output(store, summary="ö").actions == ["Sağlık ekibini çağır"]


def test_duplicate_actions_are_not_repeated():
    store = Store(":memory:")
    for _ in range(3):
        store.save_risk(RiskAssessment(
            episode_id=1, level="Orta", rationale_tr="g", preventable=True,
            proposed_actions=[ProposedAction(description_tr="Alanı güvenlik altına al",
                                         tool_name="site_alarm")]))
    assert build_output(store, summary="ö").actions == [
        "Alanı güvenlik altına al"]


def test_detail_block_is_attached_but_never_replaces_the_four_keys():
    store = Store(":memory:")
    store.save_action(ActionRecord(ts=1.0, tool_name="site_alarm",
                                      params={}, result={}, actor="agent",
                                      approval="not_required"))
    c = build_output(store, summary="ö")
    assert c.detail is not None and len(c.detail.action_ledger) == 1
    assert c.summary == "ö"


def test_adapter_derives_gathering_from_person_count():
    g = to_observation(1.0, [], _FS(person_count=3))
    assert g.signals.gathering is True
    assert to_observation(1.0, [], _FS(person_count=2)).signals.gathering is False


def test_adapter_keeps_the_person_count_delta():
    g = to_observation(1.0, [], _FS(person_count=4, person_count_delta=2))
    assert g.signals.person_count_delta == 2


def test_adapter_maps_velocities_and_vanished_tracks():
    g = to_observation(2.0, [], _FS(velocities={7: 3.1}, vanished_tracks=[9]))
    assert g.signals.velocities == {7: 3.1}
    assert g.signals.vanished_tracks == [9]
    assert g.ts == 2.0
```

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_report.py -v
```
Beklenen: `ModuleNotFoundError`

### 3. `gozcu/adapter.py` yaz

```python
from gozcu.models import Observation, Signals, Detection

GATHERING_THRESHOLD = 3


def to_observation(frame_ts: float, detections, frame_signals) -> Observation:
    """Donuk algı katmanının çıktısını ajan katmanının tipine çevirir.

    `gathering` signals.py'da hesaplanmıyor — burada kişi sayısından
    türetiliyor. Eşiği aşan kişi sayısı `gathering` sayılıyor; bu bir
    heuristik ve yönlendiriciye sadece bir sinyal olarak gidiyor, karar
    olarak değil.
    """
    return Observation(
        ts=frame_ts,
        detections=[Detection(label=t.class_name, confidence=getattr(t, "confidence", 1.0),
                          box=tuple(float(v) for v in t.bbox),
                          track_id=getattr(t, "track_id", None))
                   for t in detections],
        signals=Signals(
            velocities=dict(frame_signals.velocities),
            vanished_tracks=list(frame_signals.vanished_tracks),
            person_count=frame_signals.person_count,
            person_count_delta=frame_signals.person_count_delta,
            gathering=frame_signals.person_count >= GATHERING_THRESHOLD))
```

### 4. `gozcu/report.py` yaz

```python
from gozcu.agents.router import mmss
from gozcu.models import Detail, EventSummary, PipelineOutput, RiskLevel

ORDER: list[RiskLevel] = ["Düşük", "Orta", "Yüksek", "Kritik"]


def build_output(store, summary: str, root_cause=None) -> PipelineOutput:
    """Şartnamenin dört anahtarını üretir; her şey detail altında yanına
    eklenir, yerine değil."""
    episodes = store.episodes()
    risks = store.risks()

    events = [EventSummary(time=mmss(e.start_ts), event=e.summary_tr[:200])
              for e in episodes]

    seviyeler = [r.level for r in risks] or [e.preliminary_risk for e in episodes]
    risk = max(seviyeler, key=ORDER.index) if seviyeler else "Düşük"

    # Sadece araca bağlanmış adaylardan; böylece insanın okuduğu liste ile
    # makinenin aksiyon defteri birbirinden ayrışamaz.
    actions: list[str] = []
    for r in risks:
        for a in r.proposed_actions:
            if a.description_tr not in actions:
                actions.append(a.description_tr)

    return PipelineOutput(
        summary=summary, events=events, risk=risk, actions=actions,
        detail=Detail(
            episodes=episodes,
            risk_assessments=risks,
            handoff_chain=store.handoffs(),
            action_ledger=store.actions(),
            root_cause_report=root_cause.model_dump() if root_cause else None))
```

### 5. `gozcu/run.py` yeniden yaz

```python
def run_pipeline(video_path, store=None, gw=None, nobetci=None):
    """Uçtan uca akış. Genişletilmiş katman çökse bile dört anahtarlı geçerli
    bir çıktı döner — bozulmuş bir koşu da notlandırılabilir olmalı."""
    frames = extract_frames(video_path, output_dir)
    tracked = track_video([f.path for f in frames])
    signals = compute_signals(tracked, [f.timestamp_s for f in frames])

    observations = [to_observation(f.timestamp_s, t, s)
                 for f, t, s in zip(frames, tracked, signals, strict=True)]
    for g in observations:
        store.save_observation(g)

    summary = "Kayda değer olay tespit edilmedi."
    root_cause = None
    try:
        loop = DecisionLoop(store,
                             route=lambda p: route(
                                 gw, p, store.open_episode() is not None),
                             interpret=lambda p: interpret(
                                 gw, store, p, _frame_for(frames)),
                             synthesize=lambda p, y, k: synthesize(
                                 gw, store, p, y, k,
                                 on_close=lambda e: embed_episode(gw, store, e)),
                             # Çıplak gw.is_degraded değil: sadece görü kademesi.
                             is_degraded=lambda: gw.is_degraded("vlm"))
        for event in loop.run(observations):
            if nobetci is not None:
                message = nobetci.escalate(event.episode)
                if event.late:
                    # Kesinti telafisinden geldi: duyur, ama canlı kriz gibi değil.
                    message = f"[Telafi — kesinti sırasında atlanmıştı] {message}"
        if store.episodes():
            root_cause = generate_root_cause_report(gw, store)
            summary = root_cause.what_happened
    except Exception:  # noqa: BLE001 — bozulmuş koşu da geçerli çıktı vermeli
        return screen_delivery(
            gw, build_output(store, summary=summary)).output, output_dir

    # Teslimden hemen önceki tek denetim çağrısı (Görev 13). Denetim çökerse
    # paket olduğu gibi döner; teslim asla engellenmez.
    output = build_output(store, summary=summary, root_cause=root_cause)
    return screen_delivery(gw, output).output, output_dir
```

`_frame_for(frames)` Görev 04'ün beklediği kapanış. Tanımı:

```python
def _frame_for(frames):
    """Bir ts alıp o ana en yakın karenin dosya yolunu döndüren kapanış."""
    ordered = sorted(frames, key=lambda f: f.timestamp_s)

    def pick(ts: float):
        if not ordered:
            return None
        return min(ordered, key=lambda f: abs(f.timestamp_s - ts)).path

    return pick
```

`app.py` üç satırlık giriş noktası olarak kalsın:

```python
from gozcu.ui.console import baslat

if __name__ == "__main__":
    baslat()
```

### 6. Yeşil olduğunu gör

```bash
uv run pytest tests/ -v
```
Beklenen: hepsi yeşil.

### 7. Uçtan uca dene

```bash
uv run python app.py
```

Bir klip yükle. Dört anahtarlı JSON çıkmalı.

### 8. Commit

```bash
git add gozcu/report.py gozcu/adapter.py gozcu/run.py app.py tests/test_report.py
git commit -m "feat: şartname output contract with detail block and safe fallback"
```

## Doğrulama

```bash
uv run pytest tests/test_report.py -v && uv run pytest tests/ -q
```
Beklenen: **10 passed** ve tüm suite yeşil.
