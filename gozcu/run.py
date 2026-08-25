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

from gozcu import trace
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
from gozcu.motion import build_motion_for, raw_scores
from gozcu.report import PerceptionHealth, build_output
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

#: Hiç epizot üretilmemiş **ve algı katmanının gerçekten baktığı** koşunun
#: özeti. Kök neden raporu çağrılmıyor: olay yokken rapor yazmak yaşanmamış
#: bir olayı anlatmak olurdu.
#:
#: Bu cümle bir GÖZLEM iddiasıdır: "baktım, bir şey yoktu". Katman hiç
#: göremediyse aynı cümle bir yalana dönüşür — o dalda `build_output`
#: `PerceptionHealth.blind_summary()`'yi kullanıyor.
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


def _peak_frame_diff(frame_paths) -> float | None:
    """Koşunun HAM kare farkı zirvesi; kanıt yoksa `None`.

    `gozcu.motion.combine()` skorları koşu içinde normalize ediyor ve
    normalize zirve tanım gereği hep 1,0 — körlük ölçüsü olarak kullanılamaz.
    O yüzden okunan şey `raw_scores`'un birinci terimi: gri seviye cinsinden
    ortalama mutlak fark, mutlak ölçekte.

    `None` "hareket yok" değil **"kanıt yok"** demek; `PerceptionHealth`
    ikisini ayırt ediyor.

    Kareler `build_motion_for` için zaten bir kez okunuyor, burada ikinci kez
    okunuyorlar. Ölçüldü: kare başına ~1,9 ms, 77 karelik demo klibinde 150
    ms — tek bir görü çağrısının (3.493 ms) yirmide biri. Triyaj katmanına
    ham skorları dışarı veren bir kapı eklemek onu bu koşunun ihtiyacına göre
    eğerdi; ikinci geçiş daha ucuz bir bedel.
    """
    pairs = [pair for pair in raw_scores(frame_paths) if pair is not None]
    return max((pair[0] for pair in pairs), default=None)


def _frame_size(frames) -> tuple[int, int] | None:
    """İlk karenin (genişlik, yükseklik)'i; okunamıyorsa `None`.

    `None` bir kesinti değil: `compute_signals` boyut yokken içeri kaybolma
    sinyalini üretmiyor, diğer bütün sinyaller aynen üretiliyor.
    """
    if not frames:
        return None
    try:
        import cv2

        image = cv2.imread(str(frames[0].path))
        if image is None:
            return None
        height, width = image.shape[:2]
        return (int(width), int(height))
    except Exception:      # noqa: BLE001 — boyut okunamazsa sinyal susar
        return None


def _on_close_traced(gw, store, episode: Episode) -> None:
    with trace.step("epizot.kapandı", f"id={episode.id} ts={episode.start_ts:.1f}s"):
        _on_close(gw, store, episode)


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


def _degraded_output(store, summary: str, perception) -> PipelineOutput:
    """Genişletilmiş katman çöktüğünde teslim edilen dört anahtar.

    `detail` bilerek `None`: dolu bir `detail` epizotların, devir defterinin
    ve risk gerekçelerinin gerçekten üretildiği anlamına gelir. Çöken bir
    koşuda o iddia edilemez — kanıt depoda duruyor, ama teslim edilen paket
    kendini ölçülmüş gibi göstermiyor.
    """
    output = build_output(store, summary=summary, perception=perception)
    output.detail = None
    return output


def run_pipeline(video_path, store=None, gw=None, nobetci=None,
                 on_message=None,
                 output_dir=None,
                 on_event=None,
                 on_loop_ready=None,
                 motion_for=None) -> tuple[PipelineOutput, Path]:
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

    `motion_for` normalde burada kurulan yerel hareket triyajı; ölçüm ya da
    test sabitlemek isterse geçebiliyor. Parametre **sona** eklendi:
    `benchmark/run.py` konumsal çağırıyor ve araya sokulan bir parametre
    argümanları sessizce kaydırırdı.

    `on_event` **bu iş parçacığında, olayın tam anında** çağrılıyor: bloklarsa
    videonun zaman çizelgesi orada durur. Konsolun "Devam et" düğmesi tam
    olarak buna dayanıyor — duraklama bir numara değil, generator'ın kendisi.
    """
    store = store if store is not None else Store()
    gw = gw if gw is not None else Gateway(store)
    output_dir = Path(output_dir or tempfile.mkdtemp(prefix="gozcu-frames-"))

    frames = extract_frames(video_path, output_dir)
    tracked = track_video([frame.path for frame in frames])
    # Kadraj boyutu bir kez okunuyor: `interior_vanished_tracks` kenarı
    # bilmeden hesaplanamaz ve tahmin edilirse kadrajı terk eden her insan
    # "içeride kayboldu" diye okunur — yani olmayan bir kaza uydurulur.
    signals = compute_signals(tracked, [frame.timestamp_s for frame in frames],
                              frame_size=_frame_size(frames))

    observations = [to_observation(frame.timestamp_s, frame_tracks,
                                   frame_signals)
                    for frame, frame_tracks, frame_signals
                    in zip(frames, tracked, signals, strict=True)]
    with trace.step("depo.gözlem-yaz", f"{len(observations)} gözlem"):
        for observation in observations:
            store.save_observation(observation)

    # Algı katmanının bu koşuda ne kadar görebildiği — teslim katmanına kadar
    # taşınıyor. Sıfır epizotluk bir koşu "sakin" de olabilir "kör" de, ve o
    # ikisi aynı cümleyle anlatılamaz (bkz. `gozcu.report.PerceptionHealth`).
    health = PerceptionHealth(
        detections=sum(len(observation.detections)
                       for observation in observations),
        frames=len(frames),
        peak_motion_energy=_peak_frame_diff([frame.path for frame in frames]))
    trace.event("algı.sağlık",
                f"tespit={health.detections} kare={health.frames} "
                f"zirve-fark={health.peak_motion_energy}")

    # Yerel hareket triyajı (Görev 16). Kareler zaten elde; enerji burada,
    # koşu başına BİR kez hesaplanıyor — model yok, ağ yok, kare başına
    # 0,7 ms. Döngü pahalı görü bütçesini bununla nişanlıyor: taban geçemeyen
    # pencerelerden en yüksek enerjili olanlar bakılıyor, sıradaki değil.
    #
    # `build_motion_for` kullanılabilir kare bulamazsa `None` döndürüyor ve
    # döngü eski periyodik nöbetine düşüyor. Bu çağrı `try`'ın DIŞINDA
    # durabiliyor çünkü triyaj katmanı tasarım gereği istisna atmıyor —
    # atsaydı okunamayan tek bir kare bütün koşuyu bozulmuş sayardı.
    if motion_for is None:
        with trace.step("triyaj.enerji", f"{len(frames)} kare"):
            motion_for = build_motion_for(
                [frame.timestamp_s for frame in frames],
                [frame.path for frame in frames])

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
                on_close=lambda episode: _on_close_traced(gw, store, episode)),
            # Çıplak `gw.is_degraded` değil: o "herhangi bir kademe" demek ve
            # `rerank`'ın beklenen 400'ü her pencereyi sonsuza dek erteletir.
            is_degraded=lambda: gw.is_degraded("vlm"),
            motion_for=motion_for)
        _invoke(on_loop_ready, loop)

        for event in loop.run(observations):
            trace.event("döngü.yükseltme",
                        f"epizot={event.episode.id} ts={event.episode.start_ts:.1f}s "
                        f"geç={event.late}")
            if nobetci is not None:
                with trace.step("nöbetçi.duyur"):
                    _announce(store, nobetci, event, on_message)
            # Duyurudan SONRA: konsol burada bloklayıp operatörü bekliyor ve
            # beklerken ekranda Nöbetçi'nin mesajı çoktan durmalı.
            # Konsol BURADA operatörü bekliyor; "takıldı" görünen sürenin
            # bir kısmı aslında bu — bekleyişin kendisi kayda giriyor.
            with trace.step("konsol.bekle", "operatörün devam etmesi bekleniyor"):
                _invoke(on_event, event)

        fresh = [episode for episode in store.episodes()
                 if episode.id not in archived]
        with trace.step("risk.kalanları-biç", f"{len(fresh)} epizot"):
            _sweep_unassessed(gw, store, fresh)
        if fresh:
            with trace.step("raportör.kök-neden"):
                root_cause = generate_root_cause_report(gw, store)
            summary = root_cause.what_happened
    except CallbackFailed:
        # Çağıranın hatası kesinti değil; yutulursa konsol sessizce ölür.
        raise
    except Exception:  # noqa: BLE001 — bozulmuş koşu da geçerli çıktı vermeli
        return (screen_delivery(
            gw, _degraded_output(store, summary, health)).output, output_dir)

    # Teslimden hemen önceki tek denetim çağrısı (Görev 13). Denetim yükü
    # hiçbir koşulda boşaltmıyor; uygunsuz hükmünde bile yalnız bir not
    # ekleniyor ve teslim asla engellenmiyor.
    output = build_output(store, summary=summary, root_cause=root_cause,
                          perception=health)
    with trace.step("denetim.teslim"):
        screened = screen_delivery(gw, output).output
    trace.event("koşu.bitti", f"epizot={len(fresh)}")
    return screened, output_dir
