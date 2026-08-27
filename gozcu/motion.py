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

__all__ = ["BASELINE_S", "GRID", "HIST_BINS", "TOP_K", "anomaly_scores",
           "build_motion_for", "cell_absdiff", "combine",
           "combine_with_anomaly", "frame_energy", "raw_scores",
           "top_k_mean", "window_energy", "zscore_anomaly"]

#: Anomali ızgarası (satır, sütun). 6x8 = 48 hücre: bir insanı içine alacak
#: kadar küçük, JPEG gürültüsünü ortalayacak kadar büyük.
GRID = (6, 8)

#: Hücre temelinin kaç kareden hesaplanacağı. Saniyeye değil kareye
#: bağlanıyor çünkü `zscore_anomaly` kare dizisi üzerinde çalışıyor;
#: çağıran taraf `FRAME_FPS` ile çarpıp geçiyor.
BASELINE_S = 8.0

#: Pencere toplamasında kaç kare sayılacak. Ortalama DEĞİL: sakin bir
#: pencerede kısa bir olay ortalamada seyreliyor ve manşet olayımız tam o
#: bedeli ödedi. En büyük tek kare de değil — o her sıkıştırma zıplamasını
#: olay sayardı.
TOP_K = 3

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


def cell_absdiff(previous: np.ndarray, current: np.ndarray,
                 grid: tuple[int, int] = GRID) -> np.ndarray:
    """Izgara hücresi başına ortalama mutlak fark.

    Küresel ortalamanın kaybettiği şeyi tutuyor: **hareketin nerede
    olduğunu.** Yoğun bir fabrika zemininde toplam hareket her zaman
    yüksek; olayı ayırt eden, tek bir bölgenin kendi normalinden sapması.

    Boyut uyuşmazlığı bir arıza değil, `_pair` ile aynı davranış: kare
    öncekinin boyutuna indiriliyor.
    """
    if previous.shape != current.shape:
        current = cv2.resize(current, (previous.shape[1], previous.shape[0]),
                             interpolation=cv2.INTER_AREA)
    diff = cv2.absdiff(previous, current).astype(np.float32)
    rows, cols = grid
    height, width = diff.shape
    # Kenar hücreleri kırpmamak için bölme noktaları linspace ile alınıyor;
    # tam bölünmeyen boyutlarda son hücre biraz büyük kalıyor, bu kabul.
    row_edges = np.linspace(0, height, rows + 1).astype(int)
    col_edges = np.linspace(0, width, cols + 1).astype(int)
    out = np.zeros((rows, cols), dtype=np.float32)
    for r in range(rows):
        for c in range(cols):
            block = diff[row_edges[r]:row_edges[r + 1],
                         col_edges[c]:col_edges[c + 1]]
            out[r, c] = float(block.mean()) if block.size else 0.0
    return out


def zscore_anomaly(cell_frames, baseline: int) -> list[float | None]:
    """Kare başına "en sapmış hücrenin z-skoru"; girdiyle hizalı.

    Her hücre kendi son `baseline` karesindeki ortalama ve standart sapmaya
    göre puanlanıyor, sonra karenin skoru hücrelerin **en büyüğü**. Böylece
    sürekli çalışan bir makinenin hücresi kendi yüksek temeline göre sakin
    kalırken, sakin bir hücredeki ani sapma zirveye çıkıyor.

    `None` üç yerde: temel dolmadan önceki kareler, okunamayan kareler, ve
    temeli hiç oluşmamış hücreler. `None` "sıfır hareket" değil **"kanıt
    yok"** demek — modülün geri kalanıyla aynı sözleşme.

    Standart sapma sıfırsa (hiç değişmemiş hücre) bölme yapılmıyor: sabit
    bir hücrede en ufak kıpırtı sonsuz z-skor üretirdi.
    """
    scores: list[float | None] = []
    history: list[np.ndarray] = []
    for cells in cell_frames:
        if cells is None:
            scores.append(None)
            continue
        if len(history) < baseline:
            scores.append(None)
            history.append(cells)
            continue
        window = np.stack(history[-baseline:])
        mean = window.mean(axis=0)
        std = window.std(axis=0)
        # Sıfır sapmalı hücrede z tanımsız; taban gürültüsü kadar bir alt
        # sınır konuyor ki sabit bir hücre sonsuz skor üretmesin.
        std = np.maximum(std, 0.5)
        scores.append(float(np.max((cells - mean) / std)))
        history.append(cells)
    return scores


def top_k_mean(values, k: int = TOP_K) -> float | None:
    """En büyük `k` değerin ortalaması; kanıt yoksa `None`."""
    usable = sorted((value for value in values if value is not None),
                    reverse=True)
    if not usable:
        return None
    chosen = usable[:max(k, 1)]
    return sum(chosen) / len(chosen)


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


def _baseline_frames(total: int, requested: int | None = None) -> int:
    """Temel penceresi — koşu kısaysa kısalıyor.

    `BASELINE_S` saniyelik pencere uzun bir koşuda doğru, ama 9 karelik bir
    koşuda temel hiç dolmaz ve **bütün skorlar `None` olur**; triyaj sessizce
    yalnız histogram kanalına düşer. Bu bir testte yakalandı, canlıda
    yakalanamazdı.
    """
    if requested is None:
        from gozcu.config import FRAME_FPS
        requested = int(round(BASELINE_S * FRAME_FPS))
    return max(min(requested, total // 3), 2)


def _channels(frame_paths: Sequence, grid: tuple[int, int] = GRID):
    """Her kareyi **bir kez** okuyup iki kanalı birlikte üretir.

    İki ayrı geçiş (biri `anomaly_scores`, biri `raw_scores`) kare başına iki
    okuma demekti ve bu bir testte yakalandı. Tek geçiş hem maliyeti yarıya
    indiriyor hem de iki kanalın aynı piksellerden çıktığını garanti ediyor.
    """
    cells: list[np.ndarray | None] = []
    histograms: list[float | None] = []
    previous: np.ndarray | None = None
    for path in frame_paths:
        current = _grey(path)
        if previous is None or current is None:
            cells.append(None)
            histograms.append(None)
        else:
            try:
                cells.append(cell_absdiff(previous, current, grid))
                histograms.append(float(np.abs(
                    _histogram(previous) - _histogram(current)).sum()))
            except Exception:           # noqa: BLE001 — triyaj asla patlamaz
                cells.append(None)
                histograms.append(None)
        previous = current
    return cells, histograms


def anomaly_scores(frame_paths: Sequence,
                   grid: tuple[int, int] = GRID,
                   baseline: int | None = None) -> list[float | None]:
    """Kare başına hücre bazlı anomali skoru; girdiyle hizalı."""
    cells, _ = _channels(frame_paths, grid)
    return zscore_anomaly(cells, _baseline_frames(len(cells), baseline))


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

    **En büyük `TOP_K` karenin ortalaması** — düz ortalama değil.

    Eski hâli düz ortalamaydı ve bedelini kendi docstring'i yazıyordu: "10
    saniyelik sakin bir pencerenin içindeki 1 saniyelik bir olay ortalamada
    seyrelir." Manşet olayımız — kaza saniyesi — tam olarak o bedeli ödedi
    ve pencere tabandan geçemedi.

    En büyük tek kareyi almak da yanlış olurdu: her sıkıştırma zıplaması,
    her otomatik pozlama sıçraması olay sayılırdı. `TOP_K` ikisinin arası —
    olayın birkaç kare sürmesini istiyor, ama pencerenin tamamının
    sürmesini istemiyor.
    """
    return top_k_mean(scores, TOP_K)


def combine_with_anomaly(frame_paths: Sequence) -> list[float | None]:
    """Nişan alan skor: hücre anomalisi ve histogram kayması, koşu içinde
    normalize edilip eleman bazında en büyüğü alınarak.

    Küresel kare farkı kanalı buradan **çıkarıldı** ve yerine hücre bazlı
    z-skor kondu. Sebep ölçüldü: yoğun bir zeminde küresel büyüklük olayı
    sıralayamıyor (kaza saniyesi 116 karenin 53.'sü). Ham kare farkı hâlâ
    `raw_scores` ile erişilebilir — `run.py:_peak_frame_diff` körlük ölçüsü
    olarak onu kullanmaya devam ediyor ve o kullanım doğru.

    Histogram kanalı **kalıyor**: yangın parıltısı ve duman pusu için var,
    ve o gerekçe hâlâ geçerli — ateşin ne sınıfı, ne izi, ne hızı vardır.

    Her kare bir kez okunuyor (`_channels`).
    """
    cells, histogram = _channels(frame_paths)
    anomaly = zscore_anomaly(cells, _baseline_frames(len(cells)))

    top_anomaly = max((v for v in anomaly if v is not None), default=0.0)
    top_histogram = max((v for v in histogram if v is not None), default=0.0)

    combined: list[float | None] = []
    for a, h in zip(anomaly, histogram, strict=True):
        if a is None and h is None:
            combined.append(None)
            continue
        a_norm = (a / top_anomaly) if (a is not None and top_anomaly > 0) else 0.0
        h_norm = (h / top_histogram) if (h is not None and top_histogram > 0) else 0.0
        combined.append(max(a_norm, h_norm))
    return combined


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
        scores = combine_with_anomaly(frame_paths)
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

    # Kare serisi kapanışın ÜSTÜNDE dışarı veriliyor: konsolun piksel
    # entropisi grafiği (Görev raporu §1.B) bunu çiziyor. İkinci bir geçişle
    # yeniden hesaplanamazdı — normalizasyon koşuya göreli (bkz. modül
    # docstring'i, "Sınır"), yani başka bir çağrı başka bir ölçek üretir ve
    # grafik döngünün nişan aldığından farklı bir şey gösterirdi.
    #
    # İmzaya bir `on_scores` geri çağrısı eklemek yerine öznitelik: bu
    # fonksiyonun DÖNDÜĞÜ şey zaten `DecisionLoop`'a takılıyor
    # (`loop.motion_for`), yani seri de çağıranın elinde olan bir referansla
    # birlikte geliyor ve `run_pipeline`'ın imzası büyümüyor.
    motion_for.timestamps = timestamps
    motion_for.scores = scores
    return motion_for
