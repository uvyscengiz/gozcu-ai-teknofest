"""Görev 14 — Nöbetçi süpervizör.

Puanın %20'si burada, ve bu dosyanın testleri üç iddiayı koruyor:

**Prompt ile şema ayrışamaz.** Prompt bir araç adı sayıyorsa o ad şemada
gerçekten var olmalı — aksi hâlde model var olmayan bir aracı çağırır, kaskad
hiç tetiklenmez ve KPI sıfır okur. Bir test bunu yapısal olarak kilitliyor.

**Aynı anda tek bir onay bekleyebilir.** İkinci bir bekleyen satır, birincisini
kalıcı olarak görünmez kılıyordu. Süpervizör ikinci kapılı aksiyonu reddediyor
ve operatöre nedenini söylüyor.

**Kesinti operatöre boş mesaj olarak gitmez.** Bozulmuş yanıt, boş yanıt ve
sonuçlanmayan araç turu üç ayrı Türkçe metne düşüyor.

`gw.ask.call_args_list` üzerinden prompt içeriği doğrulanamaz: süpervizör
`self.history` listesini canlı olarak büyütüyor ve `call_args` o listeye
**referans** tutuyor. Bu yüzden `_setup` her çağrıda mesajların bir kopyasını
donduruyor ve testler `gw.prompts` üzerinden bakıyor.
"""

import json
import re
from unittest.mock import Mock, patch

import pytest

from gozcu.agents.reporter import RootCauseReport
from gozcu.agents.anomaly_analyst import EMPTY_SUMMARY as SYNTH_EMPTY
from gozcu.agents.supervisor import NO_DESCRIPTION_NOTE
from gozcu.agents.supervisor import (ALL_TOOL_SCHEMAS, AUDIT_PREFIX,
                                     CORRECT_OBSERVATION, DEGRADED_REPLY,
                                     EMPTY_REPLY, MAX_TURNS, NO_PLAN_LINE,
                                     SYSTEM_PROMPT, UNFINISHED_REPLY,
                                     Supervisor, uncertainty_note)
from gozcu.gateway import Response
from gozcu.guard import (CLEAN_NOTE, FLAGGED_NOTE, NEUTRAL_NOTICE,
                         UNREADABLE_NOTE, Screening)
from gozcu.models import (Episode, Observation, RiskAssessment,
                          Signals)
from gozcu.store import Store

EPISODE_TS = 192.0


@pytest.fixture
def store():
    """Boş bellek-içi depo — planlayıcı kaynaklı testler kendi epizodunu
    `_episode()` ile bu depoya yazıyor."""
    return Store(":memory:")


def _tool(name, params):
    return Response(tool_calls=[{"id": "c1", "type": "function",
                                 "function": {"name": name,
                                              "arguments": json.dumps(params)}}])


def _setup(responses):
    """Sahte gateway + tek açık epizot taşıyan depo.

    `gw.prompts` her çağrıdaki mesaj listesinin **dondurulmuş** kopyası:
    `call_args_list` canlı `history` listesine referans tuttuğu için doğrudan
    ondan okumak turun sonundaki hâli gösterir, o anki hâli değil.
    """
    gw = Mock()
    prompts: list[list[dict]] = []
    stream = iter(responses)

    def _ask(_tier, messages, **_kwargs):
        prompts.append([dict(m) for m in messages])
        return next(stream)

    gw.ask.side_effect = _ask
    gw.prompts = prompts

    store = Store(":memory:")
    e = Episode(start_ts=EPISODE_TS, phase="development",
                summary_tr="istif aracı devrildi, yerde hareketsiz kişi",
                preliminary_risk="Kritik")
    e.id = store.create_episode(e)
    return gw, store, e


def _risk(e):
    return RiskAssessment(episode_id=e.id, level="Kritik",
                          rationale_tr="g", preventable=True)


def _episode(store, summary_tr="istif aracı devrildi, yerde hareketsiz kişi",
            start_ts=EPISODE_TS):
    """Planlayıcı kaynaklı testlerin ortak epizodu — `_setup`'ın kurduğu
    epizottan ayrı: bu yardımcı kendi depo parametresini alıyor, gerçek bir
    `Mock()` gateway'e bağlı değil."""
    episode = Episode(start_ts=start_ts, phase="development",
                      summary_tr=summary_tr, preliminary_risk="Kritik")
    episode.id = store.create_episode(episode)
    return episode


def _gw(text):
    """Tek tip cevap veren sahte gateway — plan testleri araç turuyla
    ilgilenmiyor, yalnız `escalate()`'in mesaja plan satırını gömdüğünü
    doğruluyor."""
    gw = Mock()
    gw.ask.side_effect = lambda *a, **k: Response(content=text)
    return gw


def _halt(reason="devrilme"):
    return _tool("halt_production_line", {"line_id": "B", "rationale": reason})


def _screening(text="metin"):
    """Yamalanmış `screen_text` için gerçek bir dönüş değeri.

    `MagicMock` `DialogueTurn(text=...)` doğrulamasından geçmez (`text: str`),
    yani `return_value` verilmeyen bir yama testi kodun kendisiyle ilgisi
    olmayan bir doğrulama hatasına düşürür.
    """
    return Screening(text, "safe", CLEAN_NOTE)


# -- belirsizlik notu -------------------------------------------------------

def test_uncertainty_note_names_what_the_camera_cannot_see():
    n = uncertainty_note(Signals(vanished_tracks=[3], person_count=1))
    assert n and "göremiyor" in n.lower()


def test_person_without_a_velocity_estimate_is_an_uncertainty():
    """`velocities` boşken 'hareket ediyor mu' sorusunun cevabı YOK.

    `compute_signals` hızları yalnız iki kare arasında eşleşen track'ler için
    üretiyor: pencerenin ilk karesinde ve track eşleşmediğinde sözlük boş
    kalıyor. Yani `person_count=1, velocities={}` tam olarak Beat 2'nin hâli —
    kadrajda bir kişi var, hareket edip etmediği bilinmiyor. Not bu yüzden
    doluyor; boş dönmesi belirsizliği sessizce yutmak olurdu.
    """
    assert uncertainty_note(Signals(person_count=1))


def test_uncertainty_note_is_silent_when_nothing_is_unknown():
    assert uncertainty_note(Signals()) == ""
    assert uncertainty_note(Signals(person_count=1,
                                    velocities={1: 0.4})) == ""


# -- prompt / şema tutarlılığı ----------------------------------------------

#: Promptta geçen kimlik biçimli sözcükler (en az bir alt çizgi). Türkçe
#: düzyazı bu desene uymaz, araç ve parametre adları uyar.
_IDENTIFIER = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")


def _schema_names():
    return {s["function"]["name"] for s in ALL_TOOL_SCHEMAS}


def _schema_params():
    return {p for s in ALL_TOOL_SCHEMAS
            for p in s["function"]["parameters"]["properties"]}


def test_prompt_never_names_a_tool_that_the_schemas_do_not_define():
    """Promptun `gozlem_duzelt` demesi sistemi sessizce öldürüyordu.

    Şema `correct_observation` tanımlıyordu; model promptun dediğini
    gönderiyor, o ad hiçbir yere düşmüyor ve düzeltme kaskadı hiç
    tetiklenmiyordu. Testler yeşil, KPI sıfır.
    """
    known = _schema_names() | _schema_params()
    unknown = [t for t in _IDENTIFIER.findall(SYSTEM_PROMPT) if t not in known]
    assert unknown == []


def test_prompt_catalogue_is_generated_from_every_offered_schema():
    """Yukarıdaki test boş bir promptla da geçerdi; bu onu boş bırakmıyor."""
    for name in _schema_names():
        assert name in SYSTEM_PROMPT


def test_prompt_teaches_the_correction_tool_by_its_schema_name():
    assert CORRECT_OBSERVATION in _schema_names()
    assert CORRECT_OBSERVATION in SYSTEM_PROMPT


# -- yükseltme --------------------------------------------------------------

def test_escalation_queries_the_shift_before_speaking():
    gw, store, e = _setup([
        _tool("query_shift_personnel", {"zone": "B-Hattı",
                                        "at_time": "03:12"}),
        Response(content="03:12 — B-Hattı'nda istif aracı devrildi. "
                         "Risk: Kritik."),
        Response(content="uygun"),
    ])
    with patch("gozcu.agents.supervisor.assess_risk", return_value=_risk(e)), \
         patch("gozcu.agents.supervisor.plan_actions", return_value=None):
        message = Supervisor(gw, store).escalate(e)
    assert "query_shift_personnel" in [a.tool_name for a in store.actions()]
    assert "03:12" in message


def test_critical_escalation_is_not_filtered_by_the_guard():
    gw, store, e = _setup([Response(content="KRİTİK: yerde hareketsiz kişi.")])
    with patch("gozcu.agents.supervisor.assess_risk", return_value=_risk(e)), \
         patch("gozcu.agents.supervisor.plan_actions", return_value=None), \
         patch("gozcu.agents.supervisor.screen_text",
               return_value=_screening()) as g:
        Supervisor(gw, store).escalate(e)
    assert g.call_args.kwargs["critical"] is True


def test_escalation_carries_the_uncertainty_note_into_the_prompt():
    gw, store, e = _setup([Response(content="haber"), Response(content="uygun")])
    store.save_observation(Observation(ts=EPISODE_TS,
                                       signals=Signals(person_count=1)))
    with patch("gozcu.agents.supervisor.assess_risk", return_value=_risk(e)), \
         patch("gozcu.agents.supervisor.plan_actions", return_value=None):
        Supervisor(gw, store).escalate(e)
    assert "BELİRSİZLİK" in gw.prompts[0][-1]["content"]


# -- yükseltme kipleri: olay başına bir tam müdahale (Görev 6) --------------
#
# Ölçülen arıza (26 Ağustos, canlı koşu): aynı olay 6 kez yükseltildi, her
# seferinde `ESCALATION_INSTRUCTION` "önce araçları çağır" dediği için saha
# araçları 18 kez, risk analizi 7 kez koştu. İlk yükseltme tam müdahaledir;
# aynı olayın SONRAKİ yükseltmeleri depodaki son değerlendirmeyi kullanan bir
# gelişme bildirimidir — ne `assess_risk` yeniden koşar ne saha araçları
# yeniden çağrılır.

def _counting_assess(store, counter):
    """Gerçek `assess_risk` gibi DEPOYA DA yazan sahte.

    Kaydetmeyen bir sahteyle ikinci yükseltme `_latest_risk` üzerinden hiçbir
    şey bulamaz, `risk is None` teorik dalına düşer ve tam müdahaleye geri
    döner — test sonsuza dek kırmızı kalır.
    """
    def fake(gw, _store, episode):
        counter.append(1)
        # `ts=` burada yazılmıyor: bu sahtenin tek işi çağrı SAYISINI saymak,
        # `RiskAssessment.ts` bu testin hiçbir doğrulamasına girmiyor —
        # varsayılan 0.0 yeterli.
        assessment = RiskAssessment(episode_id=episode.id, level="Yüksek",
                                    rationale_tr="sahte", preventable=True)
        assessment.id = store.save_risk(assessment)
        return assessment
    return fake


def test_a_second_escalation_of_the_same_episode_is_an_update(monkeypatch):
    from gozcu.agents.supervisor import ESCALATION_INSTRUCTION, UPDATE_INSTRUCTION

    gw, store, e = _setup([Response(content="ilk haber"),
                           Response(content="gelişme")])
    calls: list[int] = []
    monkeypatch.setattr("gozcu.agents.supervisor.assess_risk",
                        _counting_assess(store, calls))
    nobetci = Supervisor(gw, store)

    nobetci.escalate(e)          # ilk: tam müdahale
    nobetci.escalate(e)          # ikinci: gelişme kipi

    assert len(calls) == 1, "analiz yalnız ilk yükseltmede koşar"
    last_system_message = gw.prompts[-1][-1]["content"]
    assert UPDATE_INSTRUCTION in last_system_message
    assert ESCALATION_INSTRUCTION not in last_system_message


def test_the_update_mode_reuses_the_stored_assessment(monkeypatch):
    gw, store, e = _setup([Response(content="gelişme"), Response(content="uygun")])
    stored = RiskAssessment(episode_id=e.id, level="Orta",
                            rationale_tr="önceki analiz", preventable=False)
    stored.id = store.save_risk(stored)

    def _must_not_be_called(*_args, **_kwargs):
        raise AssertionError("gelişme kipi analizi yeniden koşturmamalı")
    monkeypatch.setattr("gozcu.agents.supervisor.assess_risk",
                        _must_not_be_called)

    nobetci = Supervisor(gw, store)
    nobetci._escalated.add(e.id)   # bu olay için tam müdahale zaten yapıldı
    nobetci.escalate(e)

    # "Orta" kritik değil, denetim kademesi devrede: bu yüzden ilk (`main`)
    # çağrının mesajına bakılıyor, denetimin kendi (`guard`) çağrısına değil.
    last_system_message = gw.prompts[0][-1]["content"]
    assert "Risk: Orta" in last_system_message


def test_a_new_episode_gets_a_full_escalation_again(monkeypatch):
    gw, store, episode_one = _setup([Response(content="ilk haber"),
                                     Response(content="ikinci haber")])
    episode_two = Episode(start_ts=EPISODE_TS, phase="development",
                          summary_tr="ikinci olay: yangın algılandı",
                          preliminary_risk="Kritik")
    episode_two.id = store.create_episode(episode_two)
    calls: list[int] = []
    monkeypatch.setattr("gozcu.agents.supervisor.assess_risk",
                        _counting_assess(store, calls))
    nobetci = Supervisor(gw, store)

    nobetci.escalate(episode_one)
    nobetci.escalate(episode_two)      # farklı id → tam müdahale

    assert len(calls) == 2


# -- guard kaydı ------------------------------------------------------------

def test_flagged_reply_is_replaced_and_the_verdict_is_recorded():
    gw, store, _ = _setup([Response(content="uygunsuz bir ifade"),
                           Response(content="uygunsuz")])
    n = Supervisor(gw, store)
    reply = n.talk("özet")
    assert reply == NEUTRAL_NOTICE
    assert n.last_screening.verdict == "unsafe"
    audit = [t for t in store.dialogue() if t.text.startswith(AUDIT_PREFIX)]
    assert audit and FLAGGED_NOTE in audit[-1].text


def test_unreadable_verdict_is_recorded_as_not_screened():
    gw, store, _ = _setup([Response(content="normal cevap"),
                           Response(content="???")])
    n = Supervisor(gw, store)
    n.talk("özet")
    assert n.last_screening.screened is False
    assert any(UNREADABLE_NOTE in t.text for t in store.dialogue())


def test_clean_verdict_does_not_pollute_the_dialogue():
    gw, store, _ = _setup([Response(content="temiz cevap"),
                           Response(content="uygun")])
    Supervisor(gw, store).talk("özet")
    assert [t.role for t in store.dialogue()] == ["operator", "supervisor"]


# -- bozulmuş yanıt ---------------------------------------------------------

def test_degraded_response_does_not_reach_the_operator_as_an_empty_message():
    gw, store, _ = _setup([Response(degraded=True)])
    reply = Supervisor(gw, store).talk("durum?")
    assert reply == DEGRADED_REPLY
    assert store.dialogue()[-1].text == DEGRADED_REPLY
    assert store.dialogue()[-1].role == "system"


def test_empty_response_falls_back_with_its_own_reason():
    gw, store, _ = _setup([Response(content="   ")])
    assert Supervisor(gw, store).talk("durum?") == EMPTY_REPLY


def test_the_three_fault_texts_are_distinct():
    assert len({DEGRADED_REPLY, EMPTY_REPLY, UNFINISHED_REPLY}) == 3


# -- onay kapısı ------------------------------------------------------------

def test_line_stop_is_held_for_approval_and_not_executed(gated):
    gw, store, _ = _setup([_halt(), Response(content="B-Hattı'nı durdurayım mı?"),
                           Response(content="uygun")])
    n = Supervisor(gw, store)
    n.talk("durumu özetle")
    pending = n.pending_approval()
    assert pending is not None and pending.tool_name == "halt_production_line"
    assert pending.result["awaiting_approval"] is True


def test_a_second_gated_action_is_refused_while_one_is_pending(gated):
    """İkinci bekleyen satır birincisini kalıcı olarak görünmez kılıyordu."""
    gw, store, _ = _setup([_halt("ilk"), Response(content="onay?"),
                           Response(content="uygun"),
                           _halt("ikinci"), Response(content="ikinci cevap"),
                           Response(content="uygun")])
    n = Supervisor(gw, store)
    n.talk("hattı durdur")
    reply = n.talk("yine durdur")

    pending_rows = [a for a in store.actions() if a.approval == "pending"]
    assert len(pending_rows) == 1
    assert pending_rows[0].params["rationale"] == "ilk"
    assert n.pending_approval().id == pending_rows[0].id
    # operatör neyin beklediğini öğreniyor
    assert "halt_production_line" in reply and "onay" in reply.lower()


def test_the_refusal_reaches_the_model_as_a_tool_result(gated):
    gw, store, _ = _setup([_halt("ilk"), Response(content="onay?"),
                           Response(content="uygun"),
                           _halt("ikinci"), Response(content="ikinci cevap"),
                           Response(content="uygun")])
    n = Supervisor(gw, store)
    n.talk("hattı durdur")
    n.talk("yine durdur")
    tool_messages = [m for p in gw.prompts for m in p if m["role"] == "tool"]
    assert any(json.loads(m["content"]).get("refused") for m in tool_messages)


def test_ungated_actions_still_run_immediately():
    """Yalnız hat durdurma kapıda bekler; geri kalanı anında koşar."""
    gw, store, _ = _setup([_tool("dispatch_medical",
                                 {"location": "B-Hattı", "urgency": "critical",
                                  "description": "yerde kişi"}),
                           Response(content="ekip yolda"),
                           Response(content="uygun")])
    Supervisor(gw, store).talk("sağlık ekibi çağır")
    row = store.actions()[-1]
    assert row.tool_name == "dispatch_medical"
    assert row.approval == "not_required"
    assert row.result["state"] == "dispatched"


def test_approving_does_not_create_a_second_pending_approval(gated):
    gw, store, _ = _setup([_halt(), Response(content="onay?"),
                           Response(content="uygun")])
    n = Supervisor(gw, store)
    n.talk("dur")
    n.approve(n.pending_approval().id, True)
    assert n.pending_approval() is None
    assert [a.approval for a in store.actions()].count("pending") == 0


def test_approving_actually_halts_the_line(gated):
    gw, store, _ = _setup([_halt(), Response(content="onay?"),
                           Response(content="uygun")])
    n = Supervisor(gw, store)
    n.talk("dur")
    result = n.approve(n.pending_approval().id, True)
    # Onayın durumu ile aracın durumu ayrı anahtarlarda: düz birleştirmede
    # aracın `"halted"` değeri onayın `"approved"`ünü eziyordu.
    assert result["state"] == "approved"
    assert result["result"]["state"] == "halted"
    assert store.actions()[-1].result["state"] == "halted"


def test_refusing_marks_the_action_rejected_and_does_not_run_it(gated):
    gw, store, _ = _setup([_halt(), Response(content="onay?"),
                           Response(content="uygun")])
    n = Supervisor(gw, store)
    n.talk("dur")
    before = len(store.actions())
    n.approve(n.pending_approval().id, False)
    assert len(store.actions()) == before
    assert store.actions()[-1].approval == "rejected"


def test_a_rejected_gate_frees_the_slot_for_a_new_action(gated):
    gw, store, _ = _setup([_halt("ilk"), Response(content="onay?"),
                           Response(content="uygun"),
                           _halt("ikinci"), Response(content="onay?"),
                           Response(content="uygun")])
    n = Supervisor(gw, store)
    n.talk("dur")
    n.approve(n.pending_approval().id, False)
    n.talk("yeniden dur")
    assert n.pending_approval().params["rationale"] == "ikinci"


def test_approving_an_unknown_action_returns_a_result_instead_of_raising():
    gw, store, _ = _setup([Response(content="cevap"), Response(content="uygun")])
    result = Supervisor(gw, store).approve(9999, True)
    assert result["state"] == "unknown_action"
    assert result["error"]


def test_a_settled_action_is_never_executed_twice(gated):
    gw, store, _ = _setup([_halt(), Response(content="onay?"),
                           Response(content="uygun")])
    n = Supervisor(gw, store)
    n.talk("dur")
    action_id = n.pending_approval().id
    n.approve(action_id, True)
    before = len(store.actions())
    result = n.approve(action_id, True)
    assert result["state"] == "not_pending"
    assert len(store.actions()) == before


# -- düzeltme kaskadı -------------------------------------------------------

def _correction(**overrides):
    params = {"episode_id": 1, "field": "event_type", "old": "araç devrildi",
              "new": "yük düştü", "rationale": "operatör gözlemi"}
    return _tool(CORRECT_OBSERVATION, {**params, **overrides})


def test_correction_is_recorded_and_cascades_to_the_episode_summary():
    gw, store, e = _setup([_correction(),
                           Response(content="Anlaşıldı, kaydı güncelledim."),
                           Response(content="uygun")])
    with patch("gozcu.agents.supervisor.assess_risk", return_value=_risk(e)), \
         patch("gozcu.agents.supervisor.plan_actions", return_value=None):
        Supervisor(gw, store).talk("araç devrilmedi, yük düştü")
    assert store.corrections(1)[0].new == "yük düştü"
    assert "yük düştü" in store.episodes()[0].summary_tr


def test_correction_re_runs_the_risk_assessment():
    gw, store, e = _setup([_correction(old="a", new="b", rationale="g"),
                           Response(content="tamam"), Response(content="uygun")])
    with patch("gozcu.agents.supervisor.assess_risk",
               return_value=_risk(e)) as r, \
         patch("gozcu.agents.supervisor.plan_actions", return_value=None):
        Supervisor(gw, store).talk("düzeltme")
    r.assert_called_once()


def test_correction_is_stamped_with_the_video_time():
    gw, store, e = _setup([_correction(), Response(content="tamam"),
                           Response(content="uygun")])
    with patch("gozcu.agents.supervisor.assess_risk", return_value=_risk(e)), \
         patch("gozcu.agents.supervisor.plan_actions", return_value=None):
        Supervisor(gw, store).talk("düzeltme")
    assert store.corrections(1)[0].ts == EPISODE_TS


def test_a_correction_with_stray_keys_returns_an_error_not_a_crash():
    """`Correction` `extra="forbid"` — tek fazla anahtar bütün turu düşürürdü."""
    gw, store, _ = _setup([_correction(confidence=0.9),
                           Response(content="olmadı"), Response(content="uygun")])
    Supervisor(gw, store).talk("düzeltme")
    assert store.corrections(1) == []
    tool_messages = [m for p in gw.prompts for m in p if m["role"] == "tool"]
    assert any(json.loads(m["content"]).get("error") for m in tool_messages)


def test_correction_for_an_unknown_episode_is_reported():
    gw, store, _ = _setup([_correction(episode_id=77),
                           Response(content="olmadı"), Response(content="uygun")])
    Supervisor(gw, store).talk("düzeltme")
    tool_messages = [m for p in gw.prompts for m in p if m["role"] == "tool"]
    payloads = [json.loads(m["content"]) for m in tool_messages]
    assert any(p.get("warning") for p in payloads)


# -- süpervizörün kendi araçları --------------------------------------------

def test_search_timeline_is_reachable_as_a_tool():
    gw, store, _ = _setup([_tool("search_timeline", {"query": "devrilme"}),
                           Response(content="bulundu"),
                           Response(content="uygun")])
    with patch("gozcu.agents.supervisor.search_timeline",
               return_value=[]) as s:
        Supervisor(gw, store).talk("geçmişte oldu mu?")
    s.assert_called_once()


def test_root_cause_report_is_reachable_as_a_tool():
    """Geç import yamalanamıyordu; artık modül seviyesinde."""
    report = RootCauseReport(what_happened="oldu", probable_root_cause="fren",
                             confidence_limits="kamera")
    gw, store, _ = _setup([_tool("generate_root_cause_report", {}),
                           Response(content="rapor hazır"),
                           Response(content="uygun")])
    with patch("gozcu.agents.supervisor.generate_root_cause_report",
               return_value=report) as r:
        Supervisor(gw, store).talk("raporu ver")
    r.assert_called_once()


def test_request_risk_assessment_reports_an_unknown_episode():
    gw, store, _ = _setup([_tool("request_risk_assessment", {"episode_id": 77}),
                           Response(content="yok"), Response(content="uygun")])
    Supervisor(gw, store).talk("riski sor")
    tool_messages = [m for p in gw.prompts for m in p if m["role"] == "tool"]
    assert any(json.loads(m["content"]).get("error") for m in tool_messages)


def test_an_invented_tool_name_is_reported_to_the_model():
    gw, store, _ = _setup([_tool("make_coffee", {}), Response(content="olmadı"),
                           Response(content="uygun")])
    Supervisor(gw, store).talk("kahve")
    assert store.actions() == []
    tool_messages = [m for p in gw.prompts for m in p if m["role"] == "tool"]
    assert any(json.loads(m["content"]).get("error") for m in tool_messages)


# -- diyalog akışı ----------------------------------------------------------

def test_open_incident_is_appended_to_every_operator_turn():
    gw, store, _ = _setup([Response(content="cevap"), Response(content="uygun")])
    Supervisor(gw, store).talk("dur, başka bir şey soracağım")
    prompt_text = gw.prompts[0][-1]["content"]
    assert "Açık olay" in prompt_text


def test_dialogue_turns_are_recorded_both_sides():
    gw, store, _ = _setup([Response(content="Anlaşıldı."),
                           Response(content="uygun")])
    Supervisor(gw, store).talk("durum nedir?")
    assert [s.role for s in store.dialogue()] == ["operator", "supervisor"]


def test_dialogue_turns_carry_the_video_time_not_zero():
    """Her satır `00:00` damgalıysa kök neden raporunun diyalog bölümü yalan."""
    gw, store, _ = _setup([Response(content="Anlaşıldı."),
                           Response(content="uygun")])
    Supervisor(gw, store).talk("durum nedir?")
    assert [t.ts for t in store.dialogue()] == [EPISODE_TS, EPISODE_TS]


def test_tool_calls_are_stamped_with_the_video_time():
    gw, store, _ = _setup([_tool("query_equipment_history",
                                 {"equipment_id": "IST-04"}),
                           Response(content="bakım gecikmiş"),
                           Response(content="uygun")])
    Supervisor(gw, store).talk("ekipman geçmişi?")
    assert store.actions()[-1].ts == EPISODE_TS


def test_tool_loop_terminates_instead_of_spinning_forever():
    gw, store, _ = _setup([_tool("site_alarm", {"zone": "B",
                                                "level": "yuksek"})] * 12)
    reply = Supervisor(gw, store).talk("alarm çal")
    assert reply == UNFINISHED_REPLY
    assert gw.ask.call_count == MAX_TURNS <= 6


# =============================================================================
# D4 — Nöbetçi'nin çıkışı: "sorun yok" kabul edilebilmeli
# =============================================================================
#
# Ölçülen arıza (25 Ağustos, canlı koşu): operatör altı kez "devam et sorun
# yok" yazdı, ajan altı kez aynı onayı istedi ve konsol kilitlendi. Promptta
# iki kural çıkışsız bir döngü kuruyordu: her düzeltme `correct_observation`
# istiyor, her cevap açık olayı yeniden gündeme getiriyordu.
#
# Şartname §7 bunu doğrudan puanlıyor: "Diyalogun doğal ve insansı bir akışta
# ilerlemesi" (%20 kriterin maddesi).

class TestDismissalExit:
    def test_prompt_lets_the_agent_accept_a_dismissal(self):
        from gozcu.agents.supervisor import SYSTEM_PROMPT
        assert "KABUL EDERSİN" in SYSTEM_PROMPT
        assert "KONUYU BIRAKIRSIN" in SYSTEM_PROMPT

    def test_prompt_caps_repeated_approval_requests(self):
        from gozcu.agents.supervisor import SYSTEM_PROMPT
        assert "iki defadan fazla isteme" in SYSTEM_PROMPT

    def test_prompt_reminds_once_not_every_turn(self):
        """'Her turda hatırlat' kuralı döngünün diğer yarısıydı."""
        from gozcu.agents.supervisor import SYSTEM_PROMPT
        assert "BİR KEZ" in SYSTEM_PROMPT
        assert "her turda değil" in SYSTEM_PROMPT

    def test_the_correction_tool_is_still_named(self):
        """Çıkış kuralı aracı ismen çağırmalı, yoksa model uydurur."""
        from gozcu.agents.supervisor import CORRECT_OBSERVATION, SYSTEM_PROMPT
        assert SYSTEM_PROMPT.count(CORRECT_OBSERVATION) >= 2


class TestEscalationActsInsteadOfInterviewing:
    """Ölçülen arıza: 7 yükseltme, 0 araç çağrısı.

    Ajan sadece soru soruyordu. Promptta üç ayrı "önce sor" baskısı vardı
    (uydurma yasağı, izin kuralı, yükseltme mesajının kendisi) ve tek bir
    "beklemeden çağır" kuralı. Üçe bir.
    """

    def test_prompt_no_longer_asks_for_permission(self):
        from gozcu.agents.supervisor import SYSTEM_PROMPT
        assert "İZİN İSTERSİN" not in SYSTEM_PROMPT

    def test_prompt_demands_action_before_questions(self):
        from gozcu.agents.supervisor import SYSTEM_PROMPT
        assert "ÖNCE" in SYSTEM_PROMPT and "SONRA" in SYSTEM_PROMPT

    def test_prompt_names_the_reversible_tools_to_call(self):
        """Kural soyut kalırsa model onu kendine uygulamıyor."""
        from gozcu.agents.supervisor import SYSTEM_PROMPT
        for tool in ("dispatch_medical", "radio_call", "site_alarm",
                     "open_safety_incident"):
            assert tool in SYSTEM_PROMPT

    def test_escalation_message_does_not_lead_with_asking(self):
        """`escalate()`'in kendi mesajı 'belirsizlik varsa sor' diyordu ve
        sistem promptundaki eylem kuralını eziyordu."""
        from gozcu.agents.supervisor import ESCALATION_INSTRUCTION
        assert "sor" not in ESCALATION_INSTRUCTION.lower().split("sonra")[0]
        assert "çağır" in ESCALATION_INSTRUCTION.lower()


def test_an_operator_correction_is_journalled_as_the_supervisors_work():
    """Beslemede düzeltme, sentezleyicinin kaynaştırmasından AYRI görünmeli:
    biri model çıktısı, öbürü insan müdahalesi."""
    from gozcu.models import Correction
    from gozcu.store import Store

    store = Store(":memory:")
    eid = store.create_episode(Episode(start_ts=1.0, phase="onset",
                                       summary_tr="forklift devrildi",
                                       preliminary_risk="Orta"))
    store.update_episode(eid, summary_tr="forklift devrildi, sürücü iyi")
    origins = [e.snapshot["origin"] for e in store.journal()]
    assert origins == ["anomaly_analyst", "anomaly_analyst"]

    store.update_episode(eid, summary_tr="istif aracı devrildi",
                         origin="supervisor")
    assert [e.snapshot["origin"] for e in store.journal()][-1] == "supervisor"


def test_escalate_marks_its_reply_proactive_and_talk_does_not():
    """Rozet YAZMA ANINDA kaydediliyor. Komşuluktan türetme iş parçacıkları
    arasında kırılıyor: `talk()` operatör satırını yazıp saniyelerce modelde
    kalıyor ve o boşlukta düşen bir yükseltme rozeti yanlış satıra takıyordu.
    """
    gw, store, e = _setup([Response(content="Raf devrildi, hattı durduruyorum."),
                           Response(content="uygun"),
                           Response(content="Şu an sakin."),
                           Response(content="uygun")])
    with patch("gozcu.agents.supervisor.assess_risk", return_value=_risk(e)), \
         patch("gozcu.agents.supervisor.plan_actions", return_value=None):
        nobetci = Supervisor(gw, store)

        nobetci.escalate(e)
        said = [t for t in store.dialogue() if t.role == "supervisor"]
        assert said and said[-1].proactive is True

        nobetci.talk("durum ne")
        said = [t for t in store.dialogue() if t.role == "supervisor"]
        assert said[-1].proactive is False, (
            "operatör sordu; bu cevap kendiliğinden değil")


# --- arıza metni olay tarifi değildir (Görev 20) -----------------------------

def test_a_diagnostic_episode_is_not_described_to_the_model_as_an_event():
    """26 Ağustos canlı koşusu: sentezleyici boş döndü, epizodun özeti
    "Sentez katmanı boş yanıt döndürdü" oldu ve süpervizör bunu fabrikada
    olmuş bir olay sanıp **var olmayan** bir bölgeye ("Sentez Hattı") alarm
    çaldırdı, telsizle operatör aradı, sağlık ekibi çağırdı. Hiçbiri
    yaşanmamıştı.

    Arıza metni prompt'a olay tarifi olarak GİRMEZ; yerine ne bilinmediği
    yazılır ve model bölge adı uydurmaktan men edilir.
    """
    gw, store, e = _setup([Response(content="Anlaşıldı, bekliyorum."),
                           Response(content="uygun")])
    broken = Episode(start_ts=EPISODE_TS, phase="development",
                     summary_tr=SYNTH_EMPTY, preliminary_risk="Orta",
                     summary_source="fallback")
    broken.id = store.create_episode(broken)

    with patch("gozcu.agents.supervisor.assess_risk", return_value=_risk(e)), \
         patch("gozcu.agents.supervisor.plan_actions", return_value=None):
        Supervisor(gw, store).escalate(broken)

    prompt = gw.prompts[0][-1]["content"]
    assert SYNTH_EMPTY not in prompt, "arıza metni olay tarifi olarak geçti"
    assert NO_DESCRIPTION_NOTE in prompt


def test_a_real_episode_still_reaches_the_model_verbatim():
    gw, store, e = _setup([Response(content="haber"), Response(content="uygun")])
    with patch("gozcu.agents.supervisor.assess_risk", return_value=_risk(e)), \
         patch("gozcu.agents.supervisor.plan_actions", return_value=None):
        Supervisor(gw, store).escalate(e)
    prompt = gw.prompts[0][-1]["content"]
    assert e.summary_tr in prompt
    assert NO_DESCRIPTION_NOTE not in prompt


def test_escalation_message_carries_the_real_episode_id():
    """26 Ağustos canlı koşusu: İSG çağrıları uydurma `episode_id` ile
    reddedildi çünkü model gerçek kimliği bilmiyordu. Doğru kimlik artık
    yükseltme mesajının içinde — modelin uydurmasına gerek kalmıyor."""
    gw, store, e = _setup([Response(content="haber"), Response(content="uygun")])
    with patch("gozcu.agents.supervisor.assess_risk", return_value=_risk(e)), \
         patch("gozcu.agents.supervisor.plan_actions", return_value=None):
        Supervisor(gw, store).escalate(e)
    prompt = gw.prompts[0][-1]["content"]
    assert f"(episode_id): {e.id}" in prompt


def test_an_escalation_is_stamped_at_the_moment_it_fires_not_the_events_start():
    """26 Ağustos koşusu: bir epizot 00:40'ta açıldı ve 01:16'ya kadar sürdü.
    Dört yükseltmenin 18 araç çağrısının HEPSİ 00:40 damgası taşıyordu, çünkü
    `escalate` saati olayın BAŞINA kuruyordu. Defterdeki "ne zaman" sorusunun
    anlamlı cevabı, ajanın davrandığı andır."""
    gw, store, _ = _setup([Response(content="haber"), Response(content="uygun")])
    episode = Episode(start_ts=40.0, end_ts=76.0, phase="development",
                      summary_tr="olay sürüyor", preliminary_risk="Kritik")
    episode.id = store.create_episode(episode)

    nobetci = Supervisor(gw, store)
    with patch("gozcu.agents.supervisor.assess_risk",
               return_value=_risk(episode)), \
         patch("gozcu.agents.supervisor.plan_actions", return_value=None):
        nobetci.escalate(episode)

    assert nobetci.ts == 76.0, "ajan olayın başında değil, şu anda davranıyor"
    said = [t for t in store.dialogue() if t.role == "supervisor"]
    assert said[-1].ts == 76.0


def test_the_escalation_header_stamps_the_moment_it_fires_not_the_events_start():
    """`escalate()`'in modele yazdığı `[SİSTEM] MM:SS —` başlığı `self.ts`
    (video "şimdi"si) taşımalı, `episode.start_ts` değil. Sistem promptu
    modele MM:SS damgalarını YAZMASINI söylüyor — model bu başlıktaki yanlış
    saati örnek alıp operatöre olayın başlangıcını "şimdi" diye bildirebilir.
    00:00'da açılıp 00:19'da yükseltilen bir olayda başlık '00:19' değil
    '00:00' derse, defterdeki her aksiyon ve diyalog satırı 00:19 taşırken
    operatöre söylenen an 00:00 olur — aynı yalanın bir başka yüzü."""
    from gozcu.agents.orchestrator import mmss

    gw, store, _ = _setup([Response(content="haber"), Response(content="uygun")])
    episode = Episode(start_ts=0.0, end_ts=19.0, phase="development",
                      summary_tr="olay sürüyor", preliminary_risk="Kritik")
    episode.id = store.create_episode(episode)

    with patch("gozcu.agents.supervisor.assess_risk",
               return_value=_risk(episode)), \
         patch("gozcu.agents.supervisor.plan_actions", return_value=None):
        Supervisor(gw, store).escalate(episode)

    prompt = gw.prompts[0][-1]["content"]
    assert f"[SİSTEM] {mmss(19.0)} —" in prompt
    assert f"[SİSTEM] {mmss(0.0)} —" not in prompt


def test_an_episode_that_never_closed_still_gets_a_stamp():
    gw, store, _ = _setup([Response(content="haber"), Response(content="uygun")])
    episode = Episode(start_ts=40.0, phase="onset", summary_tr="açık",
                      preliminary_risk="Kritik")
    episode.id = store.create_episode(episode)
    nobetci = Supervisor(gw, store)
    with patch("gozcu.agents.supervisor.assess_risk",
               return_value=_risk(episode)), \
         patch("gozcu.agents.supervisor.plan_actions", return_value=None):
        nobetci.escalate(episode)
    assert nobetci.ts == 40.0


# --- arıza metni talk() hatırlatmasına olay tarifi olarak girmez (Görev 20) --

def test_the_open_episode_reminder_does_not_carry_a_fault_text():
    """`talk()` her turda açık olayı hatırlatıyor. Hatırlatma yedek özeti
    OLDUĞU GİBİ taşırsa arıza metni ("Sentez üretilemedi; ham gözlemler
    kayıtlı.") diyalog geçmişine bir olay tarifi gibi girer — tıpkı
    `escalate`'in `NO_DESCRIPTION_NOTE` ile önlediği uydurmanın aynısı, bu
    kez `talk()` üzerinden. Kimlik (episode id) hatırlatmada kalmalı; kaybolan
    yalnız uydurma tarif olmalı.
    """
    from gozcu.agents.supervisor import FALLBACK_REMINDER

    gw, store, _ = _setup([Response(content="tamam"), Response(content="uygun")])
    broken = Episode(start_ts=EPISODE_TS, phase="development",
                     summary_tr="Sentez üretilemedi; ham gözlemler kayıtlı.",
                     preliminary_risk="Orta", summary_source="fallback")
    broken.id = store.create_episode(broken)

    Supervisor(gw, store).talk("durum ne?")

    last_user_message = gw.prompts[0][-1]["content"]
    assert "Sentez üretilemedi" not in last_user_message
    assert "tarif üretilemedi" in last_user_message
    assert FALLBACK_REMINDER in last_user_message
    assert f"episode {broken.id}" in last_user_message


def test_a_real_open_episode_reminder_still_carries_its_summary_verbatim():
    gw, store, e = _setup([Response(content="tamam"), Response(content="uygun")])
    Supervisor(gw, store).talk("durum ne?")
    last_user_message = gw.prompts[0][-1]["content"]
    assert e.summary_tr in last_user_message


# -- planlayıcı zincire bağlı (Görev 5) --------------------------------------
#
# Nöbetçi bugüne kadar `proposed_actions`'ı HİÇ okumuyordu — `escalate`
# mesajı yalnız `risk.level` ve `risk.rationale_tr` taşıyordu, araç seçimini
# süpervizör kendi sezgisiyle yapıyordu. Plan mesaja girmezse yeni ajan
# yalnız kapanış raporunu ve besleme panelini besler, karar veren ajanı hiç
# etkilemez (spec §5).

def test_escalation_message_carries_the_plan(store, monkeypatch):
    """Plan yükseltme mesajına girmezse planlayıcı dekoratif kalır (spec §5)."""
    from gozcu.models import ActionPlan, ProposedAction

    episode = _episode(store)
    risk = _risk(episode)
    plan = ActionPlan(episode_id=episode.id, risk_assessment_id=1, ts=10.0,
                      protocol_id="PRT-B-CARPMA",
                      rationale_tr="B-Hattı çarpma prosedürü geçerli.",
                      proposed_actions=[
                          ProposedAction(description_tr="B hattını durdur",
                                         tool_name="halt_production_line",
                                         params={"line_id": "B"})],
                      plan_source="model")
    plan.id = store.save_action_plan(plan)

    monkeypatch.setattr("gozcu.agents.supervisor.assess_risk",
                        lambda *a, **k: risk)
    monkeypatch.setattr("gozcu.agents.supervisor.plan_actions",
                        lambda *a, **k: plan)

    supervisor = Supervisor(_gw("Anlaşıldı."), store)
    supervisor.escalate(episode)

    system_turns = [m["content"] for m in supervisor.history
                    if m["role"] == "user" and "[SİSTEM]" in m["content"]]
    assert system_turns
    message = system_turns[-1]
    assert "PRT-B-CARPMA" in message
    assert "B hattını durdur" in message


def test_escalation_without_plan_still_speaks(store, monkeypatch):
    """Boş plan yükseltmeyi düşürmez — çıktı sözleşmesi her hâlükârda.

    Yalnız "bir şey döndü" demek yetmez: mesajın gerçekten `NO_PLAN_LINE`
    taşıdığı da doğrulanmalı, yoksa bu test plan satırının hiç yazılmadığı
    bir regresyonu da yeşil geçirir.
    """
    from gozcu.models import ActionPlan

    episode = _episode(store)
    risk = _risk(episode)
    plan = ActionPlan(episode_id=episode.id, risk_assessment_id=1, ts=10.0,
                      protocol_id=None, rationale_tr="prosedür yok",
                      proposed_actions=[], plan_source="empty")
    monkeypatch.setattr("gozcu.agents.supervisor.assess_risk",
                        lambda *a, **k: risk)
    monkeypatch.setattr("gozcu.agents.supervisor.plan_actions",
                        lambda *a, **k: plan)
    supervisor = Supervisor(_gw("Anlaşıldı."), store)
    assert supervisor.escalate(episode)

    system_turns = [m["content"] for m in supervisor.history
                    if m["role"] == "user" and "[SİSTEM]" in m["content"]]
    assert NO_PLAN_LINE in system_turns[-1]


# -- güncelleme kipinde plan satırı imperatif OLMAMALI (fix turu 1) ---------
#
# Controller ruling 8: PLAN_LINE'ın "bu öneriyi operatöre sun ve onay iste"
# emri, güncelleme mesajında UPDATE_INSTRUCTION'ın hemen üstünde duruyordu
# ve UPDATE_INSTRUCTION'ın "aynı aracı aynı gerekçeyle TEKRAR ÇAĞIRMA"
# talimatıyla doğrudan çelişiyordu. Bu, 26 Ağustos'un "yükseltme fırtınası"
# arızasıyla AYNI SINIF: bir olay 6 kez yükseltilip 18 saha çağrısı üretmişti
# çünkü her yükseltme modele "yeniden aksiyon öner" diyordu.

def test_the_plan_line_is_imperative_on_first_escalation_but_a_recap_on_update(
        store, monkeypatch):
    """İlk yükseltme hâlâ "öner ve onay iste" diyebilir — orada tam
    müdahale gerçekten isteniyor. Aynı olayın İKİNCİ (güncelleme)
    yükseltmesinde plan satırı asla bu emri taşımamalı."""
    from gozcu.models import ActionPlan, ProposedAction

    episode = _episode(store)
    risk = _risk(episode)
    plan = ActionPlan(episode_id=episode.id, risk_assessment_id=1, ts=10.0,
                      protocol_id="PRT-B-CARPMA",
                      rationale_tr="B-Hattı çarpma prosedürü geçerli.",
                      proposed_actions=[
                          ProposedAction(description_tr="B hattını durdur",
                                         tool_name="halt_production_line",
                                         params={"line_id": "B"})],
                      plan_source="model")

    def _fake_assess(*_a, **_k):
        risk.id = store.save_risk(risk)
        return risk

    def _fake_plan(*_a, **_k):
        plan.id = store.save_action_plan(plan)
        return plan

    monkeypatch.setattr("gozcu.agents.supervisor.assess_risk", _fake_assess)
    monkeypatch.setattr("gozcu.agents.supervisor.plan_actions", _fake_plan)

    supervisor = Supervisor(_gw("Anlaşıldı."), store)
    supervisor.escalate(episode)          # ilk: tam müdahale
    supervisor.escalate(episode)          # ikinci: gelişme kipi

    system_turns = [m["content"] for m in supervisor.history
                    if m["role"] == "user" and "[SİSTEM]" in m["content"]]
    assert len(system_turns) == 2, "iki yükseltme, iki [SİSTEM] turu bekleniyor"
    first_message, update_message = system_turns

    # İlk yükseltme: imperatif kalmalı.
    assert "B hattını durdur" in first_message
    assert "onay iste" in first_message

    # Güncelleme: aynı öneriyi tekrar SUNMA/ONAY İSTEME emri OLMAMALI —
    # UPDATE_INSTRUCTION'ın "TEKRAR ÇAĞIRMA" talimatıyla çelişirdi.
    assert "onay iste" not in update_message
    assert "Bu öneriyi" not in update_message
    # Güncelleme "Uygulanan" DEMEMELİ — araç çağrılmamış olabilir (Ruling 10).
    assert "Uygulanan" not in update_message
    assert "önerilen" in update_message.lower()

    # tool_name ve params plan satırında görünmeli (spec §2b).
    assert "halt_production_line" in first_message
    assert "line_id" in first_message
