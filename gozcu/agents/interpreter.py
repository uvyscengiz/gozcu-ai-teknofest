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
from gozcu.models import Interpretation, Observation

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

SYSTEM_PROMPT = """Sen bir fabrika güvenlik kamerasını izleyen gözlemcisin.
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
    labels = sorted({d.label for o in window for d in o.detections})
    middle = window[len(window) // 2]
    signals = middle.signals
    parts = [f"tespitler: {', '.join(labels) or 'yok'}",
             f"kişi sayısı: {signals.person_count}"]
    if signals.velocities:
        parts.append("hızlar: " + ", ".join(
            f"{track_id}:{speed:.1f}" for track_id, speed in signals.velocities.items()))
    if signals.vanished_tracks:
        parts.append(f"kadraj dışına çıkan: {signals.vanished_tracks}")
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


def _parse(content: str) -> _VisionResponse | None:
    """Modelin ham çıktısını doğrulanmış bir yanıta çevirir; olmazsa `None`.

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
    clip_path = clip_for(start_ts, end_ts)
    # Klip yoksa istek hiç gitmez. Metin-only bir istek gönderip sonucu "video
    # analizi" diye kaydetmek sessizce uydurma üretmek olurdu.
    if clip_path is None:
        return None

    middle = window[len(window) // 2]

    response = gw.ask("vlm",
                      _message(window, clip_data_uri(clip_path),
                               start_ts, end_ts),
                      schema=_VisionResponse,
                      max_tokens=MAX_TOKENS,
                      temperature=TEMPERATURE)

    # Açık kesinti guard'ı. `json.loads("")`'ın tesadüfen istisna atmasına
    # güvenilmiyor: bozuk yanıt bir gün boş olmayan içerikle gelirse (ör.
    # önbellekten dönen bayat gövde) o tesadüf çalışmaz.
    if response.degraded:
        return None
    if not (response.content or "").strip():
        return None

    parsed = _parse(response.content)
    if parsed is None:
        return None

    interpretation = Interpretation(
        observation_ts=middle.ts,
        description=parsed.description,
        notable_event=parsed.notable_event,
        model=response.model,
        latency_ms=response.latency_ms,
        tokens=response.tokens)
    interpretation.id = store.save_interpretation(interpretation)
    return interpretation
