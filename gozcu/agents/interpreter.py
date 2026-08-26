"""Yorumlayıcı adaptörü — pencereyi görü kademesine soran tek yer.

`gozcu/interpret.py` çalışıyor ama kendi `OpenAI` istemcisini kuruyor:
`Gateway`'i baypas ettiği için `inject_failure({"vlm"})` gerçek VLM
çağrılarını yönetmiyor, ve görüntüyü yerel dosya yolu olarak gönderdiği için
uzaktaki bir gateway onu hiç okuyamıyor. Bu modül arayı kapatıyor: pencere
base64 data-URI olarak gömülüyor, istek `gw.ask("vlm", …)` üzerinden geçiyor.

**Pencere kare değil, kliptir.** İlk sürüm pencere başına üç base64 JPEG
gönderiyordu; 24 Ağustos'ta gerçek gateway'de ölçüldü ki bu tasarım hiçbir
kademede çalışmıyor:

- `vlm` görüntüye 400 veriyor — `At most 0 image(s) may be provided in one
  request.` Model görüntü yeteneğine sahip, ama bu kurulum kodlayıcı piksel
  bütçesinin tamamını video çözünürlüğüne ayırdığı için görüntü kapasitesi
  bilinçli olarak sıfır.
- Görüntü kabul eden `llm-fast` / `llm-large` istek başına en fazla İKİ tane
  alıyor; üç kare oraya da sığmıyor.

Aynı gün gerçek bir 10 saniyelik pencere klip olarak `vlm`'e gönderildi:
11,4 s, 431 KB klip → 561 KB base64, 8.285 token, düzgün Türkçe analiz — ve
**zaman içindeki değişimi** okuyor. Üç durağan karenin taklit etmeye çalıştığı
şey buydu (bkz. `docs/06-references/evren-gateway.md`).

Klibi bu modül kesmiyor: kareler nasıl dışarıdan enjekte ediliyorsa klip de
öyle geliyor (`clip_for`). Kesme işi Görev 17'nin adaptörünün — böylece burası
ffmpeg olmadan test edilebiliyor.

Buradaki çıktı temizleme mantığı gerçek çıktılarda görülmüş hatalardan doğdu;
her birinin gerekçesi ilgili sabitin başında duruyor. Şema sertleştirmesi
(`strict_schema`) artık `gozcu/gateway.py`'da ve `Gateway.ask()` onu her şemaya
kendisi uyguluyor — bir çağıranın unutması mümkün değil.
"""

import base64
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from gozcu.gateway import strict_schema
from gozcu import trace
from gozcu.models import (MAX_BEAT_TEXT, MAX_BEATS, SEVERITY_LEVELS, ClipBeat,
                          Interpretation, Observation, Severity)

# Sertleştirme artık `gozcu.gateway`'de yaşıyor ve `Gateway.ask()` onu kendisi
# uyguluyor. Buradan yeniden dışa aktarılıyor: mevcut import'lar çalışmaya
# devam etsin.
__all__ = ["clip_data_uri", "interpret", "strict_schema"]

MAX_DESCRIPTION = 300
MAX_NOTABLE_EVENT = 200

# Token tavanı. Kaçak tekrar (`gozcu.gateway._MAX_ARRAY_ITEMS` notu) yalnızca
# bir üst sınırla tam olarak kapanıyor: sınır yoksa kod çözücü JSON'u hiç
# kapatmadan üretmeye devam ediyor.
#
# 400 ölçülerek elendi: canlı video çağrısında cümlenin ORTASINDA kesti. 300 +
# 200 karakterlik iki alan Türkçede ~250 token, ama video yanıtları uzun
# başlıyor ve JSON iskeleti de pay istiyor.
#
# Diğer yönde de bir duvar var ve daha sinsi: akıl yürütme (reasoning) açıkken
# dar bir `max_tokens` **boş dize** üretiyor — düşünme izi bütçeyi yiyor,
# ayrıştırıcı izi söküyor ve geriye hiçbir şey kalmıyor (ölçülen: 128, 256 ve
# 512'nin üçü de sıfır karakter). Bu modeller için akıl yürütme varsayılan
# olarak kapalı ve öyle kalıyor; 1024 hem tam bir betimlemeye hem zarfa rahat
# yetiyor, hem de tavanın kaçak tekrara karşı anlamını koruyacak kadar dar.
MAX_TOKENS = 1024
# Güvenlik kaydı için düşük ama sıfır değil: sıfır sıcaklık aynı yanlış
# betimlemeyi her karede tekrar üretiyordu.
TEMPERATURE = 0.3

# Ciddiyet seviyesinin somut çıpaları. `SYSTEM_PROMPT` bunları SEVERITY_LEVELS
# demetinden okuyor — elle iki kez yazılan aynı üç kelime bir gün birbirinden
# ayrışır ve şema ile prompt farklı şey söyler (bkz. decision-log, 26 Ağustos:
# forklift-kazası klibinde epizot 00:00'da, park hâlindeki bir kamyonun
# yanından geçen biri yüzünden açıldı — "dikkat çekici" ölçütü tek başına
# kalabalık/hareketli bir sahneyi olaydan ayıramadı).
SYSTEM_PROMPT = f"""Sen bir fabrika güvenlik kamerasını izleyen gözlemcisin.
Sana kameranın kısa bir video kesiti ve o pencereye ait tespit/sinyal özeti
verilir.

Kurallar:
- Tek bir anı resimleme. Klip boyunca NE OLDUĞUNU ve NE DEĞİŞTİĞİNİ yaz —
  hareket, duruş bozulması, hızlanma, devrilme, kadraja giren ya da çıkan
  nesne, yerde kalan kişi.
- Sadece GÖRDÜĞÜNÜ yaz. Emin değilsen "olası" de.
- Türkçe, tek-iki kısa cümle, saha terminolojisi.
- Kişi kimliği, yaş, cinsiyet tahmini YAPMA.
- Dikkat çekici bir şey yoksa notable_event null olsun.
- severity ZORUNLU ve tam olarak şu üçünden biri olmalı:
  - "{SEVERITY_LEVELS[0]}" — normal fabrika işleyişi: yürüyen insanlar,
    seyreden araçlar, düzenli yükleme/boşaltma, duran ya da bekleyen biri.
    SAHNE KALABALIK YA DA HAREKETLİ OLMASI TEK BAŞINA seviyeyi
    "{SEVERITY_LEVELS[0]}"nin üstüne çıkarmaz.
  - "{SEVERITY_LEVELS[1]}" — bir şey düzensiz ama henüz hiçbir şey OLMADI:
    ramak kala, güvensiz duruş ya da konum, beklenmedik duruş, hareketli
    ekipmana fazla yakın biri.
  - "{SEVERITY_LEVELS[2]}" — gerçekten bir şey OLDU: çarpışma, devrilme ya
    da düşme, yük dökülmesi, yangın ya da duman, yerde yatan biri,
    yaralanma.
- beats: klip boyunca gördüğün 4–6 anı sırayla yaz. Her anın offset_s
  değeri KLİBİN BAŞLANGICINDAN itibaren geçen saniyedir (klip 0,0
  saniyede başlar) ve klibin süresini aşmasın; text ise o anda ne
  olduğunu anlatan kısa bir Türkçe cümle olsun.
- Klip boyunca hiçbir şey değişmiyorsa beats boş liste olsun.

Sadece JSON döndür."""

# Çıplak alan adı (pydantic'in otomatik başlığı "Notable Event") küçük yerel
# VLM'e içerik üretirken tutunacak hiçbir şey vermiyordu: zayıf/belirsiz
# hareket sinyali olan karelerde değer olarak alan adının kendisini geri
# yazmaya başladı (bir gerçek karede 4/4 tekrarlandı). Geçerli bir değerin
# neye benzediğini şemada hecelemek o döngüyü kapatıyor.
_NOTABLE_EVENT_DESCRIPTION = (
    "Görüntüde ya da hareket verisinde gerçekten dayanağı olan dikkat çekici "
    "bir olayı anlatan kısa ve somut bir cümle; öyle bir olay yoksa null. "
    "Asla 'notable_event' ya da başka bir yer tutucu metin olmasın.")

# Şema/prompt düzeyindeki önlem olasılıksal bir hataya olasılıksal bir çözüm;
# bu, tekrarını yakalayan mekanik güvenlik ağı. Model bunlardan birini değer
# olarak yazarsa "olay yok" diye okunur.
_NOTABLE_EVENT_PLACEHOLDERS = {
    "notable_event", "notable event", "none", "null", "n/a",
    "yok", "placeholder", "yer tutucu",
}

# Aynı üç değer `SYSTEM_PROMPT`'ta da geçiyor — ikisi `SEVERITY_LEVELS`'ten
# okuyor ki bir gün elle düzenlenip ayrışamasınlar (bkz. `gozcu.models`).
# Epizot AÇILIŞININ tek geçidi bu alan; `notable_event` betimleme olarak
# kalıyor, kapıyı severity tutuyor (bkz. `gozcu.loop.DecisionLoop._may_open`).
_SEVERITY_DESCRIPTION = (
    f"Sahnenin ciddiyet seviyesi, ZORUNLU ve tam olarak üçünden biri: "
    f"'{SEVERITY_LEVELS[0]}' — normal fabrika işleyişi (yürüyen insan, "
    f"seyreden araç, düzenli yükleme/boşaltma, duran/bekleyen biri; kalabalık "
    f"olmak dikkat çekici olmakla aynı şey DEĞİL), "
    f"'{SEVERITY_LEVELS[1]}' — düzensiz ama henüz hiçbir şey OLMADI (ramak "
    f"kala, güvensiz duruş/konum, beklenmedik duruş, ekipmana fazla yakın "
    f"biri), '{SEVERITY_LEVELS[2]}' — gerçekten bir şey OLDU (çarpışma, "
    f"devrilme/düşme, yük dökülmesi, yangın/duman, yerde yatan biri, "
    f"yaralanma).")

# Alan adının kendisi ("beats") modele klibin neresinden sayacağını
# söylemiyor; damganın ölçüsü şemada da heceleniyor. Aynı cümle prompt'ta da
# duruyor — ikisi ayrışırsa model iki farklı ölçü arasında salınır.
_BEATS_DESCRIPTION = (
    "Klip boyunca yaşanan anlar, zaman sırasına göre. offset_s klibin "
    "başlangıcından itibaren geçen SANİYE (klip 0,0'da başlar) ve klibin "
    "süresini aşamaz; text o anda ne olduğunu anlatan kısa bir Türkçe cümle. "
    "Kayda değer bir değişim yoksa boş liste.")

_SENTENCE_END = (".", "!", "?")
# Sınıra "ne kadar yakınsa kesilmiş sayılır" penceresi. Kod çözücü her zaman
# tam sınıra oturmuyor (gözlenen: bir kare tam 300, bir başkası 296 karakterde
# kesildi) — sabit 1 karakterlik tolerans gevşek olanı kaçırıyor.
_BOUNDARY_SLACK = 10


class _VisionResponse(BaseModel):
    """Görü kademesinden beklenen çıktı. Uzunluk sınırları burada kalır —
    şemadan çıkarılırlar (bkz. `strict_schema`), doğrulamadan çıkmazlar."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(max_length=MAX_DESCRIPTION)
    notable_event: str | None = Field(default=None, max_length=MAX_NOTABLE_EVENT,
                                      description=_NOTABLE_EVENT_DESCRIPTION)
    #: Varsayılansız — model bunu atlarsa şema onu reddetsin, epizot açılışı
    #: sessizce gözetimsiz kalmasın (bkz. `gozcu.loop.DecisionLoop._may_open`).
    severity: Severity = Field(description=_SEVERITY_DESCRIPTION)
    # `maxItems` bilerek buradan geliyor: `strict_schema` uzunluk anahtarlarını
    # söküyor ama dizi üst sınırını telde bırakıyor ve kaçak tekrara karşı tek
    # koruma o (bkz. `gozcu.gateway._MAX_ARRAY_ITEMS`).
    beats: list[ClipBeat] = Field(default_factory=list, max_length=MAX_BEATS,
                                  description=_BEATS_DESCRIPTION)

    @classmethod
    def model_json_schema(cls, *args, **kwargs) -> dict:
        """`Gateway.ask` artık şemayı kendisi sertleştiriyor; bu ezme yine de
        duruyor ki modeli doğrudan inceleyen kod da sertleştirilmiş şemayı
        görsün. `strict_schema` girdisini kopyalar — iki kez uygulanması
        zararsız."""
        return strict_schema(super().model_json_schema(*args, **kwargs))


def _sanitize_text(text: str, max_length: int) -> str:
    """Uzunluk sınırlı bir metin alanını (`description` / `notable_event`)
    temizler.

    Gerçek karelerde gözlenen, ikisi de pydantic doğrulamasından sessizce
    geçen iki belirti:
    - kapanış tırnağından hemen önce eklenmiş ham bir kontrol karakteri
      (kare 0011: "...roof of the building. There\\x01")
    - tam sınırda, hata vermeden yarım kelimede kesilme (kare 0005:
      "...a building in the")

    Şemadan `maxLength` çıktığı için kesme artık bize düşüyor; kesilmiş metnin
    yarım kalan son kelimesi de aynı şekilde budanıyor.
    """
    cleaned = text
    while cleaned and not cleaned[-1].isprintable():
        cleaned = cleaned[:-1]
    cleaned = cleaned.rstrip()

    original_length = len(cleaned)
    if original_length > max_length:
        cleaned = cleaned[:max_length].rstrip()

    # Metin sınıra oturmuşsa ve cümle sonuyla bitmiyorsa, büyük olasılıkla
    # yarım kelimede kesildi — sarkan parçayı bırakmaktansa son tam kelimeye
    # geri budanır.
    at_boundary = original_length >= max_length - _BOUNDARY_SLACK
    if at_boundary and not cleaned.endswith(_SENTENCE_END):
        trimmed, _, _ = cleaned.rpartition(" ")
        if trimmed:
            cleaned = trimmed.rstrip()

    return cleaned


def _sanitize_beats(raw, window_duration: float) -> list[dict]:
    """Modelin yazdığı an listesini doğrulanabilir hâle getirir.

    Diğer alanlarda olduğu gibi temizlik doğrulamadan ÖNCE: şemadan
    `minimum`/`maxLength` sökülüyor, yani model klibin dışına düşen bir damga
    ya da 400 karakterlik bir cümle yazabilir ve ham hâliyle pydantic'e
    verilirse **bütün yorum** düşerdi.

    Üç ayrı düzeltme, üçü de gerçek çıktı biçimlerinden:

    - damga klibin dışına düşerse `[0, süre]` aralığına ÇEKİLİYOR. Klipten
      önceki ya da sonraki bir offset mutlak zamana çevrildiğinde olayı hiç
      yaşanmadığı bir saniyeye yazar.
    - metin sınırı aşarsa kesiliyor (sarkan yarım kelime dahil).
    - bozuk bir kayıt DÜŞÜYOR, listeyi ya da yorumu düşürmüyor.

    `bool` bilerek sayı sayılmıyor: Python'da `isinstance(True, int)` doğru
    ve `True` sessizce 1,0 saniyeye dönüşürdü.
    """
    if not isinstance(raw, list):
        return []

    beats: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        offset = item.get("offset_s")
        text = item.get("text")
        if isinstance(offset, bool) or not isinstance(offset, (int, float)):
            continue
        if not isinstance(text, str):
            continue
        cleaned = _sanitize_text(text, MAX_BEAT_TEXT)
        if not cleaned:
            continue
        beats.append({"offset_s": min(max(float(offset), 0.0), window_duration),
                      "text": cleaned})
        if len(beats) == MAX_BEATS:
            break
    return beats


# Doğrulanmış istek biçiminin MIME türü. Uzantıdan tahmin edilmiyor: klibi
# kesen taraf uzantıyı unutursa `mimetypes` `None` döner ve gateway'e türü
# bildirilmemiş bir data-URI gider.
_CLIP_MIME = "video/mp4"


def clip_data_uri(clip_path: str | Path) -> str:
    """Pencere klibini base64 data-URI'ye gömer.

    Satır içi base64, çekilebilir URL değil: modeller verinin yerelde kalması
    için organizasyonun kendi sunucusunda ayakta ve URL isteyen bir gateway
    videoyu almak için dışarı çıkmak zorunda kalırdı (decision-log, 23
    Ağustos). Uzaktaki gateway zaten yerel dosya yolunu da okuyamaz.
    """
    path = Path(clip_path)
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{_CLIP_MIME};base64,{payload}"


def _context(window: list[Observation]) -> str:
    """Pencerenin özeti — **zirvesinden**, ortasından değil.

    İki arıza birlikte düzeltildi (25 Ağustos):

    1. **Orta kare okunuyordu.** `window[len(window) // 2]` sakin bir orta
       kareye denk gelirse, pencerenin 9. saniyesindeki olay özete hiç
       girmiyordu — yönlendirici de görü kademesini boşuna atlıyordu.
       Pencerenin zirvesi okunuyor artık: en kalabalık kare, en yüksek hız,
       pencere boyunca kaybolan bütün izler.
    2. **Her kaybolma "kadraj dışına çıkan" diye anlatılıyordu.** Makineye
       kapılan bir insan için bu tam tersini söylüyor — sistemin yakalaması
       gereken olayı, olmadığı şeye çeviriyordu. Artık nötr: "kaybolan iz".
       Nereye gittiğini klibe bakan görü kademesi söyler, biz uydurmayız.
    """
    labels = sorted({d.label for o in window for d in o.detections})
    peak_count = max((o.signals.person_count for o in window), default=0)
    velocities: dict[int, float] = {}
    for observation in window:
        for track_id, speed in observation.signals.velocities.items():
            velocities[track_id] = max(velocities.get(track_id, 0.0), speed)
    vanished = sorted({tid for o in window for tid in o.signals.vanished_tracks})
    interior = sorted({tid for o in window
                       for tid in getattr(o.signals, "interior_vanished_tracks", [])})

    parts = [f"tespitler: {', '.join(labels) or 'yok'}",
             f"kişi sayısı (pencere zirvesi): {peak_count}"]
    if velocities:
        # `.2f` — birim kare genişliği/saniye (bkz. `gozcu.signals`):
        # medyan 0,008 ve yürüyüş 0,03-0,1 bandında tek ondalık
        # basamak gerçek hareketi "0.0" diye yazar ve bu katmana,
        # yani epizodun açılmasına TEK BAŞINA karar veren yere,
        # "hareket yok" diye yalan söyler.
        parts.append("hızlar: " + ", ".join(
            f"{track_id}:{speed:.2f}" for track_id, speed in velocities.items()))
    if vanished:
        # **"kadraj dışına çıkan" DEĞİL.** Eski metin her kaybolmayı kadrajı
        # terk etmek diye anlatıyordu ve makineye kapılan bir insan için tam
        # tersini söylüyordu. Nötr kelime, gördüğümüz şeyin tamamı: iz
        # kayboldu. Nereye gittiğini klibe bakan görü kademesi söyler.
        #
        # İçeride/dışarıda ayrımı `Signals` üzerinde HESAPLANIYOR ama buraya
        # yazılmıyor: ölçüldü, iz parçalanması yüzünden saniyede 1,1–3,3
        # "içeri kaybolma" üretiyor ve o sayı prompt'a girerse modele her
        # pencerede olmayan bir kaza anlatılır (bkz. `gozcu/signals.py`).
        parts.append(f"kaybolan iz: {vanished}")
    return " | ".join(parts)


def _message(window: list[Observation], clip_uri: str,
             start_ts: float, end_ts: float) -> list[dict]:
    """Çok parçalı istek gövdesini kuran tek yer.

    Parça biçimi organizasyonun dokümanından alındı ve canlı doğrulandı:
    `{"type": "video_url", "video_url": {"url": "data:video/mp4;base64,…"}}`.
    Bir `image_url` parçası buraya asla girmemeli — `vlm`'in görüntü kapasitesi
    sıfır, dönen şey 400. Kalan risk içerik biçiminin sunucuya göre değişmesi;
    bozulursa düzeltilecek tek yer burası.
    """
    span = max(end_ts - start_ts, 0.0)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": [
            {"type": "text",
             "text": (f"Sinyaller — {_context(window)}\n\n"
                      f"Aşağıdaki {span:.1f} saniyelik kamera kesiti videonun "
                      f"{start_ts:.1f}s–{end_ts:.1f}s aralığına ait. Bu "
                      f"pencerede ne oluyor, kesit boyunca ne değişiyor?")},
            {"type": "video_url", "video_url": {"url": clip_uri}}]}]


def _parse(content: str, window_duration: float) -> _VisionResponse | None:
    """Modelin ham çıktısını doğrulanmış bir yanıta çevirir; olmazsa `None`.

    `window_duration` bilerek varsayılansız: 0,0 varsayılanı bütün anları
    sessizce klibin başlangıcına çakardı — tam olarak düzeltmeye çalıştığımız
    hata, bu kez unutulan bir argümanın arkasında.

    Kesme doğrulamadan ÖNCE yapılıyor: şemada `maxLength` olmadığı için model
    sınırı aşabilir ve pydantic'e olduğu gibi verilirse kayıt tamamen düşerdi.
    """
    try:
        data = json.loads(content)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    description = data.get("description")
    if not isinstance(description, str):
        return None
    data["description"] = _sanitize_text(description, MAX_DESCRIPTION)

    notable_event = data.get("notable_event")
    if isinstance(notable_event, str):
        cleaned = _sanitize_text(notable_event, MAX_NOTABLE_EVENT)
        if not cleaned or cleaned.strip().lower() in _NOTABLE_EVENT_PLACEHOLDERS:
            cleaned = None
        data["notable_event"] = cleaned

    if "beats" in data:
        data["beats"] = _sanitize_beats(data.get("beats"), window_duration)

    try:
        return _VisionResponse(**data)
    except Exception:  # noqa: BLE001 — bozuk çıktı bir koşuyu düşürmemeli
        return None


def interpret(gw, store, window: list[Observation],
              clip_for) -> Interpretation | None:
    """Pencereyi görü kademesine sorar, sonucu depoya yazar.

    `clip_for`: `(start_ts, end_ts)` alıp o aralığın kısa mp4 klibinin dosya
    yolunu (ya da kesilemediyse `None`) döndüren çağrılabilir. Kesme işi
    burada değil, Görev 17'nin adaptöründe — kareler nasıl enjekte ediliyorsa
    klip de öyle, ve modül ffmpeg olmadan test edilebiliyor.

    **Pencere başına bir klip; pencereler birleştirilmiyor.** Ön ek önbelleği
    (4,8× hızlanma) bütün videoyu tek seferde göndermeyi cazip gösteriyor, ama
    çözünürlük ölçeği klip süresine bağlı: 15 s → 0,95 · 30 s → 0,65 ·
    60 s → 0,47 · 180 s → 0,28. İşlenmiş karede bir token 32×32 piksel ve iki
    tokenin altında kalan nesne hiç çözülemiyor. "Yerde hareketsiz kişi"
    küçük ve düşük kontrastlı bir hedef — çözünürlük hızdan önce gelir.
    `WINDOW_S` = 10 s bu cetvelin iyi ucunda (~0,95) ve tavanların
    (260 s süre, 2,0 fps / 520 kare) çok içinde kalıyor. Pencereleri uzun
    kliplerde toplamak burayı sessizce kör eder.

    `None`'ın dört ayrı anlamı var ve ayrımı `DecisionLoop` için önemli — o
    pencereyi YALNIZCA görü kademesi gerçekten bozukken erteliyor:
    boş pencere, klip kesilememesi ve ayrıştırılamayan çıktı kesinti DEĞİL;
    yalnızca `response.degraded` kesintidir.
    """
    if not window:
        return None

    start_ts, end_ts = window[0].ts, window[-1].ts
    # ffmpeg burada koşuyor ve pencere başına bir mp4 kesiyor. Yavaşlığın
    # ikinci olası kaynağı bu ve gateway çağrısından AYRI ölçülmeli, yoksa
    # "görü yavaş" derken aslında kesme yavaş olabilir.
    with trace.step("görü.klip-kes", f"{start_ts:.0f}–{end_ts:.0f}s"):
        clip_path = clip_for(start_ts, end_ts)
    # Klip yoksa istek hiç gitmez. Metin-only bir istek gönderip sonucu "video
    # analizi" diye kaydetmek sessizce uydurma üretmek olurdu.
    if clip_path is None:
        return None

    middle = window[len(window) // 2]

    with trace.step("görü.base64", f"{Path(clip_path).stat().st_size / 1e6:.2f}MB klip"):
        data_uri = clip_data_uri(clip_path)

    response = gw.ask("vlm",
                      _message(window, data_uri, start_ts, end_ts),
                      schema=_VisionResponse,
                      max_tokens=MAX_TOKENS,
                      temperature=TEMPERATURE)
    trace.event("görü.yanıt",
                f"{response.latency_ms} ms tokens={response.tokens} "
                f"kesinti={response.degraded} "
                f"içerik={len(response.content or '')} karakter")

    # Açık kesinti guard'ı. `json.loads("")`'ın tesadüfen istisna atmasına
    # güvenilmiyor: bozuk yanıt bir gün boş olmayan içerikle gelirse (ör.
    # önbellekten dönen bayat gövde) o tesadüf çalışmaz.
    if response.degraded:
        return None
    if not (response.content or "").strip():
        return None

    parsed = _parse(response.content, max(end_ts - start_ts, 0.0))
    if parsed is None:
        return None

    interpretation = Interpretation(
        observation_ts=middle.ts,
        description=parsed.description,
        notable_event=parsed.notable_event,
        severity=parsed.severity,
        beats=parsed.beats,
        model=response.model,
        latency_ms=response.latency_ms,
        tokens=response.tokens)
    interpretation.id = store.save_interpretation(interpretation)
    return interpretation
