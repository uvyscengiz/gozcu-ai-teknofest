"""Uçtan uca boru hattı — bütün ajanların tek bir koşuda birleştiği yer.

Akış: kare çıkar → `Observation` üret → depoya yaz → `DecisionLoop` kur →
videonun kendi saatinde koştur → kapanan her epizodu gömüp riskini biç →
kök neden raporunu yaz → şartnamenin dört anahtarını derle → teslimden hemen
önce bir kez denetle.

Üç değişmez bu dosyada kod oluyor:

**Dört anahtar her koşuda üretilir.** Genişletilmiş yolun tamamı bir `try`
içinde; çöktüğünde `summary` · `events` · `risk` · `actions` yine döner —
ama `detail=None` ile. Dolu bir `detail` "o katmanlar gerçekten koştu"
demektir ve çöken bir koşuda öyle bir şey iddia edilmez.

**Kararlar olay anında verilir.** `DecisionLoop.run()` bir generator: kritik
anda duruyor, operatöre sesleniliyor, sonra videodan devam ediliyor. Kapanış
raporu bu akışın sonucu, yerine geçen şey değil.

**Görü kademesine giden şey klip.** Pencere başına bir mp4 kesiliyor
(`_clip_for`); yorumlayıcı ffmpeg'i hiç görmüyor. Kesme reçetesi canlı
ölçülen biçimin aynısı (`docs/06-references/evren-gateway.md`).
"""

import subprocess
import tempfile
from functools import partial
from pathlib import Path

from gozcu.adapter import to_observation
from gozcu.agents.interpreter import interpret
from gozcu.agents.reporter import generate_root_cause_report
from gozcu.agents.risk import assess_risk
from gozcu.agents.router import route
from gozcu.agents.synthesizer import synthesize
from gozcu.config import FRAME_FPS
from gozcu.frames import extract_frames
from gozcu.gateway import Gateway
from gozcu.guard import screen_delivery
from gozcu.loop import DecisionLoop
from gozcu.memory import embed_episode
from gozcu.models import DialogueTurn, Episode, PipelineOutput
from gozcu.report import build_output
from gozcu.signals import compute_signals
from gozcu.store import Store
from gozcu.track import track_video

__all__ = ["EMPTY_SUMMARY", "LATE_NOTICE", "CallbackFailed", "run_pipeline"]


class CallbackFailed(Exception):
    """Çağıranın geri çağrısı patladı — bozulmuş bir koşu değil.

    Aşağıdaki geniş `except Exception` bozulmuş bir koşuyu geçerli çıktıya
    çeviriyor; bu doğru, ama konsolun bir çizim hatası oraya düşerse koşu
    "başarıyla bozuldu" görünür, ekranda hiçbir şey belirmez ve nedeni hiçbir
    yerde yazmaz. Ayrı bir tip olması, `except CallbackFailed: raise`'in o
    yakalayıcının ÜSTÜNDE durabilmesi için: kesinti yutulmaya devam ediyor,
    çağıranın hatası yutulmuyor.
    """


def _invoke(callback, value) -> None:
    """Geri çağrıyı çağırır; patlarsa `CallbackFailed`'e sarar."""
    if callback is None:
        return
    try:
        callback(value)
    except Exception as error:  # noqa: BLE001 — sarılıp yukarı veriliyor
        raise CallbackFailed(
            f"çağıranın geri çağrısı hata verdi: {error}") from error

#: Hiç epizot üretilmemiş koşunun özeti. Kök neden raporu çağrılmıyor: olay
#: yokken rapor yazmak yaşanmamış bir olayı anlatmak olurdu.
EMPTY_SUMMARY = "Kayda değer olay tespit edilmedi."

#: Kesinti telafisinden gelen epizodun operatöre giden metnine eklenen damga.
#: Geç keşfedilen bir olayı saklamak bir güvenlik sistemi için kabul edilemez,
#: ama onu canlı bir kriz gibi duyurmak da yanıltıcı — o yüzden duyuruluyor,
#: ama damgalanıyor. `Supervisor.escalate` bunu kendisi bilmiyor; farkı
#: `LoopEvent.late` taşıyor ve sarmalayan taraf, yani burası yazıyor.
LATE_NOTICE = "[Telafi — kesinti sırasında atlanmıştı; canlı bir uyarı değil.]"

#: Klip çözünürlüğü. Algı katmanının `FRAME_WIDTH`'i ile ilgisi yok: o kare
#: genişliği, bu görü kademesine giden videonun ölçeği (canlı ölçüldü).
CLIP_SCALE = "scale=1280:-2"


def _clip_for(video_path, out_dir=None):
    """Bir `(start_ts, end_ts)` aralığını kısa bir mp4 klibine kesen kapanış.

    Yorumlayıcı (Görev 04) bunu pencere başına BİR kez çağırıyor ve dönen
    yolu base64 data-URI olarak gateway'e gömüyor; kesilemezse `None`.

    **`None` bir kesinti değil.** Klip yokken yorumlayıcı gateway'i hiç
    çağırmıyor ve `DecisionLoop` o pencereyi ertelemiyor — erteleme yalnızca
    `gw.is_degraded("vlm")` için. Bu yüzden ffmpeg'in kurulu olmaması da,
    okunamayan bir video da, boş çıkan bir kesit de aynı sessiz dala düşüyor.

    `-c:v libx264` H.264 üretiyor: `data:video/mp4;base64,…` yükünün
    çözülebilmesi için gereken şey bu. `-an` ses akışını atıyor — model sesi
    kullanmıyor, taşımak yalnız base64 boyutunu şişirir.

    Klipler tıpkı kareler gibi **geçici artefakt**: varsayılan
    `tempfile.mkdtemp` depo ağacının dışına düşer. Hiçbir klip commit edilmez.
    """
    workdir = Path(out_dir or tempfile.mkdtemp(prefix="gozcu-clips-"))
    workdir.mkdir(parents=True, exist_ok=True)

    def cut(start_ts: float, end_ts: float) -> Path | None:
        # Tek gözlemlik pencerede `start_ts == end_ts`; sıfır süreli bir kesit
        # ffmpeg'den boş dosya döndürür. Taban en az bir kare.
        span = max(end_ts - start_ts, 1.0 / FRAME_FPS)
        out = workdir / f"{start_ts:08.2f}-{end_ts:08.2f}.mp4"
        if out.exists() and out.stat().st_size > 0:
            return out
        try:
            done = subprocess.run(
                ["ffmpeg", "-y", "-ss", f"{start_ts:.2f}", "-t", f"{span:.2f}",
                 "-i", str(video_path), "-vf", CLIP_SCALE,
                 "-c:v", "libx264", "-an", str(out)],
                capture_output=True)
        except OSError:
            return None            # ffmpeg yok — atlanan pencere, kesinti değil
        if done.returncode != 0 or not out.exists() or out.stat().st_size == 0:
            return None
        return out

    return cut


def _on_close(gw, store, episode: Episode) -> None:
    """Kapanan epizodun iki işi: arşive gömülür, sonra riski biçilir.

    `embed_episode` bilerek `try/except` ile sarılmıyor: tasarım gereği
    istisna atmıyor, her arızayı yutup `bool` döndürüyor (Görev 08). Buraya
    konan bir `except` ölü koddur.

    Risk analisti burada çağrılıyor çünkü **kararlar olay anında veriliyor**:
    değerlendirme ve analistin çağırdığı okuma araçları epizodun kendi
    damgasıyla deftere düşüyor (Görev 11), kapanış raporundan sonra değil.
    `actions[]` ve `risk` de buradan doğuyor — analist hiç çağrılmazsa
    şartnamenin iki anahtarı sessizce boşalır.
    """
    embed_episode(gw, store, episode)
    assess_risk(gw, store, episode)


def _announce(store, nobetci, event, on_message) -> str:
    """Yükseltmeyi operatöre duyurur; geç telafiyi damgalar.

    `escalate` bir `Episode` alıyor, `LoopEvent` değil (Görev 14) — geçilen
    şey `event.episode`. Damga diyalog dökümüne de düşüyor: konsol kapalıyken
    bile kök neden raporunun DİYALOG bölümü hangi uyarının telafiden geldiğini
    görebilmeli.
    """
    message = nobetci.escalate(event.episode)
    if event.late:
        message = f"{LATE_NOTICE} {message}"
        store.save_dialogue(DialogueTurn(ts=event.episode.start_ts,
                                         role="system", text=LATE_NOTICE))
    _invoke(on_message, message)
    return message


def _sweep_unassessed(gw, store, fresh: list[Episode]) -> None:
    """Koşu bittiğinde değerlendirmesiz kalan epizotları biçer.

    Kapanmayan bir epizot `on_close`'a hiç uğramaz — video bitene kadar açık
    kalan bir olay tam olarak budur. Değerlendirmesi olmayan epizot
    `actions[]`'a hiçbir şey vermez ve `risk`'i ön riske düşürür.

    Arşivden gelen epizotlar (`load_history`) bilerek dışarıda: onlar bu
    videonun olayı değil, geçmişin kaydı.
    """
    assessed = {assessment.episode_id for assessment in store.risks()}
    for episode in fresh:
        if episode.id not in assessed:
            assess_risk(gw, store, episode)


def _degraded_output(store, summary: str) -> PipelineOutput:
    """Genişletilmiş katman çöktüğünde teslim edilen dört anahtar.

    `detail` bilerek `None`: dolu bir `detail` epizotların, devir defterinin
    ve risk gerekçelerinin gerçekten üretildiği anlamına gelir. Çöken bir
    koşuda o iddia edilemez — kanıt depoda duruyor, ama teslim edilen paket
    kendini ölçülmüş gibi göstermiyor.
    """
    output = build_output(store, summary=summary)
    output.detail = None
    return output


def run_pipeline(video_path, store=None, gw=None, nobetci=None,
                 on_message=None,
                 output_dir=None,
                 on_event=None,
                 on_loop_ready=None) -> tuple[PipelineOutput, Path]:
    """Videoyu baştan sona işler ve şartnamenin dört anahtarını döndürür.

    `store` ve `gw` verilmezse burada kuruluyor: `benchmark/run.py` yalnız
    `store` geçiyor ve `gw=None` bir dereference olurdu.

    `nobetci` verilmezse koşu **headless**: yükseltme anları operatöre
    duyurulmaz ama epizotlar, riskler ve aksiyonlar aynen üretilir — ölçüm
    koşusu (Görev 15) tam olarak böyle koşuyor.

    Algı katmanı bilerek `try`'ın DIŞINDA: okunamayan bir video bozulmuş bir
    koşu değil, hiç koşu değildir. Benchmark o çöküşü klip kaydına yazıyor.

    ## Konsolun üç kanalı

    `on_message(str)` operatöre giden metni taşıyor ve **değişmedi** — var olan
    çağıranlar aynen çalışıyor. Yanına iki tane eklendi:

    - `on_event(LoopEvent)` olayın kendisini veriyor. Metinde `LATE_NOTICE`
      aramak yerine `event.late` ve `event.episode.id` yapısal olarak
      okunabiliyor.
    - `on_loop_ready(DecisionLoop)` canlı döngüyü **bir kez** dışarı veriyor.
      Döngü bu fonksiyonun yereliydi; dışarıdan `catch_up()` çağrılamıyordu ve
      demo beat 6'nın "bağlantı geri geldi, açığı kapat" adımı gösterilemezdi.

    `on_event` **bu iş parçacığında, olayın tam anında** çağrılıyor: bloklarsa
    videonun zaman çizelgesi orada durur. Konsolun "Devam et" düğmesi tam
    olarak buna dayanıyor — duraklama bir numara değil, generator'ın kendisi.
    """
    store = store if store is not None else Store()
    gw = gw if gw is not None else Gateway(store)
    output_dir = Path(output_dir or tempfile.mkdtemp(prefix="gozcu-frames-"))

    frames = extract_frames(video_path, output_dir)
    tracked = track_video([frame.path for frame in frames])
    signals = compute_signals(tracked, [frame.timestamp_s for frame in frames])

    observations = [to_observation(frame.timestamp_s, frame_tracks,
                                   frame_signals)
                    for frame, frame_tracks, frame_signals
                    in zip(frames, tracked, signals, strict=True)]
    for observation in observations:
        store.save_observation(observation)

    # Arşiv tohumlaması koşudan ÖNCE yapılıyor; o epizotlar bu videonun
    # tespiti değil ve ne risk analizine ne de kök neden raporu kararına girer.
    archived = {episode.id for episode in store.episodes()}
    summary = EMPTY_SUMMARY
    root_cause = None
    try:
        loop = DecisionLoop(
            store,
            route=lambda window: route(gw, window,
                                       store.open_episode() is not None),
            # Klip pencere başına bir kez kesiliyor; kapanış döngü kurulurken
            # bir kez üretilir.
            interpret=partial(interpret, gw, store,
                              clip_for=_clip_for(video_path)),
            synthesize=lambda window, interpretation, decision: synthesize(
                gw, store, window, interpretation, decision,
                on_close=lambda episode: _on_close(gw, store, episode)),
            # Çıplak `gw.is_degraded` değil: o "herhangi bir kademe" demek ve
            # `rerank`'ın beklenen 400'ü her pencereyi sonsuza dek erteletir.
            is_degraded=lambda: gw.is_degraded("vlm"))
        _invoke(on_loop_ready, loop)

        for event in loop.run(observations):
            if nobetci is not None:
                _announce(store, nobetci, event, on_message)
            # Duyurudan SONRA: konsol burada bloklayıp operatörü bekliyor ve
            # beklerken ekranda Nöbetçi'nin mesajı çoktan durmalı.
            _invoke(on_event, event)

        fresh = [episode for episode in store.episodes()
                 if episode.id not in archived]
        _sweep_unassessed(gw, store, fresh)
        if fresh:
            root_cause = generate_root_cause_report(gw, store)
            summary = root_cause.what_happened
    except CallbackFailed:
        # Çağıranın hatası kesinti değil; yutulursa konsol sessizce ölür.
        raise
    except Exception:  # noqa: BLE001 — bozulmuş koşu da geçerli çıktı vermeli
        return (screen_delivery(gw, _degraded_output(store, summary)).output,
                output_dir)

    # Teslimden hemen önceki tek denetim çağrısı (Görev 13). Denetim yükü
    # hiçbir koşulda boşaltmıyor; uygunsuz hükmünde bile yalnız bir not
    # ekleniyor ve teslim asla engellenmiyor.
    output = build_output(store, summary=summary, root_cause=root_cause)
    return screen_delivery(gw, output).output, output_dir
