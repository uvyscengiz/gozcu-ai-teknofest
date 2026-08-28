"""Görev 11 — risk analisti.

Analistin iki iddiası test ediliyor: **gerçekten araştırıyor** (okuma
araçlarını aksiyon defteri üzerinden çağırıyor) ve **her önerisi gerçek bir
araca bağlı**. İkisi de sahte bir cümleyle taklit edilebilir; testler o yüzden
defterin ve modele giden mesajların içine bakıyor.
"""

import json
from unittest.mock import Mock, patch

from gozcu.agents.risk import (DEGRADED_RATIONALE, MAX_RATIONALE, READ_TOOLS,
                               _prompt, assess_risk)
from gozcu.core.gateway import Response
from gozcu.core.models import Correction, Episode, EventBeat
from gozcu.core.store import Store

# `proposed_actions` YOK: öneri üretimi `action_planner`'ın işi (Görev 6,
# spec §2d). `_RiskResponse` bu alanı `extra="forbid"` ile reddediyor —
# burada varsa analiz sessizce yedeğe düşer.
RESPONSE_JSON = ('{"level":"Kritik","rationale_tr":"Yerde hareketsiz kişi var ve '
                 'aracın fren bakımı gecikmiş.","preventable":true}')

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
    """`search_timeline` artık `Precedent` döndürüyor.

    Yamanın `Episode` döndürdüğü gün `assess_risk` `AttributeError` atardı —
    emsal okuması `p.episode.summary_tr` ve etrafında `try` yok."""
    from gozcu.core.models import Precedent
    precedents = [e if isinstance(e, Precedent) else Precedent(episode=e, score=0.8)
                  for e in episodes]
    return patch("gozcu.agents.risk.search_timeline", return_value=precedents)


# -- öneriler artık burada değil ---------------------------------------------
#
# "Öneri gerçek bir araca bağlı" ve "uydurma araç adı düşürülür" testleri
# `action_planner`'a taşındı (Görev 6, spec §2d) — bkz.
# `tests/test_action_planner.py::test_invented_tool_name_is_dropped` ve
# `test_all_invented_actions_collapse_to_an_empty_plan`. Analist artık hiçbir
# `proposed_actions` süzgeci taşımıyor.


# -- arşiv --------------------------------------------------------------------

def test_analysis_consults_the_archive_and_excludes_the_episode_itself():
    """Dışlama düşerse epizot kendi emsali olarak listenin başına çıkar.

    Dışlama bir **çift**: tek bir `episode_id` farklı videoların aynı numaralı
    epizotlarını da elerdi — nokta kimliği artık `source`'u içeriyor."""
    store = Store(":memory:")
    e = _ep(store)
    prior = Episode(start_ts=0.0, phase="outcome",
                    summary_tr="12 Ağustos gecesi aynı istif aracının freni tuttu",
                    preliminary_risk="Orta")
    gw = _gw()
    with _archive_patch([prior]) as search:
        assess_risk(gw, store, e)
    search.assert_called_once()
    assert search.call_args.kwargs["exclude"] == (e.source, e.id)
    assert prior.summary_tr in _text(gw)


def test_the_assessment_records_the_precedents_it_consulted():
    """Emsal yalnız prompt'a giriyordu ve jüri prompt görmez (B6)."""
    from gozcu.core.models import Precedent
    past = Precedent(
        episode=Episode(id=9, start_ts=0.0, phase="outcome",
                        summary_tr="IST-04 fren mesafesi uzadı",
                        preliminary_risk="Orta", source="arşiv:OLY-2026-0812",
                        occurred_at="2026-08-12T23:41:00+03:00",
                        equipment_ids=["IST-04"]),
        score=0.71)
    store = Store(":memory:")
    with _archive_patch([past]):
        assessment = assess_risk(_gw(), store, _ep(store))
    assert [p.episode.summary_tr for p in assessment.precedents] == [
        "IST-04 fren mesafesi uzadı"]
    assert assessment.precedents[0].score == 0.71


def test_an_assessment_without_precedents_records_an_empty_list():
    store = Store(":memory:")
    with _archive_patch([]):
        assessment = assess_risk(_gw(), store, _ep(store))
    assert assessment.precedents == []


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
    now = e.end_ts or e.start_ts
    assert record.ts == now, "defter damgası videonun ŞİMDİsi (spec §6)"
    assessment = store.risks()[-1]
    assert assessment.ts == now
    # `assess_risk` artık hiçbir devir yazmıyor (Görev 6) — devir zinciri
    # `action_planner._save`'e taşındı, bkz.
    # `test_assessment_is_persisted_without_writing_its_own_handoff`.
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


# `test_the_urgency_vocabulary_reaches_the_model_byte_identically` TAŞINDI:
# `dispatch_medical` gibi müdahale araçlarının şeması artık analistin
# promptunda yok — o sözlük `action_planner`'da kuruluyor. Aynı garanti bkz.
# `tests/test_action_planner.py::test_the_urgency_vocabulary_reaches_the_model_byte_identically`.


# `test_the_prompt_catalogue_names_every_registered_tool` KALDIRILDI:
# `TOOL_CATALOGUE` risk.py'den silindi (Görev 6) — katalog artık yalnız
# `action_planner`ın promptunda kuruluyor, kendi (inline) hâliyle; onu
# ayrı bir sembol olarak dışa açmıyor, o yüzden taşınacak bir sembol yok.


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


# `test_an_overlong_action_description_is_truncated_too` TAŞINDI:
# `action_planner`in kendi `MAX_ACTION_DESCRIPTION` kesmesi var; bkz.
# `tests/test_action_planner.py::test_an_overlong_action_description_is_truncated_too`.


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


def test_assessment_is_persisted_without_writing_its_own_handoff():
    """`assess_risk` artık HİÇBİR devir yazmıyor (Görev 6, spec §2d):
    zincirdeki bir sonraki durak `action_planner` ve o deviri
    `action_planner._save` yazıyor (`risk_analyst → action_planner` ve
    `action_planner → supervisor`). İkisi birden yazılsaydı aynı andan iki
    kenar çıkardı."""
    store = Store(":memory:")
    with _archive_patch():
        assess_risk(_gw(), store, _ep(store))
    assert len(store.risks()) == 1
    assert store.handoffs() == []


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


def test_the_analyst_asks_with_its_own_generous_ceiling():
    """`main` kademesi şemalı JSON'da uzun akıl yürütme izi üretiyor.

    Ölçüldü (26 Ağu, canlı): KÜÇÜK bir sentez isteminde bile 4675-8513
    token harcadı ve bir denemede 8192 tavanını tüketip BOŞ döndü. Risk
    istemi ondan büyük (olay + arşiv + düzeltmeler), yani varsayılan tavanla
    değerlendirme sessizce yedeğe düşebilir — `risk` şartnamenin puanlanan
    dört anahtarından biri. Raportör aynı sebeple kendi tavanını taşıyor.
    """
    from unittest.mock import Mock
    from gozcu.agents.risk import RISK_MAX_TOKENS, assess_risk
    from gozcu.core.models import Episode
    from gozcu.core.store import Store

    assert RISK_MAX_TOKENS > 8192

    store = Store(":memory:")
    episode = Episode(start_ts=0.0, end_ts=10.0, phase="development",
                      summary_tr="Forklift devrildi.", preliminary_risk="Yüksek")
    episode.id = store.create_episode(episode)

    gw = Mock()
    gw.ask.return_value = Mock(degraded=False, tool_calls=[], content="")
    gw.embed.return_value = []
    assess_risk(gw, store, episode)
    assert gw.ask.call_args.kwargs.get("max_tokens") == RISK_MAX_TOKENS


# -- daraltma sözleşmesi (Görev 6) -------------------------------------------

def test_assessment_no_longer_carries_actions():
    """İki ajanın işi tek kayıtta durmamalı (spec §2d)."""
    import pytest
    from pydantic import ValidationError
    from gozcu.core.models import RiskAssessment
    with pytest.raises(ValidationError):
        RiskAssessment(episode_id=1, ts=1.0, level="Yüksek",
                       rationale_tr="x", preventable=True,
                       proposed_actions=[])


def test_risk_prompt_no_longer_lists_intervention_tools():
    """Katalog planlayıcıya taşındı; analistte kalırsa iki ajan aynı işi yapar."""
    from gozcu.agents.risk import SYSTEM_PROMPT
    assert "halt_production_line" not in SYSTEM_PROMPT
    assert "dispatch_medical" not in SYSTEM_PROMPT


def test_risk_levels_still_verbatim_in_prompt():
    """Daraltma sırasında enum/prompt eşleşmesine DOKUNULMAZ (CLAUDE.md)."""
    from typing import get_args
    from gozcu.agents.risk import SYSTEM_PROMPT
    from gozcu.core.models import RiskLevel
    for value in get_args(RiskLevel):
        assert f'"{value}"' in SYSTEM_PROMPT or value in SYSTEM_PROMPT
