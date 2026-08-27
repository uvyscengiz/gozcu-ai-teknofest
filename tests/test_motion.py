"""Görev 16 — yerel hareket triyajı.

Bu dosyanın koruduğu iki cümle:

1. **İki sinyal var, çünkü tek sinyal kör.** Kare farkı yer değiştiren bir
   kütleyi görür ama sahnenin tonu kaydığında (yangın parıltısı, duman pusu,
   ışık değişimi) neredeyse hiçbir şey söylemez; histogram uzaklığı tam
   tersidir. `data/clips/yangin` etiketli bir kategori var — o klipler için
   çalışan sinyal ikincisidir.
2. **Kullanılamayan kare asla istisna atmaz.** Eksik dosya, bozuk dosya, tek
   kare, boş liste, farklı boyut — hepsi `None`'a düşer ve çağıran taraf
   periyodik nöbete geri dönebilir. Triyaj katmanı hiçbir koşuyu düşürmez.
"""

import cv2
import numpy as np
import pytest

from gozcu.models import Observation
from gozcu.motion import (build_motion_for, combine, frame_energy,
                          frame_entropy, raw_scores, window_energy)


def _write(path, image):
    # PNG, JPEG değil: kayıplı sıkıştırma kendi gürültüsünü ekliyor ve
    # testlerin sayısal iddiaları o gürültünün altında kalırdı.
    cv2.imwrite(str(path), image)
    return path


def _still(tmp_path, count, prefix="s"):
    """Değişmeyen kareler: enerji her yerde sıfır."""
    image = np.full((80, 80), 120, np.uint8)
    return [_write(tmp_path / f"{prefix}{i:02d}.png", image)
            for i in range(count)]


def _observations(timestamps):
    return [Observation(ts=ts) for ts in timestamps]


# -- kare enerjisi ------------------------------------------------------------

def test_energy_is_aligned_with_the_frames(tmp_path):
    """İlk karenin karşılaştıracağı önceki kare yok; skoru sıfır.

    Hizalama önemli: `build_motion_for` skorları zaman damgalarıyla eşliyor,
    listeler kayarsa pencere yanlış enerjiyi alır."""
    paths = _still(tmp_path, 5)
    energies = frame_energy(paths)
    assert len(energies) == 5
    assert energies[0] == 0.0


def test_energy_peaks_where_the_motion_is(tmp_path):
    """Sekiz karenin yalnız birinde bir kütle yer değiştiriyor; en yüksek
    skor orada olmalı, komşularında değil."""
    paths = []
    for i in range(8):
        image = np.full((120, 120), 90, np.uint8)
        image[30:90, (10 if i < 5 else 60):(70 if i < 5 else 120)] = 210
        paths.append(_write(tmp_path / f"m{i:02d}.png", image))
    energies = frame_energy(paths)
    assert int(np.argmax(energies)) == 5
    assert energies[5] > 0.0
    assert all(energy == 0.0 for i, energy in enumerate(energies) if i != 5)


def test_the_histogram_term_catches_what_the_frame_difference_misses(tmp_path):
    """İki sinyalin gerekçesi bu tek testte duruyor.

    Kare 3'te büyük bir kütle yer değiştiriyor: kare farkı bunu bağırarak
    söyler (62,4), histogram hiç görmez (0,0) — piksel sayıları aynı, yalnız
    yerleri değişti. Kare 6'da bütün sahne aydınlanıyor: kare farkı bunu
    ötekinin üçte biri kadar zayıf raporlar (18,0), histogram ise mümkün olan
    en yüksek uzaklığı verir (2,0).

    Yalnız kare farkıyla çalışan bir triyaj ton kaymasına 0,29 verir ve onu
    yer değiştirmenin ARKASINA sıralar. Yangın klibinde kaybedilen tam olarak
    budur.
    """
    paths = []
    for i in range(8):
        image = np.full((200, 200), 90, np.uint8)
        image[40:160, (10 if i < 3 else 110):(90 if i < 3 else 190)] = 220
        if i >= 6:
            image = np.clip(image.astype(np.int16) + 18, 0, 255).astype(np.uint8)
        paths.append(_write(tmp_path / f"h{i:02d}.png", image))

    raw = raw_scores(paths)
    absdiff = [None if pair is None else pair[0] for pair in raw]
    histogram = [None if pair is None else pair[1] for pair in raw]

    # Kare farkı yer değiştirmeye kanar, ton kaymasını ikinci plana atar.
    assert absdiff[3] > absdiff[6] > 0.0
    # Histogram yer değiştirmeyi hiç görmez, ton kaymasını tam puanla verir.
    assert histogram[3] == 0.0
    assert histogram[6] > histogram[3]
    # Birleşim ikisini de zirveye taşıyor: ton kayması artık 1,0.
    energies = frame_energy(paths)
    assert energies[6] == 1.0
    assert energies[3] == 1.0
    # ...oysa yalnız kare farkıyla 0,3'ün altında kalırdı.
    assert absdiff[6] / absdiff[3] < 0.5


def test_each_signal_is_normalised_within_the_run_before_the_max():
    """Birleşim kuralının kendisi: her sinyal koşu içindeki kendi zirvesine
    bölünür, sonra eleman bazında en büyüğü alınır.

    Sabit bir ölçeğe (255 ve 2) bölmek denenmedi değil — ama tipik videoda
    kare farkı 255'in yüzde birkaçında gezerken histogram uzaklığı 2'nin
    onda birlerinde geziyor; sabit ölçekte histogram terimi her pencerede
    kazanır ve kare farkı hiç konuşamaz. Koşu içi normalizasyon ikisini
    karşılaştırılabilir hâle getiren şey.
    """
    raw = [None, (10.0, 0.1), (20.0, 0.05), (5.0, 0.2)]
    assert combine(raw) == [None, 0.5, 1.0, 1.0]


def test_a_flat_run_is_all_zeroes_not_all_ones(tmp_path):
    """Hiç değişim yoksa normalizasyonun bölebileceği bir zirve de yoktur.

    Sıfıra bölüp `nan` üretmek ya da 'zirve = 0 ise hepsi 1,0' demek burada
    ölümcül olurdu: durgun bir klip aniden en yüksek enerjili klip gibi
    görünür ve triyaj hiçbir şeyi sıralayamazdı."""
    energies = frame_energy(_still(tmp_path, 6))
    assert energies == [0.0] * 6


# -- dayanıklılık: hiçbir arıza istisna atmaz ---------------------------------

def test_a_missing_frame_file_scores_none_instead_of_raising(tmp_path):
    paths = _still(tmp_path, 4)
    paths.insert(2, tmp_path / "yok.png")            # hiç yazılmadı
    raw = raw_scores(paths)
    assert len(raw) == 5
    # Eksik kare hem kendi konumunu hem bir sonrakini karşılaştırılamaz kılar.
    assert raw[2] is None and raw[3] is None
    assert frame_energy(paths)[2] == 0.0


def test_an_unreadable_frame_file_scores_none_instead_of_raising(tmp_path):
    paths = _still(tmp_path, 3)
    broken = tmp_path / "bozuk.png"
    broken.write_bytes(b"bu bir png degil")
    paths.insert(1, broken)
    assert raw_scores(paths)[1] is None
    assert frame_energy(paths)[1] == 0.0


def test_frames_of_different_sizes_are_compared_not_rejected(tmp_path):
    """Ölçek değişimi bir arıza değil; kare yeniden boyutlandırılıp
    karşılaştırılıyor. Reddetmek pencereyi sessizce kanıtsız bırakırdı."""
    first = _write(tmp_path / "a.png", np.full((80, 80), 100, np.uint8))
    second = _write(tmp_path / "b.png", np.full((40, 60), 200, np.uint8))
    raw = raw_scores([first, second])
    assert raw[1] is not None
    assert raw[1][0] > 0.0


def test_an_empty_frame_list_yields_nothing(tmp_path):
    assert raw_scores([]) == []
    assert frame_energy([]) == []
    assert window_energy([]) is None


def test_a_window_with_fewer_than_two_frames_has_no_energy(tmp_path):
    """Tek kareden değişim çıkarılamaz; `None` 'sıfır hareket' DEĞİL,
    'kanıt yok' demek. Çağıran taraf ikisini ayırt edebilmeli."""
    assert window_energy(raw_scores(_still(tmp_path, 1))) is None
    assert window_energy([None]) is None
    assert window_energy([None, 0.0]) == 0.0


def test_window_energy_averages_the_usable_scores_only():
    assert window_energy([None, 0.2, 0.4, None, 0.6]) == pytest.approx(0.4)


# -- döngüye takılan kapanış --------------------------------------------------

def test_build_motion_for_scores_each_window_from_its_own_frames(tmp_path):
    """Üç pencerelik bir koşu: hareket yalnız ortadaki pencerede.

    Ölçülen arızanın birebir minyatürü — W2 en yüksek enerjiyi almalı."""
    paths = []
    for i in range(9):
        image = np.full((100, 100), 80, np.uint8)
        if 3 <= i < 6:                     # yalnız orta pencerede kütle geziyor
            image[20:80, 5 * i:5 * i + 40] = 230
        paths.append(_write(tmp_path / f"w{i:02d}.png", image))

    motion_for = build_motion_for([float(i) for i in range(9)], paths)
    assert motion_for is not None
    energies = [motion_for(_observations([0.0, 1.0, 2.0])),
                motion_for(_observations([3.0, 4.0, 5.0])),
                motion_for(_observations([6.0, 7.0, 8.0]))]
    assert energies[1] > energies[0]
    assert energies[1] > energies[2]


def test_build_motion_for_reads_every_frame_exactly_once(tmp_path, monkeypatch):
    """Enerji koşu başına BİR kez hesaplanıyor.

    Pencere başına hesaplansaydı iki şey birden bozulurdu: maliyet kare
    sayısıyla değil pencere sayısıyla çarpılırdı ve normalizasyon pencere
    içine hapsolurdu — her pencerenin zirvesi 1,0 olur, pencereler arası
    sıralama anlamını yitirirdi."""
    import gozcu.motion as motion

    paths = _still(tmp_path, 6)
    reads = []
    real = motion.cv2.imread
    monkeypatch.setattr(motion.cv2, "imread",
                        lambda path, flag: reads.append(path) or real(path, flag))

    motion_for = build_motion_for([float(i) for i in range(6)], paths)
    assert motion_for is not None
    for _ in range(4):
        motion_for(_observations([0.0, 1.0]))
    assert len(reads) == 6


def test_build_motion_for_gives_up_when_no_frame_is_usable(tmp_path):
    """Hiçbir kare okunamıyorsa kanıt yok; `None` dönüyor ve çağıran taraf
    periyodik nöbete geri düşüyor."""
    missing = [tmp_path / f"yok{i}.png" for i in range(5)]
    assert build_motion_for([float(i) for i in range(5)], missing) is None


def test_build_motion_for_needs_at_least_two_aligned_frames(tmp_path):
    assert build_motion_for([], []) is None
    assert build_motion_for([0.0], _still(tmp_path, 1)) is None
    # Hizasız girdi sessizce yanlış eşleşmektense hiç kurulmuyor.
    assert build_motion_for([0.0, 1.0, 2.0], _still(tmp_path, 2)) is None


def test_a_window_whose_timestamps_are_unknown_has_no_energy(tmp_path):
    """Pencerenin damgaları kare tablosunda yoksa uydurulmuyor: `None`."""
    motion_for = build_motion_for([0.0, 1.0], _still(tmp_path, 2))
    assert motion_for is not None
    assert motion_for(_observations([99.0, 100.0])) is None


# -- hücre bazlı anomali (25 Ağustos) -----------------------------------------
#
# Küresel ortalama, yoğun bir fabrika zemininde olayı sıralayamıyor: hareket
# her yerde yüksek ve tek kişilik bir savrulma toplam kütlede yuvarlama hatası.
# Ölçüldü: kaza saniyesi 116 karenin 53.'sü. Olayı ayırt eden şey mutlak
# hareket miktarı değil, **o bölgenin kendi normalinden sapması.**

import numpy as np

from gozcu.motion import (cell_absdiff, top_k_mean, window_energy,
                          zscore_anomaly)


class TestCellAbsdiff:
    def test_shape_matches_the_grid(self):
        a = np.zeros((60, 80), dtype=np.uint8)
        b = np.zeros((60, 80), dtype=np.uint8)
        assert cell_absdiff(a, b, grid=(6, 8)).shape == (6, 8)

    def test_identical_frames_score_zero(self):
        a = np.full((60, 80), 7, dtype=np.uint8)
        assert cell_absdiff(a, a, grid=(6, 8)).max() == 0.0

    def test_change_is_localised_to_its_cell(self):
        """Tek bir hücredeki değişim yalnız o hücreyi yükseltmeli —
        küresel ortalamanın yapamadığı şey tam olarak bu."""
        a = np.zeros((60, 80), dtype=np.uint8)
        b = a.copy()
        b[0:10, 0:10] = 255
        cells = cell_absdiff(a, b, grid=(6, 8))
        assert cells[0, 0] > 0
        assert cells[5, 7] == 0.0

    def test_mismatched_shapes_are_resized_not_refused(self):
        a = np.zeros((60, 80), dtype=np.uint8)
        b = np.zeros((30, 40), dtype=np.uint8)
        assert cell_absdiff(a, b, grid=(6, 8)).shape == (6, 8)


class TestZscoreAnomaly:
    def test_a_quiet_run_has_no_spike(self):
        cells = [np.full((2, 2), 1.0) for _ in range(20)]
        scores = zscore_anomaly(cells, baseline=5)
        assert all(s is None or s < 1.0 for s in scores)

    def test_a_localised_spike_is_found(self):
        cells = [np.full((2, 2), 1.0) for _ in range(20)]
        cells[15] = np.array([[1.0, 1.0], [1.0, 40.0]])
        scores = zscore_anomaly(cells, baseline=5)
        assert scores[15] == max(s for s in scores if s is not None)

    def test_a_busy_cell_does_not_mask_a_quiet_cell_s_anomaly(self):
        """Sürekli hareketli bir hücre (çalışan makine), sakin bir hücredeki
        ani sapmayı bastırmamalı. Küresel ortalamanın kaybettiği tam bu."""
        cells = []
        for _ in range(20):
            cells.append(np.array([[50.0, 1.0]]))     # sol hücre hep meşgul
        cells[15] = np.array([[50.0, 9.0]])           # sağ hücrede sapma
        scores = zscore_anomaly(cells, baseline=5)
        assert scores[15] == max(s for s in scores if s is not None)

    def test_frames_before_the_baseline_have_no_score(self):
        cells = [np.full((2, 2), 1.0) for _ in range(10)]
        scores = zscore_anomaly(cells, baseline=4)
        assert scores[0] is None
        assert len(scores) == len(cells)

    def test_none_entries_survive_as_none(self):
        cells = [np.full((2, 2), 1.0) for _ in range(10)]
        cells[3] = None
        scores = zscore_anomaly(cells, baseline=2)
        assert scores[3] is None


class TestTopKMean:
    def test_mean_of_the_largest_k(self):
        assert top_k_mean([1.0, 9.0, 5.0, 2.0], k=2) == 7.0

    def test_k_larger_than_the_list_uses_everything(self):
        assert top_k_mean([2.0, 4.0], k=10) == 3.0

    def test_empty_is_none(self):
        assert top_k_mean([], k=3) is None

    def test_nones_are_ignored(self):
        assert top_k_mean([None, 8.0, None, 2.0], k=1) == 8.0

    def test_all_none_is_none(self):
        assert top_k_mean([None, None], k=1) is None


class TestWindowEnergyTopK:
    def test_a_short_event_is_not_diluted_by_a_calm_window(self):
        """`window_energy`'nin eski hâli ortalamaydı ve kendi docstring'i
        bedeli yazıyordu: 10 saniyelik sakin bir pencerede 1 saniyelik olay
        seyrelir. Manşet olayımız tam o bedeli ödedi."""
        calm = [0.1] * 9 + [1.0]
        assert window_energy(calm) > 0.3

    def test_a_uniformly_calm_window_stays_low(self):
        assert window_energy([0.1] * 10) < 0.2

    def test_no_evidence_is_none(self):
        assert window_energy([None, None]) is None


def test_build_motion_for_carries_the_frame_series_for_the_console(tmp_path):
    """Kapanış, hesapladığı kare skorlarını dışarı da veriyor.

    Konsolun piksel entropisi grafiği (Görev raporu §1.B) tam olarak bu
    seriyi çiziyor. İkinci bir geçişle yeniden hesaplanamazdı: normalizasyon
    koşuya göreli, yani karelerin bir alt kümesinden çıkan skorlar bu
    koşununkiyle AYNI ölçekte olmaz ve grafik döngünün gördüğünden başka bir
    şey gösterirdi.
    """
    paths = []
    for i in range(8):
        image = np.full((120, 120), 90, np.uint8)
        image[30:90, (10 if i < 5 else 60):(70 if i < 5 else 120)] = 210
        paths.append(_write(tmp_path / f"c{i:02d}.png", image))
    timestamps = [float(i) for i in range(8)]

    motion_for = build_motion_for(timestamps, paths)

    assert motion_for.timestamps == timestamps
    assert len(motion_for.scores) == len(paths)
    # Hareketin olduğu kare en yüksek skoru taşıyor — seri döngünün
    # nişan aldığı skorların ta kendisi, ayrı bir hesap değil.
    measured = [score for score in motion_for.scores if score is not None]
    assert measured
    assert motion_for.scores.index(max(measured)) == 5


# -- kare entropisi (konsol grafiği) ------------------------------------------
#
# `frame_entropy` `_grey`/`_histogram`'ın üstüne binen üçüncü bir okuma —
# kareyi ikinci kez diskten okumuyor, yalnız zaten hesaplanan olasılık
# dağılımının Shannon entropisini alıyor.

class TestFrameEntropy:
    def test_is_aligned_with_the_frames(self, tmp_path):
        """Hizalama önemli: konsol entropiyi zaman damgasıyla eşliyor,
        listeler kayarsa grafik yanlış saniyeye yanlış değeri çizer."""
        paths = _still(tmp_path, 5)
        scores = frame_entropy(paths)
        assert len(scores) == 5

    def test_is_low_for_a_flat_frame_high_for_noise(self, tmp_path):
        """Tek renkli bir kare: histogramın tek kovası 1,0, entropi 0,0.
        Gürültülü bir kare: piksel değerleri dağılmış, entropi belirgin
        şekilde daha yüksek."""
        flat = _write(tmp_path / "flat.png",
                      np.full((100, 100), 120, np.uint8))
        rng = np.random.default_rng(0)
        noisy = _write(tmp_path / "noisy.png",
                       rng.integers(0, 256, (100, 100), dtype=np.uint8))
        scores = frame_entropy([flat, noisy])
        assert scores[0] == pytest.approx(0.0, abs=1e-9)
        assert scores[1] > 4.0

    def test_is_none_for_an_unreadable_frame(self, tmp_path):
        """`_grey`'in kendi sözleşmesi: okunamayan kare `None` — 'sıfır
        entropi' değil 'kanıt yok'."""
        broken = tmp_path / "bozuk.png"
        broken.write_bytes(b"bu bir png degil")
        paths = _still(tmp_path, 2)
        paths.insert(1, broken)
        scores = frame_entropy(paths)
        assert scores[1] is None
        assert scores[0] is not None and scores[2] is not None
