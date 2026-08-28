"""Risk analisti — riski biçen ve gerekçesini yazan uzman.

İki tasarım kuralı belirleyici:

**Analist gerçekten araştırıyor.** Tek bir model çağrısı, epizodun kendi
metninden kapılan belirsiz bir cümleden fazlasını üretemez. Bu yüzden gerçek
bir araç turu var — en fazla `MAX_TOOL_ROUNDS` (5) tur boyunca modele iki
okuma aracı (`search_timeline`, `search_documents`) sunuluyor, çağırdıklarını
çalıştırıyoruz, sonuçları geri veriyoruz. 6. tur YAPISAL OLARAK araçsız: model
sonsuza dek araştırıp değerlendirmeyi hiç vermeme riskine karşı bir güvenlik
ağı (§1e).

**Analist yalnızca OKUYABİLİR.** `RISK_TOOLS` dışındaki her çağrı reddediliyor.
Bir analiz yan etkisiyle hat durduramaz ya da sağlık ekibi sevk edemez;
müdahale önerisi artık analistin işi değil — `action_planner`'ın işi (Görev
5/6). Analist yalnız riski biçer ve gerekçesini yazar; öneri üretimi ile onay
akışı (Görev 14) tamamen ayrı bir ajanın omuzlarında, çünkü öneren ile
yürüten aynı adım olursa insan döngüdeki onay tiyatroya döner — ve iki ajan
aynı işi yaparsa devir zinciri hangi ajanın neyi biçtiğini gizler.

`search_timeline` ve `search_documents` **registry'den geçmiyor** —
`_run_tool_calls` onları doğrudan Python fonksiyonu olarak çağırıyor, çünkü
ikisi de bir alan aksiyonu değil (sahada hiçbir şeyi tetiklemiyor) ve aksiyon
defteri jürinin okuduğu şey; bir okuma orada bir aksiyon gibi görünmemeli.
"""

import json

from pydantic import BaseModel, ConfigDict, Field

from gozcu.agents.interpreter import _sanitize_text
from gozcu.agents.orchestrator import mmss
from gozcu.core.config import QDRANT_SCORE_THRESHOLD_RISK
from gozcu.core.models import Episode, Precedent, RiskAssessment, RiskLevel
from gozcu.memory import (SEARCH_DOCUMENTS_SCHEMA, SEARCH_TIMELINE_SCHEMA,
                          search_documents, search_timeline)
from gozcu.memory.library import document_context

# `RiskAssessment.rationale_tr`'nin sınırı. Şema sertleştirmesi
# `maxLength`'i telden söküyor (bkz. `gozcu.gateway.strict_schema`), yani
# model onu aşabilir; kesme doğrulamadan ÖNCE Python tarafında yapılıyor.
MAX_RATIONALE = 800

#: Analistin kendi token tavanı. `main` kademesi şemalı JSON'da uzun akıl
#: yürütme izi üretiyor: 26 Ağustos'ta canlı ölçüldü — KÜÇÜK bir sentez
#: isteminde 4675-8513 token harcadı ve bir denemede 8192'lik varsayılan
#: tavanı tüketip BOŞ döndü. Risk istemi ondan büyük (olay + araç sonuçları +
#: düzeltmeler); varsayılanla değerlendirme sessizce yedeğe düşer ve `risk`
#: şartnamenin puanlanan dört anahtarından biri. Raportör (`reporter.
#: REPORT_MAX_TOKENS`) aynı sebeple kendi tavanını taşıyor.
RISK_MAX_TOKENS = 16384

#: Modele araç olarak sunulan şemalar. Sunulmayan bir aracı model çağıramaz,
#: çağırırsa da `_run_tool_calls` reddeder (iki katman, çünkü sunulmamak bir
#: garanti değil).
RISK_TOOL_SCHEMAS = [SEARCH_TIMELINE_SCHEMA, SEARCH_DOCUMENTS_SCHEMA]

#: Dağıtımın tek eşleştirdiği adlar — **şemalardan türetiliyor.** Bu dalda
#: aynı iki ad üç yerde birden yazılıydı (beyaz liste, şemalar, dağıtımdaki
#: düz dizgiler) ve dağıtım beyaz listeye hiç bakmıyordu: modül
#: docstring'inin "`RISK_TOOLS` dışındaki her çağrı reddediliyor" cümlesi
#: bir yorumdu, kod değil. Bu proje bir kez tam olarak böyle bir ayrışmadan
#: sessizce ölmüştü; üç kopya bire indirildi.
SEARCH_TIMELINE_TOOL = SEARCH_TIMELINE_SCHEMA["function"]["name"]
SEARCH_DOCUMENTS_TOOL = SEARCH_DOCUMENTS_SCHEMA["function"]["name"]

#: Analistin çağırabildiği araçlar — ikisi de okuma, ikisi de registry'nin
#: DIŞINDA doğrudan Python çağrısı (bkz. modül docstring'i). Müdahale
#: araçları bilerek burada değil. `_run_tool_calls` beyaz listeyi GERÇEKTEN
#: okuyor: buradan çıkarılan bir ad reddedilir.
RISK_TOOLS = (SEARCH_TIMELINE_TOOL, SEARCH_DOCUMENTS_TOOL)

#: Araçlı turların üst sınırı. Döngü toplam `MAX_TOOL_ROUNDS + 1` tur sürer:
#: ilk `MAX_TOOL_ROUNDS` tanesi araçlı, sonuncusu YAPISAL OLARAK araçsız —
#: model sonsuza dek araştırıp değerlendirmeyi hiç vermeme riskine karşı bir
#: güvenlik ağı (§1e).
MAX_TOOL_ROUNDS = 5

#: Kalıcı `RiskAssessment.precedents`'in üst sınırı. Model artık
#: `search_timeline`'ı birden çok turda çağırabildiği için ham liste
#: `MAX_TOOL_ROUNDS × top_k`'ya kadar şişebilir (B8'in TEK ÇAĞRI için
#: çözdüğü ikizlenme burada bir kat yukarıda yeniden açılır).
#:
#: **`search_timeline`'ın `top_k` varsayılanıyla AYNI sayı olmalı** —
#: B6-öncesi tek ön-arama cetveli oydu ve cetvel değişmemeli. Bağ eskiden
#: `inspect.signature(...)` ile kuruluyordu; o varsayılan bir gün `None`
#: olsaydı `ranked[:None]` hiçbir şeyi kırpmayan bir dilime dönüşür ve
#: sınırsız-emsal arızası sessizce geri açılırdı. Sayı artık düz yazılı,
#: bağ ise `tests/test_risk.py::test_the_precedent_cap_is_pinned_and_
#: matches_search_timelines_top_k` tarafından tutuluyor.
MAX_PRECEDENTS = 5

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
Sana bir olay verilir; geçmiş olaylara ve operatör belgelerine araçlarla erişebilirsin.

Görevin:
- Risk seviyesini belirle — tam olarak şu dördünden biri: Düşük, Orta, Yüksek,
  Kritik
- Gerekçeni Türkçe, kısa cümlelerle yaz. Kamera verisine dayan.
- KESİN HÜKÜM VERME. "olası", "muhtemelen", "görüntüye dayanarak" kullan.
- Önlenebilir olup olmadığını söyle
- Operatör düzeltmesi varsa DÜZELTİLMİŞ hâli esas al

ARAÇLARIN:
- search_timeline: geçmiş olay arşivinde arama. Benzer olaylar olmuş mu bak.
- search_documents: operatörün yüklediği belgelerde arama. Ekipman kartı,
  vardiya listesi, prosedür gibi belgelerden bilgi çek.

Arama sonuçları hakkında:
- Bir arşiv kaydı bir GEREKÇE değil, gerekçenin başlangıcıdır.
- Aynı ekipman ya da bölge tekrar ediyorsa bu bir ÖRÜNTÜDÜR; hangi kaydı
  gördüğünü yaz.
- Sonuç bu olayla ilgisizse KULLANMA ve ondan söz etme.
- Kamera ekipman kimliği OKUMAZ. Arşivdeki kaydın sahnedeki araca ait
  olduğunu VARSAYMA; "saha doğrulaması gerekir" biçiminde yaz.

ÖNCE ARAŞTIR:
1. Olaydaki ekipman/personel hakkında arşivde ve belgelerde bilgi ara
2. Yeterli bilgi topladığında değerlendir — gereksiz yere döngüye girme

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


def _run_tool_calls(gw, store, calls: list[dict],
                    episode: Episode | None = None
                    ) -> tuple[list[dict], list[Precedent]]:
    """Okuma araçlarını çalıştırır — registry DEĞİL, doğrudan Python.

    `search_timeline` ve `search_documents` bir alan aksiyonu değil: sahada
    hiçbir şeyi tetiklemiyorlar, dolayısıyla `call_tool` üzerinden geçmiyorlar
    ve aksiyon defterine HİÇ düşmüyorlar (modül docstring'i).

    Reddedilen ya da tanınmayan bir araç adı da deftere düşmez; reddin
    kendisi modele geri söyleniyor ki sonraki turda o aracı öneri olarak
    yazsın.

    İkinci dönüş değeri — `search_timeline`'ın gerçekten getirdiği emsaller —
    `assess_risk`'in `RiskAssessment.precedents`'e yazması için. Emsal yalnız
    modele giden geçici bir araç mesajında kalırsa jüri onu HİÇ göremez;
    jüri prompt'u değil deftere düşen kaydı okuyor (B6).
    """
    messages = []
    precedents: list[Precedent] = []
    for call in calls:
        name, params = _call_arguments(call)
        if name not in RISK_TOOLS:
            result = {"tool_name": name, "refused": True,
                      "reason": REFUSAL_REASON}
        elif name == SEARCH_TIMELINE_TOOL:
            exclude = ((episode.source, episode.id)
                      if episode is not None and episode.id is not None
                      else None)
            found = search_timeline(
                gw, store, params.get("query", ""),
                exclude=exclude, threshold=QDRANT_SCORE_THRESHOLD_RISK)
            precedents.extend(found)
            result = {"results": [{"summary_tr": p.episode.summary_tr,
                                   "participants": p.episode.participants,
                                   "score": round(p.score, 3)}
                                  for p in found]}
        elif name == SEARCH_DOCUMENTS_TOOL:
            # `client` GEÇİLMİYOR ve bu bir ihmal değil: belgeleri YAZAN yol
            # (`embed_document`, `POST /api/library/documents`) `episodic.
            # _documents_handle`'ı kullanıyor. `client=store` geçmek
            # `_client()`'ı o depoya ait AYRI bir yerel Qdrant açmaya
            # zorluyordu; `documents` koleksiyonu orada hiç yoktu ve arama
            # tek bir iz bırakmadan boş dönüyordu.
            found = search_documents(gw, params.get("query", ""),
                                     threshold=QDRANT_SCORE_THRESHOLD_RISK)
            result = {"results": [{"name": r.name,
                                   "text_excerpt": r.text_excerpt,
                                   "score": round(r.score, 3)}
                                  for r in found]}
        else:
            # `RISK_TOOLS`'a ad eklenip bu dal unutulursa çağrı "yapılmış"
            # gibi görünmesin.
            result = {"tool_name": name, "error": "bilinmeyen araç"}
        messages.append({"role": "tool", "tool_call_id": call.get("id", ""),
                         "name": name,
                         "content": json.dumps(result, ensure_ascii=False,
                                               default=str)})
    return messages, precedents


def _assistant_turn(response) -> dict:
    """Modelin araç çağıran turu — ikinci istekte geçmişte durmalı, yoksa
    `tool` rolündeki mesajların bağlandığı çağrı ortada kalır."""
    return {"role": "assistant", "content": response.content or None,
            "tool_calls": response.tool_calls}


def _prompt(episode: Episode, correction_text: str) -> str:
    """Modele giden kullanıcı mesajı — arşiv artık gömülü DEĞİL (§7a).

    Eskiden `ARŞİV:` başlığı altında bir ön arama sonucu buraya enjekte
    ediliyordu; şimdi arşiv `search_timeline` aracıyla modelin kendi
    seçtiği sorguyla erişilen bir kaynak, prompt'a hazır metin olarak
    kakılmıyor. Yerine, gömülü belge varsa `document_context()` ekleniyor —
    hangi belgelerin `search_documents` ile erişilebilir olduğunu bilmek
    modelin kendi kararı için gerekli, ama belge İÇERİĞİ yine aracın işi."""
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
    doc_ctx = document_context()
    if doc_ctx:
        lines.append(f"\n{doc_ctx}")
    return "\n".join(lines)


def _rank_precedents(precedents: list[Precedent]) -> list[Precedent]:
    """Araç turlarında biriken emsalleri jüriye gitmeden ÖNCE tekilleştirir,
    skora göre İNEN sırada dizer, `MAX_PRECEDENTS`'e kırpar.

    Tekilleştirme anahtarı `Episode.source` — `search_timeline`'ın TEK
    ÇAĞRI içindeki kendi kuralıyla birebir aynı (B8,
    `gozcu.memory.episodic.search_timeline`): `source is None` olan noktalar
    KENDİ BAŞINA geçer (kökeni bilinmeyen ayrı epizotları tek emsale
    indirmemek için), diğerleri kaynak başına EN YÜKSEK skorda tutulur. Model
    aynı epizodu farklı sorgularla birden çok turda getirebildiği için bu
    kural burada, bir kat yukarıda, YENİDEN uygulanıyor — yoksa B8 turlar
    arasında geri açılır.

    Sıralama skora göre İNEN: `gozcu/agents/supervisor.py`
    `precedents[0]`'ı "en yakın kayıt" diye okuyor, bu artık modelin hangi
    sorguyu ÖNCE yazdığına değil, hangi emsalin skoru en yüksek olduğuna
    bağlı olmalı.
    """
    best: dict[str, Precedent] = {}
    unique: list[Precedent] = []
    for p in precedents:
        source = p.episode.source
        if source is None:
            unique.append(p)
            continue
        current = best.get(source)
        if current is None or p.score > current.score:
            best[source] = p
    ranked = sorted([*best.values(), *unique], key=lambda p: p.score,
                    reverse=True)
    return ranked[:MAX_PRECEDENTS]


def assess_risk(gw, store, episode: Episode) -> RiskAssessment:
    """Epizodu değerlendirir, kaydeder ve süpervizöre devreder.

    Akış: modele sor (okuma araçlarıyla) → çağırdığı araçları doğrudan
    çalıştır (registry DEĞİL, bkz. modül docstring'i) → sonuçlarla tekrar
    sor → ... → nihai değerlendirmeyi süz, kaydet.

    Döngü en fazla `MAX_TOOL_ROUNDS + 1` (6) tur sürer: ilk `MAX_TOOL_ROUNDS`
    (5) tanesi araçlı, sonuncusu YAPISAL OLARAK araçsız — model sonsuza dek
    araştırıp değerlendirmeyi hiç vermeme riskine karşı bir güvenlik ağı
    (§1e). Araç turu her adımda **isteğe bağlı**: model hiçbir şey
    çağırmazsa ya da kademe bozuksa döngü erken biter. Bir kesinti bir
    koşuyu düşürmemeli (CLAUDE.md çıktı sözleşmesi).
    """
    corrections = store.corrections(episode.id) if episode.id else []
    correction_text = "\n".join(
        f"- OPERATÖR DÜZELTMESİ — {c.field}: '{c.old}' yerine '{c.new}'"
        for c in corrections)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _prompt(episode, correction_text)},
    ]

    # Videonun "şimdi"si: 882f3b3'ün süpervizöre getirdiği kuralın aynısı.
    # `start_ts` uzun bir olayda saati olayın başında dondurur.
    now = episode.end_ts or episode.start_ts

    precedents: list[Precedent] = []
    response = None
    for turn in range(MAX_TOOL_ROUNDS + 1):
        is_last = (turn == MAX_TOOL_ROUNDS)
        if is_last:
            # Güvenlik ağı: araç SUNULMUYOR, model bu turda kaçınılmaz
            # olarak bir değerlendirme üretmek zorunda.
            response = gw.ask("main", messages, schema=_RiskResponse,
                              max_tokens=RISK_MAX_TOKENS)
            break
        response = gw.ask("main", messages, schema=_RiskResponse,
                          tools=RISK_TOOL_SCHEMAS,
                          max_tokens=RISK_MAX_TOKENS)
        if response.degraded:
            break
        calls = _tool_calls(response)
        if not calls:
            break
        results, found = _run_tool_calls(gw, store, calls, episode=episode)
        precedents.extend(found)
        messages = [*messages, _assistant_turn(response), *results]

    parsed = _read_assessment(response, episode)

    assessment = RiskAssessment(
        episode_id=episode.id, ts=now, level=parsed.level,
        rationale_tr=parsed.rationale_tr, preventable=parsed.preventable,
        precedents=_rank_precedents(precedents))
    assessment.id = store.save_risk(assessment)

    # `risk_analyst → supervisor` devri BİLEREK yazılmıyor: zincirdeki bir
    # sonraki durak artık `action_planner` (Görev 6, spec §2d) ve o deviri
    # `action_planner._save` yazıyor (`risk_analyst → action_planner` ve
    # `action_planner → supervisor`). İkisi birden yazılsaydı aynı andan iki
    # kenar çıkar, trace paneli zinciri çatallı çizerdi.
    return assessment
