"""Karar & Aksiyon ajanı — protokol seçici (spec §2).

İki turlu araç deseni (spec §2e, controller ruling 3): planlayıcıya sunulan
okuma aracı (`search_documents`) çağrılırsa gerçekten çalışmalı ve nihai plan
İKİNCİ bir model turundan gelmeli — `risk.py::assess_risk`'in aynı deseni.
Yazma aracı çağrısı ise çalıştırılmadan reddedilmeli.
"""
import json
from unittest.mock import Mock, patch

import pytest

from gozcu.agents.action_planner import MAX_ACTION_DESCRIPTION, plan_actions
from gozcu.core.gateway import Response
from gozcu.core.models import Episode, RiskAssessment
from gozcu.core.store import Store
from gozcu.tools import field_systems
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
    """Yazma araçları bu ajana KAPALI (spec §2e). Fixture araçları yerine
    search_documents sunuluyor."""
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
    assert offered == {"search_documents"}


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
    """Okuma aracı çağrılırsa GERÇEKTEN çalışır (`search_documents` fonksiyonu
    çağrılır) ve nihai plan ikinci turdan gelir.

    `search_documents` bir alan aksiyonu DEĞİL: `call_tool`'dan hiç geçmez,
    doğrudan Python fonksiyonu olarak çağrılır — bu yüzden beş kayıtlı
    aksiyon aracının aksine aksiyon defterine hiç yazmaz. `store.actions()`
    boş kalması bunun kanıtı; sadece "ikinci tur oldu" demek bunu göstermez,
    çünkü `search_documents` hiç çağrılmasa da (örn. yanlışlıkla `refused`
    dalına düşse) ikinci tur yine olurdu."""
    episode = _episode(store)
    assessment = _assessment(store, episode)
    final = json.dumps({
        "protocol_id": "PRT-B-CARPMA", "rationale_tr": "gerekçe",
        "proposed_actions": [{"description_tr": "Sağlık ekibini çağır",
                              "tool_name": "dispatch_medical", "params": {}}]})
    gw = _investigating_gw(
        _tool_call("search_documents", query="ekipman bakım"),
        final=final)

    with patch("gozcu.agents.action_planner.search_documents") as mock_search:
        mock_search.return_value = []
        plan = plan_actions(gw, store, episode, assessment)

    # `client=` GEÇİLMİYOR ve bu C-1'in kendisi: yazan yol
    # (`embed_document`, `POST /api/library/documents`) varsayılan belge
    # tutamağını kullanıyor; `client=store` okuyucuyu AYRI bir yerel
    # Qdrant'a bağlar ve arama sessizce boş döner.
    mock_search.assert_called_once_with(gw, "ekipman bakım")
    assert gw.ask.call_count == 2
    assert "tools" not in gw.ask.call_args_list[1].kwargs
    assert plan.plan_source == "model"
    assert store.actions() == [], (
        "search_documents bir alan aksiyonu değil — aksiyon defterine "
        "yazmamalı, beş kayıtlı aksiyon aracından farklı olarak")


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


# -- Görev 6: risk.py'den taşınan iddialar -----------------------------------
#
# Öneri üretimi ve araç kataloğu artık tamamen bu ajanın işi (spec §2d).
# `tests/test_risk.py`'nin eski "öneriler gerçek araçlara bağlı" ve "şema ile
# promptun tek sözlüğü" bölümlerindeki iddialar buraya taşındı, KISALTILMADAN.

def test_all_invented_actions_collapse_to_an_empty_plan(store):
    """Önerinin TAMAMI uydurma araç adı taşıyorsa plan boş listeye düşer.

    `tests/test_risk.py`'nin eski
    `test_invented_tool_names_are_dropped_not_passed_through`'unun taşınmış
    hâli — orada TEK öneri vardı ve o da uydurmaydı, bu yüzden karışık liste
    (`test_invented_tool_name_is_dropped`) değil, TAM boşalma test ediliyor.
    """
    episode = _episode(store)
    assessment = _assessment(store, episode)
    payload = json.dumps({
        "protocol_id": "PRT-B-CARPMA", "rationale_tr": "gerekçe",
        "proposed_actions": [
            {"description_tr": "Helikopter gönder",
             "tool_name": "send_helicopter", "params": {}}]})
    plan = plan_actions(_gw(payload), store, episode, assessment)
    assert plan.proposed_actions == []


def test_an_overlong_action_description_is_truncated_too(store):
    """Kesme iç içe `proposed_actions` içinde de yürümeli; yürümezse tek uzun
    öneri bütün planı doğrulama hatasına düşürür — ve kaybedilen şey öneri
    değil, planın tamamı olur.

    `tests/test_risk.py`'nin eski aynı adlı testinin taşınmış hâli.
    """
    episode = _episode(store)
    assessment = _assessment(store, episode)
    payload = json.dumps({
        "protocol_id": "PRT-B-CARPMA", "rationale_tr": "gerekçe",
        "proposed_actions": [
            {"description_tr": "Sağlık ekibini çağır. " * 30,
             "tool_name": "dispatch_medical", "params": {}}]})
    plan = plan_actions(_gw(payload), store, episode, assessment)
    assert plan.proposed_actions, "uzun açıklama öneriyi düşürmemeli"
    assert len(plan.proposed_actions[0].description_tr) <= MAX_ACTION_DESCRIPTION
    assert plan.plan_source == "model"


def _system_text(gw):
    return gw.ask.call_args_list[0].args[1][0]["content"]


def test_the_prompt_catalogue_names_every_registered_tool(store):
    """Analist artık bir katalog taşımıyor (Görev 6); onun yerini alan bu
    ajanın promptu bütün kayıtlı araçları saymalı.

    `tests/test_risk.py`'nin eski aynı adlı testinin taşınmış hâli.
    """
    episode = _episode(store)
    assessment = _assessment(store, episode)
    gw = Mock()
    gw.ask.return_value = Response(content="bu JSON değil")
    plan_actions(gw, store, episode, assessment)
    system_text = _system_text(gw)
    for name in TOOLS:
        assert name in system_text


def test_the_urgency_vocabulary_reaches_the_model_byte_identically(store):
    """`URGENCY_LEVELS` prompta şemadan türetilerek giriyor; Türkçe bir
    aciliyet değeri `unrecognised_urgency` ile deftere gürültü bırakırdı.

    `tests/test_risk.py`'nin eski aynı adlı testinin taşınmış hâli — o
    katalog artık burada kuruluyor.
    """
    episode = _episode(store)
    assessment = _assessment(store, episode)
    gw = Mock()
    gw.ask.return_value = Response(content="bu JSON değil")
    plan_actions(gw, store, episode, assessment)
    system_text = _system_text(gw)
    for value in field_systems.URGENCY_LEVELS:
        assert f'"{value}"' in system_text
    # Negatif yarı: doğru değerlerin HEPSİ orada olabilir VE yanlış bir
    # Türkçe benzeri de orada olabilir — pozitif döngü bunu yakalayamaz.
    # "kritik"/"acil" modelin Türkçe yazarken doğal olarak uzanacağı
    # sözcükler, tam da bu yüzden eski testte ayrı yazılmışlardı.
    assert '"kritik"' not in system_text  # check-tasks: allow-tr
    assert '"acil"' not in system_text  # check-tasks: allow-tr


# =============================================================================
# İstem biçimi ve ikiz imzalar (whole-branch review — Minör)
# =============================================================================

def test_the_system_prompt_has_no_dangling_blank_lines_without_documents():
    """M-2: kütüphane BOŞKEN (olağan hâl) istem iki boş satırla bitiyordu.

    `{doc_context}` şablonun sonunda çıplak duruyordu; boş dizeyle
    biçimlendirildiğinde modele giden sistem mesajı "- Sadece JSON
    döndür.\n\n" oluyordu. Belge varsa aradaki boş satır KALMALI —
    `supervisor._refresh_document_context`'in deseni.
    """
    from gozcu.agents.action_planner import SYSTEM_PROMPT

    empty = _render_system_prompt("")
    assert not empty.endswith("\n")
    assert empty.endswith("Sadece JSON döndür.")

    filled = _render_system_prompt("YÜKLÜ BELGELER:\n- talimat.md")
    assert filled.endswith("YÜKLÜ BELGELER:\n- talimat.md")
    assert "Sadece JSON döndür.\n\nYÜKLÜ BELGELER:" in filled


def _render_system_prompt(doc_context: str) -> str:
    """`plan_actions`'ın sistem mesajını KURDUĞU gibi kurar."""
    from gozcu.agents.action_planner import SYSTEM_PROMPT

    return SYSTEM_PROMPT.format(
        tools="- dispatch_medical: sağlık ekibi",
        doc_context=f"\n\n{doc_context}" if doc_context else "")


def test_the_two_tool_runners_are_twins_in_signature_too():
    """`ts` artık kullanılmıyor — ikizlerin biri onu taşıyor, diğeri değil.

    `action_planner._run_tool_calls` `ts` alıyor ve çağıranlar geçiriyordu,
    oysa `call_tool(..., ts=ts)` bu daldan önce silinmişti; `risk.py`'deki
    ikizi onu çoktan bıraktı. Docstring'ler ikisini "ikiz" diye anıyor,
    imzaları da öyle olmalı.
    """
    import inspect

    from gozcu.agents import action_planner, risk

    planner = inspect.signature(action_planner._run_tool_calls).parameters
    analyst = inspect.signature(risk._run_tool_calls).parameters

    assert "ts" not in planner
    assert list(planner)[:3] == list(analyst)[:3] == ["gw", "store", "calls"]
