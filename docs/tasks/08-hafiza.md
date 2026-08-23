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
Gateway.goem(metin: str) -> list[float]
Gateway.yeniden_sirala(sorgu: str, adaylar: list[str]) -> list[int]
#   ^ indeks listesi döndürür, en alakalı önce.
#     Başarısızlıkta kimlik sırasına düşer, asla exception fırlatmaz.

# gozcu/store.py
Store.kaydet_embedding(epizot_id: int, vektor: list[float]) -> None
Store.embeddingler() -> list[tuple[int, list[float]]]
Store.epizotlar() -> list[Epizot]

# gozcu/models.py
Epizot(id, baslangic_ts, bitis_ts, faz, ozet_tr, katilimcilar, on_risk, durum)
```

## Ne yapacaksın

```python
ADAY_K = 20

epizodu_gom(gw, store, epizot: Epizot) -> None
zaman_cizelgesi_ara(gw, store, sorgu: str, ust_k: int = 5) -> list[Epizot]
```

Akış: sorguyu göm → `epizot_embedding` üzerinde kosinüs → en iyi 20 → reranker →
en iyi 5.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_memory.py`

```python
from unittest.mock import Mock

import pytest

from gozcu.memory import epizodu_gom, zaman_cizelgesi_ara
from gozcu.models import Epizot
from gozcu.store import Store


def _epizot(ozet, risk="Orta"):
    return Epizot(baslangic_ts=0.0, faz="sonuc", ozet_tr=ozet, on_risk=risk)


def _kaydet(store, gw, *ozetler):
    for o in ozetler:
        e = _epizot(o)
        e.id = store.epizot_ac(e)
        epizodu_gom(gw, store, e)


def test_search_ranks_the_semantically_closest_episode_first():
    store = Store(":memory:")
    gw = Mock()
    # sırayla: iki epizotun gömülmesi, sonra sorgunun gömülmesi
    gw.goem.side_effect = [[1.0, 0.0], [0.0, 1.0], [0.99, 0.14]]
    gw.yeniden_sirala.side_effect = lambda s, adaylar: list(range(len(adaylar)))
    _kaydet(store, gw, "istif aracı devrildi", "personel mola verdi")

    sonuc = zaman_cizelgesi_ara(gw, store, "araç devrilmesi")
    assert sonuc[0].ozet_tr == "istif aracı devrildi"


def test_search_returns_empty_when_nothing_is_stored():
    gw = Mock()
    assert zaman_cizelgesi_ara(gw, Store(":memory:"), "herhangi bir şey") == []
    gw.goem.assert_not_called()


def test_rerank_order_is_honoured():
    store = Store(":memory:")
    gw = Mock()
    gw.goem.side_effect = [[1.0, 0.0], [0.9, 0.1], [1.0, 0.0]]
    gw.yeniden_sirala.side_effect = lambda s, a: list(reversed(range(len(a))))
    _kaydet(store, gw, "birinci", "ikinci")
    assert zaman_cizelgesi_ara(gw, store, "x")[0].ozet_tr == "ikinci"


def test_zero_vectors_do_not_divide_by_zero():
    store = Store(":memory:")
    gw = Mock()
    gw.goem.side_effect = [[0.0, 0.0], [0.0, 0.0]]
    gw.yeniden_sirala.side_effect = lambda s, a: list(range(len(a)))
    _kaydet(store, gw, "sıfır vektör")
    assert len(zaman_cizelgesi_ara(gw, store, "x")) == 1


def test_gom_requires_a_saved_episode():
    with pytest.raises(ValueError):
        epizodu_gom(Mock(), Store(":memory:"), _epizot("kaydedilmemiş"))
```

İkinci test demoyu koruyor: boş arşiv **hiçbir şey** döndürmeli, operatörün
bağlam değiştirdiği anın ortasında exception fırlatmamalı.

`yeniden_sirala` mock'unun **indeks listesi** döndürdüğüne dikkat et — string
listesi döndürürse `adaylar[i]` patlar.

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_memory.py -v
```
Beklenen: `ModuleNotFoundError: No module named 'gozcu.memory'`

### 3. `gozcu/memory.py` yaz

```python
import numpy as np

from gozcu.models import Epizot

ADAY_K = 20


def epizodu_gom(gw, store, epizot: Epizot) -> None:
    if epizot.id is None:
        raise ValueError("epizot önce kaydedilmeli")
    metin = f"{epizot.ozet_tr} | katılımcılar: {', '.join(epizot.katilimcilar)}"
    store.kaydet_embedding(epizot.id, gw.goem(metin))


def zaman_cizelgesi_ara(gw, store, sorgu: str, ust_k: int = 5) -> list[Epizot]:
    kayitli = store.embeddingler()
    if not kayitli:
        return []

    q = np.asarray(gw.goem(sorgu), dtype=float)
    ids = [i for i, _ in kayitli]
    M = np.asarray([v for _, v in kayitli], dtype=float)

    normlar = np.linalg.norm(M, axis=1) * np.linalg.norm(q)
    normlar[normlar == 0] = 1e-9
    skorlar = (M @ q) / normlar

    aday_ids = [ids[i] for i in np.argsort(-skorlar)[:ADAY_K]]
    hepsi = {e.id: e for e in store.epizotlar()}
    adaylar = [hepsi[i] for i in aday_ids if i in hepsi]
    if not adaylar:
        return []

    sira = gw.yeniden_sirala(sorgu, [e.ozet_tr for e in adaylar])
    sirali = [adaylar[i] for i in sira if 0 <= i < len(adaylar)] or adaylar
    return sirali[:ust_k]
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
