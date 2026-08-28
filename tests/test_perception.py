"""Algı katmanı — takip **zenginleştirir**, süzmez.

Bu dosyanın koruduğu tek cümle: *tespit kayıttır.* BoTSORT 1 fps'te kimlik
atayamıyor (ölçüldü: raf çökmesi klibinde 6 kutu, 0 kimlik) ve eski kod
kimliksiz kutuyu atıyordu — yani takip katmanının başarısızlığı tespit
katmanının kanıtını siliyordu.

Yeni sözleşme iki parçalı ve ikisi de burada sınanıyor:

- `track_video` **bütün** kutuları veriyor; kimlik varsa iliştiriyor.
- `compute_signals` kimlik isteyen hesapları (hız, kaybolan iz) kimliği
  olanlarla sınırlıyor, kimlik istemeyeni (kişi sayısı) sınırlamıyor.

Ve iki sessiz tuzak: `None` anahtarlı sözlük çakışması (hayalet hız) ile
`kaybolan=[None]`'ın yönlendiricinin özetine sızması.
"""

from unittest.mock import patch

from gozcu.output.adapter import to_observation
from gozcu.perception.signals import FrameSignals, compute_signals
from gozcu.perception.detect import DetectedObject
from gozcu.perception.track import TrackedObject, track_video


# -- tespit ikizi -------------------------------------------------------------
#
# 25 Ağustos: bu ikiz `model.track()`'i taklit ediyordu. Artık öyle bir çağrı
# YOK — `gozcu.track` tespiti `detect_objects` ile alıyor ve kimlikleri ayrı
# bir ilişkilendiriciden iliştiriyor (bkz. `gozcu/track.py`). İkiz de o iki
# yeni dikişe taşındı; sınanan davranış aynı: **kutu asla elenmez.**

class _Box:
    """Bir kareden çıkan tek tespit; `track_id` ilişkilendiricinin cevabı."""

    def __init__(self, class_id=0, confidence=0.5, xyxy=(0, 0, 10, 10),
                 track_id=None):
        self.class_name = {0: "person", 1: "forklift"}[class_id]
        self.confidence = confidence
        self.bbox = tuple(xyxy)
        self.track_id = track_id


def _run_track(frames_of_boxes):
    """Sahte tespit + sahte ilişkilendirici ile `track_video`.

    İkisi de ayrı ayrı patch'leniyor çünkü ayrılmalarının kendisi düzeltmenin
    ta kendisi: tespit kayıt, kimlik açıklama.
    """
    detected = [[DetectedObject(class_name=b.class_name,
                                confidence=b.confidence, bbox=b.bbox)
                 for b in boxes] for boxes in frames_of_boxes]
    ids_per_frame = [[b.track_id for b in boxes] for boxes in frames_of_boxes]

    def fake_associator():
        counter = {"i": 0}

        def associate(boxes, state):
            ids = ids_per_frame[counter["i"]]
            counter["i"] += 1
            return ids
        return associate

    with (patch("gozcu.perception.track.detect_objects",
                side_effect=lambda path: detected.pop(0)),
          patch("gozcu.perception.track._default_associator", fake_associator)):
        return track_video([f"frame_{i}.jpg"
                            for i in range(len(frames_of_boxes))])


# -- takip süzgeç değil -------------------------------------------------------

def test_a_box_without_a_track_id_survives_tracking():
    """Eski kod `if box.id is None: continue` diyordu ve ölçülen sonuç şuydu:
    6 kutu bulundu, 0'ı ajan katmanına ulaştı."""
    tracked = _run_track([[_Box(class_id=1, confidence=0.31, xyxy=(1, 2, 3, 4),
                                track_id=None)]])
    assert len(tracked[0]) == 1
    only = tracked[0][0]
    assert only.track_id is None
    assert only.class_name == "forklift"
    assert only.bbox == (1, 2, 3, 4)


def test_tracking_still_attaches_the_id_when_it_has_one():
    """Zenginleştirme kaybolmuyor: kimlik varsa taşınıyor."""
    tracked = _run_track([[_Box(track_id=7)]])
    assert tracked[0][0].track_id == 7


def test_tracked_and_untracked_boxes_come_back_from_the_same_frame():
    tracked = _run_track([[_Box(track_id=3), _Box(track_id=None)]])
    assert [obj.track_id for obj in tracked[0]] == [3, None]


def test_the_untracked_box_reaches_the_agent_layer_through_the_adapter():
    """`models.Detection.track_id` zaten `int | None`; adaptör süzmemeli."""
    observation = to_observation(
        1.0,
        [TrackedObject(class_name="person", confidence=0.4, bbox=(0, 0, 4, 4),
                       track_id=None)],
        FrameSignals(person_count=1))
    assert len(observation.detections) == 1
    assert observation.detections[0].track_id is None


# -- kimlik isteyen / istemeyen hesaplar --------------------------------------

def _person(track_id=None, bbox=(0, 0, 10, 10)):
    return TrackedObject(class_name="person", confidence=0.5, bbox=bbox,
                         track_id=track_id)


def test_person_count_counts_people_without_a_track_id():
    """Kişi sayısı kimlik istemiyor: kimliksiz bir insan da karede durur."""
    signals = compute_signals([[_person(), _person()]], [0.0])
    assert signals[0].person_count == 2


def test_person_count_delta_follows_untracked_people_too():
    signals = compute_signals([[_person()], [_person(), _person()]],
                              [0.0, 1.0])
    assert [s.person_count for s in signals] == [1, 2]
    assert signals[1].person_count_delta == 1


def test_velocities_ignore_objects_without_a_track_id():
    """Hız "aynı nesne iki karede nerede" sorusudur; kimliksiz kutuyla
    cevaplanamaz."""
    signals = compute_signals(
        [[_person(bbox=(0, 0, 10, 10))], [_person(bbox=(100, 0, 110, 10))]],
        [0.0, 1.0])
    assert signals[1].velocities == {}


def test_two_untracked_objects_in_one_frame_do_not_collide_into_one_entry():
    """`{obj.track_id: obj}` naif hâliyle `None` anahtarlarını ÇAKIŞTIRIR.

    Çakışma sessiz: karedeki bütün kimliksiz nesneler tek girdiye iner ve
    iki kare arasında **farklı fiziksel nesneler** arasında hayalet bir hız
    hesaplanır. Burada iki kimliksiz nesne yer değiştiriyor; süzgeç
    kalkarsa `velocities[None]` belirir.
    """
    frames = [[_person(bbox=(0, 0, 10, 10)), _person(bbox=(500, 0, 510, 10))],
              [_person(bbox=(500, 0, 510, 10)), _person(bbox=(0, 0, 10, 10))]]
    signals = compute_signals(frames, [0.0, 1.0])
    assert signals[1].velocities == {}
    assert None not in signals[1].velocities
    assert signals[1].person_count == 2


def test_vanished_tracks_never_contain_none():
    """`kaybolan=[None]` yönlendiricinin özetine düşer ve model olmayan bir
    izin kaybolduğunu okur."""
    frames = [[_person(track_id=None), _person(track_id=4)],
              [_person(track_id=4)]]
    signals = compute_signals(frames, [0.0, 1.0])
    assert signals[1].vanished_tracks == []
    assert None not in signals[1].vanished_tracks


def test_a_real_track_still_vanishes_when_it_leaves_the_frame():
    """Süzgeç kaybolan iz tespitini öldürmüyor — sadece `None`'ı dışarıda
    tutuyor."""
    signals = compute_signals([[_person(track_id=9)], [_person(track_id=None)]],
                              [0.0, 1.0])
    assert signals[1].vanished_tracks == [9]


def test_a_tracked_object_still_gets_its_velocity():
    signals = compute_signals(
        [[_person(track_id=2, bbox=(0, 0, 10, 10))],
         [_person(track_id=2, bbox=(0, 8, 10, 18))]],
        [0.0, 2.0])
    assert signals[1].velocities == {2: 4.0}


# -- hız birimi: piksel/saniye sahneye göre yalan söylüyordu (26 Ağustos) -----
#
# Ölçüldü (k04, 98.8 sn klip): genel medyan hız 7 px/s, ama piksel bir sahne
# birimi değil bir ÇÖZÜNÜRLÜK birimi. Kare GENİŞLİĞİ başına normalize etmek
# sahne/çözünürlükten bağımsız bir sayı veriyor. `frame_size` verilmezse eski
# piksel davranışı aynen kalıyor — bir ölçek UYDURMAK piksel kadar yanlış
# olurdu.

def test_velocity_is_normalized_to_frame_widths_per_second_when_frame_size_is_given():
    """Bilinen bir piksel mesafesi, bilinen bir kare genişliğine ve `dt`ye
    bölününce tam olarak beklenen kare-genişliği/saniye değerini vermeli."""
    frames = [[_person(track_id=1, bbox=(0, 0, 10, 10))],
             [_person(track_id=1, bbox=(90, 0, 100, 10))]]  # 90 px sağa
    signals = compute_signals(frames, [0.0, 2.0], frame_size=(900, 600))
    # 90 px / 2.0 s = 45 px/s; 45 / 900 px genişlik = 0.05 kare-genişliği/s
    assert signals[1].velocities == {1: 0.05}


def test_velocity_stays_in_pixels_per_second_without_a_frame_size():
    """`frame_size=None`'da eski piksel/saniye davranışı korunuyor — bir
    ölçek uydurmak yerine dürüstçe eski birime düşülüyor."""
    frames = [[_person(track_id=1, bbox=(0, 0, 10, 10))],
             [_person(track_id=1, bbox=(90, 0, 100, 10))]]
    signals = compute_signals(frames, [0.0, 2.0], frame_size=None)
    assert signals[1].velocities == {1: 45.0}


# -- kare hızı yükseldi: kaybolma artık ısrar ister ---------------------------
#
# 1 fps'te "önceki karede vardı, bu karede yok" makul bir kaybolma tanımıydı.
# 5 fps'te aynı tanım 200 ms'lik bir kesintiyi kaybolma sayar ve yönlendirici
# özetini sahte kaybolmalarla doldurur. Eşik artık SANİYE cinsinden.

def test_a_single_frame_dropout_is_not_a_vanish_at_high_fps():
    """5 fps'te bir kare yokluk (200 ms) kaybolma DEĞİL."""
    frames = [
        [TrackedObject("person", 0.5, (0, 0, 10, 10), track_id=1)],
        [],                                        # tek kare yokluk
        [TrackedObject("person", 0.5, (0, 0, 10, 10), track_id=1)],
    ]
    ts = [0.0, 0.2, 0.4]
    signals = compute_signals(frames, ts, vanish_after_s=1.0)
    assert all(not s.vanished_tracks for s in signals)


def test_a_sustained_absence_is_still_a_vanish():
    """Eşiği aşan yokluk kaybolmadır — sinyal susturulmuyor, geciktiriliyor."""
    frames = [[TrackedObject("person", 0.5, (0, 0, 10, 10), track_id=1)]]
    frames += [[] for _ in range(8)]
    ts = [i * 0.2 for i in range(9)]
    signals = compute_signals(frames, ts, vanish_after_s=1.0)
    assert any(1 in s.vanished_tracks for s in signals)


def test_a_track_is_reported_vanished_only_once():
    """Aynı iz her karede yeniden 'kayboldu' diye bildirilmemeli."""
    frames = [[TrackedObject("person", 0.5, (0, 0, 10, 10), track_id=1)]]
    frames += [[] for _ in range(12)]
    ts = [i * 0.2 for i in range(13)]
    signals = compute_signals(frames, ts, vanish_after_s=1.0)
    assert sum(s.vanished_tracks.count(1) for s in signals) == 1


def test_vanish_threshold_is_in_seconds_not_frames():
    """Aynı yokluk süresi, farklı kare hızlarında aynı sonucu vermeli."""
    def run(fps):
        frames = [[TrackedObject("person", 0.5, (0, 0, 10, 10), track_id=1)]]
        n = int(2.0 * fps)
        frames += [[] for _ in range(n)]
        ts = [i / fps for i in range(n + 1)]
        return any(1 in s.vanished_tracks
                   for s in compute_signals(frames, ts, vanish_after_s=1.0))

    assert run(1.0) is True
    assert run(5.0) is True


# -- D5: içeri kaybolma — kazanın kendi imzası --------------------------------
#
# "Makineye kapılan işçi" sinyal olarak şudur: hızlanan ve sonra kare
# kenarına DEĞMEDEN kaybolan bir iz. Kenardan çıkan bir iz sadece kadrajı
# terk etmiştir; içeride kaybolan bir iz bir şeyin İÇİNE girmiştir.

def _tracked_person(track_id, bbox):
    return TrackedObject("person", 0.5, bbox, track_id=track_id)


def test_a_track_leaving_by_the_edge_is_not_an_interior_vanish():
    frames = [[_tracked_person(1, (0, 100, 30, 200))]]          # sol kenara yapışık
    frames += [[] for _ in range(4)]
    signals = compute_signals(frames, [i * 0.5 for i in range(5)],
                              vanish_after_s=1.0, frame_size=(896, 672))
    assert any(1 in s.vanished_tracks for s in signals)
    assert all(not s.interior_vanished_tracks for s in signals)


def test_a_track_vanishing_mid_frame_is_an_interior_vanish():
    """Üç şartın hepsi: yerleşmiş iz + kadraj ortası + eşiği aşan yokluk."""
    frames = [[_tracked_person(1, (400, 300, 460, 420))] for _ in range(4)]
    frames += [[] for _ in range(4)]
    signals = compute_signals(frames, [i * 0.5 for i in range(8)],
                              vanish_after_s=1.0, frame_size=(896, 672),
                              min_established_s=1.0)
    assert any(1 in s.interior_vanished_tracks for s in signals)


def test_a_track_seen_only_briefly_is_not_an_interior_vanish():
    """Bir karede parlayıp sönen kutu iz sayılmaz, dolayısıyla kaybolamaz.

    Bu şart olmadan sinyal kullanılamıyor: ölçüldü, 347 karelik koşuda
    614 "içeri kaybolma" — saniyede ~2, yani gürültü. Sebep tespit değil,
    iz parçalanması (~25 kişi için 500'den fazla kimlik).
    """
    frames = [[_tracked_person(1, (400, 300, 460, 420))]]       # tek kare
    frames += [[] for _ in range(6)]
    signals = compute_signals(frames, [i * 0.5 for i in range(7)],
                              vanish_after_s=1.0, frame_size=(896, 672),
                              min_established_s=1.0)
    assert any(1 in s.vanished_tracks for s in signals)          # yine kayboldu
    assert all(not s.interior_vanished_tracks for s in signals)  # ama iz değildi


def test_interior_vanish_needs_the_frame_size():
    """Kadraj boyutu bilinmiyorsa kenar da bilinemez. Tahmin etmek yerine
    sinyal üretilmiyor — yanlış bir 'içeri kayboldu' kaza uydurur."""
    frames = [[_tracked_person(1, (400, 300, 460, 420))]]
    frames += [[] for _ in range(4)]
    signals = compute_signals(frames, [i * 0.5 for i in range(5)],
                              vanish_after_s=1.0, frame_size=None)
    assert all(not s.interior_vanished_tracks for s in signals)
    # Sıradan kaybolma yine bildiriliyor — kadraj boyutu ona gerekmiyor.
    assert any(1 in s.vanished_tracks for s in signals)


def test_interior_vanish_is_a_subset_of_vanished():
    frames = [[_tracked_person(1, (400, 300, 460, 420))]]
    frames += [[] for _ in range(4)]
    signals = compute_signals(frames, [i * 0.5 for i in range(5)],
                              vanish_after_s=1.0, frame_size=(896, 672))
    for s in signals:
        assert set(s.interior_vanished_tracks) <= set(s.vanished_tracks)
