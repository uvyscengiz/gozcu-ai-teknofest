"""Risk analisti — riski biçen, gerekçesini yazan ve **ne yapılacağını**
söyleyen uzman.

Üç tasarım kuralı belirleyici:

**Analist gerçekten araştırıyor.** Tek bir model çağrısı, arşiv metninden
kapılan belirsiz bir cümleden fazlasını üretemez: "fren bakımı dört ay
gecikmiş" hiçbir fikstür dosyasında **yazmıyor**, Görev 09'un
`overdue_maintenance_months` fonksiyonu onu tarihlerden hesaplıyor ve o sayıya
yalnız `query_equipment_history` çağrılırsa ulaşılır. Bu yüzden burada gerçek
bir araç turu var: modele okuma araçları sunuluyor, çağırdıklarını
çalıştırıyoruz, sonuçları geri veriyoruz ve nihai değerlendirme ikinci turda
çıkıyor. Görev 12'nin kök neden raporu bu sayıyı iddia ediyor; ulaşılamayan
bir sayıyı iddia etmek uydurmak olurdu.

**Analist yalnızca OKUYABİLİR.** `READ_TOOLS` dışındaki her çağrı reddediliyor.
Bir analiz yan etkisiyle hat durduramaz ya da sağlık ekibi sevk edemez;
müdahale araçları `proposed_actions` olarak Nöbetçi'ye öneriliyor ve Görev
14'ün onay akışında yürütülüyor. Öneren ile yürüten aynı adım olursa insan
döngüdeki onay tiyatroya döner.

**Her aday aksiyon gerçek bir araca bağlı.** Sistemin çalıştıramayacağı bir
öneri sadece bir cümledir; uydurulmuş araç adı taşıyan öneri sessizce düşer.

Araçlara giden tek kapı `registry.call_tool` — `field_systems` fonksiyonları
doğrudan çağrılabilir ama doğrudan çağrılan araç **aksiyon defterine hiç
düşmez**, ve defter jürinin okuduğu şey.
"""

import json

from pydantic import BaseModel, ConfigDict, Field

from gozcu.agents.interpreter import _sanitize_text
from gozcu.agents.router import mmss
from gozcu.memory import search_timeline
from gozcu.models import (Episode, Handoff, ProposedAction, RiskAssessment,
                          RiskLevel)
from gozcu.tools.registry import TOOL_SCHEMAS, TOOLS, call_tool

# `RiskAssessment.rationale_tr` ve `ProposedAction.description_tr` ile aynı
# sınırlar. Şema sertleştirmesi `maxLength`'i telden söküyor (bkz.
# `gozcu.gateway.strict_schema`), yani model ikisini de aşabilir; kesme
# doğrulamadan ÖNCE Python tarafında yapılıyor.
MAX_RATIONALE = 800
MAX_ACTION_DESCRIPTION = 200

#: Analistin çağırabildiği araçlar — ikisi de okuma. Beş müdahale aracı
#: bilerek dışarıda: bkz. modül docstring'i.
#: Analistin kendi token tavanı. `main` kademesi şemalı JSON'da uzun akıl
#: yürütme izi üretiyor: 26 Ağustos'ta canlı ölçüldü — KÜÇÜK bir sentez
#: isteminde 4675-8513 token harcadı ve bir denemede 8192'lik varsayılan
#: tavanı tüketip BOŞ döndü. Risk istemi ondan büyük (olay + arşiv +
#: düzeltmeler); varsayılanla değerlendirme sessizce yedeğe düşer ve `risk`
#: şartnamenin puanlanan dört anahtarından biri. Raportör (`reporter.
#: REPORT_MAX_TOKENS`) aynı sebeple kendi tavanını taşıyor.
RISK_MAX_TOKENS = 16384

READ_TOOLS = ("query_shift_personnel", "query_equipment_history")

#: Modele araç olarak sunulan şemalar. `TOOL_SCHEMAS`'ın süzülmüş hâli —
#: sunulmayan bir aracı model çağıramaz, çağırırsa da `_run_tool_calls`
#: reddeder (iki katman, çünkü sunulmamak bir garanti değil).
READ_TOOL_SCHEMAS = [s for s in TOOL_SCHEMAS
                     if s["function"]["name"] in READ_TOOLS]

# Yedek gerekçeler. Üçü bilerek farklı: denetim kaydı "kademe sustu",
# "kademe boş yanıt döndü" ve "yanıt okunamadı" ayrımını görebilmeli. Aynı
# metni paylaşsalardı `degraded` guard'ı sessizce ölü koda dönerdi —
# `json.loads("")` zaten patlayıp okunamayan dala düşüyor ve fark hiçbir yerde
# görünmüyordu.
DEGRADED_RATIONALE = "Risk analiz katmanı yanıt vermiyor; ön risk korundu."
EMPTY_RATIONALE = "Risk analiz katmanı boş yanıt döndürdü; ön risk korundu."
UNREADABLE_RATIONALE = "Risk analizi üretilemedi; ön risk korundu."

REFUSAL_REASON = ("Analist yalnızca okuma araçlarını çağırabilir. Müdahale "
                  "araçları öneri olarak Nöbetçi'ye iletilir ve operatör "
                  "onayıyla yürütülür.")


def _describe_tool(schema: dict) -> str:
    """Bir araç şemasını prompt satırlarına çevirir — **şemadan türeterek**.

    Prompt tek başına araç ADLARINI sayarsa parametreler ve enum değerleri
    modele hiç ulaşmaz: `dispatch_medical`'in `urgency` alanı `("normal",
    "critical")` ile sınırlı, ama Türkçe promptla çalışan bir model gayet
    doğal olarak `"kritik"` yazar ve o sevk deftere `unrecognised_urgency`
    bırakır. CLAUDE.md'nin kuralı — prompt bir enum sayıyorsa değerleri
    şemadakiyle birebir aynı olmalı — burada elle kopyalayarak değil,
    **tek kaynaktan okuyarak** tutuluyor; iki sözlüğün ayrışması mümkün değil.
    """
    function = schema["function"]
    lines = [f"- {function['name']}: {function['description']}"]
    properties = function["parameters"]["properties"]
    required = set(function["parameters"].get("required", ()))
    for name, spec in properties.items():
        note = "" if name in required else " (isteğe bağlı)"
        values = spec.get("enum")
        if values:
            note += (" — TAM OLARAK şu değerlerden biri: "
                     + ", ".join(f'"{v}"' for v in values))
        lines.append(f"    {name}{note}")
    return "\n".join(lines)


#: Promptun araç kataloğu. Yedi aracın hepsi burada — analist yalnız ikisini
#: çağırabilir ama BEŞİNİ önerebilir, dolayısıyla parametrelerini bilmek
#: zorunda.
TOOL_CATALOGUE = "\n".join(_describe_tool(s) for s in TOOL_SCHEMAS)

SYSTEM_PROMPT = """Sen bir savunma sanayi üretim tesisinin iş güvenliği uzmanısın.
Sana bir olay ve arşivden gelen benzer geçmiş olaylar verilir.

Görevin:
- Risk seviyesini belirle — tam olarak şu dördünden biri: Düşük, Orta, Yüksek,
  Kritik
- Gerekçeni Türkçe, kısa cümlelerle yaz. Kamera verisine dayan.
- KESİN HÜKÜM VERME. "olası", "muhtemelen", "görüntüye dayanarak" kullan.
- Önlenebilir olup olmadığını söyle
- Operatör düzeltmesi varsa DÜZELTİLMİŞ hâli esas al

ÖNCE ARAŞTIR: sana verilen okuma araçlarını çağırabilirsin. Olaydaki ekipman
ve personel kimlikleri KATILIMCILAR satırında yazıyor; bakım gecikmesi ya da
vardiya bilgisi gerekiyorsa uydurma, aracı çağır. Sonuçlar geldikten sonra
değerlendirmeni yaz.

Her aksiyon önerisini SADECE aşağıdaki araçlardan birine bağla. Araç adını ve
parametre değerlerini burada yazdığı gibi, birebir kullan:
{tools}

Var olmayan bir araç adı uydurma. Değerlendirmeyi yazarken sadece JSON
döndür."""


class _RiskResponse(BaseModel):
    """Modelin döndürdüğü şekil.

    `RiskAssessment`'ten ayrı, çünkü onun `id` ve `episode_id` alanları var ve
    katı şema modunda her alan `required` oluyor — yani model kendi veritabanı
    kimliğini uydurmak zorunda kalırdı.
    """

    model_config = ConfigDict(extra="forbid")

    level: RiskLevel
    rationale_tr: str = Field(max_length=MAX_RATIONALE)
    preventable: bool
    proposed_actions: list[ProposedAction] = Field(default_factory=list)


def _fallback(episode: Episode, rationale_tr: str) -> _RiskResponse:
    """Analiz okunamadığında epizot yine de bir değerlendirme kazanır.

    Ön risk korunuyor: analiz katmanı sustu diye "Düşük" demek, riski
    olmadığı yere düşürmek olurdu.
    """
    return _RiskResponse(level=episode.preliminary_risk,
                         rationale_tr=rationale_tr, preventable=False)


def _sanitize_action(action):
    """Bir `proposed_actions` girdisinin açıklamasını sınıra çeker.

    Üst düzey `rationale_tr` kesilip iç içe açıklama kesilmezse tek uzun bir
    öneri bütün değerlendirmeyi doğrulama hatasına düşürür — ve kaybedilen
    şey öneri değil, analizin tamamı olur.
    """
    if not isinstance(action, dict):
        return action
    description = action.get("description_tr")
    if not isinstance(description, str):
        return action
    return {**action,
            "description_tr": _sanitize_text(description,
                                             MAX_ACTION_DESCRIPTION)}


def _parse(content: str) -> _RiskResponse | None:
    """Modelin ham çıktısını doğrulanmış bir yanıta çevirir; olmazsa `None`.

    İçeriğin iyi biçimli JSON olduğu varsayılmıyor: `ask()` şemalı istek
    tükendiğinde şemasız bir son deneme yapıyor (Görev 03), dolayısıyla düz
    metin de gelebilir.
    """
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
        return _RiskResponse(**data)
    except Exception:  # noqa: BLE001 — bozuk çıktı bir koşuyu düşürmemeli
        return None


def _read_assessment(response, episode: Episode) -> _RiskResponse:
    """Yanıtı değerlendirmeye çevirir; her arıza kendi yedek metnine düşer."""
    if response.degraded:
        return _fallback(episode, DEGRADED_RATIONALE)
    if not (response.content or "").strip():
        return _fallback(episode, EMPTY_RATIONALE)
    parsed = _parse(response.content)
    return parsed if parsed is not None else _fallback(episode,
                                                       UNREADABLE_RATIONALE)


def _tool_calls(response) -> list[dict]:
    """Yanıttaki araç çağrıları — hiç yoksa boş liste.

    Körlemesine indekslenmiyor: bozulmuş yanıt `tool_calls=[]` taşıyor ve
    `ask()` şemasız son denemeden de cevap verebiliyor (Görev 03).
    """
    calls = getattr(response, "tool_calls", None) or []
    return [c for c in calls if isinstance(c, dict)]


def _call_arguments(call: dict) -> tuple[str | None, dict]:
    """`(araç adı, parametreler)`; okunamayan argüman boş sözlüğe düşer."""
    function = call.get("function") or {}
    if not isinstance(function, dict):
        return None, {}
    raw = function.get("arguments")
    if isinstance(raw, dict):
        return function.get("name"), raw
    try:
        parsed = json.loads(raw or "{}")
    except (ValueError, TypeError):
        parsed = {}
    return function.get("name"), parsed if isinstance(parsed, dict) else {}


def _run_tool_calls(store, calls: list[dict], ts: float) -> list[dict]:
    """Okuma araçlarını çalıştırır, sonuçları model mesajlarına çevirir.

    Yürütme `call_tool` üzerinden geçiyor — tek meşru giriş noktası o, ve
    aksiyon defterine yazan da o. `ts` **videonun zamanı**: defterdeki "ajan
    ne zaman araştırdı" sorusunun anlamlı cevabı sunucu saati değil,
    görüntüdeki an.

    Reddedilen çağrı deftere HİÇ düşmüyor: olmamış bir aksiyon defterde
    görünmemeli. Reddin kendisi modele geri söyleniyor ki ikinci turda o
    aracı öneri olarak yazsın.
    """
    messages = []
    for call in calls:
        name, params = _call_arguments(call)
        if name in READ_TOOLS:
            try:
                # `caller` şart: bu çağrılar süpervizör daha ağzını
                # açmadan deftere düşüyor ve varsayılan onları ona yazardı.
                result = call_tool(store, name, params, ts=ts,
                                   caller="risk_analyst")
            except Exception as error:  # noqa: BLE001 — bozuk argüman koşuyu düşürmemeli
                result = {"tool_name": name, "failed": True,
                          "error": str(error)}
        else:
            result = {"tool_name": name, "refused": True,
                      "reason": REFUSAL_REASON}
        messages.append({"role": "tool", "tool_call_id": call.get("id", ""),
                         "name": name,
                         "content": json.dumps(result, ensure_ascii=False,
                                               default=str)})
    return messages


def _assistant_turn(response) -> dict:
    """Modelin araç çağıran turu — ikinci istekte geçmişte durmalı, yoksa
    `tool` rolündeki mesajların bağlandığı çağrı ortada kalır."""
    return {"role": "assistant", "content": response.content or None,
            "tool_calls": response.tool_calls}


def _prompt(episode: Episode, history_text: str, correction_text: str) -> str:
    participants = ", ".join(episode.participants) or "(bilinmiyor)"
    if episode.summary_source == "fallback":
        # Arıza metni bir olay tarifi değildir (spec §1): analiz yedek özete
        # değil, yorumlayıcının GERÇEK çıktısı olan ham anlara dayanır. Ama
        # an da yoksa (yorumlama hiç çalışmadıysa `beats` boş kalır) "aşağıdaki
        # ham anlara dayan" diye bir vaatte bulunmuyoruz — tutulmayan bir vaat
        # arıza metninden daha az yalan değildir.
        if episode.beats:
            lines = ["OLAY: (olay tarifi üretilemedi; aşağıdaki ham anlara dayan)"]
            lines += [f"- {mmss(beat.ts)} {beat.text}" for beat in episode.beats]
        else:
            lines = ["OLAY: (olay tarifi üretilemedi)"]
    else:
        lines = [f"OLAY: {episode.summary_tr}"]
    lines += [f"ÖN RİSK: {episode.preliminary_risk}",
              f"KATILIMCILAR (ekipman/personel kimlikleri): {participants}"]
    if correction_text:
        lines.append(correction_text)
    lines.append(f"\nARŞİV:\n{history_text}")
    return "\n".join(lines)


def assess_risk(gw, store, episode: Episode) -> RiskAssessment:
    """Epizodu değerlendirir, kaydeder ve süpervizöre devreder.

    Akış: arşive bak → modele sor (okuma araçlarıyla) → çağırdığı araçları
    defter üzerinden çalıştır → sonuçlarla ikinci kez sor → süz, kaydet,
    devret.

    Araç turu **isteğe bağlı**: model hiçbir şey çağırmazsa ya da kademe
    bozuksa tek çağrılık değerlendirmeye düşülür. Bir kesinti bir koşuyu
    düşürmemeli (CLAUDE.md çıktı sözleşmesi).
    """
    if episode.summary_source == "fallback":
        # Arşiv arıza metniyle aranmaz — 26 Ağu koşusunda o metin gömüldü ve
        # emsal araması zehirlendi. Anlar gerçek gözlem; an yoksa arama yok.
        query = " ".join([*(beat.text for beat in episode.beats),
                          *episode.participants]).strip()
    else:
        query = f"{episode.summary_tr} {' '.join(episode.participants)}"
    history = (search_timeline(gw, store, query, exclude_id=episode.id)
               if query else [])
    history_text = "\n".join(f"- {e.summary_tr}" for e in history) or "- (kayıt yok)"

    corrections = store.corrections(episode.id) if episode.id else []
    correction_text = "\n".join(
        f"- OPERATÖR DÜZELTMESİ — {c.field}: '{c.old}' yerine '{c.new}'"
        for c in corrections)

    messages = [
        {"role": "system",
         "content": SYSTEM_PROMPT.format(tools=TOOL_CATALOGUE)},
        {"role": "user",
         "content": _prompt(episode, history_text, correction_text)},
    ]

    response = gw.ask("main", messages, schema=_RiskResponse,
                      tools=READ_TOOL_SCHEMAS,
                      max_tokens=RISK_MAX_TOKENS)

    # Videonun "şimdi"si: 882f3b3'ün süpervizöre getirdiği kuralın aynısı.
    # `start_ts` uzun bir olayda saati olayın başında dondurur.
    now = episode.end_ts or episode.start_ts

    calls = [] if response.degraded else _tool_calls(response)
    if calls:
        results = _run_tool_calls(store, calls, ts=now)
        messages = [*messages, _assistant_turn(response), *results]
        # İkinci tur araçsız: nihai değerlendirme isteniyor, yeni bir tur
        # değil. Araçlar yine sunulsaydı model sonsuza dek araştırabilirdi.
        response = gw.ask("main", messages, schema=_RiskResponse,
                          max_tokens=RISK_MAX_TOKENS)

    parsed = _read_assessment(response, episode)

    # Uydurulmuş araç adları düşürülür, süpervizöre asla iletilmez.
    actions = [a for a in parsed.proposed_actions if a.tool_name in TOOLS]

    assessment = RiskAssessment(
        episode_id=episode.id, ts=now, level=parsed.level,
        rationale_tr=parsed.rationale_tr, preventable=parsed.preventable,
        proposed_actions=actions)
    assessment.id = store.save_risk(assessment)

    store.save_handoff(Handoff(ts=now,
                               source_agent="risk_analyst",
                               target_agent="supervisor",
                               reason=f"risk: {parsed.level}", confidence=0.85,
                               payload_ref=f"risk:{assessment.id}"))
    return assessment
