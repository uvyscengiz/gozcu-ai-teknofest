"""Sentezleyicinin testleri — dağınık pencereler tek bir epizota dönüşüyor mu.

Sahte gateway bilerek `Mock()` değil: bu depoda yedi kusur şekilsiz bir
`Mock()` collaborator'ın arkasında saklandı. `_FakeGateway` hangi kademeye,
hangi mesajlarla ve hangi şemayla gidildiğini kaydeder ve gerçek bir
`Response` döndürür — böylece "modele ne gitti" sorusu test edilebilir bir
soru oluyor.
"""

import json

import pytest

from gozcu.agents.router import mmss
from gozcu.agents.synthesizer import (DEGRADED_SUMMARY, EMPTY_SUMMARY, PHASES,
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
                                    description="araç yan yattı", model="m")
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
        observation_ts=5.0, model="vlm-test",
        description="istif aracı yan yattı, forkliftin altında kişi var")
    synthesize(gateway, Store(":memory:"), _window(), interpretation,
               "open_episode")
    assert interpretation.description in gateway.user_content


def test_the_interpretation_is_stamped_with_its_own_observation_ts():
    """`Interpretation.observation_ts` pencerenin ORTA damgası (Görev 04);
    yorumu `window[0].ts` ile damgalayan kod yalan söyler."""
    gateway = _gateway()
    interpretation = Interpretation(observation_ts=5.0, model="vlm-test",
                                    description="araç yan yattı")
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
    assert handoff.source_agent == "synthesizer"
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
                          model="m", beats=beats)


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
    from gozcu.agents.synthesizer import EMPTY_SUMMARY, _fallback

    fallback = _fallback(EMPTY_SUMMARY)
    assert fallback.summary_source == "fallback"


def test_a_real_synthesis_is_not_marked_as_a_diagnostic():
    from gozcu.agents.synthesizer import _parse

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
