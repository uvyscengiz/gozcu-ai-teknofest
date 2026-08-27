"""Karar & Aksiyon ajanı — protokol seçici (spec §2).

İki turlu araç deseni (spec §2e, controller ruling 3): planlayıcıya sunulan
iki okuma aracından biri çağrılırsa gerçekten çalışmalı ve nihai plan İKİNCİ
bir model turundan gelmeli — `risk.py::assess_risk`'in aynı deseni. Yazma
aracı çağrısı ise çalıştırılmadan reddedilmeli.
"""
import json
from unittest.mock import Mock

import pytest

from gozcu.agents.action_planner import plan_actions
from gozcu.gateway import Response
from gozcu.models import Episode, RiskAssessment
from gozcu.store import Store
from gozcu.tools.registry import TOOLS


@pytest.fixture
def store():
    return Store()


def _gw(content: str, degraded: bool = False):
    """Tek yanıtlık sahte ağ geçidi — `tests/test_risk.py` deseni."""
    class _Response:
        def __init__(self):
            self.content = content
            self.degraded = degraded
            self.tool_calls = []
    class _GW:
        def ask(self, *args, **kwargs):
            return _Response()
    return _GW()


def _episode(store, event_class="çarpma", zone_id="line_b") -> Episode:
    episode = Episode(start_ts=0.0, end_ts=10.0, phase="outcome",
                      summary_tr="İstif aracı raf ayağına çarptı.",
                      participants=["IST-04", "PRS-001"],
                      preliminary_risk="Yüksek", state="closed",
                      event_class=event_class, zone_id=zone_id)
    episode.id = store.create_episode(episode)
    return episode


def _assessment(store, episode, level="Yüksek") -> RiskAssessment:
    assessment = RiskAssessment(episode_id=episode.id, ts=10.0, level=level,
                                rationale_tr="Ağır yaralanma riski.",
                                preventable=True)
    assessment.id = store.save_risk(assessment)
    return assessment


def test_plan_binds_actions_to_selected_protocol(store):
    episode = _episode(store)
    assessment = _assessment(store, episode)
    payload = json.dumps({
        "protocol_id": "PRT-B-CARPMA",
        "rationale_tr": "B-Hattı çarpma prosedürü geçerli.",
        "proposed_actions": [
            {"description_tr": "B hattını durdur",
             "tool_name": "halt_production_line",
             "params": {"line_id": "B", "rationale": "çarpma"}},
            {"description_tr": "Sağlık ekibini çağır",
             "tool_name": "dispatch_medical",
             "params": {"location": "line_b", "urgency": "critical"}},
        ]})
    plan = plan_actions(_gw(payload), store, episode, assessment)
    assert plan.protocol_id == "PRT-B-CARPMA"
    assert plan.plan_source == "model"
    assert [a.tool_name for a in plan.proposed_actions] == [
        "halt_production_line", "dispatch_medical"]


def test_unreadable_response_falls_back_to_protocol_steps(store):
    """Model susarsa protokolün adımları BİREBİR plana yazılır (spec §2f)."""
    episode = _episode(store)
    assessment = _assessment(store, episode)
    plan = plan_actions(_gw("bu JSON değil"), store, episode, assessment)
    assert plan.plan_source == "protocol_fallback"
    assert plan.protocol_id == "PRT-B-CARPMA"
    assert plan.proposed_actions, "yedek boş plan üretmemeli"
    assert all(a.tool_name in TOOLS for a in plan.proposed_actions)


def test_no_matching_protocol_yields_empty_plan(store):
    """Eşleşen protokol yoksa plan BOŞ — uydurulmuş bir plan değil."""
    episode = _episode(store, event_class="rutin", zone_id="yard")
    assessment = _assessment(store, episode, level="Düşük")
    plan = plan_actions(_gw("bu JSON değil"), store, episode, assessment)
    assert plan.plan_source == "empty"
    assert plan.proposed_actions == []
    assert plan.protocol_id is None
    assert plan.rationale_tr, "sebep yazılmalı"


def test_invented_tool_name_is_dropped(store):
    episode = _episode(store)
    assessment = _assessment(store, episode)
    payload = json.dumps({
        "protocol_id": "PRT-B-CARPMA", "rationale_tr": "gerekçe",
        "proposed_actions": [
            {"description_tr": "helikopter çağır",
             "tool_name": "dispatch_helicopter", "params": {}},
            {"description_tr": "Sağlık ekibini çağır",
             "tool_name": "dispatch_medical", "params": {}},
        ]})
    plan = plan_actions(_gw(payload), store, episode, assessment)
    assert [a.tool_name for a in plan.proposed_actions] == ["dispatch_medical"]


def test_invented_protocol_id_is_rejected(store):
    """Model aday listesinde OLMAYAN bir protokol uydurursa reddedilir."""
    episode = _episode(store)
    assessment = _assessment(store, episode)
    payload = json.dumps({
        "protocol_id": "PRT-UYDURMA", "rationale_tr": "gerekçe",
        "proposed_actions": [{"description_tr": "Sağlık ekibini çağır",
                              "tool_name": "dispatch_medical", "params": {}}]})
    plan = plan_actions(_gw(payload), store, episode, assessment)
    assert plan.protocol_id is None


def test_planner_is_offered_only_read_tools(store):
    """Yazma araçları bu ajana KAPALI (spec §2e).

    Controller ruling 7: brief `<=` yazıyordu — `offered` boş kümeyken bile
    doğru çıkan, hiçbir şey kanıtlamayan bir karşılaştırma. Spec §2e planın
    metnine göre bağlayıcı: iki okuma aracı GERÇEKTEN sunulmalı, `==` bunu
    zorunlu kılıyor."""
    seen = {}

    class _GW:
        def ask(self, tier, messages, **kwargs):
            seen["tools"] = kwargs.get("tools", [])
            class _R:
                content = "bu JSON değil"
                degraded = False
                tool_calls = []
            return _R()

    episode = _episode(store)
    plan_actions(_GW(), store, episode, _assessment(store, episode))
    offered = {s["function"]["name"] for s in seen["tools"]}
    assert offered == {"query_shift_personnel", "query_equipment_history"}


def test_plan_is_persisted_and_handed_off(store):
    episode = _episode(store)
    assessment = _assessment(store, episode)
    plan_actions(_gw("bu JSON değil"), store, episode, assessment)
    assert len(store.action_plans()) == 1
    targets = [(h.source_agent, h.target_agent) for h in store.handoffs()]
    assert ("risk_analyst", "action_planner") in targets
    assert ("action_planner", "supervisor") in targets


def test_plan_timestamp_follows_video_clock(store):
    """Plan videonun anına yazılır, duvar saatine değil."""
    episode = _episode(store)
    assessment = _assessment(store, episode)
    plan = plan_actions(_gw("bu JSON değil"), store, episode, assessment)
    assert plan.ts == episode.end_ts


# -- controller ruling 3: iki turlu araç deseni ------------------------------
#
# Brief'in `plan_actions`'ı `tools=PLANNER_TOOL_SCHEMAS` sunuyordu ama bir
# araç çağrısı GELİRSE onu hiç çalıştırmıyordu — model çağırsa bile boş
# içerikle `protocol_fallback`'a düşerdi ve araç teklifi bir yalan olurdu.
# `risk.py::assess_risk`'in iki turlu deseni burada da geçerli: ilk yanıt
# araç çağırırsa çalıştır, sonuçları geri ver, İKİNCİ turu araçsız sor.

def _tool_call(name, **params):
    return {"id": f"call_{name}", "type": "function",
            "function": {"name": name, "arguments": json.dumps(params)}}


def _investigating_gw(*calls, final):
    """İlk yanıt araç çağırır, ikincisi nihai planı verir
    (bkz. `tests/test_risk.py::_investigating_gw`)."""
    gw = Mock()
    gw.ask.side_effect = [Response(tool_calls=list(calls)),
                          Response(content=final)]
    return gw


def test_tool_call_is_executed_and_triggers_a_second_gateway_round(store):
    """Okuma aracı çağrılırsa gerçekten çalışır, deftere `action_planner`
    olarak yazılır ve nihai plan ikinci turdan gelir."""
    episode = _episode(store)
    assessment = _assessment(store, episode)
    final = json.dumps({
        "protocol_id": "PRT-B-CARPMA", "rationale_tr": "gerekçe",
        "proposed_actions": [{"description_tr": "Sağlık ekibini çağır",
                              "tool_name": "dispatch_medical", "params": {}}]})
    gw = _investigating_gw(
        _tool_call("query_shift_personnel", zone="line_b", at_time="03:00"),
        final=final)

    plan = plan_actions(gw, store, episode, assessment)

    assert gw.ask.call_count == 2, "araç çağrısı ikinci bir tur doğurmalı"
    # Controller ruling 3'ün en kritik bekçisi: ikinci turda araç TEKRAR
    # sunulursa model sonsuza dek araştırabilir. Yalnız `call_count == 2`
    # bunu göremez — mutasyon testinde ikinci `gw.ask`'a `tools=` eklenip
    # bütün suit yeşil kaldı.
    assert "tools" not in gw.ask.call_args_list[1].kwargs, (
        "ikinci tur araçsız olmalı — yoksa model sonsuza dek araştırabilir")
    called = [a for a in store.actions()
             if a.tool_name == "query_shift_personnel"]
    assert len(called) == 1, "araç gerçekten çalıştırılmalı"
    assert called[0].caller == "action_planner", (
        "yanlış caller çağrıyı başka bir ajanın işi gibi deftere yazar")
    assert plan.plan_source == "model"


def test_tool_call_outside_the_allow_list_is_refused_not_executed(store):
    """Planlayıcının izin listesinde OLMAYAN bir araç (örn. bir müdahale
    aracı) çağrılırsa çalıştırılmaz — okuma araçlarıyla aynı kapı yok, ayrı
    ve daha dar bir izin listesi var."""
    episode = _episode(store)
    assessment = _assessment(store, episode)
    gw = _investigating_gw(
        _tool_call("halt_production_line", line_id="B", rationale="test"),
        final="bu JSON değil")

    plan_actions(gw, store, episode, assessment)

    assert gw.ask.call_count == 2
    assert "tools" not in gw.ask.call_args_list[1].kwargs, (
        "ikinci tur araçsız olmalı — yoksa model sonsuza dek araştırabilir")
    assert store.actions() == [], "reddedilen çağrı asla çalıştırılmamalı"
