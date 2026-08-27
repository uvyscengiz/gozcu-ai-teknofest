"""Görev 15 — benchmark koşucusu, etiket dosyası ve rapor.

`kpi.py` fikstürsüz ve gateway'sizdi; **koşu değil.** Bu dosyanın koruduğu şey
tek bir cümle: eksik ön koşulda benchmark sıfırlarla dolu bir tablo
üretmemeli. Sıfırlarla dolu bir `kpi.json` çökme değil, ölçüm gibi görünen bir
hiçtir — ve jüriye giden dosya odur.
"""

import json

import pytest

from benchmark import kpi, report, run
from benchmark.ground_truth import (DEFAULT_PATH, Clip, GroundTruthError,
                                    load_ground_truth, windows)
from gozcu.models import Episode, Handoff, Observation
from gozcu.store import Store

HEADER = "video,has_incident,start_s,end_s,kind\n"


def _csv(tmp_path, body: str):
    path = tmp_path / "gt.csv"
    path.write_text(HEADER + body, encoding="utf-8")
    return path


# --- etiket dosyası --------------------------------------------------------

def test_the_shipped_ground_truth_file_parses():
    clips = load_ground_truth(DEFAULT_PATH)
    assert len(clips) == 5
    assert sum(1 for c in clips if c.has_incident) == 4
    assert all(c.window is None or c.window[1] > c.window[0] for c in clips)


def test_a_negative_example_is_kept_but_never_measured(tmp_path):
    """`has_incident=0` satırında `start_s` boş; `float("")` istisna atardı ve
    bu satır sapma hesabına hiç girmemeli."""
    clips = load_ground_truth(_csv(tmp_path, "clips/a.mp4,0,,,yok\n"))
    assert clips[0].has_incident is False
    assert clips[0].window is None
    assert windows(clips) == []


def test_an_incident_without_a_marked_window_is_reported_not_guessed(tmp_path):
    """Pencere el işi. İşaretlenmemiş satır ölçüme girmez ama kaybolmaz."""
    clips = load_ground_truth(_csv(tmp_path, "clips/a.mp4,1,,,fire\n"))
    assert clips[0].unlabelled is True
    assert windows(clips) == []


def test_a_marked_window_reaches_the_drift_measurement(tmp_path):
    clips = load_ground_truth(_csv(tmp_path, "clips/a.mp4,1,12.5,19,fire\n"))
    assert windows(clips) == [(12.5, 19.0)]


@pytest.mark.parametrize("row, fragment", [
    ("clips/a.mp4,1,1,2,patlama\n", "bilinmeyen kind"),
    ("clips/a.mp4,1,1,2,yok\n", "has_incident=1"),
    ("clips/a.mp4,0,,,fire\n", "has_incident=0"),
    ("clips/a.mp4,1,abc,2,fire\n", "start_s sayı değil"),
    ("clips/a.mp4,1,5,5,fire\n", "büyük olmalı"),
    (",1,1,2,fire\n", "video yolu boş"),
    ("clips/a.mp4,2,1,2,fire\n", "has_incident 0 ya da 1"),
])
def test_a_broken_label_row_stops_the_run_loudly(tmp_path, row, fragment):
    with pytest.raises(GroundTruthError, match=fragment):
        load_ground_truth(_csv(tmp_path, row))


def test_comments_and_blank_lines_are_skipped(tmp_path):
    path = tmp_path / "gt.csv"
    path.write_text("# yorum\n\n" + HEADER + "clips/a.mp4,0,,,yok\n",
                    encoding="utf-8")
    assert len(load_ground_truth(path)) == 1


def test_a_missing_label_file_is_an_error_not_an_empty_run(tmp_path):
    with pytest.raises(GroundTruthError, match="etiket dosyası yok"):
        load_ground_truth(tmp_path / "yok.csv")


# --- ön koşullar -----------------------------------------------------------

def _rewritten_pipeline(video_path, store=None, gw=None):
    return None


def _stage_one_pipeline(video_path, output_dir=None):
    """1. Aşama PoC'sinin imzası — depoya hiçbir şey yazmıyordu."""
    return None


def test_preflight_rejects_the_stage_one_pipeline():
    """Ayırt edici alan `store`: PoC imzasıyla koşulan bir benchmark her
    KPI'ı `null` okur ve bunu bir bulgu sanardık.

    Görev 17 indi; depodaki `run_pipeline` artık `store` alıyor ve gözlemleri
    oraya yazıyor — `vlm_trigger_rate`'in paydası budur.
    """
    from gozcu.run import run_pipeline

    assert run.pipeline_is_rewritten(run_pipeline) is True
    assert run.pipeline_is_rewritten(_rewritten_pipeline) is True
    assert run.pipeline_is_rewritten(_stage_one_pipeline) is False


def test_preflight_names_every_missing_prerequisite_at_once(tmp_path):
    clip = Clip(video="clips/yok.mp4", has_incident=True, window=(1.0, 2.0),
                kind="fire")
    with pytest.raises(run.PrerequisiteError) as error:
        run.preflight([clip], data_dir=tmp_path, run_pipeline=None,
                      gateway_probe=lambda: False)
    message = str(error.value)
    assert "klip dosyası yok" in message
    assert "run_pipeline" in message
    assert "gateway" in message


def test_preflight_passes_when_everything_is_in_place(tmp_path):
    (tmp_path / "clips").mkdir()
    (tmp_path / "clips" / "a.mp4").write_bytes(b"0")
    clip = Clip(video="clips/a.mp4", has_incident=True, window=(1.0, 2.0),
                kind="fire")
    run.preflight([clip], data_dir=tmp_path,
                  run_pipeline=_rewritten_pipeline, gateway_probe=lambda: True)


def test_preflight_refuses_an_empty_label_set(tmp_path):
    with pytest.raises(run.PrerequisiteError, match="hiç klip yok"):
        run.preflight([], data_dir=tmp_path, run_pipeline=_rewritten_pipeline)


# --- klip koşusu -----------------------------------------------------------

def _clip(window=(12.0, 19.0)):
    return Clip(video="clips/a.mp4", has_incident=True, window=window,
                kind="fire")


def _seeded_store(_clip_unused=None):
    """Arşiv tohumlanmış bir depo — `load_history`'nin bıraktığı hâl."""
    store = Store(":memory:")
    archived = Episode(start_ts=0.0, phase="outcome", summary_tr="arşiv olayı",
                       preliminary_risk="Orta", state="closed")
    archived.id = store.create_episode(archived)
    return store


def _pipeline_writing(store_ref):
    def run_pipeline(video_path, store=None, gw=None, archive=True):
        store_ref.append(store)
        store.save_observation(Observation(ts=0.0))
        store.save_handoff(Handoff(ts=0.0, source_agent="orchestrator",
                                   target_agent="perception", reason="sakin",
                                   confidence=0.8, payload_ref="w@0"))
        episode = Episode(start_ts=14.0, phase="onset",
                          summary_tr="Yük düştü, ekip bölgede.",
                          preliminary_risk="Yüksek")
        store.create_episode(episode)
    return run_pipeline


def test_a_clip_run_measures_the_live_episode_not_the_archive():
    written: list = []
    record = run.run_clip(_clip(), run_pipeline=_pipeline_writing(written),
                          store_factory=_seeded_store)
    assert record["error"] is None
    assert record["status"] == kpi.MEASURED
    # Arşiv epizodu 0.0'da duruyor; sayılsaydı sapma 12.0 okunurdu.
    assert record["kpis"]["timestamp_drift_s"] == 2.0


def test_a_crashing_clip_is_recorded_and_the_run_continues():
    def exploding(video_path, store=None, archive=True):
        raise RuntimeError("video okunamadı")

    record = run.run_clip(_clip(), run_pipeline=exploding,
                          store_factory=_seeded_store)
    assert "video okunamadı" in record["error"]
    assert record["status"] == kpi.UNMEASURED
    assert set(record["kpis"]) == set(kpi.KPI_KEYS)


def test_an_epoch_timestamp_in_the_store_fails_the_clip_instead_of_reporting():
    """Epoch damgalı bir epizot `mmss()` altında `99:59` okunur — makul
    görünen yanlış bir saat. Ölçüm bunu sonuç diye yayınlamaz."""
    def bad_pipeline(video_path, store=None, archive=True):
        store.create_episode(Episode(start_ts=1786567260.0, phase="outcome",
                                     summary_tr="x", preliminary_risk="Orta"))

    record = run.run_clip(_clip(), run_pipeline=bad_pipeline,
                          store_factory=_seeded_store)
    assert "epoch" in record["error"]


def test_the_payload_carries_the_clip_records_and_the_aggregate():
    written: list = []
    payload = run.benchmark([_clip()], run_pipeline=_pipeline_writing(written),
                            store_factory=_seeded_store)
    assert payload["schema_version"] == run.SCHEMA_VERSION
    assert payload["ground_truth"] == {"clips": 1, "labelled": 1,
                                       "unlabelled": 0, "no_incident": 0}
    assert payload["aggregate"]["status"] == kpi.MEASURED


# --- şema ------------------------------------------------------------------

def _schema() -> dict:
    return json.loads((run.BENCH_DIR / "kpi.schema.json")
                      .read_text(encoding="utf-8"))


def test_the_schema_names_exactly_the_kpis_the_code_produces():
    """Şema ile kod ayrışırsa rapor sessizce yanlış anahtarı okur; bu proje
    o ayrışmayı beş kez yaşadı."""
    schema = _schema()
    assert set(schema["definitions"]["kpis"]["properties"]) == set(kpi.KPI_KEYS)
    assert (set(schema["definitions"]["distribution"]["properties"])
            == set(kpi.DECISION_BUCKETS))


def test_a_generated_payload_validates_against_the_committed_schema():
    jsonschema = pytest.importorskip("jsonschema")
    written: list = []
    payload = run.benchmark([_clip()], run_pipeline=_pipeline_writing(written),
                            store_factory=_seeded_store)
    jsonschema.validate(json.loads(json.dumps(payload)), _schema())


def test_a_failed_payload_also_validates():
    jsonschema = pytest.importorskip("jsonschema")

    def exploding(video_path, store=None, archive=True):
        raise RuntimeError("video yok")

    payload = run.benchmark([_clip(window=None)], run_pipeline=exploding,
                            store_factory=_seeded_store)
    jsonschema.validate(json.loads(json.dumps(payload)), _schema())


def test_the_payload_is_written_as_readable_utf8(tmp_path):
    written: list = []
    payload = run.benchmark([_clip()], run_pipeline=_pipeline_writing(written),
                            store_factory=_seeded_store)
    path = run.write_payload(payload, tmp_path / "kpi.json")
    assert json.loads(path.read_text(encoding="utf-8")) == payload


# --- rapor -----------------------------------------------------------------

def _payload(status, distribution, **kpis):
    body = {key: None for key in kpi.KPI_KEYS}
    body["decision_distribution"] = distribution
    body.update(kpis)
    return {"schema_version": 1, "generated_at": "2026-08-24T09:00:00+00:00",
            "ground_truth": {"clips": 1, "labelled": 0, "unlabelled": 1,
                             "no_incident": 0},
            "clips": [{"video": "clips/a.mp4", "status": status,
                       "error": None, "kpis": body}],
            "aggregate": {"status": status,
                          "clips": {"total": 1, "measured": 0, "degraded": 1,
                                    "unmeasured": 0, "error": 0},
                          "kpis": body}}


def test_the_report_says_not_measured_instead_of_zero():
    markdown = report.render_markdown(_payload(kpi.UNMEASURED, None))
    assert report.NOT_MEASURED_TEXT in markdown
    assert "ÖLÇÜLEMEDİ" in markdown


def test_the_report_banners_a_degraded_run():
    distribution = {"closed_at_router": 0.1, "to_interpreter": 0.0,
                    "to_synthesizer": 0.0, "escalated": 0.0, "degraded": 0.9}
    markdown = report.render_markdown(_payload(kpi.DEGRADED, distribution))
    assert "BOZULMUŞ KOŞU" in markdown
    assert "0.900" in markdown


def test_the_report_states_that_tokens_cover_the_vision_tier_only():
    markdown = report.render_markdown(_payload(kpi.MEASURED, None))
    assert "yalnız görü kademesini" in markdown


def test_no_chart_is_drawn_when_the_distribution_was_not_measured(tmp_path):
    assert report.write_chart(_payload(kpi.UNMEASURED, None),
                              tmp_path / "c.png") is None


def test_the_chart_is_written_when_the_distribution_exists(tmp_path):
    pytest.importorskip("matplotlib")
    distribution = {"closed_at_router": 0.7, "to_interpreter": 0.2,
                    "to_synthesizer": 0.05, "escalated": 0.05,
                    "degraded": 0.0}
    path = report.write_chart(_payload(kpi.MEASURED, distribution),
                              tmp_path / "c.png")
    assert path.is_file() and path.stat().st_size > 0
