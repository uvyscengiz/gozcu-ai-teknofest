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


def test_the_wire_carries_the_one_true_agent_marks_table(client):
    """Görev 6 düzeltme turu — `gozcu/ui/feed.py::AGENT_MARKS`'ın besleme
    girdilerini imzalayan emoji rozetleri tarayıcıda İKİNCİ bir kopya olarak
    elle yazılmıyor; `risk_colors` ile AYNI ilke, aynı test şekli.
    """
    from gozcu.ui.feed import AGENT_MARKS

    body = client.get("/api/meta").json()
    assert body["agent_marks"] == AGENT_MARKS


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
    states = []
    deadline = time.monotonic() + 20.0
    for frame in _frames(client, run_id, deadline=deadline):
        states.append(frame["run_state"])
        # Her çerçeve TAM durum taşıyor — kısmi güncelleme yok.
        assert {"feed", "run_state", "badges", "version"} <= set(frame)
        if frame["run_state"] == "paused":
            break
    assert "paused" in states
    # Video gerçekten durdu: bekleyen bir döngü var.
    assert client.get(f"/api/run/{run_id}/payload").status_code == 404
    assert client.post(f"/api/run/{run_id}/resume").status_code == 200


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
        ts=12.0, source_agent="router", target_agent="interpreter",
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
