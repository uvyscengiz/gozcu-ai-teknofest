# Görev 08 — Epizodik hafıza araması (`gozcu/memory.py`)

> ## ✅ TAMAMLANDI — 23 Ağustos 2026, `1cdb29b`
>
> **Hafıza katmanı indi.** `gozcu/memory.py` var, `tests/test_memory.py` 14
> test ile yeşil. Bu dosyayı yeniden uygulama — aşağısı ne yapıldığının kaydı.
>
> **Sonraki göreve başlarken bilmen gerekenler**
> ([kararlar](#tamamlanma-notları-gelecek-görevleri-bağlayan) bölümüne bak):
> `embed_episode` artık `bool` döndürüyor ve **asla istisna atmıyor** — bağlayan
> tarafın `try/except`'e ihtiyacı yok; `search_timeline` `exclude_id` alıyor ve
> sorgu metni bir epizottan geliyorsa geçilmek zorunda; ve **boş vektörler hiç
> yazılmıyor** — okuma tarafı da bozuk satırları ayrıca düşürüyor.

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
#   ^ indeks listesi döndürür, en alakalı önce. Sıra TAM bir permütasyon:
#     modelin verdiği sıra önde, atlananlar sona eklenir, tekrarlar düşürülür.
#     Başarısızlıkta kimlik sırasına düşer, asla exception fırlatmaz.

# gozcu/store.py
Store.save_embedding(episode_id: int, vector: list[float]) -> None
Store.embeddings() -> list[tuple[int, list[float]]]
Store.episodes() -> list[Episode]

# gozcu/models.py
Episode(id, start_ts, end_ts, phase, summary_tr, participants, preliminary_risk, state)
```

**Boş vektör guard'ı (Görev 03).** `gw.embed()` gömme kademesi bozukken istisna
atmıyor, **`[]` döndürüyor**. Arama boş vektörü "sonuç yok" diye okumalı: ona
karşı kosinüs hesaplama — sıfır norm `ZeroDivisionError` ya da anlamsız bir skor
üretir ve bozulmuş bir kademe sessizce yanlış epizotlar döndürür.

> **Görev 07 bağlama uyarısı — gömme geri çağrısı `on_close`'a takılıyor.**
> [Görev 07](07-sentezleyici.md) kapanan epizodu `on_close(episode)` ile
> veriyor ve `run.py` bu görevin `embed_episode`'unu oraya bağlıyor. Üç kural:
>
> 1. **`gw.embed()` `[]` döndürdüğünde hiçbir satır yazma.** Bozulmuş gömme
>    kademesi boş vektör döndürüyor (yukarıdaki guard); `store.save_embedding`
>    yine de çağrılırsa `Store.embeddings()` `(episode_id, [])` satırını gerçek
>    bir kayıt gibi geri verir ve boş vektöre karşı kosinüs anlamsızdır.
>    `save_embedding`'i tamamen atla — epizot, kademe düzeldiğinde yeniden
>    gömülebilir.
> 2. **Geri çağrı istisna atmamalı.** `on_close` `synthesize`'ın içinden
>    çağrılıyor; oradan kaçan bir istisna, zaten başarıyla yazılmış epizodu ve
>    devir teslimi birlikte götürür. **Çözüm bağlayan tarafta değil, burada:**
>    `embed_episode` her arızayı kendi içinde yutup `False` döndürüyor, yani
>    bağlama kodunun `try/except` sarmalayıcısına ihtiyacı yok.
> 3. **Satırlar `episode.id` üzerine anahtarlanıyor.** `on_close` depoya
>    yazılmış epizodu aldığı için `id` her zaman dolu; bu yolda kaydedilmemiş
>    epizot dalı tetiklenmiyor.

## Ne yapacaksın

```python
CANDIDATE_K = 20

embed_episode(gw, store, episode: Episode) -> bool
search_timeline(gw, store, query: str, top_k: int = 5,
                exclude_id: int | None = None) -> list[Episode]
```

Akış: sorguyu göm → `episode_embedding` üzerinde kosinüs → en iyi 20 → reranker →
en iyi 5.

**Depoda filtreli sorgu yok (Görev 02).** `episodes(state=...)` ya da
`risks(episode_id=...)` imzaları mevcut değil; id alan tek yardımcı
`corrections(episode_id)`. Epizot başına süzmeyi `store.episodes()` /
`store.risks()` üzerinde Python tarafında yap.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_memory.py`

```python
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
```

`numpy`'ı `pyproject.toml`'a ekle (ultralytics zaten çekiyor ama doğrudan
bağımlılık olarak beyan et).

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_memory.py -v
```
Beklenen: 14 passed

### 5. Commit

```bash
git add gozcu/memory.py pyproject.toml tests/test_memory.py
git commit -m "feat: episodic memory search with empty-vector and self-match guards"
```

## Doğrulama

```bash
uv run pytest tests/test_memory.py -v
```
Beklenen: **14 passed**

## Tamamlanma notları (gelecek görevleri bağlayan)

- **`embed_episode(gw, store, episode) -> bool` ASLA istisna atmaz — tasarım
  gereği.** `on_close` üzerinden `synthesize`'ın içinden koşuyor ([Görev
  07](07-sentezleyici.md)); oradan kaçan bir istisna, zaten başarıyla yazılmış
  epizodu ve devir teslim kaydını birlikte götürür. Arıza bu yüzden dönüş
  değerinde görünür: `False` "bu epizodun vektörü yok" demek (kaydedilmemiş
  epizot, bozulmuş gömme kademesi ya da gateway hatası) ve çağıran taraf kademe
  düzeldiğinde yeniden gömebilir. Bağlayan tarafın `try/except`'ine gerek yok
  ([Görev 17](17-cikti-sozlesmesi.md)).
- **Bozulmuş gömme kademesi HİÇBİR satır yazmıyor.** `[]` kalıcılaştırılsaydı
  `Store.embeddings()` boş vektörü gerçek bir kayıtmış gibi geri verirdi ve boş
  vektöre karşı kosinüs anlamsızdır.
- **Okuma tarafı ayrıca boş satırları ve sorgudan farklı boyutlu satırları
  düşürüyor; boş sorgu vektöründe anında `[]` dönüyor.** Bu, derinlemesine
  savunma: [Görev 09](09-tesis-dunyasi.md) fikstürleri `embed_episode`
  üzerinden tohumluyor, yani kademe bozukken yapılmış tek bir tohumlama koşusu
  tabloyu zehirleyebilir ve düzensiz dizi yüzünden sonraki HER arama
  `ValueError` atardı.
- **`search_timeline(gw, store, query, top_k=5, exclude_id=None)` — sorgu metni
  bir epizottan geliyorsa `exclude_id` GEÇİLECEK.** Aksi hâlde epizot kendi
  emsali olarak listenin başında görünür ([Görev 11](11-risk-analisti.md)
  sorguyu tam olarak gömülen metinle, `episode.summary_tr` ile atıyor).
- **`Gateway.rerank` artık tam bir permütasyon döndürüyor** (modelin sırası
  önde, atlanan indeksler sona eklenir, tekrarlar düşürülür), dolayısıyla
  çağıranlar aday listesinin tamamını güvenle indeksleyebilir.
- **Her sorguda bütün tablo okunuyor** (`embeddings()` ve `episodes()`) ve bu
  bilerek böyle: bir vardiyanın birkaç yüz epizodunda anlık. On binlerce epizot
  ölçeğinde yeniden ele alınmalı.
