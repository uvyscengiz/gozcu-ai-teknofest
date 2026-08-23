"""Epizodik hafıza — sistemin uzun ufuklu belleği.

Operatör *"daha önce bu araçla ilgili bir olay olmuş muydu?"* diye sorduğunda
cevabın geldiği yer. Gömdüğümüz şey video segmentleri değil, **olay kayıtları**:
her epizot zaten görsel yorumu, tespitleri ve sinyalleri damıtılmış hâlde
taşıyor.

Vektör veritabanı yok — bir vardiya birkaç yüz epizot demek ve numpy ile kaba
kuvvet kosinüs anlık. Akış: sorguyu göm → kosinüs → en iyi `CANDIDATE_K` →
reranker → en iyi `top_k`.

**Bozulmuş gömme kademesi bu modülün ana tehdidi.** `Gateway.embed()` kesintide
istisna atmıyor, `[]` döndürüyor (Görev 03). Boş vektör hem yazma tarafında
(anlamsız satır) hem okuma tarafında (sıfır norm, düzensiz dizi) sessiz yanlış
sonuç üretir; iki taraf da ayrıca korunuyor.
"""

import numpy as np

from gozcu.models import Episode

CANDIDATE_K = 20


def embed_episode(gw, store, episode: Episode) -> bool:
    """Kapanan epizodu gömer; vektör yazıldıysa `True`.

    **Bu fonksiyon istisna atmaz — atamaz.** Görev 07'nin `synthesize`'ı
    kapanışta `on_close(episode)` çağırıyor ve bu geri çağrı oradan
    tetikleniyor; buradan kaçan bir istisna, zaten başarıyla yazılmış epizodu
    ve devir teslim kaydını birlikte götürür. Arıza bu yüzden dönüş
    değerinde görünür: `False` "bu epizodun vektörü yok" demek, çağıran taraf
    kademe düzeldiğinde yeniden gömebilir.

    Kademe bozukken `gw.embed()` `[]` döndürüyor ve o satır YAZILMIYOR:
    yazılsaydı `Store.embeddings()` onu gerçek bir kayıt gibi geri verirdi ve
    boş vektöre karşı kosinüs anlamsızdır.
    """
    try:
        if episode.id is None:
            return False
        text = (f"{episode.summary_tr} | "
                f"katılımcılar: {', '.join(episode.participants)}")
        vector = gw.embed(text)
        if not vector:
            return False
        store.save_embedding(episode.id, list(vector))
        return True
    except Exception:  # noqa: BLE001 — bkz. docstring: geri çağrı istisna atamaz
        return False


def _cosine(matrix: np.ndarray, query: np.ndarray) -> np.ndarray:
    """Satır başına kosinüs benzerliği; sıfır norm `nan` üretmez.

    Sıfır vektör gerçek bir olasılık (model sıfır döndürebilir, satır bozuk
    olabilir). Bölme korunmazsa skor `nan` olur — istisna atmaz, sadece
    sıralamayı sessizce bozar: `argsort` `nan`'ı sona atar ve ters yönlü bir
    epizot alakasız olanın önüne geçer.
    """
    norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query)
    norms[norms == 0] = 1e-9
    return (matrix @ query) / norms


def search_timeline(gw, store, query: str, top_k: int = 5,
                    exclude_id: int | None = None) -> list[Episode]:
    """Sorguya en yakın epizotlar, en alakalı önce.

    `exclude_id` verilen epizodu aday kümesinden düşürür. Görev 11 sorguyu
    `episode.summary_tr` ile atıyor — yani tam olarak gömülmüş metinle — ve
    süzülmezse epizot kendi emsali olarak listenin başında görünür.

    Boş liste üç durumda döner: arşiv boş, sorgu vektörü boş (arama anında
    kademe bozuk) ve sorguyla aynı boyutta tek bir sağlam satır yok.
    """
    # Ölçek notu: `embeddings()` bütün tabloyu, `episodes()` her epizodu her
    # sorguda okuyor. Bir vardiyanın birkaç yüz epizodunda bu anlık ve doğru
    # (karar günlüğü SQLite + numpy'ı vektör veritabanına bilerek tercih etti);
    # on binlerce epizot ölçeğinde yeniden ele alınmalı.
    stored = [(i, v) for i, v in store.embeddings() if i != exclude_id]
    if not stored:
        return []

    query_vector = np.asarray(gw.embed(query), dtype=float)
    if query_vector.size == 0:
        return []

    # Boş ya da farklı boyutlu satırlar düşürülüyor: numpy düzensiz diziye
    # `ValueError` atıyor ve bozuk bir kademeyle yapılmış tek bir tohumlama
    # koşusu (Görev 09 fikstürleri) sonraki HER aramayı öldürürdü.
    rows = [(i, v) for i, v in stored if len(v) == query_vector.size]
    if not rows:
        return []

    ids = [i for i, _ in rows]
    matrix = np.asarray([v for _, v in rows], dtype=float)
    scores = _cosine(matrix, query_vector)

    candidate_ids = [ids[i] for i in np.argsort(-scores)[:CANDIDATE_K]]
    all_episodes = {e.id: e for e in store.episodes()}
    candidates = [all_episodes[i] for i in candidate_ids if i in all_episodes]
    if not candidates:
        return []

    order = gw.rerank(query, [e.summary_tr for e in candidates])
    ordered = [candidates[i] for i in order if 0 <= i < len(candidates)] or candidates
    return ordered[:top_k]
