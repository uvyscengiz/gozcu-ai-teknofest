"""Sentezleyicinin testleri — dağınık pencereler tek bir epizota dönüşüyor mu.

Sahte gateway bilerek `Mock()` değil: bu depoda yedi kusur şekilsiz bir
`Mock()` collaborator'ın arkasında saklandı. `_FakeGateway` hangi kademeye,
hangi mesajlarla ve hangi şemayla gidildiğini kaydeder ve gerçek bir
`Response` döndürür — böylece "modele ne gitti" sorusu test edilebilir bir
soru oluyor.
"""

import json

import pytest

from gozcu.agents.orchestrator import mmss
from gozcu.agents.anomaly_analyst import (DEGRADED_SUMMARY, EMPTY_SUMMARY, PHASES,
                                          SYSTEM_PROMPT, UNREADABLE_SUMMARY,
                                          _SynthesisResponse, _digest, _merge_beats,
                                          synthesize)
from gozcu.gateway import Response
from gozcu.models import (ClipBeat, Episode, EventBeat, Interpretation,
                          Observation, Signals)
from gozcu.store import Store

RESPONSE_JSON = json.dumps({
    "phase": "development",
    "summary_tr": "İstif aracı devrildi, yerde hareketsiz kişi var.",
    "participants": ["istif aracı", "personnel"],
    "preliminary_risk": "Kritik"}, ensure_ascii=False)


class _FakeGateway:
    """Şekilli sahte: `Gateway.ask` imzasını birebir taşır ve kaydeder."""

    def __init__(self, response: Response | None = None) -> None:
        self.response = response if response is not None else Response(
            content=RESPONSE_JSON, model="fast-test")
        self.calls: list[dict] = []

    def ask(self, tier, messages, schema=None, tools=None,
            max_tokens=None, temperature=None) -> Response:
        self.calls.append({"tier": tier, "messages": messages,
                           "schema": schema, "tools": tools,
                           "max_tokens": max_tokens,
                           "temperature": temperature})
        return self.response

    @property
    def last(self) -> dict:
        assert self.calls, "gateway hiç çağrılmadı"
        return self.calls[-1]

    @property
    def user_content(self) -> str:
        return self.last["messages"][-1]["content"]


class _Embedder:
    """Görev 08'in gömme geri çağrısının şekli: epizodu alır, kaydeder.

    Şekilsiz bir `list.append` stub'ı geri çağrının epizodu gerçekten aldığını
    kanıtlamıyordu; bu sahte, teslim edilen epizodun kimliğini ve durumunu
    tutuyor.
    """

    def __init__(self) -> None:
        self.seen: list[tuple[int, str, str]] = []

    def __call__(self, episode) -> None:
        self.seen.append((episode.id, episode.state, episode.summary_tr))


def _window(start: float = 0.0, count: int = 10) -> list[Observation]:
    return [Observation(ts=float(start + t), signals=Signals(person_count=1))
            for t in range(count)]


def _gateway() -> _FakeGateway:
    return _FakeGateway()


# --- epizot yaşam döngüsü -------------------------------------------------

def test_open_merges_a_window_into_one_episode():
    store = Store(":memory:")
    interpretation = Interpretation(observation_ts=3.0,
                                    description="araç yan yattı", model="m",
                                    severity="olay")
    episode = synthesize(_gateway(), store, _window(), interpretation,
                         "open_episode")
    assert episode.start_ts == 0.0 and episode.end_ts == 9.0
    assert episode.preliminary_risk == "Kritik"
    assert episode.phase == "development"
    assert episode.participants == ["istif aracı", "personnel"]
    assert len(store.episodes()) == 1


def test_update_extends_the_open_episode_instead_of_opening_a_new_one():
    store = Store(":memory:")
    synthesize(_gateway(), store, _window(0), None, "open_episode")
    synthesize(_gateway(), store, _window(10), None, "update_episode")
    assert len(store.episodes()) == 1
    assert store.episodes()[0].end_ts == 19.0
    assert store.episodes()[0].start_ts == 0.0


def test_close_closes_the_open_episode_and_does_not_open_a_new_one():
    store = Store(":memory:")
    synthesize(_gateway(), store, _window(0), None, "open_episode")
    synthesize(_gateway(), store, _window(10), None, "close_episode")
    assert len(store.episodes()) == 1
    episode = store.episodes()[0]
    assert episode.state == "closed" and episode.end_ts == 19.0
    assert episode.phase == "outcome"
    assert store.open_episode() is None


def test_update_without_an_open_episode_opens_one():
    """Yönlendirici açık epizot yokken de `update_episode` diyebiliyor
    (Görev 06 notu) ve döngü boş depoda bunu düzeltmiyor — kaynaşacak bir şey
    yoksa kayıt düşmesin diye epizot açılır."""
    store = Store(":memory:")
    episode = synthesize(_gateway(), store, _window(), None, "update_episode")
    assert episode is not None and len(store.episodes()) == 1
    assert episode.state == "open"


# --- hayalet epizot: kapanacak bir şey yoksa hiçbir şey yazılmaz ----------

def test_close_without_an_open_episode_writes_nothing():
    store = Store(":memory:")
    gateway = _gateway()
    assert synthesize(gateway, store, _window(), None, "close_episode") is None
    assert store.episodes() == []
    assert store.handoffs() == []
    assert gateway.calls == [], "kapanacak epizot yokken modele hiç gidilmemeli"


def test_close_without_an_open_episode_does_not_fire_the_callback():
    store, embedder = Store(":memory:"), _Embedder()
    synthesize(_gateway(), store, _window(), None, "close_episode",
               on_close=embedder)
    assert embedder.seen == []


def test_two_consecutive_closes_leave_exactly_one_episode():
    """Yönlendirici üst üste iki `close_episode` verebilir ve `_resolve()`
    yalnızca `open_episode`'u indirir — ikincisi hayalet bir olay yazmamalı."""
    store = Store(":memory:")
    synthesize(_gateway(), store, _window(0), None, "open_episode")
    synthesize(_gateway(), store, _window(10), None, "close_episode")
    synthesize(_gateway(), store, _window(20), None, "close_episode")
    assert len(store.episodes()) == 1
    assert store.episodes()[0].end_ts == 19.0


# --- gömme geri çağrısı ---------------------------------------------------

def test_close_triggers_the_embedding_callback():
    store, embedder = Store(":memory:"), _Embedder()
    opened = synthesize(_gateway(), store, _window(0), None, "open_episode",
                        on_close=embedder)
    assert embedder.seen == [], "açılış gömme tetiklememeli"
    synthesize(_gateway(), store, _window(10), None, "close_episode",
               on_close=embedder)
    assert len(embedder.seen) == 1
    episode_id, state, summary = embedder.seen[0]
    assert episode_id == opened.id
    assert state == "closed"
    assert summary == store.episodes()[0].summary_tr


def test_close_works_without_a_callback():
    store = Store(":memory:")
    synthesize(_gateway(), store, _window(0), None, "open_episode")
    episode = synthesize(_gateway(), store, _window(10), None, "close_episode")
    assert episode.state == "closed"


# --- tek açık epizot değişmezinin bekçisi döngüde, burada değil -----------

def test_open_episode_always_creates_even_with_one_already_open():
    """`DecisionLoop._resolve()` açık epizot varken `open_episode`'u
    `update_episode`'a indiriyor; bu ancak `open_episode` KOŞULSUZ açtığı için
    işe yarıyor. Bekçi döngü, sentezleyici değil — bu test o iş bölümünü
    belgeliyor."""
    store = Store(":memory:")
    synthesize(_gateway(), store, _window(0), None, "open_episode")
    synthesize(_gateway(), store, _window(10), None, "open_episode")
    assert len(store.episodes()) == 2


# --- modele ne gidiyor ----------------------------------------------------

def test_synthesize_uses_the_fast_tier_not_the_large_one():
    gateway = _gateway()
    synthesize(gateway, Store(":memory:"), _window(), None, "open_episode")
    assert gateway.last["tier"] == "fast"


def test_schema_goes_to_the_gateway_as_a_plain_pydantic_model():
    """Sertleştirmeyi `Gateway.ask()` yapıyor (Görev 03); ajan `strict_schema`
    çağırmıyor, düz modeli veriyor."""
    gateway = _gateway()
    synthesize(gateway, Store(":memory:"), _window(), None, "open_episode")
    assert gateway.last["schema"] is _SynthesisResponse


def test_the_interpretation_reaches_the_model():
    """Görsel yorumun kaynaşması bu görevin bütün sebebi. Yorumu prompt'a
    koyan satırlar silinirse bu test kırmızıya döner."""
    gateway = _gateway()
    interpretation = Interpretation(
        observation_ts=5.0, model="vlm-test", severity="olay",
        description="istif aracı yan yattı, forkliftin altında kişi var")
    synthesize(gateway, Store(":memory:"), _window(), interpretation,
               "open_episode")
    assert interpretation.description in gateway.user_content


def test_the_interpretation_is_stamped_with_its_own_observation_ts():
    """`Interpretation.observation_ts` pencerenin ORTA damgası (Görev 04);
    yorumu `window[0].ts` ile damgalayan kod yalan söyler."""
    gateway = _gateway()
    interpretation = Interpretation(observation_ts=5.0, model="vlm-test",
                                    description="araç yan yattı",
                                    severity="olay")
    synthesize(gateway, Store(":memory:"), _window(), interpretation,
               "open_episode")
    visual = next(line for line in gateway.user_content.splitlines()
                  if interpretation.description in line)
    assert visual.startswith(mmss(5.0))


def test_the_open_episode_summary_is_given_to_the_model_on_update():
    """Kaynaşma bağlam istiyor: devam eden olayın özeti gitmezse model her
    pencereyi sıfırdan anlatır ve süreklilik kaybolur."""
    store = Store(":memory:")
    synthesize(_gateway(), store, _window(0), None, "open_episode")
    gateway = _gateway()
    synthesize(gateway, store, _window(10), None, "update_episode")
    assert store.episodes()[0].summary_tr in gateway.user_content


def test_the_prompt_spells_the_schema_enums_byte_for_byte():
    """CLAUDE.md: bir prompt enum sayıyorsa değerler şemadakiyle birebir aynı
    olmalı. Bunlar bir kez ayrıştı ve sistem sessizce öldü."""
    for phase in PHASES:
        assert phase in SYSTEM_PROMPT
    for level in ("Düşük", "Orta", "Yüksek", "Kritik"):
        assert level in SYSTEM_PROMPT


# --- bozulmuş ve bozuk yanıtlar -------------------------------------------

def test_degraded_fast_tier_still_produces_an_episode():
    """Bozulmuş yanıt geçerli JSON taşısa bile içeriği okunmamalı: bir gün
    bayat bir gövdeyle gelirse (önbellek) o gövde canlı sentez sanılır."""
    gateway = _FakeGateway(Response(content=RESPONSE_JSON, degraded=True))
    store = Store(":memory:")
    episode = synthesize(gateway, store, _window(), None, "open_episode")
    assert episode is not None and len(store.episodes()) == 1
    assert episode.summary_tr == DEGRADED_SUMMARY
    assert episode.preliminary_risk == "Orta"


@pytest.mark.parametrize("content", ["", "   ", "\n"])
def test_empty_content_still_produces_an_episode(content):
    """Boş içerik "okunamadı" değil: kademe hiçbir şey söylemedi. `json.loads`
    ikisini de istisnaya çevirdiği için ayrımı guard yapıyor — denetim kaydı
    susmayı saçmalamadan ayırt edebilmeli."""
    gateway = _FakeGateway(Response(content=content, model="fast-test"))
    store = Store(":memory:")
    episode = synthesize(gateway, store, _window(), None, "open_episode")
    assert episode is not None and len(store.episodes()) == 1
    assert episode.summary_tr == EMPTY_SUMMARY


def test_prose_from_the_schemaless_retry_does_not_drop_the_episode():
    """`ask()` şemalı istek tükendiğinde şemasız bir son deneme yapıyor
    (Görev 03), yani içerik JSON olmayabilir."""
    gateway = _FakeGateway(Response(content="Elbette! İşte olay özeti:",
                                    model="fast-test"))
    episode = synthesize(gateway, Store(":memory:"), _window(), None,
                         "open_episode")
    assert episode is not None and episode.summary_tr == UNREADABLE_SUMMARY


@pytest.mark.parametrize("content", ['["development"]', "null", "42"])
def test_non_object_json_does_not_drop_the_episode(content):
    gateway = _FakeGateway(Response(content=content, model="fast-test"))
    episode = synthesize(gateway, Store(":memory:"), _window(), None,
                         "open_episode")
    assert episode is not None and episode.summary_tr == UNREADABLE_SUMMARY


def test_an_over_long_summary_is_trimmed_instead_of_collapsing_the_episode():
    """`maxLength` tele çıkmıyor (Görev 03), yani model 600'ü aşabilir. Ham
    hâliyle pydantic'e verilirse gerçek bir epizot kabuğa çöker."""
    long_summary = "İstif aracı devrildi ve yerde hareketsiz bir kişi var. " * 20
    assert len(long_summary) > 600
    gateway = _FakeGateway(Response(content=json.dumps(
        {"phase": "development", "summary_tr": long_summary,
         "participants": [], "preliminary_risk": "Kritik"},
        ensure_ascii=False), model="fast-test"))
    episode = synthesize(gateway, Store(":memory:"), _window(), None,
                         "open_episode")
    assert len(episode.summary_tr) <= 600
    assert episode.summary_tr != UNREADABLE_SUMMARY
    assert episode.summary_tr.startswith("İstif aracı devrildi")
    assert episode.preliminary_risk == "Kritik"


def test_an_unknown_phase_falls_back_to_development():
    gateway = _FakeGateway(Response(content=json.dumps(
        {"phase": "baslangic", "summary_tr": "kısa özet",
         "participants": [], "preliminary_risk": "Orta"},
        ensure_ascii=False), model="fast-test"))
    episode = synthesize(gateway, Store(":memory:"), _window(), None,
                         "open_episode")
    assert episode.phase == "development"
    assert episode.summary_tr == "kısa özet", "faz düzeltmesi özeti düşürmemeli"


def test_an_invalid_risk_level_does_not_drop_the_episode():
    gateway = _FakeGateway(Response(content=json.dumps(
        {"phase": "onset", "summary_tr": "kısa özet",
         "participants": [], "preliminary_risk": "Critical"},
        ensure_ascii=False), model="fast-test"))
    episode = synthesize(gateway, Store(":memory:"), _window(), None,
                         "open_episode")
    assert episode is not None and episode.preliminary_risk == "Orta"


# --- boş pencere ----------------------------------------------------------

def test_an_empty_window_produces_nothing():
    store = Store(":memory:")
    gateway = _gateway()
    assert synthesize(gateway, store, [], None, "open_episode") is None
    assert store.episodes() == [] and store.handoffs() == []
    assert gateway.calls == []


# --- devir teslim ---------------------------------------------------------

def test_synthesize_records_a_handoff_to_the_risk_analyst():
    store = Store(":memory:")
    synthesize(_gateway(), store, _window(), None, "open_episode")
    handoff = store.handoffs()[-1]
    assert handoff.source_agent == "anomaly_analyst"
    assert handoff.target_agent == "risk_analyst"
    assert handoff.payload_ref == f"episode:{store.episodes()[0].id}"


def test_the_handoff_carries_the_current_window_not_the_episode_start():
    """Devir teslim defterinin saati epizot boyunca donmamalı: `start_ts`
    kullanılırsa uzun bir olayın bütün devirleri ilk pencereye damgalanır."""
    store = Store(":memory:")
    synthesize(_gateway(), store, _window(0), None, "open_episode")
    synthesize(_gateway(), store, _window(30), None, "update_episode")
    assert store.episodes()[0].start_ts == 0.0
    assert store.handoffs()[-1].ts == 30.0


# --- klip içi anlar epizoda mutlak zamanla taşınıyor ------------------------
#
# Yorum, anları klibin BAŞINDAN itibaren saniye olarak veriyor; epizot video
# saatinde yaşıyor. Çevirinin tek yeri burası: `window[0].ts + offset_s`.

def _interpretation(beats, observation_ts=5.0):
    return Interpretation(observation_ts=observation_ts, description="d",
                          model="m", beats=beats, severity="olay")


def test_beats_land_on_the_episode_as_absolute_video_time():
    store = Store(":memory:")
    interpretation = _interpretation([ClipBeat(offset_s=3.0,
                                               text="raf çökmeye başlıyor")])
    episode = synthesize(_gateway(), store, _window(10), interpretation,
                         "open_episode")
    assert [(b.ts, b.text) for b in episode.beats] == [
        (13.0, "raf çökmeye başlıyor")]


def test_the_window_start_not_the_middle_stamp_anchors_the_beats():
    """`Interpretation.observation_ts` pencerenin ORTA damgası; klibin
    başlangıcı `window[0].ts`. İkisi karışırsa her an yarım pencere kayar."""
    store = Store(":memory:")
    episode = synthesize(_gateway(), store, _window(20),
                         _interpretation([ClipBeat(offset_s=0.0, text="an")],
                                         observation_ts=25.0),
                         "open_episode")
    assert episode.beats[0].ts == 20.0


def test_an_interpretation_without_beats_leaves_the_episode_empty():
    store = Store(":memory:")
    episode = synthesize(_gateway(), store, _window(0), _interpretation([]),
                         "open_episode")
    assert episode.beats == []


def test_a_window_without_an_interpretation_leaves_the_episode_empty():
    store = Store(":memory:")
    episode = synthesize(_gateway(), store, _window(0), None, "open_episode")
    assert episode.beats == []


def test_updating_an_episode_keeps_the_earlier_beats():
    """Kaynaşma anları EZERSE tam olarak düzeltmeye çalıştığımız şeyi geri
    getirir: olayın başladığı an, sonraki pencere geldiğinde kaybolur."""
    store = Store(":memory:")
    synthesize(_gateway(), store, _window(10),
               _interpretation([ClipBeat(offset_s=3.0, text="çökme başlıyor")]),
               "open_episode")
    synthesize(_gateway(), store, _window(20),
               _interpretation([ClipBeat(offset_s=2.0, text="toz yayılıyor")]),
               "update_episode")
    assert [(b.ts, b.text) for b in store.episodes()[0].beats] == [
        (13.0, "çökme başlıyor"), (22.0, "toz yayılıyor")]


def test_the_same_beat_is_not_recorded_twice():
    store = Store(":memory:")
    beat = [ClipBeat(offset_s=1.0, text="aynı an")]
    synthesize(_gateway(), store, _window(0), _interpretation(beat),
               "open_episode")
    synthesize(_gateway(), store, _window(0), _interpretation(beat),
               "update_episode")
    assert len(store.episodes()[0].beats) == 1


def test_beat_overflow_no_longer_drops_the_middle():
    """26 Ağu ölçümü: baş+son tavanı 40-60sn'deki kazayı (istif aracının
    devrildiği pencereler) `events[]`'ten düşürdü — hem eski yalnız-baş
    kuralı hem de onun yerine konan baş+son kuralı aynı hatayı işledi, ikisi
    de POZİSYONEL. `_merge_beats` artık hiçbir anı atmıyor: her an ödenmiş
    bir VLM çağrısının çıktısı. `existing` + `fresh` toplamı 48'i aşıyor ve
    aradaki zaman damgaları eski baş+son kuralının atacağı bölgede."""
    existing = [EventBeat(ts=float(i), text=f"an {i}") for i in range(30)]
    fresh = [EventBeat(ts=float(30 + i), text=f"an {30 + i}")
             for i in range(30)]
    merged = _merge_beats(existing, fresh)
    middle = next((b for b in merged if b.text == "an 40"), None)
    assert middle is not None and middle.ts == 40.0
    distinct = {(round(b.ts, 1), b.text) for b in existing + fresh}
    assert len(merged) == len(distinct) == 60
    assert [b.ts for b in merged] == sorted(b.ts for b in merged)


def test_an_episode_accumulates_a_beat_per_distinct_interpreted_window():
    """Büyümeyi artık pozisyonel bir tavan değil, dedup anahtarı
    (`round(ts,1), text`) sınırlıyor: aynı pencereyi tekrar kaynaştırmak
    hiçbir şey eklemiyor, dolayısıyla liste FARKLI yorumlanan pencere
    sayısı × pencere başına an tavanıyla (`MAX_BEATS`, interpreter.py) sınırlı
    kalıyor."""
    store = Store(":memory:")
    synthesize(_gateway(), store, _window(0), None, "open_episode")
    window_count = 30
    for window_start in range(0, window_count * 10, 10):
        synthesize(_gateway(), store, _window(window_start),
                   _interpretation([ClipBeat(offset_s=float(i), text=f"an {i}")
                                    for i in range(6)]),
                   "update_episode")
    assert len(store.episodes()[0].beats) == window_count * 6


def test_beats_survive_the_store_round_trip():
    """`Episode` `extra="forbid"`; SQLite yükü tam olarak geri okunmalı."""
    store = Store(":memory:")
    synthesize(_gateway(), store, _window(10),
               _interpretation([ClipBeat(offset_s=3.0, text="raf çöktü")]),
               "open_episode")
    reread = store.episodes()[0]
    assert reread.beats[0].ts == 13.0 and reread.beats[0].text == "raf çöktü"


def test_closing_an_episode_keeps_its_beats():
    store = Store(":memory:")
    synthesize(_gateway(), store, _window(10),
               _interpretation([ClipBeat(offset_s=3.0, text="raf çöktü")]),
               "open_episode")
    synthesize(_gateway(), store, _window(20), None, "close_episode")
    episode = store.episodes()[0]
    assert episode.state == "closed" and episode.beats[0].ts == 13.0


def test_the_event_moment_falls_back_to_the_window_start_without_beats():
    store = Store(":memory:")
    episode = synthesize(_gateway(), store, _window(10), None, "open_episode")
    assert episode.event_ts == episode.start_ts == 10.0


def test_the_event_moment_is_the_first_beat_when_there_is_one():
    store = Store(":memory:")
    episode = synthesize(_gateway(), store, _window(10),
                         _interpretation([ClipBeat(offset_s=3.0, text="a"),
                                          ClipBeat(offset_s=5.0, text="b")]),
                         "open_episode")
    assert episode.start_ts == 10.0 and episode.event_ts == 13.0


# --- arıza metni olay tarifi değildir (Görev 20) -----------------------------

def test_a_fallback_summary_is_marked_as_a_diagnostic_not_an_observation():
    """26 Ağustos canlı koşusu: sentezleyici boş döndü, epizodun özeti
    "Sentez katmanı boş yanıt döndürdü" oldu ve süpervizör bunu fabrikada
    olmuş bir olay sanıp var olmayan bir bölgeye alarm çaldırdı, sağlık ekibi
    çağırdı. Metin okunarak ayırt edilemez; yapısal bir işaret şart."""
    from gozcu.agents.anomaly_analyst import EMPTY_SUMMARY, _fallback

    fallback = _fallback(EMPTY_SUMMARY)
    assert fallback.summary_source == "fallback"


def test_a_real_synthesis_is_not_marked_as_a_diagnostic():
    from gozcu.agents.anomaly_analyst import _parse

    parsed = _parse('{"phase": "onset", "summary_tr": "İstif aracı devrildi.",'
                    ' "preliminary_risk": "Kritik", "participants": []}')
    assert parsed is not None
    assert parsed.summary_source == "model"


def test_a_fallback_summary_never_reenters_the_prompt_as_an_event():
    """Spec §1: 'Sentez üretilemedi' bir olay tarifi değildir. 26 Ağustos
    canlı koşusunda bu metin bir sonraki pencerenin prompt'una olay tarifi
    olarak girdi ve model onu fabrikada duran bir "sentez hattı"na çevirdi."""
    previous = Episode(start_ts=0.0, phase="development",
                       summary_tr=UNREADABLE_SUMMARY,
                       preliminary_risk="Orta", summary_source="fallback")
    text = _digest(_window(start=0.0), None, previous)
    assert UNREADABLE_SUMMARY not in text
    assert "tarif üretilemedi" in text  # nötr işaret satırı var


def test_a_fallback_synthesis_does_not_overwrite_a_model_summary():
    """Spec §1 kaynaşma koruması: son pencere arızalansa da model özeti
    yaşar — yedek onu bir arıza metnine düşürmemeli."""
    store = Store(":memory:")
    good = _FakeGateway(Response(content=json.dumps({
        "phase": "development", "summary_tr": "Forklift devrildi.",
        "participants": ["IST-07"], "preliminary_risk": "Yüksek"},
        ensure_ascii=False), model="fast-test"))
    synthesize(good, store, _window(start=0.0), None, "open_episode")

    window = _window(start=10.0)
    episode = synthesize(_FakeGateway(Response(content="", model="fast-test")),
                         store, window, None, "update_episode")  # boş yanıt → fallback
    assert episode.summary_tr == "Forklift devrildi."
    assert episode.summary_source == "model"
    assert episode.participants == ["IST-07"]
    assert episode.preliminary_risk == "Yüksek"
    assert episode.end_ts == window[-1].ts     # kaynaşma normal işledi


# --- olay sınıfı ve bölge (Görev 2 — spec §2b) -----------------------------
#
# Görev 3/4'ün protokol süzgeci bu iki alandan okuyor; brief'in verdiği
# `_gw`/`store` bu dosyada yok — dosyanın gerçek deseni `_FakeGateway` ve her
# testin kendi `Store(":memory:")`'si, o yüzden aşağıdaki dört test buna göre
# yazıldı.

def _gw(content: str) -> _FakeGateway:
    return _FakeGateway(Response(content=content, model="fast-test"))


def test_episode_carries_event_class_and_zone():
    """Sentez epizoda tipli olay sınıfı ve bölge yazar (spec §2b)."""
    payload = json.dumps({
        "phase": "development",
        "summary_tr": "İstif aracı raf ayağına çarptı, malzeme devrildi.",
        "participants": ["IST-04", "PRS-001"],
        "preliminary_risk": "Yüksek",
        "event_class": "çarpma",
        "zone_id": "line_b",
    }, ensure_ascii=False)
    store = Store(":memory:")
    episode = synthesize(_gw(payload), store, _window(), None, "open_episode")
    assert episode.event_class == "çarpma"
    assert episode.zone_id == "line_b"


def test_unknown_event_class_falls_back_to_diger():
    """Uydurulmuş sınıf hiçbir protokolle eşleşmez; sessiz boş plan yerine
    açıkça `"diğer"` (spec §2b)."""
    payload = json.dumps({
        "phase": "development", "summary_tr": "Bir şey oldu.",
        "participants": [], "preliminary_risk": "Orta",
        "event_class": "uzaylı istilası", "zone_id": "line_b",
    }, ensure_ascii=False)
    store = Store(":memory:")
    episode = synthesize(_gw(payload), store, _window(), None, "open_episode")
    assert episode.event_class == "diğer"


def test_zone_id_normalised_via_resolve_zone():
    """Model zone_id olarak takma ad ya da saçma bir şey gönderirse
    resolve_zone ile çözülür; tanınmayan ad None'a düşer."""
    good_alias = json.dumps({
        "phase": "onset", "summary_tr": "Test.",
        "participants": [], "preliminary_risk": "Orta",
        "event_class": "diğer", "zone_id": "B-Hattı",
    }, ensure_ascii=False)
    store = Store(":memory:")
    episode = synthesize(_gw(good_alias), store, _window(), None, "open_episode")
    assert episode.zone_id == "line_b"

    bad = json.dumps({
        "phase": "onset", "summary_tr": "Test2.",
        "participants": [], "preliminary_risk": "Orta",
        "event_class": "diğer", "zone_id": "mars_colony",
    }, ensure_ascii=False)
    store2 = Store(":memory:")
    episode2 = synthesize(_gw(bad), store2, _window(), None, "open_episode")
    assert episode2.zone_id is None


def test_system_prompt_zone_ids_from_facility():
    """Prompt'taki bölge listesi facility.json'dan türetilmeli, elle yazılmamalı."""
    from gozcu.agents.anomaly_analyst import SYSTEM_PROMPT, _ZONE_IDS
    from gozcu.fixtures.loader import load_fixture
    expected = [z["zone_id"] for z in load_fixture("facility")["zones"]]
    assert _ZONE_IDS == expected
    for zid in expected:
        assert f'"{zid}"' in SYSTEM_PROMPT, f"prompt {zid} saymıyor"


def test_system_prompt_lists_event_classes_verbatim():
    """CLAUDE.md: prompt bir enum sayıyorsa değerleri şemadakiyle birebir."""
    from typing import get_args
    from gozcu.agents.anomaly_analyst import SYSTEM_PROMPT
    from gozcu.models import EventClass
    for value in get_args(EventClass):
        assert f'"{value}"' in SYSTEM_PROMPT, f"prompt {value} saymıyor"


def test_fallback_does_not_overwrite_model_event_class():
    """Yedek yanıt, modelin biçtiği sınıfı EZMEZ — `summary_tr` ile aynı kural."""
    store = Store(":memory:")
    good = json.dumps({"phase": "onset", "summary_tr": "Çarpma oldu.",
                       "participants": [], "preliminary_risk": "Yüksek",
                       "event_class": "çarpma", "zone_id": "line_b"},
                      ensure_ascii=False)
    synthesize(_gw(good), store, _window(), None, "open_episode")
    episode = synthesize(_gw("bu JSON değil"), store, _window(start=10.0),
                         None, "update_episode")
    assert episode.event_class == "çarpma"
    assert episode.zone_id == "line_b"


# --- source damgası ---------------------------------------------------------

def test_a_new_episode_is_stamped_with_the_source_at_birth():
    """Kapanışta damgalansaydı `assess_risk` açık epizotta koşarken elde
    `"None:0"` olurdu ve epizot kendi emsali olarak listenin başına otururdu."""
    store = Store(":memory:")
    episode = synthesize(_gateway(), store, _window(), None,
                         "open_episode", source="9f2a")
    assert episode.source == "9f2a"


def test_updating_an_open_episode_does_not_overwrite_its_source():
    """Epizot `source`'unu doğuşundan taşıyor; güncelleme dalı ona dokunmaz —
    dokunursa `catch_up` ile gelen bir pencere onu yanlış videoya bağlayabilir."""
    store = Store(":memory:")
    open_ep = synthesize(_gateway(), store, _window(0), None,
                      "open_episode", source="9f2a")
    updated = synthesize(_gateway(), store, _window(10), None,
                        "update_episode", source="BAŞKA")
    assert updated.id == open_ep.id
    assert updated.source == "9f2a"


# --- kapanmış epizotların digest'i (§8.3) ---------------------------------

def test_the_digest_remembers_episodes_that_already_closed():
    """Bugün epizot kapanınca öncesi TAMAMEN unutuluyor: `_digest` yalnız
    AÇIK epizodun özetini başa koyuyor."""
    closed = Episode(id=1, start_ts=0.0, end_ts=30.0, phase="outcome",
                     summary_tr="raf hizasında zor durdu",
                     preliminary_risk="Orta", state="closed")
    text = _digest(_window(start=60.0), None, None, closed=[closed])
    assert "raf hizasında zor durdu" in text


def test_the_open_episode_still_leads_the_digest():
    """`DEVAM EDEN OLAY:` satırı BAŞTA kalmalı — kaynaşmanın süreklilik
    tarafı o satıra bağlı."""
    open_ep = Episode(id=2, start_ts=50.0, end_ts=60.0, phase="development",
                      summary_tr="istif aracı devriliyor",
                      preliminary_risk="Kritik", state="open")
    closed = Episode(id=1, start_ts=0.0, end_ts=30.0, phase="outcome",
                     summary_tr="raf hizasında zor durdu",
                     preliminary_risk="Orta", state="closed")
    lines = _digest(_window(start=60.0), None, open_ep,
                    closed=[closed]).splitlines()
    assert lines[0].startswith("DEVAM EDEN OLAY:")
    assert any("raf hizasında zor durdu" in line for line in lines[1:])


def test_synthesize_actually_fills_the_closed_episodes():
    """Parametreyi eklemek YETMEZ: `synthesize` onu doldurmazsa özellik
    testlerde yeşil, üretimde ölü kalır."""
    store = Store(":memory:")
    gateway = _gateway()
    synthesize(gateway, store, _window(0), None, "open_episode")
    synthesize(gateway, store, _window(10), None, "close_episode")
    synthesize(gateway, store, _window(20), None, "open_episode")
    assert "İstif aracı devrildi" in gateway.user_content


def test_a_fallback_summary_never_enters_the_digest_of_the_next_window():
    """Arıza metni bir olay tarifi değildir; digest'e girerse bir sonraki
    pencerenin özetini zehirler (`models.py:149`)."""
    store = Store(":memory:")
    broken = Episode(start_ts=0.0, end_ts=9.0, phase="outcome",
                     summary_tr=EMPTY_SUMMARY, preliminary_risk="Orta",
                     state="closed", summary_source="fallback")
    store.create_episode(broken)
    gateway = _gateway()
    synthesize(gateway, store, _window(20), None, "open_episode")
    assert EMPTY_SUMMARY not in gateway.user_content


def test_the_digest_without_closed_episodes_is_unchanged():
    """`closed` varsayılanı `None`: `_digest`'in bugünkü bütün çağıranları
    aynen çalışıyor."""
    assert _digest(_window(), None, None) == _digest(_window(), None, None,
                                                     closed=None)
    assert "ÖNCEKİ OLAYLAR" not in _digest(_window(), None, None, closed=[])


# --- `run.py`'deki `RunMemory` beslemesi ----------------------------------
#
# Besleme Görev 15'te indi ama HİÇBİR test onu kapsamıyordu: kapanış doğru
# epizodu döndürdüğü için mevcut testler yeşildi, `note()`'un doğru alanlarla
# çağrıldığını ise kimse iddia etmiyordu. Kapanış `run_pipeline`'ın yereli
# olan bir lambda, o yüzden tek erişim yolu boru hattını sahte algı ve sahte
# ağ geçidiyle koşturmak.

class _RecordingMemory:
    """`RunMemory` ikizi: `note()`'a ne geçildiğini kaydeder.

    `render()` gerçek imzayı taşımak zorunda — yorumlayıcı kapanışı bu
    nesneyi `recall=` olarak alıyor ve prompt'u ondan üretiyor.
    """

    def __init__(self, limit=None) -> None:
        self.notes: list[dict] = []

    def note(self, **kwargs) -> None:
        self.notes.append(kwargs)

    def recent(self, n=None) -> list:
        return []

    def render(self, n=None) -> str:
        return ""


def _pipeline(monkeypatch, tmp_path, gateway):
    """Ağsız, ffmpeg'siz bir koşu; beslemenin kaydını döndürür."""
    from gozcu import run as run_module
    from gozcu.frames import Frame
    from gozcu.signals import FrameSignals
    from gozcu.track import TrackedObject

    frames = [Frame(path=tmp_path / f"frame_{i:04d}.jpg",
                    timestamp_s=float(i), index=i) for i in range(4)]
    tracked = [[TrackedObject(class_name="forklift", confidence=0.9,
                              bbox=(0, 0, 10, 10), track_id=1)]
               for _ in frames]
    signals = [FrameSignals(person_count=2, velocities={1: 4.0})
               for _ in frames]
    clip = tmp_path / "window.mp4"
    clip.write_bytes(b"\x00fake-mp4")
    monkeypatch.setattr(run_module, "extract_frames", lambda *a, **k: frames)
    monkeypatch.setattr(run_module, "track_video", lambda *a, **k: tracked)
    monkeypatch.setattr(run_module, "compute_signals", lambda *a, **k: signals)
    monkeypatch.setattr(run_module, "_clip_for",
                        lambda *a, **k: lambda start, end: clip)

    recorded: list[_RecordingMemory] = []

    def _memory(*a, **k):
        recorded.append(_RecordingMemory())
        return recorded[-1]

    monkeypatch.setattr(run_module, "RunMemory", _memory)
    run_module.run_pipeline("video.mp4", store=Store(":memory:"), gw=gateway,
                            output_dir=tmp_path, archive=False)
    assert recorded, "`RunMemory` hiç kurulmadı"
    return recorded[0].notes


class _PipelineGateway:
    """Kademe başına sabit senaryo döndüren ağ geçidi ikizi."""

    VISION = json.dumps({"description": "İstif aracı sallanıyor.",
                         "notable_event": "Araç devrildi.",
                         "severity": "olay"})
    RISK = json.dumps({"level": "Kritik", "rationale_tr": "yerde kişi var",
                       "preventable": True, "proposed_actions": []})
    REPORT = json.dumps({"what_happened": "devrilme",
                         "probable_root_cause": "fren",
                         "actions_taken": [],
                         "prevention_recommendations": [],
                         "confidence_limits": "ses yok"})

    def __init__(self, decision="escalate", blind=False) -> None:
        self.decision, self.blind = decision, blind

    def ask(self, tier, messages, schema=None, tools=None, max_tokens=None,
            temperature=None, _retries=None) -> Response:
        if tier == "router":
            return Response(content=json.dumps(
                {"decision": self.decision, "rationale": "sinyal var",
                 "confidence": 0.9}))
        if tier == "vlm":
            return (Response(model="vlm", degraded=True) if self.blind
                    else Response(content=self.VISION, model="vlm"))
        if tier == "fast":
            return Response(content=RESPONSE_JSON)
        if tier == "guard":
            return Response(content="uygun")
        if tier == "main":
            report = getattr(schema, "__name__", "") == "RootCauseReport"
            return Response(content=self.REPORT if report else self.RISK)
        return Response(degraded=True)

    def embed(self, text):
        return []

    def is_degraded(self, tier=None) -> bool:
        return bool(self.blind) and tier in (None, "vlm")


def test_the_run_feeds_the_memory_with_the_windows_own_fields(monkeypatch,
                                                              tmp_path):
    """Kapanış `note()`'u pencerenin İLK damgası, yorumun tarifi, penceredeki
    etiketler, yönlendiricinin ÇÖZÜLMÜŞ kararı ve yorumun derecelendirmesiyle
    çağırıyor. Beşi de ayrı bir kaynaktan geliyor ve hiçbirini kimse iddia
    etmiyordu."""
    notes = _pipeline(monkeypatch, tmp_path, _PipelineGateway())
    assert notes, "besleme hiç çalışmadı"
    first = notes[0]
    assert set(first) == {"ts", "moment", "participants", "decision",
                          "severity"}
    assert first["ts"] == 0.0
    assert first["moment"] == "İstif aracı sallanıyor."
    assert first["participants"] == ["forklift"]
    assert first["severity"] == "olay"
    assert first["decision"] in ("open_episode", "update_episode")


def test_a_window_the_vision_layer_never_read_is_still_noted(monkeypatch,
                                                             tmp_path):
    """Görü katmanı okumadıysa `description` YOK. Kapanış o pencereyi
    atlamıyor: hafızada bir boşluk, sonraki pencerenin bağlamını sessizce
    kaydırırdı."""
    notes = _pipeline(monkeypatch, tmp_path,
                      _PipelineGateway(decision="close_episode"))
    assert notes, "besleme hiç çalışmadı"
    assert notes[0]["moment"] == "(görü katmanı bu pencereyi okumadı)"
    assert notes[0]["severity"] == "rutin"
    assert notes[0]["decision"] == "close_episode"
