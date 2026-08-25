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
from gozcu.models import (ActionRecord, Detail, DialogueTurn, Episode,
                          EventBeat, EventSummary, Handoff, PipelineOutput)
from gozcu.run import LATE_NOTICE
from gozcu.store import Store
from gozcu.ui import console


# -- ikizler ------------------------------------------------------------------

class _FakeGateway:
    """Yalnız `is_degraded` taşıyan ağ geçidi ikizi.

    `tier` **kaydediliyor**: durum rozetinin doğru çağrısı çıplak
    `is_degraded()` ve tek bir kademe sorulursa rozet yanlış cevap verir.
    """

    def __init__(self, broken_any=False, broken_vlm=False):
        self.broken_any, self.broken_vlm = broken_any, broken_vlm
        self.asked: list = []

    def is_degraded(self, tier=None) -> bool:
        self.asked.append(tier)
        return self.broken_any if tier is None else self.broken_vlm


class _FakeSupervisor:
    """`approve()`'un dört durumunu senaryolayan Nöbetçi ikizi."""

    def __init__(self, result, pending_after=None):
        self.result = result
        self.pending_after = pending_after
        self.calls: list = []
        self.pending_reads = 0

    def approve(self, action_id, approved):
        self.calls.append((action_id, approved))
        return self.result

    def pending_approval(self):
        self.pending_reads += 1
        return self.pending_after


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


def test_a_proactive_alert_is_marked_apart_from_a_reply():
    """Operatör hangi mesajın kendiliğinden geldiğini görmeli.

    Ayrım türetiliyor: kendinden önce operatör satırı olmayan bir süpervizör
    satırı kimse sormadan söylenmiştir (`escalate`), sonrakiler cevaptır.
    """
    turns = [DialogueTurn(ts=1.0, role="supervisor", text="Kritik olay var."),
             DialogueTurn(ts=2.0, role="operator", text="Ne oldu?"),
             DialogueTurn(ts=3.0, role="supervisor", text="İstif aracı devrildi.")]
    messages = console.chat_messages(turns)
    assert [m["role"] for m in messages] == ["assistant", "user", "assistant"]
    assert messages[0]["content"].startswith(console.PROACTIVE_MARK)
    assert not messages[2]["content"].startswith(console.PROACTIVE_MARK)
    assert "İstif aracı devrildi." in messages[2]["content"]


def test_chat_messages_marks_system_rows_and_drops_audit_rows():
    turns = [DialogueTurn(ts=1.0, role="system", text=DEGRADED_REPLY),
             DialogueTurn(ts=2.0, role="system", text=f"{AUDIT_PREFIX} not")]
    messages = console.chat_messages(turns)
    assert len(messages) == 1
    assert messages[0]["role"] == "assistant"
    assert messages[0]["content"].startswith(console.SYSTEM_MARK)
    assert DEGRADED_REPLY in messages[0]["content"]


# -- Kural 6: rozetler --------------------------------------------------------

def test_the_status_badge_asks_the_bare_degradation_flag(monkeypatch):
    """Rozet "herhangi bir kademe bozuk mu" demek — kademe adı geçilmemeli."""
    monkeypatch.setattr(console, "memory_backend", lambda: "qdrant")
    monkeypatch.setattr(console, "run_status", lambda store: "measured")
    gw = _FakeGateway(broken_any=True, broken_vlm=False)
    text = console.status_badges(gw, Store(":memory:"))
    assert gw.asked == [None]
    assert console.DEGRADED_BADGE in text
    assert console.HEALTHY_BADGE not in text


def test_a_healthy_run_shows_all_three_badges(monkeypatch):
    monkeypatch.setattr(console, "memory_backend", lambda: "local")
    monkeypatch.setattr(console, "run_status", lambda store: "unmeasured")
    text = console.status_badges(_FakeGateway(), Store(":memory:"))
    assert console.HEALTHY_BADGE in text
    assert "local" in text
    assert "unmeasured" in text


def test_the_memory_badge_reports_the_real_backend(monkeypatch):
    """Sessiz düşüşün kendisi kabul edilebilir, görünmezliği değil."""
    monkeypatch.setattr(console, "run_status", lambda store: "measured")
    monkeypatch.setattr(console, "memory_backend", lambda: "qdrant")
    assert "qdrant" in console.status_badges(_FakeGateway(), Store(":memory:"))
    monkeypatch.setattr(console, "memory_backend", lambda: "local")
    assert "local" in console.status_badges(_FakeGateway(), Store(":memory:"))


def test_the_run_status_badge_comes_from_the_kpi_module():
    """Boş depo ölçülemez bir koşudur; rozet bunu söylemeli."""
    assert "unmeasured" in console.status_badges(_FakeGateway(), Store(":memory:"))


# -- Kural 7: onay çubuğu -----------------------------------------------------

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


def test_the_approval_text_names_the_tool_and_disappears_when_empty():
    assert console.approval_text(None) == ""
    text = console.approval_text(_pending())
    assert "halt_production_line" in text
    assert "B-Hattı" in text


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


def test_a_timeline_row_carries_the_video_stamp_summary_risk_and_colour():
    rows = console.timeline_rows([_episode(start_ts=192.0)])
    assert rows == [("03:12", "İstif aracı devrildi.", "Yüksek",
                     console.ORANGE)]


def test_the_timeline_renders_every_episode_with_its_colour():
    html = console.timeline_html([_episode(start_ts=0.0, risk="Düşük"),
                                  _episode(start_ts=192.0, risk="Kritik")])
    assert "00:00" in html and "03:12" in html
    assert console.GREEN in html and console.RED in html
    assert "Düşük" in html and "Kritik" in html


def test_an_empty_timeline_says_so_in_turkish():
    assert console.TIMELINE_EMPTY in console.timeline_html([])


def test_the_timeline_escapes_model_written_summaries():
    """Özet metni modelden geliyor; ham HTML olarak basılamaz."""
    html = console.timeline_html([_episode(summary="<b>devrildi</b>")])
    assert "<b>devrildi</b>" not in html
    assert "&lt;b&gt;" in html


# -- teslim edilen yük --------------------------------------------------------

def _output(root_cause=None, detail=True):
    return PipelineOutput(
        summary="B-Hattında istif aracı devrildi.", risk="Kritik",
        events=[EventSummary(time="03:12", event="devrildi")],
        actions=["Sağlık ekibini çağır"],
        detail=Detail(root_cause_report=root_cause) if detail else None)


def test_the_four_keys_are_rendered_as_json():
    text = console.payload_json(_output())
    assert '"summary"' in text and '"events"' in text
    assert '"risk"' in text and '"actions"' in text


def test_no_run_yet_is_said_in_turkish_not_shown_as_empty_json():
    assert console.payload_json(None) == console.NO_RUN_YET
    assert console.NO_RUN_YET in console.root_cause_markdown(None)


def test_a_crashed_run_does_not_fabricate_an_empty_root_cause_report():
    """`detail=None` "o katmanlar hiç koşmadı" demek; boş bir rapor basmak
    yaşanmamış bir analizi iddia etmek olurdu.

    Ayrıca çöken koşu ile raporsuz koşu aynı cümleyi paylaşamaz: biri
    genişletilmiş yolun çöküşü, diğeri kayda değer olay olmaması.
    """
    text = console.root_cause_markdown(_output(detail=False))
    assert console.CRASHED_RUN in text
    assert console.NO_ROOT_CAUSE not in text
    assert "Muhtemel kök neden" not in text


def test_a_run_without_a_report_says_so_rather_than_printing_blanks():
    text = console.root_cause_markdown(_output(root_cause=None))
    assert console.NO_ROOT_CAUSE in text
    assert console.CRASHED_RUN not in text
    assert "Muhtemel kök neden" not in text


def test_a_real_report_renders_all_five_sections():
    report = {"what_happened": "B-Hattında istif aracı devrildi.",
              "probable_root_cause": "Olası fren arızası.",
              "actions_taken": ["Sağlık ekibi çağrıldı."],
              "prevention_recommendations": ["Fren bakımı öne alınmalı."],
              "confidence_limits": "Kamera sesi duymuyor."}
    text = console.root_cause_markdown(_output(root_cause=report))
    for value in ("B-Hattında istif aracı devrildi.", "Olası fren arızası.",
                  "Sağlık ekibi çağrıldı.", "Fren bakımı öne alınmalı.",
                  "Kamera sesi duymuyor."):
        assert value in text
    assert console.CRASHED_RUN not in text


def test_the_handoff_ledger_stamps_video_time():
    rows = console.handoff_rows([Handoff(ts=192.0, source_agent="router",
                                         target_agent="supervisor",
                                         reason="hız eşiği aşıldı",
                                         confidence=0.9,
                                         payload_ref="window@192.0")])
    assert rows == [["03:12", "router", "supervisor", "hız eşiği aşıldı", "0.90"]]


# -- modül yüzeyi -------------------------------------------------------------

def test_the_console_module_imports_cleanly():
    assert callable(console.baslat)


def test_ensure_server_running_explains_missing_mlx_vlm():
    """mlx-vlm kurulu değilken alt süreç açmadan okunur bir hata verilmeli."""
    from unittest.mock import MagicMock, patch

    client = MagicMock()
    client.models.list.side_effect = Exception("unreachable")

    with (patch.object(console, "OpenAI", return_value=client),
          patch("importlib.util.find_spec", return_value=None),
          patch.object(console.subprocess, "Popen") as popen,
          patch.object(console.time, "sleep")):
        with pytest.raises(RuntimeError, match="mlx-vlm"):
            console._ensure_server_running()
        popen.assert_not_called()


# -- ekran bağlantısı ---------------------------------------------------------
#
# Widget'ın kendisi test edilemez, ama **ağacın kurulabilmesi** ve her
# işleyicinin ekran yuvası sayısı kadar değer döndürmesi edilebilir. Bu depoda
# yeşil bir takımın altında ölü bir arayüz iki kez gönderildi; `build()` hiç
# çağrılmadığı için Gradio'nun imza değişikliği testlere hiç yansımamıştı.

class _StubLoop:
    def __init__(self, events=()):
        self.events = list(events)
        self.calls = 0

    def catch_up(self):
        self.calls += 1
        yield from self.events


class _StubGateway(_FakeGateway):
    def __init__(self):
        super().__init__()
        self.injections: list = []

    def inject_failure(self, tiers):
        self.injections.append(set(tiers))
        self.broken_any = bool(tiers)


def _session(monkeypatch):
    """Ağa çıkmayan bir oturum: gerçek depo, sahte ağ geçidi, sahte Nöbetçi."""
    monkeypatch.setattr(console, "Gateway", lambda store: _StubGateway())
    monkeypatch.setattr(console, "Supervisor",
                        lambda gw, store: _FakeSupervisor(
                            {"state": "unknown_action"}))
    return console.Session()


def test_the_console_tree_builds_and_every_handler_fills_the_whole_screen():
    """Her düğme ekranın TAMAMINI tazeliyor; eksik çıktı sessiz ölü bölge olur."""
    demo = console.build()
    handlers = [fn for fn in demo.fns.values() if len(fn.outputs) > 1]
    assert handlers, "hiç işleyici bağlanmamış"
    assert {len(fn.outputs) for fn in handlers} == {console.SCREEN_SLOTS}


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
    session = _session(monkeypatch)
    assert console._refresh(session, "x")[4]["visible"] is False

    session.nobetci.pending_after = _pending()
    screen = console._refresh(session, "x")
    assert screen[4]["visible"] is True
    assert "halt_production_line" in screen[5]

    session.nobetci.pending_after = None
    assert console._refresh(session, "x")[4]["visible"] is False


def test_the_screen_streams_and_the_loop_really_pauses(monkeypatch, tmp_path):
    """Beat 0 ve 1 tek testte: video akıyor, kritik anda **duruyor**.

    Duraklama bir numara değil — `on_event` koşu iş parçacığında bloklarken
    videonun zaman çizelgesi gerçekten bekliyor. "Devam et" bloğu çözünce
    generator sona kadar akıyor ve teslim edilen yük ekrana düşüyor.
    """
    from tests.test_run import _FakeGateway as _RunGateway
    from tests.test_run import _fake_clip, _perception

    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)
    monkeypatch.setattr(console, "Gateway",
                        lambda store: _RunGateway(router=("escalate",)))

    screens = []
    for screen in console._analyse("video.mp4", None):
        screens.append(screen)
        if screen[-2] == console.STATE_PAUSED:
            console._resume(screen[0])
        assert len(screens) < 60, "generator sonlanmadı"

    states = [screen[-2] for screen in screens]
    assert console.STATE_PAUSED in states, "kritik olayda hiç durulmadı"
    assert states[-1] == console.STATE_DONE

    final = screens[-1]
    assert console.TIMELINE_EMPTY not in final[2]      # çizelge doldu
    assert final[3], "sohbet paneli boş kaldı"
    assert '"summary"' in final[7]                     # dört anahtar teslim
    assert final[0].store.handoffs(), "devir defteri boş"


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


def test_the_timeline_shows_one_row_per_beat():
    """Epizot artık kendi içinde bir zaman çizelgesi taşıyor; konsol o
    çizelgeyi tek satıra düşürürse operatör olayın seyrini göremez."""
    episode = _episode(start_ts=10.0)
    episode.beats = [EventBeat(ts=13.0, text="raf çöküyor"),
                     EventBeat(ts=14.0, text="toz yayılıyor")]
    rows = console.timeline_rows([episode])
    assert [(stamp, text) for stamp, text, _risk, _color in rows] == [
        ("00:13", "raf çöküyor"), ("00:14", "toz yayılıyor")]
    assert {risk for _s, _t, risk, _c in rows} == {"Yüksek"}


def test_the_timeline_renders_beat_rows():
    episode = _episode(start_ts=10.0, risk="Kritik")
    episode.beats = [EventBeat(ts=13.0, text="raf çöküyor")]
    html_out = console.timeline_html([episode])
    assert "00:13" in html_out and "raf çöküyor" in html_out


def test_the_timeline_escapes_model_written_beat_text():
    episode = _episode()
    episode.beats = [EventBeat(ts=1.0, text="<b>çöktü</b>")]
    html_out = console.timeline_html([episode])
    assert "<b>çöktü</b>" not in html_out and "&lt;b&gt;" in html_out
