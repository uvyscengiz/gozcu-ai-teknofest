# Görev 08 — Epizodik hafıza araması (`gozcu/memory.py`)

**Sahip:** `uvyscengiz` · **Gün:** 25 Ağustos · **Süre:** ~2 saat
**Bağımlılık:** [01](01-sozlesme.md), [02](02-olay-deposu.md), [03](03-gateway.md)

## Bağlam

Sistemin uzun ufuklu hafızası. Operatör *"daha önce bu araçla ilgili bir olay
olmuş muydu?"* diye sorduğunda cevabın geldiği yer.

**Ne gömdüğümüz konusunda dürüst olalım:** video segmentlerini değil, **olay
kayıtlarını** gömüyoruz. Her epizot kaydı zaten görsel yorumu, tespitleri ve
sinyalleri içeriyor — yani damıtılmış bir temsil. API'den bir video kodlayıcıya
erişimimiz yok ve olmayan bir şeyi iddia etmiyoruz. Bu haliyle de tez ayakta:
bir olayı çok daha öncekine bağlamak, context penceresine sığandan fazlasını
hatırlamak.

**Vektör veritabanı yok.** Bir vardiya birkaç yüz epizot demek; numpy ile kaba
kuvvet kosinüs anlık. FAISS/Chroma bağımlılığı üç günde kurulum riski ve sıfır
kazanç.

## Kurulum

```bash
uv sync --extra dev
uv run pytest tests/test_gateway.py tests/test_store.py -v
```

## Bağımlı olduğun imzalar

```python
# gozcu/gateway.py
Gateway.embed(text: str) -> list[float]
Gateway.rerank(query: str, candidates: list[str]) -> list[int]
#   ^ indeks listesi döndürür, en alakalı önce.
#     Başarısızlıkta kimlik sırasına düşer, asla exception fırlatmaz.

# gozcu/store.py
Store.save_embedding(episode_id: int, vector: list[float]) -> None
Store.embeddings() -> list[tuple[int, list[float]]]
Store.episodes() -> list[Episode]

# gozcu/models.py
Episode(id, start_ts, end_ts, phase, summary_tr, participants, preliminary_risk, state)
```

## Ne yapacaksın

```python
CANDIDATE_K = 20

embed_episode(gw, store, episode: Episode) -> None
search_timeline(gw, store, query: str, top_k: int = 5) -> list[Episode]
```

Akış: sorguyu göm → `epizot_embedding` üzerinde kosinüs → en iyi 20 → reranker →
en iyi 5.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_memory.py`

```python
from unittest.mock import Mock

import pytest

from gozcu.memory import embed_episode, search_timeline
from gozcu.models import Episode
from gozcu.store import Store


def _ep(ozet, risk="Orta"):
    return Episode(start_ts=0.0, phase="outcome", summary_tr=ozet, preliminary_risk=risk)


def _save(store, gw, *summaries):
    for o in summaries:
        e = _ep(o)
        e.id = store.create_episode(e)
        embed_episode(gw, store, e)


def test_search_ranks_the_semantically_closest_episode_first():
    store = Store(":memory:")
    gw = Mock()
    # sırayla: iki epizotun gömülmesi, sonra sorgunun gömülmesi
    gw.embed.side_effect = [[1.0, 0.0], [0.0, 1.0], [0.99, 0.14]]
    gw.rerank.side_effect = lambda s, candidates: list(range(len(candidates)))
    _save(store, gw, "istif aracı devrildi", "personnel mola verdi")

    result = search_timeline(gw, store, "araç devrilmesi")
    assert result[0].summary_tr == "istif aracı devrildi"


def test_search_returns_empty_when_nothing_is_stored():
    gw = Mock()
    assert search_timeline(gw, Store(":memory:"), "herhangi bir şey") == []
    gw.embed.assert_not_called()


def test_rerank_order_is_honoured():
    store = Store(":memory:")
    gw = Mock()
    gw.embed.side_effect = [[1.0, 0.0], [0.9, 0.1], [1.0, 0.0]]
    gw.rerank.side_effect = lambda s, a: list(reversed(range(len(a))))
    _save(store, gw, "birinci", "ikinci")
    assert search_timeline(gw, store, "x")[0].summary_tr == "ikinci"


def test_zero_vectors_do_not_divide_by_zero():
    store = Store(":memory:")
    gw = Mock()
    gw.embed.side_effect = [[0.0, 0.0], [0.0, 0.0]]
    gw.rerank.side_effect = lambda s, a: list(range(len(a)))
    _save(store, gw, "sıfır vektör")
    assert len(search_timeline(gw, store, "x")) == 1


def test_gom_requires_a_saved_episode():
    with pytest.raises(ValueError):
        embed_episode(Mock(), Store(":memory:"), _ep("kaydedilmemiş"))
```

İkinci test demoyu koruyor: boş arşiv **hiçbir şey** döndürmeli, operatörün
bağlam değiştirdiği anın ortasında exception fırlatmamalı.

`rerank` mock'unun **indeks listesi** döndürdüğüne dikkat et — string
listesi döndürürse `candidates[i]` patlar.

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_memory.py -v
```
Beklenen: `ModuleNotFoundError: No module named 'gozcu.memory'`

### 3. `gozcu/memory.py` yaz

```python
import numpy as np

from gozcu.models import Episode

CANDIDATE_K = 20


def embed_episode(gw, store, episode: Episode) -> None:
    if episode.id is None:
        raise ValueError("episode önce kaydedilmeli")
    text = f"{episode.summary_tr} | katılımcılar: {', '.join(episode.participants)}"
    store.save_embedding(episode.id, gw.embed(text))


def search_timeline(gw, store, query: str, top_k: int = 5) -> list[Episode]:
    stored = store.embeddings()
    if not stored:
        return []

    q = np.asarray(gw.embed(query), dtype=float)
    ids = [i for i, _ in stored]
    M = np.asarray([v for _, v in stored], dtype=float)

    norms = np.linalg.norm(M, axis=1) * np.linalg.norm(q)
    norms[norms == 0] = 1e-9
    scores = (M @ q) / norms

    candidate_ids = [ids[i] for i in np.argsort(-scores)[:CANDIDATE_K]]
    all_eps = {e.id: e for e in store.episodes()}
    candidates = [all_eps[i] for i in candidate_ids if i in all_eps]
    if not candidates:
        return []

    order = gw.rerank(query, [e.summary_tr for e in candidates])
    ordered = [candidates[i] for i in order if 0 <= i < len(candidates)] or candidates
    return ordered[:top_k]
```

`numpy`'ı `pyproject.toml`'a ekle (ultralytics zaten çekiyor ama doğrudan
bağımlılık olarak beyan et).

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_memory.py -v
```
Beklenen: 5 passed

### 5. Commit

```bash
git add gozcu/memory.py pyproject.toml tests/test_memory.py
git commit -m "feat: episodic memory search via embedding and rerank"
```

## Doğrulama

```bash
uv run pytest tests/test_memory.py -v
```
Beklenen: **5 passed**
