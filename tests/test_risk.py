"""Görev 11 — risk analisti.

Analistin iki iddiası test ediliyor: **gerçekten araştırıyor** (okuma
araçlarını aksiyon defteri üzerinden çağırıyor) ve **her önerisi gerçek bir
araca bağlı**. İkisi de sahte bir cümleyle taklit edilebilir; testler o yüzden
defterin ve modele giden mesajların içine bakıyor.
"""

import json
from unittest.mock import Mock, patch

from gozcu.agents.risk import (DEGRADED_RATIONALE, MAX_RATIONALE, RISK_TOOLS,
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
#
# Arşiv artık `assess_risk` içinde otomatik aranmıyor: model `search_timeline`
# aracını KENDİ SEÇİMİYLE çağırırsa arama olur (§6b, §1e). Otomatik ön arama
# ve onun sonucundan `RiskAssessment.precedents` doldurma davranışı bu
# yeniden tasarımla kalktı — `assess_risk` artık `precedents=[]` yazıyor
# (jüri zaten prompt'u değil deftere düşen kaydı görüyor, B6). Bu bölümdeki
# testler o yüzden aracın KENDİSİNİ (dışlama, model tetiklemesi) doğruluyor.

def test_search_timeline_tool_call_excludes_the_episode_itself():
    """Dışlama düşerse epizot kendi emsali olarak listenin başına çıkar.

    Dışlama bir **çift**: tek bir `episode_id` farklı videoların aynı numaralı
    epizotlarını da elerdi — nokta kimliği artık `source`'u içeriyor. Bu
    yeniden tasarımda dışlama artık `_run_tool_calls` içinde kuruluyor,
    çünkü arama artık modelin çağırdığı bir araç."""
    store = Store(":memory:")
    e = _ep(store)
    gw = _investigating_gw(_tool_call("search_timeline", query="devrilme"))
    with _archive_patch([]) as search:
        assess_risk(gw, store, e)
    search.assert_called_once()
    assert search.call_args.kwargs["exclude"] == (e.source, e.id)


def test_an_assessment_without_precedents_records_an_empty_list():
    """Yeniden tasarımda `precedents` artık DAİMA boş — arama araç sonucu
    olarak modele dönüyor, deftere ayrı bir emsal listesi olarak değil."""
    store = Store(":memory:")
    with _archive_patch([]):
        assessment = assess_risk(_gw(), store, _ep(store))
    assert assessment.precedents == []


# -- yedek özet karantinası ---------------------------------------------------

def test_a_fallback_summary_is_not_presented_as_the_event():
    store = Store(":memory:")
    episode = _fallback_episode(store)
    text = _prompt(episode, "")
    assert "Sentez üretilemedi" not in text
    assert "olay tarifi üretilemedi" in text
    assert "00:35" in text  # ham anlar prompta girdi


def test_a_beatless_fallback_does_not_promise_moments_it_cannot_show():
    """`beats` boşsa (yorumlama hiç çalışmadıysa) "aşağıdaki ham anlara
    dayan" demek tutulmayan bir vaattir — arıza metnini geri getirmeden de
    yalan söylenebilir."""
    store = Store(":memory:")
    episode = _fallback_episode(store)
    episode.beats = []
    text = _prompt(episode, "")
    assert "aşağıdaki ham anlara dayan" not in text
    assert "Sentez üretilemedi" not in text


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
    assert offered == set(RISK_TOOLS)
    assert "halt_production_line" not in offered
    assert "dispatch_medical" not in offered


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


# -- 6-tur mekanizması (§1e, §6, §7a) ----------------------------------------
#
# `search_timeline` ve `search_documents` artık model aracı olarak
# çağrılıyor (registry'nin DIŞINDA, doğrudan Python çağrısı — bkz.
# `_run_tool_calls`). Döngü en fazla 6 tur sürer: ilk 5'i araçlı, 6.'sı
# YAPISAL OLARAK araçsız — model sonsuza dek araştırıp değerlendirmeyi hiç
# vermeme riskine karşı bir güvenlik ağı.

def test_risk_analyst_uses_search_timeline_as_a_tool():
    """§6b: search_timeline artık model aracı olarak çağrılır."""
    store = Store(":memory:")
    e = _ep(store)

    gw = _investigating_gw(
        _tool_call("search_timeline", query="devrilme"),
        final=RESPONSE_JSON)

    with _archive_patch([]):
        assessment = assess_risk(gw, store, e)

    assert gw.ask.call_count == 2
    assert assessment.level == "Kritik"


def test_risk_analyst_can_call_search_documents():
    """§1d: risk analisti search_documents aracını kullanabilir."""
    store = Store(":memory:")
    e = _ep(store)

    gw = _investigating_gw(
        _tool_call("search_documents", query="ekipman bakım"),
        final=RESPONSE_JSON)

    with _archive_patch([]):
        assessment = assess_risk(gw, store, e)

    assert gw.ask.call_count == 2
    assert assessment.level == "Kritik"


def test_risk_analyst_iterates_up_to_five_tool_rounds():
    """§1e: model 5 araç turu yapabilir, 6. tur araçsız."""
    store = Store(":memory:")
    e = _ep(store)

    responses = []
    for _ in range(5):
        responses.append(Response(
            tool_calls=[_tool_call("search_timeline", query="olay")]))
    responses.append(Response(content=RESPONSE_JSON))

    gw = Mock()
    gw.ask.side_effect = responses

    with _archive_patch([]):
        assessment = assess_risk(gw, store, e)

    assert gw.ask.call_count == 6
    assert assessment.level == "Kritik"


def test_risk_analyst_sixth_round_has_no_tools():
    """§1e: 6. tur (güvenlik ağı) araçsız — yapısal garanti."""
    store = Store(":memory:")
    e = _ep(store)

    responses = []
    for _ in range(5):
        responses.append(Response(
            tool_calls=[_tool_call("search_timeline", query="x")]))
    responses.append(Response(content=RESPONSE_JSON))

    gw = Mock()
    gw.ask.side_effect = responses

    with _archive_patch([]):
        assess_risk(gw, store, e)

    last_call = gw.ask.call_args_list[-1]
    assert "tools" not in last_call.kwargs, \
        "6. tur araçsız olmalı — güvenlik ağı"


def test_risk_analyst_early_exit_when_no_tool_called():
    """§1e: model araç çağırmazsa döngü biter, değerlendirme alınır."""
    store = Store(":memory:")
    e = _ep(store)

    gw = _gw(RESPONSE_JSON)
    with _archive_patch([]):
        assessment = assess_risk(gw, store, e)

    assert gw.ask.call_count == 1
    assert assessment.level == "Kritik"


def test_risk_analyst_prompt_has_no_archive_injection():
    """§7a: ARSIV: enjeksiyonu kaldırıldı — arşiv araç olarak erişilir."""
    store = Store(":memory:")
    e = _ep(store)

    gw = _gw(RESPONSE_JSON)
    with _archive_patch([]):
        assess_risk(gw, store, e)

    prompt_text = _text(gw, 0)
    assert "ARŞİV:" not in prompt_text
    assert "ARSIV:" not in prompt_text


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


def test_search_timeline_and_search_documents_never_reach_the_ledger():
    """§1e/§7a: bu iki okuma aracı `registry.call_tool` ÜZERİNDEN geçmiyor —
    doğrudan Python çağrısı, hiçbir alan aksiyonu değil. Deftere düşselerdi
    jüri bir okumayı bir aksiyon sanırdı."""
    store = Store(":memory:")
    gw = _investigating_gw(_tool_call("search_timeline", query="devrilme"),
                          _tool_call("search_documents", query="ekipman bakım"))
    with _archive_patch([]):
        assess_risk(gw, store, _ep(store))
    assert store.actions() == []


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
