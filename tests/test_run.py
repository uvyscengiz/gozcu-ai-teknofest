"""Görev 17 — uçtan uca boru hattı.

Bu dosyanın koruduğu üç cümle:

1. **Bozulmuş bir koşu da notlandırılabilir.** Genişletilmiş katman çökerse
   dört anahtar yine döner — ama `detail=None` ile, çünkü dolu bir `detail`
   o katmanların gerçekten koştuğu anlamına gelir.
2. **Nöbetçisiz (headless) koşuda da `risk` ve `actions[]` doludur.** İkisi de
   risk analistinin çıktısından türüyor; analist hiç çağrılmazsa şartnamenin
   iki anahtarı sessizce boşalır.
3. **Geç telafi edilmiş bir epizot canlı kriz gibi duyurulmaz.** `LoopEvent.late`
   operatöre giden metni değiştirmek zorunda.

Ağ yok: sahte ağ geçidi kademe başına senaryo döndürüyor, ffmpeg de sahte.
"""

import inspect
import json
import subprocess
import tempfile
from pathlib import Path

import pytest

from gozcu import run as run_module
from gozcu.config import FRAME_FPS
from gozcu.frames import Frame
from gozcu.gateway import Response
from gozcu.guard import DELIVERY_FLAG_NOTICE
from gozcu.models import Episode, LoopEvent, PipelineOutput
from gozcu.run import LATE_NOTICE, _clip_for, run_pipeline
from gozcu.signals import FrameSignals
from gozcu.store import Store

# -- senaryolar ---------------------------------------------------------------

VLM_JSON = json.dumps({"description": "İstif aracı sallanıyor ve devriliyor.",
                       "notable_event": "Araç devrildi, sürücü yere düştü."})

SYNTHESIS_JSON = json.dumps({"phase": "onset",
                             "summary_tr": "İstif aracı devrildi.",
                             "participants": ["IST-04"],
                             "preliminary_risk": "Yüksek"})

RISK_JSON = json.dumps({
    "level": "Kritik",
    "rationale_tr": "Yerde hareketsiz kişi olabilir; olası fren arızası.",
    "preventable": True,
    "proposed_actions": [{"description_tr": "Sağlık ekibini çağır",
                          "tool_name": "dispatch_medical",
                          "params": {"location": "B-Hattı",
                                     "urgency": "critical"}}]})

REPORT_JSON = json.dumps({
    "what_happened": "B-Hattında istif aracı devrildi.",
    "probable_root_cause": "Olası fren arızası.",
    "actions_taken": ["Sağlık ekibi çağrıldı."],
    "prevention_recommendations": ["Fren bakımı öne alınmalı."],
    "confidence_limits": "Kamera sesi duymuyor."})


class _FakeGateway:
    """Ağa hiç çıkmayan ağ geçidi ikizi; kademe başına senaryo döndürür.

    `heal_after_checks` kesinti telafisi içindir: görü kademesi ilk
    `is_degraded` sorgusunda bozuk, sonrasında sağlam görünür — `catch_up()`
    tam olarak bu geçişte çalışıyor.
    """

    def __init__(self, router=("escalate",), vlm_broken=False,
                 rerank_broken=False, heal_after_checks=0, guard="uygun"):
        self.router = list(router)
        self.vlm_broken = vlm_broken
        self.rerank_broken = rerank_broken
        self.heal_after_checks = heal_after_checks
        self.guard = guard
        self.asked: list[str] = []
        self.messages: list[list[dict]] = []
        self.degraded_checks: list[str | None] = []

    def _next_router(self) -> str:
        return self.router.pop(0) if len(self.router) > 1 else self.router[0]

    def ask(self, tier, messages, schema=None, tools=None, max_tokens=None,
            temperature=None, _retries=None) -> Response:
        self.asked.append(tier)
        self.messages.append(messages)
        if tier == "router":
            return Response(content=json.dumps(
                {"decision": self._next_router(), "rationale": "sinyal var",
                 "confidence": 0.9}))
        if tier == "vlm":
            if self.vlm_broken:
                return Response(model="vlm", degraded=True)
            return Response(content=VLM_JSON, model="vlm", tokens=8285)
        if tier == "fast":
            return Response(content=SYNTHESIS_JSON)
        if tier == "guard":
            return Response(content=self.guard)
        if tier == "main":
            report = getattr(schema, "__name__", "") == "RootCauseReport"
            return Response(content=REPORT_JSON if report else RISK_JSON)
        return Response(degraded=True)

    def embed(self, text):
        return []

    def is_degraded(self, tier=None) -> bool:
        self.degraded_checks.append(tier)
        if (self.heal_after_checks
                and len(self.degraded_checks) > self.heal_after_checks):
            self.vlm_broken = False
        if tier is None:
            return self.vlm_broken or self.rerank_broken
        return {"vlm": self.vlm_broken,
                "rerank": self.rerank_broken}.get(tier, False)


class _FakeSupervisor:
    """Nöbetçi ikizi; kendisine hangi tipin geçildiğini kaydeder."""

    REPLY = "Operatöre haber verildi."

    def __init__(self):
        self.seen: list = []

    def escalate(self, episode):
        self.seen.append(episode)
        return self.REPLY


def _perception(monkeypatch, tmp_path, count=4, person_count=2):
    """Donuk algı katmanını sahte kare/sinyal üretimiyle değiştirir.

    Gerçek ffmpeg ve YOLO burada koşamaz; adaptörün ve depoya yazmanın
    doğrulanması için gerekli olan tek şey doğru şekilli girdi.
    """
    frames = [Frame(path=tmp_path / f"frame_{i:04d}.jpg", timestamp_s=float(i),
                    index=i) for i in range(count)]
    tracked = [[] for _ in frames]
    signals = [FrameSignals(person_count=person_count,
                            velocities={1: 4.0}) for _ in frames]
    monkeypatch.setattr(run_module, "extract_frames", lambda *a, **k: frames)
    monkeypatch.setattr(run_module, "track_video", lambda *a, **k: tracked)
    monkeypatch.setattr(run_module, "compute_signals", lambda *a, **k: signals)
    return frames


def _fake_clip(monkeypatch, tmp_path):
    """Klip kesiciyi gerçek bir dosyayla değiştirir; ffmpeg çalışmaz."""
    clip = tmp_path / "window.mp4"
    clip.write_bytes(b"\x00fake-mp4")
    monkeypatch.setattr(run_module, "_clip_for", lambda *a, **k:
                        lambda start, end: clip)
    return clip


# -- klip kesici --------------------------------------------------------------

class _FakeRun:
    """`subprocess.run` ikizi: argv'yi kaydeder ve istenirse dosyayı yazar."""

    def __init__(self, returncode=0, write=True, error=None):
        self.returncode, self.write, self.error = returncode, write, error
        self.argv: list[str] = []

    def __call__(self, argv, **kwargs):
        if self.error is not None:
            raise self.error
        self.argv = argv
        if self.write:
            Path(argv[-1]).write_bytes(b"\x00mp4")
        return subprocess.CompletedProcess(argv, self.returncode)


def _cut(monkeypatch, fake, tmp_path, start=10.0, end=20.0):
    monkeypatch.setattr(run_module.subprocess, "run", fake)
    return _clip_for("video.mp4", out_dir=tmp_path)(start, end)


def test_the_clip_recipe_is_the_one_measured_against_the_live_gateway(
        monkeypatch, tmp_path):
    """`-c:v libx264` olmadan gateway `data:video/mp4;base64,…` yükünü
    çözemez; `-an` ses akışını atar, model sesi kullanmıyor."""
    fake = _FakeRun()
    assert _cut(monkeypatch, fake, tmp_path) is not None
    assert fake.argv[:3] == ["ffmpeg", "-y", "-ss"]
    assert "scale=1280:-2" in fake.argv
    assert fake.argv[fake.argv.index("-c:v") + 1] == "libx264"
    assert "-an" in fake.argv


def test_a_single_observation_window_still_asks_for_one_whole_frame(
        monkeypatch, tmp_path):
    """Tek gözlemlik pencerede `start == end`; sıfır süreli kesit ffmpeg'den
    boş dosya döndürür."""
    fake = _FakeRun()
    _cut(monkeypatch, fake, tmp_path, start=7.0, end=7.0)
    assert float(fake.argv[fake.argv.index("-t") + 1]) == pytest.approx(
        1.0 / FRAME_FPS, abs=0.01)


def test_a_failed_cut_is_a_skipped_window_not_an_outage(monkeypatch, tmp_path):
    assert _cut(monkeypatch, _FakeRun(returncode=1), tmp_path) is None


def test_an_empty_clip_file_is_treated_as_no_clip(monkeypatch, tmp_path):
    fake = _FakeRun()
    monkeypatch.setattr(run_module.subprocess, "run", fake)
    cut = _clip_for("video.mp4", out_dir=tmp_path)
    fake.write = False
    assert cut(1.0, 2.0) is None


def test_a_missing_ffmpeg_binary_does_not_bring_the_run_down(monkeypatch,
                                                             tmp_path):
    """`subprocess.run` kurulu olmayan ikili için `FileNotFoundError` atar;
    o istisna yorumlayıcıdan döngüye kaçarsa bütün koşu düşer."""
    fake = _FakeRun(error=FileNotFoundError("ffmpeg"))
    assert _cut(monkeypatch, fake, tmp_path) is None


def test_clips_are_temporary_artefacts_outside_the_repository(monkeypatch):
    """Klipler yeniden üretilebilir ikili dosyalar; depo ağacına yazılmaz."""
    fake = _FakeRun()
    monkeypatch.setattr(run_module.subprocess, "run", fake)
    clip = _clip_for("video.mp4")(1.0, 2.0)
    assert Path(tempfile.gettempdir()) in clip.parents
    assert Path(__file__).resolve().parent.parent not in clip.parents


# -- imza ve bağımlılıklar ----------------------------------------------------

def test_the_benchmark_signature_is_honoured():
    """Görev 15'in ön koşul kontrolü `store` parametresini arıyor."""
    assert "store" in inspect.signature(run_pipeline).parameters


def test_the_pipeline_builds_its_own_store_and_gateway(monkeypatch, tmp_path):
    """`benchmark/run.py` `gw` geçmiyor; varsayılan `None` dereference edilirdi."""
    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)
    built: list = []

    def _gateway(store=None):
        built.append(store)
        return _FakeGateway(router=("ignore",))

    monkeypatch.setattr(run_module, "Gateway", _gateway)
    output, _ = run_pipeline("video.mp4")
    assert isinstance(output, PipelineOutput)
    # Ağ geçidi depoyla kuruldu ve gözlemler o depoya yazıldı.
    assert built and len(built[0].observations()) == 4


def test_every_observation_is_written_to_the_store(monkeypatch, tmp_path):
    """`vlm_trigger_rate`'in paydası bu — başka hiçbir yer gözlem yazmıyor."""
    _perception(monkeypatch, tmp_path, count=6)
    _fake_clip(monkeypatch, tmp_path)
    store = Store(":memory:")
    run_pipeline("video.mp4", store=store, gw=_FakeGateway(router=("ignore",)))
    assert len(store.observations()) == 6


# -- dört anahtar -------------------------------------------------------------

def test_a_headless_run_fills_risk_and_actions(monkeypatch, tmp_path):
    """Nöbetçi yokken risk analisti hiç çağrılmazsa `actions[]` kalıcı olarak
    boş kalır ve `risk` ön riske düşer — dört anahtarın ikisi içi boş."""
    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)
    store = Store(":memory:")
    output, _ = run_pipeline("video.mp4", store=store,
                             gw=_FakeGateway(router=("open_episode",
                                                     "close_episode")))
    assert output.risk == "Kritik"          # ön risk "Yüksek" idi
    assert output.actions == ["Sağlık ekibini çağır"]
    assert store.risks() and store.risks()[0].episode_id == store.episodes()[0].id


def test_a_closed_episode_is_assessed_at_the_moment_it_closes(monkeypatch,
                                                              tmp_path):
    """Kararlar olay anında verilir (CLAUDE.md).

    Üç pencere: olay açılır, kapanır, sonra yeni bir olay açılır. Kapanan
    epizodun riski videonun geri kalanı işlenmeden BİÇİLMİŞ olmalı — koşu
    sonuna toplanan bir analiz, defterin "önce oldu, sonra karar verildi"
    hikâyesini kapanış raporuna erteler.
    """
    _perception(monkeypatch, tmp_path, count=24)
    _fake_clip(monkeypatch, tmp_path)
    store = Store(":memory:")
    run_pipeline("video.mp4", store=store,
                 gw=_FakeGateway(router=("open_episode", "close_episode",
                                         "open_episode")))
    handoffs = store.handoffs()
    first_risk = next(i for i, h in enumerate(handoffs)
                      if h.source_agent == "risk_analyst")
    last_synthesis = max(i for i, h in enumerate(handoffs)
                         if h.source_agent == "synthesizer")
    assert first_risk < last_synthesis
    assert len(store.episodes()) == 2
    # Kapanmayan ikinci epizot da değerlendirmesiz kalmıyor.
    assert {r.episode_id for r in store.risks()} == {e.id for e
                                                     in store.episodes()}


def test_the_summary_comes_from_the_root_cause_report(monkeypatch, tmp_path):
    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)
    output, _ = run_pipeline("video.mp4", store=Store(":memory:"),
                             gw=_FakeGateway(router=("open_episode",)))
    assert output.summary == "B-Hattında istif aracı devrildi."
    assert output.detail.root_cause_report["probable_root_cause"] == (
        "Olası fren arızası.")


def test_a_run_without_a_single_episode_reports_no_incident(monkeypatch,
                                                            tmp_path):
    """Hiçbir olay yokken kök neden raporu üretmek yaşanmamış bir olayı
    anlatmak olurdu."""
    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)
    gw = _FakeGateway(router=("ignore",))
    output, _ = run_pipeline("video.mp4", store=Store(":memory:"), gw=gw)
    assert output.summary == run_module.EMPTY_SUMMARY
    assert output.events == [] and output.actions == []
    assert output.risk == "Düşük"
    assert "main" not in gw.asked


def test_a_crashed_extended_pipeline_still_returns_the_four_keys(monkeypatch,
                                                                tmp_path):
    """Bozulmuş bir koşu da geçerli, notlandırılabilir bir sonuç döndürmeli."""
    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)

    def _explode(*args, **kwargs):
        raise RuntimeError("yönlendirici çöktü")

    monkeypatch.setattr(run_module, "route", _explode)
    output, _ = run_pipeline("video.mp4", store=Store(":memory:"),
                             gw=_FakeGateway())
    assert set(output.model_dump()) >= {"summary", "events", "risk", "actions"}
    assert output.risk == "Düşük"
    # Dolu bir `detail` "genişletilmiş katmanlar koştu" demek; koşmadılar.
    assert output.detail is None


def test_the_delivered_payload_passes_through_the_delivery_screening(
        monkeypatch, tmp_path):
    """Görev 13: `build_output` ile teslim arasında tek bir denetim çağrısı."""
    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)
    gw = _FakeGateway(router=("open_episode",), guard="uygunsuz")
    output, _ = run_pipeline("video.mp4", store=Store(":memory:"), gw=gw)
    assert gw.asked.count("guard") == 1
    assert DELIVERY_FLAG_NOTICE in output.summary
    # Yük boşaltılmıyor: kanıt yerinde kalıyor.
    assert output.events and output.actions


# -- olay anında karar --------------------------------------------------------

def test_the_vision_tier_is_asked_with_a_clip_not_a_frame(monkeypatch,
                                                          tmp_path):
    """Yorumlayıcıya klip kesici bağlanmazsa görü kademesi hiç çağrılmaz."""
    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)
    gw = _FakeGateway(router=("inspect",))
    store = Store(":memory:")
    run_pipeline("video.mp4", store=store, gw=gw)
    assert "vlm" in gw.asked
    parts = gw.messages[gw.asked.index("vlm")][-1]["content"]
    assert any(p.get("type") == "video_url" for p in parts)
    assert store.interpretations()


def test_only_the_vision_tier_can_defer_a_window(monkeypatch, tmp_path):
    """Çıplak `gw.is_degraded` 'herhangi bir kademe' demek; `rerank`'ın
    beklenen 400'ü her pencereyi sonsuza dek erteletirdi."""
    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)
    captured: dict = {}
    real_loop = run_module.DecisionLoop

    def _spy(store, **kwargs):
        captured.update(kwargs)
        return real_loop(store, **kwargs)

    monkeypatch.setattr(run_module, "DecisionLoop", _spy)
    gw = _FakeGateway(router=("ignore",), rerank_broken=True)
    run_pipeline("video.mp4", store=Store(":memory:"), gw=gw)
    assert captured["is_degraded"]() is False


# -- geç telafi ---------------------------------------------------------------

def _late_run(monkeypatch, tmp_path, **kwargs):
    """Görü kademesi ilk pencerede bozuk, telafi turunda sağlam.

    Karar `inspect`: canlı yükseltme hiç doğmuyor, dolayısıyla operatöre
    giden TEK metin telafi turundan geliyor.
    """
    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)
    gw = _FakeGateway(router=("inspect",), vlm_broken=True,
                      heal_after_checks=1)
    nobetci = _FakeSupervisor()
    said: list[str] = []
    run_pipeline("video.mp4", store=Store(":memory:"), gw=gw,
                 nobetci=nobetci, on_message=said.append, **kwargs)
    return nobetci, said


def test_a_live_escalation_is_announced_without_a_catch_up_marker(monkeypatch,
                                                                  tmp_path):
    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)
    nobetci = _FakeSupervisor()
    said: list[str] = []
    run_pipeline("video.mp4", store=Store(":memory:"),
                 gw=_FakeGateway(router=("escalate",)), nobetci=nobetci,
                 on_message=said.append)
    assert said == [_FakeSupervisor.REPLY]


def test_a_backfilled_episode_is_announced_but_not_as_a_live_crisis(
        monkeypatch, tmp_path):
    """Geç keşfedilen bir olayı saklamak kabul edilemez; onu canlı kriz gibi
    duyurmak da yanıltıcı. `LoopEvent.late` bu ikisini ayırır."""
    nobetci, said = _late_run(monkeypatch, tmp_path)
    assert nobetci.seen, "telafi turundan hiç epizot çıkmadı"
    assert len(said) == 1
    assert said[0].startswith(LATE_NOTICE)
    assert _FakeSupervisor.REPLY in said[0]
    # Canlı yükseltmenin metniyle aynı olsaydı ayrım hiç yapılmamış olurdu.
    assert said[0] != _FakeSupervisor.REPLY


def test_the_supervisor_receives_an_episode_not_a_loop_event(monkeypatch,
                                                             tmp_path):
    """Görev 14: `escalate` bir `Episode` alıyor, `LoopEvent` değil."""
    nobetci, _ = _late_run(monkeypatch, tmp_path)
    assert isinstance(nobetci.seen[0], Episode)
    assert not isinstance(nobetci.seen[0], LoopEvent)
