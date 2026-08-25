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
    assert console.TIMELINE_EMPTY not in final[slot["timeline"]]
    assert final[slot["chat"]], "sohbet paneli boş kaldı"
    assert '"summary"' in final[slot["payload"]]        # dört anahtar teslim
    assert final[slot["session"]].store.handoffs(), "devir defteri boş"


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


# =============================================================================
# D2 — Araç şeridi: çağrılan mock fonksiyonlar EKRANDA
# =============================================================================
#
# Şartname §7 bunu açıkça puanlıyor ("Mock fonksiyonların ajanın araçları
# olarak başarıyla kullanılması", %35 kriterin maddesi). 25 Ağustos'a kadar
# yedi saha aracının çağrıları `store.actions()`'ta duruyordu ve arayüzde
# HİÇBİR yerde görünmüyordu — yalnız kapanış JSON'unun içinde metin olarak.

from gozcu.models import ActionRecord


def _action(ts=30.0, tool="radio_call", params=None, result=None,
            actor="agent", approval="not_required"):
    return ActionRecord(ts=ts, tool_name=tool, params=params or {},
                        result=result or {}, actor=actor, approval=approval)


class TestToolRows:
    def test_empty_ledger_says_so(self):
        assert console.tool_rows([]) == []

    def test_timestamp_is_video_time(self):
        row = console.tool_rows([_action(ts=90.0)])[0]
        assert row[0] == "01:30"

    def test_tool_name_is_shown_verbatim(self):
        """Araç adı jürinin aradığı şey; süslenmiyor."""
        row = console.tool_rows([_action(tool="dispatch_medical")])[0]
        assert row[1] == "dispatch_medical"

    def test_params_are_rendered_readably(self):
        row = console.tool_rows([_action(params={"unit": "vardiya",
                                                 "message": "acil"})])[0]
        assert "unit=vardiya" in row[2] and "message=acil" in row[2]

    def test_empty_params_are_a_dash_not_blank(self):
        assert console.tool_rows([_action(params={})])[0][2] == "—"

    def test_result_is_rendered(self):
        row = console.tool_rows([_action(result={"ref": "ISG-0007"})])[0]
        assert "ISG-0007" in row[3]

    def test_approval_states_are_turkish_and_distinct(self):
        states = [console.tool_rows([_action(approval=a)])[0][4]
                  for a in ("not_required", "pending", "approved", "rejected")]
        assert len(set(states)) == 4
        assert all(s for s in states)

    def test_operator_actor_is_distinguishable_from_agent(self):
        """Operatörün tetiklediği çağrı, ajanın kendi kararıyla aynı
        görünmemeli — %20'lik otonomi kriteri tam olarak bu farkı soruyor."""
        agent = console.tool_rows([_action(actor="agent")])[0]
        operator = console.tool_rows([_action(actor="operator")])[0]
        assert agent[5] != operator[5]

    def test_rows_are_sorted_by_time(self):
        rows = console.tool_rows([_action(ts=90.0), _action(ts=30.0)])
        assert [r[0] for r in rows] == ["00:30", "01:30"]

    def test_row_width_matches_headers(self):
        assert len(console.tool_rows([_action()])[0]) == len(console.TOOL_HEADERS)


class TestToolSummary:
    def test_no_calls_is_not_an_empty_string(self):
        """Boş bir sayaç 'araçlar çalışmıyor' gibi okunur."""
        assert console.NO_TOOLS_YET in console.tool_summary([])

    def test_counts_distinct_tools_against_the_catalogue(self):
        text = console.tool_summary([_action(tool="radio_call"),
                                     _action(tool="radio_call"),
                                     _action(tool="site_alarm")])
        assert "7 araçtan 2" in text

    def test_counts_total_calls(self):
        text = console.tool_summary([_action(), _action(), _action()])
        assert "3 çağrı" in text

    def test_counts_approval_gated_calls(self):
        text = console.tool_summary([
            _action(tool="halt_production_line", approval="approved"),
            _action(tool="radio_call")])
        assert "1 onay" in text

    def test_catalogue_size_comes_from_the_registry(self):
        """Sayı elle yazılırsa yeni bir araç eklendiğinde sessizce yalan olur."""
        from gozcu.tools.registry import TOOLS
        assert str(len(TOOLS)) in console.tool_summary([_action()])


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


def test_intervention_cards_reach_the_screen(monkeypatch, tmp_path):
    """Duraklama kalktı ama müdahale anı KAYBOLMADI — kart olarak duruyor."""
    from tests.test_run import _FakeGateway as _RunGateway
    from tests.test_run import _fake_clip, _perception

    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)
    monkeypatch.setattr(console, "Gateway",
                        lambda store: _RunGateway(router=("escalate",)))

    final = list(console._analyse("video.mp4", None))[-1]
    cards = final[console.SLOT["interventions"]]
    assert console.REALTIME_FRAMING in cards
    assert console.CARD_TITLE in cards


# =============================================================================
# D3 — KPI paneli: şartname §4 metrikleri DEMODA istiyor
# =============================================================================
#
# "Katılımcılar… kendi metriklerini tanımlamalıdır… Tanımlanan metrikler,
# demo ve raporlarda AÇIK ŞEKİLDE sunulmalıdır." Hepsini üretiyoruz
# (bench/perception.json, benchmark/kpi.py, gozcu/trace.py) — konsolda
# hiçbiri yoktu.

class TestKpiPanel:
    def test_unmeasured_is_never_rendered_as_zero(self):
        """`benchmark/kpi.py` ile aynı sözleşme: 0 'ölçtük, sıfır çıktı'."""
        from gozcu.ui.console import Session
        text = console.kpi_markdown(Session().store)
        assert console.KPI_UNMEASURED in text
        assert "%0" not in text

    def test_perception_block_reads_the_bench_file(self, tmp_path):
        import json
        path = tmp_path / "perception.json"
        path.write_text(json.dumps({"result": {
            "presence_recall": 0.991, "count_recall": 0.931,
            "incident_energy_percentile": 0.035, "frames": 347,
            "real_time_factor": 0.35}}), encoding="utf-8")
        text = console.perception_markdown(path)
        assert "%99" in text and "%93" in text

    def test_perception_block_says_so_when_the_file_is_missing(self, tmp_path):
        """Ölçüm dosyası yoksa uydurulmuyor."""
        text = console.perception_markdown(tmp_path / "yok.json")
        assert console.KPI_UNMEASURED in text

    def test_perception_block_survives_a_corrupt_file(self, tmp_path):
        path = tmp_path / "bozuk.json"
        path.write_text("{ bu json değil", encoding="utf-8")
        assert console.KPI_UNMEASURED in console.perception_markdown(path)

    def test_kpi_markdown_names_its_three_blocks(self):
        from gozcu.ui.console import Session
        text = console.kpi_markdown(Session().store)
        for heading in (console.KPI_PERCEPTION, console.KPI_DECISION,
                        console.KPI_PERFORMANCE):
            assert heading in text


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


def test_kpi_numbers_use_turkish_decimal_commas():
    """Depodaki bütün Türkçe metin virgül kullanıyor ("%72,4").

    Panel nokta kullanırsa aynı sayı iki belgede iki farklı dilde yazılır.
    """
    assert console._pct(0.991) == "%99,1"
    assert "," in console.perception_markdown()


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


class TestCardsOnlyForEscalations:
    """Kart YALNIZ ajanın gerçekten yükselttiği anlar için.

    Canlı koşuda ölçüldü: 1 epizot açıldı, yönlendirici hiç "escalate"
    demedi, hiçbir araç çağrılmadı — ama kart yine de basıldı ve üstünde
    "gerçek zamanlı kurulumda ajan bu anda müdahale ederdi" yazıyordu.

    Bu bir ABARTMA. Açılan her epizot bir müdahale anı değil; epizot zaman
    çizelgesinin işi, kart yükseltmenin. İkisini aynı şeye çevirmek, sistemin
    yapmadığı bir şeyi yaptığını söylemek olur — jürinin önünde.
    """

    def _store_with_episode(self):
        from gozcu.store import Store
        store = Store()
        store.create_episode(_card_episode(episode_id=None))
        return store

    def test_an_episode_that_never_escalated_gets_no_card(self):
        store = self._store_with_episode()
        html = console.intervention_html(store, escalated_ids=set())
        assert console.CARD_TITLE not in html
        assert console.NO_INTERVENTION in html

    def test_an_escalated_episode_gets_a_card(self):
        store = self._store_with_episode()
        ids = {episode.id for episode in store.episodes()}
        html = console.intervention_html(store, escalated_ids=ids)
        assert console.CARD_TITLE in html
        assert console.REALTIME_FRAMING in html

    def test_only_the_escalated_ones_are_carded(self):
        from gozcu.store import Store
        store = Store()
        store.create_episode(_card_episode(episode_id=None, start=10.0))
        store.create_episode(_card_episode(episode_id=None, start=50.0))
        episodes = store.episodes()
        html = console.intervention_html(store,
                                         escalated_ids={episodes[1].id})
        assert html.count(console.CARD_TITLE) == 1
        assert "00:50" in html and "00:10" not in html

    def test_no_episodes_at_all_says_so(self):
        from gozcu.store import Store
        assert console.NO_INTERVENTION in console.intervention_html(
            Store(), escalated_ids=set())
