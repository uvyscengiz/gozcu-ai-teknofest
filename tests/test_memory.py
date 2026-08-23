"""Epizodik hafıza araması — gömme yazımı ve kosinüs + rerank sıralaması.

Testlerin yarısı mutlu yolu değil, **bozulmuş gömme kademesini** koruyor:
`Gateway.embed()` kesintide `[]` döndürüyor (Görev 03) ve o boş vektör hem
yazma hem okuma tarafında sessizce yanlış sonuç üretebiliyor.
"""

from unittest.mock import Mock

import numpy as np

from gozcu.memory import _cosine, embed_episode, search_timeline
from gozcu.models import Episode
from gozcu.store import Store


def _ep(summary, risk="Orta"):
    return Episode(start_ts=0.0, phase="outcome", summary_tr=summary,
                   preliminary_risk=risk)


def _save(store, gw, *summaries):
    """Epizotları kaydedip gömer; kaydedilmiş epizotları geri verir."""
    saved = []
    for summary in summaries:
        episode = _ep(summary)
        episode.id = store.create_episode(episode)
        embed_episode(gw, store, episode)
        saved.append(episode)
    return saved


def _identity_rerank(query, candidates):
    return list(range(len(candidates)))


# --- sıralama ---------------------------------------------------------------

def test_search_ranks_the_semantically_closest_episode_first():
    store = Store(":memory:")
    gw = Mock()
    # sırayla: iki epizotun gömülmesi, sonra sorgunun gömülmesi
    gw.embed.side_effect = [[1.0, 0.0], [0.0, 1.0], [0.99, 0.14]]
    gw.rerank.side_effect = _identity_rerank
    _save(store, gw, "istif aracı devrildi", "personel mola verdi")

    result = search_timeline(gw, store, "araç devrilmesi")
    assert result[0].summary_tr == "istif aracı devrildi"


def test_search_returns_empty_when_nothing_is_stored():
    """Boş arşiv hiçbir şey döndürmeli — operatörün bağlam değiştirdiği anın
    ortasında istisna değil."""
    gw = Mock()
    assert search_timeline(gw, Store(":memory:"), "herhangi bir şey") == []
    gw.embed.assert_not_called()


def test_rerank_order_is_honoured():
    store = Store(":memory:")
    gw = Mock()
    gw.embed.side_effect = [[1.0, 0.0], [0.9, 0.1], [1.0, 0.0]]
    gw.rerank.side_effect = lambda query, cands: list(reversed(range(len(cands))))
    _save(store, gw, "birinci", "ikinci")
    assert search_timeline(gw, store, "x")[0].summary_tr == "ikinci"


# --- sıfır norm guard'ı -----------------------------------------------------

def test_cosine_scores_never_contain_nan():
    """`norms[norms == 0] = 1e-9` olmadan 0/0 `nan` üretir; `nan` istisna
    atmaz, sadece sıralamayı sessizce bozar. Guard'ın taşıyıcı olduğu yer."""
    scores = _cosine(np.asarray([[0.0, 0.0], [1.0, 0.0]], dtype=float),
                     np.asarray([1.0, 0.0], dtype=float))
    assert not np.isnan(scores).any()


def test_a_zero_vector_outranks_an_opposing_vector():
    """Sıfır vektörün kosinüsü 0.0'dır, yani ters yönlü bir epizodun (-1.0)
    ÜSTÜNDE sıralanır. Guard silinirse skor `nan` olur, `argsort` `nan`'ı sona
    atar ve sıra tersine döner."""
    store = Store(":memory:")
    gw = Mock()
    gw.embed.side_effect = [[0.0, 0.0], [-1.0, 0.0], [1.0, 0.0]]
    gw.rerank.side_effect = _identity_rerank
    _save(store, gw, "sıfır vektör", "ters yön")

    result = search_timeline(gw, store, "x")
    assert [e.summary_tr for e in result] == ["sıfır vektör", "ters yön"]


# --- yazma tarafı: `on_close` sözleşmesi ------------------------------------

def test_embed_episode_reports_true_when_a_vector_is_stored():
    store = Store(":memory:")
    gw = Mock()
    gw.embed.return_value = [1.0, 0.0]
    episode = _ep("kaydedildi")
    episode.id = store.create_episode(episode)

    assert embed_episode(gw, store, episode) is True
    assert store.embeddings() == [(episode.id, [1.0, 0.0])]


def test_degraded_embed_tier_writes_no_row():
    """Bozulmuş kademe `[]` döndürüyor. Satır yazılırsa `embeddings()` onu
    gerçek bir kayıt gibi geri verir ve boş vektöre karşı kosinüs anlamsızdır."""
    store = Store(":memory:")
    gw = Mock()
    gw.embed.return_value = []
    episode = _ep("bozuk kademe")
    episode.id = store.create_episode(episode)

    assert embed_episode(gw, store, episode) is False
    assert store.embeddings() == []


def test_embed_episode_returns_false_for_an_unsaved_episode():
    """İstisna değil `False`: geri çağrı `synthesize`'ın içinden çağrılıyor,
    oradan kaçan `ValueError` epizodu ve devir teslimi birlikte götürür."""
    store = Store(":memory:")
    assert embed_episode(Mock(), store, _ep("kaydedilmemiş")) is False
    assert store.embeddings() == []


def test_embed_episode_never_raises_when_the_gateway_fails():
    """`on_close`'tan kaçan bir istisna, zaten yazılmış epizodu ve devir
    teslimi birlikte götürür."""
    store = Store(":memory:")
    gw = Mock()
    gw.embed.side_effect = RuntimeError("gateway çöktü")
    episode = _ep("patlayan gateway")
    episode.id = store.create_episode(episode)

    assert embed_episode(gw, store, episode) is False
    assert store.embeddings() == []


# --- okuma tarafı: bozuk satırlara karşı savunma ----------------------------

def test_empty_query_vector_returns_no_results():
    """Arama anında kademe bozuksa sorgu vektörü boş gelir; boş vektöre karşı
    kosinüs hesaplanmaz, rerank'a hiç gidilmez.

    Tabloda boş bir satır varken guard taşıyıcı hâle geliyor: boş sorgu ile
    boş satırın boyutu EŞLEŞİR, kosinüs 0.0 çıkar ve bozuk kademe zehirli
    satırı gerçek bir emsalmiş gibi döndürür."""
    store = Store(":memory:")
    gw = Mock()
    gw.embed.side_effect = [[1.0, 0.0], []]
    gw.rerank.side_effect = _identity_rerank
    _save(store, gw, "arşivdeki olay")
    poisoned = _ep("zehirli satır")
    poisoned.id = store.create_episode(poisoned)
    store.save_embedding(poisoned.id, [])

    assert search_timeline(gw, store, "x") == []
    gw.rerank.assert_not_called()


def test_rows_with_a_different_dimension_are_skipped():
    """Farklı boyutlu satırlar numpy'da `ValueError` demek — düşürülmeliler."""
    store = Store(":memory:")
    gw = Mock()
    gw.embed.side_effect = [[1.0, 0.0], [1.0, 0.0, 0.0], [1.0, 0.0]]
    gw.rerank.side_effect = _identity_rerank
    _save(store, gw, "iki boyutlu", "üç boyutlu")

    result = search_timeline(gw, store, "x")
    assert [e.summary_tr for e in result] == ["iki boyutlu"]


def test_search_survives_a_table_with_empty_rows():
    """Görev 09 fikstürleri `embed_episode` üzerinden tohumluyor; kademe
    bozukken tek bir tohumlama koşusu tabloyu zehirlerse her arama ölürdü."""
    store = Store(":memory:")
    gw = Mock()
    gw.embed.side_effect = [[1.0, 0.0], [1.0, 0.0]]
    good = _save(store, gw, "sağlam satır")[0]
    poisoned = _ep("zehirli satır")
    poisoned.id = store.create_episode(poisoned)
    store.save_embedding(poisoned.id, [])   # eski bir tohumlama koşusundan kalan
    gw.rerank.side_effect = _identity_rerank

    result = search_timeline(gw, store, "x")
    assert [e.id for e in result] == [good.id]


# --- kendi kendine eşleşme --------------------------------------------------

def test_search_excludes_the_originating_episode():
    """Görev 11 sorguyu `episode.summary_tr` ile atıyor — tam olarak gömülen
    metin. Süzülmezse risk analistinin arşiv paneli epizodu kendi emsali
    olarak gösterir."""
    store = Store(":memory:")
    gw = Mock()
    gw.embed.side_effect = [[1.0, 0.0], [0.0, 1.0], [1.0, 0.0]]
    gw.rerank.side_effect = _identity_rerank
    current, other = _save(store, gw, "istif aracı devrildi", "personel mola verdi")

    result = search_timeline(gw, store, current.summary_tr, exclude_id=current.id)
    assert [e.id for e in result] == [other.id]


def test_search_keeps_every_episode_when_no_exclusion_is_given():
    store = Store(":memory:")
    gw = Mock()
    gw.embed.side_effect = [[1.0, 0.0], [0.0, 1.0], [1.0, 0.0]]
    gw.rerank.side_effect = _identity_rerank
    current, other = _save(store, gw, "istif aracı devrildi", "personel mola verdi")

    result = search_timeline(gw, store, current.summary_tr)
    assert {e.id for e in result} == {current.id, other.id}
