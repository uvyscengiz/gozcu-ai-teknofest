"""Küresel piksel-entropi ön-taraması — çok uzun videolarda BAKILACAK
saniyeleri, videonun tamamını işlemeden seçen katman.

Bu modül de `gozcu.motion` gibi hiçbir model çağırmıyor: ne ağ geçidi, ne
VLM, ne YOLO. Ondan farkı GİRDİSİ — `motion.py` zaten ffmpeg ile çıkarılmış
kareler üzerinde çalışıyor (`run_pipeline` önce TÜM videoyu 3 fps'te kareye
bölüyor, sonra YOLO HER karede çalışıyor); bu modül kareler hiç çıkarılmadan
ÖNCE, doğrudan video dosyasından seyrek örnekleyerek çalışıyor. Amacı ffmpeg
+ YOLO'yu videonun tamamında değil, yalnız aday saniyelerde çalıştırmak —
1 saatlik bir videoda dakikalar süren adımı saniyelere indirmek.

## Neden "piksel entropisi"

`motion.py`'daki iki sinyal (kare farkı, histogram uzaklığı) yer değiştirmeyi
ve ton kaymasını yakalıyor. Kaza anlarının bir kısmı (patlama, toz bulutu,
enkaz saçılması) üçüncü bir imza taşıyor: görüntünün KENDİ İÇİNDEKİ
düzensizlik aniden artıyor. Sakin bir sahnede birkaç büyük, düzgün bölge
vardır (zemin, duvar, makine gövdesi) — gri ton histogramı birkaç kovada
toplanır, Shannon entropisi düşüktür. Kaza anında görüntü aniden yüzlerce
küçük, düzensiz parçaya bölünür (toz, duman, savrulan enkaz) — histogram
yayılır, entropi yükselir.

Ham kare entropisi tek başına güvenilmez: parlak/karmaşık dokulu sakin
sahneler de yüksek entropi verebilir (ör. dolu bir raf, kalabalık bir zemin).
Bunun için ikinci sinyal: ardışık iki örnek karenin FARK görüntüsünün
entropisi. Sakin bir sahnede fark görüntüsü neredeyse boştur (tek kova
baskın, entropi ~0) — sahne karmaşık olsa bile, DEĞİŞMEDİĞİ sürece fark
düzdür. Kaotik bir olayda fark görüntüsünün kendisi rastgele görünür
(entropi yüksek). Bu, kare farkının BÜYÜKLÜĞÜNDEN bağımsız bir sinyal: yavaş
ve düzgün bir kamera hareketi de büyük bir ortalama farka yol açar ama fark
görüntüsü düzenlidir (kenarlar boyunca birkaç şerit), entropisi düşük kalır.

## Birleşim

İki kanal ayrı ayrı **z-skorlanıp** sonra BÜYÜĞÜ alınıyor — "ikisinden biri
ötüyorsa bu an ilginçtir" — ama `motion.py`'nin "koşu zirvesine böl" deseni
BURADA çalışmıyor: doğal bir görüntünün gri ton histogramı durgun bir
sahnede bile geniştir (tipik 5-7 bit), yani zirveye bölmek neredeyse HER
kareyi 1,0'a yakın gösterip sinyali köreltiyor (ölçüldü, bkz.
`combine_entropy`). Z-skor mutlak ölçekten bağımsız: soru "bu kare yüksek
entropili mi" değil, "kendi koşusunun tipik değerine göre olağandışı mı".

## Sınır

Bu katman da bir triyaj: hiçbir arıza istisna atmaz, okunamayan video
`ScanResult(candidates=[])`'e düşer — "kaza yok" değil "kanıt yok" demek;
çağıran taraf boş listeyi "tüm videoyu tara" diye okumalı, "sakin video"
diye değil. Döndürdüğü pencereler bir ÖNERİ: asıl karar hâlâ
`DecisionLoop`'un (taban + yönlendirici + VLM) elinde. Bu modülün tek işi
o zincirin videonun HANGİ bölümlerinde çalışacağını seçmek.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import cv2
import numpy as np

__all__ = [
    "CandidateWindow", "ScanResult", "scan_video", "entropy_of_gray",
    "combine_entropy",
]

#: Gri ton histogramı kova sayısı. `gozcu.motion.HIST_BINS` ile aynı
#: gerekçe: JPEG/codec nicemleme gürültüsünü yutacak, bir ton kaymasını
#: kaçırmayacak genişlikte.
HIST_BINS = 64

#: Saniyede kaç kare örneklenecek. Videonun kendi fps'i değil — 1 Hz bile
#: birkaç saniye süren bir patlamayı/toz bulutunu kolayca yakalar; 1 saatlik
#: bir videoda 3.600 örnek demektir — `frames.py`'nin 3 fps × 3.600 s =
#: 10.800 kareyle YOLO çalıştırmasının üçte biri, üstelik hiçbir model
#: çağrısı içermeden (sadece decode + histogram).
SAMPLE_HZ = 1.0

#: Aday pencere genişliği (saniye), tampon EKLENMEDEN. Kısa tutulursa
#: gerçek olay iki örneğe bölünüp ikisi de zirvenin altında kalabilir.
WINDOW_S = 8.0

#: Bir örneğin "aday" sayılması için z-skor eşiği: koşunun geri kalanına
#: göre kaç standart sapma yukarıda olması gerektiği.
Z_THRESH = 2.0

#: Komşu adayları tek pencerede birleştirmek için izin verilen boşluk
#: (saniye). Aynı olayın iki örneğe bölünmesini tek pencerede toplar.
MERGE_GAP_S = 4.0

#: Aday penceresinin her iki ucuna eklenen tampon (saniye). Olayın gerçek
#: başlangıcı örnekleme anından biraz önce/sonra olabilir; asıl karar
#: zincirinin (taban + yönlendirici) bunu görebilmesi için pay bırakılır.
PAD_S = 5.0


@dataclass
class CandidateWindow:
    start_s: float
    end_s: float
    score: float  # z-skor (kaç std sapma yukarıda); sıralama VE eşik için


@dataclass
class ScanResult:
    duration_s: float
    sampled: int
    scan_time_s: float
    candidates: list[CandidateWindow] = field(default_factory=list)
    scores: list[float] = field(default_factory=list)
    timestamps: list[float] = field(default_factory=list)


def entropy_of_gray(image: np.ndarray, bins: int = HIST_BINS) -> float:
    """Gri ton görüntüsünün Shannon entropisi (bit).

    Düz/tek renkli bir görüntüde (tek kova dolu) 0'a yakın; piksel değerleri
    kovalar arasında eşit dağılmışsa `log2(bins)`'e (bu kova sayısında
    ulaşılabilecek en yüksek değer) yaklaşır.
    """
    counts = cv2.calcHist([image], [0], None, [bins], [0, 256]).ravel()
    total = float(counts.sum())
    if total <= 0:
        return 0.0
    p = counts / total
    p = p[p > 0]
    return float(-np.sum(p * np.log2(p)))


def _zscore(values: list[float]) -> list[float]:
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0:
        return []
    mean = float(arr.mean())
    std = max(float(arr.std()), 1e-6)
    return list((arr - mean) / std)


def combine_entropy(frame_entropy: list[float],
                    diff_entropy: list[float | None]) -> list[float]:
    """İki entropi kanalını KENDİ ortalama/std'sine göre ayrı ayrı
    z-skorlayıp eleman bazında büyüğünü alır. Döndürdüğü değer 0..1 değil,
    z-skorun kendisi — "kaç standart sapma yukarıda" okunabilsin diye.

    `gozcu.motion.combine` "koşu zirvesine böl" desenini kullanıyor ve orada
    doğru: kare farkı/histogram uzaklığı durgun bir sahnede sıfıra yakın,
    olayda zirve yapıyor — geniş dinamik aralık. Entropi öyle değil: doğal
    bir görüntünün gri ton histogramı durgun bir sahnede bile geniştir
    (tipik olarak 5-7 bit), yani "koşu zirvesine göre normalize et" neredeyse
    HER kareyi 1,0'a yakın gösterir ve sinyali köreltir — ölçüldü (gerçek
    video, `scripts/entropy_scan_demo.py`): ham kare entropisi 5,45-5,68 bit
    arasında, zirveye bölününce hepsi 0,96-1,0'a sıkışıyor, hiçbir kare
    ötekinden ayrışmıyor. Doğru soru "bu kare mutlak olarak yüksek entropili
    mi" değil, "bu kare KENDİ KOŞUSUNUN TİPİK değerine göre olağandışı mı" —
    z-skor bunu soruyor, mutlak ölçekten bağımsız.
    """
    fe_z = _zscore(frame_entropy)

    known_idx = [i for i, d in enumerate(diff_entropy) if d is not None]
    de_z_known = _zscore([diff_entropy[i] for i in known_idx])
    de_z: list[float | None] = [None] * len(diff_entropy)
    for idx, z in zip(known_idx, de_z_known, strict=True):
        de_z[idx] = z

    return [fz if dz is None else max(fz, dz)
           for fz, dz in zip(fe_z, de_z, strict=True)]


def _merge_windows(windows: list[CandidateWindow], gap_s: float) -> list[CandidateWindow]:
    if not windows:
        return []
    ordered = sorted(windows, key=lambda w: w.start_s)
    merged = [ordered[0]]
    for w in ordered[1:]:
        last = merged[-1]
        if w.start_s <= last.end_s + gap_s:
            merged[-1] = CandidateWindow(
                start_s=last.start_s,
                end_s=max(last.end_s, w.end_s),
                score=max(last.score, w.score))
        else:
            merged.append(w)
    return merged


def scan_video(
    video_path,
    sample_hz: float = SAMPLE_HZ,
    window_s: float = WINDOW_S,
    z_thresh: float = Z_THRESH,
    merge_gap_s: float = MERGE_GAP_S,
    pad_s: float = PAD_S,
    max_candidates: int | None = None,
) -> ScanResult:
    """Videoyu seyrek örnekleyip piksel-entropi zirvelerini aday pencerelere
    dönüştürür. Hiçbir model çağırmaz, kareleri diske yazmaz.

    `grab()`/`retrieve()` ikilisi kullanılıyor: aradaki kareler tam
    decode EDİLMEDEN atlanıyor (yalnız `grab`), yalnız örneklenen kare tam
    çözülüyor (`retrieve`). Sabit adımlı `set(CAP_PROP_POS_MSEC, ...)` ile
    tekrar tekrar aramak yerine bu tercih edildi: keyframe'e göre arama
    konteynere göre yavaş/tutarsız olabiliyor, ardışık grab ise her zaman
    doğrusal ve öngörülebilir.

    Aday bulunamazsa (ör. video baştan sona görsel olarak durgun) BOŞ LİSTE
    döner — çağıran tarafın "kanıt yok, tüm videoyu tara" diye güvenli
    varsayılana düşmesi için.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return ScanResult(duration_s=0.0, sampled=0, scan_time_s=0.0)

    native_fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    if not native_fps or native_fps <= 0 or native_fps > 240:
        native_fps = 25.0  # bozuk/okunamayan metadata: makul bir varsayılan

    frame_interval = max(1, round(native_fps / sample_hz)) if sample_hz > 0 else 1

    start = time.monotonic()
    timestamps: list[float] = []
    frame_entropy: list[float] = []
    diff_entropy: list[float | None] = []
    previous: np.ndarray | None = None

    frame_idx = 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if frame_idx % frame_interval == 0:
            ok2, frame = cap.retrieve()
            if ok2 and frame is not None:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                timestamps.append(frame_idx / native_fps)
                frame_entropy.append(entropy_of_gray(gray))
                if previous is not None:
                    if previous.shape != gray.shape:
                        previous = cv2.resize(
                            previous, (gray.shape[1], gray.shape[0]))
                    diff = cv2.absdiff(gray, previous)
                    diff_entropy.append(entropy_of_gray(diff))
                else:
                    diff_entropy.append(None)
                previous = gray
        frame_idx += 1

    cap.release()
    scan_time_s = time.monotonic() - start
    duration_s = frame_idx / native_fps

    if not timestamps:
        return ScanResult(duration_s=duration_s, sampled=0,
                          scan_time_s=scan_time_s)

    combined = combine_entropy(frame_entropy, diff_entropy)

    raw_windows = [
        CandidateWindow(
            start_s=max(0.0, ts - window_s / 2 - pad_s),
            end_s=ts + window_s / 2 + pad_s,
            score=score)
        for ts, score in zip(timestamps, combined, strict=True)
        if score >= z_thresh
    ]

    merged = _merge_windows(raw_windows, merge_gap_s)
    merged.sort(key=lambda w: w.score, reverse=True)
    if max_candidates is not None:
        merged = merged[:max_candidates]
    merged.sort(key=lambda w: w.start_s)

    return ScanResult(duration_s=duration_s, sampled=len(timestamps),
                      scan_time_s=scan_time_s, candidates=merged,
                      scores=combined, timestamps=timestamps)
