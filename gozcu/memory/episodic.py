"""Epizodik hafıza — sistemin uzun ufuklu belleği.

Operatör *"daha önce bu araçla ilgili bir olay olmuş muydu?"* diye sorduğunda
cevabın geldiği yer. Gömdüğümüz şey video segmentleri değil, **olay kayıtları**:
her epizot zaten görsel yorumu, tespitleri ve sinyalleri damıtılmış hâlde
taşıyor.

Depo **Qdrant**: takım başına izole bir örnek, LLM ağ geçidinden ayrı adres ve
ayrı anahtarla. Akış: sorguyu göm → Qdrant'ta kosinüs → en iyi `top_k`.
Öncesindeki SQLite + numpy kaba kuvvet çözümü doğruydu ama vektör veritabanı
yarışma gereği; kosinüs artık Python tarafında hesaplanmıyor.

**Reranker yok.** Organizasyon `rerank` kademesini ölçtü ve ZARARLI buldu: ilk
isabet oranı 0,95'ten 0,55'e düşüyor. `Gateway.rerank` yerinde duruyor (test
edilmiş ve zararsız) ama bu modül onu çağırmıyor.

İki bozulma senaryosu bu modülün ana tehdidi ve ikisi de sessizce yutuluyor:

1. **Bozulmuş gömme kademesi.** `Gateway.embed()` kesintide istisna atmıyor,
   `[]` döndürüyor (Görev 03). Boş vektör hem yazma tarafında (anlamsız nokta)
   hem okuma tarafında sessiz yanlış sonuç üretir; iki taraf da korunuyor.
2. **Erişilemez Qdrant.** Gateway ile aynı felsefe: bir kesinti koşuyu
   düşürmez. `search_timeline` `[]`, `embed_episode` `False` döner — hiçbiri
   istisna atmaz.
"""

import hashlib
import os
import threading
import uuid
from pathlib import Path
from weakref import WeakKeyDictionary

from markitdown import MarkItDown
from qdrant_client import QdrantClient
from gozcu.output import trace
from qdrant_client.models import (Distance, Filter, HasIdCondition,
                                  PointIdsList, PointStruct, VectorParams)

from gozcu.core.config import (QDRANT_API_KEY, QDRANT_COLLECTION,
                          QDRANT_DOCUMENT_COLLECTION, QDRANT_PORT,
                          QDRANT_PREFIX, QDRANT_SCORE_THRESHOLD_DIALOGUE,
                          QDRANT_TIMEOUT_S, QDRANT_URL, QDRANT_VECTOR_SIZE)
from gozcu.core.models import DocumentResult, Episode, Precedent

#: Yapılandırılmış uzak istemci — süreç boyunca tek.
_remote_client: QdrantClient | None = None

#: Anahtar tanımlı DEĞİLKEN tutamak başına açılan yerel indeksler. Zayıf
#: anahtar: depo çöpe gittiğinde indeksi de gider ve iki ayrı depo birbirinin
#: epizotlarını görmez.
_local_clients: WeakKeyDictionary = WeakKeyDictionary()

#: Nokta kimliklerinin ad uzayı. Sabit ve DEĞİŞMEZ: değişirse bütün arşiv
#: erişilemez hâle gelir (aynı epizot yeni bir kimlik üretir, eskisi öksüz
#: kalır ve dışlama artık onu bulamaz).
_NAMESPACE = uuid.UUID("6f5f1f7c-0b4a-5a3e-9c2d-7e1b8a4f3d20")

#: Yerel Qdrant eş zamanlı erişimde güvenli değil (B7). Ölçüldü:
#: `ValueError: operands could not be broadcast together with shapes
#: (32,) (31,)` — ve `search_timeline`'ın geniş `except`'i onu yutuyordu,
#: yani 400 sorgunun 6'sı sessizce `[]` dönüyordu.
#:
#: **Koşulsuz.** "Yalnız yerel istemciyi sar" denendi ve uygulanamaz:
#: `_client()` doğrudan geçilen bir istemciyi olduğu gibi döndürüyor ve o
#: dalda yerel mi uzak mı olduğu bilinmiyor — testlerin çoğu ve kalibrasyon
#: script'i tam o dalı kullanıyor. `not QDRANT_API_KEY` predikatı da yanlış
#: olurdu: anahtar doluyken doğrudan geçilen yerel bir istemci kilitsiz
#: kalırdı. Ölçülebilir maliyeti yok — `upsert`/`query_points` zaten seri.
#:
#: **Yeniden girişli DEĞİL** (`Lock`, `RLock` değil): `_ensure_collection`
#: kilidi kendi içinde alıyor, bu yüzden ONUN kilidi altından çağrılamaz.
_LOCK = threading.Lock()

#: Dedup'tan önce kaç kat fazla aday çekiliyor. Kaynak tekilleştirmesi
#: `top_k` KESİLMEDEN önce çalışmak zorunda: sonra yapılırsa aynı kaynağın
#: ikizleri gerçek emsallerin yerini çalar (B8).
_DEDUP_OVERSAMPLE = 4

#: `video_key` bu kadar bayt okuyor. Tamamını okumak 19 MB'lık bir klipte
#: her koşuda gereksiz I/O; ilk 1 MB + dosya boyutu iki farklı videoyu
#: ayırmaya fazlasıyla yetiyor.
_KEY_BYTES = 1024 * 1024


def video_key(path) -> str:
    """Videonun kimliği: ilk 1 MB + dosya boyutu üzerinden sha256 (16 hane).

    **Dosya adı değil İÇERİK.** Yükleme akışı ya da kopyalanmış bir
    `video.mp4` iki farklı videoyu aynı isimle getirebiliyor; ada dayalı bir
    anahtar o iki alakasız olayı tek noktada birleştirirdi — çoğaltmadan
    kötü.

    **Okunamayan dosyada İSTİSNA ATMAZ.** Süreç başına sabit bir önek döner:
    kimlik o koşu boyunca tutarlı kalır (epizotlar birbirini ezmez), yalnız
    süreçler arası kalıcı değildir. `tests/test_run.py` var olmayan bir
    `"video.mp4"` yolunu 29 kez geçiyor — atan bir sürüm hepsini çökertirdi.
    """
    try:
        with open(path, "rb") as handle:
            head = handle.read(_KEY_BYTES)
        size = os.path.getsize(path)
    except OSError:
        return f"proc-{os.getpid()}"
    digest = hashlib.sha256(head + str(size).encode())
    return digest.hexdigest()[:16]


def point_id(source: str | None, episode_id: int) -> str:
    """Qdrant nokta kimliği — `(source, episode_id)` çifti üzerinden kararlı.

    `Episode` DEĞİL iki alan alıyor: dışlama filtresi (`search_timeline`)
    elinde epizot nesnesi yokken de aynı kimliği hesaplayabilmeli.

    **İkinci parça `episode.id`, `start_ts` DEĞİL.** `DecisionLoop.catch_up`
    ertelenmiş pencereleri sonradan işliyor ve DAHA ERKEN `start_ts`'li
    epizotlar doğurabiliyor; zamana dayalı bir kimlik tam o anda kimlikleri
    birbirine kaydırırdı.
    """
    return str(uuid.uuid5(_NAMESPACE, f"{source}:{episode_id}"))


def memory_backend() -> str:
    """Hafızanın gerçekten nereye yazıldığı: `"qdrant"` ya da `"local"`.

    Anahtar tanımlı değilken `build_client()` süreç içi bir Qdrant'a düşüyor
    ve sistem **tamamen sağlıklı görünüyor** — ama epizodik hafıza süreçle
    birlikte yok oluyor, takımlar arası izole örneğe hiçbir şey yazılmıyor.
    Sessiz bir düşüş, bu kod tabanında bugün beş kez aynı arızayı üretti;
    bu yüzden düşüşün kendisi değil, **görünmezliği** kabul edilemez.

    Konsol ve KPI bunu göstersin diye tek kelimeyle dışarı veriliyor —
    `kpi.run_status`'ın bozulmuş koşuyu göstermesiyle aynı gerekçe.
    """
    return "qdrant" if QDRANT_API_KEY else "local"


def build_client() -> QdrantClient:
    """Yapılandırmadan bir Qdrant istemcisi kurar.

    Üç ayrıntı resmî belgeden geliyor ve üçü de sessizce yanlış davranıyor:

    - **`port=443` zorunlu.** Verilmezse istemci `https://` şemasını yok sayıp
      kendi varsayılan portuna düşüyor; hata `Connection refused` oluyor ve
      nedeni hiç göstermiyor.
    - **Yalnız REST.** Takımlara port değil yol ön eki veriliyor, gRPC bir ön
      ek üzerinden yönlendirilemez — `prefer_grpc` HİÇ geçilmiyor.
    - **Anahtar ayrı.** Vektör veritabanının anahtarı LLM bearer token'ı
      değil; yalnız ortamdan geliyor.

    Anahtar tanımlı değilse süreç içi yerel bir Qdrant'a düşülüyor: sistem
    yapılandırılmamış bir ortamda da (test, çevrimdışı demo) çalışır, sadece
    hafıza süreçle birlikte yok olur.
    """
    if not QDRANT_API_KEY:
        return QdrantClient(":memory:")
    return QdrantClient(url=QDRANT_URL,
                        port=QDRANT_PORT,      # ZORUNLU — bkz. docstring
                        prefix=QDRANT_PREFIX,
                        api_key=QDRANT_API_KEY,
                        timeout=QDRANT_TIMEOUT_S,
                        # Kurulum anında sürüm sorgusu atılmıyor: bağlantı
                        # arızası import/çağrı sınırında değil, kendi
                        # yutulduğu yerde görünmeli.
                        check_compatibility=False)


def _client(handle) -> QdrantClient | None:
    """Çağıranın verdiği tutamağı bir Qdrant istemcisine çevirir.

    Görev 09/11/14 ikinci argüman olarak `Store` geçiriyor ve o dosyalar bu
    göçün kapsamı dışında — imza onları kırmadan taşımak zorunda. Qdrant
    istemcisi geçildiyse o kullanılıyor (testler ve Görev 17'nin bağlaması),
    başka bir şey geçildiyse yapılandırmadan kurulana düşülüyor.

    Anahtar yokken istemci **tutamak başına** açılıyor: yerel indeks o zaman
    onu taşıyan deponun ömrünü paylaşır, iki ayrı depo birbirinin epizotlarını
    görmez. Anahtar varken tek bir uzak istemci paylaşılıyor.
    """
    if hasattr(handle, "upsert") and hasattr(handle, "query_points"):
        return handle
    try:
        if not QDRANT_API_KEY:
            client = _local_clients.get(handle)
            if client is None:
                client = _local_clients[handle] = build_client()
            return client
        global _remote_client
        if _remote_client is None:
            _remote_client = build_client()
        return _remote_client
    except Exception:  # noqa: BLE001 — kesinti bir koşuyu düşürmemeli
        return None


def _ensure_collection(client, collection: str = QDRANT_COLLECTION) -> None:
    """Koleksiyon yoksa kurar — boyutu ve mesafesi bizden.

    Organizasyon koleksiyonu hazır vermiyor; boyut gömme modelinin çıktısına
    bağlı (`bge-m3-embed` → 1024) ve mesafe kosinüs.

    `collection` varsayılanlı: epizot yolu (`embed_episode`, `search_timeline`)
    adı hiç geçirmiyor ve geçirmemeli. Belge yolu (`embed_document`) kendi
    koleksiyonunu veriyor — bkz. `config.QDRANT_DOCUMENT_COLLECTION`.
    """
    # Kontrol ile kurulum TEK kilit altında: ikisinin arasındaki boşlukta
    # ikinci bir iş parçacığı da "yok" görüp koleksiyonu kurmaya kalkar.
    #
    # Qdrant'ın kendi zaman aşımı 600 s ve bu çağrı gateway'den GEÇMİYOR —
    # yani `gw.ask`'in kalp atışı buraya ulaşmıyor, ayrıca kaydedilmeli.
    with _LOCK:
        with trace.step("qdrant.koleksiyon-kontrol", collection):
            exists = client.collection_exists(collection)
        if not exists:
            client.create_collection(
                collection,
                vectors_config=VectorParams(size=QDRANT_VECTOR_SIZE,
                                            distance=Distance.COSINE))


class _DocumentHandle:
    """`_client()`'ın yerel-indeks sözlüğü için zayıf referans alınabilir bir
    anahtar. Belgeler bir koşuya ait değil, yani ortada anahtar olarak
    kullanılacak bir `Store` yok; `None` geçmek `WeakKeyDictionary`'yi
    `TypeError` ile düşürürdü."""


#: Belge gömmelerinin tutamağı — süreç boyunca tek.
_documents_handle = _DocumentHandle()

#: Gömmeye giren en fazla karakter. `bge-m3-embed` uzun girdiyi kendi kesiyor
#: ama sessizce: 200 KB'lık bir prosedür dosyasının tamamını göndermek hem
#: ağ geçidini boşuna yorar hem de vektörü belgenin YALNIZ başına
#: yakınsatır. Kesme burada, görünür şekilde yapılıyor.
_DOCUMENT_EMBED_CHARS = 8000

SEARCH_TIMELINE_SCHEMA = {"type": "function", "function": {
    "name": "search_timeline",
    "description": "Geçmiş olay arşivinde anlamsal arama yapar. "
                   "Daha önce benzer olaylar olup olmadığını kontrol eder.",
    "parameters": {"type": "object",
                   "properties": {"query": {"type": "string",
                                            "description": "Aranacak olay"}},
                   "required": ["query"]}}}

SEARCH_DOCUMENTS_SCHEMA = {"type": "function", "function": {
    "name": "search_documents",
    "description": "Operatörün yüklediği referans belgelerinde anlamsal arama "
                   "yapar. Vardiya listesi, ekipman kartı, prosedür, güvenlik "
                   "talimatı gibi belgelerde bilgi arar.",
    "parameters": {"type": "object",
                   "properties": {"query": {"type": "string",
                                            "description": "Aranacak konu"}},
                   "required": ["query"]}}}


def _extract_text(file_path) -> str:
    """Dosyadan metin çıkarır: MarkItDown → UTF-8 geri dönüş."""
    path = Path(file_path)

    # MarkItDown ile dene
    try:
        md = MarkItDown()
        result = md.convert(str(path))
        text = (result.text_content or "").strip()[:_DOCUMENT_EMBED_CHARS]
        if text:
            return text
    except Exception:  # noqa: BLE001
        pass

    # UTF-8 geri dönüş
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8").strip()[:_DOCUMENT_EMBED_CHARS]
        return text
    except (UnicodeDecodeError, OSError):
        return ""


def embed_document(gw, document, file_path, client=None) -> bool:
    """Yüklenen belgeyi **belge koleksiyonuna** gömer; yazıldıysa `True`.

    **`episodes`'a YAZMIYOR.** Gerekçe `config.QDRANT_DOCUMENT_COLLECTION`'da
    uzun uzun yazılı ve tek cümlesi şu: `search_timeline` dönen her noktayı
    bir `Episode` diye geri kuruyor, yani oraya yazılan bir vardiya talimatı
    ajanın gözünde "fabrikada olmuş bir olay" hâline gelirdi.

    `embed_episode` ile aynı sözleşme: **istisna atmaz.** Yükleme akışı
    (`POST /api/library/documents`) buna dayanıyor — gömme kademesi bozukken
    belge yine saklanmalı, yalnız `embedded` damgası düşmeli.

    MarkItDown ile ikili dosyalar (PDF, DOCX, PPTX, XLSX) çözülür. Başarısız
    olursa UTF-8 decode denensin — o da başarısız olursa `False`.
    """
    try:
        if gw is None:
            return False

        text = _extract_text(file_path)
        if not text:
            return False

        target = _client(client if client is not None else _documents_handle)
        if target is None:
            return False
        # Ad da metne giriyor: "yangın prosedürü" araması, gövdesinde o
        # kelime hiç geçmeyen `yangin-proseduru.md`'yi de bulabilmeli.
        vector = list(gw.embed(f"{document.name} | {text}"))
        if not vector or len(vector) != QDRANT_VECTOR_SIZE:
            return False

        _ensure_collection(target, QDRANT_DOCUMENT_COLLECTION)
        with trace.step("qdrant.belge-yaz", document.id):
            with _LOCK:
                target.upsert(
                    QDRANT_DOCUMENT_COLLECTION,
                    points=[PointStruct(
                        # `point_id` KULLANILMIYOR: imzası `(source,
                        # episode_id: int)` ve ikinci parçası epizot kimliği.
                        # Belge kimliği bir epizot kimliği değil; o yardımcıyı
                        # zorlamak sözleşmesini bulandırırdı.
                        id=str(uuid.uuid5(_NAMESPACE, f"belge:{document.id}")),
                        vector=vector,
                        payload={"document_id": document.id,
                                 "name": document.name,
                                 "text": text})])
        return True
    except Exception:  # noqa: BLE001 — yükleme akışı istisna beklemiyor
        return False


def delete_document_vector(doc_id: str, client=None) -> None:
    """Belgenin Qdrant vektörünü siler (§4b). İstisna atmaz — ama SUSMAZ.

    Silme endpoint'i belgeyi kütüphaneden sildikten sonra çağırıyor; bu
    fonksiyon yine de istisna yükseltemez çünkü dosya zaten diskten gitmiş
    olur ve buradan kaçan bir hata operatöre "silinmedi" yalanı söylerdi.
    Ama spec §4b'nin ikinci yarısı **"uyarı loglanır"**: kesinti tamamen
    sessiz kalırsa öksüz vektörler hiçbir yerde görünmeden birikir. Yazma
    tarafındaki kardeşleriyle (`embed_document`'ın `qdrant.belge-yaz`'ı,
    `embed_episode`'ın `qdrant.yaz`'ı) aynı `trace.step` deseni: adım
    patlarsa `✗` satırı yazılır, İSTİSNA SONRA yukarı verilir — burada onu
    dıştaki `except` yakalayıp yutuyor, tam olarak `embed_document`'ın
    davrandığı gibi.
    """
    try:
        target = _client(client if client is not None else _documents_handle)
        if target is None:
            return
        with _LOCK:
            if not target.collection_exists(QDRANT_DOCUMENT_COLLECTION):
                return
        pid = str(uuid.uuid5(_NAMESPACE, f"belge:{doc_id}"))
        with trace.step("qdrant.belge-sil", doc_id):
            with _LOCK:
                target.delete(
                    collection_name=QDRANT_DOCUMENT_COLLECTION,
                    points_selector=PointIdsList(points=[pid]))
    except Exception:  # noqa: BLE001 — bkz. docstring: iz kaydedilir, yükseltilmez
        pass


def embed_episode(gw, client, episode: Episode) -> bool:
    """Kapanan epizodu gömer; vektör yazıldıysa `True`.

    **Bu fonksiyon istisna atmaz — atamaz.** Görev 07'nin `synthesize`'ı
    kapanışta `on_close(episode)` çağırıyor ve bu geri çağrı oradan
    tetikleniyor; buradan kaçan bir istisna, zaten başarıyla yazılmış epizodu
    ve devir teslim kaydını birlikte götürür. Arıza bu yüzden dönüş
    değerinde görünür: `False` "bu epizodun vektörü yok" demek, çağıran taraf
    kademe düzeldiğinde yeniden gömebilir. Erişilemez Qdrant de aynı dala
    düşüyor.

    Kademe bozukken `gw.embed()` `[]` döndürüyor ve o nokta YAZILMIYOR:
    yazılsaydı arama onu gerçek bir emsalmiş gibi geri verirdi ve boş vektöre
    karşı kosinüs anlamsızdır. Yanlış boyutlu vektör de yazılmıyor —
    koleksiyonun boyutu sabit ve uyuşmayan bir vektör okuma tarafını bozar.

    Nokta kimliği `(source, episode_id)` çiftinden hesaplanıyor
    (`point_id`): aynı epizodu iki kez gömmek arşivi çoğaltmaz, noktanın
    üstüne yazar (yükleyici buna dayanıyor ve tekrarsızlık kontrolü tutmuyor).
    İki farklı videonun 1 numaralı epizotları ise AYRI noktalar — kimlik
    yalnız `episode.id` olsaydı ikincisi birincisini ezerdi.
    """
    try:
        if episode.id is None:
            return False
        if episode.summary_source == "fallback":
            # Arıza metni arşive gömülmez: gelecek koşuların emsal aramasını
            # zehirler (spec §1). `False` mevcut sözleşme — kademe düzelip
            # özet iyileştiğinde yeniden gömülebilir.
            return False
        target = _client(client)
        if target is None:
            return False
        text = (f"{episode.summary_tr} | "
                f"katılımcılar: {', '.join(episode.participants)}")
        vector = list(gw.embed(text))
        if not vector or len(vector) != QDRANT_VECTOR_SIZE:
            return False

        # Kilidin DIŞINDA: `_ensure_collection` kilidi kendi içinde alıyor
        # ve `_LOCK` yeniden girişli değil — buradan kilit altında çağırmak
        # süreci kendi üstüne kilitlerdi.
        _ensure_collection(target)
        # Yük (payload) epizodun tamamı: bir arama sonucu ikinci bir SQLite
        # okuması olmadan kullanılabilir olmalı ve `Episode` payload'dan
        # birebir geri kuruluyor.
        with trace.step("qdrant.yaz", f"epizot={episode.id}"):
            with _LOCK:
                target.upsert(
                    QDRANT_COLLECTION,
                    points=[PointStruct(
                        id=point_id(episode.source, episode.id),
                        vector=vector, payload=episode.model_dump())])
        return True
    except Exception:  # noqa: BLE001 — bkz. docstring: geri çağrı istisna atamaz
        return False


def _episode(point) -> Episode | None:
    """Bir Qdrant noktasını `Episode`'a geri çevirir; okunamazsa `None`.

    Payload'dan kuruluyor, depodan değil: çağıran taraf (Görev 11/14) elinde
    yalnız gateway ve depo tutamağı ile duruyor, ikinci bir SQLite okuması
    hem gereksiz hem de arşiv ile indeksi ayrıştırırdı. Bilinmeyen anahtarlar
    süzülüyor — `Episode` `extra="forbid"` ve şema büyüdüğünde eski noktalar
    okunmaya devam etmeli.
    """
    payload = point.payload or {}
    try:
        return Episode(**{k: v for k, v in payload.items()
                          if k in Episode.model_fields})
    except Exception:  # noqa: BLE001 — bozuk tek nokta aramayı düşürmemeli
        return None


def search_timeline(gw, client, query: str, top_k: int = 5,
                    exclude: tuple[str | None, int] | None = None,
                    threshold: float | None = None) -> list[Precedent]:
    """Sorguya en yakın epizotlar, skorlarıyla, en alakalı önce.

    `exclude` bir **çift**: `(source, episode_id)`. Dışlamayı **Qdrant
    yapıyor** (`must_not=[HasIdCondition]`), Python değil — süzme sonradan
    yapılsaydı dışlanan epizot `top_k`'dan bir yer çalardı. `assess_risk`
    sorguyu `episode.summary_tr` ile atıyor, yani tam olarak gömülmüş
    metinle; süzülmezse epizot kendi emsali olarak listenin başında görünür.

    Tek bir sayı yetmiyordu: farklı videoların epizotları da 1 numarayı
    taşıyor ve düz bir `episode_id` eşleşmesi **iki noktanın ikisini birden**
    elerdi. Nokta kimliği artık `source`'u içerdiği için hesaplanan UUID tam
    olarak bir noktayı eliyor.

    `threshold` verilirse skoru altında kalan aday düşer. **`None` "koruma
    yok" demek ve varsayılan bu:** `0.0` bir korumasızlık değeri DEĞİL,
    kosinüs negatif skor üretebilir ve `0.0` negatifleri süzer — yani
    ölçülmemiş bir eşiktir. Sayılar `config`'ten, kalibrasyondan geliyor.

    Sonuçta bir kaynak (`Episode.source`) **en fazla bir kez** görünüyor:
    aynı videonun ikinci koşusu emsal listesini ikizliyordu (B8). Tekilleştirme
    `top_k` kesilmeden ÖNCE, bu yüzden aday kümesi `_DEDUP_OVERSAMPLE` katı
    çekiliyor.

    Boş liste dört durumda döner: koleksiyon yok (hiç epizot gömülmemiş),
    arşiv boş, sorgu vektörü boş (arama anında kademe bozuk) ve Qdrant
    erişilemez. Hiçbiri istisna atmaz.
    """
    try:
        target = _client(client)
        if target is None:
            return []
        # Kontrol de kilit altında: kontrol ile sorgu ARASINDAKİ boşluk B7'nin
        # tam olarak vurduğu yer.
        with _LOCK:
            if not target.collection_exists(QDRANT_COLLECTION):
                return []

        query_vector = list(gw.embed(query))
        if not query_vector:
            return []

        exclusion = None
        if exclude is not None:
            # Kimlik hesaplanıyor, payload'da AYRI bir anahtar aranmıyor:
            # yazma tarafı da aynı `point_id`'yi kullanıyor ve iki taraf tek
            # fonksiyondan geldiği sürece ayrışamaz.
            exclusion = Filter(
                must_not=[HasIdCondition(has_id=[point_id(*exclude)])])
        with _LOCK:
            response = target.query_points(
                QDRANT_COLLECTION, query=query_vector,
                # Tekilleştirme kesimden ÖNCE koşuyor; aday kümesi bu yüzden
                # `top_k`'nın katı.
                limit=top_k * _DEDUP_OVERSAMPLE,
                with_payload=True, query_filter=exclusion)
    except Exception:  # noqa: BLE001 — vektör veritabanının kesintisi bir
        # koşuyu düşürmemeli; arama sonuçsuz döner, sistem çalışmaya devam eder.
        return []

    # Qdrant'ın sırası NİHAİ sıra. Eski akış burada `gw.rerank` çağırıyordu;
    # organizasyon o kademeyi ölçtü ve zararlı buldu — ilk isabet 0,95'ten
    # 0,55'e düşüyor. `Gateway.rerank` yerinde duruyor, sadece çağrılmıyor.
    #
    # `embed_episode` yedek özetli epizotları artık gömmüyor (spec §1) — ama
    # bu bir yazma tarafı disiplini, arşivin kendisini temizlemiyor. team37
    # koleksiyonu KALICI: bu kural konmadan ÖNCE gömülmüş zehirli noktalar
    # hâlâ orada durabilir, aynı kimlik yeniden üretilmedikçe üstüne
    # yazılacakları garanti değil. Süzme burada, TEK boğazda yapılıyor çünkü
    # sonucu iki ayrı tüketici okuyor: `risk.py` analist prompt'una
    # `- {summary_tr}` diye basıyor, `supervisor.py`'nin SEARCH_TIMELINE dalı
    # alanları tool sonucuna projekte ediyor — ikisi de kendi başına süzse
    # iki kopya birbirinden ayrışabilirdi.
    found: list[Precedent] = []
    for point in response.points:
        episode = _episode(point)
        if episode is None or episode.summary_source == "fallback":
            continue
        if threshold is not None and point.score < threshold:
            continue
        found.append(Precedent(episode=episode, score=point.score))

    # Kaynak başına EN İYİ skor — kesimden ÖNCE. `response.points` zaten
    # skora göre sıralı, o yüzden ilk görülen en iyisi.
    #
    # **`source is None` olan noktalar dedup'a GİRMİYOR.** `None` bir kaynak
    # değil, kaynağın yokluğu: bu değişiklikten önce yazılmış her nokta ve
    # kaynağı üretilememiş her epizot onu taşıyor. Hepsini tek kovaya koymak
    # "aynı videonun ikizi" ile "kökeni bilinmeyen üç ayrı olay"ı aynı şeye
    # çevirir ve arşivi tek emsale indirir — B8'i onarırken B4'ten beter bir
    # şey yapmış oluruz. Kimliksizler kendi başlarına geçer.
    best: dict[str, Precedent] = {}
    kept: list[Precedent] = []
    for precedent in found:
        source = precedent.episode.source
        if source is None:
            kept.append(precedent)
        elif source not in best:
            best[source] = precedent
            kept.append(precedent)
    return kept[:top_k]


def search_documents(gw, query: str, top_k: int = 3,
                     threshold: float | None = None,
                     client=None) -> list[DocumentResult]:
    """Belge koleksiyonunda anlamsal arama (§3a).

    `search_timeline` ile aynı sözleşme: istisna atmaz, boş liste döner.

    **`threshold=None` "filtre yok" DEĞİL** (§3c): verilmediğinde
    `QDRANT_SCORE_THRESHOLD_DIALOGUE`'a çözülüyor. Eşiksiz arama, kosinüs
    sıralamasının ilk `top_k` belgesini alaka gözetmeden döndürür —
    operatörün yüklediği tek şey bir vardiya çizelgesiyse fren bakımı
    sorusunun cevabı da o olur ve doğrudan risk gerekçesine girer. İstemin
    "Sonuç bu olayla ilgisizse KULLANMA" kuralı modelin insafına
    bırakılamaz; sayısal koruma burada. Çağıran kendi eşiğini verebilir
    (§6d: analist `QDRANT_SCORE_THRESHOLD_RISK` geçiyor).
    """
    # Çözüm sonuçlar süzülmeden ÖNCE: `None` bir eşik değeri değil,
    # "varsayılanı kullan" demek.
    limit_score = (QDRANT_SCORE_THRESHOLD_DIALOGUE if threshold is None
                   else threshold)
    try:
        target = _client(client if client is not None else _documents_handle)
        if target is None:
            return []
        with _LOCK:
            if not target.collection_exists(QDRANT_DOCUMENT_COLLECTION):
                return []

        query_vector = list(gw.embed(query))
        if not query_vector:
            return []

        with _LOCK:
            response = target.query_points(
                QDRANT_DOCUMENT_COLLECTION, query=query_vector,
                limit=top_k, with_payload=True)
    except Exception:  # noqa: BLE001
        return []

    results: list[DocumentResult] = []
    for point in response.points:
        payload = point.payload or {}
        if point.score < limit_score:
            continue
        text = payload.get("text", "")
        results.append(DocumentResult(
            document_id=payload.get("document_id", ""),
            name=payload.get("name", ""),
            text_excerpt=text[:500],
            score=point.score))
    return results
