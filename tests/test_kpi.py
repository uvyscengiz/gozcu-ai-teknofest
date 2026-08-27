"""Görev 15 — KPI takımı.

Bu dosya ölçümü ölçüyor. Buradaki yanlış bir sayı çökme değil, **sonuç gibi
görünen bir yalan** olurdu; testler bu yüzden üç şeyi kilitliyor:

**Bozulmuş koşu manşetten ayrılır.** Yönlendirici kesintide `confidence=0.0`
ile `ignore`'a düşüyor ve `TARGET.get(..., "perception")` de aynı kovaya
oturuyor — yani tamamen çökmüş bir koşu "kararların %100'ü en ucuz kademede
kapandı" diye okunabilirdi. `degraded` payı ayrı bir kova ve koşunun bir
durumu var.

**Boş koşu için tek sözleşme var: `None`.** Ölçülemeyen KPI JSON'da `null`
oluyor; `0.0` "ölçtük, sıfır çıktı" demek ve ikisi karıştırılamaz.

**Türkçe ölçümü alt dizeye bakmaz.** `risk` içinde `is`, `ise` içinde `is`
geçiyor; kelime sınırı olmadan her Türkçe metin İngilizce sanılırdı.
"""

import json
from unittest.mock import Mock, patch

import pytest

from benchmark.kpi import (DEGRADED, EPOCH_THRESHOLD_S, MEASURED, UNMEASURED,
                           aggregate, collect, correction_propagation,
                           decision_distribution, epoch_scale_episodes,
                           run_status, timestamp_drift, turkish_output_rate,
                           vision_tokens, vlm_trigger_rate)
from gozcu.agents.supervisor import (AUDIT_PREFIX, CORRECT_OBSERVATION,
                                     DEGRADED_REPLY, Supervisor)
from gozcu.config import MODELS
from gozcu.fixtures.loader import load_history
from gozcu.gateway import Response
from gozcu.guard import CLEAN_NOTE, Screening
from gozcu.loop import DecisionLoop
from gozcu.models import (DialogueTurn, Episode, Handoff, Interpretation,
                          Observation, RiskAssessment, RouterDecision,
                          Signals)
from gozcu.store import Store

VLM_MODEL = MODELS["vlm"]


def _store(handoffs=(), observation=0, interpretation=0):
    """`handoffs`: (source, target, confidence) üçlüleri."""
    store = Store(":memory:")
    for source, target, confidence in handoffs:
        store.save_handoff(Handoff(ts=0.0, source_agent=source,
                                   target_agent=target, reason="n",
                                   confidence=confidence, payload_ref="r"))
    for i in range(observation):
        store.save_observation(Observation(ts=float(i)))
    for i in range(interpretation):
        store.save_interpretation(Interpretation(
            observation_ts=float(i), description="x", model=VLM_MODEL,
            tokens=100, latency_ms=500, severity="olay"))
    return store


def _episode(store, summary="istif aracı devrildi", start_ts=0.0,
             risk="Orta"):
    episode = Episode(start_ts=start_ts, phase="outcome", summary_tr=summary,
                      preliminary_risk=risk)
    episode.id = store.create_episode(episode)
    return episode


# --- karar dağılımı --------------------------------------------------------

def test_decision_distribution_sums_to_one():
    store = _store([("orchestrator", "perception", 0.8), ("orchestrator", "perception", 0.7),
                    ("orchestrator", "interpreter", 0.6),
                    ("orchestrator", "supervisor", 0.9)])
    distribution = decision_distribution(store)
    assert abs(sum(distribution.values()) - 1.0) < 1e-9
    assert distribution["closed_at_router"] == 0.5


def test_distribution_ignores_handoffs_written_by_other_agents():
    """Sentezleyici ve risk analisti de devir yazıyor; onları saymak manşet
    sayıyı sulandırır."""
    store = _store([("orchestrator", "perception", 0.8),
                    ("anomaly_analyst", "risk_analyst", 0.5),
                    ("risk_analyst", "supervisor", 0.5)])
    assert decision_distribution(store)["closed_at_router"] == 1.0


def test_a_fully_degraded_run_is_not_reported_as_perfect_filtering():
    """Kesintide yönlendirici `ignore`/`confidence=0.0`'a düşüyor ve hedef
    `perception` oluyor. Bu koşu 'her karar en ucuz kademede kapandı' diye
    okunursa, tamamen çökmüş bir sistem en gurur verici grafiği üretir."""
    store = _store([("orchestrator", "perception", 0.0),
                    ("orchestrator", "perception", 0.0)])
    distribution = decision_distribution(store)
    assert distribution["degraded"] == 1.0
    assert distribution["closed_at_router"] == 0.0
    assert run_status(store) == DEGRADED


def test_a_healthy_run_is_reported_as_measured():
    store = _store([("orchestrator", "perception", 0.8),
                    ("orchestrator", "interpreter", 0.7)])
    assert run_status(store) == MEASURED
    assert decision_distribution(store)["degraded"] == 0.0


def test_catch_up_handoffs_do_not_inflate_the_synthesizer_share():
    """`DecisionLoop._handoff` telafi devrini de `source_agent="orchestrator"` diye
    yazıyor. Gerçek döngü üzerinden koşuluyor: kaynağı taklit eden bir test
    bu sızıntıyı göremezdi."""
    store = Store(":memory:")
    degraded = {"on": True}
    observations = [Observation(ts=float(i), signals=Signals(person_count=1))
                    for i in range(3)]
    loop = DecisionLoop(
        store,
        route=lambda window: RouterDecision(decision="inspect",
                                            rationale="bakılsın",
                                            confidence=0.8),
        interpret=lambda window: None,
        synthesize=lambda window, interpretation, decision: None,
        is_degraded=lambda: degraded["on"])
    list(loop.run(observations))
    degraded["on"] = False
    list(loop.catch_up())

    assert [h.reason for h in store.handoffs()].count("telafi") == 1
    distribution = decision_distribution(store)
    assert distribution["to_interpreter"] == 1.0
    assert distribution["to_synthesizer"] == 0.0


def test_distribution_is_not_measured_on_an_empty_run():
    assert decision_distribution(_store()) is None
    assert run_status(_store()) == UNMEASURED


# --- görü tetikleme --------------------------------------------------------

def test_vlm_trigger_rate_is_interpretations_over_observations():
    assert vlm_trigger_rate(_store(observation=100, interpretation=3)) == 0.03


def test_trigger_rate_is_not_measured_on_an_empty_run():
    assert vlm_trigger_rate(_store()) is None


# --- token muhasebesi ------------------------------------------------------

def test_vision_tokens_are_grouped_by_the_recorded_model_id():
    """Anahtar `Interpretation.model`'in gerçekten taşıdığı şey — kademe
    takma adı değil, gateway'in döndürdüğü model kimliği."""
    assert vision_tokens(_store(observation=10,
                                interpretation=2))[VLM_MODEL] == 200.0


def test_vision_tokens_are_not_measured_when_nothing_was_interpreted():
    assert vision_tokens(_store(observation=10)) is None


# --- düzeltme yayılımı -----------------------------------------------------

def _corrected_store(episode_id: int) -> Store:
    """Gerçek süpervizörü bir `correct_observation` çağrısıyla koşturur.

    Elle kurulmuş bir depo bu KPI'ı hiç ölçmezdi: ölçülen şey tam olarak
    `Supervisor._apply_correction`'ın düzeltmeyi nereye yaydığı.
    """
    gateway = Mock()
    stream = iter([
        Response(tool_calls=[{"id": "c1", "type": "function", "function": {
            "name": CORRECT_OBSERVATION,
            "arguments": json.dumps({"episode_id": episode_id,
                                     "field": "event_type",
                                     "old": "araç devrildi",
                                     "new": "yük düştü",
                                     "rationale": "operatör gözlemi"})}}]),
        Response(content="Anlaşıldı, kaydı güncelledim."),
    ])
    gateway.ask.side_effect = lambda *args, **kwargs: next(stream)

    store = Store(":memory:")
    episode = _episode(store, "araç devrildi")
    risk = RiskAssessment(episode_id=episode.id, level="Orta",
                          rationale_tr="gerekçe", preventable=True)
    with patch("gozcu.agents.supervisor.assess_risk", return_value=risk), \
         patch("gozcu.agents.supervisor.screen_text",
               side_effect=lambda gw, text, critical=False:
               Screening(text, "safe", CLEAN_NOTE)):
        Supervisor(gateway, store).talk("araç devrilmedi, yük düştü")
    return store


def test_correction_propagation_is_one_when_the_supervisor_lands_it():
    assert correction_propagation(_corrected_store(episode_id=1)) == 1.0


def test_correction_propagation_is_zero_when_the_episode_does_not_exist():
    """Model var olmayan bir epizot kimliği uydurduğunda düzeltme deftere
    düşüyor ama hiçbir yere yayılmıyor — ölçüm bunu görmeli."""
    assert correction_propagation(_corrected_store(episode_id=999)) == 0.0


def test_correction_propagation_is_not_applicable_without_corrections():
    """Hiç düzeltme yoksa 1.0 okumak, operatörle hiç konuşmamış bir koşuya
    tam not vermek olurdu."""
    store = Store(":memory:")
    _episode(store)
    assert correction_propagation(store) is None


# --- Türkçe oranı ----------------------------------------------------------

def test_turkish_output_rate_is_one_for_clean_turkish():
    store = Store(":memory:")
    _episode(store, "İstif aracı devrildi, yerde hareketsiz kişi var.")
    assert turkish_output_rate(store) == 1.0


def test_turkish_output_rate_flags_english_leakage():
    store = Store(":memory:")
    _episode(store, "The forklift tipped over and a person is down.")
    assert turkish_output_rate(store) == 0.0


def test_turkish_words_that_embed_english_stopwords_are_not_flagged():
    """`risk` içinde `is`, `ise` içinde `is`, `iş` içinde `is` yok ama alt
    dize araması üçünü de yakalardı. `"İ".lower()` de iki kod noktası üretir."""
    store = Store(":memory:")
    _episode(store, "İSG riski yüksek; hasarlı istif aracı iş "
                   "durdurulmadan çekilsin.")
    _episode(store, "İŞ GÜVENLİĞİ İHLALİ TESPİT EDİLDİ")
    assert turkish_output_rate(store) == 1.0


def test_turkish_words_colliding_with_english_stopwords_are_not_flagged():
    """`not`, `at`, `on`, `in` gerçek Türkçe kelimeler — stop-word listesinde
    olmamaları bilinçli bir seçim ve test bunu kilitliyor."""
    store = Store(":memory:")
    _episode(store, "Not: on numaralı at arabası hattın içinde bekliyor.")
    assert turkish_output_rate(store) == 1.0


def test_system_rows_are_not_counted_as_model_output():
    """`[denetim]` hükümleri ve elle yazılmış arıza metinleri model üretimi
    değil; paydaya girerlerse oran şişer ya da sulanır."""
    store = Store(":memory:")
    store.save_dialogue(DialogueTurn(ts=0.0, role="supervisor",
                                     text="Hat durduruldu, ekip yolda."))
    store.save_dialogue(DialogueTurn(
        ts=0.0, role="system",
        text=f"{AUDIT_PREFIX} the verdict is unsafe and the text was blocked"))
    store.save_dialogue(DialogueTurn(ts=0.0, role="system",
                                     text=DEGRADED_REPLY))
    store.save_dialogue(DialogueTurn(ts=0.0, role="operator",
                                     text="what happened over there"))
    assert turkish_output_rate(store) == 1.0


def test_turkish_rate_covers_summaries_dialogue_and_risk_rationales():
    store = Store(":memory:")
    episode = _episode(store, "Yük düştü, kimse yaralanmadı.")
    store.save_dialogue(DialogueTurn(ts=0.0, role="supervisor",
                                     text="Yük düştü, ekip bölgede."))
    store.save_risk(RiskAssessment(
        episode_id=episode.id, level="Orta",
        rationale_tr="The load fell because the mast was overloaded.",
        preventable=True))
    assert turkish_output_rate(store) == pytest.approx(2 / 3)


def test_turkish_rate_is_not_measured_without_generated_text():
    assert turkish_output_rate(Store(":memory:")) is None


# --- zaman sapması ---------------------------------------------------------

def test_timestamp_drift_is_the_median_absolute_error():
    store = Store(":memory:")
    for ts in (10.0, 30.0):
        _episode(store, start_ts=ts)
    assert timestamp_drift(store, [(12.0, 20.0), (33.0, 40.0)]) == 2.5


def test_archive_episodes_are_not_counted_as_detections():
    """`load_history` arşiv olaylarını epizot olarak tohumluyor. Onlar tespit
    değil; sayılırlarsa sapma sahte biçimde küçülür."""
    store = Store(":memory:")
    archived = _episode(store, "arşiv olayı", start_ts=0.0)
    _episode(store, "canlı olay", start_ts=10.0)
    assert timestamp_drift(store, [(2.0, 8.0)]) == 2.0
    assert timestamp_drift(store, [(2.0, 8.0)],
                           seeded_episode_ids={archived.id}) == 8.0


def test_drift_is_not_measured_without_labelled_windows():
    store = Store(":memory:")
    _episode(store, start_ts=10.0)
    assert timestamp_drift(store, []) is None
    assert timestamp_drift(Store(":memory:"), [(1.0, 2.0)]) is None


# --- arşiv zaman birimi ----------------------------------------------------

def test_no_episode_in_the_store_carries_an_epoch_timestamp():
    """`Episode.start_ts` video saniyesi. Arşiv fikstürleri bir zamanlar aynı
    sütunda epoch saniyesi taşıyordu ve `mmss()` onları `99:59`'a yapıştırıp
    makul görünen yanlış bir saat basıyordu."""
    gateway = Mock()
    gateway.embed.return_value = [0.1, 0.2]
    store = Store(":memory:")
    load_history(gateway, store)

    assert store.episodes(), "arşiv boş yüklendi"
    assert all(e.start_ts < EPOCH_THRESHOLD_S for e in store.episodes())
    assert all((e.end_ts or 0.0) < EPOCH_THRESHOLD_S for e in store.episodes())
    assert epoch_scale_episodes(store) == []


def test_epoch_scale_episodes_names_the_offender():
    store = Store(":memory:")
    offender = _episode(store, "epoch damgalı olay", start_ts=1786567260.0)
    assert [e.id for e in epoch_scale_episodes(store)] == [offender.id]


# --- toplama ---------------------------------------------------------------

KPI_KEYS = {"decision_distribution", "vlm_trigger_rate", "vision_tokens",
            "correction_propagation", "timestamp_drift_s",
            "turkish_output_rate"}


def test_collect_reports_every_kpi_and_the_run_status():
    store = _store([("orchestrator", "perception", 0.8)], observation=10,
                   interpretation=1)
    record = collect(store)
    assert record["status"] == MEASURED
    assert set(record["kpis"]) == KPI_KEYS


def test_aggregate_averages_only_measured_clips():
    """Bozulmuş klip ortalamaya girerse manşet sayı sulanır."""
    measured = collect(_store([("orchestrator", "perception", 0.8),
                               ("orchestrator", "interpreter", 0.8)],
                              observation=10, interpretation=1))
    broken = collect(_store([("orchestrator", "perception", 0.0)] * 4))
    summary = aggregate([{"video": "a", "error": None, **measured},
                         {"video": "b", "error": None, **broken}])
    assert summary["clips"] == {"total": 2, "measured": 1, "degraded": 1,
                                "unmeasured": 0, "error": 0}
    assert summary["status"] == DEGRADED
    assert summary["kpis"]["decision_distribution"]["closed_at_router"] == 0.5
    assert summary["kpis"]["vlm_trigger_rate"] == 0.1


def test_aggregate_is_unmeasured_when_no_clip_could_be_measured():
    summary = aggregate([{"video": "a", "error": "video yok",
                          "status": UNMEASURED, "kpis": {}}])
    assert summary["status"] == UNMEASURED
    assert summary["kpis"]["decision_distribution"] is None
    assert set(summary["kpis"]) == KPI_KEYS


def test_bucket_names_survive_agent_rename():
    """Kova adları ajan adlarından bağımsız (spec §4).

    Ayrışmazlarsa `bench/kpi.json` içindeki taban ölçüm okunamaz hâle gelir.
    """
    from benchmark.kpi import DECISION_BUCKETS, _BUCKET_BY_TARGET
    assert "closed_at_router" in DECISION_BUCKETS
    assert "to_synthesizer" in DECISION_BUCKETS
    assert _BUCKET_BY_TARGET["anomaly_analyst"] == "to_synthesizer"
    assert "synthesizer" not in _BUCKET_BY_TARGET
