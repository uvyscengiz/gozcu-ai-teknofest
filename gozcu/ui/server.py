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

## Video, tespitler ve kare boyutu (Görev 5)

`Detection.box` 0-1 normalize DEĞİL: tam sayı **piksel** ve uzay orijinal
video değil, `extract_frames`'in ölçeklediği çıkarım karesi (`FRAME_WIDTH`,
`gozcu/config.py`). Tarayıcı bu ölçeği TAHMİN ETMEMELİ — `GET
.../detections` bu yüzden `frame_size`'ı her yanıtta taşıyor. Boyut
`session.output_dir`'deki ilk `frame_*.jpg`'den BİR KEZ okunup
`session.frame_size`'a önbelleğe alınıyor; sunucu bu dizini kendisi
seçtiği için (`_output_dir_for`) yol koşu BİTMEDEN de bilinir — Görev 4'ün
sağladığı garanti burada tekrar kullanılıyor.

`GET .../video`'nun `Range` desteği `FileResponse`'a bırakılmıyor: davranışı
Starlette sürümüne göre değişiyor. Uç başlığı kendisi ayrıştırıp `206` ile
`content-range`/`accept-ranges` yazıyor, başlık yoksa `200` ve tam gövde —
aranabilirlik operatörün zaman çizelgesine tıklayabilmesinin ta kendisi.

## Açıklamalı kayıt İSTEK ÜZERİNE (Görev 5)

`annotate_run` (`gozcu/annotate.py:129`) bütün kareleri yeniden çiziyor ve
bir kalp atışına sığmaz — koşuyla birlikte DEĞİL, `POST .../annotate`
tıklanınca üretiliyor. Üretilen dosya `session.output_dir/annotated.mp4`'e
yazılıp `GET .../annotated.mp4` üzerinden servis ediliyor; `annotate_run`
başarısız olursa (`AnnotateError`) koşu düşmüyor, hata `409` ile ekrana
taşınıyor.
"""

import asyncio
import importlib.util
import json
import mimetypes
import re
import subprocess
import tempfile
import threading
import time
import typing
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import anyio
from fastapi import (FastAPI, File, Form, HTTPException, Query, Request,
                     Response, UploadFile)
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

#: `NO_FRAMES`: kare boyutu okunamıyorsa (henüz kare yazılmamış/silinmiş)
#: hem `/detections` hem de çizim tarafı AYNI Türkçe mesajı taşısın diye
#: oradan alınıyor — iki ayrı cümle aynı durumu anlatırsa biri güncellenip
#: diğeri unutulur.
from gozcu.annotate import NO_FRAMES, AnnotateError, annotate_run
from gozcu.config import VLM_BASE_URL, VLM_MODEL
from gozcu.memory import memory_backend
from gozcu.models import ActionRecord, RiskLevel, WindowRecord
from gozcu.run import _announce, run_pipeline
from gozcu.store import Store
from gozcu.ui import view
from gozcu.ui.feed import (AGENT_MARKS, OUTCOME_LABELS, PROACTIVE_MARK,
                          RISK_COLORS, build_feed, format_confidence)
from gozcu.ui.session import HEARTBEAT_S, RUN_STATES, Session

#: `faster-whisper` `stt` EKSTRASI ile gelen İSTEĞE BAĞLI bir bağımlılık
#: (`pyproject.toml::[project.optional-dependencies]`) — ana bağımlılık
#: DEĞİL. Kurulu değilse `_whisper` `None` kalır ve `POST /api/stt` `501`
#: döner; ASLA örnek/uydurulmuş bir transkriptle devam etmez. `_whisper`
#: burada SINIFIN kendisi (`WhisperModel`), yüklenmiş bir model DEĞİL —
#: testler onu doğrudan `None`'a yamalayıp "kurulu değil" durumunu
#: gerçek ortamdan bağımsız sınayabiliyor.
try:
    from faster_whisper import WhisperModel as _whisper
except ImportError:  # noqa: BLE001 — ekstra kurulu değil, `501` yolu geçerli
    _whisper = None

#: Açıklamalı kayıt henüz üretilmemişken `GET .../annotated.mp4`'ün
#: dönmesi gereken Türkçe mesaj.
NO_ANNOTATED_YET = ("Açıklamalı kayıt henüz üretilmedi — önce "
                    "POST .../annotate çağrılmalı.")

#: Koşunun videosu diskte yoksa (beklenmeyen bir durum — `video_path`
#: koşu başlarken yazılıyor) `GET .../video`'nun dönmesi gereken mesaj.
NO_VIDEO_YET = "Bu koşu için video bulunamadı."

#: `faster-whisper` kurulu değilken `POST /api/stt`'nin dönmesi gereken
#: mesaj — kural: örnek/uydurulmuş bir transkript YOK, dürüst bir `501`.
STT_NOT_INSTALLED = ("Yerel konuşma tanıma (faster-whisper) kurulu değil. "
                    "Kurulum için: uv sync --extra stt")

#: `Range: bytes=start-end` — ikisi de isteğe bağlı (`bytes=500-`,
#: `bytes=-500`). Grup boşsa (`bytes=-`) eşleşme `_parse_range`'de elenir.
_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")

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

    `risk_colors` aynı ilkeyi renge uyguluyor (Görev 6): tarayıcıda karar
    veren hiçbir şey yaşamıyor, risk rengi de dahil — `gozcu/ui/feed.py`'nin
    besleme kartlarını (`FeedEntry.card`) zaten boyadığı `RISK_COLORS`
    sözlüğü burada AYNEN taşınıyor, CSS/JS'te ikinci bir renk tablosu elle
    yazılmıyor (bir gün ayrışıp iki ekranın aynı riski iki renkle göstermesi
    ihtimaline karşı).

    `agent_marks` AYNI ilkeyi emojiye uyguluyor (Görev 6 düzeltme turu):
    `gozcu/ui/feed.py::AGENT_MARKS` — besleme girdilerini imzalayan
    rozetlerin tek kaynağı — burada AYNEN taşınıyor, `js/feed.js`'te ikinci
    bir kopyası elle YAZILMIYOR.

    `badge_labels` aynı ilkeyi üst bar rozetlerinin (`gateway`/`memory`/
    `run`) Türkçe karşılığına uyguluyor: `gozcu/ui/view.py::BADGE_LABELS`
    buradan taşınıyor, tarayıcı çıplak `"healthy"`/`"qdrant"`/`"measured"`
    gibi İngilizce enum değerlerini EKRANA basmıyor — bu değerler `state.
    badges`'ta HAM kalıyor (o zaten teldeki enum), yalnız Türkçe etiketi
    ayrıca burada.

    `run_state_labels` AYNI ilkeyi `run_state`'in kendisine uyguluyor:
    `gozcu/ui/view.py::RUN_STATE_LABELS` (`RUN_STATES`'ten türetilen
    anahtar kümesiyle doğrulanmış) buradan taşınıyor — `js/sse.js`'in
    kendi elinde tuttuğu bir çeviri tablosu YOK.

    `proactive_mark` AYNI ilkeyi `gozcu/ui/feed.py::PROACTIVE_MARK`'a
    uyguluyor (Görev 6 düzeltme turu 2) — kimse sormadan söylenmiş bir
    süpervizör satırının rozeti, `js/feed.js`'te ikinci bir elle yazılmış
    kopyası YOK.

    `window_outcome_labels` AYNI ilkeyi `gozcu/ui/feed.py::OUTCOME_LABELS`'a
    uyguluyor (Görev 8 düzeltme turu) — pencere defterinin dört akıbet
    dalının (`routed`/`forced`/`skipped`/`deferred`) Türkçesi, `trace.js`'te
    ikinci bir elle yazılmış kopyası YOK. `window_outcomes` (ham enum) ile
    AYNI anahtar kümesini taşımak ZORUNDA — testte doğrulanıyor.

    `decision_bucket_labels` AYNI ilkeyi Performans görünümünün dağılım
    grafiğine uyguluyor (Görev 9): `gozcu/ui/view.py::
    DECISION_BUCKET_LABELS` — `benchmark.kpi.DECISION_BUCKETS`'ın beş ham
    kova adının Türkçesi, `bench.js`'te ikinci bir kopyası YOK.

    `kpi_unmeasured` (Görev 9) `gozcu/ui/view.py::KPI_UNMEASURED`'ın
    kendisi — `bench.js` ölçülemeyen bir hücreyi soluk göstermek için bu
    sözcüğü tanımak zorunda, ama sözcüğün ikinci bir yazımı burada YOK.

    `stt_available` (Görev 10) AYNI ilkeyi bas-konuşa uyguluyor: mikrofon
    düğmesinin devre dışı çizilip çizilmeyeceğine karar veren tarayıcı
    DEĞİL — `_whisper is not None` (`faster-whisper` kurulu mu) burada,
    sunucuda, tek yerde soruluyor. Deneme-yanılma yok: buton, bir ses
    kaydı gönderip `501` almadan ÖNCE, sayfa açılırken zaten doğru
    çiziliyor.
    """
    return {
        "run_states": list(RUN_STATES),
        "run_state_labels": dict(view.RUN_STATE_LABELS),
        "risk_levels": list(typing.get_args(RiskLevel)),
        "risk_colors": dict(RISK_COLORS),
        "agent_marks": dict(AGENT_MARKS),
        "proactive_mark": PROACTIVE_MARK,
        "badge_labels": dict(view.BADGE_LABELS),
        "window_outcomes": list(typing.get_args(
            WindowRecord.model_fields["outcome"].annotation)),
        "window_outcome_labels": dict(OUTCOME_LABELS),
        "approval_states": list(typing.get_args(
            ActionRecord.model_fields["approval"].annotation)),
        "decision_bucket_labels": dict(view.DECISION_BUCKET_LABELS),
        "kpi_unmeasured": view.KPI_UNMEASURED,
        "stt_available": _whisper is not None,
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
# Video servisi ve tespitler — kare boyutu ELLE ÖLÇÜLÜYOR, TAHMİN EDİLMİYOR
# =============================================================================

def _parse_range(range_header: str, file_size: int) -> tuple[int, int] | None:
    """`Range: bytes=start-end` ayrıştırır. Geçersiz/karşılıksız → `None`
    (çağıran bunu tam gövde — `200` — anlamına alıyor).

    `end` dosya boyutuna KIRPILIYOR: tarayıcı sık sık dosyanın gerçek
    boyutundan büyük bir üst sınır ister (ör. `bytes=0-1023` 32 baytlık bir
    dosyada), bunu reddetmek yerine elde ne varsa onu vermek istemcinin
    beklediği davranış.
    """
    match = _RANGE_RE.fullmatch(range_header.strip())
    if not match:
        return None
    start_text, end_text = match.groups()
    if not start_text and not end_text:
        return None
    if start_text:
        start = int(start_text)
        end = int(end_text) if end_text else file_size - 1
    else:
        # `bytes=-500`: SON 500 bayt.
        suffix_length = int(end_text)
        start = max(file_size - suffix_length, 0)
        end = file_size - 1
    end = min(end, file_size - 1)
    if start < 0 or start > end:
        return None
    return start, end


def _serve_file_with_range(path: Path, range_header: str | None) -> Response:
    """`Range` desteğiyle bir dosyayı servis eder — `FileResponse`'a
    BIRAKILMIYOR: davranışı Starlette sürümüne göre değişiyor. Aranabilirlik
    operatörün zaman çizelgesine tıklayabilmesinin ta kendisi (§Görev 5).
    """
    file_size = path.stat().st_size
    media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    start, end, status_code = 0, file_size - 1, 200
    if range_header:
        parsed = _parse_range(range_header, file_size)
        if parsed is not None:
            start, end, status_code = *parsed, 206

    with path.open("rb") as handle:
        handle.seek(start)
        body = handle.read(end - start + 1)

    headers = {"accept-ranges": "bytes", "content-length": str(len(body))}
    if status_code == 206:
        headers["content-range"] = f"bytes {start}-{end}/{file_size}"
    return Response(content=body, status_code=status_code,
                    media_type=media_type, headers=headers)


@app.get("/api/run/{run_id}/video")
def get_video(run_id: str, request: Request) -> Response:
    """Yüklenen ham video — `Range` destekli (yukarı bakın)."""
    session = _run_or_404(run_id)
    if session.video_path is None or not Path(session.video_path).exists():
        raise HTTPException(status_code=404, detail=NO_VIDEO_YET)
    return _serve_file_with_range(Path(session.video_path),
                                  request.headers.get("range"))


def _frame_size_for(session: Session) -> tuple[int, int]:
    """`session.frame_size`'ı BİR KEZ doldurur — `session.output_dir`'deki
    ilk `frame_*.jpg`'den gerçek piksel boyutu okunuyor, TAHMİN EDİLMİYOR.

    `Detection.box` 0-1 normalize DEĞİL: `gozcu/detect.py:36` tam sayı piksel
    üretiyor ve uzay `extract_frames`'in ölçeklediği çıkarım karesi
    (`FRAME_WIDTH`, `gozcu/config.py`) — orijinal video değil. Tarayıcı bu
    ölçeği kendi başına çıkaramaz.
    """
    if session.frame_size is not None:
        return session.frame_size
    frames = sorted(Path(session.output_dir).glob("frame_*.jpg"))
    if not frames:
        raise HTTPException(status_code=404, detail=NO_FRAMES)
    import cv2

    image = cv2.imread(str(frames[0]))
    if image is None:
        raise HTTPException(status_code=404, detail=NO_FRAMES)
    height, width = image.shape[:2]
    session.frame_size = (width, height)
    return session.frame_size


@app.get("/api/run/{run_id}/detections")
def get_detections(run_id: str, from_: float = Query(..., alias="from"),
                   to: float = Query(...)) -> dict:
    """`[from, to]` aralığındaki gözlemlerin kutuları + çıkarım karesinin
    boyutu — ikisi BİRLİKTE gidiyor ki tarayıcı ölçeği tahmin etmesin.
    """
    session = _run_or_404(run_id)
    width, height = _frame_size_for(session)
    items = [{"ts": observation.ts, "box": list(detection.box),
             "label": detection.label, "confidence": detection.confidence,
             "track_id": detection.track_id}
            for observation in session.store.observations()
            if from_ <= observation.ts <= to
            for detection in observation.detections]
    return {"frame_size": [width, height], "items": items}


# =============================================================================
# Açıklamalı kayıt — İSTEK ÜZERİNE üretiliyor, koşuyla birlikte DEĞİL (§Adım 5)
# =============================================================================

@app.post("/api/run/{run_id}/annotate")
def post_annotate(run_id: str) -> dict:
    """`annotate_run` bütün kareleri yeniden çiziyor ve bir kalp atışına
    sığmaz (`gozcu/annotate.py:129`) — bu yüzden koşuyla birlikte DEĞİL, bu
    uca ayrı bir tıklamayla üretiliyor. Hata koşuyu DÜŞÜRMEZ: `AnnotateError`
    `409`'a çevrilip ekranda gösteriliyor.
    """
    session = _run_or_404(run_id)
    out_path = Path(session.output_dir) / "annotated.mp4"
    try:
        annotate_run(session.output_dir, session.store, out_path)
    except AnnotateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"path": f"/api/run/{run_id}/annotated.mp4"}


@app.get("/api/run/{run_id}/annotated.mp4")
def get_annotated_video(run_id: str, request: Request) -> Response:
    """`POST .../annotate`'in ürettiği dosya — o henüz çağrılmadıysa `404`."""
    session = _run_or_404(run_id)
    out_path = Path(session.output_dir) / "annotated.mp4"
    if not out_path.exists():
        raise HTTPException(status_code=404, detail=NO_ANNOTATED_YET)
    return _serve_file_with_range(out_path, request.headers.get("range"))


# =============================================================================
# Bas-konuş (STT) — yerel `faster-whisper`, kurulu değilse `501` (Görev 10)
# =============================================================================

#: Yüklenmiş model — İSTEK BAŞINA DEĞİL, bir kez kurulup önbelleğe alınıyor
#: (`WhisperModel(...)` ağırlıkları diskten okuyor, her istekte tekrarı
#: gereksiz). `_whisper` (SINIF/`None`) kurulu olup olmadığını söylüyor,
#: `_whisper_model` (ÖRNEK) kurulmuşsa gerçek modeli tutuyor.
_whisper_model = None


def _transcribe(audio_path: str) -> str:
    """Modeli (bir kez) kurar ve dosyayı Türkçe metne çevirir.

    `WhisperModel.transcribe` bir GENERATOR döndürüyor — asıl iş segment
    üzerinde YİNELERKEN oluyor. İkisi de burada, TEK bir iş parçacığı
    çağrısının içinde: `segments` üreteci olay döngüsüne sızıp orada
    tüketilseydi (senkron `for`), asıl transkripsiyon işi olay döngüsünü
    bloklardı — tam da SSE bağlantılarının donmaması için server.py'nin
    başka her yerde kaçındığı hata.
    """
    global _whisper_model
    if _whisper_model is None:
        _whisper_model = _whisper("base", device="cpu", compute_type="int8")
    segments, _info = _whisper_model.transcribe(audio_path, language="tr")
    return "".join(segment.text for segment in segments).strip()


@app.post("/api/stt")
async def post_stt(audio: UploadFile = File(...)) -> dict:
    """Ses parçasını Türkçe metne çevirir — TAMAMEN yerel, ağa çıkmaz.

    `faster-whisper` kurulu değilse (`_whisper is None`) `501` döner ve
    başka hiçbir şey yapmaz: bu deponun her katmanda uyguladığı kural —
    ölçülemeyen/üretilemeyen bir şey uydurulmuş bir örnekle GİZLENMİYOR.
    Tarayıcı dönen metni sohbet kutusuna YAZIYOR, GÖNDERMİYOR — yanlış
    duyulmuş bir komutun operatör onayı olmadan ajana ulaşması bu sistemde
    geri alınamaz (gerçek saha araçlarını çağırıyor).
    """
    if _whisper is None:
        raise HTTPException(status_code=501, detail=STT_NOT_INSTALLED)

    suffix = Path(audio.filename or "audio.webm").suffix or ".webm"
    data = await audio.read()
    with tempfile.NamedTemporaryFile(suffix=suffix) as handle:
        handle.write(data)
        handle.flush()
        text = await anyio.to_thread.run_sync(_transcribe, handle.name)
    return {"text": text}


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


def _dump_feed_entry(entry) -> dict:
    """`FeedEntry`'yi tele biçimlendirilmiş hâliyle koyar.

    Tarayıcı karar veren hiçbir şey yapmıyor — ondalık biçim de dahil.
    `entry.confidence` `FeedEntry`'de (Görev 2/`gozcu/ui/feed.py`) HAM
    `float` kalıyor (Python tarafı onu öyle sınıyor, model GENİŞLETİLMEDİ);
    yalnız BURADA, tele çıkarken, `format_confidence` ile Türkçe ondalık
    virgüllü BİTMİŞ dizeye çevriliyor — `_entry_html`'in (kaçırılmış HTML)
    kullandığı AYNI fonksiyon, ikinci bir biçimlendirme kopyası yok.
    """
    data = entry.model_dump()
    if data["confidence"] is not None:
        data["confidence"] = format_confidence(data["confidence"])
    return data


def _snapshot(session: Session) -> dict:
    """Tam durum. Delta yok: yeniden bağlanma bedavaya çözülüyor."""
    pending = session.nobetci.pending_approval()
    return {
        "version": session.version,
        "run_state": session.run_state,
        "feed": [_dump_feed_entry(entry) for entry in build_feed(
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
