"""Görev 5/11 — risk analisti.

Analistin iddiası test ediliyor: **gerçekten araştırıyor** — modele iki
okuma aracı (`search_timeline`, `search_documents`) sunuluyor, çağırdıklarını
DOĞRUDAN Python çağrısıyla çalıştırıyoruz (registry DEĞİL — bu okumalar
aksiyon defterine hiç düşmüyor, bkz. `test_search_timeline_and_search_documents_never_reach_the_ledger`).
Sahte bir cümleyle taklit edilebilir; testler o yüzden aracın gerçekten
çağrıldığına, döndürdüğü sonucun doğru alanlarla modele ulaştığına ve
deftere/`RiskAssessment`'e ne düştüğüne bakıyor.
"""

import json
from unittest.mock import Mock, patch

from gozcu.agents.risk import (DEGRADED_RATIONALE, MAX_RATIONALE, RISK_TOOLS,
                               _prompt, assess_risk)
from gozcu.core.gateway import Response
from gozcu.core.models import (Correction, DocumentResult, Episode,
                               EventBeat, Precedent)
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
# aracını KENDİ SEÇİMİYLE çağırırsa arama olur (§6b, §1e). Ama emsal yine
# `RiskAssessment.precedents`'e YAZILIYOR (B6 geri getirildi, review round 1) —
# jüri prompt'u değil deftere düşen kaydı görüyor, ve arşiv okuması artık bir
# aracın geçici mesajında kalırsa jüri onu HİÇ göremezdi. Araç birden çok tur
# boyunca çağrılabildiği için biriken liste tekilleştirilip skora göre
# sıralanıyor (`_rank_precedents`, review round 2) — aksi hâlde
# `search_timeline`'ın TEK ÇAĞRI için çözdüğü B8 (aynı kaydın ikizlenmesi)
# turlar arasında yeniden açılırdı. Bu bölümdeki testler dışlamayı, model
# tetiklemesini VE bu tekilleştirme/sıralama garantisini doğruluyor.

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
    """Model hiç `search_timeline` çağırmazsa (`_gw()` araç çağrısı
    taşımıyor) toplanacak emsal de yok — boş liste kaydediliyor.

    Aracı GERÇEKTEN çağırdığında emsalin deftere düştüğünü ayrı test
    kanıtlıyor: `test_search_timeline_result_reaches_the_assessment`."""
    store = Store(":memory:")
    with _archive_patch([]):
        assessment = assess_risk(_gw(), store, _ep(store))
    assert assessment.precedents == []


def test_search_timeline_result_reaches_the_assessment():
    """§B6 (geri getirildi): `search_timeline`'ın getirdiği emsal hem
    modele giden araç mesajında hem de KALICI `RiskAssessment.precedents`'te
    durmalı — jüri prompt'u değil deftere düşen kaydı okuyor.

    `_run_tool_calls`'daki projeksiyonun (`p.episode.summary_tr`,
    `p.episode.participants`, `p.score`) doğru alanlara baktığını da
    dolaylı olarak kanıtlıyor: yanlış bir alan adı (`p.episode.summary`,
    `p.score` yerine `p.episode.score`) burada `AttributeError` fırlatır."""
    store = Store(":memory:")
    e = _ep(store)
    prior = Precedent(
        episode=Episode(id=9, start_ts=0.0, phase="outcome",
                        summary_tr="IST-04 fren mesafesi uzadı",
                        preliminary_risk="Orta", participants=["IST-04"]),
        score=0.71)
    gw = _investigating_gw(_tool_call("search_timeline", query="fren"))
    with _archive_patch([prior]):
        assessment = assess_risk(gw, store, e)

    # Geçici araç mesajında: modelin GÖRDÜĞÜ metin.
    tool_text = _text(gw, -1)
    assert "IST-04 fren mesafesi uzadı" in tool_text
    assert "0.71" in tool_text

    # Kalıcı kayıtta: jürinin GÖRDÜĞÜ kayıt.
    assert [p.episode.summary_tr for p in assessment.precedents] == [
        "IST-04 fren mesafesi uzadı"]
    assert assessment.precedents[0].score == 0.71
    assert store.risks()[-1].precedents[0].score == 0.71

    # Video-zamanı damgası (CLAUDE.md: "Kararlar olay anında verilir") —
    # araç turu kaç el sürse de değişmemeli, hep epizodun ŞİMDİsi.
    assert assessment.ts == e.end_ts
    assert store.risks()[-1].ts == e.end_ts


def test_precedents_accumulated_across_turns_are_deduped_and_ranked():
    """§B8 bir kat yukarı taşınmasın: model `search_timeline`'ı BİRDEN ÇOK
    turda çağırabildiği için ham liste turlar arasında şişebilir VE aynı
    epizot iki kez dönebilir. Bu test üç iddiayı birden sınıyor:

    1. her iki turun emsali de KALICI kayda ulaşıyor (`precedents.extend`
       yerine `precedents = found` yazılsaydı yalnız SON turun emsali
       kalırdı — bu test o zaman "B kaydı, C kaydı" görür, "A kaydı" hiç
       görünmez ve uzunluk 2 olur, aşağıdaki `len == 3` çöker)
    2. aynı kaynak (`source="arşiv:B"`) iki kez dönse bile listede TEK
       satır olarak duruyor — B8'in `search_timeline`'ın TEK ÇAĞRISI için
       çözdüğü sorunun turlar arasında yeniden açılmadığını kanıtlıyor
    3. o tek satır, iki görünümün EN YÜKSEK skorlusu (`0.9`, `0.6` değil) —
       `gozcu/agents/supervisor.py`'nin `precedents[0]`'ı "en yakın kayıt"
       diye okuması bunu şart koşuyor
    """
    store = Store(":memory:")
    e = _ep(store)

    ep_a = Episode(id=1, start_ts=0.0, phase="outcome", source="arşiv:A",
                  summary_tr="A kaydı", preliminary_risk="Orta")
    ep_b_low = Episode(id=2, start_ts=0.0, phase="outcome", source="arşiv:B",
                       summary_tr="B kaydı", preliminary_risk="Orta")
    ep_b_high = Episode(id=2, start_ts=0.0, phase="outcome", source="arşiv:B",
                        summary_tr="B kaydı", preliminary_risk="Orta")
    ep_c = Episode(id=3, start_ts=0.0, phase="outcome", source="arşiv:C",
                  summary_tr="C kaydı", preliminary_risk="Orta")

    call_1 = [Precedent(episode=ep_b_low, score=0.6),
             Precedent(episode=ep_a, score=0.4)]
    call_2 = [Precedent(episode=ep_b_high, score=0.9),
             Precedent(episode=ep_c, score=0.75)]

    gw = Mock()
    gw.ask.side_effect = [
        Response(tool_calls=[_tool_call("search_timeline", query="olay A")]),
        Response(tool_calls=[_tool_call("search_timeline", query="olay B")]),
        Response(content=RESPONSE_JSON),
    ]

    with patch("gozcu.agents.risk.search_timeline",
              side_effect=[call_1, call_2]):
        assessment = assess_risk(gw, store, e)

    assert gw.ask.call_count == 3
    assert len(assessment.precedents) == 3, \
        "iki turun emsali de deftere ulaşmalı, tekilleştirmeden SONRA 3 kalır"
    assert [p.episode.summary_tr for p in assessment.precedents] == [
        "B kaydı", "C kaydı", "A kaydı"], "skora göre İNEN sırada durmalı"
    assert assessment.precedents[0].score == 0.9, \
        "B kaydının iki görünümünden EN YÜKSEK skorlusu kalmalı"


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
    """§1d: risk analisti search_documents aracını kullanabilir.

    `gw.ask.call_count` ve `level` TEK BAŞINA `search_documents`'ın
    ÇAĞRILDIĞINI kanıtlamıyor — o iki koşul refuse dalından da geçer (bkz.
    `test_a_write_tool_call_is_refused_and_never_reaches_the_ledger`, aynı
    şekilde ikinci turda değerlendirmeye ulaşıyor). `search_documents`'ı
    doğrudan yamalayıp modelin verdiği sorguyla çağrıldığını doğruluyoruz —
    `_run_tool_calls`'daki `elif name == "search_documents":` dalı silinse
    bu iddia çöker."""
    store = Store(":memory:")
    e = _ep(store)

    gw = _investigating_gw(
        _tool_call("search_documents", query="ekipman bakım"),
        final=RESPONSE_JSON)

    with _archive_patch([]), \
         patch("gozcu.agents.risk.search_documents",
              return_value=[]) as search_docs:
        assessment = assess_risk(gw, store, e)

    search_docs.assert_called_once()
    assert search_docs.call_args.args[1] == "ekipman bakım"
    assert gw.ask.call_count == 2
    assert assessment.level == "Kritik"


def test_search_documents_result_reaches_the_model():
    """§1d/§3b: mirror of `test_search_timeline_result_reaches_the_assessment`
    for the OTHER tool. `test_risk_analyst_can_call_search_documents` only
    proves the dispatch happens — it patches `search_documents` with
    `return_value=[]`, so the projection in `_run_tool_calls`
    (`r.name`, `r.text_excerpt`, `r.score`) never actually runs against a
    populated `DocumentResult`. A field-name typo there (`r.excerpt` instead
    of `r.text_excerpt`) would raise `AttributeError` here."""
    store = Store(":memory:")
    e = _ep(store)

    doc = DocumentResult(document_id="doc-1", name="bakım-talimatı.pdf",
                         text_excerpt="Fren sistemi 3 ayda bir kontrol edilir.",
                         score=0.62)

    gw = _investigating_gw(
        _tool_call("search_documents", query="fren bakımı"),
        final=RESPONSE_JSON)

    with _archive_patch([]), \
         patch("gozcu.agents.risk.search_documents", return_value=[doc]):
        assess_risk(gw, store, e)

    tool_text = _text(gw, -1)
    assert "bakım-talimatı.pdf" in tool_text
    assert "Fren sistemi 3 ayda bir kontrol edilir." in tool_text
    assert "0.62" in tool_text


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


def test_document_context_reaches_the_prompt_when_a_document_is_embedded():
    """§3e/§7a: model `search_documents`'ı seçebilmek için hangi belgelerin
    gömülü olduğunu bilmeli — `document_context()` prompt'a giriyor.

    `tests/conftest.py`'nin autouse `_isolated_library` fixture'ı
    `library_dir`'i izole bir `tmp_path`'e yamalıyor, yani bu test gerçek
    depoya yazmıyor. `lines.append(f"\\n{doc_ctx}")` silinse bu test
    kırılır — önceki hâlde her test boş kütüphaneyle çalıştığı için
    `document_context()` hep `""` dönüyordu ve o satırın hiç
    çalıştırılmadığı fark edilmiyordu."""
    from gozcu.memory.library import mark_embedded, save_document
    store = Store(":memory:")
    doc = save_document("bakım-talimatı.pdf", b"icerik")
    mark_embedded(doc.id, True)

    gw = _gw(RESPONSE_JSON)
    with _archive_patch([]):
        assess_risk(gw, store, _ep(store))

    prompt_text = _text(gw, 0)
    assert "YÜKLÜ BELGELER" in prompt_text
    assert "bakım-talimatı.pdf" in prompt_text


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
    istemi ondan büyük (olay + araç sonuçları + düzeltmeler), yani varsayılan
    tavanla değerlendirme sessizce yedeğe düşebilir — `risk` şartnamenin
    puanlanan dört anahtarından biri. Raportör aynı sebeple kendi tavanını
    taşıyor.
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
