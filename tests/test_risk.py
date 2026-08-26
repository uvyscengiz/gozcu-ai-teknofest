"""Görev 11 — risk analisti.

Analistin iki iddiası test ediliyor: **gerçekten araştırıyor** (okuma
araçlarını aksiyon defteri üzerinden çağırıyor) ve **her önerisi gerçek bir
araca bağlı**. İkisi de sahte bir cümleyle taklit edilebilir; testler o yüzden
defterin ve modele giden mesajların içine bakıyor.
"""

import json
from unittest.mock import Mock, patch

from gozcu.agents.risk import (DEGRADED_RATIONALE, MAX_ACTION_DESCRIPTION,
                               MAX_RATIONALE, READ_TOOLS, TOOL_CATALOGUE,
                               _prompt, assess_risk)
from gozcu.gateway import Response
from gozcu.models import Correction, Episode, EventBeat
from gozcu.store import Store
from gozcu.tools import field_systems
from gozcu.tools.registry import TOOLS

RESPONSE_JSON = ('{"level":"Kritik","rationale_tr":"Yerde hareketsiz kişi var ve '
                 'aracın fren bakımı gecikmiş.","preventable":true,'
                 '"proposed_actions":[{"description_tr":"Sağlık ekibini çağır",'
                 '"tool_name":"dispatch_medical",'
                 '"params":{"location":"B-Hattı","urgency":"critical"}}]}')

EPISODE_TS = 192.5


def _ep(store, participants=("IST-04", "PRS-001")):
    e = Episode(start_ts=EPISODE_TS, end_ts=EPISODE_TS + 20, phase="development",
                summary_tr="araç devrildi", participants=list(participants),
                preliminary_risk="Yüksek")
    e.id = store.create_episode(e)
    return e


def _fallback_episode(store):
    episode = Episode(
        start_ts=30.0, end_ts=45.0, phase="development",
        summary_tr="Sentez üretilemedi; ham gözlemler kayıtlı.",
        preliminary_risk="Orta", summary_source="fallback",
        beats=[EventBeat(ts=35.0, text="Forklift kamyona temas etti.")])
    episode.id = store.create_episode(episode)
    return episode


def _gw(content=RESPONSE_JSON, **kw):
    gw = Mock()
    gw.ask.return_value = Response(content=content, **kw)
    return gw


def _tool_call(name, **params):
    return {"id": f"call_{name}", "type": "function",
            "function": {"name": name, "arguments": json.dumps(params)}}


def _investigating_gw(*calls, final=RESPONSE_JSON):
    """İlk yanıt araç çağırır, ikincisi nihai değerlendirmeyi verir."""
    gw = Mock()
    gw.ask.side_effect = [Response(tool_calls=list(calls)),
                          Response(content=final)]
    return gw


def _messages(gw, index=-1):
    return gw.ask.call_args_list[index].args[1]


def _text(gw, index=-1):
    return "\n".join(str(m.get("content")) for m in _messages(gw, index))


def _archive_patch(episodes=()):
    return patch("gozcu.agents.risk.search_timeline", return_value=list(episodes))


# -- öneriler gerçek araçlara bağlı -----------------------------------------

def test_only_actions_bound_to_registered_tools_reach_the_supervisor():
    """Süzgeç silinirse uydurma araç da geçer — o yüzden liste karışık."""
    invented = json.loads(RESPONSE_JSON)
    invented["proposed_actions"].append(
        {"description_tr": "Helikopter gönder", "tool_name": "send_helicopter",
         "params": {}})
    store = Store(":memory:")
    with _archive_patch():
        r = assess_risk(_gw(json.dumps(invented)), store, _ep(store))
    assert [a.tool_name for a in r.proposed_actions] == ["dispatch_medical"]
    assert all(a.tool_name in TOOLS for a in r.proposed_actions)


def test_invented_tool_names_are_dropped_not_passed_through():
    bad = RESPONSE_JSON.replace("dispatch_medical", "send_helicopter")
    store = Store(":memory:")
    with _archive_patch():
        r = assess_risk(_gw(bad), store, _ep(store))
    assert r.proposed_actions == []


# -- arşiv --------------------------------------------------------------------

def test_analysis_consults_the_archive_and_excludes_the_episode_itself():
    """`exclude_id` düşerse epizot kendi emsali olarak listenin başına çıkar
    (Görev 08). Arşiv metni de gerçekten modele gitmeli."""
    store = Store(":memory:")
    e = _ep(store)
    prior = Episode(start_ts=0.0, phase="outcome",
                    summary_tr="12 Ağustos gecesi aynı istif aracının freni tuttu",
                    preliminary_risk="Orta")
    gw = _gw()
    with _archive_patch([prior]) as search:
        assess_risk(gw, store, e)
    search.assert_called_once()
    assert search.call_args.kwargs["exclude_id"] == e.id
    assert prior.summary_tr in _text(gw)


# -- yedek özet karantinası ---------------------------------------------------

def test_a_fallback_summary_is_not_presented_as_the_event():
    store = Store(":memory:")
    episode = _fallback_episode(store)
    text = _prompt(episode, "- (kayıt yok)", "")
    assert "Sentez üretilemedi" not in text
    assert "olay tarifi üretilemedi" in text
    assert "00:35" in text  # ham anlar prompta girdi


def test_the_archive_is_not_searched_with_a_fault_text(monkeypatch):
    store = Store(":memory:")
    episode = _fallback_episode(store)
    queries = []
    monkeypatch.setattr("gozcu.agents.risk.search_timeline",
                        lambda gw, store, q, **kw: queries.append(q) or [])
    assess_risk(_gw(), store, episode)
    assert all("Sentez üretilemedi" not in q for q in queries)


def test_a_beatless_fallback_does_not_promise_moments_it_cannot_show():
    """`beats` boşsa (yorumlama hiç çalışmadıysa) "aşağıdaki ham anlara
    dayan" demek tutulmayan bir vaattir — arıza metnini geri getirmeden de
    yalan söylenebilir."""
    store = Store(":memory:")
    episode = _fallback_episode(store)
    episode.beats = []
    text = _prompt(episode, "- (kayıt yok)", "")
    assert "aşağıdaki ham anlara dayan" not in text
    assert "Sentez üretilemedi" not in text


def test_the_archive_is_not_searched_when_a_fallback_has_neither_beats_nor_participants(monkeypatch):
    store = Store(":memory:")
    episode = _fallback_episode(store)
    episode.beats = []
    episode.participants = []

    def _fail(*args, **kwargs):
        raise AssertionError("search_timeline aranmamalıydı — ne an ne katılımcı var")

    monkeypatch.setattr("gozcu.agents.risk.search_timeline", _fail)
    assess_risk(_gw(), store, episode)


# -- araştırma: okuma araçları ------------------------------------------------

def test_the_analyst_is_offered_read_tools_only():
    """Analiz bir yan etkiyle hat durduramaz; müdahale Görev 14'ün onay
    akışına ait."""
    store = Store(":memory:")
    gw = _gw()
    with _archive_patch():
        assess_risk(gw, store, _ep(store))
    offered = {s["function"]["name"]
               for s in gw.ask.call_args_list[0].kwargs["tools"]}
    assert offered == set(READ_TOOLS)
    assert "halt_production_line" not in offered
    assert "dispatch_medical" not in offered


def test_the_analyst_reaches_the_overdue_maintenance_figure_through_the_ledger():
    """Dört aylık gecikme hiçbir arşiv cümlesinde yazmıyor —
    `query_equipment_history` çağrılmadan ulaşılamaz."""
    store = Store(":memory:")
    e = _ep(store)
    gw = _investigating_gw(_tool_call("query_equipment_history",
                                      equipment_id="IST-04"))
    with _archive_patch():
        r = assess_risk(gw, store, e)
    record = next(a for a in store.actions()
                  if a.tool_name == "query_equipment_history")
    assert record.result["overdue_maintenance_months"] == 4
    assert record.ts == e.start_ts == EPISODE_TS
    assert record.actor == "agent" and record.approval == "not_required"
    assert "overdue_maintenance_months" in _text(gw)
    assert gw.ask.call_count == 2
    assert r.level == "Kritik"


def test_the_equipment_id_comes_from_the_episode_participants():
    """Model kimliği tahmin etmiyor: epizodun taşıdığı kararlı kimlikler
    modele veriliyor."""
    store = Store(":memory:")
    gw = _gw()
    with _archive_patch():
        assess_risk(gw, store, _ep(store))
    assert "IST-04" in _text(gw) and "PRS-001" in _text(gw)


def test_a_write_tool_call_is_refused_and_never_reaches_the_ledger():
    store = Store(":memory:")
    gw = _investigating_gw(_tool_call("halt_production_line", line_id="B-Hattı",
                                      rationale="devrilme"))
    with _archive_patch():
        r = assess_risk(gw, store, _ep(store))
    assert [a.tool_name for a in store.actions()] == []
    assert "refused" in _text(gw)
    assert r.level == "Kritik"


def test_an_unknown_tool_name_is_refused_instead_of_raising():
    store = Store(":memory:")
    gw = _investigating_gw(_tool_call("send_helicopter"))
    with _archive_patch():
        r = assess_risk(gw, store, _ep(store))
    assert store.actions() == []
    assert r.level == "Kritik"


def test_a_model_that_calls_nothing_still_gets_one_assessment():
    """Araç fazı isteğe bağlı — çağrı yoksa ikinci tur hiç yapılmaz."""
    store = Store(":memory:")
    gw = _gw()
    with _archive_patch():
        r = assess_risk(gw, store, _ep(store))
    assert gw.ask.call_count == 1
    assert r.level == "Kritik"


# -- şema ile promptun tek sözlüğü -------------------------------------------

def test_the_urgency_vocabulary_reaches_the_model_byte_identically():
    """`URGENCY_LEVELS` prompta şemadan türetilerek giriyor; Türkçe bir
    aciliyet değeri `unrecognised_urgency` ile deftere gürültü bırakırdı."""
    store = Store(":memory:")
    gw = _gw()
    with _archive_patch():
        assess_risk(gw, store, _ep(store))
    system_text = _messages(gw)[0]["content"]
    for value in field_systems.URGENCY_LEVELS:
        assert f'"{value}"' in system_text
    assert '"kritik"' not in system_text  # check-tasks: allow-tr
    assert '"acil"' not in system_text  # check-tasks: allow-tr


def test_the_prompt_catalogue_names_every_registered_tool():
    for name in TOOLS:
        assert name in TOOL_CATALOGUE


# -- doğrulamadan önce temizleme ---------------------------------------------

def test_an_overlong_rationale_is_truncated_not_collapsed_into_the_fallback():
    """`maxLength` tele çıkmıyor (Görev 06); ham doğrulama gerçek bir analizi
    kabuğa çevirirdi."""
    payload = json.loads(RESPONSE_JSON)
    payload["rationale_tr"] = "Gerekçe cümlesi. " * 120
    store = Store(":memory:")
    with _archive_patch():
        r = assess_risk(_gw(json.dumps(payload)), store, _ep(store))
    assert len(r.rationale_tr) <= MAX_RATIONALE
    assert r.rationale_tr.startswith("Gerekçe cümlesi.")
    assert r.level == "Kritik"


def test_an_overlong_action_description_is_truncated_too():
    """Kesme iç içe `proposed_actions` içinde de yürümeli; yürümezse tek uzun
    öneri bütün değerlendirmeyi düşürür."""
    payload = json.loads(RESPONSE_JSON)
    payload["proposed_actions"][0]["description_tr"] = "Sağlık ekibini çağır. " * 30
    store = Store(":memory:")
    with _archive_patch():
        r = assess_risk(_gw(json.dumps(payload)), store, _ep(store))
    assert r.proposed_actions, "uzun açıklama öneriyi düşürmemeli"
    assert len(r.proposed_actions[0].description_tr) <= MAX_ACTION_DESCRIPTION
    assert r.level == "Kritik"


# -- operatör düzeltmesi, kalıcılık, bozulma ---------------------------------

def test_operator_corrections_reach_the_prompt():
    store = Store(":memory:")
    e = _ep(store)
    store.save_correction(Correction(ts=1.0, episode_id=e.id, field="event_type",
                                     old="araç devrildi", new="yük düştü",
                                     rationale="operatör gözlemi"))
    gw = _gw()
    with _archive_patch():
        assess_risk(gw, store, e)
    prompt_text = _messages(gw)[-1]["content"]
    assert "yük düştü" in prompt_text and "araç devrildi" in prompt_text


def test_assessment_is_persisted_with_a_handoff_to_the_supervisor():
    store = Store(":memory:")
    with _archive_patch():
        assess_risk(_gw(), store, _ep(store))
    assert len(store.risks()) == 1
    assert store.handoffs()[-1].target_agent == "supervisor"
    assert store.handoffs()[-1].source_agent == "risk_analyst"


def test_degraded_tier_keeps_the_preliminary_risk_instead_of_crashing():
    """Bozulmuş yanıt bir gün geçerli bir gövde taşırsa (bayat önbellek) o
    gövde canlı analiz gibi kaydedilmemeli — `degraded` guard'ı bu yüzden
    açık, `json.loads("")`'ın tesadüfen patlamasına güvenilmiyor."""
    store = Store(":memory:")
    e = _ep(store)
    gw = Mock()
    gw.ask.return_value = Response(content=RESPONSE_JSON, degraded=True)
    with _archive_patch():
        r = assess_risk(gw, store, e)
    assert r.level == e.preliminary_risk
    assert r.proposed_actions == []
    assert r.rationale_tr == DEGRADED_RATIONALE
    assert store.risks()[-1].rationale_tr == DEGRADED_RATIONALE


def test_unreadable_content_is_distinguishable_from_a_dead_tier():
    store = Store(":memory:")
    e = _ep(store)
    with _archive_patch():
        r = assess_risk(_gw("bu JSON değil"), store, e)
    assert r.level == e.preliminary_risk
    assert r.rationale_tr != DEGRADED_RATIONALE


def test_the_analysts_own_calls_are_stamped_with_its_name():
    """Bu çağrılar `Supervisor.escalate` İÇİNDE, süpervizör daha ağzını
    açmadan deftere düşüyor. `caller` olmadan besleme hepsini süpervizöre
    yazıyordu — şartname §7'nin puanladığı zincir hakkında yalan."""
    store = Store(":memory:")
    gw = _investigating_gw(_tool_call("query_shift_personnel", zone="B-Hattı",
                                      at_time="03:12"))
    with _archive_patch():
        assess_risk(gw, store, _ep(store))

    called = store.actions()
    assert [a.tool_name for a in called] == ["query_shift_personnel"]
    assert called[0].actor == "agent"
    assert called[0].caller == "risk_analyst"
