"""Takip katmanı — tespiti **zenginleştirir**, süzmez.

25 Ağustos'a kadar buradaki kural şuydu: `if box.id is None: continue`. Yani
BoTSORT bir kimlik atayamadıysa kutu hiç var olmamış sayılıyordu. Ölçüldü
(raf çökmesi klibi, `forklift-compilation--N9bG-sOU6LE-k03.mp4`, 23 kare):

    YOLO'nun bulduğu kutu        6   (5 forklift + 1 vehicle)
    BoTSORT'un verdiği kimlik    0
    ajan katmanına ulaşan tespit 0

Altı kutunun altısı da atıldı. `participants[]` boş kaldı, kök neden raporu
"dış etki kaydedilmedi" yazdı — hiçbir şeye bakmadan.

**Sebep BoTSORT'un ayarı değil, kare hızı.** 1 fps'te iki kare arasında bir
saniye var; IoU eşleştirmesi tam da `FLOOR_VELOCITY`'nin hedeflediği hızlı
hareket için başarısız oluyor. Sıfır kimlik bu kurulumda bir istisna değil,
**beklenen** hâl. Bu yüzden burada tracker ayarı YOK: ne yaml eşiği, ne
`track_buffer`, ne re-ID. O yol ölçüldü ve çıkmaz.

Bunun yerine sözleşme tersine çevrildi: **tespit kayıttır, takip kimlik
ekleyebildiğinde ekler.** `track_id` artık `int | None` ve kimliksiz kutu
düşürülmüyor. Kimlik isteyen hesaplar (hız, kaybolan iz) `gozcu.signals`
içinde kimliği olanlarla sınırlı kalıyor; kimlik istemeyen hesaplar (kişi
sayısı) bütün kutuları görüyor.

Kazanç dürüstçe yazılsın: bu değişiklik yukarıdaki klibi KURTARMIYOR. O
klipteki kişiler zaten 0,12/0,14 puanla eşiğin altında ve forkliftin düştüğü
pencere tabandan geçemiyor. Kazandığı şey başka: eşiği geçen ama kısa süre
görünen insanlar artık sayılıyor ve `participants[]` gerçeği söylüyor.
"""

from dataclasses import dataclass
from pathlib import Path

import cv2
from ultralytics import YOLO

from gozcu.config import YOLO_CLASSES, YOLO_CONFIDENCE, YOLO_MODEL_PATH
from gozcu.detect import DetectedObject


@dataclass
class TrackedObject(DetectedObject):
    #: Takip kimliği — **isteğe bağlı**. `None` "bu kutu yok" demek değil,
    #: "bu kutuya kimlik atanamadı" demek. `models.Detection.track_id` zaten
    #: `int | None` olduğu için veri sözleşmesi değişmiyor.
    track_id: int | None = None


def track_video(frame_paths: list[str | Path]) -> list[list[TrackedObject]]:
    """Kareleri takip ederek TÜM kutuları döndürür; kimlik varsa iliştirir.

    Kimliksiz bir kutu atlanmıyor. Atlanırsa tespit katmanının bulduğu kanıt
    takip katmanının başarısızlığı yüzünden yok olur — ve bir güvenlik
    sisteminde "göremedim" ile "yoktu" aynı şeye çevrilir.
    """
    # A fresh model instance per call, not gozcu.detect's cached one — persist=True
    # carries tracker state on the model object across calls, and reusing a
    # long-lived model across different videos would leak track IDs between them.
    model = YOLO(YOLO_MODEL_PATH)
    model.set_classes(YOLO_CLASSES)

    all_tracked = []
    for frame_path in frame_paths:
        # Load frame as image (not as source path) — persist=True only works correctly
        # when passing loaded frames, not file paths (which are treated as separate video sources)
        frame = cv2.imread(str(frame_path))
        results = model.track(
            frame, persist=True, tracker="botsort.yaml", verbose=False, conf=YOLO_CONFIDENCE
        )
        result = results[0]

        tracked = []
        if result.boxes is not None:
            for box in result.boxes:
                class_id = int(box.cls.item())
                class_name = result.names[class_id]
                confidence = float(box.conf.item())
                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
                track_id = None if box.id is None else int(box.id.item())
                tracked.append(
                    TrackedObject(
                        class_name=class_name,
                        confidence=confidence,
                        bbox=(x1, y1, x2, y2),
                        track_id=track_id,
                    )
                )
        all_tracked.append(tracked)
    return all_tracked
