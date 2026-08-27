"""FastAPI — web konsolunun sunucu tarafı (§4/§5/§6, tasarım spec'i).

`console.py`'nin (Gradio) yerini alacak yeni sunucu. `console.py` bu görev
boyunca DOKUNULMADAN yaşıyor — Gradio konsolu Görev 11'e kadar bağımsız
çalışıyor.

## Oturum yokken de dürüst cevap

`GET /api/status` koşu başlamadan da cevap veriyor: `Gateway` bugün bir
`Session` ile doğuyor, oturum yokken ağ geçidi sağlığı hiç sorulamaz — bu
uç o durumda `gateway: null` döner, boş bir `500` yerine eksik ama dürüst
bir cevap (§5.1).

## Koşuya bağlı uçlar oturumsuz `404` — ama METİNLE

`payload`/`handoffs`/`actions`/`windows` koşunun kendisine ait: koşu yoksa
`404`. Görev 2 incelemesinin geri getirdiği yükümlülük burada yeniden
kuruluyor: `404`'ün gövdesi boş değil, `detail` alanı Türkçe söylüyor
(`view.NO_RUN_YET`/`view.ROOT_CAUSE_MESSAGES` sabitleri) — "boş JSON" ile
"henüz koşmadı" farklı şeyler, ikincisi birinciymiş gibi görünmemeli.

`kpi` bunun DIŞINDA: algı bloğu (`bench/perception.json`) koşudan bağımsız,
elle etiketlenmiş bir ölçüm — oturum yokken de görünür kalması gerekiyor
(§5.1, `test_perception_kpis_are_visible_before_any_run`).

## Koşu yaşam döngüsü ve SSE (Görev 4)

`POST /api/run` iş parçacığını başlatmadan ÖNCE `session.set_state
("running")` yazıyor — `idle`'da bırakılsaydı ilk SSE çerçevesi
`version = 0` taşırdı. Boru hattı `_work` içinde ayrı bir iş parçacığında
koşuyor; `on_event` o iş parçacığında, olayın TAM ANINDA çağrılıyor —
duraklama bir numara değil, `Session.wait_if_step_mode` orada gerçekten
bloklarken videonun zaman çizelgesi de orada duruyor.

`_snapshot` telin tamamı: SSE her zaman TAM durum taşıyor, kısmi güncelleme
yok — yeniden bağlanma bu yüzden bedavaya çözülüyor. Durumu değiştiren her
komut ucu, mutasyonun ardından `_bump` ile `version`'u artırıp bekleyen
her SSE bağlantısını uyandırıyor.
"""

import asyncio
import importlib.util
import json
import subprocess
import tempfile
import threading
import time
import typing
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import anyio
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from gozcu.config import VLM_BASE_URL, VLM_MODEL
from gozcu.memory import memory_backend
from gozcu.models import ActionRecord, RiskLevel, WindowRecord
from gozcu.run import _announce, run_pipeline
from gozcu.store import Store
from gozcu.ui import view
from gozcu.ui.feed import build_feed
from gozcu.ui.session import HEARTBEAT_S, RUN_STATES, Session

#: Statik dosyaların kökü — içerik Görev 6'da geliyor, bu görevde yalnız
#: `.gitkeep` var. Starlette eksik bir dizine `mount` edilirken AÇILIŞTA
#: hata atıyor; dizin olmadan bu görevden Görev 5'e kadar hiçbir test
#: koşamaz.
WEB_DIR = Path(__file__).resolve().parent / "web"

#: `_ensure_server_running`'in yerel-sunucu tespiti — `console.py`'den
#: AYNEN taşındı.
_LOCAL_HOSTNAMES = ("localhost", "127.0.0.1")
_DEFAULT_LOCAL_PORT = 8000
_server_process = None

app = FastAPI(title="Gözcü")

#: Tek seferde tek koşu (spec §5: "Aynı anda tek koşu"). `_SESSION` aktif
#: koşunun `Session`'ı, `_RUN_ID` onun kimliği — ikisi de koşu başlamadan
#: `None`. Görev 4 `POST /api/run`'ı yazınca ikisini de dolduruyor.
_SESSION: Session | None = None
_RUN_ID: str | None = None

#: `POST /api/run`'ın kontrol-et-sonra-yaz penceresini kapatıyor. `await
#: video.read()` bir askıya alma noktası — kilit olmadan iki eşzamanlı
#: istek ikisi de `is_running()`'i `False` görüp ikisi de `_SESSION`'ı
#: yazabilirdi, birincinin iş parçacığı sahipsiz kalıp aynı team37
#: kotasında ikinciyle yarışırdı (§4'ün 409'unun tam önlemeye çalıştığı
#: şey). `asyncio.Lock` tek olay döngüsünde yeterli — sunucu çok
#: kullanıcılı değil (§ "Koşu kimliği ve tek oturum").
_run_lock = asyncio.Lock()


def current_session() -> Session | None:
    """Aktif koşunun oturumu; koşu yoksa `None`."""
    return _SESSION


def _run_or_404(run_id: str) -> Session:
    """`run_id` aktif koşuyla eşleşmiyorsa Türkçe bir `404` fırlatır.

    Eşleşme testi kasıtlı BASİT: aynı anda tek koşu var, dolayısıyla tek
    doğru `run_id` `_RUN_ID`. Boş bir gövde yerine `detail` alanında
    `view.NO_RUN_YET` taşıyan bir `404` — "koşu yok" sorusunun cevabı
    tel katmanında da kayıp gitmiyor.
    """
    if _SESSION is None or run_id != _RUN_ID:
        raise HTTPException(status_code=404, detail=view.NO_RUN_YET)
    return _SESSION


# =============================================================================
# Yerel mlx-vlm sunucusu — `console._ensure_server_running`'den AYNEN taşındı
# =============================================================================

def _ensure_server_running() -> None:
    """`GOZCU_VLM_BASE_URL`'deki yerel mlx-vlm sunucusunu ayağa kaldırır.

    **Demo yolu buradan geçmiyor:** yorumlayıcı görü kademesini paylaşılan
    `Gateway` üzerinden çağırıyor (`GOZCU_GATEWAY_BASE_URL`). Bu yardımcı,
    ağ geçidi yerine yerel bir mlx-vlm sunucusuna bağlanan çevrimdışı kurulum
    için duruyor ve `baslat(yerel_vlm=True)` ile açıkça isteniyor.

    mlx-vlm kurulu değilken alt süreç **açılmıyor**: `uv run mlx_vlm.server`
    çağrısı sessizce ölür ve konsol 120 saniye boyunca hiçbir şey söylemeden
    bekler. Hata okunur ve ne yapılacağını söylüyor.
    """
    global _server_process
    client = OpenAI(base_url=VLM_BASE_URL, api_key="not-needed")
    try:
        client.models.list()
        return
    except Exception:  # noqa: BLE001 — sunucu yok, kurmayı deneyeceğiz
        pass

    hostname = urlsplit(VLM_BASE_URL).hostname
    if hostname not in _LOCAL_HOSTNAMES:
        raise RuntimeError(
            f"{VLM_BASE_URL} adresindeki sunucuya erişilemiyor ve adres yerel "
            "değil — otomatik başlatma yalnız localhost için çalışıyor. "
            "Sunucuyu elle başlatın ya da adresi düzeltin.")

    if importlib.util.find_spec("mlx_vlm") is None:
        raise RuntimeError(
            f"{VLM_BASE_URL} adresinde sunucu yok ve mlx-vlm kurulu değil. "
            "Apple Silicon'daysan: uv sync --extra dev --extra mac. "
            "Değilsen GOZCU_VLM_BASE_URL'i çalışan bir gateway'e çevir.")

    port = urlsplit(VLM_BASE_URL).port
    port = str(port) if port is not None else str(_DEFAULT_LOCAL_PORT)
    _server_process = subprocess.Popen(
        ["uv", "run", "mlx_vlm.server", "--model", VLM_MODEL, "--port", port])

    for _ in range(60):
        try:
            client.models.list()
            return
        except Exception:  # noqa: BLE001 — sunucu henüz ayakta değil
            time.sleep(2)
    raise RuntimeError(
        f"mlx_vlm.server 120 saniyede {VLM_BASE_URL} adresinde ayağa kalkmadı.")


# =============================================================================
# `GET /api/meta` — teldeki enum kümeleri, hepsi ŞEMADAN TÜRETİLİYOR
# =============================================================================

@app.get("/api/meta")
def get_meta() -> dict:
    """Teldeki enum kümelerinin TEK doğrusu.

    Hiçbiri elle yeniden yazılmıyor: bir enum iki yerde yazılırsa bu depo
    bir kez sessizce öldü (prompt/şema ayrışması). `typing.get_args` şemanın
    kendisinden okuyor.
    """
    return {
        "run_states": list(RUN_STATES),
        "risk_levels": list(typing.get_args(RiskLevel)),
        "window_outcomes": list(typing.get_args(
            WindowRecord.model_fields["outcome"].annotation)),
        "approval_states": list(typing.get_args(
            ActionRecord.model_fields["approval"].annotation)),
    }


# =============================================================================
# `GET /api/status` — koşudan ÖNCE de cevap veriyor (§5.1)
# =============================================================================

@app.get("/api/status")
def get_status() -> dict:
    """Ağ geçidi, hafıza arka ucu, model — oturum yokken `gateway: null`."""
    return {
        "model": VLM_MODEL,
        "memory": memory_backend(),
        "gateway": (view.badges(_SESSION.gw, _SESSION.store)["gateway"]
                   if _SESSION is not None else None),
    }


# =============================================================================
# Koşuya bağlı salt-okunur uçlar
# =============================================================================

@app.get("/api/run/{run_id}/payload")
def get_payload(run_id: str) -> dict:
    """Teslim edilen dört anahtar + `detail` (`PipelineOutput`)."""
    session = _run_or_404(run_id)
    payload = view.payload_dict(session.output)
    if payload is None:
        raise HTTPException(status_code=404, detail=view.NO_RUN_YET)
    return payload


@app.get("/api/run/{run_id}/handoffs")
def get_handoffs(run_id: str) -> list:
    """Devir defteri — `view.handoff_rows`."""
    session = _run_or_404(run_id)
    return view.handoff_rows(session.store.handoffs())


@app.get("/api/run/{run_id}/actions")
def get_actions(run_id: str) -> list:
    """Araç şeridi — `view.tool_rows`."""
    session = _run_or_404(run_id)
    return view.tool_rows(session.store.actions())


@app.get("/api/run/{run_id}/windows")
def get_windows(run_id: str) -> list:
    """Pencere kayıtları — Şeffaflık görünümünün ham verisi (§7.3).

    `view.py`'de bu şeklin bir derleyicisi yok (Görev 2'nin kapsamı
    değildi) — alanlar burada, `WindowRecord`'un kendisinden, doğrudan
    seçildi. `processed_until_s`'i hesaplayacak olan Görev 4/5 bu şekli
    genişletebilir; şu an yalnız oturumsuzken çökmemesi gerekiyor.
    """
    from gozcu.agents.router import mmss

    session = _run_or_404(run_id)
    return [{"ts": mmss(record.ts), "end_ts": mmss(record.end_ts),
             "outcome": record.outcome, "detections": record.detections,
             "person_peak": record.person_peak,
             "floor_passed": record.floor_passed,
             "vision_budgeted": record.vision_budgeted}
            for record in session.store.window_records()]


@app.get("/api/run/{run_id}/kpi")
def get_kpi(run_id: str) -> dict:
    """KPI blokları — algı bloğu koşudan BAĞIMSIZ, hep görünür (§5.1).

    Karar/performans blokları aktif oturumun deposundan; oturum yoksa boş
    (bellek içi) bir depodan — ikisi de `view.kpi_payload`'ın aynı ölçülemedi
    kuralına tabi, uydurulan bir sayı yok.
    """
    store = _SESSION.store if _SESSION is not None else Store()
    elapsed_s = _SESSION.elapsed_s() if _SESSION is not None else None
    return view.kpi_payload(store, elapsed_s)


# =============================================================================
# Koşu başlatma — arka plan iş parçacığı, boru hattı geri çağrıları (§4)
# =============================================================================

def _output_dir_for(run_id: str) -> Path:
    """Koşu başına YENİ bir dizin.

    `extract_frames` hedef dizindeki eskinin karelerini siliyor
    (`gozcu/frames.py:30`); aynı dizin iki koşu arasında paylaşılsaydı ikinci
    koşu kare boyutunu (§7.2) birincinin kareleri üzerinden okuyabilirdi. Ad
    kasıtlı ayrı bir fonksiyon: testler bunu kendi `tmp_path`'lerine
    yamalıyor.
    """
    base = Path(tempfile.gettempdir()) / "gozcu-web-runs" / run_id
    base.mkdir(parents=True, exist_ok=True)
    return base


def _on_loop_ready(session: Session):
    """`DecisionLoop` doğunca BİR KEZ çağrılıyor — `/gateway/restore`'un
    `catch_up()` için ihtiyaç duyduğu canlı döngü referansı böyle geliyor."""
    def handler(loop) -> None:
        with session.loop_lock:
            session.loop = loop
    return handler


def _on_event(session: Session):
    """Boru hattı iş parçacığında, olayın TAM ANINDA çağrılıyor.

    `step_mode` açıkken burada GERÇEKTEN bloklanıyor: videonun zaman
    çizelgesi de o an duruyor. Kapalıyken müdahale anı damgalanıp koşu
    sürüyor (25 Ağustos kararı).
    """
    def handler(event) -> None:
        with session.loop_lock:
            session.events.append(event)
        if session.step_mode:
            # Burada bloklanıyor: videonun zaman çizelgesi gerçekten duruyor.
            session.wait_if_step_mode()
        else:
            # Kapalıyken koşu sürüyor, an damgalanıyor (25 Ağustos kararı).
            session.note_intervention()
    return handler


def _work(session: Session, video_path) -> None:
    """Boru hattını ayrı iş parçacığında sürer; bitişi/hatayı `Session`'a yazar."""
    try:
        session.output, _ = run_pipeline(
            video_path, store=session.store, gw=session.gw,
            nobetci=session.nobetci, output_dir=session.output_dir,
            on_event=_on_event(session), on_loop_ready=_on_loop_ready(session))
    except Exception as error:      # noqa: BLE001 — ekranda görünmeli
        session.finish(error)
    else:
        session.finish()            # Terk edilmişse `done` YAZMIYOR.


class RunStartResponse(BaseModel):
    run_id: str


@app.post("/api/run", response_model=RunStartResponse)
async def post_run(video: UploadFile = File(...),
                   step_mode: bool = Form(False)) -> RunStartResponse:
    """Video yükler, koşuyu arka planda başlatır, `run_id` döner.

    **Aynı anda tek koşu.** İkinci koşu canlı bir koşu varken `409` alıyor —
    iptal mekanizması yok, koşan iş parçacığı durdurulamıyor; iki eşzamanlı
    koşu aynı uzak gateway'e (team37 kotası) yarışırdı (§4).

    İş parçacığı başlamadan ÖNCE `set_state("running")` yazılıyor: `idle`'da
    bırakılsaydı ilk SSE çerçevesi `version = 0` taşırdı.

    **Kontrol-et-sonra-yaz penceresi `_run_lock` altında.** `await
    video.read()` bir askıya alma noktası; kilit olmadan iki eşzamanlı
    `POST` ikisi de "koşu yok" görüp ikisi de `_SESSION`'ı yazabilirdi —
    birincinin iş parçacığı sahipsiz kalır, aynı team37 kotasında
    ikinciyle yarışırdı. Kilit `thread.start()`'a kadar TUTULUYOR: `409`
    denetimi `is_running()`e (yani `thread.is_alive()`'a) dayanıyor ve
    iş parçacığı başlamadan önce bu her zaman yanlış — kilit erken
    bırakılsaydı ikinci istek AYNI pencereden geçerdi.
    """
    global _SESSION, _RUN_ID

    async with _run_lock:
        if _SESSION is not None and _SESSION.is_running():
            raise HTTPException(status_code=409,
                                detail="Bir koşu zaten sürüyor.")

        run_id = uuid4().hex
        session = Session()
        output_dir = _output_dir_for(run_id)
        video_path = output_dir / (video.filename or "video.mp4")
        video_path.write_bytes(await video.read())

        session.output_dir = output_dir
        session.video_path = video_path
        session.step_mode = bool(step_mode)
        session.set_state("running")

        thread = threading.Thread(target=_work, args=(session, video_path),
                                  daemon=True)
        session.thread = thread
        _SESSION = session
        _RUN_ID = run_id
        thread.start()
    return RunStartResponse(run_id=run_id)


# =============================================================================
# SSE — durum yayını (§6). Tek olay tipi, gövdesi HER ZAMAN tam durum.
# =============================================================================

def _processed_until_s(session: Session) -> float:
    """EN YENİ kayıt hariç en büyük `end_ts`; koşu bitince hepsi.

    Kayıt pencere İŞLENMEDEN yazılıyor (`loop.py:781`), yani en yeni kayıt
    işlenmekte olan penceredir. Onu dışlamak doğru bir ALT sınır veriyor —
    sınırı abartmak, henüz karar verilmemiş bir saniyeyi "karar verildi,
    olay yok" diye göstermek olurdu.

    `set_window_outcome`'a bağlanamaz: iki çağrı yeri de `"deferred"`
    yazıyor (`loop.py:797, 813`), sağlıklı pencere akıbetini `save_window`
    anında alıyor ve bir daha güncellenmiyor — o mekanizmayla sınır
    sağlıklı koşuda sonsuza dek 0'da kalırdı.
    """
    records = session.store.window_records()
    if not records:
        return 0.0
    if session.run_state in ("done", "failed"):
        return max(record.end_ts for record in records)
    if len(records) == 1:
        return 0.0
    return max(record.end_ts for record in records[:-1])


def _snapshot(session: Session) -> dict:
    """Tam durum. Delta yok: yeniden bağlanma bedavaya çözülüyor."""
    pending = session.nobetci.pending_approval()
    return {
        "version": session.version,
        "run_state": session.run_state,
        "feed": [entry.model_dump() for entry in build_feed(
            session.store, session.escalated_ids(), session.archived)],
        "pending": view.pending_payload(pending),
        "badges": view.badges(session.gw, session.store),
        "processed_until_s": _processed_until_s(session),
        "pending_deferred_ts": sorted(session.pending_deferred_ts()),
        "elapsed_s": session.elapsed_s(),
    }


async def _stream(session: Session):
    """SSE üreteci — bağlanır bağlanmaz tam durum, sonra yalnız değişince.

    `_snapshot` `anyio.to_thread.run_sync` İÇİNDE çağrılıyor, `get_events`'in
    kendi olay döngüsü iş parçacığında DEĞİL: `_snapshot` `loop_lock`'u iki
    kez alıyor (`escalated_ids`, `pending_deferred_ts`) ve `POST
    .../gateway/restore` aynı kilidi `catch_up()`'ın SÜRESİNCE tutuyor
    (`session.py:53-55`'in `loop_lock`'u `cond` yerine seçme gerekçesi tam
    olarak buydu — SSE bekleyenlerini dondurmamak). `_snapshot` doğrudan
    olay döngüsünde çalışsaydı bu donma yalnız yer değiştirirdi: bir
    telafi sürerken olay döngüsü `loop_lock`'u beklerken TÜM SSE
    bağlantıları ve bütün diğer istekler donardı — tam da jürinin önünde
    olacak an (demo beat 6).

    `seen` her yerde `_snapshot`'TAN ÖNCE okunuyor: tersi olsaydı (önce
    çerçeveyi kur, sonra `seen`'i oku) araya giren bir `bump()` hiç
    `seen`'e yansımadan "görülmüş" sayılır ve o güncelleme bir daha asla
    gönderilmezdi.
    """
    seen = session.version
    yield {"event": "state", "data": json.dumps(
        await anyio.to_thread.run_sync(_snapshot, session))}
    while True:
        changed = await anyio.to_thread.run_sync(
            session.wait_for_version, seen, HEARTBEAT_S)
        if changed:
            seen = session.version
            yield {"event": "state", "data": json.dumps(
                await anyio.to_thread.run_sync(_snapshot, session))}
        else:
            # Kalp atışı DURUM TAŞIMIYOR — yalnız bağlantıyı canlı tutuyor.
            yield {"comment": "keepalive"}


@app.get("/api/run/{run_id}/events")
async def get_events(run_id: str) -> EventSourceResponse:
    session = _run_or_404(run_id)
    return EventSourceResponse(_stream(session))


# =============================================================================
# Komut uçları — `Session`/`Supervisor`/`Gateway` metotlarına ince sarmalayıcılar
# =============================================================================

def _bump(session: Session) -> None:
    """`session.bump()`'ı kilit alarak çağıran sarmalayıcı — komut uçları
    `cond`'u kendileri tutmuyor."""
    with session.cond:
        session.bump()


class ApproveBody(BaseModel):
    action_id: int
    approved: bool


class SayBody(BaseModel):
    text: str


class StepModeBody(BaseModel):
    enabled: bool


@app.post("/api/run/{run_id}/abandon")
def post_abandon(run_id: str) -> dict:
    """Duraklamayı çözer, koşuyu BİTİRMEZ — çıktısı `finish()`'te atılır."""
    session = _run_or_404(run_id)
    session.abandon()
    return {"ok": True}


@app.post("/api/run/{run_id}/resume")
def post_resume(run_id: str) -> dict:
    """Duraklamış döngüyü ilerletir; duraklamamışken `409` — jeton yazılmaz."""
    session = _run_or_404(run_id)
    if not session.request_resume():
        raise HTTPException(status_code=409, detail="Koşu duraklamış değil.")
    return {"ok": True}


@app.post("/api/run/{run_id}/step-mode")
def post_step_mode(run_id: str, body: StepModeBody) -> dict:
    """Anahtar koşu SIRASINDA da değişebilir; terk edilmiş koşuda `{enabled:
    true}` `409` — kabul edilseydi duraklama yeniden kurulurdu (§4)."""
    session = _run_or_404(run_id)
    if not session.set_step_mode(body.enabled):
        raise HTTPException(status_code=409,
                            detail="Terk edilmiş koşuda adım adım açılamaz.")
    return {"ok": True}


@app.post("/api/run/{run_id}/approve")
def post_approve(run_id: str, body: ApproveBody) -> dict:
    """**Onayla** / **Reddet** — bekleyen aksiyon yoksa Nöbetçi HİÇ çağrılmaz."""
    session = _run_or_404(run_id)
    pending = session.nobetci.pending_approval()
    if pending is None:
        return {"note": view.UNKNOWN_ACTION_NOTE, "pending": None}
    note, pending_after = view.apply_approval(
        session.nobetci, body.action_id, body.approved)
    _bump(session)
    return {"note": note, "pending": view.pending_payload(pending_after)}


@app.post("/api/run/{run_id}/say")
def post_say(run_id: str, body: SayBody) -> dict:
    """Sohbet paneli — bir diyalog turu. Boş metin Nöbetçi'ye gitmiyor."""
    session = _run_or_404(run_id)
    text = (body.text or "").strip()
    if text:
        session.nobetci.talk(text)
        _bump(session)
    return {"ok": True}


@app.post("/api/run/{run_id}/stress/{key}")
def post_stress(run_id: str, key: str) -> dict:
    """Zorlu koşul düğmesi — bilinmeyen anahtar sessizce boş mesaj GÖNDERMEZ."""
    session = _run_or_404(run_id)
    prompt = view.STRESS_PROMPTS.get(key)
    if prompt is None:
        raise HTTPException(status_code=400,
                            detail=f"Bilinmeyen zorlu koşul: {key}")
    session.nobetci.talk(prompt[1])
    _bump(session)
    return {"label": prompt[0]}


@app.post("/api/run/{run_id}/gateway/cut")
def post_gateway_cut(run_id: str) -> dict:
    """**Bağlantıyı kes** — görü kademesine kesinti enjekte eder."""
    session = _run_or_404(run_id)
    session.gw.inject_failure({"vlm"})
    _bump(session)
    return view.badges(session.gw, session.store)


@app.post("/api/run/{run_id}/gateway/restore")
def post_gateway_restore(run_id: str) -> dict:
    """**Bağlantıyı geri ver** — kesintiyi kaldırır VE açığı kapatır.

    İki adım tek uçta: yalnız `inject_failure(set())` yapılsaydı atlanan
    pencereler kuyrukta kalır, telafi hiç görünmezdi. `loop_lock` canlı
    döngüyle aynı `deferred` listesine dokunan tek koruma (bugünkü
    `console.py:767-772` ile aynı desen).
    """
    session = _run_or_404(run_id)
    session.gw.inject_failure(set())
    recovered = 0
    if session.loop is not None:
        with session.loop_lock:
            for event in session.loop.catch_up():
                _announce(session.store, session.nobetci, event, None)
                session.events.append(event)
                recovered += 1
    _bump(session)
    return {"recovered": recovered, "badges": view.badges(session.gw, session.store)}


# =============================================================================
# Statik dosyalar — içerik Görev 6'da geliyor
# =============================================================================

app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="static")


# =============================================================================
# Giriş noktası — `app.py` yalnız bunu çağırıyor
# =============================================================================

def baslat(yerel_vlm: bool = False, **launch) -> None:
    """Sunucuyu açar.

    `yerel_vlm=True` çevrimdışı kurulum içindir: görü kademesi paylaşılan ağ
    geçidi yerine yerel bir mlx-vlm sunucusundan geliyorsa sunucu önce ayağa
    kaldırılır. Demo yolu bunu kullanmıyor (`console.baslat`'la AYNI kural).
    """
    import uvicorn

    if yerel_vlm:
        _ensure_server_running()
    launch.setdefault("host", "0.0.0.0")
    launch.setdefault("port", 7860)
    uvicorn.run(app, **launch)
