"""Görev 16 — operatör konsolunun saf katmanları.

Widget bağlantısı test edilemez; **buradaki hiçbir fonksiyon widget değil.**
Bu ayrım bilerek yapıldı: bu depo iki kez ölü bir arayüzün üstüne yeşil bir
takım gönderdi. Ekrana ne basılacağına karar veren her şey — diyalog süzgeci,
rozet derleyici, onay dağıtıcısı, risk→renk eşlemesi, zaman çizelgesi satırı —
saf fonksiyon olarak ayrıldı ve burada sınanıyor. Gradio tarafında yalnız
"hangi bileşen hangi fonksiyonu çağırıyor" kaldı.

Ağ yok: sahte süpervizör, sahte ağ geçidi, bellek içi depo.
"""

import pytest

from gozcu.agents.supervisor import (AUDIT_PREFIX, DEGRADED_REPLY,
                                     PENDING_GATE_NOTICE)
from gozcu.models import ActionRecord, DialogueTurn, Episode, EventBeat
from gozcu.run import LATE_NOTICE
from gozcu.ui import console
from gozcu.ui.feed import CARD_TITLE, FEED_EMPTY, REALTIME_FRAMING

# -- ikizler ------------------------------------------------------------------
#
# `tests/doubles.py`'den: bu dosyanın kendi kopyaları bir gün ayrışırdı ve
# `test_console.py` Görev 11'de silinirken paylaşılan ikizler ayakta
# kalıyor (Görev 3).
from tests.doubles import FakeSupervisor as _FakeSupervisor
from tests.doubles import StubGateway as _StubGateway
from tests.doubles import StubLoop as _StubLoop


def _episode(start_ts=192.0, risk="Yüksek", summary="İstif aracı devrildi."):
    return Episode(id=1, start_ts=start_ts, phase="onset", summary_tr=summary,
                   preliminary_risk=risk)


def _pending(tool_name="halt_production_line", action_id=7):
    return ActionRecord(id=action_id, ts=192.0, tool_name=tool_name,
                        params={"line_id": "B-Hattı"},
                        result={"state": "awaiting_approval"},
                        actor="agent", approval="pending")


# -- Kural 5: diyalog süzgeci -------------------------------------------------

def test_audit_rows_are_hidden_from_the_chat_pane():
    """`[denetim]` satırı denetim hükmünün kaydı, operatöre söylenmiş söz değil."""
    turns = [DialogueTurn(ts=1.0, role="system",
                          text=f"{AUDIT_PREFIX} uygunsuz hüküm, not eklendi"),
             DialogueTurn(ts=2.0, role="supervisor", text="Sağlık ekibi yolda.")]
    assert [t.text for t in console.visible_dialogue(turns)] == \
        ["Sağlık ekibi yolda."]


def test_the_degraded_reply_stays_on_screen():
    """`role != "system"` süzgeci bozulmuş modu ekrandan siler.

    Demo beat 6'da jürinin görmesi gereken TEK metin bu: ağ geçidi kesildi,
    sistem çökmedi, operatöre ne olduğunu söyledi.
    """
    turns = [DialogueTurn(ts=1.0, role="system", text=DEGRADED_REPLY)]
    assert console.visible_dialogue(turns) == turns


def test_the_catch_up_notice_stays_on_screen():
    """Telafi damgası da `role="system"` — süzülürse beat 6'nın ikinci yarısı
    (bağlantı geri geldi, açık kapatıldı) ekranda hiç görünmez."""
    turns = [DialogueTurn(ts=1.0, role="system", text=LATE_NOTICE)]
    assert console.visible_dialogue(turns) == turns


def test_the_pending_gate_notice_stays_on_screen():
    notice = PENDING_GATE_NOTICE.format(tool="halt_production_line", params="{}")
    turns = [DialogueTurn(ts=1.0, role="system", text=notice)]
    assert console.visible_dialogue(turns) == turns


def test_only_a_leading_audit_prefix_hides_a_row():
    """Operatörün cümlesinin İÇİNDE geçen bir damga satırı gizlemez."""
    turns = [DialogueTurn(ts=1.0, role="operator",
                          text=f"{AUDIT_PREFIX} nedir?"),
             DialogueTurn(ts=2.0, role="system",
                          text=f"Not: {AUDIT_PREFIX} kaydı tutuldu.")]
    assert console.visible_dialogue(turns) == turns



# -- Kural 7: onay çubuğu -----------------------------------------------------
#
# Rozet testleri `gozcu/ui/view.py::badges`'e göç etti (Görev 2) —
# `status_badges` mantığı değişmedi, `tests/test_view.py` şimdi sözlük
# çıktısına bakıyor.

def test_an_approved_halt_says_the_line_actually_stopped():
    """`state="approved"` onayın işlendiğini söyler, hattın durduğunu değil.

    Hattın gerçekten durduğu İÇ İÇE duran araç sonucunda yazıyor.
    """
    nobetci = _FakeSupervisor({"state": "approved", "action_id": 7,
                               "result": {"state": "halted",
                                          "line": "B-Hattı"}})
    text, pending = console.apply_approval(nobetci, 7, True)
    assert console.HALTED_NOTE in text
    assert pending is None
    assert nobetci.calls == [(7, True)]


def test_an_approved_action_that_did_not_halt_is_not_reported_as_halted():
    """Onay işlendi ama araç hattı durdurmadı — bu iki farklı şey."""
    nobetci = _FakeSupervisor({"state": "approved", "action_id": 7,
                               "result": {"state": "awaiting_approval"}})
    text, _ = console.apply_approval(nobetci, 7, True)
    assert console.HALTED_NOTE not in text
    assert console.NOT_HALTED_NOTE.split("{")[0] in text


def test_a_rejected_action_says_nothing_was_called():
    nobetci = _FakeSupervisor({"state": "rejected", "action_id": 7})
    text, _ = console.apply_approval(nobetci, 7, False)
    assert console.REJECTED_NOTE in text
    assert nobetci.calls == [(7, False)]


def test_an_unknown_action_is_reported_not_raised():
    nobetci = _FakeSupervisor({"state": "unknown_action",
                               "error": "aksiyon bulunamadı: 99"})
    text, _ = console.apply_approval(nobetci, 99, True)
    assert console.UNKNOWN_ACTION_NOTE in text


def test_an_already_decided_action_is_reported_not_raised():
    nobetci = _FakeSupervisor({"state": "not_pending", "approval": "approved"})
    text, _ = console.apply_approval(nobetci, 7, True)
    assert console.NOT_PENDING_NOTE.split("{")[0] in text
    assert "approved" in text


def test_an_unexpected_state_is_still_shown_to_the_operator():
    """Sözleşme büyürse çubuk sessiz kalmamalı."""
    nobetci = _FakeSupervisor({"state": "brand_new"})
    text, _ = console.apply_approval(nobetci, 7, True)
    assert "brand_new" in text


def test_the_bar_is_refreshed_from_the_supervisor_after_every_decision():
    """Karar sonrası çubuk yeniden okunmazsa bayat satırın üzerinde açık kalır."""
    still = _pending()
    nobetci = _FakeSupervisor({"state": "rejected", "action_id": 7},
                              pending_after=still)
    _, pending = console.apply_approval(nobetci, 7, False)
    assert nobetci.pending_reads == 1
    assert pending is still


# `approval_text`'in "isim var, boşsa kaybolur" kuralı `view.pending_payload`
# olarak göç etti (Görev 2) — `tests/test_view.py`.

# -- Kural 4: risk rengi ve zaman çizelgesi -----------------------------------

# check-tasks: runs=4  — parametrize listesi `console.GREEN` gibi modül
# sabitlerine bakıyor, denetçi onu literal olarak çözemiyor.
@pytest.mark.parametrize("level, color", [("Düşük", console.GREEN),
                                          ("Orta", console.YELLOW),
                                          ("Yüksek", console.ORANGE),
                                          ("Kritik", console.RED)])
def test_every_risk_level_has_its_own_colour(level, color):
    assert console.risk_color(level) == color


def test_the_four_risk_colours_are_distinct():
    """İkisi aynı renge düşerse zaman çizelgesi bir şey söylemiyor demektir."""
    colours = [console.risk_color(level) for level in console.RISK_COLORS]
    assert len(set(colours)) == 4


def test_an_unknown_risk_level_does_not_borrow_a_real_colour():
    """Şema büyürse çizelge sessizce yanlış renk basmamalı."""
    assert console.risk_color("Belirsiz") == console.UNKNOWN_COLOR
    assert console.UNKNOWN_COLOR not in \
        [console.risk_color(level) for level in console.RISK_COLORS]






# `payload_json`/`root_cause_markdown`/`handoff_rows` testleri
# `gozcu/ui/view.py::payload_dict`/`root_cause_payload`/`handoff_rows`'a göç
# etti (Görev 2) — `tests/test_view.py`.

# -- modül yüzeyi -------------------------------------------------------------

def test_the_console_module_imports_cleanly():
    assert callable(console.baslat)


# `test_ensure_server_running_explains_missing_mlx_vlm` `tests/test_server.py`'ye
# taşındı (Görev 3) — `_ensure_server_running` artık `gozcu/ui/server.py`'de
# yaşıyor; `console.py`'deki kopyası Görev 11'e kadar AYNEN duruyor.


# -- ekran bağlantısı ---------------------------------------------------------
#
# Widget'ın kendisi test edilemez, ama **ağacın kurulabilmesi** ve her
# işleyicinin ekran yuvası sayısı kadar değer döndürmesi edilebilir. Bu depoda
# yeşil bir takımın altında ölü bir arayüz iki kez gönderildi; `build()` hiç
# çağrılmadığı için Gradio'nun imza değişikliği testlere hiç yansımamıştı.
#
# `_StubLoop`/`_StubGateway` artık `tests/doubles.py`'den import ediliyor.


def _session(monkeypatch):
    """Ağa çıkmayan bir oturum: gerçek depo, sahte ağ geçidi, sahte Nöbetçi."""
    monkeypatch.setattr(console, "Gateway", lambda store: _StubGateway())
    monkeypatch.setattr(console, "Supervisor",
                        lambda gw, store: _FakeSupervisor(
                            {"state": "unknown_action"}))
    return console.Session()


def test_no_handler_refreshes_only_part_of_the_screen():
    """Ekrana dokunan her düğme TAMAMINI tazeliyor.

    Kısmi tazeleme sessiz ölü bölge üretiyor: bir düğme beslemeyi, bir
    başkası defteri güncellemeyi unutur ve jüri bayat veri görür.

    Kural "her işleyicinin 13 çıktısı var" DEĞİL — algı çizimi (Görev 20)
    ekranın dışında duruyor ve bilerek: o çıktı depodan türetilmiyor,
    istendiğinde üretiliyor. Doğru değişmez şu: **ekran bileşenlerine
    dokunan bir işleyici hepsine dokunmak zorunda**, hiçbiri bir alt kümeyi
    tazeleyemez.
    """
    demo = console.build()
    handlers = [fn for fn in demo.fns.values() if fn.outputs]
    full = [fn for fn in handlers if len(fn.outputs) == console.SCREEN_SLOTS]
    assert full, "hiç ekran işleyicisi bağlanmamış"

    screen = set()
    for fn in full:
        screen |= {id(component) for component in fn.outputs}

    for fn in handlers:
        touched = {id(component) for component in fn.outputs} & screen
        assert touched in (set(), screen), (
            "bir işleyici ekranın yalnız bir kısmını tazeliyor")


def test_the_perception_drawing_stays_outside_the_screen_slots():
    """Her kalp atışında yeniden kodlanmamalı: koşu başına bir kez yapılacak
    iş, saniyede bir yapılırdı."""
    import gradio as gr

    demo = console.build()
    drawing = [fn for fn in demo.fns.values()
               if any(isinstance(o, gr.Video) for o in fn.outputs)]
    assert drawing, "algı çizimi hiçbir düğmeye bağlı değil"
    assert all(len(fn.outputs) != console.SCREEN_SLOTS for fn in drawing)


def test_the_refresh_and_blank_screens_have_the_same_shape(monkeypatch):
    session = _session(monkeypatch)
    assert len(console._refresh(session, "x")) == console.SCREEN_SLOTS
    assert len(console._blank("x")) == console.SCREEN_SLOTS


def test_cutting_the_link_injects_a_vision_tier_outage(monkeypatch):
    """Demo beat 6'nın ilk yarısı: jürinin gözü önünde kesiyoruz."""
    session = _session(monkeypatch)
    state = console._cut_link(session)[-2]
    assert session.gw.injections == [{"vlm"}]
    assert state == console.STATE_CUT


def test_restoring_the_link_clears_the_outage_and_catches_up(monkeypatch):
    """İkisi birlikte olmak zorunda.

    Yalnız `inject_failure(set())` yapılsaydı atlanan pencereler kuyrukta
    kalırdı ve telafi ekranda hiç görünmezdi — beat 6'nın ikinci yarısı yok.
    """
    from gozcu.models import LoopEvent

    session = _session(monkeypatch)
    session.loop = _StubLoop([LoopEvent(episode=_episode(), late=True)])
    announced: list = []
    monkeypatch.setattr(console, "_announce",
                        lambda store, nobetci, event, on_message:
                        announced.append(event))

    state = console._restore_link(session)[-2]
    assert session.gw.injections == [set()]
    assert session.loop.calls == 1
    assert len(announced) == 1 and announced[0].late is True
    assert state == console.STATE_RESTORED.format(count=1)


def test_restoring_without_a_running_loop_says_so(monkeypatch):
    session = _session(monkeypatch)
    assert console._restore_link(session)[-2] == console.STATE_NO_LOOP
    assert session.gw.injections == [set()]


def test_resume_releases_the_paused_loop(monkeypatch):
    """"Devam et" bloğu çözüyor; video kaldığı yerden sürüyor."""
    session = _session(monkeypatch)
    session.resume.clear()
    state = console._resume(session)[-2]
    assert session.resume.is_set()
    assert state == console.STATE_RESUMED


def test_starting_without_a_video_says_so_instead_of_crashing():
    screen = next(console._analyse(None, None))
    assert screen[-2] == console.STATE_NO_VIDEO


def test_every_button_handler_survives_a_missing_session():
    """Analiz başlamadan basılan düğme yığın izi üretmemeli."""
    for handler in (console._resume, console._cut_link, console._restore_link):
        assert handler(None)[-2] == console.STATE_IDLE
    assert console._decide(None, True)[-2] == console.STATE_IDLE
    assert console._say("merhaba", None)[-2] == console.STATE_IDLE


def test_the_approval_bar_opens_only_while_an_action_is_pending(monkeypatch):
    """Görev 16'nın kabul kriteri: bekleyen aksiyonda çıkar, karardan sonra
    kaybolur. Sabit görünürlük ikisini de sessizce yalanlar."""
    # Yuvalar ADIYLA okunuyor: sayıyla indeksleyen bir iddia, araya bir
    # bileşen eklendiğinde sessizce başka bir yuvayı sınamaya başlar — bir
    # kez ısırdı ve 26 Ağustos'ta yuva sayısı 15'ten 13'e indi.
    box, text = console.SLOT["approval_box"], console.SLOT["approval_text"]
    session = _session(monkeypatch)
    assert console._refresh(session, "x")[box]["visible"] is False

    session.nobetci.pending_after = _pending()
    screen = console._refresh(session, "x")
    assert screen[box]["visible"] is True
    assert "halt_production_line" in screen[text]

    session.nobetci.pending_after = None
    assert console._refresh(session, "x")[box]["visible"] is False


def test_the_screen_streams_and_the_loop_really_pauses(monkeypatch, tmp_path):
    """Beat 0 ve 1 tek testte: video akıyor, kritik anda **duruyor**.

    Duraklama bir numara değil — `on_event` koşu iş parçacığında bloklarken
    videonun zaman çizelgesi gerçekten bekliyor. "Devam et" bloğu çözünce
    generator sona kadar akıyor ve teslim edilen yük ekrana düşüyor.

    25 Ağustos: bu davranış artık `Adım adım` anahtarına bağlı ve test onu
    AÇIK koşuyor. Garanti kaybolmadı, koşullu hâle geldi — varsayılan akış
    için `test_the_run_never_blocks_by_default`.
    """
    from tests.test_run import _FakeGateway as _RunGateway
    from tests.test_run import _fake_clip, _perception

    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)
    monkeypatch.setattr(console, "Gateway",
                        lambda store: _RunGateway(router=("escalate",)))

    screens = []
    for screen in console._analyse("video.mp4", None, step_mode=True):
        screens.append(screen)
        if screen[-2] == console.STATE_PAUSED:
            console._resume(screen[0])
        assert len(screens) < 60, "generator sonlanmadı"

    states = [screen[-2] for screen in screens]
    assert console.STATE_PAUSED in states, "kritik olayda hiç durulmadı"
    assert states[-1] == console.STATE_DONE

    final = screens[-1]
    # Yuvalar ADIYLA okunuyor: araya bir bileşen eklendiğinde sayıyla
    # indeksleyen bir iddia sessizce başka bir yuvayı sınamaya başlıyor.
    slot = console.SLOT
    session = final[slot["session"]]
    # Besleme yuvası `gr.skip()` (bir sözlük) OLABİLİR: dize değişmediyse
    # bileşen atlanıyor. `x not in {}` sessizce geçerdi, bu yüzden iddia son
    # çizilen dizeye kuruluyor — `Session.last_feed` onu tutuyor.
    drawn = session.last_feed
    assert drawn and FEED_EMPTY not in drawn, "besleme boş kaldı"
    assert "supervisor" in drawn, "süpervizörün konuştuğu beslemede yok"
    assert '"summary"' in final[slot["payload"]]        # dört anahtar teslim
    assert session.store.handoffs(), "devir defteri boş"


def test_the_decision_note_reaches_the_screen(monkeypatch):
    """Onay çubuğunun cevabı ekranın son yuvasına düşmeli."""
    session = _session(monkeypatch)
    session.nobetci.pending_after = _pending()
    session.nobetci.result = {"state": "rejected", "action_id": 7}
    assert console._decide(session, False)[-1] == console.REJECTED_NOTE


def test_deciding_with_nothing_pending_does_not_call_the_supervisor(monkeypatch):
    session = _session(monkeypatch)
    screen = console._decide(session, True)
    assert session.nobetci.calls == []
    assert screen[-1] == console.UNKNOWN_ACTION_NOTE





def _action(ts=30.0, tool="radio_call", params=None, result=None,
            actor="agent", approval="not_required"):
    return ActionRecord(ts=ts, tool_name=tool, params=params or {},
                        result=result or {}, actor=actor, approval=approval)


# `tool_rows`/`tool_summary` testleri `gozcu/ui/view.py`'ye göç etti
# (Görev 2) — `tests/test_view.py::TestToolRows`/`TestToolSummary`.


def test_screen_slot_names_match_the_slot_count():
    """`SLOT` ile `SCREEN_SLOTS` ayrışırsa bir bileşen sessizce tazelenmez."""
    assert len(console.SLOT) == console.SCREEN_SLOTS
    assert sorted(console.SLOT.values()) == list(range(console.SCREEN_SLOTS))


def test_refresh_returns_exactly_the_declared_slots():
    from gozcu.ui.console import Session
    session = Session()
    assert len(console._refresh(session, "x")) == console.SCREEN_SLOTS
    assert len(console._blank("x")) == console.SCREEN_SLOTS


# =============================================================================
# D1 — Müdahale kartı: duraklama yerine GÖSTERİM
# =============================================================================
#
# Bu çevrimdışı bir video (şartname §3: "bir video sisteme yüklenir").
# Operatörün gerçekten müdahale edeceği bir an yok; duraklamanın amacı
# müdahale ETMEK değil, "gerçek zamanlı bir kurulumda ajan tam burada şunu
# yapardı" demek. Bloklayan duraklama bunu göstermiyordu, sadece engelliyordu
# — ölçüldü: `konsol.bekle` 115 s açık kaldı, video 4. pencerede durdu.

from gozcu.models import Episode, EventBeat, ProposedAction, RiskAssessment


def _card_episode(episode_id=1, start=30.0, beats=(), risk="Yüksek"):
    return Episode(id=episode_id, start_ts=start, phase="onset",
                   summary_tr="Makine çıkışında personel, zemin ıslak.",
                   participants=["operatör", "forklift"],
                   preliminary_risk=risk,
                   beats=[EventBeat(ts=ts, text=text) for ts, text in beats])


def _card_risk(episode_id=1, level="Yüksek"):
    return RiskAssessment(episode_id=episode_id, level=level,
                          rationale_tr="Islak zemin + hareketli ekipman.",
                          preventable=True,
                          proposed_actions=[
                              ProposedAction(tool_name="radio_call",
                                             params={"unit": "vardiya"},
                                             description_tr="Vardiya uyarılsın")])


class TestInterventionCard:
    def test_card_is_stamped_with_the_event_moment_not_the_window_edge(self):
        """`start_ts` PENCERENİN sınırı, `event_ts` olayın anı.

        `models.Episode` docstring'i `start_ts`'in pencere sınırı olarak
        kalmak ZORUNDA olduğunu yazıyor. Kartta pencere sınırını göstermek
        olayı 10 saniyeye kadar yanlış yere koyardı — ve kartın başlığı
        "MÜDAHALE ANI" olduğu için doğru olması gereken tek sayı bu.
        """
        episode = _card_episode(start=30.0, beats=((37.0, "Kayma"),))
        card = console.intervention_card(episode, _card_risk(), [], "")
        assert "00:37" in card
        assert "00:30" not in card

    def test_card_falls_back_to_start_when_there_are_no_beats(self):
        card = console.intervention_card(_card_episode(start=30.0), _card_risk(), [], "")
        assert "00:30" in card

    def test_card_states_the_realtime_framing(self):
        """Kartın bütün varlık sebebi bu cümle."""
        card = console.intervention_card(_card_episode(), _card_risk(), [], "")
        assert console.REALTIME_FRAMING in card

    def test_card_shows_what_was_seen(self):
        card = console.intervention_card(_card_episode(), _card_risk(), [], "")
        assert "zemin ıslak" in card.lower()

    def test_card_shows_what_the_agent_said(self):
        card = console.intervention_card(_card_episode(), _card_risk(), [],
                                         "Operatör, dikkat.")
        assert "Operatör, dikkat." in card

    def test_card_separates_automatic_calls_from_gated_ones(self):
        """Onay kapısı yalnız `halt_production_line`'da (registry).

        Altı aracı 'onay bekliyor' diye çizmek tasarımı yanlış anlatır.
        """
        actions = [_action(tool="radio_call", approval="not_required"),
                   _action(tool="halt_production_line", approval="pending")]
        card = console.intervention_card(_card_episode(), _card_risk(), actions, "")
        automatic = card.index("radio_call")
        gated = card.index("halt_production_line")
        assert card.index(console.CARD_CALLED) < automatic
        assert card.index(console.CARD_GATED) < gated

    def test_card_omits_the_gated_row_when_nothing_is_gated(self):
        card = console.intervention_card(
            _card_episode(), _card_risk(), [_action(approval="not_required")], "")
        assert console.CARD_GATED not in card

    def test_card_shows_the_risk_rationale(self):
        card = console.intervention_card(_card_episode(), _card_risk(), [], "")
        assert "hareketli ekipman" in card.lower()

    def test_card_survives_a_missing_risk_assessment(self):
        """Risk biçilmeden kapanan bir epizot kartı düşürmemeli."""
        card = console.intervention_card(_card_episode(), None, [], "")
        assert console.REALTIME_FRAMING in card
        assert "00:30" in card

    def test_card_escapes_model_text(self):
        episode = _card_episode()
        episode.summary_tr = "<script>alert(1)</script>"
        card = console.intervention_card(episode, _card_risk(), [], "")
        assert "<script>" not in card

    def test_empty_rows_are_a_dash_not_blank(self):
        card = console.intervention_card(_card_episode(), _card_risk(), [], "")
        assert "—" in card


class TestStepMode:
    def test_step_mode_is_off_by_default(self):
        """Varsayılan akış: 4 dakikalık sunumda düğmeye basılmıyor."""
        assert console.STEP_MODE_DEFAULT is False

    def test_no_blocking_when_step_mode_is_off(self):
        from gozcu.ui.console import Session
        session = Session()
        session.step_mode = False
        # Kapalıyken çağrı hemen dönmeli; dönmezse bu test DONAR ve donması
        # da doğru sonuçtur — 25 Ağustos'ta canlı koşuda olan tam buydu.
        console._wait_if_step_mode(session)

    def test_step_mode_blocks_until_resume(self):
        """Açıkken gerçekten bekliyor — eski davranış birebir korunuyor.

        `resume` önceden set EDİLEMEZ: `_wait_if_step_mode` beklemeden önce
        temizliyor, çünkü her olayın kendi beklemesi olmalı. Serbest bırakma
        bu yüzden başka bir iş parçacığından geliyor.
        """
        import threading
        import time

        from gozcu.ui.console import Session
        session = Session()
        session.step_mode = True
        released = []

        def _release():
            time.sleep(0.05)
            released.append(True)
            session.resume.set()

        threading.Thread(target=_release, daemon=True).start()
        console._wait_if_step_mode(session)
        assert released == [True], "beklemeden döndü"


def test_the_run_never_blocks_by_default(monkeypatch, tmp_path):
    """Varsayılan akış: 115 s'lik bir kayıt HİÇBİR düğmeye basılmadan biter.

    Şartname §11 sunumu 4 dakikayla sınırlıyor ve bu çevrimdışı bir kayıt
    (§3) — bekleyen bir arayüz o bütçeyi yiyor. Ölçülen arıza buydu:
    `konsol.bekle` 115 saniye açık kaldı ve video 4. pencerede durdu.
    """
    from tests.test_run import _FakeGateway as _RunGateway
    from tests.test_run import _fake_clip, _perception

    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)
    monkeypatch.setattr(console, "Gateway",
                        lambda store: _RunGateway(router=("escalate",)))

    screens = []
    for screen in console._analyse("video.mp4", None):   # step_mode varsayılan
        screens.append(screen)
        assert len(screens) < 60, "generator sonlanmadı"
        # HİÇBİR yerde `_resume` çağrılmıyor — çağrılması gerekseydi bu
        # döngü sonsuza kadar dönerdi.

    states = [screen[console.SLOT["state"]] for screen in screens]
    assert states[-1] == console.STATE_DONE
    assert console.STATE_PAUSED not in states, "varsayılanda durdu"



# `kpi_markdown`/`perception_markdown` testleri `gozcu/ui/view.py`'ye göç etti
# (Görev 2) — `tests/test_view.py::TestKpiPanel`.


# =============================================================================
# D5 — Zorlu koşullar tek tuşla
# =============================================================================
#
# Şartname §6 demo videosunda "zorlu koşulları (örn: bağlam değişimi denemesi)
# nasıl yönettiği" istiyor. 4 dakikalık sunumda (§11) bunları elle yazmak
# zaman kaybı; hazır metinler tek tıkla gidiyor.

class TestStressPrompts:
    def test_every_prompt_has_text_and_a_label(self):
        for key, (label, text) in console.STRESS_PROMPTS.items():
            assert label.strip(), key
            assert text.strip(), key

    def test_context_change_prompt_is_off_topic(self):
        """Bağlam değişimi denemesi, olayla İLGİSİZ olmalı — yoksa ajanın
        konuyu koruduğunu göstermez."""
        _, text = console.STRESS_PROMPTS["baglam"]
        assert "hava" in text.lower() or "yemek" in text.lower()

    def test_false_information_prompt_contradicts_the_observation(self):
        _, text = console.STRESS_PROMPTS["yanlis_bilgi"]
        assert "kimse yok" in text.lower()

    def test_pressing_a_button_without_a_session_does_not_crash(self):
        screen = console._stress(None, "baglam")
        assert len(screen) == console.SCREEN_SLOTS

    def test_an_unknown_key_is_refused_not_sent(self):
        """Bilinmeyen anahtar sessizce boş mesaj göndermemeli."""
        from gozcu.ui.console import Session
        session = Session()
        sent = []
        session.nobetci.talk = lambda text: sent.append(text)
        console._stress(session, "böyle-bir-şey-yok")
        assert sent == []

    def test_pressing_a_button_sends_the_canned_text(self):
        from gozcu.ui.console import Session
        session = Session()
        sent = []
        session.nobetci.talk = lambda text: sent.append(text)
        console._stress(session, "baglam")
        assert sent == [console.STRESS_PROMPTS["baglam"][1]]


def test_perception_kpis_are_visible_before_any_run():
    """Algı ölçümü koşudan BAĞIMSIZ — elle etiketli bir kayıtta ölçüldü.

    Jüri "Ölçüm" sekmesine analiz başlatmadan bakarsa boş bir panel değil,
    ölçülmüş sayıları görmeli; §4 metriklerin demoda sunulmasını istiyor.
    """
    blank = console._blank(console.STATE_IDLE)
    assert console.KPI_PERCEPTION in blank[console.SLOT["kpi"]]


# `console._pct` Türkçe ondalık virgül testi `gozcu/ui/view.py::pct`'e göç
# etti (Görev 2) — `tests/test_view.py::test_kpi_numbers_use_turkish_decimal_commas`.


class TestResumeButtonVisibility:
    """Anahtar kapalıyken 'Devam et' HİÇBİR ŞEY yapmıyor — görünmemeli."""

    def test_hidden_when_step_mode_is_off(self):
        update = console._set_step_mode(False, None)
        assert update["visible"] is False

    def test_shown_when_step_mode_is_on(self):
        update = console._set_step_mode(True, None)
        assert update["visible"] is True

    def test_turning_it_off_releases_a_waiting_loop(self):
        """Kapatmak bekleyen döngüyü serbest bırakmalı, yoksa anahtarı
        kapatmak koşuyu kilitli bırakırdı."""
        from gozcu.ui.console import Session
        session = Session()
        session.step_mode = True
        session.resume.clear()
        console._set_step_mode(False, session)
        assert session.resume.is_set()




# --- iki sekme (Görev 19) ----------------------------------------------------

def test_the_console_has_exactly_two_tabs():
    """Beş sekme sistemin işini KAYNAĞINA göre bölüyordu — devirler bir
    sekmede, araç çağrıları başkasında, konuşma üçüncüde, hepsi aynı on
    saniyede. Yeni eksen ZAMAN: olan biten ve teslim edilen."""
    import gradio as gr

    demo = console.build()
    tabs = [block.label for block in demo.blocks.values()
            if isinstance(block, gr.Tab)]
    assert tabs == ["CANLI", "RAPOR"]


def test_every_slot_has_a_name_and_the_count_matches():
    assert len(console.SLOT) == console.SCREEN_SLOTS == 13
    assert sorted(console.SLOT.values()) == list(range(console.SCREEN_SLOTS))
    assert "feed" in console.SLOT
    assert "timeline" not in console.SLOT
    assert "chat" not in console.SLOT
    assert "interventions" not in console.SLOT


def test_the_blank_screen_fills_every_slot():
    """Eksik bir çıktı Gradio'da hata vermiyor — o bileşen sessizce
    tazelenmiyor ve jüri bayat veri görür."""
    assert len(console._blank("hazır")) == console.SCREEN_SLOTS


def test_the_refresh_fills_every_slot_and_draws_the_feed(monkeypatch):
    session = _session(monkeypatch)
    session.store.save_dialogue(DialogueTurn(ts=1.0, role="supervisor",
                                             text="dikkat edin"))
    drawn = console._refresh(session, "koşuyor")
    assert len(drawn) == console.SCREEN_SLOTS
    assert "dikkat edin" in drawn[console.SLOT["feed"]]


def test_the_feed_slot_is_skipped_when_nothing_changed(monkeypatch):
    """`column-reverse` kaydırıcı her çizimde sıfırdan doğuyor ve en alta
    dönüyor. Dize değişmediği hâlde bileşeni güncellemek, jürinin geçmişi
    okumak için yaptığı her kaydırmayı saniyede bir bozardı."""
    import gradio as gr

    session = _session(monkeypatch)
    session.store.save_dialogue(DialogueTurn(ts=1.0, role="supervisor",
                                             text="bir"))
    first = console._refresh(session, "x")[console.SLOT["feed"]]
    assert isinstance(first, str) and "bir" in first

    again = console._refresh(session, "x")[console.SLOT["feed"]]
    assert again == gr.skip(), "değişmeyen besleme yeniden çizilmemeli"

    session.store.save_dialogue(DialogueTurn(ts=2.0, role="supervisor",
                                             text="iki"))
    third = console._refresh(session, "x")[console.SLOT["feed"]]
    assert isinstance(third, str) and "iki" in third


def test_the_feed_skips_episodes_that_were_in_the_store_before_the_run():
    """`load_history` arşiv fikstürlerini epizot olarak yazıyor; beslemede
    "sentezleyici olay açtı" diye görünürlerse bu videoda olmamış bir şey
    iddia edilir."""
    session = console.Session()
    assert session.archived == set()

    session.store.create_episode(Episode(start_ts=0.0, phase="outcome",
                                         summary_tr="geçen ayki kaza",
                                         preliminary_risk="Yüksek",
                                         state="closed"))
    later = console.Session()
    later.store = session.store
    later.archived = {e.id for e in session.store.episodes()}
    drawn = console._refresh(later, "x")[console.SLOT["feed"]]
    assert "geçen ayki kaza" not in drawn


def test_the_audit_rule_has_exactly_one_home():
    """`visible_dialogue` `feed.py`'ye taşındı ve buradan yeniden dışa
    veriliyor. İki kopya bir gün ayrışır ve bir ekran denetim hükmünü
    operatöre söylenmiş bir söz gibi gösterir."""
    from gozcu.ui import feed

    assert console.visible_dialogue is feed.visible_dialogue
    assert console.intervention_card is feed.intervention_card
    assert console.risk_color is feed.risk_color


def test_the_streaming_generator_survives_a_skipped_feed_slot(monkeypatch,
                                                              tmp_path):
    """`gr.skip()` bir demetin İÇİNDE akıyor. Generator yolu onu kaldıramazsa
    demo tam ortasında düşer — ve kalp atışlarının çoğu değişmemiş bir
    besleme üretiyor, yani bu yol istisna değil kural."""
    import gradio as gr

    from tests.test_run import _FakeGateway as _RunGateway
    from tests.test_run import _fake_clip, _perception

    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)
    monkeypatch.setattr(console, "Gateway",
                        lambda store: _RunGateway(router=("escalate",)))

    feed = console.SLOT["feed"]
    screens = list(console._analyse("video.mp4", None, step_mode=False))

    assert screens, "generator hiç ekran üretmedi"
    assert screens[-1][-2] == console.STATE_DONE
    drawn = [s[feed] for s in screens]
    assert any(isinstance(d, str) and FEED_EMPTY not in d for d in drawn), (
        "besleme hiç çizilmedi")
    assert any(d == gr.skip() for d in drawn), (
        "değişmeyen besleme atlanmadı — jürinin kaydırması her saniye bozulur")
    # `LoopEvent → Session.escalated_ids() → kart` zinciri UÇTAN UCA:
    # `escalated_ids` bozulursa besleme yine dolu görünür ve hiçbir birim
    # testi kırmızıya dönmez.
    session = screens[-1][console.SLOT["session"]]
    assert session.escalated_ids(), "yükseltme hiç kaydedilmedi"
    assert CARD_TITLE in session.last_feed, "müdahale kartı ekrana ulaşmadı"
    assert REALTIME_FRAMING in session.last_feed
    # Atlanan yuva HİÇBİR zaman diğer yuvaları bozmamalı.
    assert all(len(s) == console.SCREEN_SLOTS for s in screens)


def test_the_drawing_button_says_what_is_missing_instead_of_failing(monkeypatch):
    """Koşu yokken sessizce boş bir oynatıcı bırakmak, "algı hiçbir şey
    görmedi" ile "çizilecek koşu yok"u aynı şeye çevirirdi."""
    video, note = console._annotate(None)
    assert video is None and note == console.ANNOTATE_NO_RUN

    session = _session(monkeypatch)
    assert session.frames_dir is None
    video, note = console._annotate(session)
    assert video is None and note == console.ANNOTATE_NO_RUN


def test_a_drawing_failure_reaches_the_screen_instead_of_killing_the_run(
        monkeypatch, tmp_path):
    """Bir tanı aracı ölçtüğü şeyi öldürmemeli — `trace.py` ile aynı
    sözleşme."""
    session = _session(monkeypatch)
    session.frames_dir = tmp_path

    def _boom(*args, **kwargs):
        raise console.AnnotateError("kare yok")

    monkeypatch.setattr(console, "annotate_run", _boom)
    video, note = console._annotate(session)
    assert video is None
    assert "kare yok" in note


def test_a_successful_drawing_returns_a_path_the_player_can_use(monkeypatch,
                                                               tmp_path):
    session = _session(monkeypatch)
    session.frames_dir = tmp_path
    drawn = tmp_path / "algi-cizimi.mp4"
    drawn.write_bytes(b"x")
    monkeypatch.setattr(console, "annotate_run",
                        lambda *a, **k: drawn)
    video, note = console._annotate(session)
    assert video == str(drawn)
    assert note == console.ANNOTATE_DONE
