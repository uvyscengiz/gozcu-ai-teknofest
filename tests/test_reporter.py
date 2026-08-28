"""Görev 12 — raportör ve kök neden raporu.

Rapor projenin **insana dönük** çıktısı: bir operatör onu okuyup bir iş
kazasının sebebi hakkında hüküm kuracak. Bu yüzden testler metnin varlığına
değil, üç garantisine bakıyor:

- **Prompt şemadan türüyor.** Promptun saydığı her alan modelde gerçekten
  var; elle yazılmış bir alan listesi ayrışır.
- **Her sayı kanıta dayanıyor.** Türetilmiş `overdue_maintenance_months`
  rakamı aksiyon defterinden prompta ulaşıyor; ulaşmıyorsa rapordaki sayı
  uydurmadır.
- **Arızalar birbirinden ayırt ediliyor.** Bozulmuş kademe, boş yanıt ve
  okunamayan yanıt üç farklı metin üretir — aynı kabuğu paylaşsalardı
  guard'lar sessizce ölü koda dönerdi.
"""

import json
import re
from unittest.mock import Mock

import pytest

from gozcu.agents.reporter import (ABSENCE_RULE, DEGRADED_REASON,
                                   EMPTY_REASON, EMPTY_SECTION,
                                   GROUNDING_RULE, MAX_CONFIDENCE_LIMITS,
                                   MAX_ROOT_CAUSE, MAX_WHAT_HAPPENED,
                                   MISSING_CONFIDENCE_LIMITS,
                                   PREVENTABILITY_RULE, SECTION_PLANS,
                                   SECTIONS, SYSTEM_PROMPT, UNREADABLE_REASON,
                                   RootCauseReport, _fallback, _parse,
                                   _plan_line, generate_root_cause_report)
from gozcu.core.gateway import Response
from gozcu.core.models import (ActionRecord, Correction, Detail, DialogueTurn,
                          Episode, EventBeat, RiskAssessment)
from gozcu.core.store import Store
from gozcu.tools.registry import call_tool

RESPONSE_JSON = ('{"what_happened":"B-Hattı sevkiyat alanında yük düştü.",'
                 '"probable_root_cause":"Fren bakımının 4 ay gecikmiş olması.",'
                 '"actions_taken":["İSG kaydı açıldı"],'
                 '"prevention_recommendations":["Bakım periyodu denetlensin"],'
                 '"confidence_limits":"Kamera görüntüsü fren durumunu doğrudan gösteremez."}')

#: Epizodun özeti düzeltmenin yeni değerinden bilerek FARKLI. Aynı olsalardı
#: "düzeltme prompta ulaştı" testi düzeltme silinse bile yeşil kalırdı —
#: metni epizot özeti zaten taşıyordu.
EPISODE_SUMMARY = "B-Hattı sevkiyat alanında bir olay gelişti"


def _gw(content=RESPONSE_JSON, **kw):
    gw = Mock()
    gw.ask.return_value = Response(content=content, **kw)
    return gw


def _seeded_store():
    store = Store(":memory:")
    e = Episode(start_ts=12.0, phase="outcome", summary_tr=EPISODE_SUMMARY,
                participants=["IST-04"], preliminary_risk="Yüksek",
                state="closed")
    e.id = store.create_episode(e)
    store.save_risk(RiskAssessment(episode_id=e.id, level="Yüksek",
                                   rationale_tr="fren gecikmesi",
                                   preventable=True))
    store.save_action(ActionRecord(ts=1.0, tool_name="open_safety_incident",
                                   params={}, result={"record_no": "x"},
                                   actor="agent", approval="not_required"))
    store.save_dialogue(DialogueTurn(ts=1.0, role="operator",
                                     text="ne oldu?"))
    return store, e


def _messages(gw):
    return gw.ask.call_args.args[1]


def _prompt_text(gw):
    return _messages(gw)[-1]["content"]


def _line_starting(text, prefix):
    return next(l for l in text.splitlines() if l.startswith(prefix))


# -- kademe ve şema ---------------------------------------------------------

def test_report_uses_the_large_reasoning_tier():
    gw = _gw()
    store, _ = _seeded_store()
    generate_root_cause_report(gw, store)
    assert gw.ask.call_args.args[0] == "main"
    assert gw.ask.call_args.kwargs["schema"] is RootCauseReport


def test_the_reporter_passes_its_own_generous_ceiling():
    """Raportörün girdisi bir koşunun en büyük promptu — genel şema tavanı
    26 Ağustos'ta burada da tükendi. Kendi tavanını taşımazsa gateway'in
    genel `SCHEMA_MAX_TOKENS`'ına düşer ve aynı arıza tekrar eder."""
    gw = _gw('{"what_happened": "x", "probable_root_cause": "y", '
             '"confidence_limits": "z"}')
    store, _ = _seeded_store()
    generate_root_cause_report(gw, store)
    assert gw.ask.call_args.kwargs.get("max_tokens") == 16384


# -- prompt şemadan türüyor (Kural 1) ---------------------------------------

_SNAKE_CASE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+")


def test_prompt_names_no_field_that_the_model_lacks():
    """Promptun andığı her alan adı `RootCauseReport`'ta gerçekten var.

    Prompt bir zamanlar `guven_sinirlari` diyordu; şemadaki ad
    `confidence_limits`. Model var olmayan bir anahtarı doldurur, o anahtar
    atılır ve gerçek alan boş kalırdı — CLAUDE.md'nin "bir kez ayrıştılar ve
    sistem sessizce öldü" dediği arıza.
    """
    named = set(_SNAKE_CASE.findall(SYSTEM_PROMPT))
    assert named, "prompt hiçbir alan adı saymıyor — katalog düşmüş olabilir"
    assert named <= set(RootCauseReport.model_fields)


def test_prompt_field_catalogue_covers_every_model_field():
    """Katalog şemadan türetiliyor; bir alan eklenince prompt kendiliğinden
    büyümeli."""
    assert set(_SNAKE_CASE.findall(SYSTEM_PROMPT)) == set(
        RootCauseReport.model_fields)


def test_prompt_states_the_length_limits_the_wire_no_longer_carries():
    """`maxLength` şema sertleştirmesinde sökülüyor; sınırı modele prompt
    söylüyor."""
    for limit in (MAX_WHAT_HAPPENED, MAX_ROOT_CAUSE, MAX_CONFIDENCE_LIMITS):
        assert str(limit) in SYSTEM_PROMPT


# -- görmemek "olmadı" değildir ----------------------------------------------

def test_prompt_forbids_turning_a_missing_detection_into_an_absence_verdict():
    """Ölçülen arıza (25 Ağustos, raf çökmesi klibi): algı katmanı altı
    kutunun altısını da düşürmüşken rapor "dış etki kaydedilmedi" yazdı ve
    kök nedeni "yapısal yorgunluk" diye uydurdu.

    İkisi aynı hatanın iki yüzü: yokluk kanıt sanıldı. `GROUNDING_RULE`
    sayıları kanıta bağlıyor, bu kural da yokluk iddialarını.
    """
    assert ABSENCE_RULE in SYSTEM_PROMPT
    assert "YOKLUK HÜKMÜ" in SYSTEM_PROMPT
    assert "DAYANAK YAPMA" in SYSTEM_PROMPT


def test_the_absence_rule_names_the_wording_that_was_actually_produced():
    """Kural soyut kalmasın: sahada üretilen cümle biçimi promptta geçiyor."""
    assert "Dış etki yoktur" in ABSENCE_RULE


# -- her sayı kanıta dayanıyor (Kural 2) ------------------------------------

def test_prompt_forbids_unevidenced_figures():
    assert GROUNDING_RULE in SYSTEM_PROMPT
    for header in SECTIONS:
        assert header in SYSTEM_PROMPT


def test_derived_maintenance_figure_reaches_the_prompt_from_the_ledger():
    """"4 ay gecikmiş fren bakımı" rakamının TEK kaynağı defter.

    Sayı hiçbir fikstür dosyasında yazmıyor; `query_equipment_history` onu
    bakım vadelerinden türetiyor ve çağrı `call_tool` üzerinden deftere
    düşüyor. Defter prompta girmezse rapordaki sayı dayanaksız kalır.
    """
    gw = _gw()
    store, e = _seeded_store()
    result = call_tool(store, "query_equipment_history",
                       {"equipment_id": "IST-04"}, ts=e.start_ts)
    assert result["overdue_maintenance_months"] == 4

    generate_root_cause_report(gw, store)
    ledger = _prompt_text(gw)
    assert "overdue_maintenance_months" in ledger
    assert '"overdue_maintenance_months": 4' in ledger


def test_prompt_includes_the_action_ledger():
    gw = _gw()
    store, _ = _seeded_store()
    generate_root_cause_report(gw, store)
    prompt = _prompt_text(gw)
    assert "open_safety_incident" in prompt
    assert "record_no" in prompt and "not_required" in prompt


def test_prompt_includes_risk_assessments_and_dialogue():
    gw = _gw()
    store, _ = _seeded_store()
    generate_root_cause_report(gw, store)
    prompt = _prompt_text(gw)
    assert "fren gecikmesi" in prompt and "ne oldu?" in prompt
    assert "Yüksek" in prompt


def test_every_section_appears_even_when_it_is_empty():
    gw = _gw()
    generate_root_cause_report(gw, Store(":memory:"))
    prompt = _prompt_text(gw)
    for header in SECTIONS:
        assert f"{header}:" in prompt
    # UYGULANAN PROSEDÜRLER kasıtlı olarak genel `EMPTY_SECTION` yerine
    # kendi boş metnini kullanıyor (bkz. `SECTION_PLANS` docstring'i): "bu
    # kayıt hiç tutulmadı" ile "protokol hiç eşleşmedi" aynı kabuğu
    # paylaşmamalı. Bu yüzden `EMPTY_SECTION` sayısı SECTIONS uzunluğundan
    # BİR eksik — fark burada iddia ediliyor, örtülü bırakılmıyor.
    assert prompt.count(EMPTY_SECTION) == len(SECTIONS) - 1
    assert "- (prosedür kaydı yok)" in prompt


# -- operatör düzeltmesi kazanır --------------------------------------------

def _store_with_correction():
    store, e = _seeded_store()
    store.save_correction(Correction(ts=1.0, episode_id=e.id,
                                     field="event_type", old="araç devrildi",
                                     new="yük düştü",
                                     rationale="operatör gözlemi"))
    return store, e


def test_operator_corrections_reach_the_prompt():
    gw = _gw()
    store, _ = _store_with_correction()
    generate_root_cause_report(gw, store)
    prompt = _prompt_text(gw)
    # Epizot özeti düzeltmenin yeni değerini TAŞIMIYOR: iki iddia da ayrı ayrı
    # anlamlı.
    assert EPISODE_SUMMARY in prompt
    assert "yük düştü" not in EPISODE_SUMMARY
    assert "yük düştü" in prompt and "araç devrildi" in prompt
    assert "operatör gözlemi" in prompt


def test_the_corrected_value_supersedes_the_original():
    """Rapora ulaşmayan bir düzeltme hiçbir şey yapmamış bir düzeltmedir —
    ama prompta ikisini yan yana koymak da yetmez: modelin HANGİSİNİN geçerli
    olduğunu görmesi gerek."""
    gw = _gw()
    store, _ = _store_with_correction()
    generate_root_cause_report(gw, store)
    line = _line_starting(_prompt_text(gw), "- event_type:")
    assert "GEÇERLİ DEĞER 'yük düştü'" in line
    assert "'araç devrildi'" in line and "GEÇERSİZ" in line
    assert line.index("yük düştü") < line.index("araç devrildi")


# -- doğrulamadan ÖNCE kesme (Kural 3) --------------------------------------

def _overlong(field, filler):
    """Geçerli raporun tek bir alanını sınırın üstüne taşıran yanıt."""
    payload = json.loads(RESPONSE_JSON)
    payload[field] = filler
    return json.dumps(payload, ensure_ascii=False)


def test_overlong_fields_are_truncated_instead_of_collapsing_the_report():
    """Şema sertleştirmesi `maxLength`'i telden söküyor; taşma BEKLENEN yol.

    Ham hâliyle pydantic'e verilseydi doğrulama patlar ve GERÇEK bir rapor
    kabuğa düşerdi — mock'larla yeşil, sahada hep kabuk.
    """
    long_text = "Sevkiyat alanında yük düştü ve istif aracı durdu. " * 30
    gw = _gw(_overlong("what_happened", long_text))
    store, _ = _seeded_store()
    r = generate_root_cause_report(gw, store)
    assert len(r.what_happened) <= MAX_WHAT_HAPPENED
    assert r.what_happened.startswith("Sevkiyat alanında yük düştü")
    for reason in (DEGRADED_REASON, EMPTY_REASON, UNREADABLE_REASON):
        assert reason not in r.what_happened
    # Taşmayan alanlar gerçek rapordan geliyor, kabuktan değil.
    assert "4 ay" in r.probable_root_cause


def test_every_length_limited_field_is_truncated():
    store, _ = _seeded_store()
    for field, limit in (("what_happened", MAX_WHAT_HAPPENED),
                         ("probable_root_cause", MAX_ROOT_CAUSE),
                         ("confidence_limits", MAX_CONFIDENCE_LIMITS)):
        gw = _gw(_overlong(field, "Kanıta dayanan uzun bir cümle. " * 40))
        r = generate_root_cause_report(gw, store)
        assert len(getattr(r, field)) <= limit
        assert getattr(r, field).startswith("Kanıta dayanan")


# -- üç ayrı arıza, üç ayrı metin (Kural 4) ---------------------------------

def test_degraded_tier_returns_a_report_shell_not_an_exception():
    """Yanıt GEÇERLİ JSON taşıyor: kabuk yalnızca `degraded` kontrolünden
    çıkabilir. İçerik boş olsaydı test guard silinince de yeşil kalırdı."""
    gw = Mock()
    gw.ask.return_value = Response(content=RESPONSE_JSON, degraded=True)
    store, _ = _seeded_store()
    r = generate_root_cause_report(gw, store)
    assert DEGRADED_REASON in r.what_happened
    assert r.confidence_limits.strip()
    assert "4 ay" not in r.probable_root_cause


def test_empty_content_is_reported_as_its_own_fault():
    gw = _gw(content="   ")
    store, _ = _seeded_store()
    r = generate_root_cause_report(gw, store)
    assert EMPTY_REASON in r.what_happened


def test_unreadable_content_is_reported_as_its_own_fault():
    gw = _gw(content="Rapor: yük düştü, sebebi fren.")
    store, _ = _seeded_store()
    r = generate_root_cause_report(gw, store)
    assert UNREADABLE_REASON in r.what_happened


def test_the_three_fallback_texts_are_distinct():
    assert len({DEGRADED_REASON, EMPTY_REASON, UNREADABLE_REASON}) == 3


# -- kaynak etiketi: yapısal, metne bakarak DEĞİL (spec §7) -----------------

def test_a_fallback_report_says_so_structurally():
    """`report_source` metin karşılaştırmasıyla DEĞİL, `PrivateAttr` ile.

    Sentezleyicinin `Episode.summary_source` deseninin aynısı: bir yedek
    raporu ayırt etmenin tek güvenilir yolu bu etiket, `what_happened`
    içinde arıza kelimesi geçip geçmediğine bakmak değil.
    """
    report = _fallback(EMPTY_REASON)
    assert report.report_source == "fallback"


def test_a_parsed_report_is_model_sourced():
    report = _parse('{"what_happened": "x", "probable_root_cause": "y", '
                    '"confidence_limits": "z"}')
    assert report.report_source == "model"


# -- rapor her hâlükârda sınırlarını yazar ----------------------------------

def test_report_always_states_its_confidence_limits():
    """Model alanı boş bırakırsa rapor yine de neyi bilemediğini söyler.

    "Kesin hüküm yok" bu tek alanda duruyor; boş bir `confidence_limits`
    pydantic'ten sessizce geçer ve rapor kendini mutlak bir hüküm gibi
    sunardı.
    """
    gw = _gw(RESPONSE_JSON.replace(
        '"Kamera görüntüsü fren durumunu doğrudan gösteremez."', '""'))
    store, _ = _seeded_store()
    r = generate_root_cause_report(gw, store)
    assert r.confidence_limits.strip()
    assert r.confidence_limits == MISSING_CONFIDENCE_LIMITS
    # Gerçek rapor kabuğa düşmedi; sadece eksik alan tamamlandı.
    assert "4 ay" in r.probable_root_cause


def test_the_models_own_confidence_limits_survive():
    gw = _gw()
    store, _ = _seeded_store()
    r = generate_root_cause_report(gw, store)
    assert r.confidence_limits.startswith("Kamera görüntüsü")


# -- teslim şekli (Kural 7) -------------------------------------------------

def test_empty_store_returns_a_full_report_shape():
    r = generate_root_cause_report(_gw(), Store(":memory:"))
    assert isinstance(r, RootCauseReport)
    assert set(r.model_dump()) == {"what_happened", "probable_root_cause",
                                   "actions_taken",
                                   "prevention_recommendations",
                                   "confidence_limits"}
    assert r.what_happened.strip() and r.confidence_limits.strip()
    assert isinstance(r.actions_taken, list)


def test_report_is_deliverable_under_detail_root_cause_report():
    """Görev 17 raporu `detail.root_cause_report` altında düz `dict` olarak
    teslim ediyor."""
    gw = _gw()
    store, _ = _seeded_store()
    r = generate_root_cause_report(gw, store)
    detail = Detail(root_cause_report=r.model_dump())
    assert detail.root_cause_report["what_happened"] == r.what_happened


def test_report_is_returned_not_persisted():
    gw = _gw()
    store, _ = _seeded_store()
    before = (len(store.episodes()), len(store.risks()), len(store.actions()),
              len(store.handoffs()), len(store.dialogue()))
    generate_root_cause_report(gw, store)
    after = (len(store.episodes()), len(store.risks()), len(store.actions()),
             len(store.handoffs()), len(store.dialogue()))
    assert before == after


# -- yedek özet OLAY ZİNCİRİ'ne kanıt olarak girmez (Görev 20) --------------

def test_the_evidence_file_does_not_carry_a_fault_text_as_an_event():
    """OLAY ZİNCİRİ bölümü kanıt dosyasıdır: raportör oradaki her satırı
    gerçek bir gözlem sayar. Yedek özetli bir epizodun satırı arıza metnini
    OLDUĞU GİBİ taşırsa ("Sentez üretilemedi; ham gözlemler kayıtlı.") model
    onu fabrikada olmuş bir olay sanabilir — süpervizörün `NO_DESCRIPTION_NOTE`
    ile önlediği uydurmanın raportör tarafındaki karşılığı. Ham anlar hâlâ
    gerçek gözlem olduğu için kanıt olarak kalmalı.
    """
    store, _ = _seeded_store()
    fallback = Episode(start_ts=5.0, phase="development",
                       summary_tr="Sentez üretilemedi; ham gözlemler kayıtlı.",
                       preliminary_risk="Orta", summary_source="fallback",
                       beats=[EventBeat(ts=6.0,
                                        text="Forklift kamyona temas etti.")])
    store.create_episode(fallback)

    gw = _gw()
    generate_root_cause_report(gw, store)
    text = _prompt_text(gw)

    assert "Sentez üretilemedi" not in text
    assert "ham anlar epizot kaydında" in text
    assert "Forklift kamyona temas etti." in text


def test_a_real_episode_line_still_carries_its_summary_verbatim():
    store, e = _seeded_store()
    gw = _gw()
    generate_root_cause_report(gw, store)
    text = _prompt_text(gw)
    assert e.summary_tr in text


# -- kök neden raporu prosedürü anıyor (Görev 7, spec §2a) ------------------

@pytest.fixture
def store():
    return Store(":memory:")


def _episode(store) -> Episode:
    """Plan bir epizoda bağlanmak zorunda; bu testlerin ihtiyacı olan
    minimum epizot."""
    e = Episode(start_ts=0.0, phase="outcome",
               summary_tr="B-Hattında çarpma.", participants=["IST-04"],
               preliminary_risk="Yüksek", state="closed")
    e.id = store.create_episode(e)
    return e


def test_report_prompt_cites_the_protocol(store):
    """'Önlenebilirdi' iddiası bir prosedüre dayanmalı (spec §2a)."""
    from gozcu.agents.reporter import _prompt
    from gozcu.core.models import ActionPlan, ProposedAction

    episode = _episode(store)
    plan = ActionPlan(episode_id=episode.id, risk_assessment_id=1, ts=5.0,
                      protocol_id="PRT-B-CARPMA",
                      rationale_tr="B-Hattı çarpma prosedürü geçerli.",
                      proposed_actions=[
                          ProposedAction(description_tr="B hattını durdur",
                                         tool_name="halt_production_line")],
                      plan_source="model")
    store.save_action_plan(plan)

    text = _prompt(store)
    assert "PRT-B-CARPMA" in text
    assert "B hattını durdur" in text


def test_report_prompt_survives_empty_plan(store):
    """Plan yokken rapor yine üretilebilmeli — VE bölüm başlığıyla kendi boş
    metnini göstermeli, sadece çökmemesi yetmez."""
    from gozcu.agents.reporter import _prompt
    text = _prompt(store)
    assert text
    assert SECTION_PLANS in text
    assert "- (prosedür kaydı yok)" in text


def test_system_prompt_announces_the_procedures_section_it_asks_the_model_to_cite():
    """`PREVENTABILITY_RULE` modelden UYGULANAN PROSEDÜRLER'i anmasını
    istiyor; sistem promptunun açılış cümlesi ("Sana kapanmış bir olayın tam
    kaydı verilir: ...") o bölümü modele TANITMAZSA model var olduğunu
    bilmediği bir bölümü anmakla yükümlü kılınır. `SECTIONS`'ın
    `SECTION_PLANS`'ı İÇERMESİ bu testin doğrulandığı yer.
    """
    opening = SYSTEM_PROMPT.split("Bu kayda dayanarak")[0]
    assert SECTION_PLANS in opening
    assert PREVENTABILITY_RULE in SYSTEM_PROMPT


# -- plan_source üç ayrı satır üretir (protocol_fallback ve empty de) -------

def _plan(plan_source, protocol_id="PRT-B-CARPMA"):
    from gozcu.core.models import ActionPlan, ProposedAction
    return ActionPlan(episode_id=1, risk_assessment_id=1, ts=5.0,
                      protocol_id=protocol_id,
                      rationale_tr="test",
                      proposed_actions=[
                          ProposedAction(description_tr="B hattını durdur",
                                         tool_name="halt_production_line")],
                      plan_source=plan_source)


def test_a_model_composed_plan_says_the_plan_layer_built_it():
    line = _plan_line(_plan("model"))
    assert "plan katmanı kurdu" in line


def test_a_protocol_fallback_plan_says_the_steps_were_applied_verbatim():
    """`plan_source="protocol_fallback"` bir yedektir: modelin çıktısı
    okunamadığı için protokolün adımları BİREBİR yazıldı. Rapor bunu modelin
    kararı gibi anlatırsa raporun en çok güvenilmesi gereken cümlesi yalan
    olur — bu test o ayrımın hâlâ ayakta olduğunu sabitliyor.
    """
    line = _plan_line(_plan("protocol_fallback"))
    assert "prosedür adımları doğrudan uygulandı" in line
    assert "plan katmanı kurdu" not in line


def test_an_empty_plan_says_no_recommendation_was_produced():
    """`plan_source="empty"` = eşleşen protokol yoktu; öneri üretilmedi.

    Aksiyonlar boş olsa bile satır bunu "—" ile değil, kaynak etiketiyle
    açıkça söylemeli.
    """
    from gozcu.core.models import ActionPlan
    plan = ActionPlan(episode_id=1, risk_assessment_id=1, ts=5.0,
                      protocol_id=None, rationale_tr="eşleşen protokol yok",
                      proposed_actions=[], plan_source="empty")
    line = _plan_line(plan)
    assert "öneri üretilmedi" in line
    assert "plan katmanı kurdu" not in line
    assert "prosedür adımları doğrudan uygulandı" not in line
    assert "(tanımlı prosedür yok)" in line


def test_the_three_plan_source_renderings_are_pairwise_distinct():
    """Bu testin tek görevi: üç etiketin aynı kelimeye çökmediğini sabitlemek.
    Aynı kabuğu paylaşsalardı bir regresyon hiçbir şeyle yakalanmazdı — bu
    kod tabanının belgelenmiş bir arıza sınıfı (bkz. `Episode.summary_source`)
    tam olarak bu.
    """
    renderings = {source: _plan_line(_plan(source))
                 for source in ("model", "protocol_fallback", "empty")}
    assert len(set(renderings.values())) == 3
