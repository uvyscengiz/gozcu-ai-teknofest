"""Görev 3'ün iskeleti + Görev 4'ün koşu yaşam döngüsü ve SSE'si.

Görev 3'ün beş testi (client fikstürü, `/api/status`, `/api/meta`, koşuya
bağlı salt-okunur uçların oturumsuzken çökmediği) burada AYNEN duruyor —
fikstür Görev 4'te GENİŞLETİLDİ, yeniden yazılmadı; ikinci bir `client`
tanımı o beş testi sessizce kırardı.

Görev 4 planın kalbi: `run_pipeline` ayrı bir iş parçacığında koşuyor,
`on_event` o iş parçacığında olayın TAM ANINDA çağrılıyor ve `step_mode`
açıkken orada GERÇEKTEN bloklanıyor — videonun zaman çizelgesi orada
duruyor. İki test bunun tek kanıtı:
`test_the_stream_carries_full_state_and_the_loop_really_pauses` (duraklama
gerçek) ve `test_the_escalation_card_reaches_the_stream`
(`LoopEvent → escalated_ids → kart` zinciri uçtan uca).
"""

import asyncio
import json
import pathlib
import threading
import time

import httpx
import pytest
import uvicorn

from gozcu.annotate import AnnotateError
from gozcu.models import ActionRecord, Episode, LoopEvent, WindowRecord
from gozcu.run import LATE_NOTICE
from gozcu.store import Store
from gozcu.ui import server, view
from gozcu.ui import session as session_module
from gozcu.ui.session import RUN_STATES
from tests.doubles import StubGateway, StubLoop
from tests.test_run import _fake_clip, _perception

#: `fastapi.testclient.TestClient` (Starlette 1.x) `POST /api/run`'ın açtığı
#: SONSUZ SSE bağlantısını (§6: kalp atışı bağlantıyı canlı tutuyor, akış
#: kendiliğinden bitmiyor) TAMAMEN farklı sınıyor: `_TestClientTransport.
#: handle_request` `portal.call(self.app, ...)` çağırıyor ve ASGI çağrısı
#: BİTENE kadar bloklanıyor — sonsuz bir generator'da bu hiç dönmüyor,
#: `client.stream(...)` bile ilk baytı beklerken sonsuza dek asılı kalıyor
#: (ölçüldü: `test_two_connections_see_the_same_state` `TestClient` ile
#: donuyor). Gerçek soket üzerinden gerçek bir sunucu bu sınıfın DIŞINDA:
#: `uvicorn.Server.serve()` arka planda bir iş parçacığında çalışıyor,
#: `httpx.Client` gerçek TCP üzerinden bağlanıyor ve bayt geldikçe okuyor —
#: tam olarak üretimdeki `EventSourceResponse` gibi.
@pytest.fixture
def client(monkeypatch, tmp_path):
    """Ağa çıkmayan, ffmpeg/YOLO koşmayan, GERÇEK bir soket üzerinde sunucu.

    `_perception` ve `_fake_clip` YEDEK DEĞİL, **yama kurucu**: kendileri
    `monkeypatch.setattr` çağırıyor (`tests/test_run.py:135, 160`) ve
    `run_module`'ün `extract_frames`/`track_video`/`compute_signals`/
    `_clip_for` adlarını değiştiriyorlar. Onları bir şeyin YERİNE koymak
    ilk çağrıda `AttributeError` verir.

    `Gateway` **import yerinde** yamalanıyor (`gozcu.ui.session`), tanım
    yerinde değil: `session.py` `from gozcu.gateway import Gateway`
    yapıyor ve tanım yerini yamalamak onu etkilemez. Uyarlayıcı lambda
    şart — `StubGateway(store)` imzası `_FakeGateway(router=...)`'a
    düşerdi.
    """
    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)
    # İki ayrı sorun, tek çözüm. (a) `_perception` yalnız `Frame` NESNESİ
    # üretiyor, diske hiçbir şey yazmıyor; `frame_size` ilk kareyi
    # `cv2.imread` ile okuyor (Görev 5). (b) Sunucu `output_dir`'i kendisi
    # seçiyor ve oraya YALNIZ gerçek `extract_frames` yazıyor
    # (`gozcu/frames.py:30`) — sahtelenince o dizin boş kalır ve glob
    # hiçbir şey bulamaz. Bu yüzden sunucunun dizin seçicisi `tmp_path`'e
    # yamalanıyor (yukarıda) ve kareler oraya yazılıyor: `_perception`'ın
    # `Frame.path`'leri de `tmp_path/frame_XXXX.jpg` (`test_run.py:148`).
    _write_frames(tmp_path)
    monkeypatch.setattr(session_module, "Gateway", lambda store: StubGateway())
    # `Supervisor` YAMALANMIYOR — gerçek Nöbetçi sahte ağ geçidi üzerinde
    # koşuyor. `FakeSupervisor`'ın yalnız `approve`/`pending_approval`'ı var
    # (`tests/doubles.py`); `run_pipeline` her yükseltmede `nobetci.escalate()`
    # çağırıyor (`run.py:230`) ve o çağrı `on_event`'ten ÖNCE geliyor. Eksik
    # metot `run.py:469`'un geniş `except`'ine düşer, koşu sessizce bozulmuş
    # çıktıya iner, `session.events` boş kalır ve duraklama HİÇ olmaz — yani
    # planın kritik dediği iki test ölür.
    monkeypatch.setattr(server, "_output_dir_for", lambda run_id: tmp_path)
    monkeypatch.setattr(server, "_SESSION", None)
    monkeypatch.setattr(server, "_RUN_ID", None)

    config = uvicorn.Config(server.app, host="127.0.0.1", port=0,
                            log_level="warning", lifespan="on")
    uv_server = uvicorn.Server(config)
    # `uv_server.run()` DEĞİL: o `capture_signals()` ile `signal.signal()`
    # çağırıyor ve ana iş parçacığının DIŞINDA bu bir `ValueError` atıyor.
    # `serve()` doğrudan çağrılınca sinyal kurulumu hiç devreye girmiyor.
    thread = threading.Thread(target=lambda: asyncio.run(uv_server.serve()),
                              daemon=True)
    thread.start()
    deadline = time.monotonic() + 10.0
    while not uv_server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("test sunucusu 10 saniyede ayağa kalkmadı")
        time.sleep(0.01)
    port = uv_server.servers[0].sockets[0].getsockname()[1]

    with httpx.Client(base_url=f"http://127.0.0.1:{port}",
                      timeout=30.0) as test_client:
        yield test_client

    uv_server.should_exit = True
    thread.join(timeout=10.0)
    # Teardown ŞART: duraklamış bir koşu bırakan test, sonraki her
    # `_start_run`'ı 409'a düşürür (§4: iş parçacığı ölene kadar 409).
    live = server._SESSION
    if live is not None and live.is_running():
        live.abandon()
        if live.thread is not None:
            live.thread.join(timeout=5.0)


def _write_frames(tmp_path) -> None:
    import cv2
    import numpy
    for index in range(4):
        cv2.imwrite(str(tmp_path / f"frame_{index:04d}.jpg"),
                    numpy.zeros((360, 640, 3), dtype=numpy.uint8))


def _post_run(client, step_mode=False):
    return client.post("/api/run",
                       files={"video": ("k.mp4", b"\x00" * 32, "video/mp4")},
                       data={"step_mode": str(step_mode).lower()})


def _start_run(client, step_mode=False) -> str:
    response = _post_run(client, step_mode)
    assert response.status_code == 200, response.text
    return response.json()["run_id"]


def _frames(client, run_id, limit=2000, deadline=None):
    """SSE akışındaki `state` çerçevelerini sözlük olarak veriyor.

    Ayrıştırma BURADA — ayrı bir `_parse_sse` yok; kalp atışı satırları
    (`:keepalive`) `data:` ile başlamadığı için kendiliğinden eleniyor.
    """
    with client.stream("GET", f"/api/run/{run_id}/events") as stream:
        for line in stream.iter_lines():
            # Süre kontrolü `data:` süzgecinin ÜSTÜNDE: kalp atışı satırları
            # elenirken zaman aşımı da elenirse test asılır.
            if deadline is not None and time.monotonic() > deadline:
                return
            if not line.startswith("data:"):
                continue
            yield json.loads(line[5:].strip())
            limit -= 1
            if limit <= 0:
                return


def _first_frame(client, run_id) -> dict:
    return next(_frames(client, run_id))


def _wait_for_state(client, run_id, wanted, timeout=20.0) -> dict:
    """Zaman aşımı `data:` çerçevesi beklemeden işliyor.

    Süre yalnız çerçeve geldiğinde kontrol edilseydi, durum geçişini
    durduran bir regresyon testi temiz biçimde KIRMAZ, asardı: kalp
    atışları akmaya devam eder ve döngü hiç ilerlemez.
    """
    deadline = time.monotonic() + timeout
    for frame in _frames(client, run_id, deadline=deadline):
        if frame["run_state"] == wanted:
            return frame
    raise AssertionError(f"{wanted!r} durumuna hiç ulaşılmadı")


def _drain_until_done(client, run_id, timeout=20.0) -> list:
    """`deadline` ŞART: kalp atışı bağlantıyı sonsuza dek canlı tutuyor
    (§6), `httpx`'in 30s zaman aşımı da her kalp atışında sıfırlanıyor —
    deadline olmadan bir regresyon (ör. bitiş geçişinin bildirilmemesi)
    testi kırmızıya DÜŞÜRMEZ, CI'ı sonsuza dek asar."""
    deadline = time.monotonic() + timeout
    last = []
    for frame in _frames(client, run_id, deadline=deadline):
        last = frame["feed"]
        if frame["run_state"] in ("done", "failed"):
            break
    return last


def _finished_run(client) -> str:
    run_id = _start_run(client, step_mode=False)
    _drain_until_done(client, run_id)
    return run_id


def _wait_until(predicate, timeout=5.0) -> None:
    """Bir arka plan iş parçacığının durum değiştirmesini bekler (poll)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("beklenen koşul zaman aşımında gerçekleşmedi")


def _install_session(monkeypatch, run_id="test-run"):
    """Boru hattı iş parçacığı OLMADAN bir oturum kurar.

    Komut uçlarının `Session`/`Supervisor`/`Gateway` metotlarına ince
    sarmalayıcı olduğunu doğrudan sınamak için: `session_module.Gateway`
    fikstürde zaten `StubGateway`'e yamalı, yani `Session()` burada da aynı
    sahte ağ geçidi + gerçek `Supervisor`'ı kuruyor.
    """
    session = session_module.Session()
    monkeypatch.setattr(server, "_SESSION", session)
    monkeypatch.setattr(server, "_RUN_ID", run_id)
    return session, run_id


def _raise(error):
    def boom(*args, **kwargs):
        raise error
    return boom


# =============================================================================
# Görev 3 — iskelet ve salt-okunur uçlar (AYNEN korunuyor)
# =============================================================================

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


def test_the_kpi_wire_carries_all_six_benchmark_kpis(client):
    """Görev 9 — Performans görünümü `benchmark.kpi.collect`'in altı
    KPI'sının hepsini gösteriyor; tel bunları taşımazsa görev sessizce üç
    KPI'yı GİZLEMİŞ olurdu (bkz. `tests/test_view.py::
    TestKpiPanel::test_kpi_payload_carries_all_six_benchmark_kpis`)."""
    body = client.get("/api/run/none/kpi").json()
    assert "vision_tokens" in body["decision"]
    assert "correction_propagation" in body["decision"]
    assert "timestamp_drift_s" in body["performance"]


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


def test_the_wire_carries_the_one_true_risk_color_table(client):
    """Görev 6'nın gereksinimi: tarayıcı karar veren hiçbir şey yapmıyor,
    risk rengi de dahil. `gozcu/ui/feed.py::RISK_COLORS` besleme kartlarını
    (`FeedEntry.card`) zaten renklendiren TEK kaynak — bu test o kaynağın
    tel üzerinden de (`/api/meta`) taşındığını, ikinci bir renk tablosunun
    CSS/JS'te elle yazılmadığını doğruluyor.
    """
    from gozcu.ui.feed import RISK_COLORS

    body = client.get("/api/meta").json()
    assert body["risk_colors"] == RISK_COLORS
    assert set(body["risk_colors"]) == set(body["risk_levels"])


def test_the_wire_carries_turkish_run_state_labels(client):
    """Görev 6 düzeltme turu — `run_state`'in Türkçesi de aynı ilkeyle
    (`badge_labels`/`agent_marks`/`risk_colors`) tek kaynaktan, tel
    üzerinden geliyor; `js/sse.js` kendi elinde bir çeviri tablosu TUTMUYOR.
    """
    from gozcu.ui.session import RUN_STATES
    from gozcu.ui.view import RUN_STATE_LABELS

    body = client.get("/api/meta").json()
    assert body["run_state_labels"] == RUN_STATE_LABELS
    assert set(body["run_state_labels"]) == set(RUN_STATES)


def test_the_wire_carries_the_one_true_proactive_mark(client):
    """Görev 6 düzeltme turu 2 — `gozcu/ui/feed.py::PROACTIVE_MARK`'ın
    (kimse sormadan söylenmiş bir süpervizör satırının rozeti) `js/feed.js`
    tarafında elle yazılmış bir kopyası kalmıyor; `agent_marks`/`risk_colors`
    ile AYNI ilke, aynı test şekli.
    """
    from gozcu.ui.feed import PROACTIVE_MARK

    body = client.get("/api/meta").json()
    assert body["proactive_mark"] == PROACTIVE_MARK


def test_the_wire_carries_the_one_true_agent_marks_table(client):
    """Görev 6 düzeltme turu — `gozcu/ui/feed.py::AGENT_MARKS`'ın besleme
    girdilerini imzalayan emoji rozetleri tarayıcıda İKİNCİ bir kopya olarak
    elle yazılmıyor; `risk_colors` ile AYNI ilke, aynı test şekli.
    """
    from gozcu.ui.feed import AGENT_MARKS

    body = client.get("/api/meta").json()
    assert body["agent_marks"] == AGENT_MARKS


def test_the_wire_carries_the_one_true_window_outcome_labels_table(client):
    """Görev 8 düzeltme turu — `gozcu/ui/feed.py::OUTCOME_LABELS`'in dört
    Türkçe karşılığı (pencere defterinin dört akıbet dalı) `trace.js`'te
    ikinci bir kopya olarak elle yazılmıyor; `agent_marks`/`risk_colors`
    ile AYNI ilke, aynı test şekli.
    """
    from gozcu.ui.feed import OUTCOME_LABELS

    body = client.get("/api/meta").json()
    assert body["window_outcome_labels"] == OUTCOME_LABELS
    assert set(body["window_outcome_labels"]) == set(body["window_outcomes"])


def test_the_wire_carries_turkish_badge_labels(client):
    """Görev 6 düzeltme turu — üst bar rozetleri (`gateway`/`memory`/`run`)
    çıplak İngilizce enum değerini (`"healthy"`, `"qdrant"`, `"measured"` ...)
    ekrana basmıyor; Türkçe karşılığı `gozcu/ui/view.py::BADGE_LABELS`'tan,
    tek kaynaktan geliyor. Ham değer TELDE KALIYOR (`badges()`'ın kendisi) —
    o zaten bir enum, etiket yalnız SUNUM.
    """
    from benchmark.kpi import DEGRADED, MEASURED, UNMEASURED
    from gozcu.ui.view import BADGE_LABELS

    body = client.get("/api/meta").json()
    assert body["badge_labels"] == BADGE_LABELS
    # Gerçekte üretilebilecek HER rozet değerinin (view.badges/get_status)
    # bir Türkçe etiketi var — hiçbiri sessizce çıplak kalmıyor.
    assert {"healthy", "degraded", "qdrant", "local",
            MEASURED, DEGRADED, UNMEASURED} <= set(BADGE_LABELS)


def test_the_wire_carries_turkish_decision_bucket_labels(client):
    """Görev 9 — Performans görünümünün dağılım grafiği `benchmark.kpi.
    DECISION_BUCKETS`'ın beş ham kova adını (`closed_at_router` vb.)
    ekrana çıplak basmıyor; Türkçe karşılığı `gozcu/ui/view.py::
    DECISION_BUCKET_LABELS`'tan geliyor — `agent_marks`/`risk_colors`
    ile AYNI ilke, `bench.js`'te ikinci bir kopyası YOK."""
    from benchmark.kpi import DECISION_BUCKETS
    from gozcu.ui.view import DECISION_BUCKET_LABELS

    body = client.get("/api/meta").json()
    assert body["decision_bucket_labels"] == DECISION_BUCKET_LABELS
    assert set(body["decision_bucket_labels"]) == set(DECISION_BUCKETS)
    # SIRA da bir sözleşme, yalnız anahtar kümesi değil: `bench.js:113`
    # dağılım grafiğinin dilim SIRASINI `Object.keys(labels)`'ten alıyor
    # (JSON nesne sırası korunuyor). Sözlük eşitliği sırayı GÖRMEZ — bu
    # satır olmadan kovaların yeniden sıralanması grafiği sessizce
    # karıştırır ve hiçbir test kırılmazdı.
    assert list(body["decision_bucket_labels"]) == list(DECISION_BUCKETS)


def test_the_wire_carries_the_kpi_unmeasured_sentinel(client):
    """Görev 9 — `bench.js` ölçülemeyen bir KPI hücresini soluklaştırmak
    için bu sözcüğü METİN KARŞILAŞTIRMASIYLA tanıyor; sözcüğün kendisi
    `gozcu/ui/view.py::KPI_UNMEASURED`'dan geliyor, JS'te ikinci kez
    yazılmıyor."""
    from gozcu.ui.view import KPI_UNMEASURED

    body = client.get("/api/meta").json()
    assert body["kpi_unmeasured"] == KPI_UNMEASURED


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


# =============================================================================
# Görev 4 — kritik testler: duraklama gerçek, kart zinciri uçtan uca
# =============================================================================

def test_the_stream_carries_full_state_and_the_loop_really_pauses(client):
    """KRİTİK — duraklamanın gerçek olduğunun tek kanıtı.
    (`test_console.py:492`'nin yeniden kurulmuş hâli.)

    `deadline` ŞART: `_on_event` `wait_if_step_mode()`'u çağırmayı
    bırakırsa (tam da bu testin yakalaması gereken regresyon) akış hiç
    'paused' üretmez ve kalp atışı sonsuza dek sürer — deadline olmadan
    bu regresyon CI'ı kırmızıya düşürmek yerine asar.
    """
    run_id = _start_run(client, step_mode=True)
    states, feed, paused_once = [], [], False
    deadline = time.monotonic() + 40.0
    for frame in _frames(client, run_id, deadline=deadline):
        states.append(frame["run_state"])
        # Her çerçeve TAM durum taşıyor — kısmi güncelleme yok.
        assert {"feed", "run_state", "badges", "version"} <= set(frame)
        if frame["feed"]:
            feed = frame["feed"]
        if frame["run_state"] == "paused":
            if not paused_once:
                # Video gerçekten durdu: koşu bitmedi, yük teslim edilmedi.
                assert client.get(f"/api/run/{run_id}/payload").status_code == 404
                paused_once = True
            # Her olayın kendi beklemesi var; anahtar AÇIK kaldığı için
            # sonraki olaylar da duraklıyor ve her biri serbest bırakılıyor.
            assert client.post(f"/api/run/{run_id}/resume").status_code == 200
        if frame["run_state"] in ("done", "failed"):
            break

    assert "paused" in states, "kritik olayda hiç durulmadı"
    assert states[-1] == "done", f"koşu sona ermedi: {states[-1]}"

    # Dikişin geri kalanı: bloğu çözülen generator SONA kadar akıyor ve
    # teslim edilen yük ekrana düşüyor. Parçaların her biri ayrı ayrı
    # sınanıyor, ama anlatının tamamını uçtan uca gezen tek test bu.
    payload = client.get(f"/api/run/{run_id}/payload")
    assert payload.status_code == 200
    assert "summary" in payload.json(), "dört anahtar teslim edilmedi"

    assert feed, "besleme boş kaldı"
    assert any(entry["agent"] == "supervisor" for entry in feed), (
        "süpervizörün konuştuğu beslemede yok")

    session = server._SESSION
    assert session is not None and session.store.handoffs(), "devir defteri boş"


def test_the_finished_run_reaches_a_connected_client(client):
    """4. tur blocker'ı: bitiş geçişi hiçbir bekleyeni uyandırmıyordu ve
    bağlı istemci sonsuza dek 'running' gösteriyordu.

    `_wait_for_state` tam bunun için yazıldı: zaman aşımı `data:`
    çerçevesi beklemeden işliyor, yani bitiş bildirilmeyen bir regresyon
    burada kırmızıya düşer, asmaz.
    """
    run_id = _start_run(client, step_mode=False)
    _wait_for_state(client, run_id, "done", timeout=20.0)


def test_the_escalation_card_reaches_the_stream(client):
    """`LoopEvent → escalated_ids → kart` zincirinin tek uçtan uca kanıtı
    (`test_console.py:1028`'in yeniden kurulmuş hâli). Bu zincir
    bozulursa hiçbir birim testi kırmızıya dönmez."""
    run_id = _start_run(client, step_mode=False)
    cards = _drain_until_done(client, run_id)
    assert any(entry.get("card") for entry in cards)


def test_two_connections_see_the_same_state(client):
    """`queue.Queue` tek tüketiciliydi; iki SSE üreteci onu yarıştırırdı
    ve `done` bir kez tüketilirdi."""
    run_id = _start_run(client, step_mode=False)
    first = _first_frame(client, run_id)
    second = _first_frame(client, run_id)
    # Durumu KARŞILAŞTIRMIYORUZ: hızlı sahte koşu iki anlık görüntü arasında
    # `running → done` geçebilir ve test sallanırdı. Sınanan şey ikisinin de
    # tam ve geçerli bir durum almasi — yarışan kuyruk bunu veremezdi.
    for frame in (first, second):
        assert {"feed", "run_state", "badges", "version"} <= set(frame)
        assert frame["run_state"] in RUN_STATES


def test_a_second_run_is_refused_while_the_thread_is_alive(client):
    """İptal mekanizması yok; iki eşzamanlı koşu gateway kotasında
    yarışır ve ölçümü sessizce bozar."""
    _start_run(client, step_mode=True)
    assert _post_run(client).status_code == 409


def test_resume_is_refused_when_the_run_is_not_paused(client):
    run_id = _start_run(client, step_mode=False)
    assert client.post(f"/api/run/{run_id}/resume").status_code == 409


def test_the_resume_button_is_only_reachable_while_the_run_is_paused():
    """Görev 11'de `test_console.py:919/923`'ten yeniden kuruldu.

    Eski konsolda "Devam et" ayrı bir bileşendi ve `_set_step_mode` onu
    elle gizliyordu: anahtar kapalıyken düğme HİÇBİR ŞEY yapmıyor, ama
    görünüyordu. Yeni konsolda gizleme bir karar değil, YAPI —
    `#resumeButton` `#pausedBanner`ın İÇİNDE ve banner yalnız
    `run_state === "paused"` iken açılıyor. Düğmeye başka türlü
    ulaşılamıyor, üstelik sunucu da `paused` değilken `409` dönüyor
    (`test_resume_is_refused_when_the_run_is_not_paused`).
    """
    web = pathlib.Path(server.__file__).resolve().parent / "web"
    html = (web / "index.html").read_text(encoding="utf-8")
    banner = html.index('id="pausedBanner"')
    assert html.index('id="resumeButton"', banner) < html.index("</div>", banner)

    js = (web / "js" / "sse.js").read_text(encoding="utf-8")
    assert 'const isPaused = state.run_state === "paused";' in js
    assert 'els.pausedBanner.classList.toggle("hidden", !isPaused);' in js


def test_step_mode_cannot_be_re_armed_on_an_abandoned_run(client):
    run_id = _start_run(client, step_mode=True)
    client.post(f"/api/run/{run_id}/abandon")
    response = client.post(f"/api/run/{run_id}/step-mode",
                           json={"enabled": True})
    assert response.status_code == 409


# =============================================================================
# Görev 4 — "yeniden kur" listesinin kalanı (§Adım 5)
# =============================================================================

def test_every_sse_frame_carries_the_full_state_not_a_partial_update(client):
    """`test_console.py:370`'in yeniden kurulmuş hâli — SSE değişmezi:
    HER çerçeve tam durum taşıyor, hiçbiri bir alt kümeyi tazelemiyor."""
    run_id = _start_run(client, step_mode=False)
    full_shape = {"version", "run_state", "feed", "pending", "badges",
                 "processed_until_s", "pending_deferred_ts", "elapsed_s"}
    deadline = time.monotonic() + 20.0
    for frame in _frames(client, run_id, deadline=deadline):
        assert full_shape <= set(frame)
        if frame["run_state"] in ("done", "failed"):
            break


def test_the_run_never_blocks_by_default(client):
    """Varsayılan akış (`step_mode=False`): hiçbir düğmeye basılmadan koşu
    sonuna kadar akıyor — `test_console.py:787`'nin yeniden kurulmuş hâli.

    `_frames` bitişten SONRA da akmaya devam eder (kalp atışı bağlantıyı
    canlı tutuyor, §6) — döngü `done`/`failed` görünce KENDİSİ duruyor,
    yoksa sonsuza dek bekler.
    """
    run_id = _start_run(client, step_mode=False)
    states = []
    deadline = time.monotonic() + 20.0
    for frame in _frames(client, run_id, deadline=deadline):
        states.append(frame["run_state"])
        if frame["run_state"] in ("done", "failed"):
            break
    assert states[-1] == "done"
    assert "paused" not in states


def test_cutting_the_link_injects_a_vision_tier_outage(client, monkeypatch):
    """`test_console.py:415`'in yeniden kurulmuş hâli — beat 6'nın ilk
    yarısı: jürinin gözü önünde bağlantı kesiliyor."""
    session, run_id = _install_session(monkeypatch)
    response = client.post(f"/api/run/{run_id}/gateway/cut")
    assert response.status_code == 200
    assert session.gw.injections == [{"vlm"}]
    assert session.gw.is_degraded()


def test_restoring_the_link_clears_the_outage_and_catches_up(client, monkeypatch):
    """`test_console.py:423`'ün yeniden kurulmuş hâli.

    Yalnız `inject_failure(set())` yapılsaydı atlanan pencereler kuyrukta
    kalırdı ve telafi hiç görünmezdi — iki adım tek uçta birlikte olmak
    zorunda.
    """
    session, run_id = _install_session(monkeypatch)
    session.gw.inject_failure({"vlm"})
    session.store.create_episode(Episode(start_ts=192.0, phase="onset",
                                         summary_tr="İstif aracı devrildi.",
                                         preliminary_risk="Yüksek"))
    episode = session.store.episodes()[0]
    session.loop = StubLoop([LoopEvent(episode=episode, late=True)])

    response = client.post(f"/api/run/{run_id}/gateway/restore")
    assert response.status_code == 200
    assert response.json()["recovered"] == 1
    assert session.gw.injections[-1] == set()
    assert session.loop.calls == 1
    assert session.events and session.events[-1].late is True
    assert any(turn.text == LATE_NOTICE for turn in session.store.dialogue())


def test_restoring_without_a_running_loop_says_so(client, monkeypatch):
    """`test_console.py:445`'in yeniden kurulmuş hâli — canlı döngü yokken
    (koşu daha `on_loop_ready`'ye ulaşmadan) çökmüyor, `recovered=0`."""
    session, run_id = _install_session(monkeypatch)
    response = client.post(f"/api/run/{run_id}/gateway/restore")
    assert response.status_code == 200
    assert response.json()["recovered"] == 0
    assert session.gw.injections == [set()]


def test_resume_releases_the_paused_loop(client, monkeypatch):
    """`test_console.py:451`'in yeniden kurulmuş hâli — "Devam et" bloğu
    GERÇEKTEN çözüyor, bir bayrak çevirmiyor."""
    session, run_id = _install_session(monkeypatch)
    session.set_step_mode(True)
    released = threading.Event()
    thread = threading.Thread(
        target=lambda: (session.wait_if_step_mode(), released.set()),
        daemon=True)
    thread.start()
    _wait_until(lambda: session.run_state == "paused")

    response = client.post(f"/api/run/{run_id}/resume")
    assert response.status_code == 200
    thread.join(timeout=2.0)
    assert released.is_set()


def test_turning_step_mode_off_releases_a_waiting_loop(client, monkeypatch):
    """`test_console.py:927`'nin yeniden kurulmuş hâli — kapatan kişi o an
    bekleyen döngüyü serbest bırakmak ZORUNDA, yoksa koşu kilitli kalırdı."""
    session, run_id = _install_session(monkeypatch)
    session.set_step_mode(True)
    released = threading.Event()
    thread = threading.Thread(
        target=lambda: (session.wait_if_step_mode(), released.set()),
        daemon=True)
    thread.start()
    _wait_until(lambda: session.run_state == "paused")

    response = client.post(f"/api/run/{run_id}/step-mode",
                           json={"enabled": False})
    assert response.status_code == 200
    thread.join(timeout=2.0)
    assert released.is_set()


def test_starting_without_a_video_says_so_instead_of_crashing(client):
    """`test_console.py:460`'ın yeniden kurulmuş hâli — video yokken 500
    değil, okunur bir hata."""
    response = client.post("/api/run", data={"step_mode": "false"})
    assert response.status_code != 500
    assert response.json().get("detail")


def test_every_button_handler_survives_a_missing_session(client):
    """`test_console.py:465`'in yeniden kurulmuş hâli — hiçbir koşu
    başlamamışken hiçbir komut ucu 500 vermiyor, hepsi 404."""
    run_id = "hic-boyle-bir-kosu-yok"
    calls = [
        ("post", f"/api/run/{run_id}/resume", {}),
        ("post", f"/api/run/{run_id}/abandon", {}),
        ("post", f"/api/run/{run_id}/approve",
         {"json": {"action_id": 1, "approved": True}}),
        ("post", f"/api/run/{run_id}/say", {"json": {"text": "merhaba"}}),
        ("post", f"/api/run/{run_id}/stress/baglam", {}),
        ("post", f"/api/run/{run_id}/gateway/cut", {}),
        ("post", f"/api/run/{run_id}/gateway/restore", {}),
        ("post", f"/api/run/{run_id}/step-mode", {"json": {"enabled": True}}),
    ]
    for method, path, kwargs in calls:
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 404, path


def test_the_approval_bar_opens_only_while_an_action_is_pending(client, monkeypatch):
    """`test_console.py:473`'ün yeniden kurulmuş hâli — yuvalar ADIYLA değil
    tel alanıyla okunuyor: `pending` bekleyen aksiyonda dolu, kararla boşalıyor."""
    session, run_id = _install_session(monkeypatch)
    assert server._snapshot(session)["pending"] is None

    action_id = session.store.save_action(ActionRecord(
        ts=192.0, tool_name="halt_production_line",
        params={"line_id": "B-Hattı", "rationale": "test"},
        result={"state": "awaiting_approval"}, actor="agent",
        approval="pending"))
    snapshot = server._snapshot(session)
    assert snapshot["pending"] == {"action_id": action_id,
                                   "tool": "halt_production_line",
                                   "params": {"line_id": "B-Hattı",
                                              "rationale": "test"}}

    session.store.set_action_approval(action_id, "approved")
    assert server._snapshot(session)["pending"] is None


def test_confidence_reaches_the_screen_already_formatted(client, monkeypatch):
    """Görev 6 düzeltme turu — tarayıcı güveni KENDİSİ biçimlendirmiyordu
    (`js/feed.js`'in eski `toFixed(2)` + virgül değişimi,
    `gozcu/ui/feed.py:540`'ın birebir kopyasıydı). Tel artık BİTMİŞ dizeyi
    taşıyor, tarayıcı yalnız basıyor — `sse.js` başlığının kendi iddiasıyla
    tutarlı hâle getirildi.
    """
    from gozcu.models import Handoff
    from gozcu.ui.feed import format_confidence

    session, run_id = _install_session(monkeypatch)
    session.store.save_handoff(Handoff(
        ts=12.0, source_agent="orchestrator", target_agent="interpreter",
        reason="test", confidence=0.8, payload_ref="w"))

    snapshot = server._snapshot(session)
    handoff_entries = [e for e in snapshot["feed"] if e["kind"] == "handoff"]
    assert len(handoff_entries) == 1
    assert handoff_entries[0]["confidence"] == format_confidence(0.8)
    assert handoff_entries[0]["confidence"] == "güven 0,80"


def test_the_decision_note_reaches_the_screen(client, monkeypatch):
    """`test_console.py:537`'nin yeniden kurulmuş hâli — onay çubuğunun
    cevabı `POST /approve`'un gövdesine düşüyor."""
    session, run_id = _install_session(monkeypatch)
    action_id = session.store.save_action(ActionRecord(
        ts=192.0, tool_name="halt_production_line",
        params={"line_id": "B-Hattı", "rationale": "test"},
        result={"state": "awaiting_approval"}, actor="agent",
        approval="pending"))

    response = client.post(f"/api/run/{run_id}/approve",
                           json={"action_id": action_id, "approved": False})
    assert response.status_code == 200
    assert response.json()["note"] == view.REJECTED_NOTE


def test_deciding_with_nothing_pending_does_not_call_the_supervisor(client, monkeypatch):
    """`test_console.py:545`'in yeniden kurulmuş hâli — bekleyen aksiyon
    yoksa Nöbetçi'nin `approve()`'u HİÇ çağrılmıyor."""
    session, run_id = _install_session(monkeypatch)
    calls = []
    monkeypatch.setattr(session.nobetci, "approve",
                        lambda *a, **k: calls.append((a, k)) or {})

    response = client.post(f"/api/run/{run_id}/approve",
                           json={"action_id": 1, "approved": True})
    assert response.status_code == 200
    assert calls == []
    assert response.json()["note"] == view.UNKNOWN_ACTION_NOTE


def test_pressing_a_button_without_a_session_does_not_crash(client):
    """`test_console.py:875`'in yeniden kurulmuş hâli."""
    response = client.post("/api/run/hic-boyle-bir-kosu-yok/stress/baglam")
    assert response.status_code == 404


def test_an_unknown_key_is_refused_not_sent(client, monkeypatch):
    """`test_console.py:879`'un yeniden kurulmuş hâli — yanlış yazılmış bir
    anahtar sessizce boş mesaj GÖNDERMİYOR."""
    session, run_id = _install_session(monkeypatch)
    calls = []
    monkeypatch.setattr(session.nobetci, "talk", lambda text: calls.append(text))

    response = client.post(f"/api/run/{run_id}/stress/böyle-bir-şey-yok")
    assert response.status_code == 400
    assert calls == []


def test_pressing_a_button_sends_the_canned_text(client, monkeypatch):
    """`test_console.py:888`'in yeniden kurulmuş hâli."""
    session, run_id = _install_session(monkeypatch)
    sent = []
    monkeypatch.setattr(session.nobetci, "talk", lambda text: sent.append(text))

    response = client.post(f"/api/run/{run_id}/stress/baglam")
    assert response.status_code == 200
    assert sent == [view.STRESS_PROMPTS["baglam"][1]]


def test_the_feed_skips_episodes_that_were_in_the_store_before_the_run(client, monkeypatch):
    """`test_console.py:999`'un yeniden kurulmuş hâli — `Session.archived`
    koşudan ÖNCE var olan epizotları besleme dışında bırakıyor."""
    store = Store()
    store.create_episode(Episode(start_ts=0.0, phase="outcome",
                                 summary_tr="geçen ayki kaza",
                                 preliminary_risk="Yüksek", state="closed"))
    monkeypatch.setattr(session_module, "Store", lambda: store)

    session, run_id = _install_session(monkeypatch)
    assert session.archived == {episode.id for episode in store.episodes()}

    snapshot = server._snapshot(session)
    titles = [entry.get("title") for entry in snapshot["feed"]]
    assert "geçen ayki kaza" not in titles


# =============================================================================
# Görev 4 fix turu 1 — `_processed_until_s`'in davranış testleri (KRİTİK 2)
# =============================================================================
#
# `client`/uvicorn fikstürüne ihtiyaç yok: `_processed_until_s` saf bir
# fonksiyon, doğrudan bir `Session` + gerçek (bellek içi) `Store` üzerinde
# sınanıyor. `records[:-1]` koruması silinip `max(end_ts)`'e düşülse bile
# önceki 997 test yeşil kalıyordu — bu dört iddia o regresyonu YAKALIYOR.

def _window(ts, end_ts, index=0, total=1, outcome="routed") -> WindowRecord:
    return WindowRecord(ts=ts, end_ts=end_ts, index=index, total=total,
                        frames=1, floor_passed=True, outcome=outcome)


def test_no_records_means_nothing_processed_yet():
    session = session_module.Session()
    assert server._processed_until_s(session) == 0.0


def test_a_single_record_while_running_is_the_processing_window_not_decided_yet():
    """Tek kayıt İŞLENMEKTE OLAN pencerenin kendisi — henüz karar
    verilmedi, alt sınır `0.0` kalmak ZORUNDA."""
    session = session_module.Session()
    session.store.save_window(_window(ts=0.0, end_ts=10.0))
    assert session.run_state not in ("done", "failed")
    assert server._processed_until_s(session) == 0.0


def test_the_newest_record_is_excluded_while_the_run_is_still_going():
    """EN YENİ kaydı sınıra dahil etmek, henüz karara bağlanmamış bir
    saniyeyi 'karar verildi, olay yok' diye gösterirdi (brief'in
    uyardığı tam o hata). `records[:-1]` silinirse bu `20.0` yerine
    `30.0` döner ve test kırmızıya düşer."""
    session = session_module.Session()
    session.store.save_window(_window(ts=0.0, end_ts=10.0))
    session.store.save_window(_window(ts=10.0, end_ts=20.0))
    session.store.save_window(_window(ts=20.0, end_ts=30.0))
    assert server._processed_until_s(session) == 20.0


def test_a_finished_run_processes_every_record_including_the_last():
    """`run_state == "done"` olunca artık "işlenmekte olan" bir pencere
    yok — sınır bütün kayıtları kapsıyor."""
    session = session_module.Session()
    session.store.save_window(_window(ts=0.0, end_ts=10.0))
    session.store.save_window(_window(ts=10.0, end_ts=20.0))
    session.store.save_window(_window(ts=20.0, end_ts=30.0))
    session.set_state("done")
    assert server._processed_until_s(session) == 30.0


# =============================================================================
# Görev 5 — video servisi, tespitler, kare boyutu (§Adım 1)
# =============================================================================

def test_detections_report_the_inference_frame_size(client):
    """Kutular 0-1 normalize DEĞİL: tam sayı piksel ve uzay orijinal
    video değil, FRAME_WIDTH'e (896) ölçeklenmiş çıkarım karesi.
    Tarayıcı ölçeği tahmin etmemeli."""
    run_id = _finished_run(client)
    body = client.get(f"/api/run/{run_id}/detections?from=0&to=10").json()
    width, height = body["frame_size"]
    assert width > 0 and height > 0
    for item in body["items"]:
        x1, y1, x2, y2 = item["box"]
        assert 0 <= x1 <= width and 0 <= x2 <= width
        assert 0 <= y1 <= height and 0 <= y2 <= height


def test_entropy_reports_a_value_per_frame_and_a_real_threshold(client):
    """Konsolun piksel entropisi grafiği: her kare için bir değer, ve
    sabit bir eşik yerine BU koşunun kendi dağılımından (ortalama + 1,5×std)
    hesaplanmış bir zirve çizgisi."""
    run_id = _finished_run(client)
    body = client.get(f"/api/run/{run_id}/entropy").json()
    assert len(body["items"]) == 4        # _write_frames dört kare yazıyor
    for item in body["items"]:
        assert item["value"] >= 0.0
    assert body["threshold"] is not None


def test_entropy_says_missing_run_instead_of_crashing(client):
    assert client.get("/api/run/none/entropy").status_code == 404


def test_the_frame_size_is_available_while_the_run_is_still_going(client):
    """`Session.frames_dir` koşu boyunca None'dı — demet açması
    `run_pipeline` BİTTİKTEN sonra çalışıyor. Sunucu `output_dir`'i
    kendisi seçtiği için yol ilk saniyeden itibaren biliniyor."""
    run_id = _start_run(client, step_mode=True)
    _wait_for_state(client, run_id, "paused")
    body = client.get(f"/api/run/{run_id}/detections?from=0&to=5").json()
    assert body["frame_size"][0] > 0


def test_the_video_is_served_with_range_support(client):
    run_id = _finished_run(client)
    response = client.get(f"/api/run/{run_id}/video",
                          headers={"Range": "bytes=0-1023"})
    assert response.status_code == 206
    assert response.headers["accept-ranges"] == "bytes"


# =============================================================================
# Görev 5 — istek üzerine açıklamalı kayıt (§Adım 5)
# =============================================================================

def test_annotate_says_what_is_missing_instead_of_failing(client):
    """Koşu yokken uydurma bir yol dönmüyor."""
    assert client.post("/api/run/none/annotate").status_code == 404


def test_an_annotate_failure_reaches_the_screen_instead_of_killing_the_run(
        client, monkeypatch):
    run_id = _finished_run(client)
    monkeypatch.setattr("gozcu.ui.server.annotate_run",
                        _raise(AnnotateError("ffmpeg yok")))
    response = client.post(f"/api/run/{run_id}/annotate")
    assert response.status_code == 409
    assert "ffmpeg" in response.json()["detail"]


def test_a_successful_annotate_returns_a_path_the_player_can_use(client):
    run_id = _finished_run(client)
    body = client.post(f"/api/run/{run_id}/annotate").json()
    assert body["path"].endswith(".mp4")
    assert client.get(body["path"]).status_code == 200


# =============================================================================
# Görev 10 — bas-konuş (STT), yerel `faster-whisper`, kurulu değilse 501
# =============================================================================

def test_stt_returns_501_when_faster_whisper_is_absent(client, monkeypatch):
    """Örnek transkript DÖNMÜYOR. Bu depo uydurulmuş çıktıyı ölçülmüş
    gibi göstermeme kuralını başka her katmanda uyguluyor."""
    monkeypatch.setattr("gozcu.ui.server._whisper", None)
    response = client.post("/api/stt", files={"audio": ("a.webm", b"", "audio/webm")})
    assert response.status_code == 501
    assert "demo" not in response.text


def test_the_wire_carries_whether_stt_is_available(client, monkeypatch):
    """Mikrofon düğmesinin devre dışı çizilip çizilmeyeceğine tarayıcı
    değil sunucu karar veriyor — `agent_marks`/`risk_colors` ile AYNI
    ilke: `/api/meta`'nın `stt_available`'ı `server._whisper is not None`'ın
    AYNEN taşınmış hâli, ikinci bir tahmin JS'te YOK."""
    body = client.get("/api/meta").json()
    assert body["stt_available"] == (server._whisper is not None)

    monkeypatch.setattr(server, "_whisper", None)
    body = client.get("/api/meta").json()
    assert body["stt_available"] is False


# =============================================================================
# Son inceleme turu — yeniden bağlanma, yükleme güvenliği, çöken koşunun
# TEK cümlesi, kök neden paneli ve açıklamalı kayıt düğmesi
# =============================================================================

def _web_file(name: str) -> str:
    """Statik varlığın metni — `test_the_resume_button_is_only_reachable_...`
    ile AYNI desen: tarayıcıda koşan bir kural Python'dan ancak kaynağın
    kendisine bakılarak sabitlenebiliyor."""
    web = pathlib.Path(server.__file__).resolve().parent / "web"
    return (web / name).read_text(encoding="utf-8")


def _code_without_comments(source: str) -> str:
    """Yalnız KOD satırları — `//` ile başlayan satırlar ve blok yorumların
    `*` satırları atılıyor. Bir kuralın yorumda ANLATILMASI ile kodda
    UYGULANMASI ayrı şeyler; "burada yeniden hesaplanmıyor" iddiası
    yorumun kendisine takılmamalı."""
    lines = []
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        lines.append(line)
    return "\n".join(lines)


class TestReattachAfterAReload:
    """Canlı bir koşunun ortasında sayfa yenilenirse konsol ÖKSÜZ kalıyordu.

    `app.runId` sayfada yaşıyor: bir Cmd-R onu `null`'a düşürüyor, SSE hiç
    açılmıyor, her komut sessizce geri dönüyor ve "Analizi Başlat" `409
    "Bir koşu zaten sürüyor."` alıyordu — koşan iş parçacığı tasarım gereği
    durdurulamadığı için geri dönüş de YOKTU. 4 dakikalık jüri demosunda
    kazara bir tuş bütün sunumu götürürdü.
    """

    def test_the_status_names_the_live_run_so_the_page_can_reattach(self, client):
        run_id = _start_run(client, step_mode=True)
        body = client.get("/api/status").json()
        assert body["run_id"] == run_id
        assert body["run_state"] in server.LIVE_RUN_STATES
        assert body["step_mode"] is True

    def test_a_finished_run_is_not_offered_for_reattachment(self, client):
        """Bitmiş koşuya geri bağlanmak kaynak seçiciyi gizler ve operatör
        bir sonraki videoyu HİÇ başlatamazdı — `run_state` tel üzerinde
        duruyor, canlılık koşulu onu eliyor."""
        run_id = _finished_run(client)
        body = client.get("/api/status").json()
        assert body["run_id"] == run_id
        assert body["run_state"] not in server.LIVE_RUN_STATES

    def test_the_status_says_nothing_about_a_run_that_never_started(self, client):
        body = client.get("/api/status").json()
        assert body["run_id"] is None
        assert body["run_state"] is None
        assert body["step_mode"] is False

    def test_the_wire_carries_the_live_run_states_from_one_source(self, client):
        """Canlılık kümesinin İKİNCİ bir yazımı yok: `js/sse.js` düğmeleri
        de yeniden bağlanmayı da bu kümeye göre karar veriyor."""
        body = client.get("/api/meta").json()
        assert body["live_run_states"] == list(server.LIVE_RUN_STATES)
        assert set(body["live_run_states"]) <= set(body["run_states"])

    def test_the_page_reattaches_only_a_live_run(self):
        js = _web_file("js/sse.js")
        assert "function reattachIfLive(status)" in js
        assert "if (!status || !status.run_id || !isLiveRunState(status.run_state)) return;" in js
        # Canlılık JS'te elle sayılmıyor — sunucunun kümesi okunuyor.
        assert 'return (app.meta.live_run_states || []).includes(state);' in js
        assert 'state.run_state === "intervened"' not in js

    def test_reattaching_wires_exactly_what_the_upload_flow_wires(self):
        """İki yol AYNI fonksiyondan geçiyor — ikinci bir kablolama kopyası
        bir gün birinde unutulurdu."""
        js = _web_file("js/sse.js")
        assert js.count("function attachRun(runId)") == 1
        assert js.count("attachRun(") == 3       # tanım + iki çağrı
        for wiring in ("player.setRunId(runId);", "trace.setRunId(runId);",
                       "bench.setRunId(runId);", "connect(runId);",
                       'els.sourcePicker.classList.add("hidden");'):
            assert js.count(wiring) == 1, wiring

    def test_the_liveness_set_is_read_after_the_meta_arrives(self):
        """`reattachIfLive` kümeyi `meta`'dan okuyor: `loadMeta` önce
        BİTMELİ, yoksa yeniden bağlanma boş bir kümeye bakıp hiç
        bağlanmazdı."""
        js = _web_file("js/sse.js")
        assert "await loadMeta();\n  await loadInitialStatus();" in js


class TestPerRunClientStateIsReset:
    """İkinci koşu birincinin defterinin ALTINA yazıyordu.

    `player.js::setRunId` ve `trace.js::setRunId` kendi durumlarını
    sıfırlıyor; `sse.js` tek sıfırlamayan modüldü — `feedLog` hiç
    boşalmıyordu (`feed.js`'in `reset()`'i bile yoktu) ve `lastKnownRisk`
    önceki koşunun son seviyesinde kalıyordu.
    """

    def test_connect_empties_the_feed_and_forgets_the_last_risk(self):
        js = _web_file("js/sse.js")
        connect = js[js.index("function connect(runId)"):]
        body = connect[:connect.index("\n}")]
        assert "feedLog.reset();" in body
        assert "lastKnownRisk = null;" in body
        assert "app.payloadLoaded = false;" in body

    def test_the_feed_log_really_has_a_reset(self):
        js = _web_file("js/feed.js")
        assert "reset() {" in js
        # `#feedEmpty` bu listenin ÇOCUĞU — `innerHTML = ""` onu da silerdi.
        assert 'listElement.querySelectorAll(".feed-entry").forEach' in js
        assert "listElement.innerHTML" not in js


class TestUploadedFilenameCannotEscape:
    """`multipart` `filename`'i istemcinin yazdığı ham metin.

    `baslat()` `0.0.0.0`'a bağlanıyor: sunucu salon ağında kimlik
    doğrulamasız. `../../PWNED.txt` koşu dizininden ÇIKIYORDU.
    """

    def test_a_traversing_filename_stays_inside_the_run_directory(
            self, client, tmp_path):
        outside = tmp_path.parent.parent / "PWNED.txt"
        response = client.post(
            "/api/run",
            files={"video": ("../../PWNED.txt", b"\x00" * 32, "video/mp4")},
            data={"step_mode": "false"})
        assert response.status_code == 200, response.text
        assert not outside.exists()
        assert (tmp_path / "PWNED.txt").exists()

    def test_a_filename_with_a_missing_subdirectory_does_not_500(self, client):
        """Var olmayan bir alt dizin adı yakalanmamış bir
        `FileNotFoundError` ile `500` + yığın izi veriyordu."""
        response = client.post(
            "/api/run",
            files={"video": ("yok/olan/dizin.mp4", b"\x00" * 32, "video/mp4")},
            data={"step_mode": "false"})
        assert response.status_code == 200, response.text

    def test_a_dotdot_filename_falls_back_instead_of_writing_a_directory(self):
        assert server._safe_upload_name("..") == "video.mp4"
        assert server._safe_upload_name(".") == "video.mp4"
        assert server._safe_upload_name(None) == "video.mp4"
        assert server._safe_upload_name("../../PWNED.txt") == "PWNED.txt"
        assert server._safe_upload_name("/etc/passwd") == "passwd"

    def test_an_oversized_upload_is_refused_instead_of_filling_memory(
            self, client, monkeypatch, tmp_path):
        """`await video.read()` (parametresiz) gövdenin TAMAMINI belleğe
        alıyordu. Parça parça okunuyor ve sınır aşılınca `413`."""
        monkeypatch.setattr(server, "MAX_UPLOAD_BYTES", 16)
        monkeypatch.setattr(server, "UPLOAD_CHUNK_BYTES", 8)
        response = client.post(
            "/api/run",
            files={"video": ("k.mp4", b"\x00" * 64, "video/mp4")},
            data={"step_mode": "false"})
        assert response.status_code == 413
        assert response.json()["detail"] == server.UPLOAD_TOO_LARGE
        # Yarım dosya bırakılmıyor ve koşu HİÇ başlamıyor.
        assert not (tmp_path / "k.mp4").exists()
        assert server._SESSION is None


class TestAFailedRunTellsOneStory:
    """Çöken koşuda ekran ÜÇ ayrı şey söylüyordu: afiş "hata", karar paneli
    son değerinde donmuş "sürüyor"/"müdahale edildi", JSON modalı da
    `{"detail": "Analiz henüz koşmadı."}`. Üçüncüsü açıkça yanlış — analiz
    KOŞTU, yalnız bitiremedi."""

    def test_the_payload_404_says_the_run_failed_not_that_it_never_ran(
            self, monkeypatch, client):
        session, run_id = _install_session(monkeypatch)
        session.finish(RuntimeError("boru hattı çöktü"))
        assert session.run_state == "failed"

        response = client.get(f"/api/run/{run_id}/payload")
        assert response.status_code == 404
        assert response.json()["detail"] == view.FAILED_RUN_PAYLOAD

    def test_an_abandoned_run_says_its_output_was_discarded(
            self, monkeypatch, client):
        session, run_id = _install_session(monkeypatch)
        session.abandon()
        response = client.get(f"/api/run/{run_id}/payload")
        assert response.json()["detail"] == view.ABANDONED_RUN_PAYLOAD

    def test_the_decision_panel_always_says_the_real_run_state(self):
        """`decisionMeta` eskiden yalnız `else` dalında yazılıyordu; çöken
        koşuda yük çekilemiyor ve panel son değerinde DONUYORDU."""
        js = _web_file("js/sse.js")
        assert ('els.decisionMeta.textContent = app.payloadLoaded\n'
                '    ? "analiz tamamlandı" : runStateLabelFor(state.run_state);') in js

    def test_the_json_modal_prints_the_servers_sentence_not_the_error_object(self):
        js = _web_file("js/sse.js")
        assert 'els.jsonView.textContent = response.ok\n' in js
        assert '((data && data.detail) || "Çıktı okunamadı.")' in js


class TestTheRootCausePanelIsReachable:
    """`view.root_cause_payload`/`root_cause_state`/`ROOT_CAUSE_MESSAGES`'ın
    HİÇBİR tüketicisi yoktu: emekliye ayrılan konsolda "Kök neden raporu"
    paneli vardı, yenisinde yoktu. Görev 2'nin kararı üç yokluğun
    (`no_run`/`crashed`/`no_notable_event`) çökmemesini şart koşuyordu —
    ve hiçbiri hiçbir yerde çizilmiyordu."""

    def test_the_endpoint_carries_the_report_when_there_is_one(
            self, monkeypatch, client):
        from gozcu.models import Detail, EventSummary, PipelineOutput

        report = {"what_happened": "B-Hattında istif aracı devrildi.",
                  "probable_root_cause": "Olası fren arızası.",
                  "actions_taken": ["Sağlık ekibi çağrıldı."],
                  "prevention_recommendations": ["Fren bakımı öne alınmalı."],
                  "confidence_limits": "Kamera sesi duymuyor."}
        session, run_id = _install_session(monkeypatch)
        session.output = PipelineOutput(
            summary="devrildi", risk="Kritik",
            events=[EventSummary(time="03:12", event="devrildi")],
            actions=["Sağlık ekibini çağır"],
            detail=Detail(root_cause_report=report))

        body = client.get(f"/api/run/{run_id}/root-cause").json()
        assert body["state"] == "ok"
        assert body["message"] is None
        assert body["report"] == report

    def test_the_three_absences_never_collapse_into_one_sentence(
            self, monkeypatch, client):
        from gozcu.models import Detail, EventSummary, PipelineOutput

        def _output(detail):
            return PipelineOutput(
                summary="s", risk="Düşük",
                events=[EventSummary(time="00:01", event="e")],
                actions=["a"], detail=detail)

        session, run_id = _install_session(monkeypatch)
        seen = {}
        for state, output in (("no_run", None),
                              ("crashed", _output(None)),
                              ("no_notable_event",
                               _output(Detail(root_cause_report={})))):
            session.output = output
            body = client.get(f"/api/run/{run_id}/root-cause").json()
            assert body["state"] == state
            assert body["report"] is None
            seen[state] = body["message"]

        assert seen["no_run"] == view.NO_RUN_YET
        assert seen["crashed"] == view.CRASHED_RUN
        assert seen["no_notable_event"] == view.NO_ROOT_CAUSE
        assert len(set(seen.values())) == 3

    def test_the_panel_never_says_a_live_run_has_not_run(self, client):
        """Koşu SÜRERKEN panel "Analiz henüz koşmadı." basıyordu.

        Python'daki dört durum DEĞİŞMEDİ (bkz. `tests/test_view.py::
        TestTheRunInProgressIsNotOneOfTheFourAbsences`): ekran koşu
        canlıyken kök neden sorusunu hiç sormuyor ve sunucunun hazır
        cümlesini basıyor.
        """
        body = client.get("/api/meta").json()
        assert body["root_cause_pending_message"] == view.ROOT_CAUSE_PENDING

        js = _web_file("js/trace.js")
        # Soru canlıyken SORULMUYOR: `if (isLive)` dalı `fetch`'ten ÖNCE
        # dönüyor — `refreshRootCause`'un gövdesinde `/root-cause`'a giden
        # satırdan önce geliyor.
        refresh = js[js.index("async function refreshRootCause(isLive)"):]
        before_fetch = refresh[:refresh.index("/root-cause`")]
        assert "if (isLive) {" in before_fetch
        assert "wireMeta.root_cause_pending_message" in before_fetch
        # Cümlenin kendisi JS'te YAZILMIYOR — `/api/meta`'dan geliyor.
        assert view.ROOT_CAUSE_PENDING not in js

    def test_the_liveness_decision_is_passed_down_not_recomputed(self):
        """Canlılık kararının tek uygulaması `sse.js::isLiveRunState`;
        `trace.js` onu PARAMETRE olarak alıyor, kümeye kendisi
        bakmıyor."""
        sse = _web_file("js/sse.js")
        assert "trace.applyState(state, app.meta, running);" in sse
        assert sse.count("app.meta.live_run_states") == 1

        code = _code_without_comments(_web_file("js/trace.js"))
        assert "live_run_states" not in code

    def test_the_wire_carries_the_turkish_section_headings(self, client):
        body = client.get("/api/meta").json()
        assert body["root_cause_field_labels"] == view.ROOT_CAUSE_FIELD_LABELS
        assert list(body["root_cause_field_labels"]) == list(
            view.ROOT_CAUSE_FIELD_LABELS)
        assert body["root_cause_empty_item"] == view.ROOT_CAUSE_EMPTY_ITEM

    def test_the_panel_exists_and_is_fed_by_the_endpoint(self):
        html = _web_file("index.html")
        assert 'id="rootCauseBody"' in html
        assert "Kök Neden Raporu" in html
        # Koşudan önceki metin `view.NO_RUN_YET`in TA KENDİSİ — ikinci bir
        # yazım değil (`#feedEmpty`/`FEED_EMPTY` ile aynı kural).
        assert view.NO_RUN_YET in html

        js = _web_file("js/trace.js")
        assert "/root-cause`" in js
        # Dal mantığı JS'e KOPYALANMIYOR: durum da cümle de sunucudan.
        assert '"crashed"' not in js and '"no_notable_event"' not in js
        assert "messageEl.textContent = data.message" in js
        # Başlıklar `/api/meta`'dan — ikinci bir çeviri tablosu yok.
        assert "wireMeta.root_cause_field_labels" in js
        assert "Muhtemel kök neden" not in js


class TestTheAnnotateButtonIsReachable:
    """`POST .../annotate` + `GET .../annotated.mp4` Görev 5'ten beri
    kurulu ve testliydi, ama HİÇBİR düğme onları çağırmıyordu — emekliye
    ayrılan konsolda düğme vardı."""

    def test_the_button_exists_and_calls_the_endpoint(self):
        html = _web_file("index.html")
        assert 'id="annotateButton"' in html
        assert 'id="annotateNote"' in html

        js = _web_file("js/sse.js")
        assert "els.annotateButton.addEventListener" in js
        assert "`/api/run/${app.runId}/annotate`" in js
        # Dönen yol oynatıcıya veriliyor (`a_successful_annotate_returns_a_
        # path_the_player_can_use`'un ekran karşılığı).
        assert "els.videoPlayer.src = data.path;" in js

    def test_the_button_is_closed_while_the_run_is_live(self):
        """`annotate_run` diskteki BÜTÜN kareleri yeniden çiziyor; koşu
        sürerken kareler daha yazılıyor."""
        js = _web_file("js/sse.js")
        assert "els.annotateButton.disabled = !app.runId || running;" in js

    def test_a_failure_shows_the_servers_sentence_and_re_arms_the_button(self):
        js = _web_file("js/sse.js")
        assert "(data && data.detail)" in js
        assert "els.annotateButton.disabled = false;" in js


class TestTheTimestampUnitsAreDocumentedAtBothSites:
    """`ts` `/windows`'ta `MM:SS` DİZESİ, `/detections`'ta HAM `float`.
    `player.js::parseMmss` bugün tam olarak bu farkı telafi ediyor;
    uyumsuzluğu "temizleyen" biri zaman çizelgesi aramasını sessizce
    kırardı."""

    def test_both_endpoints_warn_about_the_other(self):
        source = pathlib.Path(server.__file__).read_text(encoding="utf-8")
        windows = source.index("def get_windows(")
        detections = source.index("def get_detections(")
        assert "MM:SS" in source[windows:detections]
        assert "MM:SS" in source[detections:detections + 2000]
        assert source[windows:detections].count("parseMmss") == 1


class TestTheArchiveIsSeededWhenARunStarts:
    """B1'in regresyon kilidi.

    `load_history` bugüne kadar üretimde HİÇBİR yerden çağrılmadı — yalnız
    testlerden. Kod yazıldı, testleri geçti, canlı koşuda hiç devreye
    girmedi. Bu sınıf olmadan tohumlama çağrısı bir gün silinse bütün paket
    yeşil kalır ve arıza aynen geri gelir.
    """

    def test_starting_a_run_seeds_the_archive(self, client, monkeypatch,
                                              tmp_path):
        """B1'in REGRESYONU."""
        from gozcu.ui import server

        called_with = {}

        def fake_load_history(gw, store):
            called_with["store"] = store
            return 3

        monkeypatch.setattr(server, "load_history", fake_load_history)
        monkeypatch.setattr(server, "_work", lambda session, path: None)

        # Dosyayı `tmp_path`'e YAZIP aynı yolu POST etme: `client` fikstürü
        # `server._output_dir_for`'u `tmp_path`'e yamalıyor, yani sunucu aynı
        # dosyanın üstüne yazar. Dosyanın kendi `_post_run` yardımcısı bu
        # yüzden bayt tuple'ı geçiyor — aynı desen.
        response = client.post(
            "/api/run", files={"video": ("klip.mp4", b"sahte mp4 icerigi",
                                         "video/mp4")})
        assert response.status_code == 200

        session = server._SESSION
        assert called_with.get("store") is session.store, (
            "tohumlama koşunun KENDİ tutamağıyla çağrılmalı — memory._client() "
            "anahtarsız modda yerel istemciyi tutamak başına açıyor")
        assert session.archive_count == 3

    def test_a_fresh_session_reports_an_unknown_archive_count(self):
        """`None` "sıfır" DEĞİL, "henüz tohumlanmadı" — sıfır ile bilinmeyeni
        aynı şeye çevirmek `blind` itirafının onarmak için var olduğu hata."""
        from gozcu.ui.session import Session
        assert Session().archive_count is None


class TestTheArchiveCountReachesTheWire:
    """Sayı oturumda duruyorsa yetmez — tele çıkmazsa rozet onu HİÇ görmez.

    `/api/status` `memory`'yi `badges()`'ten değil doğrudan `memory_backend()`
    ten okuyor ve `view.badges`'i yalnız `["gateway"]` için çağırıyor; anahtar
    o uca ELLE konmadıkça açılıştaki rozet sayısız kalır.
    """

    def test_the_status_carries_the_archive_count_of_the_live_session(
            self, client, monkeypatch):
        session, run_id = _install_session(monkeypatch)
        session.archive_count = 4
        assert client.get("/api/status").json()["archive"] == 4

    def test_the_status_reports_an_unseeded_archive_as_unknown(self, client):
        """Koşu yokken sayı `None` — "sıfır kayıt" DEĞİL, "bakılmadı"."""
        assert client.get("/api/status").json()["archive"] is None

    def test_the_snapshot_badges_carry_the_archive_count(
            self, client, monkeypatch):
        session, run_id = _install_session(monkeypatch)
        assert "archive" not in server._snapshot(session)["badges"]
        session.archive_count = 7
        assert server._snapshot(session)["badges"]["archive"] == 7
