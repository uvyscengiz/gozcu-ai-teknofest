"""Yorumlayıcı adaptörü — pencereyi görü kademesine soran tek yer.

`gozcu/interpret.py` çalışıyor ama kendi `OpenAI` istemcisini kuruyor:
`Gateway`'i baypas ettiği için `inject_failure({"vlm"})` gerçek VLM
çağrılarını yönetmiyor, ve kareyi yerel dosya yolu olarak gönderdiği için
uzaktaki bir gateway görüntüyü hiç okuyamıyor. Bu modül arayı kapatıyor:
kareler base64 data-URI olarak gömülüyor, istek `gw.ask("vlm", …)` üzerinden
geçiyor.

Buradaki şema sertleştirmesi ve çıktı temizleme mantığı `interpret.py`'da
gerçek karelerle görülmüş hatalardan doğdu; her birinin gerekçesi ilgili
sabitin başında duruyor. `interpret.py`'dan import edilmiyor — o modül donuk
algı katmanının parçası ve Görev 17'de çağrısız kalacak.
"""

import base64
import copy
import json
import mimetypes
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from gozcu.models import Interpretation, Observation

MAX_DESCRIPTION = 300
MAX_NOTABLE_EVENT = 200

# Token tavanı. Kaçak tekrar (aşağıdaki `_MAX_ARRAY_ITEMS` notu) yalnızca bir
# üst sınırla tam olarak kapanıyor: sınır yoksa kod çözücü JSON'u hiç
# kapatmadan üretmeye devam ediyor. 300 + 200 karakterlik iki alan Türkçede
# ~250 token; JSON iskeleti için pay bırakıyoruz.
MAX_TOKENS = 400
# Güvenlik kaydı için düşük ama sıfır değil: sıfır sıcaklık aynı yanlış
# betimlemeyi her karede tekrar üretiyordu.
TEMPERATURE = 0.3

SYSTEM_PROMPT = """Sen bir fabrika güvenlik kamerasını izleyen gözlemcisin.
Sana aynı zaman penceresinden zaman sırasıyla birkaç kare ve o penceredeki
tespit/sinyal özeti verilir.

Kurallar:
- Kareleri tek tek anlatma. Aralarında NE DEĞİŞTİĞİNİ yaz — hareket, duruş,
  yeni giren ya da kadrajdan çıkan nesne.
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

# Üst sınır olmadan strict-JSON şema kod çözümü dizi alanlarında kaçak tekrara
# giriyor: uydurma etiketleri `max_tokens` tükenene kadar yineliyor, JSON hiç
# kapanmıyor ve sonraki alanlara hiç ulaşılmıyor. Bugünkü görü şemasında dizi
# yok; sınır şema sertleştiricisinde duruyor ki bir dizi eklendiği an korumasız
# kalmasın.
_MAX_ARRAY_ITEMS = 8


def strict_schema(schema: dict) -> dict:
    """JSON şemasını OpenAI **strict** structured outputs'a uygun hâle getirir.

    Strict mod HER alanın `required` içinde olmasını ister; pydantic ise
    varsayılanı olan alanı listeden düşürür. `notable_event`'in varsayılanı
    var — yani düz `model_json_schema()` gerçek gateway'de 400 üretiyor,
    denemeler tükeniyor, kademe `degraded` oluyor ve yorumlayıcı HER pencere
    için `None` dönüyor. Sistem çalışıyor görünüp hiçbir şey üretmiyor.

    `maxLength` de çıkarılıyor: `Field(max_length=…)` onu şemaya basıyor ve
    strict-mod arka uçları bunu yaygın olarak reddediyor. Sınır pydantic
    modelinde kalır, kesme `_sanitize_text` ile Python tarafında yapılır.

    Girdi kopyalanır; çağıranın sözlüğü değişmez.
    """
    hardened = copy.deepcopy(schema)
    _harden(hardened)
    return hardened


def _harden(node) -> None:
    if isinstance(node, dict):
        node.pop("maxLength", None)
        if node.get("type") == "array":
            node.setdefault("maxItems", _MAX_ARRAY_ITEMS)
        if "properties" in node:
            node["additionalProperties"] = False
            node["required"] = list(node["properties"])
        for value in list(node.values()):
            _harden(value)
    elif isinstance(node, list):
        for value in node:
            _harden(value)


class _VisionResponse(BaseModel):
    """Görü kademesinden beklenen çıktı. Uzunluk sınırları burada kalır —
    şemadan çıkarılırlar (bkz. `strict_schema`), doğrulamadan çıkmazlar."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(max_length=MAX_DESCRIPTION)
    notable_event: str | None = Field(default=None, max_length=MAX_NOTABLE_EVENT,
                                      description=_NOTABLE_EVENT_DESCRIPTION)

    @classmethod
    def model_json_schema(cls, *args, **kwargs) -> dict:
        """`Gateway.ask` şemayı buradan üretiyor; sertleştirme tek noktada
        kalsın diye üretimin kendisi eziliyor."""
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


def frame_data_uri(frame_path: str | Path) -> str:
    """Kareyi base64 data-URI'ye gömer.

    Uzaktaki gateway yerel dosya yolunu okuyamaz; `interpret.py` görüntüyü
    `{"url": str(frame_path)}` diye gönderiyor ve bu yüzden gateway'e karşı
    hiç çalışamıyor.
    """
    path = Path(frame_path)
    kind = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{kind};base64,{payload}"


def _frame_timestamps(window: list[Observation]) -> list[float]:
    """Pencerenin ilk, orta ve son karesi — sırayla, yinelenenler atılmış.

    Tek kare yetmiyor: devrilen bir istif aracı bir hareket olayı, tek durağan
    görüntü onu ya hâlâ ayakta ya da çoktan yerde gösterir. Yönlendirici hangi
    pencerenin VLM'e ulaşacağını zaten süzdüğü için işaretlenmemiş pencereler
    yine hiçbir şeye mal olmuyor.
    """
    picks = [window[0].ts, window[len(window) // 2].ts, window[-1].ts]
    ordered: list[float] = []
    for ts in picks:
        if ts not in ordered:
            ordered.append(ts)
    return ordered


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


def _message(window: list[Observation], images: list[dict],
             stamps: list[float]) -> list[dict]:
    """Çok parçalı istek gövdesini kuran tek yer.

    Kareler satır içi base64 gidiyor, çekilebilir URL olarak değil: modeller
    verinin yerelde kalması için organizasyonun kendi sunucusunda ayakta ve
    URL isteyen bir gateway görüntüyü almak için dışarı çıkmak zorunda kalırdı
    (decision-log, 23 Ağustos). Kalan risk içerik biçiminin sunucuya göre
    değişmesi — bozulursa düzeltilecek tek yer burası.
    """
    stamp_line = ", ".join(f"{ts:.1f}s" for ts in stamps)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": [
            {"type": "text",
             "text": (f"Sinyaller — {_context(window)}\n\n"
                      f"Aşağıdaki {len(images)} kare zaman sırasıyla "
                      f"{stamp_line} anlarına ait. Bu pencerede ne oluyor, "
                      f"kareler arasında ne değişiyor?")},
            *images]}]


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
              frame_for) -> Interpretation | None:
    """Pencereyi görü kademesine sorar, sonucu depoya yazar.

    `frame_for`: bir `ts` alıp o ana ait kare dosya yolunu (ya da `None`)
    döndüren çağrılabilir.

    `None`'ın dört ayrı anlamı var ve ayrımı `DecisionLoop` için önemli — o
    pencereyi YALNIZCA görü kademesi gerçekten bozukken erteliyor:
    boş pencere, hiç kare bulunamaması ve ayrıştırılamayan çıktı kesinti
    DEĞİL; yalnızca `response.degraded` kesintidir.
    """
    if not window:
        return None

    images = []
    stamps = []
    for ts in _frame_timestamps(window):
        path = frame_for(ts)
        if path is None:
            continue
        images.append({"type": "image_url",
                       "image_url": {"url": frame_data_uri(path)}})
        stamps.append(ts)
    if not images:
        return None

    middle = window[len(window) // 2]

    response = gw.ask("vlm", _message(window, images, stamps),
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
