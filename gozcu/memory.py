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

from weakref import WeakKeyDictionary

from qdrant_client import QdrantClient
from qdrant_client.models import (Distance, Filter, HasIdCondition,
                                  PointStruct, VectorParams)

from gozcu.config import (QDRANT_API_KEY, QDRANT_COLLECTION, QDRANT_PORT,
                          QDRANT_PREFIX, QDRANT_TIMEOUT_S, QDRANT_URL,
                          QDRANT_VECTOR_SIZE)
from gozcu.models import Episode

#: Yapılandırılmış uzak istemci — süreç boyunca tek.
_remote_client: QdrantClient | None = None

#: Anahtar tanımlı DEĞİLKEN tutamak başına açılan yerel indeksler. Zayıf
#: anahtar: depo çöpe gittiğinde indeksi de gider ve iki ayrı depo birbirinin
#: epizotlarını görmez.
_local_clients: WeakKeyDictionary = WeakKeyDictionary()


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


def _ensure_collection(client) -> None:
    """Koleksiyon yoksa kurar — boyutu ve mesafesi bizden.

    Organizasyon koleksiyonu hazır vermiyor; boyut gömme modelinin çıktısına
    bağlı (`bge-m3-embed` → 1024) ve mesafe kosinüs.
    """
    if not client.collection_exists(QDRANT_COLLECTION):
        client.create_collection(
            QDRANT_COLLECTION,
            vectors_config=VectorParams(size=QDRANT_VECTOR_SIZE,
                                        distance=Distance.COSINE))


def _write_ledger(handle, episode_id: int, vector: list[float]) -> None:
    """`Store` geçiren eski çağıranlar için gömme defteri.

    Görev 09'un fikstür yükleyicisi hangi epizodun gömüldüğünü hâlâ
    `Store.embeddings()` üzerinden okuyor (`gozcu/fixtures/loader.py`) ve o
    dosya bu göçün kapsamı dışında. SQLite satırı artık **arama indeksi
    değil**, yalnız "bu epizot gömüldü" defteri; `search_timeline` ona hiç
    bakmıyor. Yükleyici tekrarsızlık kontrolünü Qdrant'a taşıdığında bu
    fonksiyon da `Store.save_embedding` de ölür.
    """
    if not hasattr(handle, "save_embedding"):
        return
    try:
        handle.save_embedding(episode_id, vector)
    except Exception:  # noqa: BLE001 — defter arızası, Qdrant'a GİRMİŞ bir
        pass          # vektörü "yazılmadı" diye raporlamamalı.


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

    Nokta kimliği epizot kimliği: aynı epizodu iki kez gömmek arşivi
    çoğaltmaz, noktanın üstüne yazar (Görev 09'un yükleyicisi buna dayanıyor).
    """
    try:
        if episode.id is None:
            return False
        target = _client(client)
        if target is None:
            return False
        text = (f"{episode.summary_tr} | "
                f"katılımcılar: {', '.join(episode.participants)}")
        vector = list(gw.embed(text))
        if not vector or len(vector) != QDRANT_VECTOR_SIZE:
            return False

        _ensure_collection(target)
        # Yük (payload) epizodun tamamı: bir arama sonucu ikinci bir SQLite
        # okuması olmadan kullanılabilir olmalı ve `Episode` payload'dan
        # birebir geri kuruluyor.
        target.upsert(QDRANT_COLLECTION,
                      points=[PointStruct(id=episode.id, vector=vector,
                                          payload=episode.model_dump())])
        _write_ledger(client, episode.id, vector)
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
                    exclude_id: int | None = None) -> list[Episode]:
    """Sorguya en yakın epizotlar, en alakalı önce.

    `exclude_id` verilen epizodu aday kümesinden düşürür ve bunu **Qdrant
    yapıyor** (`must_not=[HasIdCondition]`), Python tarafında süzmüyoruz:
    süzme sonradan yapılsaydı dışlanan epizot `top_k`'dan bir yer çalardı.
    Görev 11 sorguyu `episode.summary_tr` ile atıyor — yani tam olarak
    gömülmüş metinle — ve süzülmezse epizot kendi emsali olarak listenin
    başında görünür.

    Boş liste dört durumda döner: koleksiyon yok (hiç epizot gömülmemiş),
    arşiv boş, sorgu vektörü boş (arama anında kademe bozuk) ve Qdrant
    erişilemez. Hiçbiri istisna atmaz.
    """
    try:
        target = _client(client)
        if target is None or not target.collection_exists(QDRANT_COLLECTION):
            return []

        query_vector = list(gw.embed(query))
        if not query_vector:
            return []

        exclusion = (Filter(must_not=[HasIdCondition(has_id=[exclude_id])])
                     if exclude_id is not None else None)
        response = target.query_points(QDRANT_COLLECTION, query=query_vector,
                                       limit=top_k, with_payload=True,
                                       query_filter=exclusion)
    except Exception:  # noqa: BLE001 — vektör veritabanının kesintisi bir
        # koşuyu düşürmemeli; arama sonuçsuz döner, sistem çalışmaya devam eder.
        return []

    # Qdrant'ın sırası NİHAİ sıra. Eski akış burada `gw.rerank` çağırıyordu;
    # organizasyon o kademeyi ölçtü ve zararlı buldu — ilk isabet 0,95'ten
    # 0,55'e düşüyor. `Gateway.rerank` yerinde duruyor, sadece çağrılmıyor.
    found = [_episode(point) for point in response.points]
    return [episode for episode in found if episode is not None]
