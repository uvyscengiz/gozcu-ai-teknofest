"""Kütüphanenin sunucu tarafı: rapor kalıcılığı ve `/api/library/*` uçları.

`tests/test_library.py` deponun kendisini sınıyor; burası onu sunucuya bağlayan
iki kabloyu sınıyor:

1. **Koşu bitince rapor GERÇEKTEN yazılıyor mu** — ve terk edilmiş/çökmüş
   koşuda YAZILMIYOR mu. Bu ikincisi asıl mesele: terk edilen koşunun çıktısı
   `Session.finish()`'te bilerek atılıyor (spec §4) ve kütüphaneye sızarsa
   operatör reddettiği bir analizi "geçmiş rapor" diye geri görür.
2. **Uçlar** — yükleme, listeleme, okuma, silme.
"""

import pytest
from fastapi.testclient import TestClient

from gozcu.memory import library
from gozcu.core.models import EventSummary, PipelineOutput
from gozcu.ui import server
from gozcu.ui import session as session_module


class _EmbedGateway:
    """Yalnız `embed` bilen ağ geçidi ikizi.

    `vector` `None` ise kademe BOZUK demek (`Gateway.embed` kesintide `[]`
    döndürüyor, istisna atmıyor — `gozcu/gateway.py:269`).
    """

    def __init__(self, vector=None):
        self.vector = vector
        self.texts: list[str] = []

    def embed(self, text, *args, **kwargs):
        self.texts.append(text)
        return self.vector or []


@pytest.fixture(autouse=True)
def _tmp_library(monkeypatch, tmp_path):
    """Kütüphane `tmp_path`'e, gateway ise AĞDAN KOPUK bir ikize bağlanıyor.

    Yama olmadan `POST /api/library/documents` gerçek `Gateway()` kuruyor ve
    `embed` üstel geri çekilmeyle üç kez ağa çıkmaya çalışıyor: ölçüldü, test
    dosyası 24 saniye sürüyordu ve sonuç ağın durumuna bağlıydı.
    """
    monkeypatch.setattr(library, "library_dir", lambda: tmp_path / "library")
    monkeypatch.setattr(server, "Gateway", _EmbedGateway)


@pytest.fixture
def client():
    """SSE açmayan, koşu başlatmayan düz istemci.

    `tests/test_server.py`'nin gerçek soketli fikstürü BURADA gereksiz:
    kütüphane uçlarının hiçbiri sonsuz bir akış açmıyor, `TestClient`'ın
    bloklanma sorunu (o dosyanın başındaki not) bu uçlar için geçerli değil.
    """
    with TestClient(server.app) as test_client:
        yield test_client


_OUTPUT = PipelineOutput(
    summary="Raf çöktü, forklift devrildi.", risk="Kritik",
    events=[EventSummary(time="00:12", event="Raf çöktü")],
    actions=["B-Hattını durdur."])


def _session(monkeypatch, *, abandoned=False):
    session = session_module.Session()
    session.video_path = "raf-cokmesi.mp4"
    monkeypatch.setattr(server, "_SESSION", session)
    monkeypatch.setattr(server, "_RUN_ID", "run-1")
    if abandoned:
        session.abandon()
    return session


# =============================================================================
# Rapor kalıcılığı — `_work`'ün bitiş dalı
# =============================================================================

def test_a_finished_run_writes_its_report_to_the_library(monkeypatch):
    session = _session(monkeypatch)
    monkeypatch.setattr(server, "run_pipeline",
                        lambda *a, **k: (_OUTPUT, None))

    server._work(session, "raf-cokmesi.mp4")

    rows = library.list_reports()
    assert [r.run_id for r in rows] == ["run-1"]
    assert rows[0].risk == "Kritik"
    # Video adı satıra geçiyor: liste "hangi videonun raporu" sorusuna
    # koşu kimliğinden daha okunur bir cevap veriyor.
    assert rows[0].source_name == "raf-cokmesi.mp4"
    body = library.read_report(rows[0].id)
    assert body["payload"]["summary"] == _OUTPUT.summary
    assert body["payload"]["actions"] == ["B-Hattını durdur."]


def test_an_abandoned_run_leaves_nothing_in_the_library(monkeypatch):
    """Terk edilen koşunun çıktısı atılıyor (spec §4) — kütüphaneye de girmez.

    Girseydi operatör reddettiği analizi "geçmiş rapor" diye geri görürdü.
    """
    session = _session(monkeypatch, abandoned=True)
    monkeypatch.setattr(server, "run_pipeline",
                        lambda *a, **k: (_OUTPUT, None))

    server._work(session, "raf-cokmesi.mp4")

    assert library.list_reports() == []


def test_a_crashed_run_leaves_nothing_in_the_library(monkeypatch):
    """Çöken koşunun `output`'u `None` — boş bir rapor yazmak, analiz
    bitmişken bitmediğini söylemek olurdu."""
    session = _session(monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("boru hattı çöktü")

    monkeypatch.setattr(server, "run_pipeline", boom)
    server._work(session, "raf-cokmesi.mp4")

    assert session.run_state == "failed"
    assert library.list_reports() == []


def test_a_failing_library_write_does_not_take_down_the_run(monkeypatch):
    """Disk dolu / izin yok — koşu YİNE bitmeli.

    `finish()` çağrılmadan kalan bir koşu ekranda sonsuza dek "sürüyor"
    görünürdü; rapor yazmak bir yan defter, koşunun kendisi değil.
    """
    session = _session(monkeypatch)
    monkeypatch.setattr(server, "run_pipeline",
                        lambda *a, **k: (_OUTPUT, None))
    monkeypatch.setattr(library, "save_report",
                        _raise(OSError("disk dolu")))

    server._work(session, "raf-cokmesi.mp4")

    assert session.run_state == "done"


def _raise(error):
    def boom(*args, **kwargs):
        raise error
    return boom


# =============================================================================
# Uçlar
# =============================================================================

def test_the_library_is_empty_before_anything_is_uploaded(client):
    assert client.get("/api/library/documents").json() == []
    assert client.get("/api/library/reports").json() == []


def test_uploading_a_document_lists_it_and_serves_it_back(client):
    response = client.post(
        "/api/library/documents",
        files={"file": ("talimat.md", b"raf yukleme talimati", "text/markdown")})
    assert response.status_code == 200
    doc_id = response.json()["id"]

    listed = client.get("/api/library/documents").json()
    assert [d["name"] for d in listed] == ["talimat.md"]
    assert listed[0]["size"] == len(b"raf yukleme talimati")

    content = client.get(f"/api/library/documents/{doc_id}")
    assert content.content == b"raf yukleme talimati"


def test_deleting_a_document_removes_it(client):
    doc_id = client.post(
        "/api/library/documents",
        files={"file": ("gecici.txt", b"x", "text/plain")}).json()["id"]

    assert client.delete(f"/api/library/documents/{doc_id}").status_code == 200
    assert client.get("/api/library/documents").json() == []


def test_an_unknown_document_is_a_turkish_404_not_a_stack_trace(client):
    for path in ("/api/library/documents/" + "0" * 32,
                 "/api/library/reports/" + "0" * 32):
        response = client.get(path)
        assert response.status_code == 404
        # Mesaj Türkçe ve insan okuyabilir — `detail` bir istisna metni değil.
        assert response.json()["detail"]


def test_an_empty_upload_is_refused_with_a_reason(client):
    """Boş dosya sessizce kabul edilmiyor: listede 0 baytlık bir satır,
    yüklenmiş bir belge gibi görünürdü."""
    response = client.post("/api/library/documents",
                           files={"file": ("bos.txt", b"", "text/plain")})
    assert response.status_code == 400
    assert response.json()["detail"]


def test_a_broken_embed_tier_still_keeps_the_document_but_says_so(client):
    """Gömme başarısızken belge KAYBOLMUYOR, yalnız damgası düşüyor.

    `embedded: true` basmak, ajan o belgeyi hiç bulamazken bulacağını
    sanmaktır — `memory_backend()`'in sessiz düşüşü görünür kılma gerekçesinin
    aynısı.
    """
    body = client.post(
        "/api/library/documents",
        files={"file": ("talimat.md", b"raf yukleme talimati", "text/markdown")}
    ).json()

    assert body["embedded"] is False
    assert [d["name"] for d in client.get("/api/library/documents").json()] \
        == ["talimat.md"]


def test_a_working_embed_tier_marks_the_document_and_leaves_episodes_alone(
        client, monkeypatch):
    """Gömülen belge `documents` koleksiyonuna gidiyor, `episodes`'a DEĞİL.

    Bu ayrım bu özelliğin en riskli yeri: `search_timeline` `episodes`'taki
    her noktayı bir `Episode` diye geri kuruyor ve risk analisti onu geçmiş
    bir OLAY sayıyor. Bir vardiya talimatının oraya sızması, ajanın emsal
    listesine olmamış bir olay koymak demekti.
    """
    from gozcu.core.config import (QDRANT_COLLECTION, QDRANT_DOCUMENT_COLLECTION,
                              QDRANT_VECTOR_SIZE)
    from gozcu.memory import episodic as memory

    written: list[str] = []

    class _Client:
        def collection_exists(self, name):
            return True

        def upsert(self, collection, points):
            written.append(collection)

    monkeypatch.setattr(memory, "_client", lambda handle: _Client())
    monkeypatch.setattr(
        server, "Gateway", lambda: _EmbedGateway([0.1] * QDRANT_VECTOR_SIZE))

    body = client.post(
        "/api/library/documents",
        files={"file": ("talimat.md", b"raf yukleme talimati", "text/plain")}
    ).json()

    assert body["embedded"] is True
    assert written == [QDRANT_DOCUMENT_COLLECTION]
    assert QDRANT_COLLECTION not in written


def test_upload_survives_a_gateway_that_cannot_even_be_constructed(
        client, monkeypatch):
    """Anahtarsız kurulumda belge yükleme `500` VERMEMELİ.

    Ölçüldü, tarayıcıda: `.env.example` `GOZCU_GATEWAY_API_KEY=`'i boş
    bırakıyor, boş dize `config.py`'nin `"not-needed"` varsayılanını eziyor ve
    `OpenAI(...)` YAPICISI `OpenAIError: Missing credentials` fırlatıyor —
    `gw.embed()` hiç çağrılmadan, `Gateway()` satırında. `embed_document`'in
    geniş `except`'i buna yetmiyor çünkü istisna ONDAN ÖNCE atılıyor.

    Doğru davranış: belge saklanır, `embedded` `false` kalır.
    """
    monkeypatch.setattr(server, "Gateway",
                        _raise(RuntimeError("Missing credentials")))

    response = client.post(
        "/api/library/documents",
        files={"file": ("talimat.md", b"raf yukleme talimati", "text/plain")})

    assert response.status_code == 200
    assert response.json()["embedded"] is False
    assert [d["name"] for d in client.get("/api/library/documents").json()] \
        == ["talimat.md"]


def test_a_binary_document_is_stored_but_not_embedded(client, monkeypatch):
    """İkili dosya gömülmüyor: baytları zorla çözmek anlamsız bir vektör
    üretirdi. Dosya yine saklanıyor — operatör onu yükledi."""
    from gozcu.core.config import QDRANT_VECTOR_SIZE

    monkeypatch.setattr(
        server, "Gateway", lambda: _EmbedGateway([0.1] * QDRANT_VECTOR_SIZE))

    body = client.post(
        "/api/library/documents",
        files={"file": ("plan.bin", b"\xff\xfe\x00\x01", "application/octet-stream")}
    ).json()

    assert body["embedded"] is False
    assert body["name"] == "plan.bin"


def test_deleting_a_report_removes_it(client):
    saved = library.save_report("run-7", {"summary": "s", "events": [],
                                          "risk": "Orta", "actions": []})

    assert client.delete(f"/api/library/reports/{saved.id}").status_code == 200
    assert client.get("/api/library/reports").json() == []


def test_deleting_a_missing_report_is_a_turkish_404(client):
    response = client.delete("/api/library/reports/" + "0" * 32)
    assert response.status_code == 404
    assert response.json()["detail"]


def test_reports_endpoint_serves_the_saved_body(client):
    saved = library.save_report("run-7", {"summary": "s", "events": [],
                                          "risk": "Orta", "actions": []},
                                source_name="klip.mp4")

    rows = client.get("/api/library/reports").json()
    assert rows[0]["run_id"] == "run-7"
    # Liste satırı gövdeyi TAŞIMIYOR (bkz. `library.Report` docstring).
    assert "payload" not in rows[0]

    body = client.get(f"/api/library/reports/{saved.id}").json()
    assert body["payload"]["risk"] == "Orta"
