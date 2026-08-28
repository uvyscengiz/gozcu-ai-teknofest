"""Karar & Aksiyon ajanı — riske karşı protokole dayalı müdahale planı.

Bu ajanın var oluş sebebi, risk analistinden bir alanı devralmak değil:
planı **tesisin yazılı prosedürüne** bağlamak. Aday protokoller deterministik
süzülüp prompt'a yazılıyor (`fixtures.match_protocols`), model yalnız
aralarından seçiyor. İki sonucu var:

- `preventable` modelin kanaati olmaktan çıkıyor: "PRT-B-CARPMA prosedürü
  vardı ve uygulanmadı" denebilir hâle geliyor (kök neden raporu, Görev 7).
- Deterministik bir yedek doğuyor: model susarsa protokolün adımları birebir
  plana yazılıyor. Çıktı sözleşmesinin `actions` anahtarı artık model
  başarısına bağlı değil.

**Yazma araçları bu ajana kapalı.** Müdahale araçlarını yalnız Nöbetçi'nin
onay kapısı çağırır; planlayıcı öneri üretir, tetiklemez.

**Sunulan okuma aracı (`search_documents`) GERÇEKTEN çağrılabilir.** `tools=`
ile bir araç teklif edip çağrısını hiç çalıştırmamak bir yalandır — model
"sor" diye teşvik edilir, sorduğunda hiçbir şey olmaz ve boş içerikle yedeğe
düşer. Desen `risk.py::assess_risk`'in aynısı: modele okuma aracı sunuluyor,
çağırırsa çalıştırıyoruz, sonucu geri veriyoruz ve nihai plan İKİNCİ
(araçsız) turdan çıkıyor — model sonsuza dek araştırmasın diye. `_tool_calls`,
`_call_arguments`, `_assistant_turn` risk.py'den DEĞİŞTİRİLMEDEN alınıyor.

**`search_documents` bir alan aksiyonu değil, düz bir Python fonksiyonu.**
`call_tool` üzerinden DEĞİL, `_run_tool_calls` içinde doğrudan çağrılıyor —
aksiyon defteri yalnız gerçek saha aksiyonlarını kaydediyor, bir belge
araması onun içine karışmamalı.
"""
import json

from pydantic import BaseModel, ConfigDict, Field

from gozcu.agents.interpreter import _sanitize_text
from gozcu.agents.risk import (_assistant_turn, _call_arguments,
                               _describe_tool, _tool_calls)
from gozcu.fixtures.loader import match_protocols
from gozcu.core.models import (ActionPlan, Episode, Handoff, ProposedAction,
                          RiskAssessment)
from gozcu.memory.episodic import SEARCH_DOCUMENTS_SCHEMA, search_documents
from gozcu.memory.library import document_context
from gozcu.tools.registry import TOOL_SCHEMAS, TOOLS

MAX_RATIONALE = 800
MAX_ACTION_DESCRIPTION = 200
PLANNER_MAX_TOKENS = 4096

#: Planlayıcıya sunulan araçlar — yalnız okuma. `risk.READ_TOOLS`'ın
#: ikizi değil: analist arşive de bakıyor, planlayıcı yalnız parametre
#: dolduruyor. İkisi ayrı sebeplerle değişebilir.
PLANNER_READ_TOOLS = ("search_documents",)
PLANNER_TOOL_SCHEMAS = [SEARCH_DOCUMENTS_SCHEMA]

#: `risk.REFUSAL_REASON`'ın ikizi değil — o "Analist" diyor, bu "Planlayıcı".
#: Model reddedilen çağrının GEREKÇESİNİ görüyor; yanlış ajan adı ikinci
#: turda kafa karıştırır.
REFUSAL_REASON = ("Planlayıcı yalnızca okuma araçlarını çağırabilir. "
                  "Müdahale araçları öneri olarak proposed_actions içine "
                  "yazılır ve yalnız Nöbetçi'nin onay kapısından geçerek "
                  "yürütülür.")

NO_PROTOCOL_RATIONALE = ("Bu olay sınıfı ve bölge için tanımlı bir prosedür "
                         "bulunmadı; müdahale önerisi üretilmedi.")
FALLBACK_RATIONALE = ("Plan katmanı okunabilir yanıt vermedi; {title} "
                      "prosedürünün adımları doğrudan uygulandı.")

SYSTEM_PROMPT = """Sen bir fabrikanın İSG müdahale protokolü uzmanısın.

Sana bir olay, o olayın risk değerlendirmesi ve tesiste TANIMLI prosedürler
veriliyor. Görevin: geçerli prosedürü seçmek ve adımlarını olayın somut
verileriyle (bölge, ekipman, personel) doldurulmuş müdahale önerilerine
çevirmek.

KURALLAR:
- `protocol_id` alanına SADECE sana verilen aday prosedürlerden birinin
  kimliğini yaz. Hiçbiri uymuyorsa null yaz. Prosedür UYDURMA.
- Her öneriyi SADECE aşağıdaki araçlardan birine bağla. Araç adını ve
  parametre değerlerini burada yazdığı gibi, birebir kullan:
{tools}
- Parametreleri olayın verilerinden doldur. Bilmiyorsan `search_documents`
  aracıyla yüklü belgelerde ara; uydurma.
- Sadece JSON döndür.

{doc_context}"""


class _PlanResponse(BaseModel):
    """Modelden beklenen şekil.

    `ActionPlan`'dan ayrı: onun `id`, `episode_id`, `risk_assessment_id` ve
    `plan_source` alanları var ve katı şema modunda her alan `required`
    oluyor — model kendi veritabanı kimliğini uydurmak zorunda kalırdı.
    """

    model_config = ConfigDict(extra="forbid")

    protocol_id: str | None = None
    rationale_tr: str = Field(max_length=MAX_RATIONALE)
    proposed_actions: list[ProposedAction] = Field(default_factory=list)


def _describe_protocol(protocol) -> str:
    """Bir protokolü prompt satırlarına çevirir."""
    lines = [f"- {protocol.protocol_id}: {protocol.title_tr} "
             f"(en az {protocol.min_risk} risk)"]
    for step in sorted(protocol.steps, key=lambda s: s.order):
        lines.append(f"    {step.order}. {step.description_tr} "
                     f"→ {step.tool_name} {json.dumps(step.params, ensure_ascii=False)}")
    return "\n".join(lines)


def _prompt(episode: Episode, assessment: RiskAssessment,
            candidates: list) -> str:
    participants = ", ".join(episode.participants) or "(bilinmiyor)"
    catalogue = "\n".join(_describe_protocol(p) for p in candidates)
    return "\n".join([
        f"OLAY: {episode.summary_tr}",
        f"OLAY SINIFI: {episode.event_class}",
        f"BÖLGE: {episode.zone_id or '(bilinmiyor)'}",
        f"KATILIMCILAR (ekipman/personel kimlikleri): {participants}",
        f"RİSK: {assessment.level} — {assessment.rationale_tr}",
        f"ÖNLENEBİLİR: {'evet' if assessment.preventable else 'hayır'}",
        f"\nADAY PROSEDÜRLER:\n{catalogue}",
    ])


def _parse(content: str) -> _PlanResponse | None:
    """Ham çıktıyı doğrulanmış yanıta çevirir; olmazsa `None`."""
    try:
        data = json.loads(content)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    rationale = data.get("rationale_tr")
    if isinstance(rationale, str):
        data["rationale_tr"] = _sanitize_text(rationale, MAX_RATIONALE)
    actions = data.get("proposed_actions")
    if isinstance(actions, list):
        data["proposed_actions"] = [_sanitize_action(a) for a in actions]

    try:
        return _PlanResponse(**data)
    except Exception:  # noqa: BLE001 — bozuk çıktı bir koşuyu düşürmemeli
        return None


def _sanitize_action(action):
    """Öneri açıklamasını sınıra çeker (risk.py'deki ikizinin aynısı:
    tek uzun bir öneri bütün planı doğrulama hatasına düşürmemeli)."""
    if not isinstance(action, dict):
        return action
    description = action.get("description_tr")
    if not isinstance(description, str):
        return action
    return {**action,
            "description_tr": _sanitize_text(description,
                                             MAX_ACTION_DESCRIPTION)}


def _from_protocol(protocol) -> list[ProposedAction]:
    """Protokol adımlarını BİREBİR önerilere çevirir — deterministik yedek."""
    return [ProposedAction(description_tr=step.description_tr,
                           tool_name=step.tool_name, params=dict(step.params))
            for step in sorted(protocol.steps, key=lambda s: s.order)
            if step.tool_name in TOOLS]


def _run_tool_calls(gw, store, calls: list[dict], ts: float) -> list[dict]:
    """Okuma araçlarını çalıştırır — search_documents doğrudan Python.

    `search_documents` bir alan aksiyonu değil, `call_tool`'dan (aksiyon
    defterine yazan tek meşru giriş noktası) geçmiyor: bir belge araması
    "yapıldı" diye deftere düşerse, gerçek saha aksiyonlarıyla aynı listede
    görünüp raporu yanıltır. Reddedilen çağrı da deftere HİÇ düşmüyor —
    risk.py'deki aynı kural. Redde model geri söyleniyor ki ikinci turda o
    aracı öneri olarak yazsın.
    """
    messages = []
    for call in calls:
        name, params = _call_arguments(call)
        if name in PLANNER_READ_TOOLS:
            if name == "search_documents":
                found = search_documents(gw, params.get("query", ""),
                                         client=store)
                result = {"results": [{"name": r.name,
                                       "text_excerpt": r.text_excerpt,
                                       "score": round(r.score, 3)}
                                      for r in found]}
            else:
                result = {"tool_name": name, "error": "bilinmeyen araç"}
        else:
            result = {"tool_name": name, "refused": True,
                      "reason": REFUSAL_REASON}
        messages.append({"role": "tool", "tool_call_id": call.get("id", ""),
                         "name": name,
                         "content": json.dumps(result, ensure_ascii=False,
                                               default=str)})
    return messages


def plan_actions(gw, store, episode: Episode,
                 assessment: RiskAssessment) -> ActionPlan:
    """Epizoda karşı müdahale planı üretir, kaydeder ve devreder.

    Akış: protokolleri süz → aday yoksa boş plan → modele sor (okuma
    araçlarıyla) → çağırdığı araçları defter üzerinden çalıştır → sonuçlarla
    ikinci kez sor → okunamazsa protokol adımlarına düş → süz, kaydet,
    devret.

    Araç turu **isteğe bağlı**: model hiçbir şey çağırmazsa ya da kademe
    bozuksa tek çağrılık plana düşülür — `risk.assess_risk`'in aynı kuralı.
    """
    # Videonun "şimdi"si — `start_ts` uzun bir olayda saati olayın başında
    # dondurur (risk.py'deki aynı kural).
    now = episode.end_ts or episode.start_ts

    candidates = match_protocols(episode.event_class, episode.zone_id,
                                 assessment.level)

    if not candidates:
        return _save(store, ActionPlan(
            episode_id=episode.id, risk_assessment_id=assessment.id, ts=now,
            protocol_id=None, rationale_tr=NO_PROTOCOL_RATIONALE,
            proposed_actions=[], plan_source="empty"))

    doc_ctx = document_context()
    messages = [
        {"role": "system",
         "content": SYSTEM_PROMPT.format(
             tools="\n".join(_describe_tool(s) for s in TOOL_SCHEMAS),
             doc_context=doc_ctx)},
        {"role": "user", "content": _prompt(episode, assessment, candidates)},
    ]

    response = gw.ask("main", messages, schema=_PlanResponse,
                      tools=PLANNER_TOOL_SCHEMAS, max_tokens=PLANNER_MAX_TOKENS)

    calls = [] if response.degraded else _tool_calls(response)
    if calls:
        results = _run_tool_calls(gw, store, calls, ts=now)
        messages = [*messages, _assistant_turn(response), *results]
        # İkinci tur araçsız: nihai plan isteniyor, yeni bir tur değil.
        # Araçlar yine sunulsaydı model sonsuza dek araştırabilirdi.
        response = gw.ask("main", messages, schema=_PlanResponse,
                          max_tokens=PLANNER_MAX_TOKENS)

    parsed = None if response.degraded else _parse(response.content or "")

    if parsed is None:
        protocol = candidates[0]
        return _save(store, ActionPlan(
            episode_id=episode.id, risk_assessment_id=assessment.id, ts=now,
            protocol_id=protocol.protocol_id,
            rationale_tr=FALLBACK_RATIONALE.format(title=protocol.title_tr),
            proposed_actions=_from_protocol(protocol),
            plan_source="protocol_fallback"))

    # Uydurulmuş protokol kimliği reddedilir: aday listesinde olmayan bir
    # kimlik raporda "prosedür uygulandı" diye görünürdü.
    known = {p.protocol_id for p in candidates}
    protocol_id = parsed.protocol_id if parsed.protocol_id in known else None

    # Uydurulmuş araç adları düşürülür, Nöbetçi'ye asla iletilmez.
    actions = [a for a in parsed.proposed_actions if a.tool_name in TOOLS]

    return _save(store, ActionPlan(
        episode_id=episode.id, risk_assessment_id=assessment.id, ts=now,
        protocol_id=protocol_id, rationale_tr=parsed.rationale_tr,
        proposed_actions=actions, plan_source="model"))


def _save(store, plan: ActionPlan) -> ActionPlan:
    """Planı kaydeder ve iki devri deftere yazar.

    İKİ devir, çünkü planlayıcı zincirin bir DURAĞI: gelen kenar
    (risk analistinden) ve giden kenar (Nöbetçi'ye) ayrı ayrı görünmezse
    trace paneli yeni ajanı zincirin dışında, kopuk bir kutu olarak çizer.
    """
    plan.id = store.save_action_plan(plan)
    store.save_handoff(Handoff(
        ts=plan.ts, source_agent="risk_analyst", target_agent="action_planner",
        reason=f"plan isteniyor: episode {plan.episode_id}", confidence=0.9,
        payload_ref=f"risk:{plan.risk_assessment_id}"))
    store.save_handoff(Handoff(
        ts=plan.ts, source_agent="action_planner", target_agent="supervisor",
        reason=f"plan: {plan.protocol_id or '(prosedür yok)'} "
               f"— {len(plan.proposed_actions)} öneri",
        confidence=0.85, payload_ref=f"plan:{plan.id}"))
    return plan
