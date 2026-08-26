"""Raportör — olay kapandığında bir **insanın** okuyacağı kök neden raporu.

Demo'nun kapanış anı bu. Malzeme zaten depoda: olay zinciri, risk
değerlendirmeleri, operatörün yaptığı düzeltmeler, çağrılan saha sistemleri ve
diyalog dökümü. Buradaki iş onları tek bir Türkçe rapora dönüştürmek.

**Bu rapor nereye gidiyor.** `generate_root_cause_report()` bir
`RootCauseReport` döndürür ve **hiçbir şey kaydetmez** — deposu yok, çağıran
onu istediği gibi kullanır. Görev 17'nin boru hattı iki şey yapıyor:

- `what_happened` şartnamenin dört anahtarından biri olan **`summary`** hâline
  gelir. Yani bu alan bir iç metin değil, jürinin okuduğu ilk cümledir.
- Raporun tamamı `detail.root_cause_report` altında **düz bir `dict`** olarak
  teslim edilir: `Detail.root_cause_report` `dict | None` tipli, dolayısıyla
  çağıran `.model_dump()` uygular. Model nesnesi oraya doğrudan konmaz.

Raporu belirleyen dört kural:

**Operatör düzeltmesi kazanır.** Operatör "araç devrilmedi, yük düştü" dediyse
rapor da yük düştü der. Düzeltme bölümü eski değeri GEÇERSİZ diye işaretliyor;
ikisini yan yana koyup hangisinin geçerli olduğunu söylememek modele seçim
bırakmak olurdu. Rapora ulaşmayan bir düzeltme hiçbir şey yapmamış bir
düzeltmedir — ve orası puanın %20'sini taşıyan diyalog kalemi.

**Her sayı kanıta dayanır.** Raporun iddia ettiği "4 ay gecikmiş fren bakımı"
hiçbir fikstür dosyasında yazmıyor: `query_equipment_history` onu bakım
vadeleriyle senaryo tarihinden **türetiyor** ve çağrı aksiyon defterine
videonun zamanıyla düşüyor (Görev 09/11). Defter prompta olduğu gibi giriyor
ve `GROUNDING_RULE` modele sayıların kaynağını yazdırıyor. Bu kural olmadan
model aynı sayıyı arşiv metnindeki bulanık "gecikmiş bakım" ifadesinden
uydurabilir — ve raporu defterle karşılaştıran bir jüri dayanaksız bir iddia
bulur.

**Kesin hüküm yok.** Kamera bir kazanın sebebine hükmedemez. Rapor "muhtemel
kök neden" der ve `confidence_limits` alanında neyi bilemeyeceğini açıkça
yazar. Model o alanı boş bırakırsa `MISSING_CONFIDENCE_LIMITS` devreye girer:
boş bir sınırlar alanı pydantic'ten sessizce geçer ve rapor kendini mutlak bir
hüküm gibi sunardı.

**Promptun alan listesi şemadan türer.** Prompt bir zamanlar
`guven_sinirlari` diyordu; şemadaki ad `confidence_limits`. Model var olmayan
bir anahtarı doldurur, o anahtar atılır ve gerçek alan boş kalırdı. Elle
yazılan liste ayrışır, türetilen liste ayrışamaz.
"""

import json

from pydantic import BaseModel, ConfigDict, Field

from gozcu.agents.interpreter import _sanitize_text
from gozcu.agents.router import mmss

# `RootCauseReport` alan sınırları. Şema sertleştirmesi `maxLength`'i telden
# söküyor (bkz. `gozcu.gateway.strict_schema`), yani model üçünü de aşabilir;
# kesme doğrulamadan ÖNCE Python tarafında yapılıyor. Sınırın modele ulaşan
# tek kopyası promptun alan kataloğu.
MAX_WHAT_HAPPENED = 800
MAX_ROOT_CAUSE = 600
MAX_CONFIDENCE_LIMITS = 400

#: Raportörün kendi tavanı. Koşu başına BİR kez çalışır, girdisi en büyük
#: prompt (epizotlar + riskler + defter + diyalog) ve 26 Ağustos'ta 4096'yı
#: da tükettiği ölçüldü. Burada duruyor ki iki çağıran da — boru hattı ve
#: süpervizörün GENERATE_ROOT_CAUSE_REPORT iç aracı — aynı tavanı alsın.
REPORT_MAX_TOKENS = 16384

#: Promptun bölüm başlıkları. Sistem mesajı da kullanıcı mesajı da BURADAN
#: okuyor: kural metni "AKSİYON DEFTERİ'ne bak" derken başlık başka bir şey
#: yazıyorsa model neye bakacağını bilemez.
SECTION_EPISODES = "OLAY ZİNCİRİ"
SECTION_RISKS = "RİSK DEĞERLENDİRMELERİ"
SECTION_CORRECTIONS = "OPERATÖR DÜZELTMELERİ"
SECTION_LEDGER = "AKSİYON DEFTERİ"
SECTION_DIALOGUE = "DİYALOG"
SECTIONS = (SECTION_EPISODES, SECTION_RISKS, SECTION_CORRECTIONS,
            SECTION_LEDGER, SECTION_DIALOGUE)

EMPTY_SECTION = "- (yok)"

# Yedek metinler. Üçü bilerek farklı: operatörün okuduğu şey de denetim kaydı
# da "kademe sustu", "kademe boş yanıt döndü" ve "yanıt okunamadı" ayrımını
# görebilmeli — üçü farklı arızalar ve farklı müdahale gerektiriyor. Aynı
# kabuğu paylaşsalardı `degraded` guard'ı sessizce ölü koda dönerdi:
# `json.loads("")` zaten patlayıp okunamayan dala düşüyor ve fark hiçbir yerde
# görünmüyordu.
DEGRADED_REASON = "Rapor katmanı yanıt vermiyor"
EMPTY_REASON = "Rapor katmanı boş yanıt döndürdü"
UNREADABLE_REASON = "Rapor yanıtı okunamadı"

#: Model `confidence_limits`'i boş bırakırsa rapor yine de neyi bilemediğini
#: söyler. "Kesin hüküm yok" kuralının tek somut karşılığı bu alan.
MISSING_CONFIDENCE_LIMITS = (
    "Rapor kendi sınırlarını yazmadı. Bu rapor yalnızca kamera görüntüsüne, "
    "aksiyon defterine ve operatör beyanına dayanır; görüntünün dışında kalan "
    "hiçbir nedeni doğrulayamaz ve kesin hüküm taşımaz.")

#: Sayıların kaynağını zorunlu kılan kural. `gozcu.agents.risk` aynı ilkeyi
#: analiz tarafında uyguluyor ("uydurma, aracı çağır"); rapor tarafında
#: karşılığı bu: araç zaten çağrıldı, sonucu defterde — rapor oradan alacak.
GROUNDING_RULE = (
    f"HER SAYIYI, TARİHİ VE KİMLİĞİ KANITA DAYANDIR. Rapordaki her rakam, her "
    f"tarih ve her ekipman/personel kimliği sana verilen bölümlerden birinde "
    f"geçmek zorunda — özellikle {SECTION_LEDGER} bölümündeki araç "
    f"sonuçlarında. Bir sayıyı kullanırken hangi kayıttan aldığını cümle "
    f"içinde belirt. Dayanağı olmayan bir sayıyı TAHMİN ETME, YUVARLAMA ve "
    f"arşiv metninden ÇIKARIM YAPMA; onun yerine 'kayıtlarda bu veri yok' "
    f"yaz.")


#: Yokluk hükmü yasağı. Ölçülen arıza (25 Ağustos, raf çökmesi klibi): algı
#: katmanı altı kutunun altısını da düşürmüşken rapor "dış etki
#: kaydedilmedi" yazdı ve kök nedeni "yapısal yorgunluk" diye uydurdu. İkisi
#: de aynı hatanın iki yüzü — **görmemek görmedi demektir, olmadı demek
#: değil.** `GROUNDING_RULE` sayıları kanıta bağlıyor; bu kural da yokluk
#: iddialarını.
ABSENCE_RULE = (
    "GÖRÜLMEYEN ŞEYİ 'OLMADI' DİYE YAZMA. Bir şey sana verilen bölümlerde "
    "geçmiyorsa doğru cümle 'kayıtlarda buna dair bir tespit yok'tur. "
    "'Dış etki yoktur', 'kimse yoktu', 'başka bir olay yaşanmadı' gibi bir "
    "YOKLUK HÜKMÜ verme; kamera görmediği şeyin olmadığını kanıtlamaz. "
    "Tespit edilmemiş bir şeyin yokluğunu kök neden iddiana DAYANAK YAPMA — "
    "bilinmeyeni elemek bir kanıt değildir.")


class RootCauseReport(BaseModel):
    """Raporun sözleşmesi.

    Alan açıklamaları burada duruyor çünkü promptun alan kataloğu **bu
    şemadan** üretiliyor: açıklamayı değiştirmek promptu da değiştirir, ikisi
    ayrışamaz.
    """

    model_config = ConfigDict(extra="forbid")

    what_happened: str = Field(
        max_length=MAX_WHAT_HAPPENED,
        description="Ne oldu, nerede, kim vardı. Kayda dayanan kısa cümleler. "
                    "Bu metin operatörün okuduğu olay özetidir.")
    probable_root_cause: str = Field(
        max_length=MAX_ROOT_CAUSE,
        description="MUHTEMEL kök neden ve dayandığı kanıt. Kesin hüküm verme.")
    actions_taken: list[str] = Field(
        default_factory=list,
        description="Olay sırasında GERÇEKTEN yürütülen aksiyonlar; sadece "
                    "aksiyon defterinde görünenler. Her madde tek cümle.")
    prevention_recommendations: list[str] = Field(
        default_factory=list,
        description="Tekrarını önleyecek somut öneriler. Her madde tek cümle.")
    confidence_limits: str = Field(
        max_length=MAX_CONFIDENCE_LIMITS,
        description="Bu raporun NEYİ BİLEMEDİĞİ. Kamera verisinin göremediği "
                    "ve kayıtların cevaplamadığı şeyleri açıkça yaz. Algı "
                    "katmanının hiç tespit üretemediği bir aralık varsa onu "
                    "da buraya yaz; sessizlik bir bulgu değildir.")


_SCHEMA = RootCauseReport.model_json_schema()

#: Şemadaki JSON tiplerinin Türkçe karşılıkları — prompt satırı için.
_TYPE_NAMES = {"string": "metin", "array": "metin listesi",
               "integer": "tam sayı", "number": "sayı",
               "boolean": "evet/hayır"}


def _describe_field(name: str, spec: dict, required: bool) -> str:
    """Bir şema alanını prompt satırına çevirir — **şemadan türeterek**.

    Elle yazılmış bir alan listesi şemadan ayrışır; bu liste ayrışamaz. Sınır
    (`maxLength`) de buradan geliyor: `strict_schema()` onu telden söktüğü
    için modelin sınırı öğrenebileceği tek yer prompt metni.
    """
    notes = [_TYPE_NAMES.get(spec.get("type"), "metin")]
    limit = spec.get("maxLength")
    if limit:
        notes.append(f"en fazla {limit} karakter")
    if not required:
        notes.append("boş bırakılabilir")
    return f"- {name} ({', '.join(notes)}): {spec['description']}"


#: Promptun alan kataloğu. `RootCauseReport`'a bir alan eklendiği an prompt da
#: onu saymaya başlar.
FIELD_CATALOGUE = "\n".join(
    _describe_field(name, spec, name in set(_SCHEMA.get("required", ())))
    for name, spec in _SCHEMA["properties"].items())

_SYSTEM_TEMPLATE = """Sen bir savunma sanayi üretim tesisinin olay inceleme raportörüsün.
Sana kapanmış bir olayın tam kaydı verilir: {sections}. Bu kayda dayanarak bir
kök neden raporu yaz. Raporu bir vardiya amiri okuyacak.

Kurallar:
- Türkçe yaz. Kısa cümleler, saha terminolojisi: istif aracı, vardiya amiri,
  yerde hareketsiz kişi.
- Edilgen çatıdan kaçın. "Yük düştü" de; "yükün düşmüş olduğu görülmektedir"
  deme.
- KESİN HÜKÜM VERME. Kamera bir kazanın sebebine hükmedemez. "Olası",
  "muhtemelen", "görüntüye dayanarak" kullan.
- {absence}
- Operatör düzeltmesi varsa DÜZELTİLMİŞ hâli esas al. {corrections} bölümünde
  hangi değerin geçerli olduğu yazıyor; GEÇERSİZ işaretli eski değeri rapora
  taşıma.
- {grounding}

Raporun alanları — tam olarak bu adlarla doldur, başka anahtar ekleme:
{fields}

Sadece JSON döndür."""

SYSTEM_PROMPT = _SYSTEM_TEMPLATE.format(sections=", ".join(SECTIONS),
                                        corrections=SECTION_CORRECTIONS,
                                        absence=ABSENCE_RULE,
                                        grounding=GROUNDING_RULE,
                                        fields=FIELD_CATALOGUE)

#: Kesilecek alanlar ve sınırları — **şemadan** okunuyor, elle sayılmıyor.
#: Uzunluk sınırlı bir alan eklendiğinde kesme kendiliğinden onu da kapsar.
LENGTH_LIMITS = {name: spec["maxLength"]
                 for name, spec in _SCHEMA["properties"].items()
                 if "maxLength" in spec}


def _dump(payload: dict) -> str:
    """Defter satırlarındaki sözlükleri okunur JSON'a çevirir.

    `ensure_ascii=False`: Türkçe karakterler kaçış dizisine dönerse modelin
    okuduğu kanıt metni bozulur.
    """
    return json.dumps(payload, ensure_ascii=False, default=str)


def _section(title: str, lines: list[str]) -> list[str]:
    """Bir bölüm başlığı ve satırları; satır yoksa açıkça '(yok)'.

    Boş bölüm atlanmıyor: atlanan bölüm modele "bu kayıt hiç tutulmadı" ile
    "bu olayda böyle bir kayıt yok" arasındaki farkı kaybettirir.
    """
    return [f"\n{title}:", *(lines or [EMPTY_SECTION])]


def _correction_line(correction) -> str:
    """Düzeltmeyi, hangi değerin geçerli olduğunu SÖYLEYEREK yazar.

    Eski ve yeni değeri yan yana koyup ikisini eşit sunmak modele seçim
    bırakır. Rapor operatörün düzelttiği değeri kullanmak zorunda.
    """
    return (f"- {correction.field}: GEÇERLİ DEĞER '{correction.new}' — "
            f"operatör düzeltti; eski değer '{correction.old}' GEÇERSİZ "
            f"({correction.rationale})")


def _episode_line(episode) -> str:
    """Kanıt dosyasının epizot satırı.

    Yedek özet kanıt DEĞİLDİR (spec §1): süpervizörün `NO_DESCRIPTION_NOTE`
    ile önlediği aynı uydurma, arıza metni OLAY ZİNCİRİ'ne olduğu gibi girerse
    raportör tarafında da olur — model onu fabrikada olmuş bir gözlem sanabilir.
    Onun yerine ham anlar yazılır: rapor gerçek gözleme dayanmalı, arıza
    metnine değil.
    """
    if episode.summary_source == "fallback":
        beats = "; ".join(f"{mmss(b.ts)} {b.text}" for b in episode.beats)
        line = (f"- {mmss(episode.start_ts)} [{episode.phase}] "
                f"(tarif üretilemedi — sentez arızası; ham anlar epizot "
                f"kaydında)")
        return f"{line} anlar: {beats}" if beats else line
    return f"- {mmss(episode.start_ts)} [{episode.phase}] {episode.summary_tr}"


def _prompt(store) -> str:
    """Depodaki her şeyi tek bir kanıt dosyasına toplar.

    Aksiyon defteri sonuçları BUDANMADAN giriyor: `query_equipment_history`
    çağrısının türetilmiş `overdue_maintenance_months` alanı raporun kök neden
    iddiasının tek dayanağı ve bir kısaltma onu düşürebilir.
    """
    episodes = store.episodes()
    parts: list[str] = []

    parts += _section(SECTION_EPISODES,
                      [_episode_line(episode) for episode in episodes])

    parts += _section(SECTION_RISKS, [
        f"- {r.level}: {r.rationale_tr}" for r in store.risks()])

    corrections = [c for e in episodes if e.id
                   for c in store.corrections(e.id)]
    parts += _section(SECTION_CORRECTIONS,
                      [_correction_line(c) for c in corrections])

    parts += _section(SECTION_LEDGER, [
        f"- {mmss(a.ts)} {a.tool_name}({_dump(a.params)}) → "
        f"{_dump(a.result)} [{a.approval}]" for a in store.actions()])

    parts += _section(SECTION_DIALOGUE, [
        f"- {mmss(t.ts)} {t.role}: {t.text}" for t in store.dialogue()])

    return "\n".join(parts)


def _fallback(reason: str) -> RootCauseReport:
    """Arıza hâlinde bile şartnamenin dört anahtarı üretilebilsin diye kabuk.

    Kabuk bir bulgu gibi okunmamalı: `confidence_limits` bunun bir arıza kaydı
    olduğunu açıkça söylüyor, yoksa "Belirlenemedi" cümlesi bir inceleme
    sonucu sanılır.
    """
    return RootCauseReport(
        what_happened=f"{reason}; olay zinciri, risk değerlendirmeleri ve "
                      f"aksiyon defteri depoda kayıtlıdır.",
        probable_root_cause="Belirlenemedi — rapor katmanı bir değerlendirme "
                            "üretmedi.",
        confidence_limits=f"{reason}. Bu metin bir bulgu değil, bir arıza "
                          f"kaydıdır: kök neden hiç incelenmemiştir.")


def _parse(content: str) -> RootCauseReport | None:
    """Modelin ham çıktısını doğrulanmış bir rapora çevirir; olmazsa `None`.

    İçeriğin iyi biçimli JSON olduğu varsayılmıyor: `ask()` şemalı istek
    tükendiğinde şemasız bir son deneme yapıyor (Görev 03), dolayısıyla düz
    metin de gelebilir.

    Kesme doğrulamadan ÖNCE: şemada `maxLength` olmadığı için taşma beklenen
    yoldur ve ham hâliyle pydantic'e verilen GERÇEK bir rapor kabuğa çökerdi —
    mock'larla yeşil, sahada hep kabuk.
    """
    try:
        data = json.loads(content)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    for name, limit in LENGTH_LIMITS.items():
        value = data.get(name)
        if isinstance(value, str):
            data[name] = _sanitize_text(value, limit)

    limits = data.get("confidence_limits")
    if not isinstance(limits, str) or not limits.strip():
        data["confidence_limits"] = MISSING_CONFIDENCE_LIMITS

    try:
        return RootCauseReport(**data)
    except Exception:  # noqa: BLE001 — bozuk çıktı bir koşuyu düşürmemeli
        return None


def generate_root_cause_report(gw, store) -> RootCauseReport:
    """Depodaki kaydı tek bir Türkçe kök neden raporuna dönüştürür.

    Rapor **döndürülür, kaydedilmez**: çağıran onu `detail.root_cause_report`
    altına `.model_dump()` ile koyar ve `what_happened`'i şartnamenin
    `summary` anahtarı olarak kullanır (Görev 17).

    Üç arıza dalı da açık ve üçü ayrı metin üretiyor. `degraded` kontrolü
    olmadan bozulmuş ama gövdeli bir yanıt (ör. önbellekten dönen bayat rapor)
    canlı bulgu gibi okunur; boş içerik kontrolü olmadan ise `json.loads("")`
    tesadüfen patladığı için "okunamadı" diye raporlanırdı — kademe aslında
    hiçbir şey söylememişken.
    """
    response = gw.ask("main", [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _prompt(store)},
    ], schema=RootCauseReport, max_tokens=REPORT_MAX_TOKENS)

    if response.degraded:
        return _fallback(DEGRADED_REASON)
    if not (response.content or "").strip():
        return _fallback(EMPTY_REASON)

    parsed = _parse(response.content)
    return parsed if parsed is not None else _fallback(UNREADABLE_REASON)
