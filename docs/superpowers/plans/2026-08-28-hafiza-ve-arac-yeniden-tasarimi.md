# Hafıza ve araç yeniden tasarımı uygulama planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fixture-bağımlı iki okuma aracını kaldırıp yerine dinamik RAG araçları (`search_documents`, `query_current_run`, `search_timeline` as risk tool) koymak; MarkItDown ile ikili belge gömme desteği eklemek; Qdrant silme temizliği yapmak.

**Architecture:** Registry'deki 7 araç 5'e düşer (2 fixture araç gider). Yeni 3 okuma aracı (`search_timeline`, `search_documents`, `query_current_run`) registry'ye DEĞİL, ajan içi dispatch'e eklenir — bunlar Python fonksiyonları, action ledger'a yazmaz. Risk analisti 2 turdan 6 tura çıkar (son tur araçsız garanti). Şema sabitleri `episodic.py`'de tanımlanır (circular import'u önler).

**Tech Stack:** Python 3.12+, Qdrant (qdrant-client), Pydantic v2, MarkItDown, pytest

**Spec:** [docs/superpowers/specs/2026-08-28-hafiza-ve-arac-yeniden-tasarimi-design.md](../specs/2026-08-28-hafiza-ve-arac-yeniden-tasarimi-design.md)

## Global Constraints

- Kod İngilizce; insana görünen metin (promptlar, risk seviyeleri, açıklamalar) Türkçe
- Prompt bir enum sayıyorsa değerleri şemadakiyle birebir aynı olmalı
- Çıktı sözleşmesi: `summary` · `events` · `risk` · `actions` — her zaman üretilir
- Model kimlikleri sadece `gozcu/core/config.py`'da
- TDD: önce test, kırmızı olduğunu gör, sonra minimum kod
- `extra="forbid"` olan modellere bilinmeyen alan eklenmez

---

## File Structure

| Dosya | Sorumluluk | Değişiklik |
|---|---|---|
| `pyproject.toml` | Bağımlılık bildirimi | `markitdown` eklenir |
| `gozcu/core/models.py` | Paylaşılan sözleşme | `DocumentResult` modeli eklenir |
| `gozcu/memory/episodic.py` | Epizodik hafıza + belge gömme | `embed_document` imza değişir, `search_documents` eklenir, şema sabitleri eklenir |
| `gozcu/memory/recall.py` | Koşu içi kısa süreli hafıza | `recent()` zaman filtresi eklenir |
| `gozcu/memory/__init__.py` | Re-export'lar | `search_documents` eklenir |
| `gozcu/tools/field_systems.py` | Saha sistemi mock'ları | 2 fixture fonksiyon silinir |
| `gozcu/tools/registry.py` | Araç kaydı | 2 araç çıkar |
| `gozcu/agents/risk.py` | Risk analisti | 6-tur mekanizması, `search_timeline` + `search_documents` araç olarak |
| `gozcu/agents/action_planner.py` | Aksiyon planlayıcı | Fixture araçlar yerine `search_documents` |
| `gozcu/agents/supervisor.py` | Nöbetçi | `query_current_run` + `search_documents` eklenir, `run_memory` parametresi |
| `gozcu/ui/server.py` | Web API | `embed_document` çağrısı `file_path` alır, silme endpoint'i Qdrant cleanup yapar |
| `gozcu/ui/session.py` | Oturum yönetimi | Supervisor'a `run_memory` geçirilir (run.py'den) |
| `gozcu/memory/library.py` | Belge kütüphanesi | `document_context()` yardımcısı eklenir |
| `tests/test_memory.py` | Hafıza testleri | `search_documents`, MarkItDown gömme, Qdrant cleanup testleri |
| `tests/test_tools.py` | Registry testleri | Fixture araç testleri kaldırılır, araç sayısı güncellenir |
| `tests/test_risk.py` | Risk analisti testleri | 6-tur mekanizması, yeni araç referansları |
| `tests/test_action_planner.py` | Aksiyon planlayıcı testleri | Yeni araç referansları |
| `tests/test_recall.py` | RunMemory testleri | Zaman filtresi testleri |

---

### Task 1: MarkItDown bağımlılığı ve `embed_document` imza değişikliği (§2, §12)

**Files:**
- Modify: `pyproject.toml:5` (dependencies listesi)
- Modify: `gozcu/memory/episodic.py:236` (`embed_document` fonksiyonu)
- Modify: `gozcu/ui/server.py:1296` (`post_library_document` endpoint'i)
- Modify: `gozcu/memory/__init__.py` (re-export değişmez ama import kontrol)
- Test: `tests/test_memory.py`

**Interfaces:**
- Consumes: `library.save_document()` → `Document` (mevcut), `library._content_path()` → `Path` (mevcut), `library.document_path()` → `Path` (mevcut)
- Produces: `embed_document(gw, document, file_path: Path, client=None) -> bool` — imza değişikliği, tüm çağıranlar güncellenir

- [ ] **Step 1: Write the failing tests**

`tests/test_memory.py`'ye aşağıdaki testleri ekle. Mevcut `embed_document` testlerini KALDIRMA — onlar bu görevde güncellenecek.

```python
# --- MarkItDown belge gömme (§2) -------------------------------------------

def test_embed_document_accepts_a_file_path_instead_of_bytes():
    """§2e: imza `data: bytes` yerine `file_path: Path` alır."""
    import tempfile
    from pathlib import Path
    from gozcu.core.config import QDRANT_DOCUMENT_COLLECTION
    from gozcu.memory.library import Document

    client, gw = _client(), Mock()
    gw.embed.return_value = _vec(1.0)
    doc = Document(id="abc123", name="talimat.md", size=100,
                   uploaded_at="2026-08-28T10:00:00")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md",
                                     delete=False) as f:
        f.write("Yangın prosedürü: alarm → tahliye → söndürme.")
        path = Path(f.name)
    try:
        result = memory.embed_document(gw, doc, path, client=client)
        assert result is True
        points = client.scroll(QDRANT_DOCUMENT_COLLECTION, limit=10,
                               with_payload=True)[0]
        assert len(points) == 1
        assert "talimat.md" in points[0].payload["name"]
    finally:
        path.unlink(missing_ok=True)


def test_embed_document_uses_markitdown_for_binary_files():
    """§2b: PDF/DOCX gibi ikili dosyalar MarkItDown ile çözülür."""
    import tempfile
    from pathlib import Path
    from unittest.mock import patch as mock_patch
    from gozcu.core.config import QDRANT_DOCUMENT_COLLECTION
    from gozcu.memory.library import Document

    client, gw = _client(), Mock()
    gw.embed.return_value = _vec(1.0)
    doc = Document(id="pdf001", name="ekipman.pdf", size=500,
                   uploaded_at="2026-08-28T10:00:00")
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.4 fake pdf content")
        path = Path(f.name)
    try:
        mock_result = Mock()
        mock_result.text_content = "Forklift bakım kartı: fren, lastik, hidrolik."
        with mock_patch("gozcu.memory.episodic.MarkItDown") as MockMID:
            MockMID.return_value.convert.return_value = mock_result
            result = memory.embed_document(gw, doc, path, client=client)
        assert result is True
        points = client.scroll(QDRANT_DOCUMENT_COLLECTION, limit=10,
                               with_payload=True)[0]
        assert "Forklift bakım kartı" in points[0].payload["text"]
    finally:
        path.unlink(missing_ok=True)


def test_embed_document_falls_back_to_utf8_when_markitdown_fails():
    """§2b: MarkItDown başarısız → UTF-8 decode denensin."""
    import tempfile
    from pathlib import Path
    from unittest.mock import patch as mock_patch
    from gozcu.core.config import QDRANT_DOCUMENT_COLLECTION
    from gozcu.memory.library import Document

    client, gw = _client(), Mock()
    gw.embed.return_value = _vec(1.0)
    doc = Document(id="txt001", name="notlar.txt", size=50,
                   uploaded_at="2026-08-28T10:00:00")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                     delete=False) as f:
        f.write("Basit metin notu.")
        path = Path(f.name)
    try:
        with mock_patch("gozcu.memory.episodic.MarkItDown") as MockMID:
            MockMID.return_value.convert.side_effect = Exception("desteklenmiyor")
            result = memory.embed_document(gw, doc, path, client=client)
        assert result is True
        points = client.scroll(QDRANT_DOCUMENT_COLLECTION, limit=10,
                               with_payload=True)[0]
        assert "Basit metin notu" in points[0].payload["text"]
    finally:
        path.unlink(missing_ok=True)


def test_embed_document_returns_false_when_both_paths_fail():
    """§2b: MarkItDown başarısız + UTF-8 başarısız → False."""
    import tempfile
    from pathlib import Path
    from unittest.mock import patch as mock_patch
    from gozcu.memory.library import Document

    client, gw = _client(), Mock()
    doc = Document(id="bin001", name="data.bin", size=50,
                   uploaded_at="2026-08-28T10:00:00")
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        f.write(bytes(range(256)))
        path = Path(f.name)
    try:
        with mock_patch("gozcu.memory.episodic.MarkItDown") as MockMID:
            MockMID.return_value.convert.side_effect = Exception("binary")
            result = memory.embed_document(gw, doc, path, client=client)
        assert result is False
    finally:
        path.unlink(missing_ok=True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_memory.py::test_embed_document_accepts_a_file_path_instead_of_bytes tests/test_memory.py::test_embed_document_uses_markitdown_for_binary_files tests/test_memory.py::test_embed_document_falls_back_to_utf8_when_markitdown_fails tests/test_memory.py::test_embed_document_returns_false_when_both_paths_fail -v`
Expected: FAIL — `embed_document` still takes `data: bytes`

- [ ] **Step 3: Add `markitdown` dependency**

`pyproject.toml`: add `"markitdown>=0.1.0"` to the `dependencies` list (after `"qdrant-client>=1.12"`).

```toml
    "qdrant-client>=1.12",
    "markitdown>=0.1.0",
```

Run: `uv sync --extra dev`

- [ ] **Step 4: Implement `embed_document` signature change**

`gozcu/memory/episodic.py` — replace the `embed_document` function (line 236):

```python
def embed_document(gw, document, file_path, client=None) -> bool:
    """Yüklenen belgeyi **belge koleksiyonuna** gömer; yazıldıysa `True`.

    **`episodes`'a YAZMIYOR.** Gerekçe `config.QDRANT_DOCUMENT_COLLECTION`'da
    uzun uzun yazılı.

    `embed_episode` ile aynı sözleşme: **istisna atmaz.**

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
        vector = list(gw.embed(f"{document.name} | {text}"))
        if not vector or len(vector) != QDRANT_VECTOR_SIZE:
            return False

        _ensure_collection(target, QDRANT_DOCUMENT_COLLECTION)
        with trace.step("qdrant.belge-yaz", document.id):
            with _LOCK:
                target.upsert(
                    QDRANT_DOCUMENT_COLLECTION,
                    points=[PointStruct(
                        id=str(uuid.uuid5(_NAMESPACE, f"belge:{document.id}")),
                        vector=vector,
                        payload={"document_id": document.id,
                                 "name": document.name,
                                 "text": text})])
        return True
    except Exception:  # noqa: BLE001 — yükleme akışı istisna beklemiyor
        return False
```

Add `_extract_text` helper just above `embed_document`:

```python
def _extract_text(file_path) -> str:
    """Dosyadan metin çıkarır: MarkItDown → UTF-8 geri dönüş."""
    from pathlib import Path
    path = Path(file_path)

    # MarkItDown ile dene
    try:
        from markitdown import MarkItDown
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
```

- [ ] **Step 5: Update `server.py` to pass file path**

`gozcu/ui/server.py` line 1296 — change the `post_library_document` endpoint:

```python
    record = library.save_document(file.filename, data)
    from gozcu.memory.library import _content_path
    embedded = embed_document(_embed_gateway(), record, _content_path(record.id))
```

- [ ] **Step 6: Update existing `embed_document` tests**

In `tests/test_memory.py`, find any existing tests that call `embed_document` with `data: bytes` and update them to pass a file path. Search for `embed_document` calls in the test file — the existing document embedding tests use `data=b"..."`. Write a temporary file in each and pass the path.

- [ ] **Step 7: Run all tests to verify**

Run: `uv run pytest tests/test_memory.py -v -k "embed_document"`
Expected: ALL PASS

- [ ] **Step 8: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: PASS (no regressions)

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml gozcu/memory/episodic.py gozcu/ui/server.py tests/test_memory.py
git commit -m "feat: MarkItDown integration for binary document embedding (§2, §12)"
```

---

### Task 2: `search_documents` fonksiyonu ve `DocumentResult` modeli (§3)

**Files:**
- Modify: `gozcu/core/models.py` (`DocumentResult` eklenir)
- Modify: `gozcu/memory/episodic.py` (`search_documents` fonksiyonu + şema sabitleri)
- Modify: `gozcu/memory/__init__.py` (re-export)
- Modify: `gozcu/memory/library.py` (`document_context()` yardımcısı)
- Test: `tests/test_memory.py`

**Interfaces:**
- Consumes: `gw.embed(query)` (mevcut), `_client()` (mevcut), `QDRANT_DOCUMENT_COLLECTION` (mevcut), `QDRANT_SCORE_THRESHOLD_DIALOGUE` (mevcut), `library.list_documents()` (mevcut)
- Produces:
  - `DocumentResult(document_id: str, name: str, text_excerpt: str, score: float)` — models.py
  - `search_documents(gw, query, top_k=3, threshold=None, client=None) -> list[DocumentResult]` — episodic.py
  - `SEARCH_DOCUMENTS_SCHEMA` — dict, OpenAI function calling format, episodic.py
  - `SEARCH_TIMELINE_SCHEMA` — dict, OpenAI function calling format, episodic.py (moved from supervisor.py)
  - `document_context() -> str` — library.py, gömülü belge listesi prompt parçası

- [ ] **Step 1: Write the failing tests**

`tests/test_memory.py`'ye ekle:

```python
# --- search_documents (§3) -------------------------------------------------

def test_search_documents_returns_matching_documents():
    """§3a: anlamsal arama, skor sıralı sonuç."""
    import tempfile
    from pathlib import Path
    from gozcu.core.config import QDRANT_DOCUMENT_COLLECTION
    from gozcu.core.models import DocumentResult
    from gozcu.memory.library import Document

    client, gw = _client(), Mock()
    gw.embed.side_effect = [_vec(1.0, 0.0), _vec(0.0, 1.0), _vec(0.99, 0.1)]

    for doc_id, name, text in [("d1", "vardiya.xlsx", "Gece vardiyası personeli"),
                                ("d2", "menu.txt", "Kantinde bugün mercimek")]:
        doc = Document(id=doc_id, name=name, size=50,
                       uploaded_at="2026-08-28T10:00:00")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                         delete=False) as f:
            f.write(text)
            path = Path(f.name)
        try:
            memory.embed_document(gw, doc, path, client=client)
        finally:
            path.unlink(missing_ok=True)

    from gozcu.memory.episodic import search_documents
    results = search_documents(gw, "vardiya personeli", client=client)
    assert len(results) >= 1
    assert isinstance(results[0], DocumentResult)
    assert results[0].name == "vardiya.xlsx"
    assert results[0].document_id == "d1"


def test_search_documents_returns_empty_when_collection_missing():
    """Koleksiyon yokken boş liste, istisna değil."""
    from gozcu.memory.episodic import search_documents
    gw = Mock()
    result = search_documents(gw, "herhangi", client=_client())
    assert result == []
    gw.embed.assert_not_called()


def test_search_documents_honours_threshold():
    """§3c: eşik altındaki sonuçlar süzülür."""
    import tempfile
    from pathlib import Path
    from gozcu.memory.library import Document

    client, gw = _client(), Mock()
    gw.embed.side_effect = [_vec(1.0, 0.0), _vec(0.0, 1.0), _vec(1.0, 0.0)]

    for doc_id, name, text in [("d1", "a.txt", "yangın prosedürü"),
                                ("d2", "b.txt", "kantinde kuyruk")]:
        doc = Document(id=doc_id, name=name, size=50,
                       uploaded_at="2026-08-28T10:00:00")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                         delete=False) as f:
            f.write(text)
            path = Path(f.name)
        try:
            memory.embed_document(gw, doc, path, client=client)
        finally:
            path.unlink(missing_ok=True)

    from gozcu.memory.episodic import search_documents
    unfiltered = search_documents(gw, "yangın", client=client)
    assert len(unfiltered) == 2

    gw.embed.side_effect = [_vec(1.0, 0.0)]
    filtered = search_documents(gw, "yangın", threshold=0.5, client=client)
    assert all(r.score >= 0.5 for r in filtered)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_memory.py::test_search_documents_returns_matching_documents tests/test_memory.py::test_search_documents_returns_empty_when_collection_missing tests/test_memory.py::test_search_documents_honours_threshold -v`
Expected: FAIL — `search_documents` does not exist

- [ ] **Step 3: Add `DocumentResult` model**

`gozcu/core/models.py` — add after the `Precedent` class:

```python
class DocumentResult(Base):
    """Belge araması sonucu (§3b)."""
    document_id: str
    name: str
    text_excerpt: str
    score: float
```

- [ ] **Step 4: Add tool schema constants to `episodic.py`**

`gozcu/memory/episodic.py` — add after `_DOCUMENT_EMBED_CHARS = 8000`:

```python
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
```

- [ ] **Step 5: Implement `search_documents`**

`gozcu/memory/episodic.py` — add after `search_timeline`:

```python
def search_documents(gw, query: str, top_k: int = 3,
                     threshold: float | None = None,
                     client=None) -> list:
    """Belge koleksiyonunda anlamsal arama (§3a).

    `search_timeline` ile aynı sözleşme: istisna atmaz, boş liste döner.
    """
    from gozcu.core.models import DocumentResult
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
        if threshold is not None and point.score < threshold:
            continue
        text = payload.get("text", "")
        results.append(DocumentResult(
            document_id=payload.get("document_id", ""),
            name=payload.get("name", ""),
            text_excerpt=text[:500],
            score=point.score))
    return results
```

- [ ] **Step 6: Update `__init__.py` re-exports**

`gozcu/memory/__init__.py`:

```python
from gozcu.memory.episodic import (  # noqa: F401
    SEARCH_DOCUMENTS_SCHEMA,
    SEARCH_TIMELINE_SCHEMA,
    build_client,
    embed_document,
    embed_episode,
    memory_backend,
    point_id,
    search_documents,
    search_timeline,
    video_key,
)
```

- [ ] **Step 7: Add `document_context()` to library.py**

`gozcu/memory/library.py` — add after `list_documents()`:

```python
def document_context() -> str:
    """Gömülü belge listesini prompt parçası olarak döndürür (§3e).

    Yalnız `embedded: True` olan belgeler listelenir. Belge yoksa boş dize.
    """
    docs = [d for d in list_documents() if d.embedded]
    if not docs:
        return ""
    lines = ["YÜKLÜ BELGELER (search_documents aracıyla erişilebilir):"]
    for i, doc in enumerate(docs, 1):
        lines.append(f'{i}. "{doc.name}"')
    return "\n".join(lines)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/test_memory.py -v -k "search_documents"`
Expected: ALL PASS

- [ ] **Step 9: Commit**

```bash
git add gozcu/core/models.py gozcu/memory/episodic.py gozcu/memory/__init__.py gozcu/memory/library.py tests/test_memory.py
git commit -m "feat: search_documents function and DocumentResult model (§3)"
```

---

### Task 3: Qdrant vektör temizliği ve `RunMemory.recent()` zaman filtresi (§4, §5e)

**Files:**
- Modify: `gozcu/ui/server.py:1342` (silme endpoint'i)
- Modify: `gozcu/memory/recall.py:65` (`recent()` filtresi)
- Test: `tests/test_memory.py` (Qdrant cleanup)
- Create: `tests/test_recall.py` (zaman filtresi)

**Interfaces:**
- Consumes: `episodic._NAMESPACE` (mevcut), `QDRANT_DOCUMENT_COLLECTION` (mevcut), `_documents_handle` (mevcut), `episodic._client()` (mevcut)
- Produces:
  - `recent(self, n=None, *, from_ts=None, to_ts=None) -> list[WindowNote]` — recall.py genişletilmiş imza
  - Silme endpoint'inde Qdrant cleanup — server.py

- [ ] **Step 1: Write the failing tests for Qdrant cleanup**

`tests/test_memory.py`'ye ekle:

```python
# --- Qdrant cleanup on delete (§4) -----------------------------------------

def test_qdrant_vector_is_deleted_when_document_is_removed():
    """§4b: silme endpoint'i Qdrant'taki vektörü de temizler."""
    import tempfile, uuid
    from pathlib import Path
    from gozcu.core.config import QDRANT_DOCUMENT_COLLECTION
    from gozcu.memory.library import Document

    client, gw = _client(), Mock()
    gw.embed.return_value = _vec(1.0)
    doc_id = uuid.uuid4().hex
    doc = Document(id=doc_id, name="silinecek.txt", size=50,
                   uploaded_at="2026-08-28T10:00:00")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                     delete=False) as f:
        f.write("Bu belge silinecek.")
        path = Path(f.name)
    try:
        memory.embed_document(gw, doc, path, client=client)
    finally:
        path.unlink(missing_ok=True)

    points_before = client.scroll(QDRANT_DOCUMENT_COLLECTION, limit=10)[0]
    assert len(points_before) == 1

    from gozcu.memory.episodic import delete_document_vector
    delete_document_vector(doc_id, client=client)

    points_after = client.scroll(QDRANT_DOCUMENT_COLLECTION, limit=10)[0]
    assert len(points_after) == 0


def test_qdrant_cleanup_is_graceful_when_collection_missing():
    """§4b: koleksiyon yoksa hata değil."""
    from gozcu.memory.episodic import delete_document_vector
    delete_document_vector("nonexistent", client=_client())
```

- [ ] **Step 2: Write the failing tests for `RunMemory.recent()` time filter**

`tests/test_recall.py` (yeni dosya):

```python
"""RunMemory zaman filtresi testleri (§5e)."""

from gozcu.memory.recall import RunMemory


def test_recent_filters_by_from_ts():
    mem = RunMemory(limit=10)
    mem.note(ts=5.0, moment="birinci")
    mem.note(ts=15.0, moment="ikinci")
    mem.note(ts=25.0, moment="üçüncü")

    result = mem.recent(from_ts=10.0)
    assert [n.moment for n in result] == ["ikinci", "üçüncü"]


def test_recent_filters_by_to_ts():
    mem = RunMemory(limit=10)
    mem.note(ts=5.0, moment="birinci")
    mem.note(ts=15.0, moment="ikinci")
    mem.note(ts=25.0, moment="üçüncü")

    result = mem.recent(to_ts=20.0)
    assert [n.moment for n in result] == ["birinci", "ikinci"]


def test_recent_filters_by_both_from_and_to():
    mem = RunMemory(limit=10)
    mem.note(ts=5.0, moment="birinci")
    mem.note(ts=15.0, moment="ikinci")
    mem.note(ts=25.0, moment="üçüncü")

    result = mem.recent(from_ts=10.0, to_ts=20.0)
    assert [n.moment for n in result] == ["ikinci"]


def test_recent_time_filter_still_pins_incidents():
    mem = RunMemory(limit=2)
    mem.note(ts=1.0, moment="büyük olay", severity="olay")
    mem.note(ts=10.0, moment="rutin pencere")
    mem.note(ts=20.0, moment="son pencere")

    result = mem.recent(from_ts=8.0)
    moments = [n.moment for n in result]
    assert "büyük olay" in moments, "olay pin'i zaman filtresinden geçmeli"
    assert "son pencere" in moments


def test_recent_without_time_filter_is_unchanged():
    mem = RunMemory(limit=2)
    mem.note(ts=5.0, moment="birinci")
    mem.note(ts=15.0, moment="ikinci")
    mem.note(ts=25.0, moment="üçüncü")

    result = mem.recent()
    assert [n.moment for n in result] == ["ikinci", "üçüncü"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_memory.py::test_qdrant_vector_is_deleted_when_document_is_removed tests/test_memory.py::test_qdrant_cleanup_is_graceful_when_collection_missing tests/test_recall.py -v`
Expected: FAIL — `delete_document_vector` does not exist, `recent()` has no `from_ts`/`to_ts`

- [ ] **Step 4: Implement `delete_document_vector`**

`gozcu/memory/episodic.py` — add after `embed_document`:

```python
def delete_document_vector(doc_id: str, client=None) -> None:
    """Belgenin Qdrant vektörünü siler (§4b). İstisna atmaz."""
    try:
        target = _client(client if client is not None else _documents_handle)
        if target is None:
            return
        with _LOCK:
            if not target.collection_exists(QDRANT_DOCUMENT_COLLECTION):
                return
        pid = str(uuid.uuid5(_NAMESPACE, f"belge:{doc_id}"))
        from qdrant_client.models import PointIdsList
        with _LOCK:
            target.delete(
                collection_name=QDRANT_DOCUMENT_COLLECTION,
                points_selector=PointIdsList(points=[pid]))
    except Exception:  # noqa: BLE001
        pass
```

- [ ] **Step 5: Wire cleanup into server.py delete endpoint**

`gozcu/ui/server.py` — update `delete_library_document` (line 1342):

```python
@app.delete("/api/library/documents/{doc_id}")
def delete_library_document(doc_id: str) -> dict:
    """Belgeyi siler. Zaten yoksa `404`."""
    if not library.delete_document(doc_id):
        raise HTTPException(status_code=404, detail=DOCUMENT_NOT_FOUND)
    from gozcu.memory.episodic import delete_document_vector
    delete_document_vector(doc_id)
    return {"deleted": True}
```

- [ ] **Step 6: Implement `RunMemory.recent()` time filter**

`gozcu/memory/recall.py` — update `recent()` method:

```python
    def recent(self, n: int | None = None, *,
               from_ts: float | None = None,
               to_ts: float | None = None) -> list[WindowNote]:
        """Kalıcı olaylar + son N pencere, zaman sırasında ve tekrarsız.

        `from_ts`/`to_ts` verilmişse zaman filtresi uygulanır; pin'ler
        filtreden muaf — olay her zaman görünür (§5e).
        """
        limit = self.limit if n is None else n
        notes = self._notes

        if from_ts is not None or to_ts is not None:
            filtered = [note for note in notes
                        if (from_ts is None or note.ts >= from_ts)
                        and (to_ts is None or note.ts <= to_ts)]
        else:
            filtered = notes

        pinned_notes = [note for note in self._notes
                        if note.severity == INCIDENT]
        latest_notes = filtered[-limit:] if limit else []
        selected = {id(note): note for note in (*pinned_notes, *latest_notes)}
        return sorted(selected.values(), key=lambda note: note.ts)
```

- [ ] **Step 7: Add re-export for `delete_document_vector`**

`gozcu/memory/__init__.py` — add `delete_document_vector` to the import:

```python
from gozcu.memory.episodic import (  # noqa: F401
    SEARCH_DOCUMENTS_SCHEMA,
    SEARCH_TIMELINE_SCHEMA,
    build_client,
    delete_document_vector,
    embed_document,
    embed_episode,
    memory_backend,
    point_id,
    search_documents,
    search_timeline,
    video_key,
)
```

- [ ] **Step 8: Run tests**

Run: `uv run pytest tests/test_memory.py tests/test_recall.py -v`
Expected: ALL PASS

- [ ] **Step 9: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add gozcu/memory/episodic.py gozcu/memory/recall.py gozcu/memory/__init__.py gozcu/ui/server.py tests/test_memory.py tests/test_recall.py
git commit -m "feat: Qdrant vector cleanup on delete + RunMemory time filter (§4, §5e)"
```

---

### Task 4: Fixture araçları kaldır + registry güncelle (§1a, §8a, §8b)

**Files:**
- Modify: `gozcu/tools/field_systems.py:150-180` (2 fonksiyon silinir)
- Modify: `gozcu/tools/registry.py:13` (`TOOLS` dict), `registry.py:43` (`_TOOL_SPECS`)
- Modify: `tests/test_tools.py` (fixture araç testleri kaldırılır)
- Modify: `tests/test_action_planner.py:148` (`offered` assertion güncellenir)

**Interfaces:**
- Consumes: Yok (kaldırma işi)
- Produces: `TOOLS` dict'i 5 araç, `TOOL_SCHEMAS` 5 şema — registry.py

- [ ] **Step 1: Update the registry tests FIRST**

`tests/test_tools.py` — şu testleri tamamen kaldır:
- `test_the_roster_is_scoped_to_the_shift_that_owns_the_query_time` (line 193)
- `test_equipment_history_derives_the_overdue_months_instead_of_reading_a_key` (line 204)
- `test_unknown_equipment_returns_a_flag_not_an_exception` (line 215)

`test_schemas_cover_every_registered_tool` (line 223) zaten `set(TOOLS)` ile karşılaştırıyor — 5'e düşünce otomatik olarak doğru. Dokunmaya gerek yok.

- [ ] **Step 2: Update `test_action_planner.py` planner read tools assertion**

`tests/test_action_planner.py` line 148 — `offered` assertion'ı güncelle:

```python
    # Bu test Task 6'da (action_planner güncellemesi) son şeklini alacak.
    # Şimdilik fixture araçlar hâlâ READ_TOOLS'da ise kırmızı olmalı.
```

**NOT:** Bu assertion Task 6'da tam güncellenecek. Şimdilik fixture araç adlarını kaldırıp testi geçici olarak boş bırakmayın — bu test Task 6'nın doğruluğunu koruyor.

- [ ] **Step 3: Run tests to verify the assertions that reference fixture tools fail**

Run: `uv run pytest tests/test_tools.py -v`
Expected: Tests that call `query_shift_personnel` or `query_equipment_history` will fail after removal

- [ ] **Step 4: Remove fixture functions from `field_systems.py`**

`gozcu/tools/field_systems.py` — delete `query_shift_personnel` (line 150) and `query_equipment_history` (line 168) functions completely. Keep the imports needed by the remaining 5 functions (zone resolution, protocols, etc.).

- [ ] **Step 5: Remove from `registry.py`**

`gozcu/tools/registry.py`:
- `TOOLS` dict (line 13): remove `"query_shift_personnel"` and `"query_equipment_history"` entries
- `_TOOL_SPECS` dict (line 43): remove entries for these two tools

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_tools.py -v`
Expected: PASS (5 tools instead of 7, fixture tests removed)

- [ ] **Step 7: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: `test_action_planner.py::test_planner_is_offered_only_read_tools` will FAIL (expected — Task 6 fixes it). All other tests PASS.

- [ ] **Step 8: Commit**

```bash
git add gozcu/tools/field_systems.py gozcu/tools/registry.py tests/test_tools.py
git commit -m "refactor: remove fixture read tools from registry (§1a, §8a, §8b)"
```

---

### Task 5: Risk analisti overhaul — 6-tur mekanizması + `search_timeline`/`search_documents` araç (§1e, §6, §8c, §7a)

**Files:**
- Modify: `gozcu/agents/risk.py` (tüm araç deseni yeniden yazılır)
- Modify: `tests/test_risk.py` (yeni araç referansları, 6-tur testleri)

**Interfaces:**
- Consumes: `SEARCH_TIMELINE_SCHEMA` ve `SEARCH_DOCUMENTS_SCHEMA` (Task 2'den, `gozcu.memory.episodic`), `search_timeline()` (mevcut), `search_documents()` (Task 2'den), `document_context()` (Task 2'den), `QDRANT_SCORE_THRESHOLD_RISK` (mevcut)
- Produces:
  - `RISK_TOOLS = ("search_timeline", "search_documents")` — risk.py
  - `RISK_TOOL_SCHEMAS = [SEARCH_TIMELINE_SCHEMA, SEARCH_DOCUMENTS_SCHEMA]` — risk.py
  - `MAX_TOOL_ROUNDS = 5` — risk.py
  - `assess_risk(gw, store, episode) -> RiskAssessment` — imza aynı, davranış değişir

- [ ] **Step 1: Write the failing tests for the 6-turn mechanism**

`tests/test_risk.py`'ye ekle. Önce import'ları güncelle — `READ_TOOLS` artık olmayacak, `RISK_TOOLS` gelecek:

```python
# tests/test_risk.py — yeni testler

def test_risk_analyst_uses_search_timeline_as_a_tool():
    """§6b: search_timeline artık model aracı olarak çağrılır."""
    store = Store(":memory:")
    e = _ep(store)

    gw = _investigating_gw(
        _tool_call("search_timeline", query="devrilme"),
        final=RESPONSE_JSON)

    with _archive_patch([]):
        assessment = assess_risk(gw, store, e)

    assert gw.ask.call_count == 2
    assert assessment.level == "Kritik"


def test_risk_analyst_can_call_search_documents():
    """§1d: risk analisti search_documents aracını kullanabilir."""
    store = Store(":memory:")
    e = _ep(store)

    gw = _investigating_gw(
        _tool_call("search_documents", query="ekipman bakım"),
        final=RESPONSE_JSON)

    with _archive_patch([]):
        assessment = assess_risk(gw, store, e)

    assert gw.ask.call_count == 2
    assert assessment.level == "Kritik"


def test_risk_analyst_iterates_up_to_five_tool_rounds():
    """§1e: model 5 araç turu yapabilir, 6. tur araçsız."""
    store = Store(":memory:")
    e = _ep(store)

    responses = []
    for _ in range(5):
        responses.append(Response(
            tool_calls=[_tool_call("search_timeline", query="olay")]))
    responses.append(Response(content=RESPONSE_JSON))

    gw = Mock()
    gw.ask.side_effect = responses

    with _archive_patch([]):
        assessment = assess_risk(gw, store, e)

    assert gw.ask.call_count == 6
    assert assessment.level == "Kritik"


def test_risk_analyst_sixth_round_has_no_tools():
    """§1e: 6. tur (güvenlik ağı) araçsız — yapısal garanti."""
    store = Store(":memory:")
    e = _ep(store)

    responses = []
    for _ in range(5):
        responses.append(Response(
            tool_calls=[_tool_call("search_timeline", query="x")]))
    responses.append(Response(content=RESPONSE_JSON))

    gw = Mock()
    gw.ask.side_effect = responses

    with _archive_patch([]):
        assess_risk(gw, store, e)

    last_call = gw.ask.call_args_list[-1]
    assert "tools" not in last_call.kwargs, \
        "6. tur araçsız olmalı — güvenlik ağı"


def test_risk_analyst_early_exit_when_no_tool_called():
    """§1e: model araç çağırmazsa döngü biter, değerlendirme alınır."""
    store = Store(":memory:")
    e = _ep(store)

    gw = _gw(RESPONSE_JSON)
    with _archive_patch([]):
        assessment = assess_risk(gw, store, e)

    assert gw.ask.call_count == 1
    assert assessment.level == "Kritik"


def test_risk_analyst_prompt_has_no_archive_injection():
    """§7a: ARSIV: enjeksiyonu kaldırıldı — arşiv araç olarak erişilir."""
    store = Store(":memory:")
    e = _ep(store)

    gw = _gw(RESPONSE_JSON)
    with _archive_patch([]):
        assess_risk(gw, store, e)

    prompt_text = _text(gw, 0)
    assert "ARŞİV:" not in prompt_text
    assert "ARSIV:" not in prompt_text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_risk.py::test_risk_analyst_uses_search_timeline_as_a_tool tests/test_risk.py::test_risk_analyst_iterates_up_to_five_tool_rounds tests/test_risk.py::test_risk_analyst_sixth_round_has_no_tools tests/test_risk.py::test_risk_analyst_prompt_has_no_archive_injection -v`
Expected: FAIL

- [ ] **Step 3: Implement risk analyst overhaul**

`gozcu/agents/risk.py` — replace `READ_TOOLS`, `READ_TOOL_SCHEMAS`, `_run_tool_calls`, `_prompt`, and `assess_risk`:

**Constants (replace `READ_TOOLS` and `READ_TOOL_SCHEMAS`):**

```python
from gozcu.memory.episodic import (SEARCH_DOCUMENTS_SCHEMA,
                                    SEARCH_TIMELINE_SCHEMA,
                                    search_documents, search_timeline)
from gozcu.memory.library import document_context

RISK_TOOLS = ("search_timeline", "search_documents")
RISK_TOOL_SCHEMAS = [SEARCH_TIMELINE_SCHEMA, SEARCH_DOCUMENTS_SCHEMA]

MAX_TOOL_ROUNDS = 5
```

**Remove** the old import `from gozcu.memory import search_timeline` and `from gozcu.tools.registry import TOOL_SCHEMAS, call_tool`. Keep `from gozcu.tools.registry import call_tool` if still used elsewhere, but since risk analyst no longer calls registry tools, remove the `TOOL_SCHEMAS` import.

**`_run_tool_calls`** — rewrite to dispatch `search_timeline` and `search_documents` directly (NOT through `call_tool`):

```python
def _run_tool_calls(store, calls: list[dict], ts: float,
                    episode=None) -> list[dict]:
    """Okuma araçlarını çalıştırır — registry DEĞİL, doğrudan Python."""
    from gozcu.core.config import QDRANT_SCORE_THRESHOLD_RISK
    messages = []
    for call in calls:
        name, params = _call_arguments(call)
        if name == "search_timeline":
            exclude = ((episode.source, episode.id)
                       if episode is not None and episode.id is not None
                       else None)
            found = search_timeline(
                store,  # _client() handle olarak geçer
                store, params.get("query", ""),
                exclude=exclude,
                threshold=QDRANT_SCORE_THRESHOLD_RISK)
            result = {"results": [{"summary_tr": p.episode.summary_tr,
                                    "participants": p.episode.participants,
                                    "score": round(p.score, 3)}
                                   for p in found]}
        elif name == "search_documents":
            found = search_documents(
                store,  # gw handle — embed çağrısı store'dan değil gw'den
                params.get("query", ""), client=store)
            result = {"results": [{"name": r.name,
                                    "text_excerpt": r.text_excerpt,
                                    "score": round(r.score, 3)}
                                   for r in found]}
        else:
            result = {"tool_name": name, "refused": True,
                      "reason": REFUSAL_REASON}
        messages.append({"role": "tool", "tool_call_id": call.get("id", ""),
                         "name": name,
                         "content": json.dumps(result, ensure_ascii=False,
                                               default=str)})
    return messages
```

**IMPORTANT NOTE for the implementer:** The `_run_tool_calls` above shows the CONCEPT. The actual `gw` parameter must come from `assess_risk`'s scope, not `store`. The `search_timeline(gw, store, ...)` and `search_documents(gw, ...)` calls need the gateway for embedding. Adjust the function signature to accept `gw` as well:

```python
def _run_tool_calls(gw, store, calls, ts, episode=None):
```

And call `search_timeline(gw, store, ...)` and `search_documents(gw, ..., client=store)`.

**`_prompt`** — remove `history_text` parameter, add document context:

```python
def _prompt(episode: Episode, correction_text: str) -> str:
    participants = ", ".join(episode.participants) or "(bilinmiyor)"
    if episode.summary_source == "fallback":
        if episode.beats:
            lines = ["OLAY: (olay tarifi üretilemedi; aşağıdaki ham anlara dayan)"]
            lines += [f"- {mmss(beat.ts)} {beat.text}" for beat in episode.beats]
        else:
            lines = ["OLAY: (olay tarifi üretilemedi)"]
    else:
        lines = [f"OLAY: {episode.summary_tr}"]
    lines += [f"ÖN RİSK: {episode.preliminary_risk}",
              f"KATILIMCILAR (ekipman/personel kimlikleri): {participants}"]
    if correction_text:
        lines.append(correction_text)
    doc_ctx = document_context()
    if doc_ctx:
        lines.append(f"\n{doc_ctx}")
    return "\n".join(lines)
```

**`assess_risk`** — 6-turn loop:

```python
def assess_risk(gw, store, episode: Episode) -> RiskAssessment:
    corrections = store.corrections(episode.id) if episode.id else []
    correction_text = "\n".join(
        f"- OPERATÖR DÜZELTMESİ — {c.field}: '{c.old}' yerine '{c.new}'"
        for c in corrections)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",
         "content": _prompt(episode, correction_text)},
    ]

    now = episode.end_ts or episode.start_ts

    # 6-turn loop: turns 1-5 with tools, turn 6 without (safety net)
    response = None
    for turn in range(MAX_TOOL_ROUNDS + 1):
        is_last = (turn == MAX_TOOL_ROUNDS)
        if is_last:
            response = gw.ask("main", messages, schema=_RiskResponse,
                              max_tokens=RISK_MAX_TOKENS)
        else:
            response = gw.ask("main", messages, schema=_RiskResponse,
                              tools=RISK_TOOL_SCHEMAS,
                              max_tokens=RISK_MAX_TOKENS)
            if response.degraded:
                break
            calls = _tool_calls(response)
            if not calls:
                break
            results = _run_tool_calls(gw, store, calls, ts=now,
                                       episode=episode)
            messages = [*messages, _assistant_turn(response), *results]

    parsed = _read_assessment(response, episode)

    assessment = RiskAssessment(
        episode_id=episode.id, ts=now, level=parsed.level,
        rationale_tr=parsed.rationale_tr, preventable=parsed.preventable,
        precedents=[])
    assessment.id = store.save_risk(assessment)
    return assessment
```

**SYSTEM_PROMPT** — update to mention tool usage:

Replace the `ARSIV KAYITLARI hakkında:` and `query_shift_personnel`/`query_equipment_history` references with:

```
ARAÇLARIN:
- search_timeline: geçmiş olay arşivinde arama. Benzer olaylar olmuş mu bak.
- search_documents: operatörün yüklediği belgelerde arama. Ekipman kartı,
  vardiya listesi, prosedür gibi belgelerden bilgi çek.

ÖNCE ARAŞTIR:
1. Olaydaki ekipman/personel hakkında arşivde ve belgelerde bilgi ara
2. Yeterli bilgi topladığında değerlendir — gereksiz yere döngüye girme
```

- [ ] **Step 4: Update existing tests in `test_risk.py`**

- Import `RISK_TOOLS` instead of `READ_TOOLS`
- Update `_archive_patch` — since `assess_risk` no longer calls `search_timeline` hardcoded, the patch target changes. The mock should now be on the dispatch inside `_run_tool_calls` or the tests should use `_investigating_gw` which mocks `gw.ask`
- Update tests that reference `READ_TOOLS`

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_risk.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add gozcu/agents/risk.py tests/test_risk.py
git commit -m "feat: risk analyst 6-turn tool loop with search_timeline + search_documents (§1e, §6, §8c, §7a)"
```

---

### Task 6: Action planner update (§8d, §7b)

**Files:**
- Modify: `gozcu/agents/action_planner.py` (araç seti güncellenir)
- Modify: `tests/test_action_planner.py` (assertion'lar güncellenir)

**Interfaces:**
- Consumes: `SEARCH_DOCUMENTS_SCHEMA` (Task 2'den), `search_documents()` (Task 2'den), `document_context()` (Task 2'den), `TOOL_SCHEMAS` (mevcut — 5 aksiyon), `TOOLS` (mevcut — 5 araç)
- Produces:
  - `PLANNER_READ_TOOLS = ("search_documents",)` — action_planner.py
  - `PLANNER_TOOL_SCHEMAS = [SEARCH_DOCUMENTS_SCHEMA]` — action_planner.py
  - `plan_actions(gw, store, episode, assessment) -> ActionPlan` — imza aynı, araç seti değişir

- [ ] **Step 1: Write/update the failing test**

`tests/test_action_planner.py` — `test_planner_is_offered_only_read_tools` (line 127) assertion'ı güncelle:

```python
def test_planner_is_offered_only_read_tools(store):
    """Yazma araçları bu ajana KAPALI (spec §2e). Fixture araçları yerine
    search_documents sunuluyor."""
    seen = {}

    class _GW:
        def ask(self, tier, messages, **kwargs):
            seen["tools"] = kwargs.get("tools", [])
            class _R:
                content = "bu JSON değil"
                degraded = False
                tool_calls = []
            return _R()

    episode = _episode(store)
    plan_actions(_GW(), store, episode, _assessment(store, episode))
    offered = {s["function"]["name"] for s in seen["tools"]}
    assert offered == {"search_documents"}
```

Also update `test_tool_call_is_executed_and_triggers_a_second_gateway_round` (line 191) — change the tool call from `query_shift_personnel` to `search_documents`:

```python
def test_tool_call_is_executed_and_triggers_a_second_gateway_round(store):
    episode = _episode(store)
    assessment = _assessment(store, episode)
    final = json.dumps({
        "protocol_id": "PRT-B-CARPMA", "rationale_tr": "gerekçe",
        "proposed_actions": [{"description_tr": "Sağlık ekibini çağır",
                              "tool_name": "dispatch_medical", "params": {}}]})
    gw = _investigating_gw(
        _tool_call("search_documents", query="ekipman bakım"),
        final=final)

    plan = plan_actions(gw, store, episode, assessment)

    assert gw.ask.call_count == 2
    assert "tools" not in gw.ask.call_args_list[1].kwargs
    assert plan.plan_source == "model"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_action_planner.py::test_planner_is_offered_only_read_tools tests/test_action_planner.py::test_tool_call_is_executed_and_triggers_a_second_gateway_round -v`
Expected: FAIL — still offering fixture tools

- [ ] **Step 3: Implement action planner update**

`gozcu/agents/action_planner.py`:

**Replace constants:**

```python
from gozcu.memory.episodic import SEARCH_DOCUMENTS_SCHEMA, search_documents
from gozcu.memory.library import document_context

PLANNER_READ_TOOLS = ("search_documents",)
PLANNER_TOOL_SCHEMAS = [SEARCH_DOCUMENTS_SCHEMA]
```

**Replace `_run_tool_calls`** — dispatch `search_documents` directly instead of through `call_tool`:

```python
def _run_tool_calls(gw, store, calls: list[dict], ts: float) -> list[dict]:
    """Okuma araçlarını çalıştırır — search_documents doğrudan Python."""
    messages = []
    for call in calls:
        name, params = _call_arguments(call)
        if name in PLANNER_READ_TOOLS:
            if name == "search_documents":
                found = search_documents(gw, params.get("query", ""),
                                          client=store)
                result = {"results": [{"name": r.name,
                                        "text_excerpt": r.text_excerpt,
                                        "score": round(r.score, 3)}
                                       for r in found]}
            else:
                result = {"tool_name": name, "error": "bilinmeyen araç"}
        else:
            result = {"tool_name": name, "refused": True,
                      "reason": REFUSAL_REASON}
        messages.append({"role": "tool", "tool_call_id": call.get("id", ""),
                         "name": name,
                         "content": json.dumps(result, ensure_ascii=False,
                                               default=str)})
    return messages
```

**Update `_run_tool_calls` call site in `plan_actions`** — pass `gw` as first argument.

**Update SYSTEM_PROMPT** — replace fixture tool references with `search_documents` and add document context. The `{tools}` placeholder that injects all 5 action tool descriptions via `_describe_tool` stays — that's the action catalogue. Add document context:

In the prompt template, add after tool descriptions:
```
{doc_context}
```

In `plan_actions`, compute:
```python
doc_ctx = document_context()
```

And pass it to the prompt formatting.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_action_planner.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add gozcu/agents/action_planner.py tests/test_action_planner.py
git commit -m "feat: action planner uses search_documents instead of fixture tools (§8d, §7b)"
```

---

### Task 7: Supervisor update — `query_current_run` + `search_documents` + `run_memory` (§5b-d, §1d, §3e, §7c)

**Files:**
- Modify: `gozcu/agents/supervisor.py` (yeni araçlar, `run_memory` parametresi)
- Modify: `gozcu/ui/session.py:64` (Supervisor'a `run_memory` geçirilmez — `run_memory` `run.py`'de yaratılıyor, session'da değil)
- Modify: `gozcu/pipeline/run.py` (Supervisor'a `run_memory` geçirilir)
- Test: `tests/test_supervisor.py` (varsa güncellenir)

**Interfaces:**
- Consumes: `RunMemory` (mevcut), `SEARCH_DOCUMENTS_SCHEMA` (Task 2'den), `search_documents()` (Task 2'den), `document_context()` (Task 2'den)
- Produces:
  - `Supervisor.__init__(self, gw, store, source=None, run_memory=None)` — genişletilmiş imza
  - `QUERY_CURRENT_RUN` sabit + şema — supervisor.py
  - `SEARCH_DOCUMENTS` sabit — supervisor.py
  - `_internal_tool` dispatch'inde `QUERY_CURRENT_RUN` ve `SEARCH_DOCUMENTS` dalları

- [ ] **Step 1: Write the failing tests**

Bir `tests/test_supervisor.py` varsa orada, yoksa bu testler supervisor davranışını kontrol eden bir dosyaya eklenir. Mevcut supervisor testlerini kontrol et.

```python
# tests/test_supervisor.py veya mevcut dosyaya ekle

def test_query_current_run_returns_window_notes():
    """§5b: query_current_run RunMemory'den pencere notlarını döndürür."""
    from gozcu.agents.supervisor import Supervisor, QUERY_CURRENT_RUN
    from gozcu.memory.recall import RunMemory
    from unittest.mock import Mock

    gw, store = Mock(), Mock()
    store.open_episode.return_value = None
    mem = RunMemory(limit=10)
    mem.note(ts=10.0, moment="Forklift hareketli", participants=["IST-04"],
             decision="investigate", severity="dikkat")
    mem.note(ts=20.0, moment="Çarpma gerçekleşti", participants=["IST-04", "PRS-001"],
             decision="escalate", severity="olay")

    sup = Supervisor(gw, store, run_memory=mem)
    result = sup._internal_tool(QUERY_CURRENT_RUN, {})

    assert "notes" in result
    assert len(result["notes"]) == 2
    assert "Forklift hareketli" in result["notes"][0]


def test_query_current_run_with_time_filter():
    """§5c: from_s/to_s filtresi çalışır."""
    from gozcu.agents.supervisor import Supervisor, QUERY_CURRENT_RUN
    from gozcu.memory.recall import RunMemory
    from unittest.mock import Mock

    gw, store = Mock(), Mock()
    store.open_episode.return_value = None
    mem = RunMemory(limit=10)
    mem.note(ts=5.0, moment="birinci")
    mem.note(ts=15.0, moment="ikinci")
    mem.note(ts=25.0, moment="üçüncü")

    sup = Supervisor(gw, store, run_memory=mem)
    result = sup._internal_tool(QUERY_CURRENT_RUN, {"from_s": 10.0, "to_s": 20.0})

    assert len(result["notes"]) == 1
    assert "ikinci" in result["notes"][0]


def test_query_current_run_without_memory():
    """§5d: run_memory yoksa (None) bilgilendirici mesaj döner."""
    from gozcu.agents.supervisor import Supervisor, QUERY_CURRENT_RUN
    from unittest.mock import Mock

    sup = Supervisor(Mock(), Mock())
    result = sup._internal_tool(QUERY_CURRENT_RUN, {})

    assert "henüz" in result.get("message", "").lower() or result.get("notes") == []


def test_search_documents_is_in_supervisor_tool_schemas():
    """§1d: supervisor search_documents aracına sahip."""
    from gozcu.agents.supervisor import ALL_TOOL_SCHEMAS
    names = {s["function"]["name"] for s in ALL_TOOL_SCHEMAS}
    assert "search_documents" in names
    assert "query_current_run" in names
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_supervisor.py -v -k "query_current_run or search_documents_is_in"`
Expected: FAIL — no `QUERY_CURRENT_RUN` constant, no `run_memory` parameter

- [ ] **Step 3: Implement supervisor changes**

`gozcu/agents/supervisor.py`:

**Add constants (after `GENERATE_ROOT_CAUSE_REPORT`):**

```python
SEARCH_DOCUMENTS = "search_documents"
QUERY_CURRENT_RUN = "query_current_run"
```

**Add tool schemas to `SUPERVISOR_TOOLS`:**

```python
from gozcu.memory.episodic import SEARCH_DOCUMENTS_SCHEMA
from gozcu.memory.episodic import search_documents
from gozcu.memory.library import document_context

SUPERVISOR_TOOLS = [
    # ... existing 4 tools stay ...
    {"type": "function", "function": {
        "name": SEARCH_DOCUMENTS,
        "description": "Operatörün yüklediği referans belgelerinde anlamsal "
                       "arama yapar.",
        "parameters": {"type": "object",
                       "properties": {"query": {"type": "string"}},
                       "required": ["query"]}}},
    {"type": "function", "function": {
        "name": QUERY_CURRENT_RUN,
        "description": "Bu koşudaki pencere gözlemlerini döndürür. "
                       "Mevcut videoda ne olduğunu sorgular.",
        "parameters": {"type": "object",
                       "properties": {
                           "from_s": {"type": "number",
                                      "description": "Başlangıç saniyesi"},
                           "to_s": {"type": "number",
                                    "description": "Bitiş saniyesi"}},
                       "required": []}}},
]
```

**Update `__init__`:**

```python
def __init__(self, gw, store, source=None, run_memory=None):
    # ... existing init code ...
    self.run_memory = run_memory
```

**Add dispatch branches in `_internal_tool`:**

```python
        if name == SEARCH_DOCUMENTS:
            found = search_documents(self.gw, params["query"],
                                      client=self.store)
            return {"results": [{"name": r.name,
                                  "text_excerpt": r.text_excerpt,
                                  "score": round(r.score, 3)}
                                 for r in found]}
        if name == QUERY_CURRENT_RUN:
            if self.run_memory is None:
                return {"message": "Bu koşuda henüz gözlem kaydı yok.",
                        "notes": []}
            from_s = params.get("from_s")
            to_s = params.get("to_s")
            notes = self.run_memory.recent(from_ts=from_s, to_ts=to_s)
            return {"notes": [
                f"{int(n.ts // 60):02d}:{int(n.ts % 60):02d}"
                f"{' [' + ', '.join(n.participants) + ']' if n.participants else ''}"
                f" {n.moment}"
                for n in notes]}
```

**Update SYSTEM_PROMPT** — add `search_documents` and `query_current_run` descriptions and document context.

- [ ] **Step 4: Wire `run_memory` in `run.py`**

`gozcu/pipeline/run.py` — the `nobetci` (Supervisor) is passed as a parameter to `run_pipeline`, created in `session.py`. The `run_memory` is created inside `run_pipeline` (line 534). After `run_memory` is created, set it on the supervisor:

After line 534 (`run_memory = RunMemory()`), add:

```python
    if nobetci is not None:
        nobetci.run_memory = run_memory
```

This avoids changing `session.py`'s Supervisor construction — `run_memory` is `None` at construction time, set when the run starts.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 6: Close PR #5**

Run: `gh pr close 5 --comment "Replaced by query_current_run (RunMemory-based) — see spec §13"`
Delete the branch: `git push origin --delete fix/supervisor-kosu-zaman-cizelgesi`

- [ ] **Step 7: Commit**

```bash
git add gozcu/agents/supervisor.py gozcu/pipeline/run.py tests/
git commit -m "feat: supervisor gains query_current_run + search_documents (§5, §7c)"
```

---

## Self-Review

### 1. Spec coverage

| Spec bölümü | Task |
|---|---|
| §1a — kaldırılan araçlar | Task 4 |
| §1b — korunan araçlar | Dokunulmaz (global constraint) |
| §1c — eklenen araçlar | Task 2 (search_documents), Task 5 (search_timeline as tool), Task 7 (query_current_run) |
| §1d — ajan başına dağılım | Task 5 (risk), Task 6 (planner), Task 7 (supervisor) |
| §1e — 6-tur mekanizması | Task 5 |
| §2 — MarkItDown | Task 1 |
| §3 — search_documents | Task 2 |
| §3e — belge ön bilgisi | Task 2 (document_context) |
| §4 — Qdrant cleanup | Task 3 |
| §5 — query_current_run | Task 3 (recent filter), Task 7 (tool) |
| §6 — search_timeline araç | Task 5 |
| §7a — risk prompt | Task 5 |
| §7b — planner prompt | Task 6 |
| §7c — supervisor prompt | Task 7 |
| §8a — field_systems | Task 4 |
| §8b — registry | Task 4 |
| §8c — risk.py | Task 5 |
| §8d — action_planner.py | Task 6 |
| §9 — değişmeyen şeyler | Dokunulmaz (plan kapsamı dışı) |
| §12 — markitdown bağımlılığı | Task 1 |
| §13 — PR #5 kapatma | Task 7 |

### 2. Placeholder scan

Placeholder yok. Her step gerçek kod içeriyor.

### 3. Type consistency

- `embed_document(gw, document, file_path: Path, client=None) -> bool` — Task 1'de tanımlanır, Task 1'de server.py güncellenir
- `search_documents(gw, query, top_k=3, threshold=None, client=None) -> list[DocumentResult]` — Task 2'de tanımlanır, Task 5/6/7'de kullanılır
- `DocumentResult(document_id, name, text_excerpt, score)` — Task 2'de tanımlanır, tutarlı
- `SEARCH_TIMELINE_SCHEMA`, `SEARCH_DOCUMENTS_SCHEMA` — Task 2'de tanımlanır, Task 5/6/7'de import edilir
- `document_context() -> str` — Task 2'de tanımlanır, Task 5/6/7'de kullanılır
- `delete_document_vector(doc_id, client=None) -> None` — Task 3'te tanımlanır, Task 3'te server.py'den çağrılır
- `recent(n, *, from_ts, to_ts)` — Task 3'te tanımlanır, Task 7'de kullanılır
- `RISK_TOOLS`, `RISK_TOOL_SCHEMAS`, `MAX_TOOL_ROUNDS` — Task 5'te tanımlanır
- `PLANNER_READ_TOOLS`, `PLANNER_TOOL_SCHEMAS` — Task 6'da tanımlanır
- `Supervisor.__init__(gw, store, source=None, run_memory=None)` — Task 7'de tanımlanır
