"""`gozcu.ui.series` — konsolun iki canlı grafiğini besleyen zaman serileri.

Grafikler videonun kendi saatinde ilerliyor; bu modül onların ARKASINDAKİ
veriyi kuruyor ve burada sınanan şey çizim değil, o verinin dürüstlüğü:
ölçülmemiş bir kare sıfır gibi görünmemeli, eşik koşuya göreli kalmalı,
"Diğer" kovası gerçekten geri kalanın toplamı olmalı.
"""

import pytest

from gozcu.core.models import Detection, Observation, RiskAssessment
from gozcu.ui.series import (MAX_NAMED_LABELS, OTHER_LABEL, energy_series,
                             entity_series, peak_threshold, risk_track)


def _observation(ts: float, *labels: str) -> Observation:
    """`labels`'ın her biri için bir tespit taşıyan gözlem."""
    return Observation(
        ts=ts,
        detections=[Detection(label=label, confidence=0.9, box=(0, 0, 1, 1))
                    for label in labels])


# =============================================================================
# Varlık sayısı grafiği
# =============================================================================

def test_entity_series_counts_each_label_per_timestamp():
    """Y ekseni o saniyedeki tespit sayısı — türe göre ayrılmış."""
    series = entity_series([
        _observation(0.0, "insan", "insan", "forklift"),
        _observation(1.0, "insan"),
    ])

    assert series["ts"] == [0.0, 1.0]
    by_label = {row["label"]: row["values"] for row in series["series"]}
    assert by_label == {"insan": [2, 1], "forklift": [1, 0]}


def test_entity_series_keeps_only_the_three_most_seen_labels():
    """Ekranda en çok tespit edilen üç tür kendi çizgisiyle kalıyor.

    Görev raporunun kuralı: grafiğin karmaşıklaşmaması için üçten fazlası
    tek bir kategoriye toplanıyor.
    """
    series = entity_series([
        _observation(0.0, *(["insan"] * 5), *(["araç"] * 4),
                     *(["paket"] * 3), "kedi", "köpek"),
    ])

    labels = [row["label"] for row in series["series"]]
    assert labels[:MAX_NAMED_LABELS] == ["insan", "araç", "paket"]
    assert labels[MAX_NAMED_LABELS] == OTHER_LABEL


def test_entity_series_folds_the_rest_into_one_other_line():
    """"Diğer" gerçekten geri kalanın TOPLAMI — örnek bir tür değil."""
    series = entity_series([
        _observation(0.0, *(["insan"] * 5), *(["araç"] * 4),
                     *(["paket"] * 3), "kedi", "köpek", "kuş"),
    ])

    by_label = {row["label"]: row["values"] for row in series["series"]}
    assert by_label[OTHER_LABEL] == [3]      # kedi + köpek + kuş


def test_entity_series_has_no_other_line_when_three_labels_or_fewer():
    """Üç tür varken boş bir "Diğer" çizgisi çizilmiyor."""
    series = entity_series([_observation(0.0, "insan", "araç", "paket")])

    assert OTHER_LABEL not in [row["label"] for row in series["series"]]


def test_entity_series_orders_timestamps_and_is_empty_without_observations():
    """Zaman ekseni sıralı; gözlem yoksa seri boş — uydurma nokta yok."""
    series = entity_series([_observation(2.0, "insan"),
                            _observation(0.0, "insan")])
    assert series["ts"] == [0.0, 2.0]

    assert entity_series([]) == {"ts": [], "series": []}


# =============================================================================
# Zirve eşiği — koşuya GÖRELİ, sabit değil
# =============================================================================

def test_peak_threshold_sits_above_the_run_mean():
    """Eşik koşunun kendi dağılımından çıkıyor (ortalama + k·sapma).

    `gozcu.motion` skorları koşu içinde normalize ediyor ve modül
    docstring'i sabit bir eşiği açıkça yasaklıyor ("enerji > 0,8 ise
    alarm" kuralı çıkarılmasın) — bu yüzden çizgi koşudan koşuya kayar.
    """
    values = [0.1, 0.1, 0.1, 0.1, 0.9]
    threshold = peak_threshold(values)

    assert threshold is not None
    assert sum(values) / len(values) < threshold < 0.9


def test_peak_threshold_is_none_when_nothing_stands_out():
    """Düz bir seride zirve YOK — sıfır sapma, çizgi çizilmiyor."""
    assert peak_threshold([0.4, 0.4, 0.4]) is None


def test_peak_threshold_is_none_without_enough_evidence():
    """Tek nokta ya da hiç nokta bir dağılım değil."""
    assert peak_threshold([]) is None
    assert peak_threshold([0.5]) is None


# =============================================================================
# Piksel entropisi (hareket enerjisi) grafiği
# =============================================================================

def test_energy_series_pairs_each_timestamp_with_its_score():
    series = energy_series([0.0, 1.0, 2.0], [0.2, 0.9, 0.3])

    assert series["ts"] == [0.0, 1.0, 2.0]
    assert series["values"] == [0.2, 0.9, 0.3]


def test_energy_series_keeps_unmeasured_frames_as_null_not_zero():
    """Okunamayan kare bir BOŞLUK, sıfır değil.

    `gozcu.motion` kanıtsız kareyi `None` veriyor. Onu 0,0'a düşürmek
    grafiğe "burada hiç hareket yoktu" diye yalan söyletirdi; konsolun
    Performans sayfasındaki kural da aynı — ölçülemeyen hücre sıfır diye
    gösterilmiyor.
    """
    series = energy_series([0.0, 1.0, 2.0], [0.2, None, 0.3])

    assert series["values"] == [0.2, None, 0.3]


def test_energy_series_marks_the_peaks_above_the_threshold():
    """Zirveler eşiği AŞAN kareler — kırmızı çizginin üstünde kalanlar."""
    timestamps = [0.0, 1.0, 2.0, 3.0, 4.0]
    series = energy_series(timestamps, [0.1, 0.1, 0.1, 0.1, 0.9])

    assert series["peaks"] == [4.0]
    assert series["threshold"] == peak_threshold([0.1, 0.1, 0.1, 0.1, 0.9])


def test_energy_series_ignores_nulls_when_computing_the_threshold():
    """Eşik ölçülmüş karelerden çıkıyor; boşluklar dağılımı aşağı çekmiyor."""
    with_gaps = energy_series([0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
                              [0.1, None, 0.1, 0.1, 0.1, 0.9])
    without_gaps = energy_series([0.0, 2.0, 3.0, 4.0, 5.0],
                                 [0.1, 0.1, 0.1, 0.1, 0.9])

    assert with_gaps["threshold"] == without_gaps["threshold"]


def test_energy_series_has_no_peaks_when_there_is_no_threshold():
    """Eşik yoksa zirve de yok — "hepsi zirve" demek hiçbir şey demek."""
    series = energy_series([0.0, 1.0], [0.4, 0.4])

    assert series["threshold"] is None
    assert series["peaks"] == []


def test_energy_series_refuses_misaligned_input():
    """Hizasız girdi sessizce eşleştirilmiyor — yanlış saniyeye yanlış skor."""
    with pytest.raises(ValueError):
        energy_series([0.0, 1.0], [0.2])


def test_energy_series_is_empty_without_frames():
    assert energy_series([], []) == {"ts": [], "values": [],
                                     "threshold": None, "peaks": []}


# =============================================================================
# Risk izi — video saatine bağlı durum çubuğu (Görev raporu §2)
# =============================================================================

def _risk(ts: float, level: str, episode_id: int = 1) -> RiskAssessment:
    return RiskAssessment(episode_id=episode_id, ts=ts, level=level,
                          rationale_tr="gerekçe", preventable=True)


def test_risk_track_is_ordered_by_video_time():
    """Çubuk videonun saatini takip ediyor; sıra kayarsa yanlış anda
    yanlış renk yanar."""
    track = risk_track([_risk(9.0, "Kritik"), _risk(3.0, "Düşük")])

    assert [row["ts"] for row in track] == [3.0, 9.0]
    assert [row["level"] for row in track] == ["Düşük", "Kritik"]


def test_risk_track_keeps_the_four_level_contract():
    """Çubuk üç kademeli ama seviye DÖRT — sözleşme (CLAUDE.md) korunuyor.

    "Kritik"i "Yüksek"e katlamak teli fakirleştirirdi: çubuğun kaç bölmesi
    olduğu bir ÇİZİM kararı, seviyenin adı ise sistemin kararı.
    """
    track = risk_track([_risk(1.0, "Yüksek"), _risk(2.0, "Kritik")])

    assert [row["level"] for row in track] == ["Yüksek", "Kritik"]


def test_risk_track_drops_the_seeded_archive():
    """Arşivden tohumlanan epizotların riski BU videonun riski değil.

    Onlar koşu başlamadan önce belleğe konan eski kayıtlar; çubuğa
    girselerdi video daha başlamadan kırmızı yanardı.
    """
    track = risk_track([_risk(1.0, "Kritik", episode_id=7),
                        _risk(2.0, "Düşük", episode_id=8)],
                       archived={7})

    assert [row["level"] for row in track] == ["Düşük"]


def test_risk_track_is_empty_without_any_assessment():
    assert risk_track([]) == []
