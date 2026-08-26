"""Algı katmanının ne gördüğünü kareye çizer — 0. Faz için tanı yüzeyi.

## Neden

Algı katmanının kalitesi bugün yalnız **sayı** olarak görülebiliyordu
(`bench/perception.json`: varlık duyarlılığı, sayım duyarlılığı). Bir sayı
"neyi kaçırdı" sorusunu cevaplamıyor. 25 Ağustos'ta raf çökmesi klibinde 23
karenin 23'ünde sıfır tespit çıktı ve bunu ancak elle bakarak anlayabildik —
çünkü katmanın gördüğü şeyi gösteren hiçbir yüzey yoktu.

Bu modül gözlemleri kareye geri çiziyor: kutu, etiket, iz kimliği ve pencere
başına yönlendirme verdikti. Yeni bir ölçüm YAPMIYOR — depoda ne varsa onu
gösteriyor. Ekranın ölçüm göstermesi, ölçüm yapması demek değil.

## Kaynak depo, kare değil

Kutular `Store.observations()`'tan geliyor, modelden yeniden sorulmuyor:
çizilen şey koşunun GERÇEKTEN kaydettiği şey olmak zorunda, yoksa tanı
aracının kendisi ikinci bir gerçeklik üretir.

## Kodlama ffmpeg ile

`cv2.VideoWriter`'ın `mp4v`'si tarayıcıda oynamıyor. Kareler JPEG olarak
yazılıp `libx264` ile birleştiriliyor — `report._clip_for` ile aynı reçete.
"""

import shutil
import subprocess
from pathlib import Path

__all__ = ["annotate_run", "AnnotateError"]

#: Etiket başına renk (BGR — OpenCV'nin sırası). İnsan ayrı renkte: kalabalık
#: bir karede "kaç kişi var" sorusu diğer her şeyden önce geliyor.
#: OpenCV'nin Hershey yazı tipi Türkçe karakterleri çiziyor (ölçüldü:
#: ş, ğ, İ, ö, ç, ü, ı). Metinleri ASCII'ye düşürmeye gerek yok ve
#: düşürmek CLAUDE.md'nin "insana görünen metin Türkçe" kuralını bozardı.
COLORS = {
    "person": (60, 200, 60),
    "forklift": (0, 165, 255),
    "truck": (0, 165, 255),
    "vehicle": (0, 165, 255),
}
DEFAULT_COLOR = (200, 200, 200)
HEADER_BG = (28, 28, 28)
HEADER_FG = (240, 240, 240)
WARN_FG = (80, 80, 255)

#: Üst şeridin yüksekliği (piksel). İki satır metin sığıyor.
HEADER_H = 46

FLOOR_LABELS = {True: "taban=EVET", False: "taban=HAYIR"}
OUTCOME_LABELS = {"routed": "yönlendiriciye gitti",
                  "forced": "görü bütçesinden bakıldı",
                  "skipped": "hiçbir katman bakmadı",
                  "deferred": "görü kesik — telafide"}

NO_FRAMES = "Çizilecek kare yok — koşu kareleri silinmiş olabilir."
NO_FFMPEG = "ffmpeg bulunamadı; açıklamalı video üretilemiyor."


class AnnotateError(RuntimeError):
    """Çizim üretilemedi. Koşuyu DÜŞÜRMEZ — çağıran yakalayıp yazar."""


def _mmss(seconds: float) -> str:
    return f"{int(seconds) // 60:02d}:{int(seconds) % 60:02d}"


def _window_for(ts: float, records: list):
    """Bu karenin düştüğü pencere kaydı; yoksa `None`.

    Aralık `ts <= end_ts` ile KAPALI: pencerenin son karesi de o pencereye
    ait ve dışarıda bırakılırsa her pencerenin son karesi başlıksız kalır.
    """
    for record in records:
        if record.ts <= ts <= record.end_ts:
            return record
    return None


def _draw(image, observation, record, index: int, total: int):
    """Tek karenin üstüne kutuları ve üst şeridi çizer."""
    import cv2

    height, width = image.shape[:2]
    for detection in observation.detections:
        x1, y1, x2, y2 = (int(v) for v in detection.box)
        color = COLORS.get(detection.label, DEFAULT_COLOR)
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
        tag = detection.label
        if detection.track_id is not None:
            tag += f" #{detection.track_id}"
        tag += f" {detection.confidence:.2f}"
        # Etiket kutunun ÜSTÜNE, kadraj dışına taşarsa içine.
        baseline = y1 - 6 if y1 > 18 else y1 + 16
        cv2.putText(image, tag, (x1, baseline), cv2.FONT_HERSHEY_SIMPLEX,
                    0.45, color, 1, cv2.LINE_AA)

    cv2.rectangle(image, (0, 0), (width, HEADER_H), HEADER_BG, -1)
    signals = observation.signals
    left = (f"{_mmss(observation.ts)}  kare {index}/{total}  "
            f"kişi={signals.person_count}  kutu={len(observation.detections)}")
    cv2.putText(image, left, (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                HEADER_FG, 1, cv2.LINE_AA)

    if record is None:
        right = "pencere kaydı yok"
        colour = WARN_FG
    else:
        right = (f"pencere {record.index}/{record.total}  "
                 f"{FLOOR_LABELS[record.floor_passed]}  "
                 f"{OUTCOME_LABELS.get(record.outcome, record.outcome)}")
        colour = HEADER_FG if record.floor_passed else WARN_FG
    cv2.putText(image, right, (8, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                colour, 1, cv2.LINE_AA)

    # Kadrajın ORTASINDA kaybolan izler ayrı yazılıyor: kadrajı terk eden bir
    # insan gitmiştir, ortasında kaybolan bir insan bir şeyin İÇİNE girmiştir
    # (bkz. `models.Signals.interior_vanished_tracks`).
    if signals.interior_vanished_tracks:
        cv2.putText(image,
                    f"iç kayıp: {signals.interior_vanished_tracks}",
                    (8, HEADER_H + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    WARN_FG, 1, cv2.LINE_AA)
    return image


def annotate_run(frames_dir, store, out_path, fps: float | None = None) -> Path:
    """Koşunun karelerini gözlemlerle çizip bir mp4 üretir.

    `frames_dir` `run_pipeline`'ın döndürdüğü dizin. Kutular depodan geliyor,
    modelden yeniden sorulmuyor: tanı aracı ikinci bir gerçeklik üretmemeli.

    Hata hâlinde `AnnotateError` atıyor — sessizce boş bir dosya bırakmak,
    "algı hiçbir şey görmedi" ile "çizim üretilemedi"yi aynı şeye çevirirdi.
    """
    import cv2

    from gozcu.config import FRAME_FPS

    fps = FRAME_FPS if fps is None else fps
    frames = sorted(Path(frames_dir).glob("frame_*.jpg"))
    if not frames:
        raise AnnotateError(NO_FRAMES)
    if shutil.which("ffmpeg") is None:
        raise AnnotateError(NO_FFMPEG)

    observations = store.observations()
    by_ts = {round(observation.ts, 3): observation for observation in observations}
    records = store.window_records()

    out_path = Path(out_path)
    work = out_path.parent / f"{out_path.stem}-kare"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)

    for index, frame_path in enumerate(frames):
        image = cv2.imread(str(frame_path))
        if image is None:            # okunamayan kare çizimi düşürmez
            continue
        ts = round(index / fps, 3)
        observation = by_ts.get(ts)
        if observation is not None:
            image = _draw(image, observation, _window_for(ts, records),
                          index + 1, len(frames))
        cv2.imwrite(str(work / f"kare_{index:05d}.jpg"), image)

    written = sorted(work.glob("kare_*.jpg"))
    if not written:
        shutil.rmtree(work, ignore_errors=True)
        raise AnnotateError(NO_FRAMES)

    # `libx264`: `mp4v` tarayıcıda oynamıyor ve bu video konsolda gösteriliyor.
    result = subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(fps),
         "-i", str(work / "kare_%05d.jpg"),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out_path)],
        capture_output=True)
    shutil.rmtree(work, ignore_errors=True)

    if result.returncode != 0 or not out_path.exists():
        raise AnnotateError(
            f"ffmpeg çizimi birleştiremedi: "
            f"{result.stderr.decode('utf-8', 'replace')[-300:]}")
    return out_path
