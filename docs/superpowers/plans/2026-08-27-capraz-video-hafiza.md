# Çapraz Video Epizodik Hafıza + Koşu İçi Kısa Süreli Hafıza — Uygulama Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sistemin iki türlü hafızasını (videolar arası epizodik arşiv + koşu içi kısa süreli bağlam) canlı koşuda gerçekten devreye sokmak — kod yazılmış ve testleri geçiyor ama üretim yolundan hiç çağrılmıyor.

**Architecture:** SQLite (`Store`) koşu kapsamlı KALIR; Qdrant uzun süreli hafızanın TEK adresidir. Arşiv koşunun deposuna hiç girmez. Nokta kimliği koşu içi rowid yerine `uuid5(source:episode_id)` olur; `source` videonun içerik hash'i. Kısa süreli hafıza yeni bir `gozcu/recall.py` modülünde, `DecisionLoop`'a **dokunmadan**, `run.py`'deki kapanışlarla bağlanır.

**Tech Stack:** Python 3.12, pydantic v2, `qdrant-client`, FastAPI + SSE, pytest, uv. Model çağrıları `gozcu.gateway.Gateway` üzerinden.

**Spec:** `docs/superpowers/specs/2026-08-27-capraz-video-hafiza-design.md` — görev metnindeki §N o belgeye gönderme. Spec iki kör inceleme turundan geçti; "reddedilen tasarım" kutuları **bilerek** orada, tekrar önerilmesin.

## Global Constraints

- **Kod İngilizce; insana görünen her metin Türkçe** — promptlar, operatör mesajları, sabitler, yorumlar, docstring'ler. (CLAUDE.md)
- **Risk seviyeleri tam olarak** `"Düşük" | "Orta" | "Yüksek" | "Kritik"`.
- **Çıktı sözleşmesi** `summary` · `events` · `risk` · `actions` her koşuda üretilir; fazlası `detail` altında.
- **Model kimlikleri yalnız `gozcu/config.py`'da.** Başka hiçbir dosyada model adı yazılmaz.
- **Hiçbir kesinti bir koşuyu düşürmez.** `embed_episode` `False` döner, `search_timeline` `[]` döner; ikisi de **istisna atmaz**.
- **TDD:** önce test, kırmızı olduğunu GÖR, sonra minimum kod. Her görev kendi commit'iyle biter.
- Testler depo kökünden: `uv run pytest tests/ -v`. **Taban 1026 test**; her sapma o görevin commit mesajında açıklanır.
- `DecisionLoop`, `loop.py` ve `_may_open` kapısı **DEĞİŞMEZ**.
- Algı katmanı (`frames.py`, `detect.py`, `track.py`, `signals.py`) bu planın kapsamı dışında.

## Dosya haritası

| Dosya | Sorumluluk | Görev |
|---|---|---|
| `gozcu/memory.py` | Qdrant'a yazma/okuma, kimlik, eşik, dedup, kilit | 1, 4, 9, 10 |
| `gozcu/models.py` | `Episode` köken alanları, `Precedent`, `RiskAssessment.precedents` | 2, 9, 11 |
| `gozcu/run.py` | `source` üretimi, `archive` bayrağı, gömme süpürmesi, `RunMemory` kapanışları | 3, 7, 8, 15 |
| `gozcu/agents/synthesizer.py` | `source` damgası, digest'e kapanmış epizotlar | 3, 16 |
| `gozcu/fixtures/loader.py` | Arşiv tohumlama — artık yalnız Qdrant'a | 5 |
| `gozcu/ui/session.py` · `server.py` | `source` taşıma, tohumlama çağrısı, arşiv sayısı | 3, 6, 12 |
| `gozcu/agents/risk.py` · `supervisor.py` | Emsal tüketimi, projeksiyon, yükseltme cümlesi | 9, 11, 16 |
| `gozcu/ui/feed.py` · `view.py` | EMSAL kartı, rozet | 12 |
| `gozcu/recall.py` **(yeni)** | `RunMemory` — koşu içi kısa süreli hafıza | 14 |
| `gozcu/agents/interpreter.py` | `ÖNCEKİ PENCERELER` bloğu | 15 |
| `scripts/reset_memory.py` · `calibrate_memory.py` **(yeni)** | Koleksiyon sıfırlama, eşik kalibrasyonu | 0, 17 |
| `gozcu/config.py` | Eşikler, `RECALL_*`, `SUPERVISOR_HISTORY_TURNS` | 10, 14, 16, 17 |

## Bağımlılık ve paralellik

Zorunlu sıra: **0 → 1 → {2,3,4} → 5 → 6 → 7 → 8 → 9 → 10 → {11,12,13} → 17**.
**Görev 14–16 (Aşama 6) tamamen bağımsız** — 1–13 ile paralel koşabilir, ama **17'den ÖNCE bitmeli**: eşik epizot ÖZET METİNLERİ üzerinden kalibre ediliyor ve Görev 15 yorumlayıcının `description`'ını değiştiriyor → `summary_tr` değişiyor → aynı arşive karşı skorlar kayıyor. **Görev 17 her hâlükârda EN SON.**

> **Sırayı bozma tuzağı (§1):** Görev 6 (tohumlamanın çağrılması) Görev 1'den (kararlı kimlik) ÖNCE inerse, fikstür noktaları (`id = 0,1,2`) o koşunun canlı epizotları (SQLite rowid `1,2,3`) tarafından **gerçekten paylaşılan `team37`'de ezilir**.

---

### Task 0: Koleksiyon sıfırlama aracı (§2)

**Files:**
- Create: `scripts/reset_memory.py`
- Test: yok — script'ler test edilmiyor (`scripts/gen-litellm-config.py` ile aynı gelenek); doğrulama Görev 17'nin koşusunda

**Interfaces:**
- Consumes: `gozcu.memory.build_client`, `gozcu.config.QDRANT_COLLECTION`, `gozcu.fixtures.loader.load_history`, `gozcu.gateway.Gateway`, `gozcu.store.Store`
- Produces: elle koşulan bir script. **Hiçbir kod ona bağlanmaz.**

> **Script YAZILIR, KOŞTURULMAZ.** Sıfırlama Görev 17'nin 2. adımında, Görev 1–16 indikten SONRA koşar. Şimdi koşturulursa koleksiyona taze **tamsayı** kimlikli noktalar konur ve hiçbir işe yaramaz.

- [ ] **Step 1: Script'i yaz**

```python
"""team37 koleksiyonunu düşürür ve fikstürlerle yeniden tohumlar.

Bu depoda bir ilk: **veri silen** bir script. O yüzden çıplak çağrıldığında
hiçbir şey silmiyor — ne yapacağını yazıp çıkıyor. Silmesi için ortamda
`GOZCU_MEMORY_RESET=1` olmak zorunda.

Neden gerekli: 27 Ağustos'ta canlı koleksiyonda ölçüldü — üç nokta, üçü de
`prior_incidents.json` fikstürü, kimlikleri tamsayı (`1`/`2`/`3`) ve payload'da
`source` alanı YOK. Yeni kimlik `uuid5(source:id)` olduğu için o noktalar yeni
şemayla çakışmaz, ama silinmezlerse aynı üç fikstür arşivde İKİ KEZ durur ve
ne dışlama filtresi ne kaynak tekilleştirmesi onları tanır.

Kayıp geri alınabilir: silinen her nokta `prior_incidents.json`'dan bire bir
yeniden üretiliyor.
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from gozcu.config import QDRANT_COLLECTION          # noqa: E402
from gozcu.fixtures.loader import load_history      # noqa: E402
from gozcu.gateway import Gateway                   # noqa: E402
from gozcu.memory import build_client, memory_backend  # noqa: E402
from gozcu.store import Store                       # noqa: E402

ONAY = "GOZCU_MEMORY_RESET"


def main() -> int:
    if memory_backend() != "qdrant":
        # Anahtarsız modda `build_client()` süreç içi bir Qdrant döndürüyor
        # (`memory.py:87`). O örneği "sıfırlamak" hiçbir şey yapmaz ama
        # ekrana "3 fikstür yeniden tohumlandı" yazar — yani script kalıcı
        # bir şey yaptığını SANDIRIR. Sessiz düşüş yasak.
        print("HATA: GOZCU_QDRANT_API_KEY tanımlı değil. Süreç içi bir "
              "Qdrant'ı sıfırlamanın anlamı yok; anahtarı ver.")
        return 1

    client = build_client()
    exists = client.collection_exists(QDRANT_COLLECTION)
    existing = client.get_collection(QDRANT_COLLECTION).points_count if exists else 0

    if exists and existing:
        # **Silinecekler silinmeden ÖNCE basılıyor.** "Üçü de fikstür"
        # ölçümü 27 Ağustos'a ait; uygulama gününde bir takım arkadaşının
        # noktası eklenmiş olabilir ve script buna körü körüne devam
        # etmemeli. Onay veren kişi neyi kaybettiğini GÖRSÜN.
        points, _ = client.scroll(QDRANT_COLLECTION, limit=100,
                                  with_payload=True, with_vectors=False)
        for point in points:
            payload = point.payload or {}
            print(f"  silinecek: id={point.id} "
                  f"kaynak={payload.get('source', '(yok)')} "
                  f"özet={str(payload.get('summary_tr'))[:60]}")

    if os.environ.get(ONAY) != "1":
        print(f"{QDRANT_COLLECTION}: {existing} nokta. Hiçbir şey silinmedi — "
              f"silmek için {ONAY}=1 ver.")
        return 0

    if exists:
        client.delete_collection(QDRANT_COLLECTION)

    store = Store()
    embedded = load_history(Gateway(store), store)
    print(f"{QDRANT_COLLECTION}: {existing} nokta silindi, "
          f"{embedded} fikstür yeniden tohumlandı.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Onaysız koşuyu doğrula — hiçbir şey silinmemeli**

Run: `uv run --env-file .env python scripts/reset_memory.py`
Expected: silinecek noktaların dökümü, ardından `episodes: 3 nokta. Hiçbir şey silinmedi — silmek için GOZCU_MEMORY_RESET=1 ver.`

> Anahtar tanımlı değilse script `HATA: GOZCU_QDRANT_API_KEY tanımlı değil` deyip **1** ile çıkar — süreç içi bir Qdrant'ı sıfırlamak kalıcı bir şey yapıldığı izlenimi verirdi.

> **`GOZCU_MEMORY_RESET=1` ile ŞİMDİ koşturma.** Yukarıdaki kutuya bak.

- [ ] **Step 3: Testlerin hâlâ 1026 olduğunu doğrula**

Run: `uv run pytest tests/ -q`
Expected: 1026 passed

- [ ] **Step 4: Commit**

```bash
git add scripts/reset_memory.py
git commit -m "feat(hafıza): koleksiyon sıfırlama aracı — onaysız hiçbir şey silmiyor"
```

---

### Task 1: Kararlı nokta kimliği — `video_key` + `point_id` (§3.1)

**Files:**
- Modify: `gozcu/memory.py` (import bloğu ~1-30; `embed_episode` ~199)
- Test: `tests/test_memory.py`

**Interfaces:**
- Produces: `memory.video_key(path) -> str` · `memory.point_id(source: str | None, episode_id: int) -> str`. Görev 3 `video_key`'i, Görev 9 `point_id`'yi çağırıyor.
- Produces: `embed_episode` artık `PointStruct(id=point_id(episode.source, episode.id), …)` yazıyor. **Bu satır olmadan Görev 9'un dışlaması hiçbir zaman eşleşmez ve istisna da atmaz.**

> Bu görev `Episode.source`'a **başvuruyor ama onu tanımlamıyor** — Görev 2 tanımlıyor. Aradaki tek görevlik boşlukta `getattr(episode, "source", None)` KULLANMA; bunun yerine görevleri sırayla uygula: Görev 1'in testleri `source` alanı olmadan da geçer çünkü `point_id`'yi doğrudan çağırıyorlar, `embed_episode` satırı ise Görev 2 indikten sonra yeşile döner. **Görev 1 ve 2 aynı commit'te birleştirilebilir; ayrı tutulmalarının tek sebebi inceleme kolaylığı.**

- [ ] **Step 1: Kırmızı testleri yaz**

`tests/test_memory.py` sonuna ekle. Dosyanın `_client`, `_vec`, `_ep(summary, risk, episode_id, participants)`, `_save`, `_points` yardımcıları zaten var — **`_ep` `source` ALMIYOR**, o yüzden aşağıda gereken yerlerde alan kurulumdan sonra elle yazılıyor (`episode.source = …`). `_ep`'e parametre eklemek de olurdu; elle yazmak testin neyi kurduğunu görünür kılıyor.

```python
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
```

- [ ] **Step 2: Kırmızıyı gör**

Run: `uv run pytest tests/test_memory.py -q -k "point_id or video_key or uuid_identity"`
Expected: FAIL — `ImportError: cannot import name 'point_id'`

- [ ] **Step 3: Minimum kodu yaz**

`gozcu/memory.py` — import bloğuna `import hashlib`, `import os`, `import uuid` ekle; modül sabitlerinin yanına:

```python
#: Nokta kimliklerinin ad uzayı. Sabit ve DEĞİŞMEZ: değişirse bütün arşiv
#: erişilemez hâle gelir (aynı epizot yeni bir kimlik üretir, eskisi öksüz
#: kalır ve dışlama artık onu bulamaz).
_NAMESPACE = uuid.UUID("6f5f1f7c-0b4a-5a3e-9c2d-7e1b8a4f3d20")

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
```

`embed_episode` içinde `PointStruct` satırını değiştir:

```python
            target.upsert(
                QDRANT_COLLECTION,
                points=[PointStruct(
                    id=point_id(getattr(episode, "source", None), episode.id),
                    vector=vector, payload=episode.model_dump())])
```

> `getattr` **geçici**: Görev 2 `source` alanını eklediğinde bu satır
> `point_id(episode.source, episode.id)` olur. Görev 2'nin son adımı bunu
> düzeltmek.

- [ ] **Step 4: Yeşili gör**

Run: `uv run pytest tests/test_memory.py -q`
Expected: iki test kırmızı kalır — `test_embed_episode_reports_true_when_a_vector_is_stored` (`[p.id …] == [7]`) ve `test_embedding_the_same_episode_twice_replaces_the_point`. **Beklenen**; sıradaki adım.

- [ ] **Step 5: Kimliği tamsayı bekleyen iki testi güncelle**

`tests/test_memory.py:114` içinde `assert [p.id for p in stored] == [7]` yerine:

```python
    assert [p.id for p in stored] == [point_id(None, 7)]
    assert stored[0].payload["id"] == 7, "epizot kimliği payload'da okunabilir kalmalı"
```

`tests/test_memory.py:143` (`…same_episode_twice_replaces_the_point`) içinde tekillik iddiasını kimlikten bağımsız kur:

```python
    assert len(_points(client)) == 1, "aynı çift tek nokta bırakmalı"
```

**ÜÇÜNCÜ bir test de kırılıyor ve bu görevde onarılamıyor.** `tests/test_memory.py:247` `test_search_excludes_the_originating_episode`: `search_timeline` hâlâ `exclude_id: int` alıyor (`memory.py:224`, `:252`) ve `HasIdCondition(has_id=[1])` artık hiçbir UUID noktayla eşleşmiyor — dışlama sessizce hiçbir şey elemiyor ve `[1, 2] != [2]` düşüyor. Onarımı **Görev 9'da** (imza `exclude` çiftine dönünce).

İki seçenek, ikisi de kabul:
1. **Önerilen:** testi Görev 9'a kadar `@pytest.mark.xfail(reason="exclude imzası Görev 9'da çifte dönüyor", strict=True)` ile işaretle. `strict=True` önemli — Görev 9 inince beklenmedik şekilde GEÇERSE test kırmızı olur ve işaretin kaldırılması unutulmaz.
2. Görev 1 ve 9'u tek commit'te birleştir.

**Beklenen sayı bu seçime bağlı.** `xfail` ile: 1026 + 5 yeni = **1031 passed, 1 xfailed**.

Dosyanın başındaki import satırına `point_id`'yi ekle:
`from gozcu.memory import embed_episode, point_id, search_timeline`

- [ ] **Step 6: Bütün paketi koştur**

Run: `uv run pytest tests/ -q`
Expected: 1031 passed, 1 xfailed

- [ ] **Step 7: Commit**

```bash
git add gozcu/memory.py tests/test_memory.py
git commit -m "feat(hafıza): nokta kimliği uuid5(source:episode_id) — koşular birbirini ezmiyor

B3: nokta kimliği koşu içi SQLite rowid'iydi ve Store her koşuda ':memory:';
iki videodan iki epizot tek noktaya düşüyordu. video_key içerik hash'i
(dosya adı DEĞİL) ve okunamayan yolda istisna atmıyor."
```

---

### Task 2: `Episode` köken alanları (§3.2)

**Files:**
- Modify: `gozcu/models.py` (`Episode`, ~134-157)
- Modify: `gozcu/memory.py` (`embed_episode`'daki geçici `getattr`)
- Test: `tests/test_models.py`, `tests/test_memory.py`

**Interfaces:**
- Produces: `Episode.source: str | None` · `Episode.occurred_at: str | None` · `Episode.equipment_ids: list[str]` · `Episode.actions_taken: list[dict]`. Görev 3, 4, 5, 9, 11, 12 bu alanları okuyor.

- [ ] **Step 1: Kırmızı testleri yaz**

`tests/test_models.py` sonuna:

```python
def test_an_episode_carries_its_provenance():
    from gozcu.models import Episode
    episode = Episode(start_ts=0.0, phase="onset", summary_tr="devrilme",
                      preliminary_risk="Yüksek", source="9f2a",
                      occurred_at="2026-08-12T23:41:00+03:00",
                      equipment_ids=["IST-04"],
                      actions_taken=[{"tool": "dispatch_medical",
                                      "eta_minutes": 4}])
    assert episode.source == "9f2a"
    assert episode.equipment_ids == ["IST-04"]
    assert episode.actions_taken[0]["eta_minutes"] == 4


def test_provenance_fields_default_to_empty_so_old_rows_still_load():
    """Alanlar eklemeden ÖNCE yazılmış satırlar okunmaya devam etmeli."""
    from gozcu.models import Episode
    episode = Episode(start_ts=0.0, phase="onset", summary_tr="x",
                      preliminary_risk="Düşük")
    assert episode.source is None and episode.occurred_at is None
    assert episode.equipment_ids == [] and episode.actions_taken == []


def test_occurred_at_is_a_separate_text_field_from_start_ts():
    """`start_ts` VİDEO saniyesi. Oraya epoch damgası yazılırsa `mmss()` onu
    `99:59`'a yapıştırır ve `kpi.epoch_scale_episodes` koşuyu düşürür —
    olayın takvim tarihi bu yüzden AYRI bir alanda yaşıyor."""
    from benchmark.kpi import EPOCH_THRESHOLD_S
    from gozcu.models import Episode
    episode = Episode(start_ts=12.5, phase="onset", summary_tr="x",
                      preliminary_risk="Düşük",
                      occurred_at="2026-08-12T23:41:00+03:00")
    assert episode.start_ts < EPOCH_THRESHOLD_S
    assert isinstance(episode.occurred_at, str)
```

`tests/test_memory.py` sonuna:

```python
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
```

`tests/test_memory.py`'nin import satırına `VectorParams` ekle:
`from qdrant_client.models import Distance, PointStruct, VectorParams`

- [ ] **Step 2: Kırmızıyı gör**

Run: `uv run pytest tests/test_models.py tests/test_memory.py -q -k "provenance or occurred_at or before_the_new_fields"`
Expected: FAIL — `ValidationError: Extra inputs are not permitted [type=extra_forbidden]`

- [ ] **Step 3: Alanları ekle**

`gozcu/models.py`, `Episode` sınıfında `summary_source` alanının **hemen altına**:

```python
    #: Epizodun geldiği yer: canlı videonun içerik anahtarı (`video_key`,
    #: 16 haneli hex) ya da arşiv kaydı (`"arşiv:OLY-2026-0812"`). Nokta
    #: kimliğinin ilk parçası — `None` kalırsa `memory.point_id` bütün
    #: epizotları tek kaynak sanır ve kaynak tekilleştirmesi onları tek
    #: kovaya koyar (spec §3.3).
    source: str | None = None
    #: Olayın TAKVİM zamanı, ISO 8601 text. `start_ts` video saniyesi ve
    #: öyle KALMAK ZORUNDA: oraya epoch damgası yazılırsa `mmss()` onu
    #: `99:59`'a yapıştırır ve `kpi.epoch_scale_episodes` koşuyu düşürür.
    occurred_at: str | None = None
    #: Olaya karışan ekipman kimlikleri. Arşiv kayıtlarında fikstürden
    #: geliyor; canlı epizotta boş — kamera ekipman kimliği OKUMUYOR ve
    #: bu belirsizlik dürüstçe taşınıyor (algı katmanında OCR yok).
    equipment_ids: list[str] = Field(default_factory=list)
    #: Bu olayda gerçekten çağrılmış saha araçları ve sonuçlarının anahtar
    #: alanları. Aksiyon defteri koşu kapsamlı SQLite'ta yaşıyor ve video
    #: bitince yok oluyor; bu alan olmadan "geçen sefer ambulans kaç
    #: dakikada geldi" YAPISAL olarak cevaplanamaz (spec §3.4).
    actions_taken: list[dict] = Field(default_factory=list)
```

`gozcu/memory.py`'de Görev 1'in geçici satırını sadeleştir:

```python
                points=[PointStruct(
                    id=point_id(episode.source, episode.id),
                    vector=vector, payload=episode.model_dump())])
```

- [ ] **Step 4: Yeşili gör**

Run: `uv run pytest tests/ -q`
Expected: 1035 passed, 1 xfailed

- [ ] **Step 5: Commit**

```bash
git add gozcu/models.py gozcu/memory.py tests/test_models.py tests/test_memory.py
git commit -m "feat(sözleşme): Episode köken alanları — source, occurred_at, equipment_ids, actions_taken

B5: emsalin kökeni yoktu; Episode hangi videodan/tarihten geldiğini
taşımıyordu. occurred_at AYRI bir ISO metin alanı — start_ts video
saniyesi kalıyor, epoch damgası kpi.epoch_scale_episodes'ı düşürürdü."
```

---

### Task 3: `source` zincirinin bağlanması (§3.3)

**Files:**
- Modify: `gozcu/agents/synthesizer.py` (`synthesize` imzası ~257-259; açılış dalı ~298-305)
- Modify: `gozcu/run.py` (`run_pipeline` ~313; `synthesize` kapanışı ~426-428)
- Modify: `gozcu/agents/supervisor.py` (`__init__` ~266)
- Modify: `gozcu/ui/session.py` (`Session.__init__` ~55-60)
- Modify: `gozcu/ui/server.py` (`post_run` ~800-835)
- Test: `tests/test_synthesizer.py`, `tests/test_session.py`, `tests/test_server.py`

**Interfaces:**
- Consumes: `memory.video_key` (Görev 1), `Episode.source` (Görev 2)
- Produces: `synthesize(gw, store, window, interpretation, decision, on_close=None, source=None)` · `Supervisor(gw, store, source=None)` · `Session(source=None)` ile `session.source`

> **`source` YARATILIŞTA damgalanır, kapanışta değil.** `Supervisor.escalate` → `assess_risk` **açık** epizot üzerinde koşuyor; kapanışta damgalansaydı dışlama için elde `"None:0"` olurdu ve epizot kendi emsali olarak listenin başına otururdu.

> **`run_pipeline`'a `source` PARAMETRESİ EKLENMİYOR.** `video_key` iki yerde çağrılıyor — `run_pipeline` içinde (epizotları damgalamak için) ve `post_run` içinde (`Supervisor`'ı kurmak için). İkisi de aynı dosyayı okuyor ve hash saf, yani değerler eşit olmak zorunda. Parametre eklemek o eşitliği çağıranın disiplinine bırakırdı; bir çağıran geçmeyi unuttuğunda filtre **sessizce boş küme** döndürürdü.

- [ ] **Step 1: Kırmızı testleri yaz**

`tests/test_synthesizer.py` sonuna. **Dosyanın gerçek yardımcıları `_gateway()` ve `_window(start=0.0, count=10)`** — `_gw`/`_store` diye bir şey YOK; depo `Store(":memory:")` ile satır içinde kuruluyor (bkz. `:84`, `:98`):

```python
def test_a_new_episode_is_stamped_with_the_source_at_birth():
    """Kapanışta damgalansaydı `assess_risk` açık epizotta koşarken elde
    `"None:0"` olurdu ve epizot kendi emsali olarak listenin başına otururdu."""
    store = Store(":memory:")
    episode = synthesize(_gateway(), store, _window(), None,
                         "open_episode", source="9f2a")
    assert episode.source == "9f2a"


def test_updating_an_open_episode_does_not_overwrite_its_source():
    """Epizot `source`'unu doğuşundan taşıyor; güncelleme dalı ona dokunmaz —
    dokunursa `catch_up` ile gelen bir pencere onu yanlış videoya bağlayabilir."""
    store = Store(":memory:")
    open_ep = synthesize(_gateway(), store, _window(0), None,
                      "open_episode", source="9f2a")
    updated = synthesize(_gateway(), store, _window(10), None,
                        "update_episode", source="BAŞKA")
    assert updated.id == open_ep.id
    assert updated.source == "9f2a"
```

`tests/test_session.py` sonuna:

```python
def test_the_session_hands_its_source_to_the_supervisor():
    """Süpervizör kendi precedent_line aramasında aynı dışlamayı uygulayabilmeli."""
    from gozcu.ui.session import Session
    session = Session(source="9f2a")
    assert session.source == "9f2a"
    assert session.nobetci.source == "9f2a"


def test_a_session_without_a_source_still_builds():
    """Doğrudan çağıranlar ve testler `source` vermiyor."""
    from gozcu.ui.session import Session
    assert Session().source is None
```

- [ ] **Step 2: Kırmızıyı gör**

Run: `uv run pytest tests/test_synthesizer.py tests/test_session.py -q -k "source"`
Expected: FAIL — `TypeError: synthesize() got an unexpected keyword argument 'source'`

- [ ] **Step 3: Zinciri bağla**

`gozcu/agents/synthesizer.py` — imza (parametre **sonda**, dosyanın geleneği):

```python
def synthesize(gw, store, window: list[Observation],
               interpretation: Interpretation | None,
               decision: str, on_close=None,
               source: str | None = None) -> Episode | None:
```

açılış dalında (`~298`):

```python
        episode = Episode(start_ts=window[0].ts, end_ts=end_ts,
                          phase=synthesis.phase,
                          summary_tr=synthesis.summary_tr,
                          participants=synthesis.participants,
                          preliminary_risk=synthesis.preliminary_risk,
                          state="open", beats=beats,
                          summary_source=synthesis.summary_source,
                          # Damga YARATILIŞTA. Güncelleme dalı (aşağıda)
                          # `source`'a DOKUNMUYOR: epizot onu doğuşundan
                          # taşıyor ve `catch_up` ile gelen geç bir pencere
                          # onu yanlış videoya bağlayamaz.
                          source=source)
```

`gozcu/run.py` — `run_pipeline` gövdesinde, `archived = …` satırının hemen üstüne:

```python
    # Bu videonun kimliği. `run_pipeline`'a parametre olarak GEÇİLMİYOR:
    # `post_run` da aynı dosyadan aynı anahtarı üretiyor ve hash saf.
    # Parametre olsaydı eşitlik çağıranın disiplinine kalırdı ve bir çağıran
    # onu geçmeyi unuttuğunda precedent_line filtresi sessizce boş küme döndürürdü.
    source = video_key(video_path)
```

`synthesize` kapanışını (`~426`) güncelle:

```python
            synthesize=lambda window, interpretation, decision: synthesize(
                gw, store, window, interpretation, decision,
                on_close=lambda episode: _on_close_traced(gw, store, episode),
                source=source),
```

import satırına ekle: `from gozcu.memory import embed_episode, video_key`

`gozcu/agents/supervisor.py`:

```python
    def __init__(self, gw, store, source: str | None = None) -> None:
        self.gw, self.store = gw, store
        #: Bu koşunun videosunun kimliği — precedent_line aramasında kendi
        #: epizotlarını dışlayabilmek için. `None` doğrudan çağıranlar için.
        self.source = source
```

`gozcu/ui/session.py`:

```python
    def __init__(self, source: str | None = None) -> None:
        self.store = Store()
        self.gw = Gateway(self.store)
        #: Videonun içerik anahtarı (`memory.video_key`). `post_run` yükleme
        #: BİTTİKTEN sonra kuruyor — hash dosyanın diskte tam olmasını
        #: gerektiriyor.
        self.source = source
        self.nobetci = Supervisor(self.gw, self.store, source=source)
```

`gozcu/ui/server.py` — `post_run` içinde **`Session()` kurulumunu yükleme döngüsünden SONRAYA al**. Bugünkü sıra `session = Session()` → `output_dir` → `video_path` → yazma döngüsü; aradaki iki satır `session`'a dokunmuyor, o yüzden taşıma güvenli ve `_run_lock` blok boyunca tutulduğu için yarış penceresi açılmıyor:

```python
        run_id = uuid4().hex
        output_dir = _output_dir_for(run_id)
        video_path = output_dir / _safe_upload_name(video.filename)
        written = 0
        with video_path.open("wb") as handle:
            while chunk := await video.read(UPLOAD_CHUNK_BYTES):
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    handle.close()
                    video_path.unlink(missing_ok=True)
                    raise HTTPException(status_code=413,
                                        detail=UPLOAD_TOO_LARGE)
                handle.write(chunk)

        # `Session` yükleme BİTTİKTEN sonra kuruluyor: `video_key` dosyanın
        # diskte tam olmasını gerektiriyor ve `Supervisor` kimliği kurulumda
        # alıyor. `_run_lock` block boyunca tutulduğu için sıra değişikliği
        # yeni bir yarış penceresi açmıyor.
        session = Session(source=video_key(video_path))
        session.output_dir = output_dir
```

import satırına ekle: `from gozcu.memory import memory_backend, video_key`

- [ ] **Step 4: Yeşili gör**

Run: `uv run pytest tests/ -q`
Expected: 1039 passed, 1 xfailed

- [ ] **Step 5: Commit**

```bash
git add gozcu/agents/synthesizer.py gozcu/agents/supervisor.py gozcu/run.py gozcu/ui/session.py gozcu/ui/server.py tests/
git commit -m "feat(hafıza): source zinciri — epizot köken damgasını doğuşta alıyor

Kapanışta damgalamak assess_risk'i açık epizotta 'None:0' ile bırakır ve
epizot kendi emsali olarak listenin başına oturur. post_run'da Session
kurulumu yükleme döngüsünden sonraya alındı: video_key dosyanın diskte
tam olmasını gerektiriyor."
```

---

### Task 4: `actions_taken` doldurma (§3.4)

**Files:**
- Modify: `gozcu/run.py` (`_on_close` ~205-220; yeni `_stamp_actions` yardımcısı)
- Test: `tests/test_run.py`

**Interfaces:**
- Consumes: `Episode.actions_taken` (Görev 2), `store.actions() -> list[ActionRecord]`
- Produces: `run._stamp_actions(store, episode) -> None` — Görev 8'in süpürmesi de çağırıyor

> **Neden `memory.py`'de DEĞİL.** Spec "gömme anında" diyor ve bu tam olarak o an; ama `embed_episode`'un ikinci parametresi bir `Store` de olabiliyor bir `QdrantClient` de (`memory._client()`'ın tutamak sözleşmesi). Depoyu orada aramak, testlerin çoğunun geçtiği dalda `store.actions()`'ın var olmadığı anlamına gelirdi. `run.py` elinde her zaman gerçek depoyla duruyor.

> `ActionRecord`'da `episode_id` **yok** (`models.py:215`); eşleme video zamanıyla yapılıyor.

- [ ] **Step 1: Kırmızı testi yaz**

`tests/test_run.py` sonuna:

```python
def test_the_episode_carries_the_field_calls_made_during_its_window():
    """Aksiyon defteri koşu kapsamlı SQLite'ta yaşıyor ve video bitince yok
    oluyor. Bu alan olmadan "geçen sefer ekip kaç dakikada geldi" YAPISAL
    olarak cevaplanamaz."""
    from gozcu.models import ActionRecord, Episode
    from gozcu.run import _stamp_actions
    from gozcu.store import Store

    store = Store(":memory:")
    episode = Episode(start_ts=10.0, end_ts=40.0, phase="outcome",
                      summary_tr="devrilme", preliminary_risk="Kritik")
    store.save_action(ActionRecord(
        ts=5.0, tool_name="site_alarm", actor="agent",
        params={}, result={"zone_id": "line_b"}))          # pencereden ÖNCE
    store.save_action(ActionRecord(
        ts=22.0, tool_name="dispatch_medical", actor="agent",
        params={"zone": "B-Hattı"},
        result={"team": "revir-1", "eta_minutes": 4}))      # pencere İÇİNDE
    store.save_action(ActionRecord(
        ts=99.0, tool_name="halt_production_line", actor="agent",
        params={}, result={"record_no": "KYT-9"}))          # pencereden SONRA

    _stamp_actions(store, episode)

    assert [a["tool"] for a in episode.actions_taken] == ["dispatch_medical"]
    assert episode.actions_taken[0]["eta_minutes"] == 4
    assert episode.actions_taken[0]["team"] == "revir-1"


def test_stamping_actions_on_an_episode_without_an_end_uses_its_start():
    from gozcu.models import Episode
    from gozcu.run import _stamp_actions
    from gozcu.store import Store
    episode = Episode(start_ts=10.0, phase="onset", summary_tr="x",
                      preliminary_risk="Düşük")
    _stamp_actions(Store(":memory:"), episode)
    assert episode.actions_taken == []
```

- [ ] **Step 2: Kırmızıyı gör**

Run: `uv run pytest tests/test_run.py -q -k "field_calls or stamping_actions"`
Expected: FAIL — `ImportError: cannot import name '_stamp_actions'`

- [ ] **Step 3: Yardımcıyı yaz ve `_on_close`'a bağla**

`gozcu/run.py`, `_on_close`'un **üstüne**:

```python
#: `ActionRecord.result`'tan arşive taşınan anahtarlar. Tamamını taşımak
#: precedent_line payload'ını mock araçların bütün iç alanlarıyla şişirirdi; bu dördü
#: operatörün gerçekten sorduğu şeyler ("kaç dakikada geldi", "hangi ekip",
#: "hangi bölge", "kayıt no").
_ACTION_RESULT_KEYS = ("team", "eta_minutes", "zone_id", "record_no")


def _stamp_actions(store, episode: Episode) -> None:
    """Epizodun zaman penceresine düşen saha çağrılarını epizoda yazar.

    `ActionRecord`'da `episode_id` YOK (`models.py:215`) — eşleme video
    zamanıyla yapılıyor. Pencere `[start_ts, end_ts]`; `end_ts` yoksa epizot
    henüz tek bir ana oturuyor ve aralık boş kalıyor.

    Ölçüldü: `dispatch_medical` gerçekten `{'team': 'revir-1',
    'eta_minutes': 4}` döndürüyor (`tools/field_systems.py`), ama o satır
    koşu kapsamlı SQLite'ta yaşıyor ve video bitince yok oluyor.
    """
    end_ts = episode.end_ts if episode.end_ts is not None else episode.start_ts
    taken = []
    for action in store.actions():
        if not episode.start_ts <= action.ts <= end_ts:
            continue
        row = {"tool": action.tool_name}
        row.update({key: action.result[key]
                    for key in _ACTION_RESULT_KEYS if key in action.result})
        taken.append(row)
    episode.actions_taken = taken
```

`_on_close` içinde, `embed_episode`'dan **önce**:

```python
def _on_close(gw, store, episode: Episode) -> None:
    ...
    _stamp_actions(store, episode)
    embed_episode(gw, store, episode)
    assess_risk(gw, store, episode)
```

- [ ] **Step 4: Yeşili gör**

Run: `uv run pytest tests/ -q`
Expected: 1041 passed, 1 xfailed

- [ ] **Step 5: Commit**

```bash
git add gozcu/run.py tests/test_run.py
git commit -m "feat(hafıza): epizot kendi saha çağrılarını arşive taşıyor

ActionRecord'da episode_id yok; eşleme video zamanıyla. run.py'de çünkü
embed_episode'un ikinci parametresi Store da olabiliyor QdrantClient de."
```

---

### Task 5: Arşiv yalnız Qdrant'ta yaşar — yükleyici ve ölü defter (§4)

**Files:**
- Modify: `gozcu/fixtures/loader.py` (`load_history` ~106-125)
- Modify: `gozcu/memory.py` (`_write_ledger` ~138-152 **SİL**; `embed_episode` içindeki çağrısı **SİL**)
- Modify: `gozcu/store.py` (`episode_embedding` tablosu ~21; `save_embedding` ~273; `embeddings` ~280 — üçü de **SİL**)
- Modify: `gozcu/fixtures/README.md` (satır ~62)
- Test: `tests/test_fixtures.py`, `tests/test_store.py`, `tests/test_memory.py`, `tests/test_kpi.py`

**Interfaces:**
- Consumes: `memory.embed_episode` (Görev 1-2), `Episode` köken alanları (Görev 2)
- Produces: `load_history(gw, store) -> int` — imzası **DEĞİŞMİYOR**, ama `store` artık bir depo değil `memory._client()`'ın **indeks anahtarı**

> **Tutamak kuralı — atlanırsa sessizce bozulur.** `store` hâlâ geçiliyor çünkü anahtarsız modda yerel istemciler tutamak başına bir `WeakKeyDictionary`'de tutuluyor (`memory.py:109`). Ölçüldü: `store_A` ile tohumlayıp `store_B` ile aramak → **0 sonuç**. Docstring'e yaz, yoksa biri "kullanılmayan parametre" diye siler.

- [ ] **Step 1: Silinecek testleri sil, alan kuralı taşıyanları YENİDEN KUR**

**Sil:** `tests/test_store.py:54` `test_embedding_roundtrips_and_replaces_by_episode_id` · `tests/test_memory.py:290` `test_a_store_handle_is_accepted_by_the_legacy_callers` · `tests/test_fixtures.py:156` `test_prior_incidents_are_loaded_closed_and_embedded` · `tests/test_fixtures.py:191` `test_a_second_call_embeds_what_the_degraded_tier_missed`

**Yeniden kur** — `tests/test_fixtures.py`'de bu ikisi bir **mekanizma** değil bir **alan kuralı** taşıyor, o yüzden silinmiyor; iddiaları Qdrant üzerinden kurulur. `:156`, `:166`, `:173`, `:181` bloklarını şununla değiştir:

```python
def _memory_client():
    """Süreç içi Qdrant — yükleyicinin yazdığı yer artık burası."""
    from qdrant_client import QdrantClient
    return QdrantClient(":memory:")


def _points(client):
    from gozcu.config import QDRANT_COLLECTION
    if not client.collection_exists(QDRANT_COLLECTION):
        return []
    return client.scroll(QDRANT_COLLECTION, limit=100, with_payload=True)[0]


def test_prior_incidents_are_embedded_and_never_touch_the_store():
    """Arşiv koşunun deposuna GİRMEZ: girdiği gün fikstürler `00:00`
    damgasıyla şartnamenin puanlanan `events[]` dizisine girer, `risk`
    yedeği kayar ve körlük itirafı ölür (spec §0)."""
    store, gw = Store(":memory:"), _gateway([0.1, 0.2, 0.3])
    client = _memory_client()
    n = load_history(gw, client)
    assert n >= 3
    assert len(_points(client)) == n
    assert store.episodes() == [], "arşiv depoya girmemeli"


def test_every_archive_point_carries_its_provenance():
    """Eşleme yapılmazsa üçü de `source=None` ile gömülür ve kaynak
    tekilleştirmesi üçünü TEK kovaya koyar — precedent_line listesine yalnız biri
    girer ve beat 5 hatasız kesilir (spec §4)."""
    client = _memory_client()
    load_history(_gateway([0.1]), client)
    sources = {p.payload["source"] for p in _points(client)}
    # Sabit `3` DEĞİL: Görev 13 dördüncü kaydı ekliyor ve sabit bir sayı o
    # gün sessizce kırılırdı. İddia "her kayıt KENDİ kaynağını taşıyor".
    expected = len(load_fixture("prior_incidents")["incidents"])
    assert len(sources) == expected, f"her kayıt kendi kaynağını taşımalı: {sources}"
    assert all(k.startswith("arşiv:") for k in sources)
    assert all(p.payload["occurred_at"] for p in _points(client))


def test_a_prior_incident_involves_the_same_vehicle_as_the_demo():
    """ALAN KURALI: demo aracının arşivde bir emsali olmak zorunda — §7'nin
    bütün precedent_line→araç zinciri (IST-04 → query_equipment_history → gecikmiş
    bakım) buna dayanıyor."""
    client = _memory_client()
    load_history(_gateway([0.1]), client)
    assert any("IST-04" in p.payload["participants"]
               or "IST-04" in p.payload.get("equipment_ids", [])
               for p in _points(client))


def test_loading_twice_does_not_duplicate_the_archive():
    """Tekrarsızlık kontrolü SİLİNDİ — kararlı kimlik `upsert`'ü zaten
    idempotent yapıyor. Sayı artık 0 değil 3 dönüyor: yükleyici "kaç kayıt
    arşivde" diyor, "kaç YENİ kayıt" değil."""
    client = _memory_client()
    n = load_history(_gateway([0.1]), client)
    assert load_history(_gateway([0.1]), client) == n
    assert len(_points(client)) == n


def test_a_degraded_embedding_tier_is_reported_as_zero_not_as_success():
    """ALAN KURALI — sessiz düşüş yasak: kademe bozuksa yükleyici yalan
    söylemez. Sayı doğrudan rozete gidiyor (`session.archive_count`)."""
    client = _memory_client()
    assert load_history(_gateway([]), client) == 0
    assert _points(client) == []


def test_a_blind_run_still_confesses_even_though_the_archive_is_seeded():
    """Körlük itirafı `if not episodes and perception.blind`'a bağlı
    (`report.py:176`). Arşiv depoya girseydi üç fikstür o koşulu ASLA
    tetiklemez ve kör bir koşu "kayda değer olay tespit edilmedi" derdi —
    bu bir gözlem iddiasıdır ve gözlem yapılmamıştır."""
    from gozcu.report import PerceptionHealth, build_output
    store, client = Store(":memory:"), _memory_client()
    load_history(_gateway([0.1]), client)

    blind_health = PerceptionHealth(frames=20, frames_with_detections=0)
    assert blind_health.blind
    output = build_output(store, "kayda değer olay tespit edilmedi",
                          perception=blind_health)
    assert output.summary == blind_health.blind_summary()
    assert output.events == [], "arşiv hayalet satır üretmemeli"
```

`tests/test_kpi.py:305` `test_no_episode_in_the_store_carries_an_epoch_timestamp` — iddia **korunur, taşınır**:

```python
def test_no_archive_episode_carries_an_epoch_timestamp():
    """`Episode.start_ts` VİDEO saniyesi. Arşiv fikstürleri bir zamanlar aynı
    sütunda epoch saniyesi (`1786567260.0`) taşıyordu; `mmss()` onu `99:59`'a
    yapıştırıyor ve rapor makul görünen yanlış bir saat basıyordu. Olayın
    takvim tarihi artık `occurred_at`'te.

    `load_history` depoya yazmadığı için iddia fikstür dosyasına taşındı.
    """
    from gozcu.fixtures.loader import load_fixture
    for incident in load_fixture("prior_incidents")["incidents"]:
        episode = incident["episode"]
        assert episode["start_ts"] < EPOCH_THRESHOLD_S
        assert (episode.get("end_ts") or 0.0) < EPOCH_THRESHOLD_S
        assert incident["occurred_at"], "takvim zamanı occurred_at'te yaşamalı"
```

- [ ] **Step 2: Kırmızıyı gör**

Run: `uv run pytest tests/test_fixtures.py tests/test_kpi.py -q`
Expected: FAIL — `KeyError: 'source'` ve `assert store.episodes() == []`

- [ ] **Step 3: Yükleyiciyi yeniden yaz**

`gozcu/fixtures/loader.py`:

```python
def load_history(gw, store) -> int:
    """Önceki olayları **Qdrant'a** gömer; gerçekten gömülen sayısı döner.

    **Epizotlar depoya GİRMİYOR.** Girdikleri gün dört şey birden bozuluyor
    (spec §0): fikstürler `00:00` damgasıyla şartnamenin puanlanan `events[]`
    dizisine giriyor, `risk` yedeği kayıyor (`levels = […] or
    [e.preliminary_risk …]`), `perception.blind` itirafı hiç tetiklenmiyor ve
    kök neden raporu kirleniyor. Arşiv, koşunun deposunun değil uzun süreli
    hafızanın kaydı.

    **`store` yine de geçiliyor ve SİLİNMEMELİ** — artık bir depo değil,
    `memory._client()`'ın **indeks anahtarı**. Anahtar tanımlı değilken yerel
    Qdrant istemcileri tutamak başına bir `WeakKeyDictionary`'de tutuluyor
    (`memory.py:109`); ölçüldü: `store_A` ile tohumlayıp `store_B` ile aramak
    **0 sonuç** veriyor.

    Kademe bozuksa sayı sıfır ve bu bir yalan değil: "3 olay yüklendi" demek,
    arama hiçbir şey bulamazken sistemin çalıştığını sanmak demektir.

    Tekrarsızlık kontrolü YOK: nokta kimliği `uuid5(source:id)` ve `upsert`
    idempotent. İkinci çağrı aynı noktaların üstüne yazar; dönen sayı "kaç
    kayıt arşivde", "kaç YENİ kayıt" değil.
    """
    payload = load_fixture("prior_incidents")
    stored = 0
    for index, record in enumerate(payload["incidents"]):
        fields = record["episode"]
        episode = Episode(
            **fields, state="closed",
            # Kaynak öneki bilerek okunur: canlı `video_key` 16 haneli hex,
            # arşiv kaydı bir olay kimliği. EMSAL kartının köken sütunu
            # (spec §7) ikisini ayırt edebilmeli.
            source=f"arşiv:{record['incident_id']}",
            # Takvim zamanı BURADA, `start_ts`'te değil: oraya epoch damgası
            # yazmak `kpi.epoch_scale_episodes`'ı düşürür.
            occurred_at=record["occurred_at"],
            equipment_ids=([record["equipment_id"]]
                           if record.get("equipment_id") else []))
        # Kimlik AÇIKÇA veriliyor: `embed_episode`'un `episode.id is None`
        # guard'ı yerinde kalıyor ve kaldırılmamalı — kaldırmak sessiz bir
        # çakışma açar.
        episode.id = index
        if embed_episode(gw, store, episode):
            stored += 1
        else:
            print(f"UYARI: fikstür gömülemedi — {episode.summary_tr}")
    return stored
```

- [ ] **Step 4: Ölü defteri sil**

- `gozcu/memory.py`: `_write_ledger` fonksiyonunu ve `embed_episode` içindeki `_write_ledger(client, episode.id, vector)` çağrısını sil.
- `gozcu/store.py`: `CREATE TABLE … episode_embedding …` satırını, `save_embedding` ve `embeddings` metotlarını sil.
- `gozcu/fixtures/README.md:62`: `load_history(gw, store)  # arşivi tohumlar` satırının yorumunu güncelle — *"arşivi Qdrant'a tohumlar; depoya hiçbir şey yazmaz"*.

- [ ] **Step 5: Ölü defterin başka okuyanı kalmadığını doğrula**

Run: `grep -rn "save_embedding\|embeddings()\|episode_embedding" gozcu tests benchmark scripts`

> **Kapsam `.` DEĞİL:** depoda üç worktree kopyası duruyor (`.claude/worktrees/*`) ve hepsi bu adları içeriyor — `-r .` asla sıfır satır dönmez.
Expected: sıfır satır

- [ ] **Step 6: Yeşili gör**

Run: `uv run pytest tests/ -q`
Expected: 1040 passed, 1 xfailed

- [ ] **Step 7: Commit**

```bash
git add gozcu/fixtures/loader.py gozcu/fixtures/README.md gozcu/memory.py gozcu/store.py tests/
git commit -m "feat(hafıza)!: arşiv yalnız Qdrant'ta yaşar, koşunun deposuna girmiyor

B1'in yan hasarı: load_history depoya yazsaydı fikstürler 00:00 damgasıyla
events[]'e girer, risk yedeği kayar (bu videonun gerçeği Düşük, teslim
edilen Yüksek), körlük itirafı ölür ve kök neden raporu kirlenirdi.

Fikstürler artık source/occurred_at/equipment_ids taşıyor — eşleme
olmadan üçü de source=None ile gömülür ve kaynak dedup'ı üçünü tek
kovaya koyar. episode_embedding tablosu, save_embedding, embeddings()
ve _write_ledger silindi (Görev 08'in işaretlediği 17/18 borcu)."
```

---

### Task 6: Tohumlamanın çağrılması — B1'in onarımı (§4)

**Files:**
- Modify: `gozcu/ui/server.py` (`post_run` ~800-835)
- Modify: `gozcu/ui/session.py` (`Session.__init__` — `archive_count`)
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `load_history(gw, store)` (Görev 5), `Session(source=…)` (Görev 3)
- Produces: `session.archive_count: int | None` — Görev 12'nin rozeti okuyor. **`None` "sıfır" DEĞİL, "henüz tohumlanmadı"**

> **B1 buymuş.** `load_history` bugüne kadar üretimde hiçbir yerden çağrılmadı — yalnız testlerden. Kod yazıldı, testleri geçti, canlı koşuda hiç devreye girmedi.

- [ ] **Step 1: Kırmızı testi yaz** ← **B1'in regresyon kilidi**

`tests/test_server.py` sonuna (dosyanın kendi `client` fixture'ını kullan):

```python
def test_starting_a_run_seeds_the_archive(client, monkeypatch, tmp_path):
    """B1'in REGRESYONU. Bu test olmadan tohumlama thread'i bir gün silinse
    bütün paket yeşil kalır ve arıza aynen geri gelir."""
    from gozcu.ui import server

    called_with = {}

    def fake_load_history(gw, store):
        called_with["store"] = store
        return 3

    monkeypatch.setattr(server, "load_history", fake_load_history)
    monkeypatch.setattr(server, "_work", lambda session, path: None)

    # Dosyayı `tmp_path`'e YAZIP aynı yolu POST etme: `client` fixture'ı
    # `server._output_dir_for`'u `tmp_path`'e yamalıyor (`test_server.py:83`),
    # yani sunucu aynı dosyanın üstüne yazar. Dosyanın kendi `_post_run`
    # yardımcısı (`:126`) bu yüzden bayt tuple'ı geçiyor — aynı deseni kullan.
    response = client.post(
        "/api/run", files={"video": ("klip.mp4", b"sahte mp4 icerigi",
                                     "video/mp4")})
    assert response.status_code == 200

    session = server._SESSION
    assert called_with.get("store") is session.store, (
        "tohumlama koşunun KENDİ tutamağıyla çağrılmalı — memory._client() "
        "anahtarsız modda yerel istemciyi tutamak başına açıyor")
    assert session.archive_count == 3


def test_a_fresh_session_reports_an_unknown_archive_count():
    """`None` "sıfır" DEĞİL, "henüz tohumlanmadı" — sıfır ile bilinmeyeni
    aynı şeye çevirmek `blind` itirafının onarmak için var olduğu hata."""
    from gozcu.ui.session import Session
    assert Session().archive_count is None
```

- [ ] **Step 2: Kırmızıyı gör**

Run: `uv run pytest tests/test_server.py -q -k "seeds_the_archive or unknown_archive_count"`
Expected: FAIL — `AttributeError: module 'gozcu.ui.server' has no attribute 'load_history'`

- [ ] **Step 3: Tohumlamayı bağla**

`gozcu/ui/session.py` — `Session.__init__` içine, `self.archived` satırının yanına:

```python
        #: Arşivde kaç kayıt var. **`None` "sıfır" DEĞİL**, "henüz
        #: tohumlanmadı" — rozet o durumda sayıyı hiç basmıyor.
        self.archive_count: int | None = None
```

`gozcu/ui/server.py` — üst tarafa `from gozcu.fixtures.loader import load_history` ve `_SEED_TIMEOUT_S` sabiti:

```python
#: Tohumlamanın boru hattını bekletebileceği en uzun süre. `QDRANT_TIMEOUT_S`
#: 600 saniye ve senkron bir çağrı arayüzü dakikalarca kilitlerdi; ayrı
#: thread + SINIRLI join. Süre dolarsa boru hattı yine başlar ve tohumlama
#: arkada sürer — örtüşmeyi `memory.py`'nin kilidi güvenli kılıyor.
_SEED_TIMEOUT_S = 20.0


def _seed_archive(session: Session) -> None:
    """Arşivi ayrı bir thread'de tohumlar; süre dolarsa koşu yine başlar.

    Bozuk bir fikstür JSON'u ya da erişilemez bir Qdrant bir koşuyu
    ÖLDÜRMEMELİ — sayı `None` kalır, rozet bunu söyler, koşu sürer.
    """
    def run_seed() -> None:
        try:
            session.archive_count = load_history(session.gw, session.store)
        except Exception:      # noqa: BLE001 — tohumlama bir koşuyu düşürmez
            session.archive_count = None

    thread = threading.Thread(target=run_seed, daemon=True)
    thread.start()
    thread.join(timeout=_SEED_TIMEOUT_S)
```

`post_run` içinde, Görev 3'ün eklediği `session = Session(source=…)` satırından sonra ve `thread.start()`'tan **önce**:

```python
        session.step_mode = bool(step_mode)
        # Boru hattı BAŞLAMADAN önce: analistin ilk precedent_line araması arşivi
        # dolu bulmalı. Sınırlı `join` — bkz. `_seed_archive`.
        _seed_archive(session)
        session.set_state("running")
```

- [ ] **Step 4: Yeşili gör**

Run: `uv run pytest tests/ -q`
Expected: 1042 passed, 1 xfailed

- [ ] **Step 5: Commit**

```bash
git add gozcu/ui/server.py gozcu/ui/session.py tests/test_server.py
git commit -m "fix(hafıza): B1 — arşiv tohumlaması üretimde hiç çağrılmıyordu

load_history bugüne kadar yalnız testlerden çağrıldı. Ayrı thread +
sınırlı join: QDRANT_TIMEOUT_S 600 sn ve senkron çağrı arayüzü
dakikalarca kilitlerdi. Regresyon testi eklendi — thread silinse
bütün paket yeşil kalırdı."
```

---

### Task 7: `archive` bayrağı — benchmark team37'ye yazmasın (§4)

**Files:**
- Modify: `gozcu/run.py` (`run_pipeline` imzası ~313-318; `_on_close` ~205; `synthesize` kapanışı ~426)
- Modify: `benchmark/run.py` (`run_pipeline` çağrısı ~142; `seeded` yorumu ~141)
- Modify: `tests/test_benchmark.py` (dört sahte `run_pipeline` imzası: `:152`, `:176`, `:189`, `:235`)
- Test: `tests/test_run.py`

**Interfaces:**
- Produces: `run_pipeline(video_path, store=None, gw=None, nobetci=None, on_message=None, output_dir=None, on_event=None, on_loop_ready=None, motion_for=None, archive=True)`

> Parametre imzanın **SONUNA** ekleniyor — bu dosyanın yerleşik geleneği (`motion_for` aynı gerekçeyle sonda, `run.py:318`): araya sokulan bir parametre konumsal çağrıları sessizce kaydırır.

> **Bayrak İKİ yola birden ulaşmalı:** koşu sonu süpürmesine (Görev 8) **ve** `_on_close`'un koşu ortasındaki gömmesine. Yalnız süpürmeyi kapatmak, kapanan her epizodun yine `team37`'ye yazılması demektir.

- [ ] **Step 1: Kırmızı testi yaz**

`tests/test_run.py` sonuna:

```python
def test_archive_false_writes_no_point_from_either_path(monkeypatch):
    """Ölçüm koşusu paylaşılan team37 koleksiyonuna yazmamalı: benchmark'ın
    epizotları gerçek bir olayın kaydı değil, bir ölçümün yan ürünü."""
    from gozcu import run as run_module

    written = []
    monkeypatch.setattr(run_module, "embed_episode",
                        lambda gw, store, episode: written.append(episode.id))

    # `tests/test_run.py`'nin GERÇEK yardımcıları: `_FakeGateway` (:65) ve
    # `_seed_episode(store, *, end_ts)` (:328). `_gw`/`_store`/
    # `_episode_fixture` diye bir şey YOK.
    store = Store(":memory:")
    episode = _seed_episode(store, end_ts=40.0)
    gw = _FakeGateway()

    run_module._on_close(gw, store, episode, archive=False)
    assert written == [], "_on_close arşivlememeli"

    run_module._sweep_unembedded(gw, store, [episode], archive=False)
    assert written == [], "süpürme arşivlememeli"
```

> `_sweep_unembedded` Görev 8'de geliyor; bu testin o yarısı Görev 8'e kadar
> `AttributeError` verir. **İki görevi de bitirmeden bu testi yeşil sayma** —
> ya da testi Görev 8'e ertele. Bu planın uygulayıcısı Görev 7 ve 8'i tek
> commit'te birleştirebilir; ayrı tutulmalarının sebebi inceleme kolaylığı.

- [ ] **Step 2: Kırmızıyı gör**

Run: `uv run pytest tests/test_run.py -q -k "archive_false"`
Expected: FAIL — `TypeError: _on_close() got an unexpected keyword argument 'archive'`

- [ ] **Step 3: Bayrağı geçir**

`gozcu/run.py`:

```python
def _on_close_traced(gw, store, episode: Episode, archive: bool = True) -> None:
    with trace.step("epizot.kapandı", f"id={episode.id} ts={episode.start_ts:.1f}s"):
        _on_close(gw, store, episode, archive=archive)


def _on_close(gw, store, episode: Episode, archive: bool = True) -> None:
    """..."""
    _stamp_actions(store, episode)
    if archive:
        embed_episode(gw, store, episode)
    assess_risk(gw, store, episode)
```

`run_pipeline` imzasının **sonuna** `archive: bool = True` ekle ve docstring'ine:

```
    `archive=False` bu koşunun hiçbir epizodunu Qdrant'a yazmaz — ölçüm
    koşusu (`benchmark/run.py`) böyle koşuyor: benchmark'ın epizotları
    gerçek bir olayın kaydı değil, ölçümün yan ürünü ve paylaşılan `team37`
    koleksiyonunu kirletirlerdi. Bayrak İKİ yola birden ulaşıyor —
    `_on_close`'un koşu ortasındaki gömmesi ve koşu sonu süpürmesi;
    yalnız birini kapatmak sızıntıyı kapatmaz.
```

`synthesize` kapanışını güncelle:

```python
                on_close=lambda episode: _on_close_traced(gw, store, episode,
                                                          archive=archive),
```

**`tests/test_benchmark.py`'nin DÖRT sahte imzası önce genişletilmeli** — yoksa `run_clip`'in geniş `except`'i `TypeError`'ı yutar, `record["error"]` dolar ve dört test birden düşer (`…measures_the_live_episode_not_the_archive`, `…crashing_clip_is_recorded`, `…epoch_timestamp_in_the_store_fails_the_clip`, `…payload_carries_the_clip_records`):

```python
# tests/test_benchmark.py:152
def run_pipeline(video_path, store=None, gw=None, archive=True):
# tests/test_benchmark.py:176 ve :235
def exploding(video_path, store=None, archive=True):
# tests/test_benchmark.py:189
def bad_pipeline(video_path, store=None, archive=True):
```

`benchmark/run.py` — `run_pipeline(str(data_dir / clip.video), store=store)` çağrısını `run_pipeline(str(data_dir / clip.video), store=store, archive=False)` yap ve `seeded` satırının yorumunu güncelle:

```python
        # `load_history` artık depoya yazmıyor (Görev 17/18) ve benchmark onu
        # zaten hiç çağırmıyordu: bu küme HER ZAMAN boş. `kpi.detections`'ın
        # `seeded_episode_ids` parametresi bu yüzden ölü — silinmiyor,
        # imza sözleşmesi ve gelecekte tohumlanan bir koşu için duruyor.
        seeded = {episode.id for episode in store.episodes()}
```

- [ ] **Step 4: Görev 8'i bitir, sonra yeşili gör** (aşağıya bak)

- [ ] **Step 5: Commit** — Görev 8 ile birlikte

---

### Task 8: Koşu sonu gömme süpürmesi — B2'nin onarımı (§5)

**Files:**
- Modify: `gozcu/run.py` (`_sweep_stale_risk`'in yanına yeni `_sweep_unembedded`; `run_pipeline` ~452)
- Test: `tests/test_run.py`

**Interfaces:**
- Consumes: `_stamp_actions` (Görev 4), `embed_episode` (Görev 1-2)
- Produces: `run._sweep_unembedded(gw, store, fresh, archive=True) -> None`

> **B2:** gömmenin tek yolu `_on_close` ve o da yalnız `close_episode` dalında (`on_close` çağrısı `synthesizer.py:338`; `loop.py:564` o dalın yönlendirmesi). Koşturularak ölçüldü: `open_episode` → çağrılmadı, `update_episode` → çağrılmadı, `close_episode` → çağrıldı. **Gerçek demo klibinde epizot videonun sonuna kadar açık kalıyor** — yani kaydedilen olay arşive HİÇ girmiyor. `_sweep_stale_risk` risk biçiyor, gömmüyor.

- [ ] **Step 1: Kırmızı testi yaz**

`tests/test_run.py` sonuna:

```python
def test_an_episode_still_open_at_the_end_of_the_run_is_archived(monkeypatch):
    """B2'nin REGRESYONU. Gömmenin tek yolu `_on_close`'du ve o da yalnız
    `close_episode` dalında koşuyor; gerçek demo klibinde epizot videonun
    sonuna kadar AÇIK kalıyor ve arşive hiç girmiyordu."""
    from gozcu import run as run_module
    from gozcu.models import Episode

    embedded = []
    monkeypatch.setattr(run_module, "embed_episode",
                        lambda gw, store, episode: embedded.append(episode.id))

    open_ep = Episode(id=1, start_ts=0.0, end_ts=99.0, phase="development",
                   summary_tr="istif aracı devrildi", preliminary_risk="Kritik",
                   state="open", source="9f2a")
    run_module._sweep_unembedded(_FakeGateway(), Store(":memory:"), [open_ep])
    assert embedded == [1], "AÇIK kalan epizot da arşivlenmeli"


def test_the_sweep_backfills_a_missing_source_but_never_overwrites_one():
    """`source` yedeği bir GERİ DOLDURMA, ana yol değil (§5). Damgalı bir
    epizodun kaynağını ezmek `catch_up` ile gelen bir epizodu yanlış videoya
    bağlayabilirdi."""
    from gozcu import run as run_module
    from gozcu.models import Episode
    unstamped = Episode(id=1, start_ts=0.0, phase="onset", summary_tr="x",
                       preliminary_risk="Düşük")
    stamped = Episode(id=2, start_ts=0.0, phase="onset", summary_tr="y",
                      preliminary_risk="Düşük", source="ESKİ")
    run_module._sweep_unembedded(_FakeGateway(), Store(":memory:"),
                                 [unstamped, stamped], source="YENİ")
    assert unstamped.source == "YENİ"
    assert stamped.source == "ESKİ"
```

- [ ] **Step 2: Kırmızıyı gör**

Run: `uv run pytest tests/test_run.py -q -k "still_open or backfills"`
Expected: FAIL — `AttributeError: module 'gozcu.run' has no attribute '_sweep_unembedded'`

- [ ] **Step 3: Süpürmeyi yaz**

`gozcu/run.py`, `_sweep_stale_risk`'in **hemen altına**:

```python
def _sweep_unembedded(gw, store, fresh: list[Episode],
                      source: str | None = None, archive: bool = True) -> None:
    """Koşu biterken HER taze epizodu arşive gömer — açık kalanlar dahil.

    **B2'nin onarımı.** Gömmenin tek yolu `_on_close`'du ve o da yalnız
    `close_episode` dalında koşuyor (`synthesizer.py:338`). Gerçek demo klibinde
    epizot videonun sonuna kadar açık kalıyor; yani kaydedilen olay arşive
    HİÇ girmiyordu ve "bu araçla daha önce sorun oldu mu?" sorusu her
    seferinde boş dönüyordu.

    **Risk süpürmesinden SONRA çağrılıyor.** Gerekçe `summary_tr` DEĞİL —
    `_sweep_stale_risk` özete hiç dokunmuyor, yalnız `assess_risk` çağırıyor
    (`run.py:289-300`) ve özet zaten döngü içinde `synthesize` tarafından son
    hâline getirilmiş oluyor. Gerçek gerekçe sıranın kendisi: `_on_close`
    yolunda gömme riskten ÖNCE geliyor, süpürme yolunda da aynı sırayı
    korumak iki yolun aynı epizot için aynı payload'ı üretmesini garanti
    ediyor. Ters sırada, açık kalan bir epizot `_on_close`'la kapananlardan
    farklı bir anda gömülür ve iki koşu karşılaştırılamaz hâle gelir.

    **Kapanmış/açık ayrımı yapılmıyor:** `embed_episode` idempotent ve
    istisna atmıyor, zaten gömülmüş epizot noktanın üstüne yazar.

    `source` bir GERİ DOLDURMA: yalnız damgasız epizotlara yazılıyor.
    Damgalı bir epizodun kaynağını ezmek, `catch_up` ile gelen bir epizodu
    yanlış videoya bağlayabilirdi.
    """
    if not archive:
        return
    for episode in fresh:
        if episode.source is None and source is not None:
            episode.source = source
        _stamp_actions(store, episode)
        embed_episode(gw, store, episode)
```

`run_pipeline` içinde, `_sweep_stale_risk`'ten **sonra**:

```python
        with trace.step("risk.kalanları-biç", f"{len(fresh)} epizot"):
            _sweep_stale_risk(gw, store, fresh)
        with trace.step("hafıza.kalanları-göm", f"{len(fresh)} epizot"):
            _sweep_unembedded(gw, store, fresh, source=source, archive=archive)
```

- [ ] **Step 4: Yeşili gör**

Run: `uv run pytest tests/ -q`
Expected: 1045 passed, 1 xfailed

- [ ] **Step 5: Bozulma tablosunu belgele**

`docs/05-decisions/decision-log.md`'ye ekle — **iki sessiz dal ekranda görünmüyor** ve bu bilerek kabul edildi:

- `embed_episode`, `summary_source == "fallback"` olan epizodu reddediyor (`memory.py:183`) — doğru karar, arıza metni emsal aramasını zehirler. Ama sentezin bozulduğu bir koşuda süpürme **hiçbir şey** arşivlemez.
- Süpürme genişletilmiş yolun `try` bloğunun içinde. O yol çökerse koşu geçerli çıktı verir ama **arşive hiçbir şey yazılmaz**.

- [ ] **Step 6: Commit** (Görev 7 ile birlikte)

```bash
git add gozcu/run.py benchmark/run.py tests/test_run.py docs/05-decisions/decision-log.md
git commit -m "fix(hafıza): B2 — kapanmayan epizot arşive hiç girmiyordu

Gömmenin tek yolu _on_close ve o da yalnız close_episode dalında.
Ölçüldü: open_episode→çağrılmadı, update_episode→çağrılmadı. Gerçek
demo klibinde epizot videonun sonuna kadar açık kalıyor. Süpürme risk
süpürmesinden SONRA: önce koşarsa arşive olayın erken hâli girer.

archive bayrağı iki yola birden ulaşıyor (_on_close + süpürme);
benchmark archive=False geçiyor."
```

---

### Task 9: Skorlu emsal + hesaplanan kimlikle dışlama (§6.1, §7)

**Files:**
- Modify: `gozcu/models.py` (yeni `Precedent`)
- Modify: `gozcu/memory.py` (`search_timeline` ~240-270)
- Modify: `gozcu/agents/risk.py` (~324)
- Modify: `gozcu/agents/supervisor.py` (`_internal_tool` ~339-341)
- Test: `tests/test_memory.py`, `tests/test_risk.py`, `tests/test_supervisor.py`

**Interfaces:**
- Consumes: `point_id` (Görev 1), `Episode.source` (Görev 2)
- Produces: `models.Precedent(episode: Episode, score: float)` · `search_timeline(gw, client, query, top_k=5, exclude: tuple[str | None, int] | None = None) -> list[Precedent]`

> **`exclude_id: int` → `exclude: tuple`.** Düz `must_not=[episode_id == X]` **iki noktanın ikisini birden** eler — farklı videoların epizotları da 1 numarayı taşıyor. Kimlik artık `source`'u içerdiği için hesaplanan UUID o tuzağa hiç girmiyor.

- [ ] **Step 1: Kırmızı testleri yaz**

`tests/test_memory.py`:

```python
def test_search_carries_the_score_with_each_precedent():
    """Skor jüriye görünen tek nicel işaret (EMSAL kartı) ve eşiğin ölçüldüğü
    şey. `query_points` onu zaten döndürüyordu; taşımıyorduk."""
    client, gw = _client(), Mock()
    gw.embed.side_effect = [_vec(1.0, 0.0), _vec(0.0, 1.0), _vec(1.0, 0.0)]
    _save(client, gw, "istif aracı devrildi", "personel mola verdi")

    found = search_timeline(gw, client, "araç devrilmesi")
    assert found[0].episode.summary_tr == "istif aracı devrildi"
    assert found[0].score > found[1].score
    assert 0.0 <= found[0].score <= 1.0


def test_exclusion_drops_only_the_episode_from_the_same_source():
    """Ölçülmüş tuzak: farklı videoların epizotları da 1 numarayı taşıyor;
    tamsayı kimliğe dayalı dışlama İKİSİNİ birden elerdi."""
    client, gw = _client(), Mock()
    gw.embed.side_effect = [_vec(1.0), _vec(1.0), _vec(1.0)]
    for source in ("videoA", "videoB"):
        episode = _ep("devrilme", episode_id=1)
        episode.source = source
        embed_episode(gw, client, episode)

    found = search_timeline(gw, client, "devrilme", exclude=("videoA", 1))
    assert [p.episode.source for p in found] == ["videoB"]


def test_an_open_episode_is_excluded_from_its_own_precedents():
    """`assess_risk` AÇIK epizot üzerinde koşuyor ve sorguyu tam gömülmüş
    metinle atıyor — süzülmezse epizot kendi emsali olarak listenin başına
    oturur."""
    client, gw = _client(), Mock()
    gw.embed.side_effect = [_vec(1.0), _vec(1.0)]
    open_ep = _ep("istif aracı devriliyor", episode_id=4)
    open_ep.source, open_ep.state = "9f2a", "open"
    embed_episode(gw, client, open_ep)

    found = search_timeline(gw, client, "istif aracı devriliyor",
                            exclude=("9f2a", 4))
    assert found == []
```

`tests/test_risk.py` — `_archive_patch` yardımcısı `Precedent` döndürmeli, yoksa `assess_risk` `AttributeError` atar (etrafında `try` yok):

```python
def _archive_patch(episodes=()):
    from gozcu.models import Precedent
    precedents = [e if isinstance(e, Precedent) else Precedent(episode=e, score=0.8)
                  for e in episodes]
    return patch("gozcu.agents.risk.search_timeline", return_value=precedents)
```

- [ ] **Step 2: Kırmızıyı gör**

Run: `uv run pytest tests/test_memory.py -q -k "score or exclusion or own_precedents"`
Expected: FAIL — `AttributeError: 'Episode' object has no attribute 'episode'`

- [ ] **Step 3: `Precedent` modelini ekle**

`gozcu/models.py`, `Episode`'un **altına**:

```python
class Precedent(Base):
    """Arşivden dönen bir precedent_line ve kosinüs skoru.

    Skor `query_points` yanıtında bugün de vardı ve atılıyordu. Taşınmasının
    üç tüketicisi var: eşik (`search_timeline`), EMSAL kartının nicel sütunu
    (`ui/feed.py`) ve kalibrasyon script'i. Model prozasına bağlı değil —
    jürinin gördüğü tek ölçülmüş sayı.
    """

    episode: Episode
    score: float
```

- [ ] **Step 4: `search_timeline`'ı skorlu ve yeni dışlamayla yaz**

`gozcu/memory.py`:

```python
def search_timeline(gw, client, query: str, top_k: int = 5,
                    exclude: tuple[str | None, int] | None = None
                    ) -> list[Precedent]:
    """Sorguya en yakın epizotlar, skorlarıyla, en alakalı önce.

    `exclude` bir **çift**: `(source, episode_id)`. Dışlamayı **Qdrant
    yapıyor**, Python değil — süzme sonradan yapılsaydı dışlanan epizot
    `top_k`'dan bir yer çalardı.

    Tek sayı yetmiyordu: farklı videoların epizotları da 1 numarayı taşıyor
    ve düz bir `episode_id` eşleşmesi **iki noktanın ikisini birden** elerdi
    (ölçüldü). Nokta kimliği artık `source`'u içerdiği için hesaplanan UUID
    tam olarak bir noktayı eliyor.

    Boş liste dört durumda döner: koleksiyon yok, arşiv boş, sorgu vektörü
    boş (arama anında kademe bozuk), Qdrant erişilemez. **Hiçbiri istisna
    atmaz.**
    """
    try:
        target = _client(client)
        if target is None or not target.collection_exists(QDRANT_COLLECTION):
            return []

        query_vector = list(gw.embed(query))
        if not query_vector:
            return []

        exclusion = None
        if exclude is not None:
            exclusion = Filter(
                must_not=[HasIdCondition(has_id=[point_id(*exclude)])])
        with _LOCK:
            response = target.query_points(
                QDRANT_COLLECTION, query=query_vector, limit=top_k,
                with_payload=True, query_filter=exclusion)
    except Exception:  # noqa: BLE001 — vektör veritabanının kesintisi bir
        # koşuyu düşürmemeli; arama sonuçsuz döner, system_line çalışmaya devam eder.
        return []

    found = []
    for point in response.points:
        episode = _episode(point)
        # Yedek özetli epizotlar TEK boğazda süzülüyor: sonucu iki ayrı
        # tüketici okuyor ve ikisi kendi başına süzse bir gün ayrışırlardı.
        if episode is not None and episode.summary_source != "fallback":
            found.append(Precedent(episode=episode, score=point.score))
    return found
```

> `_LOCK` Görev 10'da tanımlanıyor. Görev 9 ve 10 art arda uygulanıyor; ayrı tutulmalarının sebebi inceleme kolaylığı. Görev 9'u tek başına çalıştırmak istersen `with _LOCK:` satırını Görev 10'a ertele.

- [ ] **Step 5: İki tüketiciyi güncelle**

`gozcu/agents/risk.py` (~324):

```python
    history = (search_timeline(gw, store, query, exclude=(episode.source, episode.id))
               if query and episode.id is not None else [])
    history_text = "\n".join(f"- {p.episode.summary_tr}"
                             for p in history) or "- (kayıt yok)"
```

`gozcu/agents/supervisor.py` (`_internal_tool`, ~339):

```python
        if name == SEARCH_TIMELINE:
            # Kendi koşusunun AÇIK epizodu precedent_line değil: operatör "bu araçla
            # daha önce sorun oldu mu?" diye sorduğunda ŞU ANKİ olayın
            # kendisini geri almamalı. `self.source` (Görev 3) tam olarak
            # bunun için taşınıyor — dışlanmazsa alan ölü kalırdı.
            open_ep = self.store.open_episode()
            exclude = ((self.source, open_ep.id)
                       if open_ep is not None and open_ep.id is not None else None)
            found = search_timeline(self.gw, self.store, params["query"],
                                    exclude=exclude)
            # Tam `model_dump()` DEĞİL: `Episode` artık `beats` ve
            # `actions_taken` da taşıyor ve o yük doğrudan `self.history`'ye
            # girip her turda yeniden gönderilirdi — geçmiş budamasıyla
            # (spec §8.4) ters yönde. `participants` projeksiyonda KALIYOR:
            # arşiv kayıtlarında ekipman kimliğini bugün gerçekten taşıyan
            # alan o (`["IST-04", "PRS-001"]`).
            return {"results": [{"summary_tr": p.episode.summary_tr,
                                 "occurred_at": p.episode.occurred_at,
                                 "source": p.episode.source,
                                 "equipment_ids": p.episode.equipment_ids,
                                 "participants": p.episode.participants,
                                 "actions_taken": p.episode.actions_taken,
                                 "score": round(p.score, 3)}
                                for p in found]}
```

- [ ] **Step 6: Yeşili gör**

Run: `uv run pytest tests/ -q`
Expected: 1049 passed

| Test | Değişiklik |
|---|---|
| `test_memory.py:64` `…ranks_the_semantically_closest…` | `result[0].summary_tr` → `result[0].episode.summary_tr` |
| `test_memory.py:247` `…excludes_the_originating_episode` | `exclude_id=` → `exclude=(source, id)`; **Görev 1'in `xfail` işareti KALDIRILIR** |
| `test_memory.py:261` `…keeps_every_episode_when_no_exclusion` | `[e.id …]` → `[p.episode.id …]` |
| `test_memory.py:271` `…returns_episodes_rebuilt_from_the_payload` | `isinstance(found, Episode)` → `Precedent`; docstring'i ("çağıranlar değişmedi") artık yanlış |
| `test_memory.py:305` `…drops_fallback_sourced_episodes…` | `[e.id …]` → `[p.episode.id …]` |
| **Görev 2'nin `…before_the_new_fields_still_loads`'ı** | `[e.summary_tr …]` ve `found[0].source` → `p.episode.…` |
| `test_risk.py:104-116` `…consults_the_archive_and_excludes…` | `call_args.kwargs["exclude_id"]` → `["exclude"]`, çift bekle |
| `test_supervisor.py:505` `…reachable_as_a_tool` | Araç sonucu artık altı alanlık projeksiyon |

- [ ] **Step 7: Commit**

```bash
git add gozcu/models.py gozcu/memory.py gozcu/agents/risk.py gozcu/agents/supervisor.py tests/
git commit -m "feat(hafıza): emsal skorunu taşıyor, dışlama hesaplanan UUID ile

exclude artık (source, episode_id) çifti: düz episode_id eşleşmesi iki
noktanın ikisini birden eliyordu — farklı videoların epizotları da 1
numarayı taşıyor. Süpervizörün araç sonucu altı alanlık projeksiyon;
tam model_dump() beats+actions_taken'ı history'ye taşıyıp her turda
yeniden gönderirdi."
```

---

### Task 10: Eşik iskeleti, kaynak tekilleştirmesi, kilit (§6.2, §6.3)

**Files:**
- Modify: `gozcu/config.py` (Qdrant bloğunun sonu)
- Modify: `gozcu/memory.py` (`_LOCK`, `_DEDUP_OVERSAMPLE`, `search_timeline`, `_ensure_collection`, `embed_episode`)
- Modify: `.env.example`
- Test: `tests/test_memory.py`

**Interfaces:**
- Produces: `config.QDRANT_SCORE_THRESHOLD_RISK` · `config.QDRANT_SCORE_THRESHOLD_DIALOGUE` (**ikisi de `None`**) · `search_timeline(..., threshold: float | None = None)`

> **`0.0` bir "koruma yok" değeri DEĞİL.** Kosinüs negatif skor üretebilir; `0.0` negatifleri süzer — yani ölçülmemiş bir eşiktir. Korumasız hâl `None`'dır. Gerçek sayılar Görev 17'nin kalibrasyonundan gelecek.

> **Neden İKİ eşik:** `risk.py` arşivi bir **cümleyle** sorguluyor (`f"{summary_tr} {participants}"`), `supervisor.py` ise modelin yazdığı bir **soruyla**. Soru–cümle kosinüsü sistematik olarak cümle–cümle kosinüsünden düşük; tek eşik ya analisti kör eder ya beat 5'i keser.

- [ ] **Step 1: Kırmızı testleri yaz**

```python
def test_a_candidate_below_the_threshold_is_dropped():
    client, gw = _client(), Mock()
    gw.embed.side_effect = [_vec(1.0, 0.0), _vec(0.0, 1.0), _vec(1.0, 0.0)]
    _save(client, gw, "istif aracı devrildi", "kantinde kuyruk uzadı")

    hepsi = search_timeline(gw, client, "araç devrilmesi")
    assert len(unfiltered) == 2, "eşiksiz hâlde ikisi de dönmeli"

    gw.embed.side_effect = [_vec(1.0, 0.0)]
    filtered = search_timeline(gw, client, "araç devrilmesi", threshold=0.5)
    assert [p.episode.summary_tr for p in filtered] == ["istif aracı devrildi"]


def test_an_unset_threshold_is_none_not_a_zero_floor():
    """`0.0` negatif kosinüsleri süzer — yani ölçülmemiş bir eşiktir.
    Korumasız hâl `None`.

    İddia `_threshold`'ün KENDİSİNE kuruluyor, modül sabitinin o anki
    değerine değil: Görev 17 kalibre edilmiş sayıları varsayılan yapacak ve
    sabite bağlı bir test o gün sessizce kırılırdı.
    """
    from gozcu.config import _threshold
    assert _threshold("GOZCU_OLMAYAN_BIR_ANAHTAR") is None


def test_a_configured_threshold_parses_as_a_float(monkeypatch):
    from gozcu.config import _threshold
    monkeypatch.setenv("GOZCU_TEST_ESIK", "0.42")
    assert _threshold("GOZCU_TEST_ESIK") == 0.42


def test_the_same_source_appears_once_and_dedup_runs_before_the_cut():
    """B8: aynı videonun ikinci koşusu precedent_line listesini ikizliyordu. Dedup
    `top_k` kesilmeden ÖNCE — sonra yapılırsa ikizler gerçek emsallerin
    yerini çalar."""
    client, gw = _client(), Mock()
    gw.embed.side_effect = [_vec(1.0), _vec(1.0), _vec(0.9, 0.1), _vec(1.0)]
    for episode_id in (1, 2):
        repeat_ep = _ep("aynı klibin epizodu", episode_id=episode_id)
        repeat_ep.source = "prova"
        embed_episode(gw, client, repeat_ep)
    other_ep = _ep("başka videodaki devrilme", episode_id=1)
    other_ep.source = "gercek"
    embed_episode(gw, client, other_ep)

    found = search_timeline(gw, client, "devrilme", top_k=2)
    sources = [p.episode.source for p in found]
    assert sources.count("prova") == 1, "aynı kaynak listede bir kez"
    assert "gercek" in sources, "ikiz gerçek emsalin yerini çalmamalı"


def test_sourceless_points_are_not_collapsed_into_one_bucket():
    """`None` bir kaynak DEĞİL, kaynağın yokluğu. Bu değişiklikten önce
    yazılmış her nokta onu taşıyor; hepsini tek kovaya koymak arşivi tek
    emsale indirirdi — B8'i onarırken B4'ten beter bir şey."""
    client, gw = _client(), Mock()
    gw.embed.side_effect = [_vec(1.0), _vec(0.9, 0.1), _vec(1.0)]
    _save(client, gw, "birinci eski kayıt", "ikinci eski kayıt")  # ikisi de source=None

    found = search_timeline(gw, client, "kayıt")
    assert len(found) == 2, "kimliksiz noktalar birbirini yutmamalı"


def test_concurrent_read_and_write_lose_no_result():
    """B7'nin regresyonu. Ölçüldü: `ValueError: operands could not be
    broadcast together with shapes (32,) (31,)` — `search_timeline`'ın geniş
    `except`'i onu yutuyordu ve 400 sorgunun 6'sı sessizce `[]` dönüyordu."""
    import threading
    client, gw = _client(), Mock()
    gw.embed.return_value = _vec(1.0)
    seed_ep = _ep("ilk kayıt", episode_id=1)
    seed_ep.source = "a"
    embed_episode(gw, client, seed_ep)

    empty_results = []

    def writer(n):
        episode = _ep(f"kayıt {n}", episode_id=n)
        episode.source = "a"
        embed_episode(gw, client, episode)

    def reader():
        for _ in range(20):
            if not search_timeline(gw, client, "kayıt"):
                empty_results.append(1)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(2, 12)]
    threads.append(threading.Thread(target=reader))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert empty_results == [], "eş zamanlı yazma okumayı sessizce boşaltmamalı"
```

- [ ] **Step 2: Kırmızıyı gör**

Run: `uv run pytest tests/test_memory.py -q -k "threshold or same_source or concurrent"`
Expected: FAIL — `ImportError: cannot import name 'QDRANT_SCORE_THRESHOLD_RISK'`

- [ ] **Step 3: Yapılandırmayı ekle**

`gozcu/config.py`, Qdrant bloğunun sonuna:

```python
# Emsal alaka eşikleri. **İKİSİ DE `None` ve bu bilerek.**
#
# `0.0` bir "koruma yok" değeri DEĞİL: kosinüs negatif skor üretebilir ve
# `0.0` negatifleri süzer — yani ölçülmemiş bir eşiktir. Korumasız hâl
# `None`'dır ve gerçek sayılar `scripts/calibrate_memory.py`'nin üç sorgu
# ailesinden gelecek.
#
# **Neden iki tane:** risk analisti arşivi bir CÜMLEYLE sorguluyor
# (`agents/risk.py`: `f"{summary_tr} {participants}"`), süpervizör ise
# modelin yazdığı bir SORUYLA (`agents/supervisor.py`, SEARCH_TIMELINE).
# Soru–cümle kosinüsü sistematik olarak cümle–cümle kosinüsünden düşük;
# tek bir eşik ya analisti kör eder ya demo senaryosunun 5. beat'ini keser.
#
# Ölçülmüş arıza (B4): alakasız bir sorgu ("kantinde yemek kuyruğu uzadı")
# üç kaydın ÜÇÜNÜ de döndürdü — 0,743 / 0,557 / 0,371.
def _threshold(name: str) -> float | None:
    raw = os.environ.get(name, "").strip()
    return float(raw) if raw else None


QDRANT_SCORE_THRESHOLD_RISK = _threshold("GOZCU_QDRANT_SCORE_THRESHOLD_RISK")
QDRANT_SCORE_THRESHOLD_DIALOGUE = _threshold(
    "GOZCU_QDRANT_SCORE_THRESHOLD_DIALOGUE")
```

`.env.example`, Qdrant bloğunun sonuna (dosyanın kendi gerekçeli üslubuyla):

```
# Emsal alaka eşikleri — BOŞ bırakılırsa süzme yapılmaz.
# `0` yazma: kosinüs negatif olabilir ve `0` negatifleri süzer, yani
# ölçülmemiş bir eşiktir. Sayılar scripts/calibrate_memory.py'den gelir.
# İkisi ayrı çünkü risk analisti CÜMLEYLE, süpervizör SORUYLA sorguluyor.
GOZCU_QDRANT_SCORE_THRESHOLD_RISK=
GOZCU_QDRANT_SCORE_THRESHOLD_DIALOGUE=
```

- [ ] **Step 4: Kilit, dedup ve eşiği `memory.py`'ye ekle**

Modül sabitlerinin yanına:

```python
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
_LOCK = threading.Lock()

#: Dedup'tan önce kaç kat fazla aday çekiliyor. Kaynak tekilleştirmesi
#: `top_k` KESİLMEDEN önce çalışmak zorunda: sonra yapılırsa aynı kaynağın
#: ikizleri gerçek emsallerin yerini çalar (B8).
_DEDUP_OVERSAMPLE = 4
```

`search_timeline`'a `threshold: float | None = None` parametresi ekle; `query_points` çağrısını `limit=top_k * _DEDUP_OVERSAMPLE` yap ve dönüş bloğunu değiştir:

```python
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
```

`_ensure_collection`'ın **`collection_exists` + `create_collection`'ının ikisini birden** ve `embed_episode`'un `upsert`'ünü `with _LOCK:` altına al. `search_timeline`'ın `collection_exists` çağrısı da kilit altında olmalı — **kontrol ile sorgu arasındaki boşluk B7'nin tam olarak vurduğu yer** ve dışarıda bırakılırsa regresyon testi ara sıra kırmızı verir. `import threading` ekle.

> `_LOCK` **yeniden girişli değil (`Lock`, `RLock` değil)**: `_ensure_collection`'ı `embed_episode`'un kilidi ALTINDAN çağırma — kendi kendine kilitlenir. `_ensure_collection` kilidi kendi içinde alıyor ve `upsert` ondan SONRA, ayrı bir `with` bloğunda koşuyor.

- [ ] **Step 5: Eşikleri iki tüketiciye bağla**

`gozcu/agents/risk.py`: `search_timeline(..., threshold=QDRANT_SCORE_THRESHOLD_RISK)`
`gozcu/agents/supervisor.py`: `search_timeline(..., threshold=QDRANT_SCORE_THRESHOLD_DIALOGUE)`

- [ ] **Step 6: Yeşili gör**

Run: `uv run pytest tests/ -q`
Expected: 1055 passed

- [ ] **Step 7: Commit**

```bash
git add gozcu/config.py gozcu/memory.py gozcu/agents/ .env.example tests/test_memory.py
git commit -m "feat(hafıza): eşik iskeleti (None), kaynak dedup'ı, koşulsuz kilit

B4: alakasız sorgu üç kaydın üçünü de döndürüyordu. Eşikler None —
0.0 negatif kosinüsleri süzer, yani ölçülmemiş bir eşiktir. Sayılar
kalibrasyondan gelecek. İki eşik: risk CÜMLEYLE, süpervizör SORUYLA
sorguluyor ve soru-cümle kosinüsü sistematik olarak düşük.

B8: dedup top_k kesilmeden ÖNCE, yoksa ikizler gerçek emsalin yerini
çalar. B7: kilit koşulsuz — 'yalnız yerel' predikatı hesaplanamıyor."
```

---

### Task 11: `RiskAssessment.precedents` + yükseltme cümlesi + prompt kuralları (§7)

**Files:**
- Modify: `gozcu/models.py` (`RiskAssessment` ~191)
- Modify: `gozcu/agents/risk.py` (`assess_risk` kaydetme dalı; `SYSTEM_PROMPT`)
- Modify: `gozcu/agents/supervisor.py` (`escalate` `[SİSTEM]` satırı ~515-520)
- Test: `tests/test_risk.py`, `tests/test_supervisor.py`, `tests/test_report.py`

**Interfaces:**
- Consumes: `Precedent` (Görev 9)
- Produces: `RiskAssessment.precedents: list[Precedent]` — Görev 12'nin EMSAL kartı okuyor

> **Yeni tablo ya da `build_output` değişikliği GEREKMİYOR:** `Detail` teslim anında depodan yeniden kuruluyor (`report.py:192-200`), alan `detail.risk_assessments` içinde kendiliğinden teslim edilir.

- [ ] **Step 1: Kırmızı testleri yaz**

```python
# tests/test_risk.py
def test_the_assessment_records_the_precedents_it_consulted():
    """Emsal yalnız prompt'a giriyordu ve jüri prompt görmez (B6)."""
    from gozcu.models import Episode, Precedent
    past = Precedent(
        episode=Episode(id=9, start_ts=0.0, phase="outcome",
                        summary_tr="IST-04 fren mesafesi uzadı",
                        preliminary_risk="Orta", source="arşiv:OLY-2026-0812",
                        occurred_at="2026-08-12T23:41:00+03:00",
                        equipment_ids=["IST-04"]),
        score=0.71)
    # `tests/test_risk.py`'nin GERÇEK yardımcıları: `_gw(content=RESPONSE_JSON)`
    # (:48) ve `_ep(store, participants=…)` (:30). `_gw_with_assessment`/
    # `_store`/`_episode` diye bir şey YOK.
    store = Store(":memory:")
    with _archive_patch([past]):
        assessment = assess_risk(_gw(), store, _ep(store))
    assert [p.episode.summary_tr for p in assessment.precedents] == [
        "IST-04 fren mesafesi uzadı"]
    assert assessment.precedents[0].score == 0.71


def test_an_assessment_without_precedents_records_an_empty_list():
    store = Store(":memory:")
    with _archive_patch([]):
        assessment = assess_risk(_gw(), store, _ep(store))
    assert assessment.precedents == []


# tests/test_report.py
def test_precedents_reach_the_delivered_detail():
    """`Detail` teslim anında depodan yeniden kuruluyor — yeni tablo yok."""
    from gozcu.models import Precedent, RiskAssessment
    store = Store(":memory:")
    episode = Episode(start_ts=10.0, end_ts=40.0, phase="outcome",
                      summary_tr="istif aracı devrildi",
                      preliminary_risk="Kritik")
    episode.id = store.create_episode(episode)
    past = Episode(id=9, start_ts=0.0, phase="outcome",
                     summary_tr="IST-04 fren mesafesi uzadı",
                     preliminary_risk="Orta", source="arşiv:OLY-2026-0812",
                     occurred_at="2026-08-12T23:41:00+03:00")
    store.save_risk(RiskAssessment(
        episode_id=episode.id, ts=20.0, level="Kritik",
        rationale_tr="devrilme gerçekleşti", preventable=True,
        precedents=[Precedent(episode=past, score=0.71)]))

    output = build_output(store, "özet")
    emsaller = output.detail.risk_assessments[0].precedents
    assert emsaller[0].episode.summary_tr == "IST-04 fren mesafesi uzadı"
    assert emsaller[0].score == 0.71


# tests/test_supervisor.py
def test_the_escalation_opening_names_the_precedent_when_there_is_one():
    """Jürinin izlediği ilk an burası. Cümle DETERMİNİSTİK — model
    prozasına bağlı değil."""
    from gozcu.models import Precedent
    gw, store, e = _setup([Response(content="KRİTİK: yerde hareketsiz kişi.")])
    past = Episode(id=9, start_ts=0.0, phase="outcome",
                     summary_tr="IST-04 fren mesafesi uzadı",
                     preliminary_risk="Orta", source="arşiv:OLY-2026-0812",
                     occurred_at="2026-08-12T23:41:00+03:00")
    with_precedent = RiskAssessment(episode_id=e.id, level="Kritik",
                             rationale_tr="g", preventable=True,
                             precedents=[Precedent(episode=past, score=0.71)])
    nobetci = Supervisor(gw, store)
    with patch("gozcu.agents.supervisor.assess_risk", return_value=with_precedent), \
         patch("gozcu.agents.supervisor.screen_text",
               return_value=_screening()):
        nobetci.escalate(e)

    system_line = next(m["content"] for m in reversed(nobetci.history)
                  if m["role"] == "user" and "[SİSTEM]" in str(m["content"]))
    assert "IST-04 fren mesafesi uzadı" in system_line
    assert "2026-08-12" in system_line


def test_the_escalation_opening_stays_silent_without_precedents():
    """Uydurma precedent_line yok: precedent_line yoksa cümle HİÇ basılmaz."""
    gw, store, e = _setup([Response(content="KRİTİK: yerde hareketsiz kişi.")])
    nobetci = Supervisor(gw, store)
    with patch("gozcu.agents.supervisor.assess_risk", return_value=_risk(e)), \
         patch("gozcu.agents.supervisor.screen_text",
               return_value=_screening()):
        nobetci.escalate(e)

    system_line = next(m["content"] for m in reversed(nobetci.history)
                  if m["role"] == "user" and "[SİSTEM]" in str(m["content"]))
    assert "Arşivde" not in system_line
```

- [ ] **Step 2: Kırmızıyı gör**

Run: `uv run pytest tests/test_risk.py -q -k "precedents"`
Expected: FAIL — `ValidationError: Extra inputs are not permitted`

- [ ] **Step 3: Alanı ve cümleyi ekle**

`gozcu/models.py`, `RiskAssessment` içine:

```python
    #: Bu değerlendirmede gerçekten danışılmış arşiv kayıtları, skorlarıyla.
    #: Emsal eskiden YALNIZ prompt'a giriyordu ve jüri prompt görmez (B6).
    #: Yeni tablo gerekmiyor: `Detail` teslim anında depodan yeniden
    #: kuruluyor (`report.py:192`) ve alan `detail.risk_assessments` içinde
    #: kendiliğinden teslim ediliyor.
    precedents: list[Precedent] = Field(default_factory=list)
```

`gozcu/agents/risk.py` — `RiskAssessment(...)` kurulumuna `precedents=history` ekle.

`gozcu/agents/risk.py`, `SYSTEM_PROMPT`'a arşiv kuralları (Türkçe, §7):

```
ARŞİV KAYITLARI hakkında:
- Bir arşiv kaydı bir GEREKÇE değil, gerekçenin başlangıcıdır.
- Kayıt bir ekipman kimliği taşıyorsa `query_equipment_history` ile o
  ekipmanın geçmişini sorgula.
- Aynı ekipman ya da bölge tekrar ediyorsa bu bir ÖRÜNTÜDÜR; hangi kaydı
  gördüğünü yaz.
- Arşiv kaydı bu olayla ilgisizse KULLANMA ve ondan söz etme.
- Kamera ekipman kimliği OKUMAZ. Arşivdeki kaydın sahnedeki araca ait
  olduğunu VARSAYMA; "saha doğrulaması gerekir" biçiminde yaz.
```

`gozcu/agents/supervisor.py`, `escalate`'in `[SİSTEM]` satırına:

```python
        # Emsal cümlesi DETERMİNİSTİK ve model prozasına bağlı değil:
        # jürinin izlediği ilk an burası. Emsal yoksa satır HİÇ basılmıyor —
        # uydurma precedent_line yok.
        precedent_line = ""
        if risk.precedents:
            closest = risk.precedents[0].episode
            when = (closest.occurred_at or "")[:10]
            precedent_line = (f" Arşivde benzer kayıt var"
                     f"{f' ({when})' if when else ''}: "
                     f"{closest.summary_tr}")
        self.history.append({
            "role": "user",
            "content": f"[SİSTEM] {mmss(self.ts)} — {headline} "
                       f"Olay kimliği (episode_id): {episode.id}. "
                       f"Risk: {risk.level}.{precedent_line} "
                       ...})
```

- [ ] **Step 4: Yeşili gör**

Run: `uv run pytest tests/ -q`
Expected: 1060 passed

- [ ] **Step 5: Commit**

```bash
git add gozcu/models.py gozcu/agents/risk.py gozcu/agents/supervisor.py tests/
git commit -m "feat(hafıza): B6 — emsal artık teslim JSON'unda ve yükseltme açılışında

Emsal yalnız prompt'a giriyordu; jüri prompt görmez. precedents
detail.risk_assessments içinde kendiliğinden teslim ediliyor — Detail
teslim anında depodan yeniden kuruluyor, yeni tablo yok. Yükseltme
cümlesi deterministik; emsal yoksa hiç basılmıyor."
```

---

### Task 12: EMSAL kartı ve arşiv rozeti (§7)

**Files:**
- Modify: `gozcu/ui/feed.py` (`CARD_*` sabitleri ~192; `intervention_card` ~254)
- Modify: `gozcu/ui/view.py` (`badges` ~127-141)
- Modify: `gozcu/ui/server.py` (`get_status` ~365-388; `_snapshot` ~889)
- Modify: `gozcu/ui/web/js/sse.js` (~258, ~422)
- Test: `tests/test_feed.py`, `tests/test_view.py`, `tests/test_server.py`

**Interfaces:**
- Consumes: `RiskAssessment.precedents` (Görev 11), `session.archive_count` (Görev 6)
- Produces: `view.badges(gw, store, archive=None) -> dict` — `archive` anahtarı **yalnız `archive is not None` iken** sözlükte

> `tests/test_view.py:139` `assert result == {…}` **tam sözlük eşitliği** kuruyor. `archive`'ı koşulsuz eklemek onu kırar — ve `None` "sıfır" değil "henüz tohumlanmadı" demek olduğu için koşullu ekleme zaten doğru davranış.

- [ ] **Step 1: Kırmızı testleri yaz**

**`tests/test_feed.py`'nin GERÇEK yardımcıları `_card_episode(...)` (:710) ve `_card_risk(...)` (:718)** — `_episode`/`_risk` diye bir şey YOK. Emsalli varyant için yeni bir yardımcı gerekiyor; onu da yaz:

```python
# tests/test_feed.py — yeni yardımcı, `_card_risk`'in yanına
def _card_risk_with_precedent(score=0.71):
    risk = _card_risk()
    risk.precedents = [Precedent(
        episode=Episode(id=9, start_ts=0.0, phase="outcome",
                        summary_tr="IST-04 fren mesafesi uzadı",
                        preliminary_risk="Orta",
                        source="arşiv:OLY-2026-0812",
                        occurred_at="2026-08-12T23:41:00+03:00"),
        score=score)]
    return risk


def test_the_card_shows_the_precedent_with_its_origin_date_and_score():
    """Jüri prompt görmez; precedent_line EKRANDA görünmeli (B6)."""
    card = intervention_card(_card_episode(), _card_risk_with_precedent(),
                             [], "mesaj")
    assert "EMSAL" in card
    assert "IST-04 fren mesafesi uzadı" in card
    assert "2026-08-12" in card
    assert "0,71" in card, "Türkçe ondalık virgül (feed.format_confidence kuralı)"
    assert "0.71" not in card


def test_the_card_prints_no_precedent_row_when_there_is_none():
    """Uydurma precedent_line yok: satır HİÇ basılmaz."""
    assert "EMSAL" not in intervention_card(_card_episode(), _card_risk(),
                                           [], "mesaj")


# tests/test_view.py
def test_the_badges_omit_the_archive_count_until_seeding_has_run():
    """`None` "sıfır" DEĞİL, "henüz tohumlanmadı"."""
    assert "archive" not in view.badges(_FakeGateway(), Store(":memory:"))


def test_the_badges_report_a_zero_archive_as_zero():
    """Tohumlama sessizce başarısız olduysa tek uyarı bu."""
    sonuc = view.badges(_FakeGateway(), Store(":memory:"), archive=0)
    assert sonuc["archive"] == 0
```

- [ ] **Step 2: Kırmızıyı gör**

Run: `uv run pytest tests/test_feed.py tests/test_view.py -q -k "precedent or archive"`
Expected: FAIL — `assert "EMSAL" in kart`

- [ ] **Step 3: Kartı ve rozeti yaz**

`gozcu/ui/feed.py`, `CARD_WHY`'ın yanına `CARD_PRECEDENT = "EMSAL"`; `intervention_card` içinde `CARD_WHY` satırından **sonra**:

```python
    # Emsal satırı DETERMİNİSTİK — model prozasından değil, arşivin
    # kendisinden geliyor. Emsal yoksa satır HİÇ basılmıyor: boş bir
    # "EMSAL —" satırı "arşivde kayıt yok" ile "arşive bakılmadı"yı aynı
    # şeye çevirirdi.
    # `getattr` fallback'i YOK: `RiskAssessment.precedents` varsayılanlı bir
    # alan ve her zaman var. Ölü bir dal, çalıştığı sanılan bir daldır.
    precedents = risk.precedents if risk else []
    if precedents:
        lines = []
        for precedent in precedents:
            past = precedent.episode
            when = (past.occurred_at or "")[:10]
            koken = past.source or "—"
            lines.append(
                f"{html.escape(past.summary_tr)} "
                f"<span style='opacity:.7'>· {html.escape(when)} "
                f"· {html.escape(origin)} · benzerlik "
                # Türkçe ondalık VİRGÜL — `feed.format_confidence` (feed.py:114)
                # aynı kuralı "TEK biçimlendirme yeri" diye ilan ediyor ve
                # ikinci bir biçim bir gün ondan ayrışır.
                + f"{precedent.score:.2f}".replace(".", ",") + "</span>")
        rows.append(_card_row(CARD_PRECEDENT, "<br>".join(lines)))
```

`gozcu/ui/view.py`:

```python
def badges(gw, store, archive: int | None = None) -> dict:
    """Üç rozet + varsa arşiv kayıt sayısı.

    `archive is None` **"sıfır" DEĞİL, "henüz tohumlanmadı"** — anahtar o
    durumda sözlüğe hiç girmiyor. Sıfır ile bilinmeyeni aynı şeye çevirmek,
    `perception.blind` itirafının onarmak için var olduğu hatanın aynısı.
    """
    sonuc = {"gateway": "degraded" if gw.is_degraded() else "healthy",
             "memory": memory_backend(),
             "run": run_status(store)}
    if archive is not None:
        sonuc["archive"] = archive
    return sonuc
```

`gozcu/ui/server.py` — `_snapshot`: `view.badges(session.gw, session.store, archive=session.archive_count)`.
`get_status` **gövdesine** de ekle (o uç `memory`'yi `badges()`'ten değil doğrudan okuyor):

```python
        "archive": _SESSION.archive_count if _SESSION is not None else None,
```

`gozcu/ui/web/js/sse.js` — **birleşik bir dize GEÇME.** `setBadge` (`:207-215`) `rawValue`'yu iki yere birden veriyor: `el.dataset.state` (CSS renk seçicisi `[data-state="qdrant"]`) ve `badgeLabelFor(rawValue)` (Türkçe etiket sözlüğü). `"qdrant · 4"` geçmek ikisini birden düşürür — rozet rengini kaybeder ve ham dize ekrana basılır. Bunun yerine **dördüncü, isteğe bağlı bir `suffix` parametresi**:

```js
function setBadge(el, valueEl, rawValue, suffix) {
  // `rawValue` teldeki HAM enum ve HAM KALIYOR: CSS renk seçicisi
  // (`[data-state="..."]`) ve `badge_labels` sözlüğü ikisi de onu okuyor.
  // `suffix` yalnız EKRANDAKİ metne ekleniyor — birleşik bir `rawValue`
  // hem rengi hem Türkçe etiketi düşürürdü.
  el.dataset.state = rawValue || "";
  valueEl.textContent = badgeLabelFor(rawValue)
    + (suffix === null || suffix === undefined ? "" : ` · arşiv ${suffix}`);
}
```

İki çağrı (`:258`, `:422`) `status.archive` / `state.badges.archive` geçer. Sayı yoksa (`undefined`) ek **hiç basılmaz** — "henüz tohumlanmadı" ile "sıfır" aynı şey değil.

- [ ] **Step 4: Yeşili gör**

Run: `uv run pytest tests/ -q`
Expected: 1064 passed

- [ ] **Step 5: Commit**

```bash
git add gozcu/ui/ tests/
git commit -m "feat(konsol): EMSAL kartı ve arşiv rozeti — hafıza ekranda görünüyor

B6: emsal yalnız prompt'a giriyordu. Kart satırı deterministik (köken,
tarih, skor); emsal yoksa hiç basılmıyor. Rozet archive=None iken sayıyı
hiç basmıyor — 'henüz tohumlanmadı' ile 'sıfır' aynı şey değil."
```

---

### Task 13: Fikstür tutarlılığı — IST-04'ün bağlanmamış arıza kaydını terfi ettir (§7)

**Files:**
- Modify: `gozcu/fixtures/prior_incidents.json`
- Modify: `gozcu/fixtures/equipment.json` (IST-04 `fault_records[1].incident_id`)
- Test: `tests/test_fixtures.py`

**Interfaces:**
- Produces: `prior_incidents.json` dördüncü kayıt — `OLY-2026-0419`

> **Anlatılan örüntü GERÇEK olmalı — şartname §16, jüriyi yanıltıcı bilgi.** Bugün IST-04 arşivde **tek** kayıtta geçiyor; "IST-04 iki kez" diyen bir anlatı uydurma olurdu. Doğru hamle üçüncü bir olay uydurmak değil: `equipment.json`'da IST-04 için `incident_id: null` taşıyan **bağlanmamış** bir arıza kaydı zaten duruyor. **DÖRDÜNCÜ BİR OLAY UYDURULMAZ.**

- [ ] **Step 1: Kırmızı testi yaz**

```python
def test_no_fault_record_is_left_unlinked_to_the_archive():
    """İki fikstür dosyası birbirinden ayrışmasın: arıza defterinde duran
    ama arşivde karşılığı olmayan bir kayıt, precedent_line anlatısını yarım bırakır."""
    faults = load_fixture("equipment")["equipment"]["IST-04"]["fault_records"]
    arsiv = {i["incident_id"] for i in load_fixture("prior_incidents")["incidents"]}
    for fault in faults:
        assert fault["incident_id"], f"bağlanmamış arıza kaydı: {fault['date']}"
        assert fault["incident_id"] in arsiv


def test_the_archive_shows_ist04_as_a_repeated_brake_problem():
    """§7'nin precedent_line→araç zinciri buna dayanıyor: örüntü İKİ gerçek kayıttan
    doğuyor, uydurulmuş bir üçüncüden değil."""
    records = [i for i in load_fixture("prior_incidents")["incidents"]
                if i["equipment_id"] == "IST-04"]
    assert len(records) == 2
    assert all("fren" in i["episode"]["summary_tr"].lower() for i in records)
```

- [ ] **Step 2: Kırmızıyı gör**

Run: `uv run pytest tests/test_fixtures.py -q -k "unlinked or repeated_brake"`
Expected: FAIL — `bağlanmamış arıza kaydı: 2026-04-19`

- [ ] **Step 3: Kaydı terfi ettir**

`gozcu/fixtures/prior_incidents.json`'a **`OLY-2026-0812`'den önce** (tarih sırası korunuyor) ekle.

> **`summary_tr` kaynak cümlenin DIŞINA çıkmıyor.** `equipment.json`'daki kayıt tam olarak şunu diyor: *"Fren pedalı sertleşti; bakım talebi açıldı, iş emri kapanmadı."* Yer (B-Hattı), tarih ve araç kimliği kaydın kendi alanlarından türetilebilir; **ama fiil türetilemez.** İlk taslak "Operatör aracı hat kenarına çekti" diye bir cümle ekliyordu — kaynakta böyle bir şey yok ve spec §7 terfiyi açıkça *"yeni bir olay uydurulmuyor, var olan kayıt arşive taşınıyor"* diye çerçeveliyor. Şartname §16: jüriyi yanıltıcı bilgi.

```json
    {
      "incident_id": "OLY-2026-0419",
      "date": "2026-04-19",
      "occurred_at": "2026-04-19T10:05:00+03:00",
      "zone_id": "line_b_shipping",
      "line_id": "B",
      "shift_id": "day",
      "equipment_id": "IST-04",
      "equipment_fault": true,
      "episode": {
        "start_ts": 0.0,
        "end_ts": 18.0,
        "phase": "outcome",
        "preliminary_risk": "Orta",
        "participants": ["IST-04", "PRS-005"],
        "summary_tr": "19 Nisan'da B-Hattı sevkiyat alanında IST-04 istif aracının fren pedalı sertleşti. Bakım talebi açıldı, iş emri kapanmadı."
      }
    }
```

`gozcu/fixtures/equipment.json`, IST-04'ün 2026-04-19 tarihli arıza kaydında `"incident_id": null` → `"incident_id": "OLY-2026-0419"`.

- [ ] **Step 4: Yeşili gör**

Run: `uv run pytest tests/ -q`
Expected: 1066 passed

- [ ] **Step 5: Commit**

```bash
git add gozcu/fixtures/ tests/test_fixtures.py
git commit -m "fix(fikstür): IST-04'ün bağlanmamış arıza kaydı arşive terfi etti

equipment.json'da incident_id: null taşıyan 2026-04-19 kaydı arşivde
karşılığı olmadan duruyordu. Örüntü artık İKİ GERÇEK kayıttan doğuyor —
üçüncü bir olay UYDURULMADI (şartname §16)."
```

---

### Task 14: `RunMemory` — koşu içi kısa süreli hafıza (§8)

**Files:**
- Create: `gozcu/recall.py`
- Create: `tests/test_recall.py`
- Modify: `gozcu/config.py` (`RECALL_WINDOW_N`, `RECALL_VISION`)
- Modify: `.env.example`

**Interfaces:**
- Produces: `recall.RunMemory()` · `.note(ts, moment, participants, decision, severity)` · `.recent(n=None) -> list[WindowNote]` · `.render(n=None) -> str`. Görev 15, 16, 17 tüketiyor.

> **Ajansız ve modelsiz.** `RunMemory` saf veri yapısı: model çağırmıyor, ağa çıkmıyor, `DecisionLoop`'a bağımlı değil. `run.py`'deki kapanışlar onu besliyor.

- [ ] **Step 1: Kırmızı testleri yaz**

`tests/test_recall.py` (yeni dosya):

```python
"""Koşu içi kısa süreli hafıza — Aşama 6.

Görü katmanı her pencereye SIFIRDAN bakıyor: 2. dakikadaki dengesizlik,
5. dakikadaki devrilmenin bağlamı olamıyor. `RunMemory` o bağlamı taşıyor.
"""

from gozcu.models import SEVERITY_LEVELS
from gozcu.recall import RunMemory


def _dolu(memory, n, severity="rutin"):
    for index in range(n):
        memory.note(ts=float(index * 10), moment=f"pencere {index}",
                    participants=["forklift"], decision="ignore",
                    severity=severity)


def test_routine_windows_scroll_out_of_the_recent_view():
    memory = RunMemory(limit=3)
    _dolu(memory, 6)
    assert [n.moment for n in memory.recent()] == [
        "pencere 3", "pencere 4", "pencere 5"]


def test_an_incident_window_is_never_dropped():
    """Sınır HİYERARŞİK: son N pencere tam detay + `severity == "olay"` olan
    HER pencere kalıcı. Olay asla düşmez, rutin pencereler kayar."""
    memory = RunMemory(limit=2)
    memory.note(ts=0.0, moment="istif aracı dengesini kaybetti",
                participants=["forklift"], decision="open_episode",
                severity="olay")
    _dolu(memory, 5)
    moments = [n.moment for n in memory.recent()]
    assert "istif aracı dengesini kaybetti" in moments
    assert moments[-1] == "pencere 4", "rutin pencereler yine de kayar"


def test_kept_incidents_stay_in_chronological_order():
    memory = RunMemory(limit=2)
    memory.note(ts=5.0, moment="ilk olay", participants=[],
                decision="open_episode", severity="olay")
    _dolu(memory, 4)
    memory.note(ts=90.0, moment="ikinci olay", participants=[],
                decision="escalate", severity="olay")
    stamps = [n.ts for n in memory.recent()]
    assert stamps == sorted(stamps)


def test_the_rendered_block_leaks_no_severity_grading():
    """`severity` epizot açılışının TEK kapısı (`DecisionLoop._may_open`).
    Geçmiş derecelendirmeleri gören model kendini doğrulayan bir döngüye
    girer ("olay, olay → olay"). Blok NE GÖRÜLDÜĞÜNÜ taşır, NASIL
    DERECELENDİRİLDİĞİNİ değil.

    Kayıt metinleri o üç kelimeyi içermeyecek şekilde seçildi — yoksa test
    kendi verisini yakalar.
    """
    memory = RunMemory(limit=4)
    memory.note(ts=0.0, moment="istif aracı yükü yüksek konuma kaldırıyor",
                participants=["forklift"], decision="open_episode",
                severity="olay")
    memory.note(ts=10.0, moment="arka tekerlekler yerden kesildi",
                participants=["forklift"], decision="update_episode",
                severity="dikkat")
    block = memory.render()
    for level in SEVERITY_LEVELS:
        assert level not in block, f"derecelendirme sızdı: {level}"
    assert "istif aracı yükü yüksek konuma kaldırıyor" in block


def test_an_empty_memory_renders_nothing():
    """İlk pencerede block HİÇ basılmamalı — boş bir başlık modele
    olmayan bir geçmiş vaat eder."""
    assert RunMemory().render() == ""


def test_the_block_says_it_is_context_and_not_evidence():
    memory = RunMemory()
    memory.note(ts=0.0, moment="forklift geçti", participants=[],
                decision="ignore", severity="rutin")
    assert "kanıt" in memory.render().lower()
```

- [ ] **Step 2: Kırmızıyı gör**

Run: `uv run pytest tests/test_recall.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'gozcu.recall'`

- [ ] **Step 3: Modülü yaz**

`gozcu/recall.py`:

```python
"""Koşu içi kısa süreli hafıza — bir koşunun kendi geçmişi.

Görü katmanı her pencereye **sıfırdan** bakıyor: 10 saniyelik bir klip
gidiyor, bir açıklama dönüyor, sonraki pencere öncekini hiç bilmiyor. 2.
dakikadaki dengesizlik 5. dakikadaki devrilmenin bağlamı olamıyor.

Uzun-video literatüründeki "hafıza bankası" deseninin **text** karşılığı:
özellik seviyesinde yapılamıyor çünkü ağ geçidine base64 mp4 gidip text
dönüyor. Elimizdeki tek temsil text, o yüzden hafıza da text.

**Ajansız ve modelsiz.** Saf veri yapısı: model çağırmıyor, ağa çıkmıyor,
`DecisionLoop`'a bağımlı değil. Beslemesi `run.py`'deki kapanışlardan
geliyor — döngünün kendisi DEĞİŞMİYOR.
"""

from dataclasses import dataclass, field

from gozcu.config import RECALL_WINDOW_N
from gozcu.models import SEVERITY_LEVELS

#: Bloğun başlığı. "kanıt DEĞİL" kısmı süs değil: block görü çağrısına
#: giriyor ve modelin oradan üreteceği anlar epizoda, oradan da teslim
#: edilen `events[]`'e akıyor. Model geçmiş bir pencereyi bu klipte
#: gördüğü bir şey sanarsa uydurma üretir.
RECALL_HEADER = "ÖNCEKİ PENCERELER (bağlam — bu klibin kanıtı DEĞİL)"

#: Kalıcı tutulan derecelendirme. **Kopyalanmıyor, İTHAL EDİLİYOR:** bu
#: depoda bir enum bir kez ikinci bir yere elle yazıldı ve iki liste
#: ayrışınca sistem sessizce ölü hâle geldi (CLAUDE.md). Yorumla önlenen
#: ayrışma, önlenmemiş ayrışmadır.
INCIDENT = SEVERITY_LEVELS[-1]


@dataclass
class WindowNote:
    """Tek pencerenin satırı."""

    ts: float
    moment: str
    participants: list[str] = field(default_factory=list)
    decision: str = "ignore"
    #: **Tutuluyor ama RENDER EDİLMİYOR** — bkz. `render()`.
    severity: str = "rutin"


class RunMemory:
    """Koşunun pencere geçmişi, hiyerarşik sınırla.

    Sınır iki katmanlı: **son N pencere** tam detay + `severity == "olay"`
    olan **her** pencere kalıcı. Olay asla düşmez, rutin pencereler kayar.
    Düz bir kayan pencere, uzun bir videoda olayın kendisini düşürürdü ve
    tam da hatırlanması gereken şey odur.
    """

    def __init__(self, limit: int | None = None) -> None:
        self.limit = RECALL_WINDOW_N if limit is None else limit
        self._notes: list[WindowNote] = []

    def note(self, ts: float, moment: str, participants=(),
             decision: str = "ignore", severity: str = "rutin") -> None:
        self._notes.append(WindowNote(ts=ts, moment=moment,
                                      participants=list(participants),
                                      decision=decision, severity=severity))

    def recent(self, n: int | None = None) -> list[WindowNote]:
        """Kalıcı olaylar + son N pencere, zaman sırasında ve tekrarsız."""
        limit = self.limit if n is None else n
        pinned_notes = [note for note in self._notes if note.severity == INCIDENT]
        son = self._notes[-limit:] if limit else []
        selected = {id(note): note for note in (*pinned_notes, *son)}
        return sorted(selected.values(), key=lambda note: note.ts)

    def render(self, n: int | None = None) -> str:
        """Prompt'a girecek block. Boşsa **boş dize** — başlık bile yok.

        **`severity` YAZILMIYOR ve bu bir tercih değil, bir kısıt.**
        `severity` epizot açılışının tek kapısı (`DecisionLoop._may_open`).
        Geçmiş derecelendirmeleri gören model kendini doğrulayan bir döngüye
        girer: "olay, olay → olay". Blok NE GÖRÜLDÜĞÜNÜ taşır, NASIL
        DERECELENDİRİLDİĞİNİ değil.
        """
        notes = self.recent(n)
        if not notes:
            return ""
        lines = [RECALL_HEADER]
        for note in notes:
            who = f" [{', '.join(note.participants)}]" if note.participants else ""
            lines.append(f"- {int(note.ts // 60):02d}:"
                            f"{int(note.ts % 60):02d}{who} {note.moment}")
        return "\n".join(lines)
```

`gozcu/config.py` sonuna:

```python
# --- Kısa süreli hafıza (Aşama 6) -------------------------------------------
#
# Kaç pencere tam detayla taşınıyor. Ölçüldü: dört satırlık bir block 301
# karakter ≈ 120 token; görü çağrısı bugün ~8.285 token, yani **+%1,5**.
# `SCHEMA_MAX_TOKENS` bir ÇIKTI tavanı ve değişmiyor.
RECALL_WINDOW_N = int(os.environ.get("GOZCU_RECALL_WINDOW_N", "4"))

# Bloğun görü çağrısına girip girmediği. Kapalıyken `RunMemory` yine doluyor
# ve yönlendirici/sentezleyici/süpervizör bağlanmaları çalışmaya devam
# ediyor — anahtar YALNIZ görü çağrısını kapsıyor, çünkü ölçülen tek bedel
# orada.
RECALL_VISION = os.environ.get("GOZCU_RECALL_VISION", "1") != "0"
```

`.env.example`'a iki satır, gerekçeleriyle.

- [ ] **Step 4: Yeşili gör**

Run: `uv run pytest tests/ -q`
Expected: 1072 passed

- [ ] **Step 5: Commit**

```bash
git add gozcu/recall.py gozcu/config.py tests/test_recall.py .env.example
git commit -m "feat(hafıza): RunMemory — koşu içi kısa süreli hafıza

Görü katmanı her pencereye sıfırdan bakıyor. Sınır hiyerarşik: son N
pencere + her 'olay' penceresi kalıcı; düz kayan pencere uzun videoda
olayın kendisini düşürürdü. severity tutuluyor ama RENDER EDİLMİYOR:
epizot açılışının tek kapısı o ve geçmiş derecelendirmeleri gören model
kendini doğrulayan bir döngüye girer."
```

---

### Task 15: Yorumlayıcı bağlanması — `ÖNCEKİ PENCERELER` (§8.1)

**Files:**
- Modify: `gozcu/agents/interpreter.py` (`interpret` imzası; `_message` ~331-350)
- Modify: `gozcu/run.py` (`interpret` kapanışı ~424; `RunMemory` kurulumu)
- Test: `tests/test_interpreter.py`

**Interfaces:**
- Consumes: `RunMemory.render()` (Görev 14), `config.RECALL_VISION`
- Produces: `interpret(gw, store, window, clip_for=None, recall=None)` · `_message(window, clip_uri, start_ts, end_ts, recall_text="")`

> **`RunMemory` BESLEMESİ de bu görevde.** İlk taslak beslemeyi Görev 16'ya koyuyordu; o hâlde Görev 15 bittiğinde `render()` her pencerede boş dize dönerdi — blok hiç basılmaz, Adım 5'in "önce/sonra" ölçümünde **"sonra" diye bir şey olmaz** ve kapı anlamsızca yeşil geçerdi. Besleme ile tüketim aynı görevde.

> **Bu görev tek başına birleştirilmez.** §12.8: k04 **VE** k05 üzerinde canlı ölçülmeden merge edilmiyor — k05 projenin aşırı-uyum kontrol klibi. Ölçülecek: epizot açılış anı, `events[]` an sayısı, koşu süresi ve **uydurma, karşılaştırmayla**: aynı klibin önce/sonra `events[]` listeleri yan yana konur, sonrasındaki her yeni satır için "bu an klipte gerçekten var mı" tek tek cevaplanır.

- [ ] **Step 1: Kırmızı testleri yaz**

```python
def test_the_vision_prompt_carries_the_previous_windows():
    from gozcu.agents.interpreter import _message
    from gozcu.recall import RunMemory
    memory = RunMemory()
    memory.note(ts=120.0, moment="istif aracı yükü yüksek konuma kaldırıyor",
                participants=["forklift"], decision="open_episode",
                severity="olay")
    mesaj = _message(_window(), "data:video/mp4;base64,AA==", 300.0, 310.0,
                     recall_text=memory.render())
    text = mesaj[1]["content"][0]["text"]
    assert "ÖNCEKİ PENCERELER" in text
    assert "02:00" in text


def test_the_vision_prompt_omits_the_block_when_there_is_no_history():
    """İlk pencerede başlık bile basılmamalı."""
    from gozcu.agents.interpreter import _message
    mesaj = _message(_window(), "data:video/mp4;base64,AA==", 0.0, 10.0,
                     recall_text="")
    assert "ÖNCEKİ PENCERELER" not in mesaj[1]["content"][0]["text"]


def test_the_recall_block_can_be_switched_off(monkeypatch):
    """`GOZCU_RECALL_VISION=0` — ölçülen tek bedel görü çağrısında."""
    from gozcu.agents import interpreter
    from gozcu.recall import RunMemory
    monkeypatch.setattr(interpreter, "RECALL_VISION", False)
    memory = RunMemory()
    memory.note(ts=0.0, moment="istif aracı geçti", participants=[],
                decision="ignore", severity="rutin")
    mesaj = interpreter._message(_window(), "data:video/mp4;base64,AA==",
                                 0.0, 10.0,
                                 recall_text=("" if not interpreter.RECALL_VISION
                                              else memory.render()))
    assert "ÖNCEKİ PENCERELER" not in mesaj[1]["content"][0]["text"]


def test_the_block_never_presents_past_windows_as_this_clip_s_evidence():
    """§8.1'in YAPISAL koruması. Blok görü çağrısına giriyor ve modelin
    oradan üreteceği `beats` epizoda, oradan da teslim edilen `events[]`'e
    akıyor (`synthesizer.py:295` → `report.py:181`). Tek koruma prompt
    metni olamaz: bu depo tam olarak bu tür bir uydurmayı bir kez ağır
    ödedi (`models.py:149`).

    İddia iki parçalı — block (a) kanıt olmadığını SÖYLÜYOR ve (b) bu
    klibin sinyallerinden AYRI bir başlık altında duruyor.
    """
    from gozcu.agents.interpreter import _message
    from gozcu.recall import RECALL_HEADER, RunMemory
    memory = RunMemory()
    memory.note(ts=10.0, moment="kamyon rampaya yanaştı", participants=[],
                decision="ignore", severity="rutin")
    text = _message(_window(), "data:video/mp4;base64,AA==", 300.0, 310.0,
                     recall_text=memory.render())[1]["content"][0]["text"]

    assert RECALL_HEADER in text
    assert "kanıt" in text.lower()
    # Geçmiş satır, BU pencerenin sinyal bloğundan önce ve ayrı duruyor.
    assert text.index("kamyon rampaya yanaştı") < text.index("Sinyaller —")


def test_the_video_part_is_still_the_last_content_piece():
    """Blok text parçasına giriyor; `video_url` parçası sona kalmalı —
    `vlm`'in görüntü kapasitesi sıfır ve parça sırası canlı doğrulandı."""
    from gozcu.agents.interpreter import _message
    mesaj = _message(_window(), "data:video/mp4;base64,AA==", 0.0, 10.0,
                     recall_text="ÖNCEKİ PENCERELER (bağlam)\n- 00:10 x")
    assert mesaj[1]["content"][-1]["type"] == "video_url"
```

- [ ] **Step 2: Kırmızıyı gör**

Run: `uv run pytest tests/test_interpreter.py -q -k "previous_windows or omits_the_block"`
Expected: FAIL — `TypeError: _message() got an unexpected keyword argument 'recall_text'`

- [ ] **Step 3: Bloğu bağla**

`gozcu/agents/interpreter.py`:

```python
def _message(window: list[Observation], clip_uri: str,
             start_ts: float, end_ts: float,
             recall_text: str = "") -> list[dict]:
    """...

    `recall_text` boşsa block **hiç basılmıyor**: boş bir başlık modele
    olmayan bir geçmiş vaat eder ve tutulmayan bir vaat uydurmaya davettir.
    Blok sinyallerin ÜSTÜNDE duruyor — bu klibin kanıtı sinyaller ve
    videonun kendisi; geçmiş yalnız bağlam.
    """
    span = max(end_ts - start_ts, 0.0)
    onceki = f"{recall_text}\n\n" if recall_text else ""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": [
            {"type": "text",
             "text": (f"{onceki}Sinyaller — {_context(window)}\n\n"
                      f"Aşağıdaki {span:.1f} saniyelik kamera kesiti videonun "
                      f"{start_ts:.1f}s–{end_ts:.1f}s aralığına ait. Bu "
                      f"pencerede ne oluyor, kesit boyunca ne değişiyor?")},
            {"type": "video_url", "video_url": {"url": clip_uri}}]}]
```

`interpret`'e `recall=None` parametresi ekle; `_message` çağrısında:

```python
    recall_text = (recall.render()
                   if recall is not None and RECALL_VISION else "")
```

import: `from gozcu.config import RECALL_VISION` (model kimliği DEĞİL, bir davranış anahtarı — `config.py` yine tek kaynak).

`gozcu/run.py` — `run_windows = list(windows(observations))` satırının yanına `run_memory = RunMemory()`, `interpret` kapanışına `recall`, ve **`synthesize` kapanışına besleme**:

```python
            interpret=partial(interpret, gw, store,
                              clip_for=_clip_for(video_path),
                              recall=run_memory),
            # Kayıt `synthesize` kapanışında yazılıyor: yorumlayıcı O pencere
            # için çoktan koştu (elimizde `interpretation` var) ve bu kapanış
            # pencere başına TAM BİR KEZ çağrılıyor. `interpret` kapanışına
            # konsaydı kayıt kendi penceresini "önceki pencere" diye modele
            # geri verirdi; `route` kapanışına konsaydı ertelenmiş pencereler
            # (`catch_up`) iki kez yazılırdı.
            synthesize=lambda window, interpretation, decision: (
                run_memory.note(
                    ts=window[0].ts,
                    moment=(interpretation.description if interpretation
                            else "(görü katmanı bu pencereyi okumadı)"),
                    participants=sorted({d.label for o in window
                                         for d in o.detections}),
                    decision=decision,
                    severity=(interpretation.severity if interpretation
                              else "rutin")),
                synthesize(gw, store, window, interpretation, decision,
                           on_close=lambda episode: _on_close_traced(
                               gw, store, episode, archive=archive),
                           source=source))[1],
```

- [ ] **Step 4: Yeşili gör**

Run: `uv run pytest tests/ -q`
Expected: 1077 passed

- [ ] **Step 5: Canlı ölçüm — k04 VE k05** (§12.8)

Run: `uv run --env-file .env python app.py`, her iki klibi de koştur. Önce/sonra `events[]` listelerini yan yana koy. **Sonrasında öncesinde olmayan bir olay iddiası varsa bu görev birleştirilmez.** Ölçümü `docs/05-decisions/decision-log.md`'ye yaz.

- [ ] **Step 6: Commit**

```bash
git add gozcu/agents/interpreter.py gozcu/run.py tests/test_interpreter.py
git commit -m "feat(hafıza): görü çağrısı önceki pencereleri görüyor

Bugüne kadar _context(window) yalnız O pencerenin sinyallerini yazıyordu.
Blok severity TAŞIMIYOR: geçmiş derecelendirmeleri gören model kendini
doğrulayan bir döngüye girer. Geçmiş yoksa başlık bile basılmıyor.
GOZCU_RECALL_VISION=0 ile kapatılabilir."
```

---

### Task 16: Yönlendirici, sentezleyici ve süpervizör bağlanmaları (§8.2–8.4)

**Files:**
- Modify: `gozcu/agents/router.py` (`route` imzası ~329-331; prompt)
- Modify: `gozcu/agents/synthesizer.py` (`_digest` ~116-138)
- Modify: `gozcu/agents/supervisor.py` (`history` budama)
- Modify: `gozcu/run.py` (`route` kapanışı ~419-421; `synthesize` kapanışı; `RunMemory` beslemesi)
- Test: `tests/test_router.py`, `tests/test_synthesizer.py`, `tests/test_supervisor.py`

**Interfaces:**
- Consumes: `RunMemory` (Görev 14)
- Produces: `route(gw, window, has_open_episode, *, energy=None, run_windows=None, recall=None)`

> **`DecisionLoop`'a DOKUNULMUYOR.** `loop.py:479` `route`'u **iki** argümanla çağırıyor (`self.route(window, energy)`); eklenen üçüncü konumsal parametre hiçbir zaman geçilmez ve varsayılansız olursa `TypeError` verir. `RunMemory` `run.py`'deki **kapanışla** yakalanıyor. `_route_accepts_energy` de değişmiyor.

> **`_may_open` kapısına DOKUNULMUYOR.** Kapanmış epizotlar yalnız digest'i ve risk analizini zenginleştirir; açılış kararına girmez.

- [ ] **Step 1: Kırmızı testleri yaz**

```python
# tests/test_router.py
def test_the_router_sees_the_last_decisions():
    """Son kararlar yönlendiricinin açma/kapama kararını sabitliyor:
    üç penceredir açık olan bir olay dördüncüde yeniden açılmamalı."""
    from gozcu.recall import RunMemory
    gateway = _FakeGateway()
    memory = RunMemory()
    for index, karar in enumerate(("open_episode", "update_episode",
                                   "update_episode")):
        memory.note(ts=float(index * 10), moment=f"pencere {index}",
                    participants=["forklift"], decision=karar,
                    severity="dikkat")
    route(gateway, [_observation(30.0)], True, recall=memory)
    text = _prompt_text(gateway)
    assert "update_episode" in text
    assert "open_episode" in text


def test_the_router_still_works_without_recall():
    """`recall` varsayılanı `None`: bugünkü bütün çağıranlar aynen çalışıyor
    ve `DecisionLoop`'un iki argümanlı çağrısı bozulmuyor."""
    gateway = _FakeGateway()
    decision = route(gateway, [_observation(0.0)], False)
    assert decision.decision in ("ignore", "inspect", "open_episode",
                                "update_episode", "close_episode", "escalate")
    assert "ÖNCEKİ" not in _prompt_text(gateway)


# tests/test_synthesizer.py
def test_the_digest_remembers_episodes_that_already_closed():
    """Bugün epizot kapanınca öncesi TAMAMEN unutuluyor: `_digest` yalnız
    AÇIK epizodun özetini başa koyuyor."""
    from gozcu.agents.synthesizer import _digest
    from gozcu.models import Episode
    kapali = Episode(id=1, start_ts=0.0, end_ts=30.0, phase="outcome",
                     summary_tr="raf hizasında zor durdu",
                     preliminary_risk="Orta", state="closed")
    text = _digest(_window(start=60.0), None, None, closed=[kapali])
    assert "raf hizasında zor durdu" in text


def test_the_open_episode_still_leads_the_digest():
    """`DEVAM EDEN OLAY:` satırı BAŞTA kalmalı — kaynaşmanın süreklilik
    tarafı o satıra bağlı."""
    from gozcu.agents.synthesizer import _digest
    from gozcu.models import Episode
    open_ep = Episode(id=2, start_ts=50.0, end_ts=60.0, phase="development",
                   summary_tr="istif aracı devriliyor",
                   preliminary_risk="Kritik", state="open")
    kapali = Episode(id=1, start_ts=0.0, end_ts=30.0, phase="outcome",
                     summary_tr="raf hizasında zor durdu",
                     preliminary_risk="Orta", state="closed")
    lines = _digest(_window(start=60.0), None, open_ep,
                       closed=[kapali]).splitlines()
    assert lines[0].startswith("DEVAM EDEN OLAY:")
    assert any("raf hizasında zor durdu" in satir for satir in lines[1:])


# tests/test_supervisor.py
def test_the_history_is_pruned_but_keeps_the_system_prompt():
    """`Supervisor.history` sistem promptu + her tur + her araç sonucu
    JSON'u ile SINIRSIZ büyüyordu."""
    from gozcu.config import SUPERVISOR_HISTORY_TURNS
    gw, store, _e = _setup([Response(content=f"cevap {i}") for i in range(30)])
    nobetci = Supervisor(gw, store)
    with patch("gozcu.agents.supervisor.screen_text",
               return_value=_screening()):
        for index in range(30):
            nobetci.talk(f"soru {index}")
    assert nobetci.history[0]["role"] == "system"
    assert len(nobetci.history) <= SUPERVISOR_HISTORY_TURNS * 2 + 2, (
        "geçmiş sınırsız büyümemeli")


def test_pruning_keeps_the_pinned_summary_of_the_open_episode():
    """Budama açık olayın özetini DÜŞÜREMEZ: düşerse süpervizör kendi
    müdahale ettiği olayı unutur."""
    gw, store, e = _setup([Response(content=f"cevap {i}") for i in range(30)])
    nobetci = Supervisor(gw, store)
    with patch("gozcu.agents.supervisor.assess_risk", return_value=_risk(e)), \
         patch("gozcu.agents.supervisor.screen_text",
               return_value=_screening()):
        nobetci.escalate(e)
        for index in range(25):
            nobetci.talk(f"soru {index}")
    # `_setup`'ın açık epizodunun özeti: "istif aracı devrildi, yerde
    # hareketsiz kişi" (test_supervisor.py:69)
    assert any("istif aracı devrildi" in str(m["content"])
               for m in nobetci.history), "açık olayın özeti sabitlenmiş olmalı"
```

- [ ] **Step 2: Kırmızıyı gör**

Run: `uv run pytest tests/test_router.py tests/test_synthesizer.py tests/test_supervisor.py -q -k "recall or closed or pruned or pinned"`
Expected: FAIL

- [ ] **Step 3: Üç bağlanmayı yaz**

**8.2** `gozcu/agents/router.py` — `route`'a `recall=None` **keyword-only** parametresi (`*`'dan sonra, `run_windows`'un yanına). Prompt'a eklenen blok:

```python
    if recall is not None:
        last = recall.recent(3)
        if last:
            lines.append("SON KARARLAR (bu koşuda, en yeni sonda): "
                         + " → ".join(n.decision for n in last))
```

> **Neden burada ham karar enum'u YAZILABİLİYOR, `severity` yazılamıyordu.** `severity` yorumlayıcının DERECELENDİRMESİ ve epizot açılışının tek kapısı; modele geri verilirse kendini doğrulayan bir döngü açar ("olay, olay → olay"). Karar ise yönlendiricinin kendi **durum makinesi**: `open_episode`'dan sonra `update_episode` gelmesi bir önyargı değil, sözleşmenin kendisi — `DecisionLoop._resolve` aynı geçişi zaten zorluyor. Model o kısıt altında zaten; görmesi yalnız aynı olayı ikinci kez açmasını engelliyor.

`gozcu/run.py`'de kapanış:

```python
            # Üçüncü KONUMSAL parametre YOK: `DecisionLoop` route'u iki
            # argümanla çağırıyor (`loop.py:479`). `RunMemory` buradaki
            # kapanışla yakalanıyor; döngü değişmiyor.
            route=lambda window, energy=None: route(
                gw, window, store.open_episode() is not None, energy=energy,
                run_windows=run_windows, recall=run_memory),
```

**8.3** `gozcu/agents/synthesizer.py` — `_digest`'e `closed: list[Episode] | None = None` parametresi. `DEVAM EDEN OLAY:` satırı **başta kalır**, kapanmışlar onun altına:

```python
    if closed:
        # Bugün epizot kapanınca öncesi TAMAMEN unutuluyor: `previous` yalnız
        # AÇIK epizodu taşıyor. Kapanmışlar `_may_open` kapısına GİRMİYOR —
        # yalnız digest'i zenginleştiriyorlar.
        lines.insert(1 if previous is not None else 0,
                     "ÖNCEKİ OLAYLAR: "
                     + " | ".join(e.summary_tr for e in closed))
```

**Ve `synthesize` onu DOLDURMAK zorunda** — yoksa parametre eklenir, testler yeşil olur ve özellik üretimde ölü kalır (Görev 15'in ilk taslağıyla birebir aynı tuzak). `synthesize` içindeki `_digest` çağrısı:

```python
    closed_before = [e for e in store.episodes()
                     if e.state == "closed" and e.summary_source == "model"]
    prompt = _digest(window, interpretation, open_episode, closed=closed_before)
```

> `summary_source == "model"` süzgeci ŞART: arıza metni bir olay tarifi değildir ve digest'e girerse bir sonraki pencerenin özetini zehirler — bu depo o arızayı bir kez ağır ödedi (`models.py:149`).

**8.4** `gozcu/agents/supervisor.py` — `history` **her `gw.ask`'ten ÖNCE** budanıyor; `self.history`'nin kendisi kırpılmıyor. Yeni metot:

```python
def _prune_history(self) -> list[dict]:
    """Sistem promptu + sabitlenmiş açık olay + son N tur.

    `self.history` sistem promptu + her tur + her araç sonucu JSON'u ile
    SINIRSIZ büyüyordu: uzun bir koşuda her istek bir öncekinin tamamını
    yeniden taşıyor.

    **Listeyi YERİNDE kırpmıyor, bir GÖRÜNÜM döndürüyor.** `self.history`
    devir defterinin ve testlerin okuduğu tam kayıt; onu kısaltmak
    ekrandaki zinciri de kısaltırdı.
    """
    if len(self.history) <= SUPERVISOR_HISTORY_TURNS * 2 + 2:
        return list(self.history)
    system = self.history[:1]
    # Açık olayın EN SON `[SİSTEM]` satırı sabitleniyor: düşerse süpervizör
    # kendi müdahale ettiği olayı unutur.
    pinned = [m for m in self.history[1:]
              if m["role"] == "user" and "[SİSTEM]" in str(m["content"])][-1:]
    tail = self.history[-(SUPERVISOR_HISTORY_TURNS * 2):]
    # `tool` rolündeki bir mesaj, bağlandığı `assistant` turu olmadan
    # GEÇERSİZ: kuyruk bir `tool` ile başlıyorsa onu düşür.
    while tail and tail[0].get("role") == "tool":
        tail = tail[1:]
    return [*system, *(m for m in pinned if m not in tail), *tail]
```

Üç `gw.ask` çağrısında (`supervisor.py:451` ve `_reply`/`talk`'ın turları) `self.history` yerine `self._prune_history()` geçilir. `gozcu/config.py`'a:

```python
# Süpervizör geçmişinde tutulan tur sayısı. Sistem promptu ve açık olayın
# `[SİSTEM]` satırı bunun DIŞINDA — ikisi de her zaman korunuyor.
SUPERVISOR_HISTORY_TURNS = int(
    os.environ.get("GOZCU_SUPERVISOR_HISTORY_TURNS", "8"))
```

> **`RunMemory` beslemesi Görev 15'te İNDİ** — burada yeniden yazılmıyor. Bu görev yalnız üç TÜKETİCİ ekliyor.

- [ ] **Step 4: Yeşili gör**

Run: `uv run pytest tests/ -q`
Expected: 1083 passed

- [ ] **Step 5: Commit**

```bash
git add gozcu/agents/ gozcu/run.py gozcu/config.py tests/
git commit -m "feat(hafıza): yönlendirici, digest ve süpervizör geçmişi hatırlıyor

route'a ÜÇÜNCÜ KONUMSAL PARAMETRE EKLENMEDİ: DecisionLoop onu iki
argümanla çağırıyor (loop.py:479). RunMemory run.py kapanışıyla
yakalanıyor; loop.py ve _route_accepts_energy değişmedi.

_digest artık kapanmış epizotları da taşıyor — epizot kapanınca öncesi
tamamen unutuluyordu. Supervisor.history budandı: sistem promptu + açık
olayın sabitlenmiş özeti + son N tur. _may_open kapısına dokunulmadı."
```

---

### Task 17: Kalibrasyon, eşikler ve dokümanlar (§9, §12)

**Files:**
- Create: `scripts/calibrate_memory.py`
- Modify: `gozcu/config.py` (kalibre edilmiş eşikler)
- Modify: `docs/05-decisions/decision-log.md`, `docs/tasks/README.md`, `README.md`, `docs/tasks/22-capraz-video-hafiza.md` (yeni)

> **EN SON.** Eşik epizot **özet metinleri** üzerinden kalibre ediliyor; Görev 15 yorumlayıcının `description`'ını değiştiriyor → sentezleyicinin `summary_tr`'si değişiyor → **aynı arşive karşı kosinüs skorları kayıyor.** Görev 14–16 inmeden kalibre edilirse iki kez kalibre edilir.

- [ ] **Step 1: Script'i yaz**

`scripts/calibrate_memory.py` — `reset_memory.py` ile aynı gelenek. Fikstürleri gömer ve **üç sorgu ailesi** koşturur; her aile için skor dağılımını basar:

```python
#: (a) fikstür konusuna NEAR — eşik bunları KESMEMELİ.
NEAR = ["B-Hattı'nda istif aracının freni tutmadı",
         "forklift yükü hatalı istifledi",
         "kask takmayan personel görüldü"]

#: (b) kasten IRRELEVANT — eşik bunları KESMELİ. B4'ün ölçüm sorgusu.
IRRELEVANT = ["kantinde yemek kuyruğu uzadı",
            "muhasebe departmanı toplantı yapıyor",
            "otoparkta kar yağışı başladı"]

#: (c) **beat 5'in GERÇEK diyalog biçimi.** Bu aile ŞART: canlı sorgu,
#: süpervizör modelinin `params["query"]`'si — fikstür metnine benzeyen bir
#: cümle değil. (c)'yi ölçmeyen bir eşik, onarmak için var olduğumuz beat'i
#: keser. Soru–cümle kosinüsü sistematik olarak cümle–cümle kosinüsünden
#: düşük ve `QDRANT_SCORE_THRESHOLD_DIALOGUE` bu yüzden ayrı.
DIALOGUE = ["bu araçla daha önce sorun oldu mu?",
           "IST-04 ile ilgili geçmiş kayıt var mı?",
           "bu bölgede daha önce kaza oldu mu?"]
```

Script'in gövdesi:

```python
"""Emsal alaka eşiklerini ölçer. Hiçbir şey YAZMAZ — sayıları basar.

Eşik iki tane çünkü iki tüketici arşivi FARKLI biçimde sorguluyor: risk
analisti bir CÜMLEYLE (`f"{summary_tr} {participants}"`), süpervizör
modelin yazdığı bir SORUYLA. Soru–cümle kosinüsü sistematik olarak
cümle–cümle kosinüsünden düşük; tek bir eşik ya analisti kör eder ya demo
senaryosunun 5. beat'ini keser.

**Bu script Aşama 6'dan SONRA koşar.** Eşik epizot özet metinleri üzerinden
kalibre ediliyor; Aşama 6.1 yorumlayıcının `description`'ını değiştiriyor →
sentezleyicinin `summary_tr`'si değişiyor → aynı arşive karşı skorlar
kayıyor. Önce koşulursa iki kez kalibre edilir.
"""

import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from gozcu.fixtures.loader import load_history     # noqa: E402
from gozcu.gateway import Gateway                  # noqa: E402
from gozcu.memory import search_timeline           # noqa: E402
from gozcu.store import Store                      # noqa: E402

FAMILIES = {"yakın": NEAR, "alakasız": IRRELEVANT, "diyalog": DIALOGUE}


def _scores(gw, store, queries) -> list[float]:
    scores = []
    for sorgu in queries:
        scores += [p.score for p in search_timeline(gw, store, sorgu)]
    return sorted(scores, reverse=True)


def main() -> int:
    store = Store()
    gw = Gateway(store)
    embedded = load_history(gw, store)
    if not embedded:
        print("HATA: hiçbir fikstür gömülemedi — gömme kademesi bozuk.")
        return 1

    measured = {}
    for ad, queries in FAMILIES.items():
        scores = _scores(gw, store, queries)
        measured[ad] = scores
        if scores:
            print(f"{ad:10s} n={len(scores):3d} "
                  f"min={min(scores):.3f} "
                  f"medyan={statistics.median(scores):.3f} "
                  f"max={max(scores):.3f}")
        else:
            print(f"{ad:10s} n=0 — hiçbir sonuç dönmedi")

    # Eşik iki ailenin ARASINA konuyor: kesilmesi gerekenin en yükseğinin
    # üstü, korunması gerekenin en düşüğünün altı. Aralık negatifse
    # (kesilecek olan korunacak olandan yüksek skorluysa) eşik o aileyi
    # ayıramaz ve bu bir BULGU — susulmuyor.
    for ad, keep_family in (("RISK", "yakın"), ("DIALOGUE", "diyalog")):
        cut_family = measured["alakasız"]
        if not measured[keep_family] or not cut_family:
            print(f"{ad}: ölçülemedi")
            continue
        low, high = max(cut_family), min(measured[keep_family])
        if low >= high:
            print(f"{ad}: AYIRAMAZ — alakasız {low:.3f} >= korunacak {high:.3f}. "
                  f"Eşik bu ikisini ayırt edemiyor; karar günlüğüne writer.")
        else:
            print(f"{ad}: önerilen eşik {(low + high) / 2:.3f} "
                  f"(aralık {low:.3f}–{high:.3f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Çıktı: her ailenin min/medyan/max skoru ve **önerilen iki eşik** — kesilmesi gereken ailenin en yükseği ile korunması gereken ailenin en düşüğünün ortası. **Aralık negatifse eşik o iki aileyi ayıramaz ve script bunu söyler**; susmaz.

- [ ] **Step 2: Koleksiyonu sıfırla ve kalibre et**

```bash
GOZCU_MEMORY_RESET=1 uv run --env-file .env python scripts/reset_memory.py
uv run --env-file .env python scripts/calibrate_memory.py
```

> **Arşiv kapsamı — beklenen bir bulgu.** Arşivdeki kayıtlar fren, hatalı istifleme ve kask; demo klipleri **forklift devrilmesi**. Kalibre edilmiş bir eşik büyük ihtimalle sıfır emsal döndürür ve beat 5 dürüstçe ama işe yaramaz şekilde "kayıt bulunamadı" der. **Dördüncü bir olay UYDURULMAZ** (şartname §16); skorlar düşükse bu bir bulgu olarak karar günlüğüne yazılır ve kapsam genişletmesi ayrı bir ürün sahibi kararıdır.

- [ ] **Step 3: Sayıları `config.py`'a yaz**

Ölçülen değerleri `QDRANT_SCORE_THRESHOLD_RISK` / `…_DIALOGUE`'un varsayılanı yap ve **hangi koşudan geldiklerini** yorumda yaz.

- [ ] **Step 4: §12'nin sekiz doğrulama adımını koştur**

Spec'in "Doğrulama — bitti demeden önce" bölümü. Her adımın sonucu karar günlüğüne.

- [ ] **Step 5: Dokümanları güncelle**

- `docs/05-decisions/decision-log.md` — aşama başına önce/sonra ölçümü
- `docs/tasks/22-capraz-video-hafiza.md` — yeni görev dosyası, `✅ TAMAMLANDI` bandı ve hangi commit'lerde indiği
- `docs/tasks/README.md` — durum tablosuna satır; **satır 108-112'deki hafıza kurulum notu** (`memory_backend()` bunu `"local"` diye söyler) tohumlamanın artık `post_run`'dan çağrıldığını anlatacak şekilde
- `README.md` — tohumlamanın nereden çağrıldığı, dört yeni `.env` anahtarı

- [ ] **Step 6: Commit**

```bash
git add scripts/calibrate_memory.py gozcu/config.py docs/ README.md
git commit -m "feat(hafıza): eşik kalibrasyonu ve teslim dokümanları

Üç sorgu ailesi: yakın, kasten alakasız, ve beat 5'in GERÇEK diyalog
biçimi. (c) şart — onu ölçmeyen bir eşik, onarmak için var olduğumuz
beat'i keser."
```

---

## Plan öz-incelemesi

**Spec kapsamı.** §2→Görev 0 · §3→1,2,3,4 · §4→5,6,7 · §5→8 · §6→9,10 · §7→11,12,13 · §8→14,15,16 · §9→17 · §10→8. adımın bozulma tablosu + 12. görevin rozeti · §11→her görevin test adımları · §12→17. görev · §13→dokunulmadı. **Boşluk yok.**

**Tip tutarlılığı.** `point_id(source, episode_id)` — Görev 1'de tanımlı, Görev 9'da `point_id(*exclude)` olarak çağrılıyor, ikisi de iki argüman. `Precedent(episode, score)` — Görev 9'da tanımlı, 11 ve 12'de `p.episode.…`/`p.score`. `search_timeline(..., exclude=tuple, threshold=float|None)` — Görev 9 ve 10'da genişliyor, iki tüketici ikisini de geçiyor. `_stamp_actions(store, episode)` — Görev 4'te tanımlı, Görev 8'de çağrılıyor. `archive` bayrağı — Görev 7'de `_on_close`/`run_pipeline`, Görev 8'de `_sweep_unembedded`; üçü de aynı ad.

**Bilerek birleştirilebilir görevler.** 1+2 (`source` alanına başvuru), 7+8 (`archive` bayrağı iki yola birden ulaşmadan test yeşil olmaz), 9+10 (`_LOCK`). Ayrı tutulmalarının tek sebebi inceleme kolaylığı; uygulayıcı isterse tek commit'te birleştirebilir.

**Test sayısı yolculuğu.**

| Görev | Delta | Beklenen |
|---|---|---|
| taban | — | 1026 passed |
| G1 | +6 yeni; `test_memory.py:247` **xfail** | 1031 passed, 1 xfailed |
| G2 | +4 | 1035 passed, 1 xfailed |
| G3 | +4 | 1039 passed, 1 xfailed |
| G4 | +2 | 1041 passed, 1 xfailed |
| G5 | −2 silindi (`test_store.py:54`, `test_memory.py:290`), +1 yeni; `test_fixtures.py` 5→5 net 0 | 1040 passed, 1 xfailed |
| G6 | +2 | 1042 passed, 1 xfailed |
| G7+8 | +3 | 1045 passed, 1 xfailed |
| G9 | +3; **xfail işareti kalkıyor** | 1049 passed |
| G10 | +6 | 1055 passed |
| G11 | +5 | 1060 passed |
| G12 | +4 | 1064 passed |
| G13 | +2 | 1066 passed |
| G14 | +6 | 1072 passed |
| G15 | +5 | 1077 passed |
| G16 | +6 | 1083 passed |
| G17 | 0 | 1083 passed |

**Her sapma o görevin commit mesajında açıklanmalı.** Sayı tutmuyorsa önce planın kaçırdığı bir kırılma aranır — bu plan bir turda üç ayrı sessiz kırılma (`test_memory.py:247`, `tests/test_benchmark.py`'nin dört sahte imzası, Görev 13'ün Görev 5'i kırması) tam olarak böyle yakalandı.
