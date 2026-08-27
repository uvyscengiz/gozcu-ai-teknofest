"""Epizodik hafıza araması — Qdrant'a yazma ve kosinüs araması.

Testlerin yarısı mutlu yolu değil, **iki bozulma senaryosunu** koruyor:
`Gateway.embed()` kesintide `[]` döndürüyor (Görev 03) ve Qdrant'ın kendisi
erişilemez olabilir. İkisi de bir koşuyu düşürmemeli.

Her test yerel `QdrantClient(":memory:")` ile çalışıyor — ağa çıkan tek bir
test yok.
"""

from unittest.mock import Mock

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from gozcu.config import QDRANT_COLLECTION, QDRANT_VECTOR_SIZE
from gozcu import memory
from gozcu.memory import embed_episode, point_id, search_timeline
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
    assert [p.id for p in stored] == [point_id(None, 7)]
    assert stored[0].payload["id"] == 7, "epizot kimliği payload'da okunabilir kalmalı"
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
    assert len(_points(client)) == 1, "aynı çift tek nokta bırakmalı"


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


def test_a_fallback_episode_is_not_embedded():
    """Yedek özetli bir epizot arşive GÖMÜLMEZ: arıza metni gelecekteki bir
    koşunun emsal aramasını zehirler (`search_timeline` onu gerçek bir olay
    gibi geri verirdi). Kademe düzelip özet iyileştiğinde `False` dönüşü
    çağıran tarafın yeniden gömmesine izin veriyor.
    """
    client, gw = Mock(), Mock()
    gw.embed.return_value = _vec(1.0)
    episode = Episode(id=11, start_ts=0.0, phase="outcome",
                      summary_tr="Sentez üretilemedi; ham gözlemler kayıtlı.",
                      preliminary_risk="Orta", summary_source="fallback")

    assert embed_episode(gw, client, episode) is False
    client.upsert.assert_not_called()


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

@pytest.mark.xfail(reason="exclude imzası Görev 9'da çifte dönüyor", strict=True)
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


def test_search_timeline_drops_fallback_sourced_episodes_from_earlier_runs():
    """Yazma tarafı (`embed_episode`) yedek özetli epizotları artık gömmüyor
    (bkz. `test_a_fallback_episode_is_not_embedded`) — ama team37 koleksiyonu
    KALICI ve nokta kimliği epizot kimliği: bu kısıtlamadan ÖNCE gömülmüş
    zehirli noktalar hâlâ arşivde durabilir, aynı kimlik yeniden üretilmedikçe
    üstüne yazılacakları garanti değil. Böyle bir noktayı burada DOĞRUDAN
    yazıyoruz — tam olarak bu dal öncesi koşuların yaptığı gibi — ve okuma
    tarafının onu tek başına süzdüğünü doğruluyoruz.
    """
    client, gw = _client(), Mock()
    gw.embed.side_effect = [_vec(1.0, 0.0), _vec(1.0, 0.0)]
    real = _ep("istif aracı devrildi", episode_id=2)
    embed_episode(gw, client, real)

    poisoned = Episode(id=1, start_ts=0.0, phase="outcome",
                       summary_tr="Sentez üretilemedi; ham gözlemler kayıtlı.",
                       preliminary_risk="Orta", summary_source="fallback")
    client.upsert(QDRANT_COLLECTION, points=[
        PointStruct(id=1, vector=_vec(1.0, 0.0),
                   payload=poisoned.model_dump())])

    result = search_timeline(gw, client, "x")
    assert [e.id for e in result] == [2]


def test_memory_backend_reports_local_when_no_key_is_configured(monkeypatch):
    """Anahtarsız düşüş sessiz olmamalı: konsol/KPI bunu gösterebilmeli."""
    monkeypatch.setattr(memory, "QDRANT_API_KEY", "")
    assert memory.memory_backend() == "local"


def test_memory_backend_reports_qdrant_when_a_key_is_configured(monkeypatch):
    monkeypatch.setattr(memory, "QDRANT_API_KEY", "qdr-team37-test")
    assert memory.memory_backend() == "qdrant"


# --- kararlı kimlik ---------------------------------------------------------

def test_point_id_is_stable_for_the_same_source_and_episode():
    """Aynı çift → aynı nokta; ikinci gömme çoğaltmaz, üstüne yazar."""
    from gozcu.memory import point_id
    assert point_id("9f2a", 3) == point_id("9f2a", 3)


def test_point_id_separates_episodes_that_share_a_rowid():
    """B3'ün onarımı: iki farklı video da 1 numaralı epizot üretir.

    Eski kimlik (`episode.id`) ikisini TEK noktada birleştiriyordu — ölçüldü:
    iki videodan iki epizot → 1 nokta, birincisi yok oldu.
    """
    from gozcu.memory import point_id
    assert point_id("videoA", 1) != point_id("videoB", 1)


def test_video_key_reads_content_not_the_file_name(tmp_path):
    """Gradio yüklemesi iki farklı videoyu aynı isimle getirebiliyor;
    çakışma iki alakasız olayı tek noktada birleştirir — çoğaltmadan kötü."""
    from gozcu.memory import video_key
    bir, iki = tmp_path / "video.mp4", tmp_path / "başka.mp4"
    farkli = tmp_path / "farkli.mp4"
    bir.write_bytes(b"ayni icerik")
    iki.write_bytes(b"ayni icerik")
    farkli.write_bytes(b"other_ep icerik")

    assert video_key(bir) == video_key(iki), "anahtar dosya adına bakmamalı"
    assert video_key(bir) != video_key(farkli)


def test_video_key_never_raises_on_an_unreadable_path():
    """`tests/test_run.py` var olmayan bir `"video.mp4"` yolunu 29 kez
    geçiyor; atan bir `video_key` o testlerin hepsini çökertirdi."""
    from gozcu.memory import video_key
    anahtar = video_key("olmayan-bir-dosya.mp4")
    assert isinstance(anahtar, str) and anahtar


def test_a_late_episode_from_catch_up_does_not_overwrite_an_earlier_point():
    """`DecisionLoop.catch_up` ertelenmiş pencereleri sonradan işliyor ve DAHA
    ERKEN `start_ts`'li epizotlar doğurabiliyor. Kimliğin ikinci parçası bu
    yüzden `episode.id`, `start_ts` DEĞİL — zamana dayalı bir kimlik tam o
    anda iki epizodu birbirine kaydırırdı."""
    from gozcu.memory import point_id
    client, gw = _client(), Mock()
    gw.embed.return_value = _vec(1.0)
    early = _ep("önce işlenen pencere", episode_id=1)
    early.source, early.start_ts = "9f2a", 30.0
    late_ep = _ep("telafi edilen pencere", episode_id=2)
    late_ep.source, late_ep.start_ts = "9f2a", 10.0      # DAHA ERKEN damga, SONRA doğdu

    embed_episode(gw, client, early)
    embed_episode(gw, client, late_ep)

    assert len(_points(client)) == 2, "telafi epizodu öncekini ezmemeli"
    assert {p.id for p in _points(client)} == {point_id("9f2a", 1),
                                              point_id("9f2a", 2)}


def test_the_written_point_carries_the_uuid_identity():
    """Yazma ve okuma tarafı AYNI fonksiyondan gelmek zorunda."""
    from gozcu.memory import point_id
    client, gw = _client(), Mock()
    gw.embed.return_value = _vec(1.0)
    episode = _ep("devrilme", episode_id=7)
    episode.source = "9f2a"

    assert embed_episode(gw, client, episode) is True
    stored = _points(client)
    assert [p.id for p in stored] == [point_id("9f2a", 7)]
    assert stored[0].payload["id"] == 7
    assert stored[0].payload["source"] == "9f2a"


def test_a_point_written_before_the_new_fields_still_loads():
    """`Base` `extra="forbid"` ama `_episode()` bilinmeyen anahtarları süzüyor
    ve eksikler varsayılana düşüyor — çift yönlü uyumlu."""
    client, gw = _client(), Mock()
    gw.embed.side_effect = [_vec(1.0), _vec(1.0)]
    client.create_collection(
        QDRANT_COLLECTION,
        vectors_config=VectorParams(size=QDRANT_VECTOR_SIZE,
                                    distance=Distance.COSINE))
    client.upsert(QDRANT_COLLECTION, points=[PointStruct(
        id=1, vector=_vec(1.0),
        payload={"id": 1, "start_ts": 0.0, "end_ts": 4.0, "phase": "outcome",
                 "summary_tr": "eski şema kaydı", "participants": ["IST-04"],
                 "preliminary_risk": "Orta", "state": "closed"})])

    found = search_timeline(gw, client, "eski")
    assert [e.summary_tr for e in found] == ["eski şema kaydı"]
    assert found[0].source is None, "eksik alan varsayılana düşmeli"
