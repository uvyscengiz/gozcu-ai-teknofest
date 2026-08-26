# 26 Ağustos Dürüstlük Onarımları — Uygulama Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 26 Ağustos canlı koşusunun beş yalanını (arıza metni uydurması, çalışmayan sirenler, yükseltme fırtınası, kazasız `events[]`, arıza kaydı `summary`) kaynağında onarmak.

**Architecture:** Yedi bağımsız iş kalemi; çoğu silme ve sabit değişimi. Tek davranışsal değişiklik süpervizörün iki kipli yükseltmesi. Döngü (`DecisionLoop`) DEĞİŞMİYOR.

**Tech Stack:** Python 3.12, pydantic v2, pytest, uv. Model çağrıları `gozcu.gateway.Gateway` üzerinden.

**Spec:** `docs/superpowers/specs/2026-08-26-run-truthfulness-fixes-design.md` — her görev spec'in bir bölümünü uygular; görev metninde §N o belgeye gönderme.

## Global Constraints

- Kod İngilizce; insana görünen her metin (promptlar, sabit mesajlar, yorumlar) Türkçe. (CLAUDE.md)
- Çıktı sözleşmesi `summary` · `events` · `risk` · `actions` her koşuda üretilir; fazlası `detail` altında.
- Model kimlikleri yalnız `gozcu/config.py`'da.
- TDD: önce test, kırmızı gör, sonra minimum kod. Her görev kendi commit'iyle biter.
- Testler `uv run pytest tests/ -v` ile koşar (çalışma dizini depo kökü).
- `DecisionLoop`'a ve tek-açık-epizot değişmezine (`_resolve`) DOKUNULMAZ.

---

### Task 1: Token politikası — tek cömert sigorta, genişletme-tekrarı silinir (§5)

**Files:**
- Modify: `gozcu/config.py` (SCHEMA_MAX_TOKENS bloğu ~143-173)
- Modify: `gozcu/gateway.py` (import ~12-13, widen dalı ~261-278)
- Modify: `gozcu/agents/reporter.py` (`generate_root_cause_report`, ~338)
- Test: `tests/test_gateway.py`, `tests/test_reporter.py`

**Interfaces:**
- Consumes: mevcut `Gateway.ask(tier, messages, schema=, tools=, max_tokens=, ...)`.
- Produces: `config.SCHEMA_MAX_TOKENS == 8192`; `SCHEMA_WIDEN_FACTOR` ARTIK YOK; `reporter.REPORT_MAX_TOKENS = 16384`. Sonraki görevler gateway'de tek deneme varsayar.

- [ ] **Step 1: Kırmızı testleri yaz.** `tests/test_gateway.py` içinde `test_an_empty_truncated_schema_call_is_retried_with_a_wider_budget` (satır ~424) ve `test_the_widened_retry_happens_only_once` (satır ~442) testlerini SİL; yerlerine şunu ekle (dosyadaki mevcut sahte-istemci desenini kullan — komşu testler `monkeypatch` ile `self._client.chat.completions.create`'i sayaçlı sahteyle değiştiriyor, aynısını kopyala):

```python
def test_an_empty_truncated_schema_call_is_not_retried(monkeypatch):
    """Bütçe tükenirse İKİNCİ deneme YOK: tek cömert sigorta (spec §5)."""
    gw, calls = _gateway_with_counting_client(
        monkeypatch, finish_reason="length", content="")
    response = gw.ask("fast", [{"role": "user", "content": "x"}],
                      schema=_Shape)
    assert len(calls) == 1, "genişletme-tekrarı silindi; tek çağrı olmalı"
    assert response.content == ""
    assert response.truncated is True


def test_the_default_schema_ceiling_is_generous():
    from gozcu.config import SCHEMA_MAX_TOKENS
    assert SCHEMA_MAX_TOKENS == 8192
```

(`_gateway_with_counting_client` ve `_Shape` dosyada yoksa, ~401'deki `test_a_budget_exhausted_reply_is_not_reported_as_silence` testinin kurduğu sahteyi bir yardımcıya çıkar ve iki testte de kullan. `truncated` özelliği `Response`'ta zaten var.)

`tests/test_reporter.py`'a ekle — dosyanın GERÇEK yardımcıları `_seeded_store()` ve `_gw()` (Mock tabanlı); yakalama `call_args` ile:

```python
def test_the_reporter_passes_its_own_generous_ceiling():
    gw = _gw('{"what_happened": "x", "probable_root_cause": "y", '
             '"confidence_limits": "z"}')
    generate_root_cause_report(gw, _seeded_store())
    assert gw.ask.call_args.kwargs.get("max_tokens") == 16384
```

(`_gw`'nin dosyadaki gerçek imzasına uy; `ask` bir Mock değilse çağrı kwargs'ını kaydeden ince bir sarmalayıcı yaz.)

- [ ] **Step 2: Kırmızıyı doğrula.** `uv run pytest tests/test_gateway.py tests/test_reporter.py -v` — yeni üç test FAIL (retry hâlâ var, tavan 2048, reporter max_tokens geçmiyor).

- [ ] **Step 3: Uygula.**
  - `gozcu/config.py`: `SCHEMA_MAX_TOKENS` varsayılanı `"2048"` → `"8192"`. Bloğun yorumunu güncelle: 2048'in ölçülen yetersizliği (26 Ağu: sentezleyici pencerelerin ~%60'ında tükendi, raportör 4096'da da tükendi) ve genişletme-tekrarının neden silindiği (iki mekanizmanın bileşimi pencere başına 20-50 s ikinci deneme üretti; tavan tükenmedikçe bedava — sigorta, bütçe değil). `SCHEMA_WIDEN_FACTOR` bloğunu (satır ~162-173) tamamen SİL.
  - `gozcu/gateway.py`: import listesinden `SCHEMA_WIDEN_FACTOR`'ı çıkar; `ask` içindeki genişletme dalını (`if (finish == "length" ...` bloğu, ~261-278, üstündeki "Kurtarılabilir arıza" yorumu dâhil) SİL. `finish` değişkeni `Response`'a aynen gitmeye devam eder.
  - `gozcu/agents/reporter.py`: modül sabiti ekle ve çağrıya geçir:

```python
#: Raportörün kendi tavanı. Koşu başına BİR kez çalışır, girdisi en büyük
#: prompt (epizotlar + riskler + defter + diyalog) ve 26 Ağustos'ta 4096'yı
#: da tükettiği ölçüldü. Burada duruyor ki iki çağıran da — boru hattı ve
#: süpervizörün GENERATE_ROOT_CAUSE_REPORT iç aracı — aynı tavanı alsın.
REPORT_MAX_TOKENS = 16384
```

```python
    response = gw.ask("main", [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _prompt(store)},
    ], schema=RootCauseReport, max_tokens=REPORT_MAX_TOKENS)
```

- [ ] **Step 4: Yeşili doğrula.** `uv run pytest tests/test_gateway.py tests/test_reporter.py -v` — hepsi PASS.

- [ ] **Step 5: Commit.** `git add -A && git commit -m "feat(gateway): genişletme-tekrarı silindi — tek cömert sigorta (8192/16384)"`

---

### Task 2: Sentezleyici karantinası — arıza metni devam-eden-olay olarak anlatılmaz; yedek, model kaydını ezmez (§1)

**Files:**
- Modify: `gozcu/agents/synthesizer.py` (`_digest` ~103-122, `synthesize` güncelleme dalı ~273-282)
- Test: `tests/test_synthesizer.py`

**Interfaces:**
- Consumes: `Episode.summary_source` (`"model" | "fallback"`, `gozcu/models.py:123`).
- Produces: `synthesizer.FALLBACK_CONTINUATION` sabiti; güncelleme dalında ezme koruması. Task 3-4 aynı `summary_source` desenini kopyalar.

- [ ] **Step 1: Kırmızı testleri yaz** (`tests/test_synthesizer.py`; dosyanın mevcut sahte-gateway/depo kurulumunu kullan):

```python
def test_a_fallback_summary_never_reenters_the_prompt_as_an_event():
    """Spec §1: 'Sentez üretilemedi' bir olay tarifi değildir."""
    previous = Episode(start_ts=0.0, phase="development",
                       summary_tr=UNREADABLE_SUMMARY,
                       preliminary_risk="Orta", summary_source="fallback")
    text = _digest(_window(start=0.0), None, previous)
    assert UNREADABLE_SUMMARY not in text
    assert "tarif üretilemedi" in text  # nötr işaret satırı var


def test_a_fallback_synthesis_does_not_overwrite_a_model_summary():
    """Spec §1 kaynaşma koruması: son pencere arızalansa da model özeti yaşar."""
    store = Store(":memory:")
    good = '{"phase": "development", "summary_tr": "Forklift devrildi.", "participants": ["IST-07"], "preliminary_risk": "Yüksek"}'
    synthesize(_FakeGateway(good), store, _window(start=0.0), None,
               "open_episode")

    window = _window(start=10.0)
    episode = synthesize(_FakeGateway(""), store, window, None,
                         "update_episode")     # boş yanıt → fallback
    assert episode.summary_tr == "Forklift devrildi."
    assert episode.summary_source == "model"
    assert episode.participants == ["IST-07"]
    assert episode.preliminary_risk == "Yüksek"
    assert episode.end_ts == window[-1].ts     # kaynaşma normal işledi
```

(Dosyanın gerçek yardımcıları: `_window(start=..., count=...)` ve sahte gateway sınıfı — dosyada `_FakeGateway` benzeri hangi ad varsa ONU kullan, imzasına uy; buradaki adlar niyet gösterimi. İkinci testte model kaydı için sahteye GEÇERLİ JSON verildiğine dikkat.)

- [ ] **Step 2: Kırmızıyı doğrula.** `uv run pytest tests/test_synthesizer.py -v -k "fallback"` — iki test FAIL.

- [ ] **Step 3: Uygula** (`gozcu/agents/synthesizer.py`):

Sabit (yedek özet sabitlerinin yanına):

```python
#: Yedek özetli bir epizodun devam satırı. Arıza metni ("Sentez üretilemedi…")
#: bir kez prompt'a olay tarifi olarak girdi ve model onu fabrikada duran bir
#: "sentez hattı"na çevirdi (26 Ağu canlı koşu). Arıza metni bir olay tarifi
#: DEĞİLDİR ve modele öyle anlatılmaz.
FALLBACK_CONTINUATION = ("DEVAM EDEN OLAY: (tarif üretilemedi — önceki "
                         "pencerenin sentezi arızalandı; olayı aşağıdaki "
                         "gözlemlerden yeniden kur)")
```

`_digest` içinde (satır ~120-121):

```python
    if previous is not None:
        line = (FALLBACK_CONTINUATION
                if previous.summary_source == "fallback"
                else f"DEVAM EDEN OLAY: {previous.summary_tr}")
        lines.insert(0, line)
```

`synthesize` güncelleme dalında, `fields` sözlüğü kurulduktan hemen sonra (satır ~274-279):

```python
        # Yedek, model kaydını EZMEZ (spec §1): son penceresi arızalanan bir
        # epizot, ömrü boyunca taşıdığı model özetini kapanış anında bir arıza
        # metnine kaybederdi — ve gömme koruması onu arşivden tamamen düşürürdü.
        # participants/preliminary_risk de korunuyor: yedek yanıt onları
        # varsayılandan ([], "Orta") doldurur, yani ezmek aynı bilgiyi siler.
        if (synthesis.summary_source == "fallback"
                and open_episode.summary_source == "model"):
            for key in ("summary_tr", "summary_source", "participants",
                        "preliminary_risk"):
                fields.pop(key, None)
```

- [ ] **Step 4: Yeşili doğrula.** `uv run pytest tests/test_synthesizer.py -v` — tümü PASS (mevcutlar dâhil).

- [ ] **Step 5: Commit.** `git commit -am "fix(sentez): arıza metni devam-eden-olay olarak anlatılmıyor; yedek model kaydını ezmiyor"`

---

### Task 3: Risk analisti karantinası — arıza metniyle ne analiz ne arşiv araması (§1)

**Files:**
- Modify: `gozcu/agents/risk.py` (`_prompt` ~273-281, `assess_risk` arama ~295-298)
- Test: `tests/test_risk.py`

**Interfaces:**
- Consumes: `Episode.summary_source`, `Episode.beats` (`EventBeat.ts/.text`), `router.mmss`.
- Produces: `_prompt(episode, history_text, correction_text)` imzası aynı kalır; davranış `summary_source`'a duyarlı.

- [ ] **Step 1: Kırmızı testleri yaz** (`tests/test_risk.py`; dosyanın mevcut sahte-gateway desenini kullan):

```python
def test_a_fallback_summary_is_not_presented_as_the_event(fallback_episode):
    text = _prompt(fallback_episode, "- (kayıt yok)", "")
    assert "Sentez üretilemedi" not in text
    assert "olay tarifi üretilemedi" in text
    assert "00:35" in text  # ham anlar prompta girdi


def test_the_archive_is_not_searched_with_a_fault_text(store, fallback_episode, monkeypatch):
    queries = []
    monkeypatch.setattr("gozcu.agents.risk.search_timeline",
                        lambda gw, store, q, **kw: queries.append(q) or [])
    assess_risk(_quiet_gateway(), store, fallback_episode)
    assert all("Sentez üretilemedi" not in q for q in queries)
```

Kurulum, dosyanın ev deseniyle (fixture yerine yardımcı — `tests/test_risk.py`'da `store` fixture'ı YOK, depo satır içi kurulur):

```python
def _fallback_episode(store):
    episode = Episode(
        start_ts=30.0, end_ts=45.0, phase="development",
        summary_tr="Sentez üretilemedi; ham gözlemler kayıtlı.",
        preliminary_risk="Orta", summary_source="fallback",
        beats=[EventBeat(ts=35.0, text="Forklift kamyona temas etti.")])
    episode.id = store.create_episode(episode)
    return episode
```

Her test kendi `Store(":memory:")`'sini kurar ve `_fallback_episode(store)` çağırır; sahte gateway için dosyadaki mevcut yardımcıyı kullan.

- [ ] **Step 2: Kırmızıyı doğrula.** `uv run pytest tests/test_risk.py -v -k "fallback or fault"` — FAIL.

- [ ] **Step 3: Uygula** (`gozcu/agents/risk.py`). Import'lara `from gozcu.agents.router import mmss` ekle. `_prompt` başı:

```python
def _prompt(episode: Episode, history_text: str, correction_text: str) -> str:
    participants = ", ".join(episode.participants) or "(bilinmiyor)"
    if episode.summary_source == "fallback":
        # Arıza metni bir olay tarifi değildir (spec §1): analiz yedek özete
        # değil, yorumlayıcının GERÇEK çıktısı olan ham anlara dayanır.
        lines = ["OLAY: (olay tarifi üretilemedi; aşağıdaki ham anlara dayan)"]
        lines += [f"- {mmss(beat.ts)} {beat.text}" for beat in episode.beats]
    else:
        lines = [f"OLAY: {episode.summary_tr}"]
    lines += [f"ÖN RİSK: {episode.preliminary_risk}",
              f"KATILIMCILAR (ekipman/personel kimlikleri): {participants}"]
    if correction_text:
        lines.append(correction_text)
    lines.append(f"\nARŞİV:\n{history_text}")
    return "\n".join(lines)
```

`assess_risk` başındaki arama (satır ~295-298):

```python
    if episode.summary_source == "fallback":
        # Arşiv arıza metniyle aranmaz — 26 Ağu koşusunda o metin gömüldü ve
        # emsal araması zehirlendi. Anlar gerçek gözlem; an yoksa arama yok.
        query = " ".join([*(beat.text for beat in episode.beats),
                          *episode.participants]).strip()
    else:
        query = f"{episode.summary_tr} {' '.join(episode.participants)}"
    history = (search_timeline(gw, store, query, exclude_id=episode.id)
               if query else [])
```

- [ ] **Step 4: Yeşili doğrula.** `uv run pytest tests/test_risk.py -v` — tümü PASS.

- [ ] **Step 5: Commit.** `git commit -am "fix(risk): yedek özet analize ve arşiv aramasına olay diye girmiyor"`

---

### Task 4: Kalan dört tüketici — talk hatırlatması, rapor kanıt dosyası, events[], gömme (§1)

**Files:**
- Modify: `gozcu/agents/supervisor.py` (`talk` ~470-486)
- Modify: `gozcu/agents/reporter.py` (`_prompt` OLAY ZİNCİRİ ~255-256)
- Modify: `gozcu/report.py` (`_events` ~128-137)
- Modify: `gozcu/memory.py` (`embed_episode` ~175-185)
- Test: `tests/test_supervisor.py`, `tests/test_reporter.py`, `tests/test_report.py`, `tests/test_memory.py`

**Interfaces:**
- Consumes: `Episode.summary_source`, `Episode.beats`, `mmss` (reporter zaten import ediyor).
- Produces: `supervisor.FALLBACK_REMINDER`, `report.FALLBACK_EVENT` sabitleri.

- [ ] **Step 1: Kırmızı testleri yaz.** Dört dosyaya birer test (kurulum olarak Task 3'teki `_fallback_episode` biçimini her dosyada yerel kur). **Kırmızı fazda toplama hatasına dikkat:** `FALLBACK_EVENT`, `FALLBACK_REMINDER` gibi henüz VAR OLMAYAN sabitleri modül tepesinden import etme — bütün dosya toplama aşamasında patlar ve öbür testleri de düşürür; import'u testin İÇİNE yaz (yeşil fazdan sonra tepeye taşınabilir):

```python
# tests/test_supervisor.py — mevcut sahte-gateway desenini kullan
def test_the_open_episode_reminder_does_not_carry_a_fault_text(...):
    # depoya summary_source="fallback" epizot yaz; nobetci.talk("durum ne?")
    # sonra history'deki son user mesajında:
    assert "Sentez üretilemedi" not in last_user_message
    assert "tarif üretilemedi" in last_user_message
    assert "episode 1" in last_user_message   # kimlik kalıyor

# tests/test_reporter.py
def test_the_evidence_file_does_not_carry_a_fault_text_as_an_event(store):
    # depoya fallback epizot (beats'li) yaz; text = _prompt(store)
    assert "Sentez üretilemedi" not in text
    assert "ham anlar epizot kaydında" in text
    assert "Forklift kamyona temas etti." in text  # anlar kanıt olarak girdi

# tests/test_report.py
def test_a_beatless_fallback_episode_yields_a_neutral_event(store):
    # beats=[] ve summary_source="fallback" epizot; output = build_output(...)
    assert output.events[0].event == FALLBACK_EVENT
    assert "Sentez üretilemedi" not in output.events[0].event

# tests/test_memory.py
def test_a_fallback_episode_is_not_embedded(store):
    # summary_source="fallback" epizot; embed_episode(...) is False
    # ve sahte istemciye upsert HİÇ gelmedi
```

- [ ] **Step 2: Kırmızıyı doğrula.** `uv run pytest tests/test_supervisor.py tests/test_reporter.py tests/test_report.py tests/test_memory.py -v -k "fallback or fault or neutral"` — dördü FAIL.

- [ ] **Step 3: Uygula.**

`gozcu/agents/supervisor.py` — sabit (arıza metinlerinin yanına) ve `talk` içindeki `reminder`:

```python
#: Açık olay yedek özetliyse hatırlatmada özetin YERİNE geçen metin. Arıza
#: metni olay tarifi değildir; kimlik ve varlık bilgisi kalır (spec §1).
FALLBACK_REMINDER = "(tarif üretilemedi — sentez arızası)"
```

```python
        summary = (FALLBACK_REMINDER
                   if open_episode and open_episode.summary_source == "fallback"
                   else open_episode.summary_tr if open_episode else "")
        reminder = (f"\n[SİSTEM] Açık olay: episode {open_episode.id} — "
                    f"{summary}" if open_episode else "")
```

`gozcu/agents/reporter.py` — `_prompt` içindeki OLAY ZİNCİRİ satırı yardımcıya çıkar:

```python
def _episode_line(episode) -> str:
    """Kanıt dosyasının epizot satırı. Yedek özet kanıt DEĞİLDİR (spec §1):
    onun yerine ham anlar yazılır — rapor gerçek gözleme dayanır."""
    if episode.summary_source == "fallback":
        beats = "; ".join(f"{mmss(b.ts)} {b.text}" for b in episode.beats)
        line = (f"- {mmss(episode.start_ts)} [{episode.phase}] "
                f"(tarif üretilemedi — sentez arızası; ham anlar epizot "
                f"kaydında)")
        return f"{line} anlar: {beats}" if beats else line
    return f"- {mmss(episode.start_ts)} [{episode.phase}] {episode.summary_tr}"
```

```python
    parts += _section(SECTION_EPISODES,
                      [_episode_line(episode) for episode in episodes])
```

`gozcu/report.py` — sabit ve `_events` dalı:

```python
#: Anı olmayan yedek-özetli epizodun `events[]` metni. Arıza metni jüri
#: anahtarına girmez; uydurma da girmez — olan şey dürüstçe söylenir.
FALLBACK_EVENT = "Olay tespit edildi; tarifi üretilemedi (sentez arızası)."
```

```python
    for episode in episodes:
        if not episode.beats:
            text = (FALLBACK_EVENT if episode.summary_source == "fallback"
                    else episode.summary_tr[:MAX_EVENT])
            events.append(EventSummary(time=mmss(episode.start_ts),
                                       event=text))
            continue
```

`gozcu/memory.py` — `embed_episode` içinde `if episode.id is None` dalının hemen ardına:

```python
        if episode.summary_source == "fallback":
            # Arıza metni arşive gömülmez: gelecek koşuların emsal aramasını
            # zehirler (spec §1). `False` mevcut sözleşme — kademe düzelip
            # özet iyileştiğinde yeniden gömülebilir.
            return False
```

- [ ] **Step 4: Yeşili doğrula.** `uv run pytest tests/test_supervisor.py tests/test_reporter.py tests/test_report.py tests/test_memory.py -v` — tümü PASS.

- [ ] **Step 5: Commit.** `git commit -am "fix(karantina): arıza metni talk/rapor/events/arşivin hiçbirine olay diye girmiyor"`

---

### Task 5: Saha araçları her çağrıda başarır; İSG kaydı uydurma kimliği de kabul eder (§2)

**Files:**
- Modify: `gozcu/tools/field_systems.py` (`dispatch_medical` ~42-70, `site_alarm` ~73-86, `halt_production_line` ~97-124)
- Modify: `gozcu/tools/registry.py` (`_incident_guard` ~100-130)
- Modify: `gozcu/agents/supervisor.py` (`ESCALATION_INSTRUCTION` ~149-162, `escalate` mesajı ~462-467)
- Test: `tests/test_tools.py`, `tests/test_supervisor.py`, `tests/test_feed.py`

**Interfaces:**
- Consumes: `resolve_zone` (kalıyor — çözülürse fikstür verisi süslüyor, çözülmezse varsayılan).
- Produces: `dispatch_medical` → her zaman `state="dispatched"`; `site_alarm` → her zaman `siren_state="active"`; `halt_production_line` → yalnız `awaiting_approval`/`halted`; `_incident_guard` yalnız yineleme kısa devresi. `field_systems.DEFAULT_MEDICAL_TEAM/DEFAULT_MEDICAL_ETA_MINUTES` sabitleri.

- [ ] **Step 1: Mevcut testleri çevir + kırmızıları yaz** (`tests/test_tools.py`):
  - `test_halting_a_zone_that_belongs_to_no_line_is_explicit` (~96) ve `test_halting_an_unknown_line_is_explicit` (~105): SİL; yerine (dosyanın ev deseni satır içi `Store(":memory:")`; `gated` fixture'ı `tests/conftest.py`'da ve kapıyı AÇAR — kapısız varsayılanda `call_tool` `approved=True` enjekte eder, registry.py:165-169):

```python
def test_halting_an_unknown_line_still_halts():
    """Spec §2: mock her adı kabul eder; kapısız varsayılanda tek faz eylem."""
    store = Store(":memory:")
    result = call_tool(store, "halt_production_line",
                       {"line_id": "sentez-hatti", "rationale": "test"})
    assert result["state"] == "halted"
    assert result["line_id"] == "sentez-hatti"
    assert result["zone_id"] is None


def test_halting_an_unknown_line_waits_at_the_gate_when_gated(gated):
    """Kapı açıkken onay makinesi bilinmeyen hatta da normal işler."""
    store = Store(":memory:")
    result = call_tool(store, "halt_production_line",
                       {"line_id": "sentez-hatti", "rationale": "test"})
    assert result["state"] == "awaiting_approval"
```

  - `~147` (`dispatch_medical` `zone_unresolved`) ve `~164` (`site_alarm` `zone_unresolved`) assert'lerini çevir:

```python
def test_dispatch_to_an_unknown_zone_still_dispatches():
    result = dispatch_medical("kırmızı kamyon önü", urgency="critical")
    assert result["state"] == "dispatched"
    assert result["team"] == DEFAULT_MEDICAL_TEAM
    assert result["eta_minutes"] == DEFAULT_MEDICAL_ETA_MINUTES
    assert result["zone_id"] is None      # çözülemediği defterden okunuyor


def test_an_alarm_in_an_unknown_zone_still_sounds():
    result = site_alarm("362", level="high")
    assert result["siren_state"] == "active"
    assert result["affected_zone"] == "362"
    assert result["zone_id"] is None
```

  - `~291` civarındaki `refused is True` İSG testi (uydurma `episode_id` reddi): çevir —

```python
def test_a_fabricated_episode_id_still_opens_a_record(store):
    result = call_tool(store, "open_safety_incident",
                       {"episode_id": 999, "classification": "Yüksek",
                        "description": "x"})
    assert result["state"] == "open" and result["record_no"]
```

  - Yineleme testi varsa AYNEN kalır (aynı `episode_id`'ye ikinci kayıt → `duplicate: True` + ilk `record_no`); yoksa ekle.
  - `tests/test_supervisor.py`'a ekle: `escalate` sonrası history'deki `[SİSTEM]` mesajı `f"(episode_id): {episode.id}"` içeriyor — parantezli biçim, uygulamadaki `"Olay kimliği (episode_id): {id}."` metniyle birebir.
  - `tests/test_feed.py:507-509` (`zone_unresolved` detayı): fixture'daki kayıt bir `site_alarm` sonucu ve `siren_state` üzerinden kurulu — sonucu `siren_state="active"` yap ve assert'i ona çevir; test hâlâ "çağrı satırı çağrıldığı anki durumu korur" davranışını sınıyor, durum adı değişti.

- [ ] **Step 2: Kırmızıyı doğrula.** `uv run pytest tests/test_tools.py tests/test_supervisor.py tests/test_feed.py -v` — yeni/çevrilen testler FAIL.

- [ ] **Step 3: Uygula.**

`gozcu/tools/field_systems.py` — modül docstring'ine ve fonksiyonlara spec kararını işle. Sabitler:

```python
#: Bölge çözülemediğinde kullanılan varsayılan revir ekibi ve varış süresi.
#: 26 Ağustos kararı (spec §2): bu araçlar MOCK ve her çağrı başarır —
#: gerçek bir devrilmede sahaya tek müdahale ulaştırmayan şey, uydurma bölge
#: adı değil bölge DOĞRULAMASIYDI. Ajanın bölgeyi bilmediği defterden
#: okunur (zone_id=None); müdahale yine de yürür.
DEFAULT_MEDICAL_TEAM = "revir-1"
DEFAULT_MEDICAL_ETA_MINUTES = 4
```

`dispatch_medical` gövdesi (zone dalını değiştir):

```python
    zone = resolve_zone(location)
    if zone is None:
        eta = DEFAULT_MEDICAL_ETA_MINUTES
        team, zone_id = DEFAULT_MEDICAL_TEAM, None
    else:
        eta = zone["medical_eta_minutes"]
        team, zone_id = zone["medical_team"], zone["zone_id"]
    if effective != "critical":
        eta += NON_CRITICAL_DELAY_MINUTES
    result |= {"zone_id": zone_id, "team": team, "eta_minutes": eta,
               "state": "dispatched"}
```

`site_alarm`:

```python
    found = resolve_zone(zone)
    return {"alarm_id": _ref("alarm"),
            "affected_zone": found["name"] if found else zone,
            "zone_id": found["zone_id"] if found else None,
            "level": level, "siren_state": "active"}
```

`halt_production_line` (ret dalları silinir, onay makinesi aynen):

```python
    zone = resolve_zone(line_id)
    if zone is None or zone["line_id"] is None:
        resolved = {"line_id": line_id,
                    "zone_id": zone["zone_id"] if zone else None,
                    "rationale": rationale}
    else:
        resolved = {"line_id": zone["line_id"], "zone_id": zone["zone_id"],
                    "rationale": rationale}
    if not approved:
        return resolved | {"state": "awaiting_approval",
                           "awaiting_approval": True}
    return resolved | {"state": "halted"}
```

`gozcu/tools/registry.py` — `NO_SUCH_EPISODE` sabitini ve `_incident_guard`'daki varlık kontrolünü SİL; docstring'i güncelle (karar: mock her kimliği kabul eder; doğru kimlik artık yükseltme mesajıyla veriliyor, kısa devre kalan artığı süpürür):

```python
def _incident_guard(store, tool_name: str, params: dict) -> dict | None:
    if tool_name != INCIDENT_TOOL:
        return None
    episode_id = params.get("episode_id")
    for action in store.actions():
        if (action.tool_name == INCIDENT_TOOL
                and action.params.get("episode_id") == episode_id
                and action.result.get("record_no")):
            return {**action.result, "duplicate": True}
    return None
```

`gozcu/agents/supervisor.py` — `ESCALATION_INSTRUCTION`'ı sadeleştir (zone_unresolved paragrafı ölü; genel ilke kalır):

```python
ESCALATION_INSTRUCTION = (
    "ÖNCE gerekli saha araçlarını çağır (sağlık, telsiz, alarm, İSG kaydı), "
    "SONRA operatöre ne yaptığını tek paragrafta anlat ve eksik bilgi varsa "
    "en fazla iki soru sor. "
    "ARAÇ SONUCUNU OKU: yalnızca gerçekten başarılı olan çağrıları rapor "
    "et; `refused` ya da `duplicate` dönen bir çağrıyı yapılmış gibi "
    "anlatma.")
```

`escalate` mesajına kimlik satırı (headline'dan sonra):

```python
        self.history.append({
            "role": "user",
            "content": f"[SİSTEM] {mmss(episode.start_ts)} — {headline} "
                       f"Olay kimliği (episode_id): {episode.id}. "
                       f"Risk: {risk.level}. "
                       f"Gerekçe: {risk.rationale_tr}\n{note}\n"
                       f"{ESCALATION_INSTRUCTION}"})
```

- [ ] **Step 4: Yeşili doğrula.** `uv run pytest tests/test_tools.py tests/test_supervisor.py tests/test_feed.py -v` — tümü PASS.

- [ ] **Step 5: Commit.** `git commit -am "feat(araçlar): mock saha araçları her çağrıda başarır; İSG kimliği yükseltme mesajından gelir"`

---

### Task 6: Yükseltme kipleri — olay başına bir tam müdahale, gerisi gelişme bildirimi (§3)

**Files:**
- Modify: `gozcu/agents/supervisor.py` (`__init__` ~236-253, `escalate` ~436-468; yeni `UPDATE_INSTRUCTION`, `_latest_risk`)
- Test: `tests/test_supervisor.py`

**Interfaces:**
- Consumes: `store.risks()` (ekleme sıralı liste), `assess_risk`.
- Produces: `Supervisor._escalated: set[int]`; `UPDATE_INSTRUCTION` sabiti. `DecisionLoop` DEĞİŞMEZ.

- [ ] **Step 1: Kırmızı testleri yaz** (`tests/test_supervisor.py`, mevcut sahte-gateway desenini kullan). **KRİTİK — sayaçlı sahte, değerlendirmeyi DEPOYA DA YAZMALI:** gerçek `assess_risk` kaydeder ve gelişme kipi `store.risks()`'ten okur; kaydetmeyen bir sahteyle ikinci yükseltme `risk is None` teorik dalına düşer, tam müdahaleye geri döner ve test sonsuza dek kırmızı kalır. O dal SPEC GEREĞİ var (§3) — koddan silerek "düzeltme"ye kalkma:

```python
def _counting_assess(store, counter):
    def fake(gw, _store, episode):
        counter.append(1)
        assessment = RiskAssessment(
            episode_id=episode.id, ts=episode.end_ts or episode.start_ts,
            level="Yüksek", rationale_tr="sahte", preventable=True)
        assessment.id = store.save_risk(assessment)
        return assessment
    return fake


def test_a_second_escalation_of_the_same_episode_is_an_update(monkeypatch):
    # kurulum: depo + epizot + sahte gateway'li Supervisor (dosyanın deseni)
    calls = []
    monkeypatch.setattr("gozcu.agents.supervisor.assess_risk",
                        _counting_assess(store, calls))
    nobetci.escalate(episode)          # ilk: tam müdahale
    nobetci.escalate(episode)          # ikinci: gelişme kipi
    assert len(calls) == 1, "analiz yalnız ilk yükseltmede koşar"
    assert UPDATE_INSTRUCTION in last_system_message
    assert ESCALATION_INSTRUCTION not in last_system_message


def test_the_update_mode_reuses_the_stored_assessment(...):
    # depoya elle bir RiskAssessment yaz; ikinci escalate mesajındaki
    # "Risk:" satırı o kaydın seviyesini taşımalı


def test_a_new_episode_gets_a_full_escalation_again(monkeypatch):
    # aynı `_counting_assess` sahtesiyle:
    nobetci.escalate(episode_one)
    nobetci.escalate(episode_two)      # farklı id → tam müdahale
    assert len(calls) == 2
```

- [ ] **Step 2: Kırmızıyı doğrula.** `uv run pytest tests/test_supervisor.py -v -k "update or second or full"` — FAIL.

- [ ] **Step 3: Uygula** (`gozcu/agents/supervisor.py`):

```python
#: Aynı açık olayın SONRAKİ yükseltmelerinin talimatı. İlk yükseltme tam
#: müdahaledir; 26 Ağustos koşusunda aynı olay 6 kez yükseltilip 18 saha
#: çağrısı üretti — ESCALATION_INSTRUCTION her seferinde "önce araçları
#: çağır" diye emrettiği için. Gelişme kipi operatörü bilgilendirir,
#: ambulansı yeniden çağırmaz (spec §3).
UPDATE_INSTRUCTION = (
    "Bu olay için saha araçları ZATEN çağrıldı ve aksiyon defterinde "
    "duruyor; aynı aracı aynı gerekçeyle TEKRAR ÇAĞIRMA. Gelişmeyi 1-2 "
    "cümleyle operatöre bildir. Yalnız YENİ doğan bir ihtiyaç için yeni "
    "araç çağırabilirsin. ARAÇ SONUCUNU OKU: yalnızca gerçekten başarılı "
    "olan çağrıları rapor et.")
```

`__init__`'e: `self._escalated: set[int] = set()` (yorum: "Tam müdahalesi yapılmış epizot kimlikleri — spec §3'ün iki kipli yükseltmesi").

`_latest_risk` yardımcısı:

```python
    def _latest_risk(self, episode: Episode):
        """Epizodun depodaki SON değerlendirmesi; yoksa None."""
        rows = [r for r in self.store.risks() if r.episode_id == episode.id]
        return rows[-1] if rows else None
```

`escalate` gövdesinde `risk = assess_risk(...)` satırının yerine:

```python
        update = episode.id in self._escalated
        risk = self._latest_risk(episode) if update else None
        if risk is None:
            # İlk yükseltme — ya da (teorik dal) güncellemede depoda hiç
            # değerlendirme yok: tam müdahaleye düşülür.
            update = False
            risk = assess_risk(self.gw, self.store, episode)
        self._escalated.add(episode.id)
```

ve mesajdaki talimat:

```python
                       f"{UPDATE_INSTRUCTION if update else ESCALATION_INSTRUCTION}"})
```

- [ ] **Step 4: Yeşili doğrula.** `uv run pytest tests/test_supervisor.py -v` — tümü PASS.

- [ ] **Step 5: Commit.** `git commit -am "feat(nöbetçi): olay başına bir tam müdahale — sonraki yükseltmeler gelişme bildirimi"`

---

### Task 7: Anlar — tavan 48, baş+son tutma (§4)

**Files:**
- Modify: `gozcu/models.py` (`MAX_EPISODE_BEATS`, satır 25)
- Modify: `gozcu/agents/synthesizer.py` (`_merge_beats` ~140-163)
- Test: `tests/test_synthesizer.py`

**Interfaces:**
- Produces: `MAX_EPISODE_BEATS == 48`; taşmada ilk 24 + son 24.

- [ ] **Step 1: Kırmızı testi yaz** (`tests/test_synthesizer.py`):

```python
def test_beat_overflow_keeps_both_the_onset_and_the_latest_moments():
    """Spec §4: yalnız-baş kuralı kazayı events[]'ten düşürdü (26 Ağu)."""
    existing = [EventBeat(ts=float(i), text=f"an {i}") for i in range(50)]
    fresh = [EventBeat(ts=float(50 + i), text=f"an {50 + i}")
             for i in range(10)]
    merged = _merge_beats(existing, fresh)
    assert len(merged) == MAX_EPISODE_BEATS == 48
    assert merged[0].text == "an 0"          # başlangıç korunuyor
    assert merged[-1].text == "an 59"        # EN GÜNCEL an garantili
    assert [b.ts for b in merged] == sorted(b.ts for b in merged)
```

- [ ] **Step 2: Kırmızıyı doğrula.** `uv run pytest tests/test_synthesizer.py -v -k overflow` — FAIL (bugün ilk 12 tutuluyor).

- [ ] **Step 3: Uygula.** `gozcu/models.py`: `MAX_EPISODE_BEATS = 48` (yorumu güncelle: pencere başına ~6 an ölçüldü; 48 sekiz pencereyi tam tutar, 10 dakikalık en kötü hâlde hâlâ gerekli bir tavandır). `_merge_beats` sonu:

```python
    merged.sort(key=lambda beat: beat.ts)
    if len(merged) <= MAX_EPISODE_BEATS:
        return merged
    # Baş + son (spec §4): baş olayın nasıl başladığını, son ise epizot ne
    # kadar uzarsa uzasın EN GÜNCEL gelişmenin listede olmasını garanti eder.
    # Yalnız-baş kuralının ölçülen arızası: 00:00'da açılan epizotta tavan
    # park hâlindeki kamyonla doldu ve kaza `events[]`ten düştü (26 Ağu).
    # İki dilim çakışamaz: kural yalnız len > MAX'ta tetikleniyor.
    half = MAX_EPISODE_BEATS // 2
    return merged[:half] + merged[-half:]
```

(`_merge_beats` docstring'indeki "İLK anlar korunarak" gerekçesini de bu kurala göre yeniden yaz.)

- [ ] **Step 4: Yeşili doğrula.** `uv run pytest tests/test_synthesizer.py tests/test_models.py -v` — tümü PASS.

- [ ] **Step 5: Commit.** `git commit -am "fix(anlar): tavan 48 ve baş+son tutma — kaza artık events[]'ten düşmüyor"`

---

### Task 8: Saatler — analistin damgaları, RiskAssessment.ts, beslemenin risk satırı ve müdahale kartı (§6)

**Files:**
- Modify: `gozcu/models.py` (`RiskAssessment`, ~157-163)
- Modify: `gozcu/agents/risk.py` (`assess_risk` ~312-339)
- Modify: `gozcu/ui/feed.py` (risk satırı ~443-458, `intervention_card` ~193-246 ve çağıranı ~430-441)
- Test: `tests/test_risk.py`, `tests/test_feed.py`, `tests/test_console.py` (satır ~678-746: `TestInterventionCard` karta dört konumlu argümanla çağrı yapıyor — imza kararı aşağıda onları KIRMADAN veriliyor)

**Interfaces:**
- Produces: `RiskAssessment.ts: float = 0.0` (varsayılan 0.0 = damgasız eski kayıt); `intervention_card(episode, risk, actions, said, ts=None)` — YENİ İSTEĞE BAĞLI son parametre; `None` `episode.event_ts`'e düşer. Varsayılan bilinçli: `tests/test_console.py::TestInterventionCard`'ın ~13 testi dört konumlu argümanla çağırıyor ve `test_card_is_stamped_with_the_event_moment_not_the_window_edge` ile `test_card_falls_back_to_start_when_there_are_no_beats` tam da bu geri-düşme dalını sınamaya devam ediyor — canlı yol (feed çağıranı) `ts`'i HER ZAMAN geçer ve yeni feed testi o yolu ayrıca sınar.

- [ ] **Step 1: Kırmızı testleri yaz.**
  - `tests/test_risk.py:138`'deki `assert record.ts == e.start_ts == EPISODE_TS` beklentisini çevir ve genişlet:

```python
    now = e.end_ts or e.start_ts
    assert record.ts == now, "defter damgası videonun ŞİMDİsi (spec §6)"
    assessment = store.risks()[-1]
    assert assessment.ts == now
    handoff = store.handoffs()[-1]
    assert handoff.ts == now
```

(Fixture'ın epizoduna `end_ts` ver ki `start_ts != end_ts` olsun ve test ayrımı gerçekten ölçsün.)
  - `tests/test_feed.py`'a ekle:

```python
def test_the_risk_row_carries_the_assessment_moment_not_the_episode_start(...):
    # epizot start=0, end=90; ts=90.0'lık değerlendirme yaz
    # feed'deki risk satırının ts'i 90.0 olmalı, 0.0 (event_ts) değil

def test_the_intervention_card_is_stamped_with_the_first_assessment(...):
    # iki değerlendirme (ts=19.0 ve ts=90.0) yaz; kart HTML'inde mmss(19.0)
    # ("00:19") geçmeli — müdahale anı İLK değerlendirmenin anıdır
```

Not: `tests/test_feed.py:254` (`risk_entry.ts == 7.0` benzeri mevcut test) `risk.ts or ...` geri-düşme dalının nöbetçisidir — depoda `ts=0.0` (damgasız) kayıt epizot damgasına düşer; o test bilerek DEĞİŞTİRİLMEZ. `tests/test_console.py::TestInterventionCard` da değiştirilmez: `ts=None` varsayılanı sayesinde dört-argümanlı çağrılar ve iki damga-anlamı testi geri-düşme dalını sınamaya devam eder.

- [ ] **Step 2: Kırmızıyı doğrula.** `uv run pytest tests/test_risk.py tests/test_feed.py -v` — çevrilen/yeni testler FAIL.

- [ ] **Step 3: Uygula.**

`gozcu/models.py` — `RiskAssessment`'e alan:

```python
class RiskAssessment(Base):
    id: int | None = None
    episode_id: int
    #: Değerlendirmenin yapıldığı VİDEO anı. 0.0 = damgasız (arşivden
    #: tohumlanan eski kayıt); besleme o durumda epizot damgasına düşer.
    #: Eskiden hiç yoktu ve besleme risk satırını epizodun BAŞINA yazıyordu —
    #: 01:38'de yapılmış analiz "00:00 ⚖️" görünüyordu (26 Ağu, spec §6).
    ts: float = 0.0
    level: RiskLevel
    ...
```

`gozcu/agents/risk.py` — `assess_risk` içinde:

```python
    # Videonun "şimdi"si: 882f3b3'ün süpervizöre getirdiği kuralın aynısı.
    # `start_ts` uzun bir olayda saati olayın başında dondurur.
    now = episode.end_ts or episode.start_ts
```

- `_run_tool_calls(store, calls, ts=episode.start_ts)` → `ts=now`
- `RiskAssessment(episode_id=..., ...)` → `RiskAssessment(episode_id=episode.id, ts=now, level=...)`
- `save_handoff(Handoff(ts=episode.start_ts, ...))` → `ts=now`

`gozcu/ui/feed.py` — risk satırı (yorumunu da yeni kurala çevir):

```python
        elif entry.source == "risk":
            risk = risks.get(entry.row_id)
            if risk:
                episode = episodes.get(risk.episode_id)
                proposed = " · ".join(action.tool_name
                                      for action in risk.proposed_actions)
                # Değerlendirmenin KENDİ anı (spec §6). 0.0 damgasız eski
                # kayıt demek; o durumda epizot damgasına düşülür.
                made = FeedEntry(
                    seq=entry.seq,
                    ts=risk.ts or (episode.event_ts if episode else 0.0),
                    agent="risk_analyst", kind="risk",
                    title=risk.rationale_tr,
                    detail=f"önerilen: {proposed}" if proposed else "",
                    risk=risk.level)
```

`intervention_card` imzası `(episode, risk, actions, said, ts=None)` olur; gövde başında `stamp = ts if ts is not None else episode.event_ts` ve `mmss(episode.event_ts)` → `mmss(stamp)`; docstring'in damga paragrafını değiştir: "Damga YÜKSELTME ANI — canlı yolda ilk risk değerlendirmesinin `ts`'i (ilk değerlendirme ilk yükseltmenin içinde koşar, ikisi aynı an; kapanışta değerlendirilip geç yükseltilen telafi epizodunda kapanış anı basılır — kabul edilen sapma). `ts=None` `event_ts`'e düşer: doğrudan çağıranlar ve damgasız eski kayıtlar için." Çağıran (~436-440):

```python
                    first_risk = next(
                        (r for r in risks.values()
                         if r.episode_id == episode.id and r.ts), None)
                    card = intervention_card(
                        episode, risk_by_episode.get(episode.id), window,
                        spoken,
                        ts=first_risk.ts if first_risk else episode.event_ts)
```

- [ ] **Step 4: Yeşili doğrula.** `uv run pytest tests/test_risk.py tests/test_feed.py tests/test_models.py -v` — tümü PASS.

- [ ] **Step 5: Commit.** `git commit -am "fix(saat): analist damgaları ve besleme risk satırı videonun şimdisini söylüyor"`

---

### Task 9: Raportör düşerse `summary` arıza kaydı olmasın (§7)

**Files:**
- Modify: `gozcu/agents/reporter.py` (`RootCauseReport`, `_fallback`)
- Modify: `gozcu/run.py` (`run_pipeline` özet seçimi ~396-398)
- Test: `tests/test_reporter.py`, `tests/test_run.py`

**Interfaces:**
- Produces: `RootCauseReport.report_source` özelliği (`"model" | "fallback"`, sentezleyicinin `_source` deseniyle — metin karşılaştırması YASAK).

- [ ] **Step 1: Kırmızı testleri yaz.**

```python
# tests/test_reporter.py
def test_a_fallback_report_says_so_structurally():
    report = _fallback(EMPTY_REASON)
    assert report.report_source == "fallback"

def test_a_parsed_report_is_model_sourced():
    report = _parse('{"what_happened": "x", "probable_root_cause": "y", '
                    '"confidence_limits": "z"}')
    assert report.report_source == "model"

# tests/test_run.py — mevcut sahte-boru-hattı kurulumunu kullan
def test_a_fallback_report_does_not_become_the_summary(...):
    # raportörü boş yanıtla düşür; depoda model özetli bir epizot bulunsun
    output, _ = run_pipeline(...)
    assert output.summary == "Forklift devrildi."   # epizot özeti
    assert "boş yanıt" not in output.summary
    # detail.root_cause_report yine de teslim edildi
    assert output.detail.root_cause_report is not None
```

- [ ] **Step 2: Kırmızıyı doğrula.** `uv run pytest tests/test_reporter.py tests/test_run.py -v -k "fallback or summary or sourced"` — FAIL.

- [ ] **Step 3: Uygula.**

`gozcu/agents/reporter.py` — `RootCauseReport`'a sentezleyicinin deseni:

```python
    #: **Şemanın DIŞINDA** — `PrivateAttr` `model_json_schema()`'e girmiyor.
    #: Metne bakarak yedek raporu ayırt etmek YASAK; o yol bir kez yanılttı
    #: (bkz. `Episode.summary_source`). Yapısal kaynak etiketi (spec §7).
    _source: str = PrivateAttr(default="model")

    @property
    def report_source(self) -> str:
        """Rapor modelden mi geldi ("model") yoksa bir arıza kabuğu mu
        ("fallback")."""
        return self._source
```

(`PrivateAttr` importu `pydantic`'ten — dosyada zaten `BaseModel, ConfigDict, Field` var, yanına ekle.) `_fallback` dönüşten önce:

```python
    report = RootCauseReport(...)
    report._source = "fallback"
    return report
```

`gozcu/run.py` — `summary = root_cause.what_happened` satırının (satır ~398) yerine:

```python
            summary = root_cause.what_happened
            if root_cause.report_source == "fallback":
                # Arıza kabuğu şartnamenin ilk cümlesi OLMAMALI (spec §7):
                # elde model üretimi bir epizot özeti varsa o konuşur; yoksa
                # kabuk kalır — dürüst son çare. Rapor `detail` altında her
                # iki dalda da aynen teslim ediliyor.
                model_summaries = [e.summary_tr for e in fresh
                                   if e.summary_source == "model"]
                if model_summaries:
                    summary = model_summaries[-1]
```

- [ ] **Step 4: Yeşili doğrula.** `uv run pytest tests/test_reporter.py tests/test_run.py -v` — tümü PASS.

- [ ] **Step 5: Commit.** `git commit -am "fix(teslim): raportör düşerse summary son model özetine düşüyor, arıza kaydına değil"`

---

### Task 10: Belgeler, tam takım koşusu ve uçtan uca doğrulama (§10, §9)

**Files:**
- Modify: `docs/05-decisions/decision-log.md`
- Modify: `docs/tasks/README.md` (Durum notu)
- Test: tam takım + canlı koşu

**Interfaces:**
- Consumes: Task 1-9'un tamamı merge edilmiş hâlde.

- [ ] **Step 1: Karar günlüğüne üç kayıt ekle** (`docs/05-decisions/decision-log.md`, dosyanın mevcut biçimine uyarak, tarih 26 Ağustos 2026):
  1. **Bölge doğrulaması kaldırıldı** — eski karar ("serbest metne siren çaldırmak olmayan bir bölge uydurmaktır") ve ters ölçüm (canlı koşuda 6/6 sevk + 6/6 alarm `zone_unresolved`; gerçek devrilmeye sıfır mock müdahale); yeni kural: mock her adı kabul eder, bilinmezlik `zone_id=None` ile defterde kalır. Elenen alternatif: bölge adlarını şemaya enum koymak — katı şema bilinmeyen bölgede uydurma-ama-geçerli bir ad seçtirirdi.
  2. **Token politikası** — 2048+genişletme ölçümleri (pencerelerin ~%60'ında tükenme, 20-50 s ikinci deneme, raportörde 4096'nın da tükenip `summary`'nin arıza kaydına düşmesi); yeni kural: 8192 tek sigorta, raportör 16384, tekrar yok; tavanın tamamen kaldırılmasının reddi (1106 s ölçülü asılma, zaman aşımı yakalamıyor).
  3. **Yükseltme kipleri** — 6 yükseltme / 18 çağrı / 7 değerlendirme ölçümü; olay başına bir tam müdahale + gelişme bildirimi; döngüde bastırmanın reddi (kaza operatörden saklanırdı). Ek not: `notable_event` eşiği ölçülecek borç.

- [ ] **Step 2: Görev durumunu işle.** `docs/tasks/README.md`'deki durum tablosuna bu işin satırını/bölümünü ekle (spec ve plan yollarıyla), CLAUDE.md'nin "Algı katmanı" kuralındaki değişiklik-kayıt şartına uygun biçimde.

- [ ] **Step 3: Tam takımı koştur.** `uv run pytest tests/ -v` — TÜMÜ PASS. Kırık kalan her test ya bu planın çevirdiği bir sözleşmedir (ilgili görevin adımına dön) ya da gerçek bir regresyondur (düzelt, yutma).

- [ ] **Step 4: Canlı doğrulama (gateway erişilebilirse).**

```bash
uv run --env-file .env python -c "
from gozcu.run import run_pipeline
import json
out, _ = run_pipeline('WhatsApp Video 2026-08-25 at 15.35.33.mp4')
print(json.dumps(out.model_dump(), ensure_ascii=False, indent=1))
" > /tmp/gozcu-verify.json
```

Başarı ölçütleri (spec §9): çıktıda ve trace'te sıfır `zone_unresolved`; olay başına ≤2 risk değerlendirmesi; `events[]` içinde ~00:35/00:45 anları; `summary` arıza kaydı değil; günlükte tek bir `bütçe ... tekrar` satırı yok. Gateway erişilemiyorsa bu adımı raporda "koşulamadı" diye açıkça işaretle — sessizce geçme.

- [ ] **Step 5: Commit.** `git commit -am "docs(görev): dürüstlük onarımları kayda geçti — karar günlüğü ve durum"`
