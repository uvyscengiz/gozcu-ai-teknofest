"""Görev 3 — `gozcu/ui/server.py`'nin iskeleti ve salt-okunur uçları.

`console.py`'nin (Gradio) yerini alacak yeni sunucu. Bu dosya yalnız bu
görevin kapsamındaki uçları sınıyor: `GET /api/status`, `GET /api/meta` ve
koşuya bağlı salt-okunur uçların oturumsuzken çökmediğini. Yazan uçlar
(koşu başlatma, onay, SSE) sonraki görevlerde geliyor.
"""

import pytest
from fastapi.testclient import TestClient

from gozcu.ui import server
from gozcu.ui.session import RUN_STATES


@pytest.fixture
def client(monkeypatch):
    """Bu görevin fikstürü — boru hattı sahteleri Görev 4'te EKLENİYOR.

    Modül düzeyinde `client = TestClient(app)` yazılamaz: Görev 4 bu
    fikstürü YERİNDE genişletiyor ve modül düzeyi bir adı ezerdi. Tek bir
    `client` var ve büyüyen o.
    """
    monkeypatch.setattr(server, "_SESSION", None)
    monkeypatch.setattr(server, "_RUN_ID", None)
    with TestClient(server.app) as test_client:
        yield test_client


def test_every_endpoint_survives_a_missing_session(client):
    """`every_button_handler_survives_a_missing_session`'ın HTTP karşılığı:
    oturum yokken hiçbir uç 500 vermiyor."""
    for path in ("/api/status", "/api/run/none/payload", "/api/run/none/kpi",
                 "/api/run/none/handoffs", "/api/run/none/actions",
                 "/api/run/none/windows"):
        response = client.get(path)
        assert response.status_code in (200, 404), path


def test_status_answers_before_any_run(client):
    """`Gateway` oturumla doğuyor; oturum yokken uç modül düzeyi bilgiyi
    döndürüyor — boş bir 500 yerine eksik ama dürüst bir cevap."""
    body = client.get("/api/status").json()
    assert body["model"]
    assert body["gateway"] is None


def test_perception_kpis_are_visible_before_any_run(client):
    body = client.get("/api/run/none/kpi").json()
    assert body["perception"]["blocks"]


def test_the_wire_run_states_come_from_one_source(client):
    body = client.get("/api/meta").json()
    assert tuple(body["run_states"]) == RUN_STATES


def test_the_wire_enums_match_the_schema(client):
    """Enum eşleme tablosunun testi — teldeki küme koddakiyle birebir."""
    import typing

    from gozcu.models import ActionRecord, RiskLevel, WindowRecord
    body = client.get("/api/meta").json()
    assert set(body["risk_levels"]) == set(typing.get_args(RiskLevel))
    assert set(body["window_outcomes"]) == set(
        typing.get_args(WindowRecord.model_fields["outcome"].annotation))
    assert set(body["approval_states"]) == set(
        typing.get_args(ActionRecord.model_fields["approval"].annotation))


def test_no_run_yet_is_said_in_turkish_not_shown_as_empty_json(client):
    """Görev 2 incelemesinden taşınan yükümlülük: eski
    `test_no_run_yet_is_said_in_turkish_not_shown_as_empty_json`
    `payload_json(None) == NO_RUN_YET` diyordu (`console.py`'nin Markdown
    katmanında). Göç veri katmanına (`view.payload_dict(None) is None`)
    indiğinde bu garanti tel katmanında yeniden kurulmadan kayboluyordu —
    burada tel düzeyinde yeniden kuruluyor: koşu yokken `GET
    .../payload` boş/`null` bir gövde değil, Türkçe bir mesaj taşıyan
    `404` döndürüyor.
    """
    from gozcu.ui.view import NO_RUN_YET

    response = client.get("/api/run/none/payload")
    assert response.status_code == 404
    assert response.json()["detail"] == NO_RUN_YET


def test_ensure_server_running_explains_missing_mlx_vlm():
    """`test_console.py:224`'ten taşındı — `_ensure_server_running` artık
    burada yaşıyor (`console.py`'deki AYNEN korunuyor, konsol Görev 11'e
    kadar kendi kopyasını kullanmaya devam ediyor)."""
    from unittest.mock import MagicMock, patch

    client = MagicMock()
    client.models.list.side_effect = Exception("unreachable")

    with (patch.object(server, "OpenAI", return_value=client),
          patch("importlib.util.find_spec", return_value=None),
          patch.object(server.subprocess, "Popen") as popen,
          patch.object(server.time, "sleep")):
        with pytest.raises(RuntimeError, match="mlx-vlm"):
            server._ensure_server_running()
        popen.assert_not_called()
