"""0. Faz ölçüm fonksiyonlarının testleri.

Bu testler `benchmark.perception`'ın **saf** yarısını sınıyor: girdisi
listeler, çıktısı sayılar. Model, ffmpeg, dosya sistemi yok — ölçüm katmanının
kendisi yanlış sayarsa bir çöküş görmeyiz, **sonuç gibi görünen bir yalan**
görürüz, ve o yalan burada yakalanmalı.
"""

import math

import pytest

from benchmark import perception


class TestPresenceRecall:
    """Manşet ölçüm: karede en az bir kişi görülebildi mi."""

    def test_every_frame_has_a_person(self):
        assert perception.presence_recall([1, 2, 3]) == 1.0

    def test_no_frame_has_a_person(self):
        assert perception.presence_recall([0, 0, 0]) == 0.0

    def test_half_the_frames(self):
        assert perception.presence_recall([0, 1, 0, 4]) == 0.5

    def test_empty_run_is_unmeasured_not_zero(self):
        # `0.0` "ölçtük, hiç göremedi" demek; boş koşuda ölçülen bir şey yok.
        assert perception.presence_recall([]) is None


class TestCountRecall:
    """Sayım duyarlılığı — fazla sayma duyarlılığı ŞİŞİREMEZ."""

    def test_perfect_count(self):
        assert perception.count_recall([(4, 4), (10, 10)]) == 1.0

    def test_undercount_is_penalised(self):
        assert perception.count_recall([(1, 4)]) == 0.25

    def test_overcount_cannot_exceed_one(self):
        # min() olmasaydı 8/4 = 2,0 çıkardı ve kör bir katman "%200 duyarlı"
        # görünürdü.
        assert perception.count_recall([(8, 4)]) == 1.0

    def test_overcount_does_not_mask_a_miss(self):
        # Bir karede 8 fazla saymak, başka bir karedeki 0'ı telafi etmemeli.
        assert perception.count_recall([(8, 4), (0, 4)]) == 0.5

    def test_zero_truth_is_unmeasured(self):
        assert perception.count_recall([(0, 0)]) is None

    def test_empty_is_unmeasured(self):
        assert perception.count_recall([]) is None


class TestCountError:
    def test_mean_absolute_error(self):
        stats = perception.count_error([(1, 4), (2, 4)])
        assert stats["mae"] == pytest.approx(2.5)
        assert stats["mean_reported"] == pytest.approx(1.5)
        assert stats["mean_truth"] == pytest.approx(4.0)

    def test_worst_frame_is_named(self):
        stats = perception.count_error([(1, 4), (1, 20), (3, 4)])
        assert stats["worst_gap"] == 19

    def test_empty_is_unmeasured(self):
        assert perception.count_error([]) is None


class TestZeroDetectionRate:
    def test_all_frames_blind(self):
        assert perception.zero_detection_rate([0, 0]) == 1.0

    def test_no_frame_blind(self):
        assert perception.zero_detection_rate([1, 5]) == 0.0

    def test_empty_is_unmeasured(self):
        assert perception.zero_detection_rate([]) is None


class TestTrackIdRate:
    def test_all_boxes_get_an_id(self):
        assert perception.track_id_rate([1, 2, 3]) == 1.0

    def test_no_box_gets_an_id(self):
        assert perception.track_id_rate([None, None]) == 0.0

    def test_mixed(self):
        assert perception.track_id_rate([1, None, 2, None]) == 0.5

    def test_no_boxes_at_all_is_unmeasured(self):
        # Sıfır kutuda "kimlik oranı %0" demek takip katmanını, tespit
        # katmanının başarısızlığı için suçlamak olurdu.
        assert perception.track_id_rate([]) is None


class TestEnergyRank:
    """Hareket triyajının nişanı: olay saniyesi enerjide kaçıncı sırada."""

    def test_highest_energy_frame_ranks_first(self):
        assert perception.energy_rank([0.1, 0.9, 0.5], 1) == 1

    def test_lowest_energy_frame_ranks_last(self):
        assert perception.energy_rank([0.1, 0.9, 0.5], 0) == 3

    def test_ties_share_the_better_rank(self):
        # Beraberlikte kötü sırayı vermek triyajı olduğundan kötü gösterirdi.
        assert perception.energy_rank([0.5, 0.5, 0.1], 1) == 1

    def test_missing_evidence_has_no_rank(self):
        assert perception.energy_rank([None, 0.9], 0) is None

    def test_index_out_of_range_is_none(self):
        assert perception.energy_rank([0.1], 7) is None


class TestNearestSampleIndex:
    """Etiket saniyesi ile kare saniyesi birebir tutmayabilir."""

    def test_exact_hit(self):
        assert perception.nearest_index([0.0, 1.0, 2.0], 1.0) == 1

    def test_nearest_within_tolerance(self):
        assert perception.nearest_index([0.0, 1.0, 2.0], 1.4) == 1

    def test_outside_tolerance_is_dropped(self):
        # Uzak bir kareyi etiketle eşleştirmek, ölçülmemiş bir kareye not
        # vermek olurdu.
        assert perception.nearest_index([0.0, 1.0], 9.0, tolerance=0.5) is None

    def test_empty_timeline(self):
        assert perception.nearest_index([], 1.0) is None


class TestRealTimeFactor:
    def test_faster_than_realtime(self):
        assert perception.real_time_factor(10.0, 100.0) == pytest.approx(0.1)

    def test_zero_duration_is_unmeasured(self):
        assert perception.real_time_factor(10.0, 0.0) is None


class TestTrackingCost:
    """Takip katmanının tespite mal ettiği kutular.

    `gozcu.track` sözleşmesi "takip yalnız kimlik ekler" diyor. Bu fonksiyon
    o sözleşmenin tutup tutmadığını sayıyor: takip bir kareden kutu ELERSE
    sözleşme tutmamıştır, ve bunu kimse fark etmeden geçmemeli.
    """

    def test_tracking_keeps_everything(self):
        cost = perception.tracking_cost([2, 3], [2, 3])
        assert cost["boxes_lost"] == 0
        assert cost["frames_reduced"] == 0

    def test_tracking_drops_boxes(self):
        cost = perception.tracking_cost(tracked=[1, 3], untracked=[6, 3])
        assert cost["boxes_lost"] == 5
        assert cost["frames_reduced"] == 1
        assert cost["retention"] == pytest.approx(4 / 9)

    def test_tracking_never_adds_is_reported(self):
        # Takip bir kareye kutu EKLİYORSA sözleşme başka türlü bozulmuştur;
        # sayı yutulmamalı.
        cost = perception.tracking_cost(tracked=[5], untracked=[2])
        assert cost["frames_increased"] == 1

    def test_ragged_input_is_refused(self):
        with pytest.raises(ValueError):
            perception.tracking_cost([1], [1, 2])

    def test_empty_is_unmeasured(self):
        assert perception.tracking_cost([], []) is None


class TestSummarise:
    """Uçtan uca birleştirme — parçalar doğruyken bütün de doğru mu."""

    def _run(self):
        return perception.summarise(
            timestamps=[0.0, 1.0, 2.0, 3.0],
            person_counts=[3, 0, 0, 1],
            box_counts=[3, 0, 0, 2],
            track_ids=[1, 2, 3, None, 4],
            energies=[None, 0.2, 0.9, 0.4],
            truth={
                "persons_present_every_frame": True,
                "incident": {"onset_s": 2.0},
                "samples": [{"t_s": 0, "persons": 4},
                            {"t_s": 2, "persons": 10}],
            },
            duration_s=4.0,
            timings_s={"detect": 1.0},
        )

    def test_presence_recall_counts_only_frames_with_a_person(self):
        assert self._run()["presence_recall"] == pytest.approx(0.5)

    def test_count_recall_uses_only_labelled_frames(self):
        # Etiketli kareler t=0 (3/4) ve t=2 (0/10) → 3/14.
        assert self._run()["count_recall"] == pytest.approx(3 / 14)

    def test_incident_frame_energy_rank_is_reported(self):
        assert self._run()["incident_energy_rank"] == 1

    def test_frames_counted(self):
        assert self._run()["frames"] == 4

    def test_presence_recall_is_none_when_truth_does_not_claim_it(self):
        """Etiket "her karede insan var" DEMİYORSA manşet ölçüm üretilmez.

        Bu ölçüm bütünüyle o iddiaya dayanıyor; iddia yokken üretilen sayı
        neyin duyarlılığı olduğunu söyleyemez.
        """
        result = perception.summarise(
            timestamps=[0.0], person_counts=[0], box_counts=[0],
            track_ids=[], energies=[None],
            truth={"persons_present_every_frame": False, "samples": []},
            duration_s=1.0, timings_s={})
        assert result["presence_recall"] is None

    def test_ragged_input_is_refused(self):
        """Hizasız listeler sessizce kırpılmaz.

        Kırpılsaydı ölçüm eksik bir kare kümesi üzerinden yapılır ve bunu
        hiçbir sayı söylemezdi.
        """
        with pytest.raises(ValueError):
            perception.summarise(
                timestamps=[0.0, 1.0], person_counts=[1], box_counts=[1],
                track_ids=[], energies=[None, 0.1],
                truth={"samples": []}, duration_s=1.0, timings_s={})

    def test_json_serialisable(self):
        import json
        # `nan`/`inf` geçerli JSON değil; rapor dosyası yazılamazsa ölçüm yok.
        text = json.dumps(self._run())
        assert "NaN" not in text and "Infinity" not in text
        assert not any(isinstance(v, float) and math.isnan(v)
                       for v in self._run().values())


class TestRenderMarkdown:
    """Rapor gövdesi — ölçülemeyen hiçbir hücre sayıya çevrilmez."""

    def _payload(self, **overrides):
        result = {
            "video": "k.mp4", "frames": 2, "presence_recall": 0.5,
            "count_recall": None, "count_error": None,
            "zero_detection_rate": 0.5, "track_id_rate": None,
            "unique_track_ids": 0, "peak_person_count": 1,
            "real_time_factor": 0.3, "incident_onset_s": None,
            "incident_energy_rank": None, "incident_person_count": None,
            "timings_s": {"track": 1.0}, "samples": [],
            "tracking_cost": None, "untracked": {},
        }
        result.update(overrides)
        return {"generated_at": "2026-08-25T00:00:00+00:00",
                "schema_version": 1, "result": result,
                "config": {"model": "m.pt", "classes": ["person"],
                           "confidence": 0.2, "fps": 1.0, "width": 896}}

    def test_unmeasured_kpi_is_not_rendered_as_zero(self):
        text = perception.render_markdown(self._payload())
        assert perception.NOT_MEASURED in text
        assert "%0 |" not in text

    def test_measured_kpi_is_a_percentage(self):
        assert "%50" in perception.render_markdown(self._payload())

    def test_incident_section_appears_only_when_labelled(self):
        assert "## Olay anı" not in perception.render_markdown(self._payload())
        labelled = self._payload(incident_onset_s=49.0,
                                 incident_energy_rank=53,
                                 incident_person_count=0)
        assert "## Olay anı" in perception.render_markdown(labelled)

    def test_sample_rows_are_rendered(self):
        payload = self._payload(samples=[
            {"t_s": 8, "truth": 4, "uncertainty": 0, "reported": 1}])
        assert "| 8 | 4 | 1 | 3 |" in perception.render_markdown(payload)
