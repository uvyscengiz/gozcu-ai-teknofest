# Görev 08 — Epizodik hafıza araması (`gozcu/memory.py`)

> ## ✅ TAMAMLANDI — 23 Ağustos 2026, `1cdb29b`
>
> **24 Ağustos: Qdrant'a taşındı — `7d6a473`.** Vektör veritabanı yarışma
> gerekliliği; organizasyon takım başına izole bir Qdrant veriyor ve kosinüs
> artık Python tarafında hesaplanmıyor.
>
> **Hafıza katmanı indi.** `gozcu/memory.py` var, `tests/test_memory.py` 21
> test ile yeşil. Bu dosyayı yeniden uygulama — aşağısı ne yapıldığının kaydı.
>
> **Sonraki göreve başlarken bilmen gerekenler**
> ([kararlar](#tamamlanma-notları-gelecek-görevleri-bağlayan) bölümüne bak):
> `embed_episode` `bool` döndürüyor ve **asla istisna atmıyor** — bağlayan
> tarafın `try/except`'e ihtiyacı yok; `search_timeline` `exclude_id` alıyor ve
> sorgu metni bir epizottan geliyorsa geçilmek zorunda; **erişilemez Qdrant bir
> koşuyu düşürmüyor** (arama `[]`, gömme `False`); ve `GOZCU_QDRANT_API_KEY`
> tanımlı değilken hafıza sessizce süreç içinde kalıyor — `memory_backend()`
> bunu tek kelimeyle söylüyor.

**Sahip:** `uvyscengiz` · **Gün:** 25 Ağustos · **Süre:** ~2 saat
**Bağımlılık:** [01](01-sozlesme.md), [02](02-olay-deposu.md), [03](03-gateway.md), [07](07-sentezleyici.md)

## Bağlam

Sistemin uzun ufuklu hafızası. Operatör *"daha önce bu araçla ilgili bir olay
olmuş muydu?"* diye sorduğunda cevabın geldiği yer.

**Ne gömdüğümüz konusunda dürüst olalım:** video segmentlerini değil, **olay
kayıtlarını** gömüyoruz. Her epizot kaydı zaten görsel yorumu, tespitleri ve
sinyalleri içeriyor — yani damıtılmış bir temsil. API'den bir video kodlayıcıya
erişimimiz yok ve olmayan bir şeyi iddia etmiyoruz. Bu haliyle de tez ayakta:
bir olayı çok daha öncekine bağlamak, context penceresine sığandan fazlasını
hatırlamak.

**Depo Qdrant.** Organizasyon takım başına **izole bir örnek** veriyor
(`https://evren-vektor.ssyz.org.tr`, ön ek `team37`); LLM ağ geçidinden
geçmiyor, ayrı adres ve **ayrı anahtar**. Öncesindeki SQLite + numpy kaba
kuvvet kosinüs çözümü doğruydu — bir vardiya birkaç yüz epizot demek — ama
vektör veritabanı yarışma gereği ve geçiş bir ürün kararı. Ayrıntılar:
[EVREN saha notları](../06-references/evren-gateway.md).

**Reranker yok.** Organizasyon `rerank` kademesini kendi ölçtü ve **zararlı**
buldu: ilk isabet oranı 0,95'ten 0,55'e düşüyor. `Gateway.rerank` yerinde
duruyor (test edilmiş, zararsız) ama bu modül onu çağırmıyor.

## Kurulum

```bash
uv sync --extra dev
uv run pytest tests/test_gateway.py tests/test_store.py -v
```

`qdrant-client` bir **çalışma zamanı** bağımlılığı — `pyproject.toml`'da
duruyor. Testler ağ görmüyor: hepsi süreç içi `QdrantClient(":memory:")` ile
koşuyor.

## Bağımlı olduğun imzalar

```python
# gozcu/gateway.py
Gateway.embed(text: str) -> list[float]
Gateway.rerank(query: str, candidates: list[str]) -> list[int]
#   ^ duruyor ama ÇAĞRILMIYOR: organizasyonun ölçümü R@1 0,95 → 0,55.

# gozcu/config.py — hepsi ortamdan geçersiz kılınabilir
QDRANT_URL          # "https://evren-vektor.ssyz.org.tr"
QDRANT_PORT         # 443 — ZORUNLU, bkz. aşağıdaki tuzaklar
QDRANT_PREFIX       # "team37" — port değil YOL ÖN EKİ, bu yüzden REST-only
QDRANT_API_KEY      # GOZCU_QDRANT_API_KEY — LLM bearer token'ından AYRI
QDRANT_COLLECTION   # "episodes"
QDRANT_VECTOR_SIZE  # 1024 = bge-m3-embed çıktısı
QDRANT_TIMEOUT_S    # 600

# gozcu/store.py — artık ARAMA İNDEKSİ DEĞİL, yalnız gömme defteri
Store.save_embedding(episode_id: int, vector: list[float]) -> None
Store.embeddings() -> list[tuple[int, list[float]]]

# gozcu/models.py
Episode(id, start_ts, end_ts, phase, summary_tr, participants, preliminary_risk, state)
```

**Üç tuzak, üçü de sessiz** (kaynak: EVREN saha notları):

1. **`port=443` zorunlu.** Verilmezse `qdrant-client` `https://` şemasını yok
   sayıp kendi varsayılan portuna düşüyor; hata `Connection refused` oluyor ve
   nedeni hiç göstermiyor.
2. **Yalnız REST, gRPC yok.** Takımlara port değil yol ön eki veriliyor ve gRPC
   bir ön ek üzerinden yönlendirilemiyor — `prefer_grpc=True` hiç geçilmemeli.
3. **Koleksiyonu biz kuruyoruz, boyutunu biz seçiyoruz.** `bge-m3-embed` →
   **1024**, `Distance.COSINE`.

**Boş vektör guard'ı (Görev 03).** `gw.embed()` gömme kademesi bozukken istisna
atmıyor, **`[]` döndürüyor**. Boş vektör ne yazılır ne de sorgulanır: ona karşı
kosinüs anlamsızdır ve bozulmuş bir kademe sessizce yanlış epizotlar döndürür.

> **Görev 07 bağlama uyarısı — gömme geri çağrısı `on_close`'a takılıyor.**
> [Görev 07](07-sentezleyici.md) kapanan epizodu `on_close(episode)` ile
> veriyor ve `run.py` bu görevin `embed_episode`'unu oraya bağlıyor. Üç kural:
>
> 1. **`gw.embed()` `[]` döndürdüğünde hiçbir nokta yazma.** Bozulmuş gömme
>    kademesi boş vektör döndürüyor (yukarıdaki guard); nokta yine de
>    yazılırsa arama onu gerçek bir emsalmiş gibi geri verir ve boş vektöre
>    karşı kosinüs anlamsızdır. Epizot, kademe düzeldiğinde yeniden gömülebilir.
> 2. **Geri çağrı istisna atmamalı.** `on_close` `synthesize`'ın içinden
>    çağrılıyor; oradan kaçan bir istisna, zaten başarıyla yazılmış epizodu ve
>    devir teslimi birlikte götürür. **Çözüm bağlayan tarafta değil, burada:**
>    `embed_episode` her arızayı kendi içinde yutup `False` döndürüyor —
>    erişilemez Qdrant de dâhil.
> 3. **Noktalar `episode.id` üzerine anahtarlanıyor.** `on_close` depoya
>    yazılmış epizodu aldığı için `id` her zaman dolu; bu yolda kaydedilmemiş
>    epizot dalı tetiklenmiyor.

## Ne yapacaksın

```python
memory_backend() -> str          # "qdrant" | "local"
build_client() -> QdrantClient
embed_episode(gw, client, episode: Episode) -> bool
search_timeline(gw, client, query: str, top_k: int = 5,
                exclude_id: int | None = None) -> list[Episode]
```

Akış: sorguyu göm → Qdrant'ta kosinüs → en iyi `top_k`. Aday kümesi, yeniden
sıralama kademesi ve Python tarafında kosinüs **yok**.

**İkinci argüman hâlâ `Store` olabilir.** Görev 09/11/14 oraya depo tutamağı
geçiriyor ve o dosyalar bu göçün kapsamı dışında — imza onları kırmadan
taşımak zorunda. Qdrant istemcisi geçilirse o kullanılır, başka bir şey
geçilirse yapılandırmadan kurulan istemciye düşülür.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_memory.py`

```python
"""Epizodik hafıza araması — Qdrant'a yazma ve kosinüs araması.

Testlerin yarısı mutlu yolu değil, **iki bozulma senaryosunu** koruyor:
`Gateway.embed()` kesintide `[]` döndürüyor (Görev 03) ve Qdrant'ın kendisi
erişilemez olabilir. İkisi de bir koşuyu düşürmemeli.

Her test yerel `QdrantClient(":memory:")` ile çalışıyor — ağa çıkan tek bir
test yok.
"""

from unittest.mock import Mock

from qdrant_client import QdrantClient
from qdrant_client.models import Distance

from gozcu.config import QDRANT_COLLECTION, QDRANT_VECTOR_SIZE
from gozcu import memory
from gozcu.memory import embed_episode, search_timeline
from gozcu.models import Episode
from gozcu.store import Store


def _client() -> QdrantClient:
    """Süreç içi Qdrant — gerçek istemcinin aynı API'si, ağ yok."""
    return QdrantClient(":memory:")


def _vec(*head: float) -> list[float]:
    """Koleksiyonun boyutuna doldurulmuş vektör.

    Boyut `config.QDRANT_VECTOR_SIZE`'dan geliyor: koleksiyonu biz kuruyoruz ve
    yanlış boyutlu bir vektör Qdrant tarafından reddedilir.
    """
    vector = [0.0] * QDRANT_VECTOR_SIZE
    for index, value in enumerate(head):
        vector[index] = value
    return vector


def _ep(summary, risk="Orta", episode_id=None, participants=()):
    return Episode(id=episode_id, start_ts=0.0, phase="outcome",
                   summary_tr=summary, preliminary_risk=risk,
                   participants=list(participants))


def _save(client, gw, *summaries):
    """Epizotları gömer; gömülmüş epizotları geri verir."""
    saved = []
    for index, summary in enumerate(summaries, 1):
        episode = _ep(summary, episode_id=index)
        embed_episode(gw, client, episode)
        saved.append(episode)
    return saved


def _points(client):
    if not client.collection_exists(QDRANT_COLLECTION):
        return []
    return client.scroll(QDRANT_COLLECTION, limit=100, with_payload=True)[0]


# --- sıralama ---------------------------------------------------------------

def test_search_ranks_the_semantically_closest_episode_first():
    client, gw = _client(), Mock()
    # sırayla: iki epizotun gömülmesi, sonra sorgunun gömülmesi
    gw.embed.side_effect = [_vec(1.0, 0.0), _vec(0.0, 1.0), _vec(0.99, 0.14)]
    _save(client, gw, "istif aracı devrildi", "personel mola verdi")

    result = search_timeline(gw, client, "araç devrilmesi")
    assert result[0].summary_tr == "istif aracı devrildi"


def test_search_returns_empty_when_nothing_is_stored():
    """Boş arşiv hiçbir şey döndürmeli — operatörün bağlam değiştirdiği anın
    ortasında istisna değil. Koleksiyon henüz yokken sorgu da gömülmüyor."""
    gw = Mock()
    assert search_timeline(gw, _client(), "herhangi bir şey") == []
    gw.embed.assert_not_called()


def test_search_returns_empty_when_the_collection_holds_no_episode():
    """Koleksiyon var ama içi boş — yine sonuç yok, yine istisna yok."""
    client, gw = _client(), Mock()
    gw.embed.side_effect = [_vec(1.0, 0.0), []]
    embed_episode(gw, client, _ep("silinecek", episode_id=1))
    client.delete(QDRANT_COLLECTION, points_selector=[1])

    assert search_timeline(gw, client, "x") == []


def test_search_honours_top_k():
    client, gw = _client(), Mock()
    gw.embed.side_effect = [_vec(1.0, 0.0), _vec(0.9, 0.1), _vec(0.8, 0.2),
                            _vec(1.0, 0.0)]
    _save(client, gw, "birinci", "ikinci", "üçüncü")

    assert len(search_timeline(gw, client, "x", top_k=2)) == 2


def test_rerank_is_never_called():
    """Organizasyon `rerank`'i ÖLÇTÜ ve zararlı buldu: R@1 0,95'ten 0,55'e
    düşüyor. `Gateway.rerank` duruyor ama hafıza araması onu çağırmıyor."""
    client, gw = _client(), Mock()
    gw.embed.side_effect = [_vec(1.0, 0.0), _vec(1.0, 0.0)]
    _save(client, gw, "tek olay")

    search_timeline(gw, client, "x")
    gw.rerank.assert_not_called()


# --- yazma tarafı: `on_close` sözleşmesi ------------------------------------

def test_embed_episode_reports_true_when_a_vector_is_stored():
    client, gw = _client(), Mock()
    gw.embed.return_value = _vec(1.0, 0.0)
    episode = _ep("kaydedildi", episode_id=7, participants=["IST-04"])

    assert embed_episode(gw, client, episode) is True
    stored = _points(client)
    assert [p.id for p in stored] == [7]
    # Ruling 7: sonuç ikinci bir SQLite okuması olmadan kullanılabilir olmalı.
    assert stored[0].payload["summary_tr"] == "kaydedildi"
    assert stored[0].payload["preliminary_risk"] == "Orta"
    assert stored[0].payload["start_ts"] == 0.0
    assert stored[0].payload["participants"] == ["IST-04"]
    assert stored[0].payload["id"] == 7


def test_the_collection_is_created_on_the_first_write():
    """Koleksiyonu organizasyon değil BİZ kuruyoruz — kendi boyutumuzla."""
    client, gw = _client(), Mock()
    gw.embed.return_value = _vec(1.0)
    assert client.collection_exists(QDRANT_COLLECTION) is False

    embed_episode(gw, client, _ep("ilk yazma", episode_id=1))

    params = client.get_collection(QDRANT_COLLECTION).config.params.vectors
    assert params.size == QDRANT_VECTOR_SIZE
    assert params.distance == Distance.COSINE


def test_embedding_the_same_episode_twice_replaces_the_point():
    """Nokta kimliği epizot kimliği: Görev 09'un yükleyicisi ikinci kez
    çağrıldığında arşivi çoğaltmamalı."""
    client, gw = _client(), Mock()
    gw.embed.side_effect = [_vec(1.0, 0.0), _vec(0.0, 1.0)]
    episode = _ep("aynı epizot", episode_id=3)

    assert embed_episode(gw, client, episode) is True
    assert embed_episode(gw, client, episode) is True
    assert [p.id for p in _points(client)] == [3]


def test_degraded_embed_tier_writes_nothing():
    """Bozulmuş kademe `[]` döndürüyor. Nokta yazılırsa arama onu gerçek bir
    emsalmiş gibi geri verir; boş vektöre karşı kosinüs anlamsızdır."""
    client, gw = _client(), Mock()
    gw.embed.return_value = []
    episode = _ep("bozuk kademe", episode_id=1)

    assert embed_episode(gw, client, episode) is False
    assert _points(client) == []


def test_embed_episode_rejects_a_vector_of_the_wrong_dimension():
    """Koleksiyonun boyutu sabit; farklı boyutlu bir vektör (ör. başka bir
    gömme modeline geçilmiş) yazılırsa arama tarafı patlardı."""
    client, gw = _client(), Mock()
    gw.embed.return_value = [1.0, 0.0]
    assert embed_episode(gw, client, _ep("yanlış boyut", episode_id=1)) is False
    assert _points(client) == []


def test_embed_episode_returns_false_for_an_unsaved_episode():
    """İstisna değil `False`: geri çağrı `synthesize`'ın içinden çağrılıyor,
    oradan kaçan `ValueError` epizodu ve devir teslimi birlikte götürür."""
    client = _client()
    assert embed_episode(Mock(), client, _ep("kaydedilmemiş")) is False
    assert _points(client) == []


def test_embed_episode_never_raises_when_the_gateway_fails():
    """`on_close`'tan kaçan bir istisna, zaten yazılmış epizodu ve devir
    teslimi birlikte götürür."""
    client, gw = _client(), Mock()
    gw.embed.side_effect = RuntimeError("gateway çöktü")

    assert embed_episode(gw, client, _ep("patlayan gateway", episode_id=1)) is False
    assert _points(client) == []


# --- Qdrant erişilemezse ----------------------------------------------------

def test_embed_episode_returns_false_when_qdrant_is_unreachable():
    """Vektör veritabanının kesintisi bir koşuyu düşürmemeli — gateway ile
    aynı felsefe."""
    gw = Mock()
    gw.embed.return_value = _vec(1.0, 0.0)
    broken = Mock()
    broken.collection_exists.side_effect = ConnectionError("Connection refused")
    broken.upsert.side_effect = ConnectionError("Connection refused")

    assert embed_episode(gw, broken, _ep("erişilemez", episode_id=1)) is False


def test_search_timeline_returns_empty_when_qdrant_is_unreachable():
    gw = Mock()
    gw.embed.return_value = _vec(1.0, 0.0)
    broken = Mock()
    broken.collection_exists.side_effect = ConnectionError("Connection refused")
    broken.query_points.side_effect = ConnectionError("Connection refused")

    assert search_timeline(gw, broken, "x") == []


# --- okuma tarafı: bozuk kademeye karşı savunma -----------------------------

def test_empty_query_vector_returns_no_results():
    """Arama anında kademe bozuksa sorgu vektörü boş gelir; boş vektörle
    Qdrant'a hiç gidilmiyor."""
    client, gw = _client(), Mock()
    gw.embed.side_effect = [_vec(1.0, 0.0), []]
    _save(client, gw, "arşivdeki olay")

    assert search_timeline(gw, client, "x") == []


# --- kendi kendine eşleşme --------------------------------------------------

def test_search_excludes_the_originating_episode():
    """Görev 11 sorguyu `episode.summary_tr` ile atıyor — tam olarak gömülen
    metin. Süzülmezse risk analistinin arşiv paneli epizodu kendi emsali
    olarak gösterir."""
    client, gw = _client(), Mock()
    gw.embed.side_effect = [_vec(1.0, 0.0), _vec(0.0, 1.0), _vec(1.0, 0.0)]
    current, other = _save(client, gw, "istif aracı devrildi",
                           "personel mola verdi")

    result = search_timeline(gw, client, current.summary_tr,
                             exclude_id=current.id)
    assert [e.id for e in result] == [other.id]


def test_search_keeps_every_episode_when_no_exclusion_is_given():
    client, gw = _client(), Mock()
    gw.embed.side_effect = [_vec(1.0, 0.0), _vec(0.0, 1.0), _vec(1.0, 0.0)]
    current, other = _save(client, gw, "istif aracı devrildi",
                           "personel mola verdi")

    result = search_timeline(gw, client, current.summary_tr)
    assert {e.id for e in result} == {current.id, other.id}


def test_search_returns_episodes_rebuilt_from_the_payload():
    """Sonuç `Episode` olarak dönüyor — çağıranlar (Görev 11/14) değişmedi."""
    client, gw = _client(), Mock()
    gw.embed.side_effect = [_vec(1.0, 0.0), _vec(1.0, 0.0)]
    embed_episode(gw, client, Episode(id=5, start_ts=12.5, end_ts=30.0,
                                      phase="onset", summary_tr="devrilme",
                                      participants=["IST-04"],
                                      preliminary_risk="Yüksek",
                                      state="closed"))

    found = search_timeline(gw, client, "x")[0]
    assert isinstance(found, Episode)
    assert (found.id, found.start_ts, found.end_ts) == (5, 12.5, 30.0)
    assert (found.phase, found.state) == ("onset", "closed")
    assert found.preliminary_risk == "Yüksek"


# --- eski çağıranlar --------------------------------------------------------

def test_a_store_handle_is_accepted_by_the_legacy_callers():
    """Görev 09/11/14 ikinci argüman olarak `Store` geçiriyor ve o dosyalar bu
    görevin kapsamı dışında. `Store` geçildiğinde modül süreç varsayılanı olan
    istemciye düşüyor ve **gömme defteri** yine SQLite'a yazılıyor — yükleyici
    hangi epizodun gömüldüğünü oradan okuyor."""
    store, gw = Store(":memory:"), Mock()
    gw.embed.return_value = _vec(1.0, 0.0)
    episode = _ep("eski çağıran")
    episode.id = store.create_episode(episode)

    assert embed_episode(gw, store, episode) is True
    assert store.embeddings() == [(episode.id, _vec(1.0, 0.0))]
    assert isinstance(search_timeline(gw, store, "x"), list)


def test_memory_backend_reports_local_when_no_key_is_configured(monkeypatch):
    """Anahtarsız düşüş sessiz olmamalı: konsol/KPI bunu gösterebilmeli."""
    monkeypatch.setattr(memory, "QDRANT_API_KEY", "")
    assert memory.memory_backend() == "local"


def test_memory_backend_reports_qdrant_when_a_key_is_configured(monkeypatch):
    monkeypatch.setattr(memory, "QDRANT_API_KEY", "qdr-team37-test")
    assert memory.memory_backend() == "qdrant"
```

İkinci test demoyu koruyor: boş arşiv **hiçbir şey** döndürmeli, operatörün
bağlam değiştirdiği anın ortasında exception fırlatmamalı.

Testlerin tamamı süreç içi `QdrantClient(":memory:")` üzerinde koşuyor —
gerçek istemcinin aynı API'si, `HasIdCondition` ile `must_not` filtresi dâhil,
ağa çıkan tek bir test yok.

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_memory.py -v
```
Beklenen: `ModuleNotFoundError: No module named 'gozcu.memory'`

### 3. `gozcu/memory.py` yaz

```python
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
```

`qdrant-client`'ı `pyproject.toml`'a **çalışma zamanı** bağımlılığı olarak ekle
(Görev 18 paketlemede bunu arayacak).

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_memory.py -v
```
Beklenen: 21 passed

### 5. Commit

```bash
git add gozcu/memory.py pyproject.toml tests/test_memory.py
git commit -m "feat: episodic memory on Qdrant instead of SQLite cosine"
```

## Doğrulama

```bash
uv run pytest tests/test_memory.py -v
```
Beklenen: **21 passed**

## Tamamlanma notları (gelecek görevleri bağlayan)

- **`embed_episode(gw, client, episode) -> bool` ASLA istisna atmaz — tasarım
  gereği.** `on_close` üzerinden `synthesize`'ın içinden koşuyor ([Görev
  07](07-sentezleyici.md)); oradan kaçan bir istisna, zaten başarıyla yazılmış
  epizodu ve devir teslim kaydını birlikte götürür. Arıza bu yüzden dönüş
  değerinde görünür: `False` "bu epizodun vektörü yok" demek (kaydedilmemiş
  epizot, bozulmuş gömme kademesi, erişilemez Qdrant ya da gateway hatası) ve
  çağıran taraf kademe düzeldiğinde yeniden gömebilir. Bağlayan tarafın
  `try/except`'ine gerek yok ([Görev 17](17-cikti-sozlesmesi.md)).
- **Bozulmuş gömme kademesi HİÇBİR nokta yazmıyor.** `[]` yazılsaydı arama onu
  gerçek bir emsalmiş gibi geri verirdi ve boş vektöre karşı kosinüs
  anlamsızdır. Yanlış boyutlu vektör de yazılmıyor: koleksiyonun boyutu sabit
  ve uyuşmayan bir vektör okuma tarafını bozar.
- **`search_timeline(gw, client, query, top_k=5, exclude_id=None)` — sorgu
  metni bir epizottan geliyorsa `exclude_id` GEÇİLECEK.** Süzmeyi artık Python
  değil **Qdrant** yapıyor (`Filter(must_not=[HasIdCondition(...)])`): sonradan
  süzülseydi dışlanan epizot `top_k`'dan bir yer çalardı. [Görev
  11](11-risk-analisti.md) sorguyu tam olarak gömülen metinle,
  `episode.summary_tr` ile atıyor — süzülmezse epizot kendi emsali olarak
  listenin başında görünür.
- **Erişilemez Qdrant bir koşuyu DÜŞÜRMEZ.** Gateway ile aynı felsefe:
  `search_timeline` `[]`, `embed_episode` `False` döner, ikisi de istisna
  atmaz. Boş liste ayrıca şu üç durumda da dönüyor: koleksiyon yok (hiç epizot
  gömülmemiş), arşiv boş, sorgu vektörü boş (arama anında kademe bozuk).
- **`port=443` ZORUNLU.** Verilmezse `qdrant-client` `https://` şemasını yok
  sayıp kendi varsayılan portuna düşüyor; hata `Connection refused` oluyor ve
  kök nedeni hiç göstermiyor. Saatler buna gider.
- **Yalnız REST, gRPC YOK.** Takımlara port değil yol ön eki veriliyor ve gRPC
  bir ön ek üzerinden yönlendirilemiyor — `prefer_grpc=True` hiçbir yerde
  geçilmemeli.
- **Qdrant anahtarı LLM bearer token'ından AYRI** (`qdr-team37-…`, ortam
  değişkeni `GOZCU_QDRANT_API_KEY`). Koleksiyon boyutu **1024**
  (`bge-m3-embed`), mesafe `Distance.COSINE`; koleksiyonu ilk yazmada biz
  kuruyoruz.
- **`rerank` ARTIK ÇAĞRILMIYOR.** Organizasyonun kendi ölçümü o kademeyi
  zararlı buluyor: ilk isabet oranı 0,95'ten 0,55'e düşüyor. `Gateway.rerank`
  yerinde duruyor ve test ediliyor, sadece hafıza araması ona uğramıyor —
  Qdrant'ın sırası nihai sıra.
- **`memory_backend()` `"qdrant"` ya da `"local"` döndürür.** Anahtar tanımlı
  değilken istemci süreç içi bir Qdrant'a düşüyor ve sistem **tamamen sağlıklı
  görünüyor** — ama epizodik hafıza süreçle birlikte yok oluyor, izole örneğe
  hiçbir şey yazılmıyor. Düşüşün kendisi kabul edilebilir (test, çevrimdışı
  demo), **görünmezliği değil**: [Görev 16](16-konsol.md) ve KPI bunu
  göstersin diye tek kelimeyle dışarı veriliyor, `kpi.run_status`'ın bozulmuş
  koşuyu göstermesiyle aynı gerekçe.
- **Testler tamamen çevrimdışı.** Her test `QdrantClient(":memory:")` kullanıyor;
  ağa çıkan tek bir test yok.
- **Görev 17/18 borcu — `Store.save_embedding`/`embeddings` ÖLÜ DEĞİL.**
  [Görev 09](09-tesis-dunyasi.md)'un fikstür yükleyicisi
  (`gozcu/fixtures/loader.py`) hangi epizodun gömüldüğünü hâlâ
  `store.embeddings()` üzerinden okuyor — "zaten gömüldü" idempotenlik kümesi
  o. Bu yüzden `embed_episode` başarılı bir Qdrant upsert'inden **sonra** o
  satırı bir **defter** olarak yazmaya devam ediyor; satır artık arama indeksi
  değil, `search_timeline` ona hiç bakmıyor. Yükleyicinin kontrolü Qdrant'a
  taşındığında defter yazımı, iki `Store` metodu ve `episode_embedding`
  tablosu **birlikte** ölür ([Görev 17](17-cikti-sozlesmesi.md),
  [Görev 18](18-paketleme.md)).
