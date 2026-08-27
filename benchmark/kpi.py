"""Ölçüm katmanı — depodaki kayıtlardan hesaplanan saf fonksiyonlar.

Bu modül fikstür, gateway, dosya sistemi ve ağ görmez: girdisi bir `Store`,
çıktısı sayılardır. Sunumun manşet grafiği (`decision_distribution`) buradan
çıkıyor, dolayısıyla buradaki yanlış bir sayı bir çökme değil — **sonuç gibi
görünen bir yalan** olurdu. Üç tasarım kararı bunu engellemek için var:

**Bozulmuş koşu manşetten ayrılır.** Yönlendirici kademesi kesintiye
girdiğinde `route()` `decision="ignore"`, `confidence=0.0` döndürüyor;
`DecisionLoop` de tanımadığı kararı `TARGET.get(..., "perception")` ile aynı
hedefe yazıyor. İkisi de `closed_at_router` kovasına düşerdi ve **tamamen
çökmüş bir koşu, mümkün olan en gurur verici grafiği** üretirdi. Bu yüzden
`confidence == 0.0` devirleri ayrı bir `degraded` payına gidiyor ve koşunun
bir durumu var (`run_status`).

**Boş koşu için tek sözleşme: `None`.** Ölçülemeyen her KPI `None` döner ve
JSON'da `null` olur. `0.0` "ölçtük, sıfır çıktı" demek; `1.0` ise hiç
operatör düzeltmesi olmayan bir koşuya tam not vermek olurdu. `nan` zaten
geçerli JSON değil.

**Ölçüm, ölçebildiğini söyler.** `vision_tokens` yalnız görü kademesinin
token'larını sayabiliyor çünkü `tokens` sistemde tek bir yerde
(`Interpretation`) kalıcı hâle geliyor; koşu geneli maliyet iddiası veriye
dayanmaz ve bu yüzden üretilmiyor.
"""

import re
import unicodedata
from collections import defaultdict
from statistics import median

#: Koşu durumları. `measured` = sayılar bir şey ifade ediyor; `degraded` =
#: kararların kayda değer bir kısmı kesintiden geldi, grafik okunmamalı;
#: `unmeasured` = yönlendirici hiç karar vermemiş, ölçülecek bir şey yok.
MEASURED = "measured"
DEGRADED = "degraded"
UNMEASURED = "unmeasured"

#: Koşuyu `degraded` sayan eşik: devirlerin beşte birinden fazlası kesinti
#: kaynaklıysa manşet sayı okunamaz. Tek bir bozuk JSON bütün koşuyu
#: damgalamasın diye sıfır değil.
DEGRADED_RUN_THRESHOLD = 0.2

#: `DecisionLoop.catch_up()`'ın telafi devrine yazdığı gerekçe. `_handoff`
#: her deviri `source_agent="orchestrator"` diye yazıyor, yani telafi devirleri
#: yönlendiricinin gerçek kararlarından **yalnız** bu gerekçeyle ayrılabiliyor
#: (bkz. `router_handoffs`).
CATCH_UP_REASON = "telafi"

#: Video saniyesi ile epoch saniyesi arasındaki sınır. `Episode.start_ts`
#: videonun kaçıncı saniyesi demek; 1e9 (2001) üstü bir değer o sütuna epoch
#: damgası yazıldığının kanıtıdır. `mmss()` böyle bir değeri `99:59`'a
#: yapıştırır ve rapor makul görünen yanlış bir saat basar.
EPOCH_THRESHOLD_S = 1e9

DECISION_BUCKETS = ("closed_at_router", "to_interpreter", "to_synthesizer",
                    "escalated", "degraded")

#: Yönlendirici kararının hedef ajanı -> kova adı.
_BUCKET_BY_TARGET = {"perception": "closed_at_router",
                     "interpreter": "to_interpreter",
                     "anomaly_analyst": "to_synthesizer",
                     "supervisor": "escalated"}


# --- devirler --------------------------------------------------------------

def router_handoffs(store) -> list:
    """Yönlendiricinin **kendi kararları**; telafi devirleri hariç.

    İki ayıklama var ve ikisi de manşet sayıyı korur:

    1. Sentezleyici ve risk analisti de `handoff` tablosuna yazıyor. Hepsini
       saymak oranları 1'e toplamaz.
    2. `DecisionLoop.catch_up()` kesinti telafisinde `source_agent="orchestrator"`,
       `target_agent="anomaly_analyst"` bir devir yazıyor — yönlendiricinin
       verdiği bir karar değil, döngünün kendi kaydı. Sayılırsa
       `to_synthesizer` payı şişer.

    **Sınırı açıkça söylemek gerekir:** telafi devri yalnız `reason` alanıyla
    ayırt edilebiliyor (`loop.py` kaynağı sabit yazıyor ve bu görev ona
    dokunmuyor). Gerekçe modelden gelen bir metin olduğu için, yönlendirici
    bir gün gerekçesini tam olarak `"telafi"` yazar ve hedefi sentezleyici
    olursa o karar da ayıklanır. Üçlü eşleşme (kaynak + hedef + gerekçe) bu
    olasılığı küçültüyor; sıfırlamıyor.
    """
    return [h for h in store.handoffs()
            if h.source_agent == "orchestrator"
            and not (h.target_agent == "anomaly_analyst"
                     and h.reason == CATCH_UP_REASON)]


def decision_distribution(store) -> dict[str, float] | None:
    """Yönlendiricinin kararlarının nereye düştüğü; beş pay 1'e toplanır.

    Dördü gerçek kararlar, beşincisi (`degraded`) kesintiden gelen
    devirlerdir. Beşi de **aynı paydaya** (toplam yönlendirici devri) bölünür:
    böylece tamamen çökmüş bir koşuda `degraded` payı 1.0 okur ve grafiğe
    bakan kişi "mükemmel filtreleme" değil, "bu koşu ölçülemedi" görür.

    Hiç yönlendirici devri yoksa `None` — ölçülecek karar yok.

    `confidence == 0.0` kesintinin işareti olarak kullanılıyor: `route()`'un
    `_fallback`'i bunu bilerek sıfır veriyor. Gerçekten sıfır güvenle
    dönen bir model kararı da bu kovaya düşer; kaydedilen tek ayırt edici
    alan bu.
    """
    handoffs = router_handoffs(store)
    if not handoffs:
        return None

    total = len(handoffs)
    counter: dict[str, int] = defaultdict(int)
    for handoff in handoffs:
        if handoff.confidence == 0.0:
            counter["degraded"] += 1
            continue
        bucket = _BUCKET_BY_TARGET.get(handoff.target_agent)
        if bucket is not None:
            counter[bucket] += 1
    return {bucket: counter[bucket] / total for bucket in DECISION_BUCKETS}


def run_status(store) -> str:
    """Koşunun sayıları okunabilir mi: `measured` / `degraded` / `unmeasured`.

    Rapor ve konsol bunu tek bakışta göstermek için okuyor. Bir KPI tablosu,
    okuyanına o tablodaki sayıların bir anlam taşıyıp taşımadığını
    söylemeden yayınlanamaz.
    """
    distribution = decision_distribution(store)
    if distribution is None:
        return UNMEASURED
    return (DEGRADED if distribution["degraded"] > DEGRADED_RUN_THRESHOLD
            else MEASURED)


# --- görü kademesi ---------------------------------------------------------

def vlm_trigger_rate(store) -> float | None:
    """Gözlemlerin yüzde kaçı görsel modele gitti. Hedef: %5'in altı.

    Hiç gözlem yoksa `None`: sıfır gözlemde oran tanımsızdır, sıfır değil.
    """
    observations = len(store.observations())
    if observations == 0:
        return None
    return len(store.interpretations()) / observations


def vision_tokens(store) -> dict[str, float] | None:
    """**Yalnız görü kademesinin** token'ları, kaydedilen model kimliği başına.

    Adı bilerek `tokens_by_model` değil. Sistemde `tokens` tek bir yerde
    kalıcı hâle geliyor — `Interpretation` — yani yönlendirici, ana model,
    denetim, gömme ve yeniden sıralama kademelerinin token'ları hiçbir yerde
    yazmıyor. "Model başına token" adı taşıyan bir çıktı koşu geneli bir
    maliyet tablosu vaat ederdi; veri bunu desteklemiyor ve desteklemeyen bir
    maliyet iddiası yayınlanmaz.

    Anahtar `Interpretation.model`'in gerçekten taşıdığı değer: gateway'in
    döndürdüğü model kimliği (`gozcu.config.MODELS["vlm"]`), kademe takma adı
    değil.
    """
    interpretations = store.interpretations()
    if not interpretations:
        return None
    totals: dict[str, float] = defaultdict(float)
    for interpretation in interpretations:
        totals[interpretation.model] += interpretation.tokens
    return dict(totals)


# --- operatör düzeltmeleri -------------------------------------------------

def _all_corrections(store) -> list:
    """Depodaki bütün düzeltmeler.

    `Store.corrections()` epizot kimliği istiyor, yani var olmayan bir
    epizoda yazılmış düzeltme onunla hiç görünmez — oysa ölçmek istediğimiz
    arıza tam olarak o. Kimlik listesi bu yüzden doğrudan tablodan okunuyor;
    satırların çözümü yine `Store` üzerinden yapılıyor.
    """
    ids = [row[0] for row in
           store.db.execute("SELECT DISTINCT episode_id FROM correction")]
    return [c for episode_id in ids for c in store.corrections(episode_id)]


def correction_propagation(store) -> float | None:
    """Operatör düzeltmelerinin kaçı **gerçek bir epizoda** oturdu. Hedef: 1.0.

    Ne ölçtüğü konusunda dürüst olmak gerekiyor. `Supervisor._apply_correction`
    özette `replace(old, new)` yapıyor ve bu boşa çıktığında düzeltmeyi
    `"(operatör düzeltmesi: …)"` diye **ekliyor** — yani epizot bulunduğu
    sürece yeni metin özette her hâlükârda bulunur. Dolayısıyla "yeni metin
    özette mi" sorusu tek başına asla başarısız olamaz; ölçüm 1.0'da çakılı
    kalırdı.

    Gerçekten başarısız olabilen şey şu: modelin verdiği `episode_id` var
    olmayan bir epizodu gösterdiğinde düzeltme deftere yazılır, `warning` ile
    döner ve **hiçbir yere yayılmaz** — özet güncellenmez, risk yeniden
    koşmaz. Bu KPI onu sayıyor: düzeltmenin kimliği gerçek bir epizoda
    çözülüyor mu ve o epizodun özeti düzeltilmiş metni taşıyor mu.

    Ölçemediği: `Correction` doğrulamasında düşen çağrılar. Onlar deftere hiç
    yazılmadığı için paydada görünmezler; o arıza `_apply_correction`'ın
    döndürdüğü hata metninde ve diyalog dökümünde aranır.

    Hiç düzeltme yoksa `None`. Operatörle hiç konuşulmamış bir koşuya 1.0
    vermek, yapılmamış bir işi tam puanla ödüllendirmek olurdu.
    """
    corrections = _all_corrections(store)
    if not corrections:
        return None
    episodes = {e.id: e for e in store.episodes()}
    landed = sum(1 for correction in corrections
                 if correction.episode_id in episodes
                 and correction.new in episodes[correction.episode_id].summary_tr)
    return landed / len(corrections)


# --- Türkçe kalma oranı ----------------------------------------------------

#: İngilizce stop-word listesi. Yalnız işlev kelimeleri; içerik kelimeleri
#: (`forklift`, `report`) Türkçe metinde de teknik terim olarak geçebiliyor.
#:
#: Türkçede gerçek kelime olan İngilizce stop-word'ler listeden BİLEREK
#: çıkarıldı: `not` (bilgi notu), `at` (hayvan), `on` (sayı), `an` (zaman
#: birimi), `in` (mağara), `it` (hayvan), `her` (nicelik), `as` (asmak),
#: `a` (ünlem). Bunları saymak Türkçe metni İngilizce sanmaya yol açardı.
ENGLISH_STOPWORDS = frozenset({
    "the", "and", "is", "are", "was", "were", "be", "been", "being",
    "with", "without", "that", "this", "these", "those", "from", "for",
    "have", "has", "had", "will", "would", "should", "could", "there",
    "they", "them", "their", "which", "what", "when", "where", "who",
    "because", "about", "into", "onto", "over", "under", "after", "before",
    "your", "you", "our", "his", "she", "he", "we", "of", "to", "or",
    "but", "if", "then", "than", "also", "while", "during", "between",
})

#: Bir metni "İngilizceye kaymış" saymak için gereken **farklı** stop-word
#: sayısı. Tek eşleşme rastlantı olabilir: Türkçe `is` (kurum) kelimesi
#: `"İs"` biçiminde yazıldığında birleştirici nokta atıldıktan sonra
#: İngilizce `is`'e denk düşer. İki farklı işlev kelimesi ise dilin
#: kaydığının kanıtıdır.
MIN_STOPWORD_HITS = 2

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
_COMBINING_DOT = "\u0307"


def _fold(word: str) -> str:
    """Kelimeyi karşılaştırılabilir hâle getirir.

    `"İ".casefold()` **iki** kod noktası üretir (`i` + U+0307); ham
    karşılaştırma büyük harfli Türkçe metinde hiçbir şeyi eşleştiremez ve
    ölçüm sessizce kör kalırdı. Birleştirici nokta bu yüzden ayrıştırılıp
    atılıyor.
    """
    folded = unicodedata.normalize("NFD", word.casefold())
    return folded.replace(_COMBINING_DOT, "")


def looks_english(text: str) -> bool:
    """Metin İngilizceye kaymış mı.

    Kural: metin **kelime sınırlarıyla** ayrıştırılır ve en az
    `MIN_STOPWORD_HITS` farklı İngilizce stop-word içeriyorsa kaymış sayılır.

    Alt dize araması bilerek kullanılmıyor: `risk` içinde `is`, `hasarlı`
    içinde `has`, `istif` içinde `is` geçiyor. Alt dizeye bakan bir ölçüm
    tertemiz Türkçe bir raporu "İngilizce" diye damgalar — ve o damga
    yarışmanın adı Türkçe olan bir kategoride en pahalı yanlış ölçümdür.
    """
    hits = {token for token in map(_fold, _WORD.findall(text))
            if token in ENGLISH_STOPWORDS}
    return len(hits) >= MIN_STOPWORD_HITS


def generated_texts(store) -> list[str]:
    """Ölçüme giren korpus: **modelin ürettiği, insana görünen** metinler.

    Üç kaynak: süpervizörün diyalog satırları (`role == "supervisor"`),
    epizot özetleri (`summary_tr`) ve risk gerekçeleri (`rationale_tr`).

    `role == "system"` satırları korpusun dışında ve bu bir ayrıntı değil:
    o rolde iki farklı şey yatıyor ve **ikisi de model üretimi değil** —
    `AUDIT_PREFIX` önekli denetim hükümleri ve elle yazılmış Türkçe arıza
    metinleri (`DEGRADED_REPLY` gibi). Arıza metinleri her zaman Türkçe
    olduğu için oranı yapay olarak yukarı çeker, denetim hükümleri ise
    payda şişirir. `role == "operator"` da haliyle dışarıda: operatörün ne
    yazdığı sistemin dil performansı değildir.
    """
    texts = [turn.text for turn in store.dialogue()
             if turn.role == "supervisor"]
    texts += [episode.summary_tr for episode in store.episodes()]
    texts += [risk.rationale_tr for risk in store.risks()]
    return [text for text in texts if text and text.strip()]


def turkish_output_rate(store) -> float | None:
    """Üretilen operatör metninin ne kadarı Türkçe kaldı. Hedef: 1.0.

    Yarışmanın adı **Türkçe** dil ajanları ve modelin sessizce İngilizceye
    kayması en sinsi başarısızlık: sistem çalışmaya devam eder, çıktılar
    makul görünür, teslim değersizleşir. Kasıntı Türkçe'yi yakalamaz — onun
    için insan turu var — ama dilin tamamen kaymasını yakalar.

    Korpus `generated_texts()`'te tanımlı. Hiç üretilmiş metin yoksa `None`.
    """
    texts = generated_texts(store)
    if not texts:
        return None
    return sum(1 for text in texts if not looks_english(text)) / len(texts)


# --- zaman doğruluğu -------------------------------------------------------

def epoch_scale_episodes(store) -> list:
    """`start_ts`'i epoch ölçeğinde olan epizotlar — boş olmalı.

    `Episode.start_ts` **video saniyesi**. Arşiv fikstürleri bir zamanlar aynı
    sütuna epoch saniyesi (`1786567260.0`) yazıyordu; `mmss()` onu `99:59`'a
    yapıştırıyor ve rapor ile konsol makul görünen yanlış bir saat basıyordu.
    Olayın takvim tarihi fikstürün `occurred_at` / `date` alanlarında yaşıyor,
    epizot satırında değil.
    """
    return [e for e in store.episodes()
            if e.start_ts >= EPOCH_THRESHOLD_S
            or (e.end_ts or 0.0) >= EPOCH_THRESHOLD_S]


def detections(store, seeded_episode_ids=()) -> list:
    """Bu koşuda **tespit edilmiş** epizotlar.

    Arşiv olayları (`load_history`) da epizot satırı olarak duruyor ve hiçbir
    alanları onları canlı tespitten ayırmıyor. Ayırt eden tek güvenilir bilgi
    çağıranda: koşu başlamadan önce depoda hangi epizotların olduğu. Benchmark
    koşucusu tohumlamadan hemen sonra kimlikleri alıp buraya veriyor.
    """
    seeded = set(seeded_episode_ids)
    return [e for e in store.episodes() if e.id not in seeded]


def timestamp_drift(store, truth: list[tuple[float, float]],
                    seeded_episode_ids=()) -> float | None:
    """Etiketli olay başlangıcı ile en yakın epizot başlangıcı arasındaki
    medyan mutlak fark, saniye.

    `truth` yalnızca **gerçekten olay içeren** pencerelerden oluşmalı;
    `benchmark.ground_truth.load_ground_truth()` `has_incident=0` satırlarını
    ve penceresi henüz işaretlenmemiş satırları zaten ayıklıyor (boş bir
    `start_s` alanında `float("")` istisna atar).

    Etiketli pencere yoksa ya da hiç tespit yoksa `None` döner: sıfır sapma
    "mükemmel isabet" demek olurdu ve hiçbir şey tespit etmemiş bir koşu böyle
    okunamaz.
    """
    episodes = detections(store, seeded_episode_ids)
    if not episodes or not truth:
        return None
    drifts = [min(abs(episode.start_ts - start) for episode in episodes)
              for start, _end in truth]
    return float(median(drifts))


# --- klip ve koşu özeti ----------------------------------------------------

def collect(store, truth: list[tuple[float, float]] = (),
            seeded_episode_ids=()) -> dict:
    """Tek bir klip için bütün KPI'lar ve koşunun durumu.

    Dönen sözlük `bench/kpi.schema.json`'daki `clip` kaydının gövdesi;
    `video` ve `error` alanlarını koşucu ekliyor.
    """
    return {
        "status": run_status(store),
        "kpis": {
            "decision_distribution": decision_distribution(store),
            "vlm_trigger_rate": vlm_trigger_rate(store),
            "vision_tokens": vision_tokens(store),
            "correction_propagation": correction_propagation(store),
            "timestamp_drift_s": timestamp_drift(store, list(truth),
                                                 seeded_episode_ids),
            "turkish_output_rate": turkish_output_rate(store),
        },
    }


KPI_KEYS = ("decision_distribution", "vlm_trigger_rate", "vision_tokens",
            "correction_propagation", "timestamp_drift_s",
            "turkish_output_rate")

_SCALAR_KPIS = ("vlm_trigger_rate", "correction_propagation",
                "timestamp_drift_s", "turkish_output_rate")


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def aggregate(clips: list[dict]) -> dict:
    """Klip kayıtlarını koşu özetine indirger.

    **Ortalamalara yalnız `measured` klipler girer.** Bozulmuş bir klibin
    dağılımı büyük ölçüde `degraded` payından ibaret; onu ortalamaya katmak
    manşet sayıyı sulandırır ve kesintiyi başarı gibi gösterir. Bozulmuş ve
    çöken klipler kaybolmuyor — `clips` sayacında adıyla duruyorlar.
    """
    counts = {"total": len(clips), "measured": 0, "degraded": 0,
              "unmeasured": 0, "error": 0}
    measured: list[dict] = []
    for clip in clips:
        if clip.get("error"):
            counts["error"] += 1
            continue
        status = clip.get("status", UNMEASURED)
        counts[status] = counts.get(status, 0) + 1
        if status == MEASURED:
            measured.append(clip.get("kpis") or {})

    kpis: dict = {key: None for key in KPI_KEYS}
    for key in _SCALAR_KPIS:
        kpis[key] = _mean([k[key] for k in measured if k.get(key) is not None])

    distributions = [k["decision_distribution"] for k in measured
                     if k.get("decision_distribution")]
    if distributions:
        kpis["decision_distribution"] = {
            bucket: sum(d[bucket] for d in distributions) / len(distributions)
            for bucket in DECISION_BUCKETS}

    token_tables = [k["vision_tokens"] for k in measured
                    if k.get("vision_tokens")]
    if token_tables:
        totals: dict[str, float] = defaultdict(float)
        for table in token_tables:
            for model, tokens in table.items():
                totals[model] += tokens
        kpis["vision_tokens"] = dict(totals)

    if counts["measured"] == 0 and counts["degraded"] == 0:
        status = UNMEASURED
    elif (counts["measured"] == 0 or counts["degraded"] or counts["error"]
          or counts["unmeasured"]):
        status = DEGRADED
    else:
        status = MEASURED
    return {"status": status, "clips": counts, "kpis": kpis}
