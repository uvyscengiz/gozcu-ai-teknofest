"""Yerel hareket triyajı — pahalı bakışı nereye harcayacağımızı seçen katman.

Bu modül **hiçbir model çağırmıyor**: ne ağ geçidi, ne VLM, ne YOLO. Yaptığı
tek şey ardışık kareleri birbirinden çıkarmak. Ölçüldü (25 Ağustos, 896 piksel
genişliğinde kare, raf çökmesi klibi): 1,9 ms/kare, 23 karelik klibin tamamı
44 ms. Karşılaştırma için aynı koşuda tek bir görü çağrısı 3.493 ms sürdü —
triyajın tamamı o tek çağrının yüzde biri kadar.

## Neden var

`DecisionLoop` tabandan geçemeyen pencerelerin her `FORCED_SAMPLE_EVERY`'incisini
görü kademesine gönderiyordu. Bütçe doğruydu, NİŞAN yanlıştı: hangi
pencerenin bakılacağını bir sayaç seçiyordu, kanıt değil.

Ölçülen arıza (`forklift-compilation--N9bG-sOU6LE-k03.mp4`, depoda raf
çökmesi, sıfır YOLO tespiti — yani taban her yerde başarısız):

    saniye başına kare farkı enerjisi  t=11–13 s'de zirve (9,34 / 9,09 / 9,13)
    klip ortalaması                     3,75
    pencere ortalamaları                W1 2,48 · W2 5,45 · W3 1,59

Olay W2'de. Sayaç W1'i seçti. Tek pahalı bakış yanlış yere harcandı ve koşu
"Kayda değer olay tespit edilmedi." dedi.

## İki sinyal, çünkü tek sinyal kör

- **Kare farkı (mutlak fark ortalaması, gri tonda)** — yer değiştiren kütleyi
  görür: hareket, çökme, ani devrilme. Sahnenin tonu kaydığında neredeyse
  hiçbir şey söylemez.
- **Histogram uzaklığı (64 kova, L1)** — tam tersi: piksellerin yeri değişince
  hiç kıpırdamaz, ama sahnenin ton dağılımı kayınca (yangın parıltısı, duman
  pusu, ışık değişimi) zirveye çıkar.

`data/clips/yangin` bu veri kümesinde etiketli bir kategori ve yangının ne
sınıfı, ne izi, ne hızı vardır — yalnız görünür. İkinci sinyal onun için var.

## Birleşim kuralı: koşu içi normalizasyon, sonra eleman bazında en büyük

Her sinyal kendi koşusundaki zirvesine bölünüyor, sonra ikisinin büyüğü
alınıyor. Sabit bir ölçek (255 ve 2) denenmedi değil, ama tipik videoda kare
farkı 255'in yüzde birkaçında gezerken histogram uzaklığı 2'nin onda
birlerinde geziyor: sabit ölçekte histogram terimi her pencerede kazanır ve
kare farkı hiç konuşamaz. Koşu içi normalizasyon ikisini karşılaştırılabilir
kılan şey.

En büyük — toplam ya da ortalama değil — çünkü kural "ikisinden BİRİ ötüyorsa
bu pencere ilginçtir". Toplamda güçlü bir histogram sinyali zayıf bir kare
farkıyla seyreltilirdi.

Bedeli dürüstçe yazılsın: `max` her iki sinyalin yanlış pozitiflerini de
devralır. Kamera sarsıntısı kare farkını, otomatik pozlama histogramı
zıplatır; ikisi de gerçek olay değildir ve triyaj onları olay sanabilir.

## Sınır: normalizasyon koşuya göreli

Skorlar mutlak değil **göreli**. Baştan sona durgun bir klipte de bir kare
1,0 alır — o karede bir şey olduğu için değil, koşudaki en yüksek gürültü
orada olduğu için. Bu sıralama için doğru (triyajın işi budur), mutlak bir
eşik için yanlış. Kimse buradan "enerji > 0,8 ise alarm" kuralı çıkarmasın.

## Hiçbir arıza istisna atmaz

Eksik dosya, bozuk dosya, tek kare, boş liste, farklı boyut — hepsi `None`'a
düşüyor. Çağıran taraf `None`'ı "kanıt yok" diye okuyup eski periyodik
nöbetine geri dönebiliyor. Triyaj katmanı hiçbir koşuyu düşürmemeli: bu
katman koşunun sigortası değil, nişancısı.
"""

from collections.abc import Callable, Sequence
from pathlib import Path

import cv2
import numpy as np

from gozcu.models import Observation

__all__ = ["HIST_BINS", "build_motion_for", "combine", "frame_energy",
           "raw_scores", "window_energy"]

#: Histogram kova sayısı. 64 kova = 4 gri seviye genişliğinde kova: JPEG
#: nicemleme gürültüsünü yutacak kadar geniş, bir ton kaymasını kaçırmayacak
#: kadar dar.
HIST_BINS = 64

#: Zaman damgası eşlemesinin yuvarlama hassasiyeti. Kare damgaları `i / fps`
#: ile üretiliyor ve gözleme aynen taşınıyor, yani eşitlik zaten tam; yuvarlama
#: yalnız kayan nokta gösteriminin ileride değişmesine karşı bir yastık.
_TS_PRECISION = 6


def _grey(path) -> np.ndarray | None:
    """Kareyi gri tonda okur; okunamıyorsa `None`.

    `cv2.imread` olmayan dosyada da bozuk dosyada da istisna atmaz, `None`
    döndürür — ama yolun tipi beklenmedik olursa atabiliyor, o yüzden yine de
    sarılı.
    """
    try:
        image = cv2.imread(str(Path(path)), cv2.IMREAD_GRAYSCALE)
    except Exception:                       # noqa: BLE001 — triyaj asla patlamaz
        return None
    if image is None or image.size == 0:
        return None
    return image


def _histogram(image: np.ndarray) -> np.ndarray:
    """Toplamı 1 olan gri ton histogramı."""
    counts = cv2.calcHist([image], [0], None, [HIST_BINS], [0, 256]).ravel()
    total = float(counts.sum())
    return counts / total if total > 0 else counts


def _pair(previous: np.ndarray, current: np.ndarray) -> tuple[float, float]:
    """İki kare arasındaki (kare farkı, histogram uzaklığı) ikilisi.

    Boyut değişimi bir arıza değil: kare öncekinin boyutuna indiriliyor.
    Reddetmek pencereyi sessizce kanıtsız bırakır ve o pencere hiç bakılmadan
    geçerdi.
    """
    if previous.shape != current.shape:
        current = cv2.resize(current, (previous.shape[1], previous.shape[0]),
                             interpolation=cv2.INTER_AREA)
    absdiff = float(np.mean(cv2.absdiff(previous, current)))
    histogram = float(np.abs(_histogram(previous) - _histogram(current)).sum())
    return absdiff, histogram


def raw_scores(frame_paths: Sequence) -> list[tuple[float, float] | None]:
    """Kare başına ham `(kare farkı, histogram uzaklığı)`; hizalı liste.

    Uzunluk girdiyle aynı. `None` üç durumda: ilk kare (karşılaştıracağı
    önceki kare yok), okunamayan kare, ve okunamayan bir karenin hemen
    ardındaki kare. `None` "sıfır hareket" DEĞİL, "kanıt yok" demek — ikisini
    ayırt edemeyen bir çağıran, kör bir pencereyi sakin bir pencere sanır.

    Her kare **bir kez** okunuyor: önceki karenin dizisi elde tutuluyor.
    """
    scores: list[tuple[float, float] | None] = []
    previous: np.ndarray | None = None
    for path in frame_paths:
        current = _grey(path)
        if previous is None or current is None:
            scores.append(None)
        else:
            try:
                scores.append(_pair(previous, current))
            except Exception:               # noqa: BLE001 — triyaj asla patlamaz
                scores.append(None)
        previous = current
    return scores


def combine(raw: Sequence[tuple[float, float] | None]) -> list[float | None]:
    """İki sinyali koşu içinde normalize edip eleman bazında en büyüğünü alır.

    Zirve sıfırsa (hiç değişim yok) bölme yapılmıyor ve skor 0,0 kalıyor.
    "Zirve 0 ise hepsi 1,0" demek ölümcül olurdu: durgun bir klip aniden en
    yüksek enerjili klip gibi görünür ve triyaj hiçbir şeyi sıralayamazdı.
    """
    usable = [pair for pair in raw if pair is not None]
    top_absdiff = max((pair[0] for pair in usable), default=0.0)
    top_histogram = max((pair[1] for pair in usable), default=0.0)

    combined: list[float | None] = []
    for pair in raw:
        if pair is None:
            combined.append(None)
            continue
        absdiff = pair[0] / top_absdiff if top_absdiff > 0 else 0.0
        histogram = pair[1] / top_histogram if top_histogram > 0 else 0.0
        combined.append(max(absdiff, histogram))
    return combined


def frame_energy(frame_paths: Sequence) -> list[float]:
    """Kare başına değişim skoru, 0..1 aralığında, girdiyle hizalı.

    `raw_scores` + `combine`'ın düz hâli: `None` konumları 0,0'a düşüyor.
    Kanıtsız bir konumu sıfırdan ayırt etmesi gereken çağıran `raw_scores`
    kullanmalı — bu fonksiyon kolaylık için var, karar için değil.
    """
    return [0.0 if score is None else score
            for score in combine(raw_scores(frame_paths))]


def window_energy(scores: Sequence[float | None]) -> float | None:
    """Bir pencereye düşen kare skorlarının toplu değeri; kanıt yoksa `None`.

    **Ortalama, en büyük değil.** Ölçüm pencere ORTALAMALARIYLA yapıldı
    (W1 2,48 · W2 5,45 · W3 1,59) ve olayı bulan buydu; ortalama tek karelik
    bir sıkıştırma artefaktına ya da anlık parlamaya da dayanıklı.

    Bedeli var: 10 saniyelik sakin bir pencerenin içindeki 1 saniyelik bir
    olay ortalamada seyrelir. En büyüğü almak onu kurtarırdı ama her sıkıştırma
    zıplamasını da olay sayardı. Ölçülen kanıt ortalamadan yana, tercih bu
    yüzden ortalama.
    """
    usable = [score for score in scores if score is not None]
    if not usable:
        return None
    return sum(usable) / len(usable)


def build_motion_for(
    timestamps: Sequence[float],
    frame_paths: Sequence,
) -> Callable[[list[Observation]], float | None] | None:
    """`DecisionLoop`'a takılacak `motion_for` kapanışını üretir.

    Enerji burada, **koşu başına bir kez** hesaplanıyor; dönen kapanış yalnız
    hazır skorları topluyor. Pencere başına hesaplansaydı iki şey birden
    bozulurdu: maliyet pencere sayısıyla çarpılırdı ve normalizasyon pencere
    içine hapsolurdu — her pencerenin zirvesi 1,0 olur, pencereler arası
    sıralama anlamını yitirirdi.

    Hiç kullanılabilir kare yoksa `None` dönüyor: döngü bunu görüp eski
    periyodik nöbetine geri düşüyor.
    """
    timestamps = list(timestamps)
    frame_paths = list(frame_paths)
    if len(timestamps) != len(frame_paths) or len(frame_paths) < 2:
        # Hizasız girdiyi sessizce eşleştirmek pencerelere yanlış enerji
        # dağıtırdı; hiç kurulmamak yanlış nişan almaktan iyidir.
        return None

    try:
        scores = combine(raw_scores(frame_paths))
    except Exception:                       # noqa: BLE001 — triyaj asla patlamaz
        return None
    if all(score is None for score in scores):
        return None

    by_ts: dict[float, list[float | None]] = {}
    for timestamp, score in zip(timestamps, scores, strict=True):
        by_ts.setdefault(round(float(timestamp), _TS_PRECISION),
                         []).append(score)

    def motion_for(window: list[Observation]) -> float | None:
        collected: list[float | None] = []
        for observation in window:
            collected.extend(
                by_ts.get(round(float(observation.ts), _TS_PRECISION), []))
        return window_energy(collected)

    return motion_for
