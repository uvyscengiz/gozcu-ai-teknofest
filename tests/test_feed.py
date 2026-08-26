"""Besleme katmanı — oluş sırası ve ajan atfı.

Beslemenin bütün değeri iki şeyde: satırlar GERÇEKTEN olduğu sırada duruyor
ve her satır hangi ajanın ürettiğini söylüyor. İkisi de sessizce bozulabilir,
bu yüzden ikisi de burada sınanıyor.
"""

from gozcu.agents.supervisor import AUDIT_PREFIX
from gozcu.models import (ActionRecord, ClipBeat, DialogueTurn, Episode,
                          Handoff, Interpretation, ProposedAction,
                          RiskAssessment, WindowRecord)
from gozcu.store import Store
from gozcu.ui.feed import FEED_EMPTY, build_feed, feed_html


def _store():
    return Store(":memory:")


def test_an_empty_store_says_so_instead_of_drawing_a_box():
    assert build_feed(_store()) == []
    assert FEED_EMPTY in feed_html([])


def test_the_feed_follows_write_order_not_timestamp():
    """Telafi (`catch_up`) sonradan yazılan bir kaydı ÖNCEKİ bir video
    saniyesine koyabiliyor. Besleme yaşanan sırayı göstermek zorunda; damga
    zaten hangi saniyeye ait olduğunu söylüyor."""
    s = _store()
    s.save_dialogue(DialogueTurn(ts=90.0, role="supervisor", text="sonra"))
    s.save_dialogue(DialogueTurn(ts=10.0, role="system", text="telafi"))
    assert [e.title for e in build_feed(s)] == ["sonra", "telafi"]
    assert [e.ts for e in build_feed(s)] == [90.0, 10.0]


def test_every_entry_names_the_agent_that_produced_it():
    """%20'lik otonomi kriteri tam olarak "bunu ajan mı yaptı, insan mı" diye
    soruyor; besleme her satırda cevap veriyor."""
    s = _store()
    s.save_window(WindowRecord(ts=0.0, end_ts=9.0, index=1, total=2, frames=3,
                               floor_passed=True, outcome="routed"))
    s.save_handoff(Handoff(ts=0.0, source_agent="router",
                           target_agent="interpreter", reason="bak",
                           confidence=0.8, payload_ref="w"))
    s.save_interpretation(Interpretation(observation_ts=0.0,
                                         description="forklift devrildi",
                                         model="m"))
    eid = s.create_episode(Episode(start_ts=0.0, phase="onset",
                                   summary_tr="devrilme",
                                   preliminary_risk="Yüksek"))
    s.save_risk(RiskAssessment(episode_id=eid, level="Kritik",
                               rationale_tr="yaralı olabilir",
                               preventable=True))
    s.save_dialogue(DialogueTurn(ts=0.0, role="supervisor", text="dikkat"))
    s.save_action(ActionRecord(ts=0.0, tool_name="notify_supervisor",
                               actor="agent", approval="not_required"))

    assert [e.agent for e in build_feed(s)] == [
        "perception", "router", "interpreter", "synthesizer", "risk_analyst",
        "supervisor", "supervisor"]


def test_a_handoff_carries_both_ends_so_the_arrow_can_be_drawn():
    """Ajanların birbirine ne devrettiği — şartname §7'nin "çok adımlı karar
    zincirleri" kalemi tam olarak bu."""
    s = _store()
    s.save_handoff(Handoff(ts=1.0, source_agent="risk_analyst",
                           target_agent="supervisor", reason="yükselt",
                           confidence=0.91, payload_ref="e1"))
    entry, = build_feed(s)
    assert (entry.agent, entry.target) == ("risk_analyst", "supervisor")
    assert entry.confidence == 0.91
    assert entry.detail == "yükselt"
    assert "→" in feed_html([entry])


def test_the_perception_line_says_what_was_seen_and_what_happened_to_it():
    """"Bakılmadı" ile "bakıldı, bir şey yoktu" aynı satıra düşemez."""
    s = _store()
    s.save_window(WindowRecord(ts=10.0, end_ts=19.0, index=2, total=7,
                               frames=30, person_peak=2, detections=14,
                               labels=["forklift", "person"],
                               floor_passed=False, outcome="skipped"))
    entry, = build_feed(s)
    assert entry.agent == "perception"
    assert "2/7" in entry.title
    assert "taban geçemedi" in entry.title
    assert "30 kare" in entry.detail
    assert "kişi≤2" in entry.detail
    assert "hiçbir katman bakmadı" in entry.detail


def test_an_operator_action_is_not_credited_to_an_agent():
    s = _store()
    s.save_action(ActionRecord(ts=1.0, tool_name="notify_supervisor",
                               actor="operator", approval="not_required"))
    assert build_feed(s)[0].agent == "operator"


def test_the_approval_decision_appears_where_it_was_decided():
    """Çağrı çağrıldığı anda kalıyor, karar verildiği anda görünüyor."""
    s = _store()
    aid = s.save_action(ActionRecord(ts=3.0, tool_name="halt_production_line",
                                     actor="agent", approval="pending"))
    s.save_dialogue(DialogueTurn(ts=3.0, role="operator", text="onayla"))
    s.set_action_approval(aid, "approved")
    assert [(e.kind, e.agent) for e in build_feed(s)] == [
        ("action", "supervisor"), ("dialogue", "operator"),
        ("approval", "operator")]


def test_the_call_line_keeps_the_state_it_had_when_it_was_called():
    """Anlık görüntü olmasaydı, çağrıldığı anda `pending` olan bir araç
    geriye dönük `onaylandı` görünürdü."""
    s = _store()
    aid = s.save_action(ActionRecord(ts=3.0, tool_name="halt_production_line",
                                     actor="agent", approval="pending"))
    s.set_action_approval(aid, "approved")
    call, decision = build_feed(s)
    assert "onay bekliyor" in call.detail
    assert "onaylandı" in decision.title


def test_a_gated_call_does_not_print_the_same_tool_three_times():
    """Onaylı bir araç ÜÇ defter satırı doğuruyor: ajanın `pending` çağrısı,
    operatörün ikinci `call_tool`u ve onay güncellemesi. Üçünü de basmak bir
    kez çağrılan aracı üç kez çağrılmış gibi gösterir."""
    s = _store()
    aid = s.save_action(ActionRecord(ts=3.0, tool_name="halt_production_line",
                                     actor="agent", approval="pending"))
    s.save_action(ActionRecord(ts=3.0, tool_name="halt_production_line",
                               actor="operator", approval="approved"))
    s.set_action_approval(aid, "approved")
    assert [(e.kind, e.agent) for e in build_feed(s)] == [
        ("action", "supervisor"), ("approval", "operator")]


def test_an_updated_episode_shows_the_summary_it_had_at_the_time():
    s = _store()
    eid = s.create_episode(Episode(start_ts=1.0, phase="onset",
                                   summary_tr="ilk hâli",
                                   preliminary_risk="Düşük"))
    s.update_episode(eid, summary_tr="sonraki hâli", preliminary_risk="Kritik")
    first, second = build_feed(s)
    assert (first.title, first.risk) == ("ilk hâli", "Düşük")
    assert (second.title, second.risk) == ("sonraki hâli", "Kritik")


def test_an_operator_correction_is_not_dressed_up_as_model_output():
    """`update_episode`'un iki çağıranı ayrı şeyler yapıyor: sentezleyici
    kaynaştırıyor, süpervizör operatörün sözüyle DÜZELTİYOR."""
    s = _store()
    eid = s.create_episode(Episode(start_ts=1.0, phase="onset",
                                   summary_tr="a", preliminary_risk="Orta"))
    s.update_episode(eid, summary_tr="kaynaştı")
    s.update_episode(eid, summary_tr="düzeltildi", origin="supervisor")
    merged, corrected = build_feed(s)[1], build_feed(s)[2]
    assert (merged.agent, merged.detail) == ("synthesizer", "Olaya eklendi")
    assert (corrected.agent, corrected.detail) == ("supervisor",
                                                   "Özet düzeltildi")


def test_the_escalated_episode_is_marked_and_the_others_are_not():
    s = _store()
    quiet = s.create_episode(Episode(start_ts=1.0, phase="onset",
                                     summary_tr="sakin",
                                     preliminary_risk="Düşük"))
    loud = s.create_episode(Episode(start_ts=9.0, phase="onset",
                                    summary_tr="kriz",
                                    preliminary_risk="Kritik"))
    kinds = {e.title: e.kind for e in build_feed(s, escalated_ids={loud})}
    assert kinds == {"sakin": "episode", "kriz": "escalation"}
    # `None` = "bilmiyorum" ve güvenli yorumu abartmak değil susmaktır.
    assert [e.kind for e in build_feed(s, escalated_ids=None)] == [
        "episode", "episode"]
    assert [e.kind for e in build_feed(s, escalated_ids={quiet})] == [
        "escalation", "episode"]


def test_an_escalation_that_merged_into_an_open_episode_is_still_marked():
    """Açık bir epizotta `escalate` `_resolve` ile kaynaşmaya iniyor ve o an
    bir `update` satırı doğuruyor — çapa `create` ile sınırlı olamaz."""
    s = _store()
    eid = s.create_episode(Episode(start_ts=1.0, phase="onset",
                                   summary_tr="açık olay",
                                   preliminary_risk="Orta"))
    s.update_episode(eid, summary_tr="olay büyüdü")
    # Kart epizodun SON satırında, hepsinde değil: yükseltilen bir epizot
    # birden çok defter satırı taşıyor ve hepsini işaretlemek aynı kartı iki
    # kez bastırırdı — beslemenin ortadan kaldırmak için var olduğu tekrar.
    kinds = [e.kind for e in build_feed(s, escalated_ids={eid})]
    assert kinds == ["episode", "escalation"]
    cards = [e.card for e in build_feed(s, escalated_ids={eid})]
    assert cards[0] is None and cards[1] is not None


def test_the_proactive_mark_comes_from_the_record_not_from_adjacency():
    """Komşuluktan türetme iş parçacıkları arasında kırılıyor: `talk()`
    operatör satırını yazıp saniyelerce modelde kalıyor ve o boşlukta düşen
    bir yükseltme sırayı operatör → yükseltme → cevap yapıyor. Türetilmiş
    kural rozeti YANLIŞ satıra takardı; kaynak artık yazma anı."""
    s = _store()
    s.save_dialogue(DialogueTurn(ts=1.0, role="operator", text="ne oluyor"))
    # araya düşen yükseltme — operatörün sorusundan SONRA, cevabından ÖNCE
    s.save_dialogue(DialogueTurn(ts=3.0, role="supervisor", text="uyarı",
                                 proactive=True))
    s.save_dialogue(DialogueTurn(ts=2.0, role="supervisor", text="cevap"))

    # Rozet `title`'a gömülü DEĞİL: başlık saf metin kalıyor.
    marks = {e.title: e.proactive for e in build_feed(s)
             if e.kind == "dialogue"}
    assert marks == {"ne oluyor": False, "uyarı": True, "cevap": False}, (
        "komşuluk kuralı burada 'cevap'ı kendiliğinden sayardı")

    from gozcu.ui.feed import PROACTIVE_MARK
    assert PROACTIVE_MARK in feed_html(build_feed(s))


def test_audit_rows_stay_out_of_the_feed():
    """Denetim hükmü operatöre söylenmiş bir söz değil. Diğer `system`
    satırları GÖRÜNÜYOR — bozulmuş mod cevapları ve `LATE_NOTICE` demo
    beat 6'nın kendisi."""
    s = _store()
    s.save_dialogue(DialogueTurn(ts=1.0, role="system",
                                 text=f"{AUDIT_PREFIX} engellendi"))
    s.save_dialogue(DialogueTurn(ts=2.0, role="system",
                                 text="bağlantı kesildi"))
    assert [e.title for e in build_feed(s)] == ["bağlantı kesildi"]


def test_archived_episodes_never_enter_the_feed():
    """`load_history` arşiv fikstürlerini epizot olarak yazıyor. Beslemede
    "sentezleyici olay açtı" diye görünürlerse bu videoda olmamış bir şey
    iddia edilir."""
    s = _store()
    old = s.create_episode(Episode(start_ts=0.0, phase="outcome",
                                   summary_tr="geçen ayki kaza",
                                   preliminary_risk="Yüksek", state="closed"))
    s.create_episode(Episode(start_ts=5.0, phase="onset", summary_tr="bugünkü",
                             preliminary_risk="Orta"))
    assert [e.title for e in build_feed(s, archived={old})] == ["bugünkü"]


def test_the_risk_line_carries_its_level_and_proposed_tools():
    s = _store()
    eid = s.create_episode(Episode(start_ts=7.0, phase="onset",
                                   summary_tr="devrilme",
                                   preliminary_risk="Yüksek"))
    s.save_risk(RiskAssessment(
        episode_id=eid, level="Kritik", rationale_tr="yaralı olabilir",
        preventable=True,
        proposed_actions=[ProposedAction(description_tr="hattı durdur",
                                         tool_name="halt_production_line")]))
    risk_entry = build_feed(s)[-1]
    assert risk_entry.agent == "risk_analyst"
    assert risk_entry.risk == "Kritik"
    assert risk_entry.ts == 7.0, "risk satırı epizodun saniyesinde durmalı"
    assert "halt_production_line" in risk_entry.detail


def test_the_risk_row_carries_the_assessment_moment_not_the_episode_start():
    """26 Ağustos koşusunda 01:38'de yapılan analiz besleme satırında
    "00:00" görünüyordu — defter damgasız kaydediyordu, satır da epizodun
    başına düşüyordu (spec §6). `RiskAssessment.ts` artık kendi anını
    taşıyor ve satır onu göstermeli, epizot başlangıcını değil."""
    s = _store()
    eid = s.create_episode(Episode(start_ts=0.0, end_ts=90.0, phase="onset",
                                   summary_tr="devrilme",
                                   preliminary_risk="Yüksek"))
    s.save_risk(RiskAssessment(
        episode_id=eid, ts=90.0, level="Kritik",
        rationale_tr="yaralı olabilir", preventable=True))
    risk_entry = build_feed(s)[-1]
    assert risk_entry.ts == 90.0


def test_the_interpreter_line_carries_its_beats():
    s = _store()
    s.save_interpretation(Interpretation(
        observation_ts=4.0, description="istif aracı devrildi", model="m",
        beats=[ClipBeat(offset_s=1.0, text="araç yalpaladı"),
               ClipBeat(offset_s=3.0, text="yük düştü")]))
    entry, = build_feed(s)
    assert entry.agent == "interpreter"
    assert entry.detail == "araç yalpaladı · yük düştü"


def test_a_journal_row_pointing_at_a_missing_record_is_skipped_not_raised():
    """Bir tanı yüzeyi ölçtüğü koşuyu öldürmemeli — `trace.py` ile aynı
    sözleşme."""
    s = _store()
    s.save_dialogue(DialogueTurn(ts=1.0, role="supervisor", text="var"))
    s.db.execute("INSERT INTO journal (source, row_id, kind) "
                 "VALUES ('dialogue', 999, 'create')")
    s.db.execute("INSERT INTO journal (source, row_id, kind) "
                 "VALUES ('kimsenin_bilmediği_tablo', 1, 'create')")
    s.db.commit()
    assert [e.title for e in build_feed(s)] == ["var"]


def test_the_html_puts_the_newest_entry_first_in_the_dom():
    """`column-reverse` görsel sırayı ters çeviriyor: DOM'da EN YENİ ÖNCE
    yazılıyor ki ekranda eskiden yeniye okunsun ve kaydırma en yeniye
    sabitlensin (tarayıcıda ölçüldü)."""
    s = _store()
    s.save_dialogue(DialogueTurn(ts=1.0, role="supervisor", text="birinci"))
    s.save_dialogue(DialogueTurn(ts=2.0, role="supervisor", text="ikinci"))
    markup = feed_html(build_feed(s))
    assert "column-reverse" in markup
    assert markup.index("ikinci") < markup.index("birinci")


def test_the_html_is_deterministic_so_the_skip_can_work():
    """`console._feed_slot` dizeyi bir öncekiyle karşılaştırıyor; çizim anı
    ya da duvar saati girerse atlama hiç çalışmaz ve jürinin kaydırması her
    saniye bozulur."""
    s = _store()
    s.save_dialogue(DialogueTurn(ts=1.0, role="supervisor", text="bir"))
    assert feed_html(build_feed(s)) == feed_html(build_feed(s))


def test_the_operator_is_visually_apart_from_the_supervisor():
    """`gr.Chatbot` baloncukları kalktı ve şartname §7 metin tabanlı
    etkileşimin NET görünmesini istiyor."""
    s = _store()
    s.save_dialogue(DialogueTurn(ts=1.0, role="operator", text="soru"))
    s.save_dialogue(DialogueTurn(ts=2.0, role="supervisor", text="cevap"))
    operator, supervisor = build_feed(s)
    from gozcu.ui.feed import _entry_html
    assert "margin-left" in _entry_html(operator)
    assert "margin-left" not in _entry_html(supervisor)


def test_model_text_is_escaped_so_it_cannot_break_the_page():
    s = _store()
    s.save_dialogue(DialogueTurn(ts=1.0, role="supervisor",
                                 text="<script>alert(1)</script>"))
    markup = feed_html(build_feed(s))
    assert "<script>alert(1)</script>" not in markup
    assert "&lt;script&gt;" in markup


def test_an_unknown_risk_level_does_not_borrow_a_real_colour():
    from gozcu.ui.feed import RISK_COLORS, UNKNOWN_COLOR, risk_color

    assert risk_color("Felaket") == UNKNOWN_COLOR
    assert UNKNOWN_COLOR not in RISK_COLORS.values()
    assert len(set(RISK_COLORS.values())) == 4


def test_the_intervention_card_is_drawn_inside_the_feed_at_that_moment():
    """Kart artık kendi sekmesinde değil. Ayrı sekme onu olaydan koparıyordu:
    jüri kartı görmek için ekran değiştirmek zorundaydı."""
    from gozcu.ui.feed import CARD_TITLE, REALTIME_FRAMING

    s = _store()
    eid = s.create_episode(Episode(start_ts=10.0, end_ts=20.0, phase="onset",
                                   summary_tr="istif aracı devrildi",
                                   participants=["forklift"],
                                   preliminary_risk="Yüksek"))
    s.save_dialogue(DialogueTurn(ts=10.0, role="supervisor",
                                 text="hattı durdurun"))
    s.save_action(ActionRecord(ts=12.0, tool_name="notify_supervisor",
                               actor="agent", approval="not_required"))
    s.save_risk(RiskAssessment(episode_id=eid, level="Kritik",
                               rationale_tr="yaralı olabilir",
                               preventable=True))

    escalated = build_feed(s, escalated_ids={eid})[0]
    assert escalated.kind == "escalation"
    assert CARD_TITLE in escalated.card
    assert REALTIME_FRAMING in escalated.card
    assert "notify_supervisor" in escalated.card
    assert "hattı durdurun" in escalated.card
    assert CARD_TITLE in feed_html(build_feed(s, escalated_ids={eid}))


def test_the_intervention_card_is_stamped_with_the_first_assessment():
    """Kapanışta ikinci kez değerlendirilip yeniden yükseltilen bir epizotta
    devir defterine iki risk kaydı düşebilir. Kartın başlığındaki "MÜDAHALE
    ANI" her zaman İLK değerlendirmenin anı olmalı — ikinci, geç yükseltmenin
    anı değil (spec §6)."""
    s = _store()
    eid = s.create_episode(Episode(start_ts=0.0, end_ts=90.0, phase="onset",
                                   summary_tr="istif aracı devrildi",
                                   preliminary_risk="Yüksek"))
    s.save_risk(RiskAssessment(episode_id=eid, ts=19.0, level="Yüksek",
                               rationale_tr="ilk değerlendirme",
                               preventable=True))
    s.save_risk(RiskAssessment(episode_id=eid, ts=90.0, level="Kritik",
                               rationale_tr="ikinci değerlendirme",
                               preventable=True))

    escalated = build_feed(s, escalated_ids={eid})[0]
    assert "00:19" in escalated.card


def test_an_episode_nobody_escalated_gets_no_card():
    """Bir koşuda 1 epizot açıldı, hiç yükseltme olmadı ve kart yine de
    basılmıştı — üstünde "ajan bu anda müdahale ederdi" yazıyordu. Sistem
    yapmadığı bir şeyi yaptığını söylüyordu."""
    s = _store()
    s.create_episode(Episode(start_ts=1.0, phase="onset", summary_tr="sakin",
                             preliminary_risk="Düşük"))
    assert build_feed(s)[0].card is None
    from gozcu.ui.feed import CARD_TITLE
    assert CARD_TITLE not in feed_html(build_feed(s))


def test_an_episode_shows_its_own_beats_not_just_the_summary():
    """Epizot kendi içinde bir zaman çizelgesi taşıyor; besleme onu tek
    satıra düşürürse operatör olayın SEYRİNİ değil yalnız pencerenin
    sınırını görür."""
    from gozcu.models import EventBeat

    s = _store()
    s.create_episode(Episode(start_ts=10.0, phase="onset",
                             summary_tr="raf çöktü", preliminary_risk="Yüksek",
                             beats=[EventBeat(ts=13.0, text="raf çöküyor"),
                                    EventBeat(ts=14.0, text="toz yayılıyor")]))
    entry, = build_feed(s)
    assert "00:13 raf çöküyor" in entry.detail
    assert "00:14 toz yayılıyor" in entry.detail
    assert entry.ts == 13.0, "damga olayın başladığı an, pencerenin sınırı değil"


def test_an_episode_entry_does_not_show_beats_learned_later():
    """Kaynaşma her pencerede yeni an ekliyor. Canlı okunursa koşunun
    başındaki bir girdi olayın SONUNDA öğrenilen anları gösterir."""
    from gozcu.models import EventBeat

    s = _store()
    eid = s.create_episode(Episode(start_ts=10.0, phase="onset",
                                   summary_tr="raf çöktü",
                                   preliminary_risk="Yüksek",
                                   beats=[EventBeat(ts=13.0, text="raf çöküyor")]))
    s.update_episode(eid, beats=[EventBeat(ts=13.0, text="raf çöküyor"),
                                 EventBeat(ts=21.0, text="ekip geldi")])
    opened, merged = build_feed(s)
    assert "ekip geldi" not in opened.detail
    assert "ekip geldi" in merged.detail


def test_an_episode_with_no_beats_falls_back_to_the_window_edge():
    s = _store()
    s.create_episode(Episode(start_ts=10.0, phase="onset", summary_tr="sakin",
                             preliminary_risk="Düşük"))
    assert build_feed(s)[0].ts == 10.0


def test_the_operator_indent_is_not_eaten_by_the_margin_shorthand():
    """`margin:.25rem 0` kısayolu kendinden ÖNCEKİ `margin-left`i sıfırlar.
    Tarayıcıda ölçüldü: girinti sessizce kayboluyordu ve operatör ile
    süpervizör yalnız zemin tonuyla ayrılıyordu."""
    from gozcu.ui.feed import _entry_html

    s = _store()
    s.save_dialogue(DialogueTurn(ts=1.0, role="operator", text="soru"))
    markup = _entry_html(build_feed(s)[0])
    style = markup.split("style='", 1)[1].split("'", 1)[0]
    assert "margin-left:2.5rem" in style
    assert style.index("margin:") < style.index("margin-left:"), (
        "kısayol girintiden sonra gelirse onu ezer")


def test_the_risk_analysts_tool_calls_are_not_credited_to_the_supervisor():
    """`assess_risk` soruşturma araçlarını `Supervisor.escalate` İÇİNDE,
    süpervizör daha ağzını açmadan çağırıyor. Hepsini süpervizöre yazmak
    §7'nin puanladığı zincir hakkında yalan söylemek olurdu."""
    s = _store()
    s.save_action(ActionRecord(ts=1.0, tool_name="get_equipment_history",
                               actor="agent", approval="not_required",
                               caller="risk_analyst"))
    s.save_action(ActionRecord(ts=2.0, tool_name="notify_supervisor",
                               actor="agent", approval="not_required"))
    assert [e.agent for e in build_feed(s)] == ["risk_analyst", "supervisor"]


def test_an_operator_triggered_call_stays_the_operators_whatever_the_caller():
    """`actor` "insan mı makine mi" diye soruyor ve `caller`'ı eziyor."""
    s = _store()
    s.save_action(ActionRecord(ts=1.0, tool_name="notify_supervisor",
                               actor="operator", approval="not_required",
                               caller="risk_analyst"))
    assert build_feed(s)[0].agent == "operator"


def test_the_card_quotes_what_was_said_after_the_escalation_not_before():
    """`talk()` sohbet cevabını AÇIK epizodun `start_ts`'ine sabitliyor —
    kartın eski `ts` anahtarlı araması yükseltmeden ÖNCEKİ bir sohbet
    cevabını "DEDİĞİ" diye basabiliyordu."""
    from gozcu.ui.feed import CARD_SAID

    s = _store()
    eid = s.create_episode(Episode(start_ts=10.0, end_ts=20.0, phase="onset",
                                   summary_tr="olay", preliminary_risk="Orta"))
    # olay açık; operatör soruyor, süpervizör cevaplıyor — HENÜZ yükseltme yok
    s.save_dialogue(DialogueTurn(ts=10.0, role="operator", text="durum ne"))
    s.save_dialogue(DialogueTurn(ts=10.0, role="supervisor",
                                 text="sakin görünüyor"))
    # sonra olay büyüyor ve ajan kendiliğinden sesleniyor
    s.update_episode(eid, summary_tr="olay büyüdü", preliminary_risk="Kritik")
    s.save_dialogue(DialogueTurn(ts=10.0, role="supervisor",
                                 text="hattı durdurun", proactive=True))

    card = [e for e in build_feed(s, escalated_ids={eid}) if e.card][0].card
    assert "hattı durdurun" in card
    assert "sakin görünüyor" not in card, (
        "kart yükseltmeden önceki sohbet cevabını alıntılıyor")
    assert CARD_SAID in card


def test_the_feed_shows_a_deferred_window_as_its_own_line():
    """Düzeltmeyi ilk satıra yazmak kesintiyi olayın başında olmuş gibi
    gösterirdi. Pencere işlendi, SONRA ertelendi — ikisi de olmuş şeyler."""
    s = _store()
    wid = s.save_window(WindowRecord(ts=30.0, end_ts=39.0, index=4, total=6,
                                     frames=30, person_peak=1, detections=5,
                                     labels=["person"], floor_passed=True,
                                     outcome="routed"))
    s.set_window_outcome(wid, "deferred")

    first, correction = build_feed(s)
    assert "yönlendiriciye gitti" in first.detail
    assert correction.agent == "perception"
    assert correction.kind == "window_update"
    assert "telafi kuyruğuna alındı" in correction.title
    assert "4/6" in correction.title


def test_a_call_lines_detail_shows_the_state_it_was_recorded_with():
    """26 Ağustos kararı (spec §2): saha araçları artık her çağrıda başarır,
    yani `site_alarm` bir daha `zone_unresolved` döndürmez. Ölçüye dayanan
    değişen şey durumun ADI; kartın kaydedilen sonucu OLDUĞU GİBİ (üç noktanın
    arkasına gizlemeden) göstermesi davranışı aynı kalıyor."""
    s = _store()
    s.save_action(ActionRecord(
        ts=1.0, tool_name="site_alarm", actor="agent",
        approval="not_required",
        params={"zone": "Sentez Hattı", "level": "warning"},
        result={"alarm_id": "2026-3003", "affected_zone": "Sentez Hattı",
                "zone_id": None, "level": "warning",
                "siren_state": "active"}))
    entry, = build_feed(s)
    assert "active" in entry.detail


def test_a_successful_call_still_reads_naturally():
    s = _store()
    s.save_action(ActionRecord(
        ts=1.0, tool_name="site_alarm", actor="agent",
        approval="not_required", params={"zone": "B-Hattı"},
        result={"alarm_id": "2026-3001", "affected_zone": "B-Hattı",
                "zone_id": "Z-01", "siren_state": "active"}))
    assert "active" in build_feed(s)[0].detail


def test_a_merge_is_stamped_when_it_merged_not_when_the_event_began():
    """26 Ağustos koşusunda besleme 01:13'ten sonra 00:40 gösteriyordu:
    kaynaşma satırı epizodun İLK anını basıyordu, kaynaşmanın olduğu anı
    değil. Sıra doğruydu, saat yalan söylüyordu."""
    from gozcu.models import EventBeat

    s = _store()
    eid = s.create_episode(Episode(start_ts=40.0, end_ts=49.0, phase="onset",
                                   summary_tr="olay başladı",
                                   preliminary_risk="Orta",
                                   beats=[EventBeat(ts=42.0, text="ilk an")]))
    s.update_episode(eid, end_ts=79.0, summary_tr="olay büyüdü",
                     beats=[EventBeat(ts=42.0, text="ilk an"),
                            EventBeat(ts=70.0, text="sonraki an")])

    opened, merged = build_feed(s)
    assert opened.ts == 42.0, "açılış olayın başladığı anı gösterir"
    assert merged.ts == 79.0, "kaynaşma kaynaştığı pencereyi gösterir"


def test_an_episode_with_no_end_still_stamps_something_sensible():
    s = _store()
    eid = s.create_episode(Episode(start_ts=40.0, phase="onset",
                                   summary_tr="açık olay",
                                   preliminary_risk="Orta"))
    s.update_episode(eid, summary_tr="hâlâ açık")
    assert [e.ts for e in build_feed(s)] == [40.0, 40.0]
