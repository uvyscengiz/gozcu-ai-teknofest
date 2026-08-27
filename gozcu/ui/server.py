"""FastAPI iskeleti — web konsolunun sunucu tarafı (§5, tasarım spec'i).

`console.py`'nin (Gradio) yerini alacak yeni sunucu. Bu görevde yalnız
iskelet ve salt-okunur (`GET`) uçlar var: koşu başlatma, SSE, onay/adım
modu gibi durum DEĞİŞTİREN uçlar sonraki görevlerde geliyor. `console.py`
bu görev boyunca DOKUNULMADAN yaşıyor — Gradio konsolu Görev 11'e kadar
bağımsız çalışıyor.

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
"""

import importlib.util
import subprocess
import time
import typing
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from openai import OpenAI

from gozcu.config import VLM_BASE_URL, VLM_MODEL
from gozcu.memory import memory_backend
from gozcu.models import ActionRecord, RiskLevel, WindowRecord
from gozcu.store import Store
from gozcu.ui import view
from gozcu.ui.session import RUN_STATES, Session

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
