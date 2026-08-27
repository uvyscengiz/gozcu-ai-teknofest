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
müdahale önerisi artık analistin işi değil — `action_planner`'ın işi (Görev
5/6). Analist yalnız riski biçer ve gerekçesini yazar; öneri üretimi ile onay
akışı (Görev 14) tamamen ayrı bir ajanın omuzlarında, çünkü öneren ile
yürüten aynı adım olursa insan döngüdeki onay tiyatroya döner — ve iki ajan
aynı işi yaparsa devir zinciri hangi ajanın neyi biçtiğini gizler.

Araçlara giden tek kapı `registry.call_tool` — `field_systems` fonksiyonları
doğrudan çağrılabilir ama doğrudan çağrılan araç **aksiyon defterine hiç
düşmez**, ve defter jürinin okuduğu şey.
"""

import json

from pydantic import BaseModel, ConfigDict, Field

from gozcu.agents.interpreter import _sanitize_text
from gozcu.agents.orchestrator import mmss
from gozcu.config import QDRANT_SCORE_THRESHOLD_RISK
from gozcu.memory import search_timeline
from gozcu.models import Episode, RiskAssessment, RiskLevel
from gozcu.tools.registry import TOOL_SCHEMAS, call_tool

# `RiskAssessment.rationale_tr`'nin sınırı. Şema sertleştirmesi
# `maxLength`'i telden söküyor (bkz. `gozcu.gateway.strict_schema`), yani
# model onu aşabilir; kesme doğrulamadan ÖNCE Python tarafında yapılıyor.
MAX_RATIONALE = 800

#: Analistin çağırabildiği araçlar — ikisi de okuma. Müdahale araçları
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


SYSTEM_PROMPT = """Sen bir savunma sanayi üretim tesisinin iş güvenliği uzmanısın.
Sana bir olay ve arşivden gelen benzer geçmiş olaylar verilir.

Görevin:
- Risk seviyesini belirle — tam olarak şu dördünden biri: Düşük, Orta, Yüksek,
  Kritik
- Gerekçeni Türkçe, kısa cümlelerle yaz. Kamera verisine dayan.
- KESİN HÜKÜM VERME. "olası", "muhtemelen", "görüntüye dayanarak" kullan.
- Önlenebilir olup olmadığını söyle
- Operatör düzeltmesi varsa DÜZELTİLMİŞ hâli esas al

ARŞİV KAYITLARI hakkında:
- Bir arşiv kaydı bir GEREKÇE değil, gerekçenin başlangıcıdır.
- Kayıt bir ekipman kimliği taşıyorsa `query_equipment_history` ile o
  ekipmanın geçmişini sorgula.
- Aynı ekipman ya da bölge tekrar ediyorsa bu bir ÖRÜNTÜDÜR; hangi kaydı
  gördüğünü yaz.
- Arşiv kaydı bu olayla ilgisizse KULLANMA ve ondan söz etme.
- Kamera ekipman kimliği OKUMAZ. Arşivdeki kaydın sahnedeki araca ait
  olduğunu VARSAYMA; "saha doğrulaması gerekir" biçiminde yaz.

ÖNCE ARAŞTIR: sana verilen okuma araçlarını çağırabilirsin. Olaydaki ekipman
ve personel kimlikleri KATILIMCILAR satırında yazıyor; bakım gecikmesi ya da
vardiya bilgisi gerekiyorsa uydurma, aracı çağır. Sonuçlar geldikten sonra
değerlendirmeni yaz.

Müdahale önerisi senin işin DEĞİL — sadece riski değerlendir. Değerlendirmeyi
yazarken sadece JSON döndür."""


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


def _fallback(episode: Episode, rationale_tr: str) -> _RiskResponse:
    """Analiz okunamadığında epizot yine de bir değerlendirme kazanır.

    Ön risk korunuyor: analiz katmanı sustu diye "Düşük" demek, riski
    olmadığı yere düşürmek olurdu.
    """
    return _RiskResponse(level=episode.preliminary_risk,
                         rationale_tr=rationale_tr, preventable=False)


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
    history = (search_timeline(gw, store, query,
                               exclude=(episode.source, episode.id),
                               threshold=QDRANT_SCORE_THRESHOLD_RISK)
               if query and episode.id is not None else [])
    history_text = "\n".join(f"- {p.episode.summary_tr}"
                             for p in history) or "- (kayıt yok)"

    corrections = store.corrections(episode.id) if episode.id else []
    correction_text = "\n".join(
        f"- OPERATÖR DÜZELTMESİ — {c.field}: '{c.old}' yerine '{c.new}'"
        for c in corrections)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
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

    assessment = RiskAssessment(
        episode_id=episode.id, ts=now, level=parsed.level,
        rationale_tr=parsed.rationale_tr, preventable=parsed.preventable,
        precedents=history)
    assessment.id = store.save_risk(assessment)

    # `risk_analyst → supervisor` devri BİLEREK yazılmıyor: zincirdeki bir
    # sonraki durak artık `action_planner` (Görev 6, spec §2d) ve o deviri
    # `action_planner._save` yazıyor (`risk_analyst → action_planner` ve
    # `action_planner → supervisor`). İkisi birden yazılsaydı aynı andan iki
    # kenar çıkar, trace paneli zinciri çatallı çizerdi.
    return assessment
