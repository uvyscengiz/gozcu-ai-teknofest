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
                                      _SynthesisResponse, synthesize)
from gozcu.gateway import Response
from gozcu.models import Interpretation, Observation, Signals
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
