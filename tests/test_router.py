"""Yönlendirici ajanının testleri.

Sahte gateway bilerek `Mock()` değil. Görev dosyasının testleri `Mock()`
kullanıyordu ve hiçbiri `schema=` geçilip geçilmediğine bakmıyordu: `schema`
argümanını tamamen silmek altı testi de yeşil bırakıyordu — sertleştirme
kusuru tam bu yüzden görünmez kaldı. `_FakeGateway` `Gateway.ask` imzasını
birebir taşır ve ne ile çağrıldığını kaydeder.
"""

import json
import re
from typing import get_args

import pytest

from gozcu.agents.router import (MAX_DECISION_TOKENS, MAX_RATIONALE,
                                 SYSTEM_PROMPT, _WINDOW_VERDICT_LABELS,
                                 mmss, route, window_digest,
                                 window_signal_verdict)
from gozcu.gateway import Response
from gozcu.models import EventSummary, Observation, RouterDecision

DECISION = '{"decision":"escalate","rationale":"araç devrildi","confidence":0.91}'


class _FakeGateway:
    """Şekilli sahte: kademe, mesajlar ve şema tek tek incelenebilir."""

    def __init__(self, response: Response | None = None) -> None:
        self.response = response if response is not None else Response(
            content=DECISION, model="router-test")
        self.calls: list[dict] = []

    def ask(self, tier, messages, schema=None, tools=None,
            max_tokens=None, temperature=None) -> Response:
        self.calls.append({"tier": tier, "messages": messages,
                           "schema": schema, "tools": tools,
                           "max_tokens": max_tokens})
        return self.response

    @property
    def last(self) -> dict:
        assert self.calls, "gateway hiç çağrılmadı"
        return self.calls[-1]


def _observation(ts, **signals) -> Observation:
    return Observation(ts=ts, signals=signals)


def _prompt_text(gateway: _FakeGateway) -> str:
    return gateway.last["messages"][-1]["content"]


# --- mmss -----------------------------------------------------------------

def test_mmss_formats_video_time():
    assert mmss(192.0) == "03:12" and mmss(0.0) == "00:00"


def test_mmss_clamps_instead_of_emitting_an_invalid_timestamp():
    """Saat devri yok: `mmss(6000)` düz hesapla "100:00" verir ve bu
    `EventSummary.time`'ın `^\\d{2}:\\d{2}$` desenini ihlal eder — Görev 17'de
    doğrulama hatası olur. Demo klipleri dakikalarla ölçülüyor, o yüzden saat
    desteği kapsam dışı; ama geçersiz bir damga da üretilmemeli."""
    assert mmss(6000.0) == "99:59"
    assert re.fullmatch(r"\d{2}:\d{2}", mmss(6000.0))
    EventSummary(time=mmss(6000.0), event="devrilme")


# --- window_digest --------------------------------------------------------

def test_digest_is_one_stamped_line_per_observation():
    """Görev dosyasının `"base64" not in digest` iddiası boştu — herhangi bir
    Türkçe metin geçiyordu. Asıl sözleşme şu: gözlem başına bir satır, başında
    zaman damgası, gövdesinde o gözlemin sinyalleri.

    Hız `.2f` ile basılıyor (26 Ağustos): birim artık kare genişliği/saniye
    ve tipik değerler 0.01-0.6 aralığında — tek ondalık basamak medyan
    hareketi hep "0.0"a yuvarlardı (bkz. `gozcu.signals`)."""
    digest = window_digest([_observation(0.0, person_count=2, velocities={1: 0.34}),
                            _observation(61.0, vanished_tracks=[1])])
    lines = digest.splitlines()
    assert len(lines) == 2
    assert lines[0] == "00:00 kişi=2 hızlar=1:0.34"
    assert lines[1] == "01:01 kişi=0 kaybolan=[1]"


def test_digest_reports_the_remaining_signals():
    digest = window_digest([_observation(5.0, person_count=4,
                                         person_count_delta=3, gathering=True)])
    assert digest == "00:05 kişi=4 değişim=+3 toplanma"


def test_digest_of_an_empty_window_is_empty():
    assert window_digest([]) == ""


# --- prompt ---------------------------------------------------------------

def test_the_prompt_lists_exactly_the_schema_decision_values():
    """CLAUDE.md: bir prompt enum sayıyorsa değerleri şemadakiyle birebir aynı
    olmalı. Bu bir kez ayrıldı ve sistem sessizce ölü hâle geldi."""
    listed = re.findall(r"(?m)^- ([a-z_]+):", SYSTEM_PROMPT)
    assert listed == list(get_args(
        RouterDecision.model_fields["decision"].annotation))


def test_the_prompt_spells_every_decision_value_byte_identically():
    """Enumerasyon testinin tamamlayıcısı: madde biçimi değişse bile altı
    değerin promptta HARFİ HARFİNE geçtiğini ve promptun şemada olmayan bir
    karar adı uydurmadığını korur. `open_epizot` gibi tek harflik bir kayma
    modeli sessizce şema dışı bir değere iter ve karar `ignore`'a çöker."""
    values = list(get_args(
        RouterDecision.model_fields["decision"].annotation))
    for value in values:
        assert re.search(rf"(?<![a-z_]){re.escape(value)}(?![a-z_])",
                         SYSTEM_PROMPT), f"promptta eksik: {value}"
    # Promptta geçen her `alt_çizgili` jeton şemadan gelmeli.
    assert set(re.findall(r"(?<![a-z_])[a-z]+_[a-z]+(?![a-z_])",
                          SYSTEM_PROMPT)) <= set(values)


def test_the_decision_request_carries_a_token_ceiling():
    """Canlı ölçüm (25 Ağustos): tavansız istekler altı pencerelik probun
    dördünde ~243 saniye sürüp ayrıştırılamayan içerikle döndü — strict-JSON
    kod çözümü kaçak tekrara giriyor. Ayrıştırılamayan yanıt `_fallback`
    üzerinden `ignore`'a çöküyor, yani tavanın yokluğu doğrudan
    eksik-tetikleme demek."""
    gw = _FakeGateway()
    route(gw, [_observation(0.0, person_count=3, gathering=True)],
          has_open_episode=False)
    assert gw.last["max_tokens"] == MAX_DECISION_TOKENS
    # 200 karakterlik bir gerekçeyi taşıyan JSON'u kesmeyecek kadar geniş.
    assert MAX_DECISION_TOKENS >= 200


def test_open_episode_state_reaches_the_prompt():
    gw = _FakeGateway()
    route(gw, [_observation(0.0)], has_open_episode=True)
    assert "Açık bir olay var" in _prompt_text(gw)


def test_closed_episode_state_reaches_the_prompt():
    gw = _FakeGateway()
    route(gw, [_observation(0.0)], has_open_episode=False)
    assert "Açık olay yok" in _prompt_text(gw)


# --- hareket enerjisi (26 Ağustos) -----------------------------------------

def test_route_renders_the_windows_energy_into_the_prompt():
    """Yönlendirici görüntü görmüyor ama artık pencerenin bu koşuya göre ne
    kadar hareketli olduğunu biliyor — `gozcu.loop`'un zaten hesapladığı
    enerjiden (bkz. `gozcu.motion.build_motion_for`)."""
    gw = _FakeGateway()
    route(gw, [_observation(0.0, person_count=1)], has_open_episode=False,
          energy=0.97)
    assert "enerji=0.97" in _prompt_text(gw)


def test_route_omits_the_energy_line_cleanly_when_it_is_none():
    """`energy=None` — enjekte edilmemiş ya da bu pencere için kanıt yok —
    satırı prompt'tan sessizce düşürüyor; "enerji=0.0" yazmak "kanıt yok"u
    "durağan" diye okurdu."""
    gw = _FakeGateway()
    route(gw, [_observation(0.0, person_count=1)], has_open_episode=False)
    assert "enerji=" not in _prompt_text(gw)


def test_the_rule_text_uses_the_new_normalized_speed_constants_not_old_pixel_ones():
    """K3'ün eşiği artık kare-genişliği/saniye biriminde (bkz.
    `gozcu.signals`'ın modül başı notu — piksel/saniye sahneye göre yalan
    söylüyordu). Assert doğrudan SABİTLERE karşı, prompttaki metne göre
    değil: metin serbestçe değişebilir, ama kod ve prompt aynı sabitten
    okumalı — CLAUDE.md'nin birim uyuşmazlığı kuralı."""
    from gozcu.agents.router import RUN_SPEED, WALK_SPEED
    assert WALK_SPEED != 1.0 and RUN_SPEED != 4.0
    assert f"{WALK_SPEED:.2f}" in SYSTEM_PROMPT
    assert f"{RUN_SPEED:.2f}" in SYSTEM_PROMPT
    assert "1.0'dan büyük" not in SYSTEM_PROMPT
    assert "4.0 üstü" not in SYSTEM_PROMPT


# --- gateway'e giden istek ------------------------------------------------

def test_route_asks_the_router_tier_with_the_decision_schema():
    """Şemanın gerçekten geçildiğini kimse doğrulamıyordu; `schema=` silinince
    bütün takım yeşil kalıyordu."""
    gw = _FakeGateway()
    route(gw, [_observation(0.0, person_count=1)], has_open_episode=False)
    assert gw.last["tier"] == "router"
    assert gw.last["schema"] is RouterDecision
    assert gw.last["messages"][0]["role"] == "system"
    assert gw.last["messages"][0]["content"] == SYSTEM_PROMPT
    assert "00:00 kişi=1" in _prompt_text(gw)


def test_the_window_digest_reaches_the_prompt_not_an_image():
    gw = _FakeGateway()
    route(gw, [_observation(0.0, person_count=2)], has_open_episode=False)
    assert isinstance(_prompt_text(gw), str)
    assert window_digest([_observation(0.0, person_count=2)]) in _prompt_text(gw)


# --- karar ayrıştırma -----------------------------------------------------

def test_route_parses_the_model_decision():
    gw = _FakeGateway()
    decision = route(gw, [_observation(0.0, person_count=1)],
                     has_open_episode=False)
    assert decision.decision == "escalate" and decision.confidence == 0.91
    assert decision.rationale == "araç devrildi"


def test_unparseable_response_degrades_to_ignore_not_a_crash():
    gw = _FakeGateway(Response(content="model bugün konuşmuyor"))
    assert route(gw, [_observation(0.0)], has_open_episode=False).decision == "ignore"


def test_degraded_router_tier_degrades_to_ignore():
    """Görev dosyasının testi `Response(degraded=True)` kullanıyordu; onun
    `content`'i `""` olduğu için `json.loads("")` aynı yedeğe düşüyor ve
    `degraded` dalını tamamen silmek de testi geçiriyordu. Geçerli JSON taşıyan
    bozuk bir yanıt yalnızca gerçek bir `degraded` kontrolüyle `ignore` verir."""
    gw = _FakeGateway(Response(content=DECISION, degraded=True))
    decision = route(gw, [_observation(0.0)], has_open_episode=False)
    assert decision.decision == "ignore" and decision.confidence == 0.0


# --- modelin döndürdüğü değerlerin temizlenmesi ---------------------------

def test_over_long_rationale_is_truncated_not_dropped():
    """`maxLength` artık tele çıkmıyor (Görev 03 sertleştirmesi), yani model
    sınırı aşabilir. Ham hâliyle pydantic'e verilirse gerçek bir karar
    doğrulama hatasında `ignore`'a çöker."""
    gw = _FakeGateway(Response(content=json.dumps(
        {"decision": "escalate", "rationale": "a" * 500, "confidence": 0.9})))
    decision = route(gw, [_observation(0.0)], has_open_episode=False)
    assert decision.decision == "escalate"
    assert len(decision.rationale) == MAX_RATIONALE


@pytest.mark.parametrize("raw,clamped", [(1.7, 1.0), (-0.5, 0.0), (0.42, 0.42)])
def test_out_of_range_confidence_is_clamped_not_dropped(raw, clamped):
    gw = _FakeGateway(Response(content=json.dumps(
        {"decision": "inspect", "rationale": "kaynak sızıntısı", "confidence": raw})))
    decision = route(gw, [_observation(0.0)], has_open_episode=False)
    assert decision.decision == "inspect" and decision.confidence == clamped


# --- pencere-düzeyi K1/K2/K4 (26 Ağustos, "her pencere inspect" arızası) ---
#
# Ölçüldü (k04, 98.8 sn, 10 pencere, ~30 kare/pencere): koşunun HER
# penceresi en az bir `kaybolanYoğun` VE en az bir `değişimYoğun` kareli
# taşıyordu — "herhangi bir satırda" okunan K1/K2/K4 10/10 pencerede
# `inspect` üretti. Aşağıdaki dört sütun tam o tablo (bkz.
# `gozcu.agents.router`'ın modül başı notu ve decision-log).
K04_ROWS = [
    # (toplanma, kaybolanYoğun, değişimYoğun, tepe hız)
    (14, 4, 5, 0.238),    #  0-10s
    (4, 6, 2, 0.157),     # 10-20s
    (0, 2, 3, 0.100),     # 20-30s
    (1, 4, 5, 0.604),     # 30-40s  <- çarpışma
    (0, 7, 5, 0.293),     # 40-50s  <- devrilme
    (2, 1, 1, 0.218),     # 50-60s
    (15, 4, 14, 0.149),   # 60-70s
    (24, 15, 18, 0.082),  # 70-80s
    (30, 16, 15, 0.193),  # 80-90s
    (26, 8, 9, 0.115),    # 90-98s
]


def _window_with_flags(toplanma=0, kaybolanYoğun=0, değişimYoğun=0, speed=0.0,
                       frames=30):
    """k04'ün ölçtüğü şekilde bir pencere üretir: `frames` karenin ilk
    `toplanma`/`kaybolanYoğun`/`değişimYoğun` tanesi ilgili bayrağı taşıyor,
    ilk karede (varsa) tepe hız var."""
    observations = []
    for i in range(frames):
        signals = {"person_count": 1}
        if i < toplanma:
            signals["gathering"] = True
        if i < kaybolanYoğun:
            signals["vanished_unusual"] = True
        if i < değişimYoğun:
            signals["count_change_unusual"] = True
        if i == 0 and speed:
            signals["velocities"] = {1: speed}
        observations.append(_observation(float(i), **signals))
    return observations


def _k04_run_windows():
    return [_window_with_flags(*row) for row in K04_ROWS]


def test_a_window_ordinary_for_its_run_does_not_trip_the_window_level_flags():
    """20-30s penceresi 2/30 karede `kaybolanYoğun` taşıyor — "herhangi bir
    satırda" okusaydı bu iki kare bile K2'yi tetiklerdi. Koşunun diğer
    pencereleri bunu fersah fersah aşıyor (medyan 5, eşik 10), yani bu
    pencere kendi türünün geri kalanından ayırt edilemiyor ve olağan
    sayılmalı."""
    run_windows = _k04_run_windows()
    quiet_window = run_windows[2]
    assert window_signal_verdict(quiet_window, run_windows) == {
        "toplanma": False, "kaybolanYoğun": False, "değişimYoğun": False}


def test_a_window_unusual_for_its_run_trips_the_window_level_flags():
    """80-90s: üç bayrağın da kare sayısı koşunun medyanının kat kat üstünde
    (30/16/15 vs medyan 9/5/5) — kalabalıklaşan sonrasının bir parçası,
    gerçekten olağandışı."""
    run_windows = _k04_run_windows()
    busy_window = run_windows[8]
    assert window_signal_verdict(busy_window, run_windows) == {
        "toplanma": True, "kaybolanYoğun": True, "değişimYoğun": True}


def test_the_crash_shaped_window_still_trips_via_k3():
    """K3 pencere MAKSİMUMUNA bakıyor ve bu düzeltmeden etkilenmiyor: 30-40s
    penceresinin 0.604'lük tepe hızı hâlâ `WALK_SPEED`'i (0.25) aşıyor ve
    digest'te aynen görünüyor — bu düzeltme K1/K2/K4'ün AGGREGASYONUNU
    değiştiriyor, K3'ün şeklini değil."""
    from gozcu.agents.router import WALK_SPEED
    crash_window = _k04_run_windows()[3]
    peak_speed = max(speed for o in crash_window
                     for speed in o.signals.velocities.values())
    assert peak_speed > WALK_SPEED
    assert f"{peak_speed:.2f}" in window_digest(crash_window)


def test_the_rule_text_references_the_window_level_flags_not_any_row():
    """K1/K2/K4 artık `_WINDOW_VERDICT_LABELS`'tan okunan pencere-düzeyi
    etiketlere bakıyor — prompt'ta elle yeniden yazılmış bir kelimeye değil.
    Assert paylaşılan SABİTE karşı, kendi yazdığımız bir prose'a karşı değil:
    etiketler ayrışırsa bu test de ayrışmayı yakalar."""
    rule_lines = {line.split(".", 1)[0]: line
                 for line in SYSTEM_PROMPT.splitlines()
                 if line.startswith(("K1.", "K2.", "K4."))}
    assert _WINDOW_VERDICT_LABELS["toplanma"] in rule_lines["K1"]
    assert _WINDOW_VERDICT_LABELS["kaybolanYoğun"] in rule_lines["K2"]
    assert _WINDOW_VERDICT_LABELS["değişimYoğun"] in rule_lines["K4"]
    for rule_line in rule_lines.values():
        assert "Herhangi bir satırda" not in rule_line


def test_route_renders_the_window_level_verdict_when_run_windows_is_given():
    gw = _FakeGateway()
    run_windows = _k04_run_windows()
    route(gw, run_windows[8], has_open_episode=False, run_windows=run_windows)
    prompt = _prompt_text(gw)
    assert "pencereBayrakları=" in prompt
    assert _WINDOW_VERDICT_LABELS["toplanma"] in prompt


def test_route_omits_the_window_level_line_cleanly_when_run_windows_is_none():
    """`run_windows=None` — koşunun diğer pencereleri bilinmiyor — satırı
    `_energy_line` ile aynı desende sessizce düşürüyor; "pencereBayrakları=yok"
    yazmak "ölçülemedi"yi "olağan" diye okurdu."""
    gw = _FakeGateway()
    route(gw, [_observation(0.0, person_count=1)], has_open_episode=False)
    assert "pencereBayrakları=" not in _prompt_text(gw)
