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
import os
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
from gozcu.config import (FRAME_FPS, STT_COMPUTE_TYPE, STT_DEVICE, STT_MODEL,
                          VLM_BASE_URL, VLM_MODEL)
from gozcu.fixtures.loader import load_history
from gozcu.gateway import Gateway
from gozcu.memory import embed_document, memory_backend, video_key
from gozcu import library
from gozcu.motion import frame_entropy
from gozcu.models import ActionRecord, RiskLevel, WindowRecord
from gozcu.run import _announce, run_pipeline
from gozcu.store import Store
from gozcu.ui import series, view
from gozcu.ui.feed import (AGENT_LABELS, AGENT_MARKS, OUTCOME_LABELS,
                          PROACTIVE_MARK,
                          RISK_COLORS, build_feed, format_confidence)
from gozcu.ui.session import (HEARTBEAT_S, LIVE_RUN_STATES, RUN_STATES,
                              Session)

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

#: Yüklenen videonun ÜST SINIRI ve okuma parçası. `await video.read()`
#: (parametresiz) bütün gövdeyi belleğe alıyordu: `baslat()` `0.0.0.0`'a
#: bağlanıyor (aşağıda), yani sunucu salon ağında kimlik doğrulamasız —
#: keyfi büyüklükte bir gövde sunucuyu belleğinden düşürmeye yeterdi.
#: Parça parça okunuyor ve sınır aşılırsa `413` dönüyor.
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024
UPLOAD_TOO_LARGE = (f"Video çok büyük — en fazla "
                    f"{MAX_UPLOAD_BYTES // 1024 ** 3} GiB yüklenebilir.")


def _safe_upload_name(raw: str | None) -> str:
    """Yüklenen dosyanın adını koşu dizinine HAPSEDER.

    `multipart` `filename`'i istemcinin yazdığı ham metin — güvenilmez.
    `../../PWNED.txt` koşu dizininden ÇIKIYORDU (ölçüldü) ve var olmayan
    bir alt dizin adı yakalanmamış bir `FileNotFoundError` ile `500` +
    yığın izi veriyordu. `Path(...).name` yol bileşenlerinin hepsini atıyor.

    `".."` AYRICA eleniyor: `Path("..").name` boş DEĞİL, `".."`'nin kendisi
    — tek başına bırakılsaydı hedef üst dizinin ta kendisi olurdu.
    `NUL` de eleniyor; dosya adına gömülü bir `\x00` `open()`'ı `ValueError`
    ile düşürüp yine `500` verirdi.
    """
    name = Path((raw or "").replace("\x00", "")).name
    return "video.mp4" if name in ("", ".", "..") else name

#: Koşunun videosu diskte yoksa (beklenmeyen bir durum — `video_path`
#: koşu başlarken yazılıyor) `GET .../video`'nun dönmesi gereken mesaj.
NO_VIDEO_YET = "Bu koşu için video bulunamadı."

#: `faster-whisper` kurulu değilken `POST /api/stt`'nin dönmesi gereken
#: mesaj — kural: örnek/uydurulmuş bir transkript YOK, dürüst bir `501`.
STT_NOT_INSTALLED = ("Yerel konuşma tanıma (faster-whisper) kurulu değil. "
                    "Kurulum için: uv sync --extra stt")

#: `faster-whisper` KURULU ama model ağırlıkları önbellekte YOKKEN
#: `POST /api/stt`'nin dönmesi gereken mesaj — `503` (geçici, kurulumla
#: düzelir), `501`'den (hiç kurulu değil) AYRI bir durum. `_load_stt_model`
#: modeli `local_files_only=True` ile açtığı için önbellek boşsa Hugging
#: Face Hub'a SESSİZCE uzanmaz (bkz. modülün başındaki `_whisper` yorumu ve
#: `README.md`, "Bas-konuş" bölümü) — final Bilişim Vadisi'nde fiziki, ağsız
#: bir salon; sessiz bir ağ denemesi jürinin önünde donma/hata demek olurdu.
STT_CACHE_MISSING = (
    "Yerel konuşma modeli (\"{model}\") önbellekte yok. Bu KURULUM "
    "sırasında, demo öncesinde çözülmesi gereken bir adım — bkz. "
    "README.md, \"Bas-konuş\" bölümündeki önbellek doldurma komutu."
).format(model=STT_MODEL)

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
        "live_run_states": list(LIVE_RUN_STATES),
        "run_state_labels": dict(view.RUN_STATE_LABELS),
        "risk_levels": list(typing.get_args(RiskLevel)),
        "risk_colors": dict(RISK_COLORS),
        "agent_marks": dict(AGENT_MARKS),
        # Agents ekranının düğüm başlıkları — İngilizce kimliğin Türkçe
        # karşılığı. JS'te ikinci bir çeviri tablosu YAZILMIYOR.
        "agent_labels": dict(AGENT_LABELS),
        "proactive_mark": PROACTIVE_MARK,
        "badge_labels": dict(view.BADGE_LABELS),
        "window_outcomes": list(typing.get_args(
            WindowRecord.model_fields["outcome"].annotation)),
        "window_outcome_labels": dict(OUTCOME_LABELS),
        "approval_states": list(typing.get_args(
            ActionRecord.model_fields["approval"].annotation)),
        "decision_bucket_labels": dict(view.DECISION_BUCKET_LABELS),
        "kpi_unmeasured": view.KPI_UNMEASURED,
        "root_cause_field_labels": dict(view.ROOT_CAUSE_FIELD_LABELS),
        "root_cause_empty_item": view.ROOT_CAUSE_EMPTY_ITEM,
        "root_cause_pending_message": view.ROOT_CAUSE_PENDING,
        "stt_available": _whisper is not None,
    }


# =============================================================================
# `GET /api/status` — koşudan ÖNCE de cevap veriyor (§5.1)
# =============================================================================

@app.get("/api/status")
def get_status() -> dict:
    """Ağ geçidi, hafıza arka ucu, model — oturum yokken `gateway: null`.

    **`run_id`/`run_state`/`step_mode` yeniden bağlanma İÇİN.** Sayfa canlı
    bir koşunun ortasında yenilenirse (jüri önünde kazara bir Cmd-R yeter)
    tarayıcının elindeki `run_id` sıfırlanıyordu: SSE açılmıyor, her komut
    sessizce geri dönüyor ve "Analizi Başlat" `409` alıyordu — koşan iş
    parçacığı ölene kadar geri dönüş YOKTU ve o iş parçacığı tasarım gereği
    acele ettirilemiyor. Açılışta bu üç alan okunuyor ve koşu HÂLÂ CANLIYSA
    (`LIVE_RUN_STATES`) yükleme akışının yaptığı kablolama aynen yapılıyor.
    Bitmiş bir koşuya geri bağlanmak YANLIŞ olurdu: kaynak seçici gizlenir
    ve operatör bir sonraki videoyu başlatamazdı — canlılık koşulu bu yüzden
    tarayıcıda değil, burada, tek kaynaktan (`session.py`) geliyor.
    """
    return {
        "model": VLM_MODEL,
        "memory": memory_backend(),
        "gateway": (view.badges(_SESSION.gw, _SESSION.store)["gateway"]
                   if _SESSION is not None else None),
        # Bu uç `badges()`'i yalnız `gateway` için çağırıyor, `memory`'yi
        # doğrudan okuyor — arşiv sayısı da bu yüzden ELLE konuyor. `None`
        # "sıfır kayıt" DEĞİL, "henüz tohumlanmadı": rozet sayıyı hiç basmaz.
        "archive": _SESSION.archive_count if _SESSION is not None else None,
        "run_id": _RUN_ID if _SESSION is not None else None,
        "run_state": _SESSION.run_state if _SESSION is not None else None,
        "step_mode": bool(_SESSION.step_mode) if _SESSION is not None else False,
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
        # Cümle koşunun DURUMUNA bağlı: çökmüş bir koşuya "Analiz henüz
        # koşmadı." demek üçüncü bir yalan olurdu (afiş "hata" diyor,
        # karar paneli "sürüyor" diyordu, modal da "koşmadı" diyordu).
        raise HTTPException(
            status_code=404,
            detail=view.payload_absence_message(session.run_state))
    return payload


@app.get("/api/run/{run_id}/root-cause")
def get_root_cause(run_id: str) -> dict:
    """Kök neden raporu — VARSA rapor, YOKSA yokluğunun NEDENİ.

    Üç yokluk üç ayrı şey: koşu hiç olmadı (`no_run`), genişletilmiş katman
    çöktü (`crashed`), koşu tamam ama kayda değer olay yok
    (`no_notable_event`). Görev 2'nin kararı bu ayrımın ÇÖKMEMESİNİ şart
    koşmuştu; `view.root_cause_state`/`ROOT_CAUSE_MESSAGES` o günden beri
    hazır duruyordu ama hiçbir tüketicisi yoktu — panel emekliye ayrılan
    konsolda vardı, yenisinde yoktu.

    Dal mantığı JS'e KOPYALANMIYOR: durum da cümlesi de burada seçiliyor,
    tarayıcı yalnız basıyor.
    """
    session = _run_or_404(run_id)
    state = view.root_cause_state(session.output)
    return {"state": state,
            "message": view.ROOT_CAUSE_MESSAGES[state],
            "report": view.root_cause_payload(session.output)}


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
    from gozcu.agents.orchestrator import mmss

    session = _run_or_404(run_id)
    # DİKKAT — `ts`/`end_ts` BURADA `MM:SS` DİZESİ (`mmss`), `GET
    # .../detections`'ta ise HAM saniye (`float`). İki uç aynı adı farklı
    # birimle taşıyor: bu defter insana okunuyor (`js/trace.js` dizeyi
    # olduğu gibi basıyor), tespitler ise aritmetiğe giriyor. Birini
    # normalleştiren biri diğerini de düzeltmeli — `js/player.js::parseMmss`
    # bugün TAM OLARAK bu farkı telafi ediyor ve sessizce kırılır.
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
    # DİKKAT — `ts` BURADA HAM saniye (`float`), `GET .../windows`'ta ise
    # `MM:SS` DİZESİ. Kutu çizimi videonun `currentTime`'ıyla doğrudan
    # karşılaştırılıyor, biçimlenmiş bir dize burada aritmetiği bozardı.
    # Bkz. `get_windows`'taki eş uyarı ve `js/player.js::parseMmss`.
    items = [{"ts": observation.ts, "box": list(detection.box),
             "label": detection.label, "confidence": detection.confidence,
             "track_id": detection.track_id}
            for observation in session.store.observations()
            if from_ <= observation.ts <= to
            for detection in observation.detections]
    return {"frame_size": [width, height], "items": items}


@app.get("/api/run/{run_id}/entropy")
def get_entropy(run_id: str) -> dict:
    """Konsolun piksel entropisi grafiği — kare başına Shannon entropisi.

    `frame_size` gibi koşu boyunca değişmiyor, bu yüzden AYNI önbellek deseni
    (`session.entropy_series`, `_frame_size_for`'daki `session.frame_size`
    ile birebir): ilk istek diskten kareleri okuyup hesaplıyor, sonrakiler
    önbellekten dönüyor.

    Zaman damgası `extract_frames`'in ürettiği AYNI `i / fps` formülüyle
    (`gozcu/frames.py`) — kareler `frame_0000.jpg` sırasıyla o formülle
    numaralandığı için burada ikinci bir kaynaktan okunmuyor, yeniden
    üretiliyor.

    `threshold`, sabit bir sayı UYDURMAK yerine bu koşunun kendi entropi
    dağılımından (ortalama + 1,5×standart sapma) hesaplanıyor — "belirgin
    sapma" tanımı koşudan koşuya değişebilir, sabit bir eşik farklı
    videolarda farklı yanlışlıkta olurdu. Hiç ölçülebilir kare yoksa `None`.
    """
    session = _run_or_404(run_id)
    if session.entropy_series is None:
        frames = sorted(Path(session.output_dir).glob("frame_*.jpg"))
        scores = frame_entropy([str(path) for path in frames])
        session.entropy_series = [
            {"ts": index / FRAME_FPS, "value": value}
            for index, value in enumerate(scores) if value is not None]

    items = session.entropy_series
    values = [item["value"] for item in items]
    threshold = None
    if values:
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        threshold = mean + 1.5 * (variance ** 0.5)
    return {"items": items, "threshold": threshold}


# =============================================================================
# Video altındaki iki canlı grafik (Görev raporu §1)
# =============================================================================

def _energy_series_for(session: Session) -> dict:
    """Koşunun kare kare piksel entropisi; triyaj koşmadıysa BOŞ.

    Seri `gozcu.motion.build_motion_for`'un döngüye taktığı kapanışın
    üstünde geliyor (`loop.motion_for.scores`). Burada yeniden
    hesaplanamazdı: normalizasyon koşuya göreli, yani ikinci bir geçiş
    döngünün nişan aldığından BAŞKA bir ölçek üretir ve grafik sistemin
    gerçekte gördüğü şeyi göstermezdi.

    Triyaj kullanılabilir kare bulamamışsa `motion_for` `None` ve döngü
    periyodik nöbetine düşmüş demektir. O koşuda entropi ÖLÇÜLMEDİ; düz bir
    sıfır çizgisi "hiç hareket yoktu" diye yalan söylerdi, boş seri
    grafiği hiç çizdirmiyor.
    """
    with session.loop_lock:
        loop = session.loop
    motion_for = getattr(loop, "motion_for", None)
    timestamps = getattr(motion_for, "timestamps", None)
    scores = getattr(motion_for, "scores", None)
    if timestamps is None or scores is None:
        return series.energy_series([], [])
    return series.energy_series(timestamps, scores)


@app.get("/api/run/{run_id}/series")
def get_series(run_id: str) -> dict:
    """İki grafiğin verisi TEK çağrıda: varlık sayısı + piksel entropisi.

    İkiye bölünseydi tarayıcı aynı koşunun iki yarısını iki ayrı anda
    çeker ve zaman eksenleri kayabilirdi.

    Koşunun bitmesi **beklenmiyor**: algı da triyaj da karar döngüsünden
    ÖNCE bitiyor (`run_pipeline`), yani iki seri de ilk saniyeden itibaren
    hazır. Koşu sonunu beklemek grafikleri demonun tam ortasında boş
    bırakırdı.
    """
    session = _run_or_404(run_id)
    return {"entities": series.entity_series(session.store.observations()),
            "energy": _energy_series_for(session),
            # Risk izi de BURADA: durum çubuğu (Görev raporu §2) grafiklerle
            # aynı video saatini okuyor. Ayrı bir uç olsaydı tarayıcı aynı
            # koşunun üç parçasını üç ayrı anda çeker, eksenleri kayabilirdi.
            "risk": series.risk_track(session.store.risks(),
                                      session.archived)}


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


def _load_stt_model():
    """`_whisper_model`'i BİR KEZ doldurur — `local_files_only=True` İLE.

    **Bu deponun "TAMAMEN yerel" iddiası bir ÖN KOŞULA bağlı**: model
    ağırlıkları önbellekte olmalı. `local_files_only=True` OLMASAYDI,
    önbellek boşken `WhisperModel(...)` Hugging Face Hub'a SESSİZCE
    uzanırdı — final Bilişim Vadisi'nde fiziki, ağsız bir salon, yani
    jürinin önünde ilk mikrofon basışı donar ya da zaman aşımıyla
    başarısız olurdu. Bu bayrakla önbellek boşsa bunun yerine BURADA,
    açıkça, `STT_CACHE_MISSING` ile patlıyor — çağıran (`_transcribe`)
    bunu yakalayıp `503`'e çeviriyor. Önbelleği doldurmak `README.md`'nin
    "Bas-konuş" bölümündeki kurulum adımı, demo anının değil.
    """
    global _whisper_model
    if _whisper_model is None:
        try:
            _whisper_model = _whisper(
                STT_MODEL, device=STT_DEVICE, compute_type=STT_COMPUTE_TYPE,
                local_files_only=True)
        except Exception as error:  # noqa: BLE001 — önbellek yok/bozuk
            raise RuntimeError(STT_CACHE_MISSING) from error
    return _whisper_model


def _transcribe(audio_path: str) -> str:
    """Modeli (bir kez) kurar ve dosyayı Türkçe metne çevirir.

    `WhisperModel.transcribe` bir GENERATOR döndürüyor — asıl iş segment
    üzerinde YİNELERKEN oluyor. İkisi de burada, TEK bir iş parçacığı
    çağrısının içinde: `segments` üreteci olay döngüsüne sızıp orada
    tüketilseydi (senkron `for`), asıl transkripsiyon işi olay döngüsünü
    bloklardı — tam da SSE bağlantılarının donmaması için server.py'nin
    başka her yerde kaçındığı hata.
    """
    model = _load_stt_model()
    segments, _info = model.transcribe(audio_path, language="tr")
    return "".join(segment.text for segment in segments).strip()


@app.post("/api/stt")
async def post_stt(audio: UploadFile = File(...)) -> dict:
    """Ses parçasını Türkçe metne çevirir.

    **Yerellik bir ÖN KOŞULA bağlı — koşulsuz bir "ağa çıkmaz" iddiası
    DEĞİL.** İki başarısızlık ayrı ve ayrı durum kodları taşıyor:

    - `faster-whisper` hiç kurulu DEĞİLSE (`_whisper is None`) → `501`,
      `STT_NOT_INSTALLED`. Bu deponun her katmanda uyguladığı kural burada
      da geçerli: ölçülemeyen/üretilemeyen bir şey uydurulmuş bir örnekle
      GİZLENMİYOR.
    - `faster-whisper` KURULU ama model ağırlıkları önbellekte YOKSA
      (`_load_stt_model`'ın `local_files_only=True` çağrısı bunu
      yakalıyor) → `503`, `STT_CACHE_MISSING`. Bu durumda gerçek ağ
      çağrısı hiç YAPILMIYOR — önbellek boşken varsayılan davranış
      (Hub'dan sessizce indirmeye çalışmak) final gibi ağsız bir salonda
      donma/hata demek olurdu; bunun yerine kurulum adımına açıkça
      yönlendiriyor (`README.md`, "Bas-konuş").

    Önbellek doluyken (kurulum tamamlanmışken) çağrı gerçekten tamamen
    yerel — ikinci bir ağ isteği hiç kurulmuyor.

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
        try:
            text = await anyio.to_thread.run_sync(_transcribe, handle.name)
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
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


def _on_progress(session: Session):
    """Her kare algılandığında SSE'yi bump eder — grafikler artımlı dolsun."""
    def handler(progress) -> None:
        done, total = progress
        session.perception_total = total
        session.perception_done = done
        with session.cond:
            session.bump()
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
        # `note_intervention` yalnız İLK olayda bump ediyor (durum geçişi):
        # `_set_state_locked` zaten `"intervened"` ise erken dönüyor ve
        # `bump()` çağrılmıyor — sonraki olaylar SSE'ye hiç ulaşmıyordu.
        with session.cond:
            session.bump()
    return handler


def _archive_report(session: Session) -> None:
    """Biten koşunun raporunu kütüphaneye yazar — Hafıza ekranının verisi.

    **`finish()`'ten SONRA çağrılıyor ve bu sıra önemli:** terk edilmiş
    koşunun çıktısını `finish()` atıyor (`session.output = None`, spec §4),
    çöken koşuda ise `output` hiç yazılmıyor. İkisi de burada `None` olarak
    görünüyor ve rapor yazılmıyor — tek bir kontrol iki durumu birden
    kapatıyor, çünkü ikisinin de ortak cevabı aynı: teslim edilmiş bir çıktı
    yok. Reddedilen bir analizi "geçmiş rapor" diye geri göstermek
    operatörün kararını sessizce iptal etmek olurdu.

    **İstisna yutuluyor.** Rapor bir YAN defter; dolu disk ya da izin hatası
    yüzünden koşunun kendisi düşmemeli. `_work` bunu `finish()`'ten sonra
    çağırdığı için buradan kaçan bir istisna koşuyu ekranda sonsuza dek
    "sürüyor" bırakmazdı ama arka plan iş parçacığını sessizce öldürürdü.
    """
    if session.output is None:
        return
    try:
        library.save_report(
            _RUN_ID or "?", session.output.model_dump(),
            source_name=(Path(session.video_path).name
                         if session.video_path else None))
    except Exception:  # noqa: BLE001 — yan defter bir koşuyu düşürmez
        pass


def _work(session: Session, video_path) -> None:
    """Boru hattını ayrı iş parçacığında sürer; bitişi/hatayı `Session`'a yazar."""
    try:
        session.output, _ = run_pipeline(
            video_path, store=session.store, gw=session.gw,
            nobetci=session.nobetci, output_dir=session.output_dir,
            on_event=_on_event(session), on_loop_ready=_on_loop_ready(session),
            on_progress=_on_progress(session))
    except Exception as error:      # noqa: BLE001 — ekranda görünmeli
        session.finish(error)
    else:
        session.finish()            # Terk edilmişse `done` YAZMIYOR.
    _archive_report(session)


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
        session.video_path = video_path
        session.step_mode = bool(step_mode)
        # Boru hattı BAŞLAMADAN önce: analistin ilk precedent_line araması
        # arşivi dolu bulmalı. Sınırlı `join` — bkz. `_seed_archive`.
        _seed_archive(session)
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
        "badges": view.badges(session.gw, session.store,
                              archive=session.archive_count),
        "perception_progress": {
            "done": session.perception_done,
            "total": session.perception_total,
        },
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
# Kütüphane — Hafıza ekranının iki sütunu (`gozcu/library.py`)
# =============================================================================
#
# Bu uçların HİÇBİRİ `_run_or_404`'ten geçmiyor ve geçmemeli: kütüphane
# koşudan bağımsız yaşıyor, zaten var olma sebebi bu. Koşuya bağlanmış
# olsalardı ekran ancak bir video analiz edilirken açılabilirdi.

#: Yüklenen belgenin üst sınırı. Videonun 2 GiB'ından AYRI ve çok daha
#: küçük: burası talimat/prosedür metni alıyor, medya değil. Sunucu salon
#: ağında kimlik doğrulamasız (`baslat()` `0.0.0.0`'a bağlanıyor) — sınırsız
#: bir metin yüklemesi diski doldurmaya yeterdi.
MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
DOCUMENT_TOO_LARGE = (f"Belge çok büyük — en fazla "
                      f"{MAX_DOCUMENT_BYTES // 1024 ** 2} MiB yüklenebilir.")

#: Boş dosya reddediliyor: listede 0 baytlık bir satır, yüklenmiş bir belge
#: gibi görünür ve ajan onu emsal olarak hiç bulamazken orada durur.
DOCUMENT_EMPTY = "Boş dosya yüklenemez."

DOCUMENT_NOT_FOUND = "Belge bulunamadı."
REPORT_NOT_FOUND = "Rapor bulunamadı."


@app.get("/api/library/documents")
def get_library_documents() -> list:
    """Operatörün yüklediği referans belgeleri — en yenisi önce."""
    return [doc.model_dump() for doc in library.list_documents()]


@app.post("/api/library/documents")
async def post_library_document(file: UploadFile = File(...)) -> dict:
    """Belgeyi kütüphaneye alır ve epizodik hafızaya gömmeyi DENER.

    Gömme ayrı bir adım ve ayrı bir başarısızlık: vektör yazılamasa da belge
    saklanıyor, yalnız satırın `embedded` damgası `false` kalıyor. "Gömüldü"
    diye göstermek, ajan onu hiç bulamazken bulacağını sanmak olurdu.
    """
    data = await file.read(MAX_DOCUMENT_BYTES + 1)
    if len(data) > MAX_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail=DOCUMENT_TOO_LARGE)
    if not data:
        raise HTTPException(status_code=400, detail=DOCUMENT_EMPTY)

    record = library.save_document(file.filename, data)
    embedded = embed_document(_embed_gateway(), record, data)
    updated = library.mark_embedded(record.id, embedded)
    return (updated or record).model_dump()


def _embed_gateway():
    """Gömme için bir ağ geçidi; kurulamıyorsa `None`.

    Koşu YOKKEN de gömülebilmeli: belge yükleme koşudan bağımsız bir iş ve
    operatör talimatları tipik olarak analiz BAŞLAMADAN önce yüklüyor. Canlı
    koşunun gateway'i varsa o kullanılıyor — kesinti enjeksiyonu
    (`/gateway/cut`) o nesnede yaşıyor ve ikinci bir istemci onu görmezdi.

    **Kurulum İSTİSNA ATABİLİR ve bu ölçüldü.** `.env.example`
    `GOZCU_GATEWAY_API_KEY=`'i BOŞ bırakıyor; boş dize `config.py`'nin
    `"not-needed"` varsayılanını EZİYOR ve `OpenAI(...)` yapıcısı
    `OpenAIError: Missing credentials` fırlatıyor. Yakalanmadığında sonuç
    şuydu: anahtarsız bir kurulumda belge yüklemek `500` veriyordu — oysa
    yükleme gömmeden bağımsız çalışabilmeli ve çalışıyor.
    """
    if _SESSION is not None:
        return _SESSION.gw
    try:
        return Gateway()
    except Exception:  # noqa: BLE001 — anahtarsız kurulum gömmesiz çalışır
        return None


@app.get("/api/library/documents/{doc_id}")
def get_library_document(doc_id: str) -> Response:
    """Belgenin içeriği.

    UTF-8 olarak çözülebiliyorsa `text/plain` dönüyor — ekran onu okunur
    biçimde gösterebilsin diye. Çözülemeyen dosya `octet-stream`: bir ikili
    dosyayı metin diye etiketlemek tarayıcıda çöp gösterir.
    """
    data = library.read_document(doc_id)
    if data is None:
        raise HTTPException(status_code=404, detail=DOCUMENT_NOT_FOUND)
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return Response(content=data, media_type="application/octet-stream")
    return Response(content=data, media_type="text/plain; charset=utf-8")


@app.delete("/api/library/documents/{doc_id}")
def delete_library_document(doc_id: str) -> dict:
    """Belgeyi siler. Zaten yoksa `404` — silme yalan söylemiyor.

    **Qdrant'taki vektör BURADA silinmiyor** ve bu bilerek: gömme yalnız
    anahtar tanımlıyken gerçekten uzak koleksiyona yazıyor, anahtarsızken
    süreç içi bir indekse düşüyor (`memory.build_client`). Sessizce
    "silindi" demek yerine eksik olan tarafı açıkça bırakıyoruz — belgenin
    vektörü bir sonraki koleksiyon temizliğine kadar kalır.
    """
    if not library.delete_document(doc_id):
        raise HTTPException(status_code=404, detail=DOCUMENT_NOT_FOUND)
    return {"deleted": True}


@app.get("/api/library/reports")
def get_library_reports() -> list:
    """Geçmiş koşuların raporları — GÖVDESİZ, en yenisi önce."""
    return [report.model_dump() for report in library.list_reports()]


@app.get("/api/library/reports/{report_id}")
def get_library_report(report_id: str) -> dict:
    """Raporun tam gövdesi — şartnamenin dört anahtarı `payload` altında."""
    body = library.read_report(report_id)
    if body is None:
        raise HTTPException(status_code=404, detail=REPORT_NOT_FOUND)
    return body


@app.delete("/api/library/reports/{report_id}")
def delete_library_report(report_id: str) -> dict:
    """Raporu siler. Zaten yoksa `404` — silme yalan söylemiyor.

    Rapor belgeden DAHA değerli: operatör yüklediği belgenin aslını
    elinde tutuyor, ama bir koşu raporunun tek kopyası bu ve yeniden
    üretmek videoyu baştan analiz etmeyi gerektiriyor. Teyit bu yüzden
    ekranda iki adımlı (`js/memory.js`).
    """
    if not library.delete_report(report_id):
        raise HTTPException(status_code=404, detail=REPORT_NOT_FOUND)
    return {"deleted": True}


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
    kaldırılır. Demo yolu bunu kullanmıyor — emekliye ayrılan Gradio
    konsolunun `baslat`ında da kural AYNIYDI.
    """
    import uvicorn

    if yerel_vlm:
        _ensure_server_running()
    launch.setdefault("host", "0.0.0.0")
    #: `PORT` ikinci bir kopyayı (inceleme, yan yana karşılaştırma) 7860'ı
    #: işgal etmeden açmaya yarıyor; ayarlanmamışsa demo portu değişmiyor.
    launch.setdefault("port", int(os.environ.get("PORT") or 7860))
    uvicorn.run(app, **launch)
