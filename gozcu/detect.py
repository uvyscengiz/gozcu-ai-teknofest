from dataclasses import dataclass
from pathlib import Path

from ultralytics import YOLO

from gozcu.config import YOLO_CLASSES, YOLO_CONFIDENCE, YOLO_MODEL_PATH

_model = None


@dataclass
class DetectedObject:
    class_name: str
    confidence: float
    bbox: tuple[int, int, int, int]


def _get_model() -> YOLO:
    global _model
    if _model is None:
        _model = YOLO(YOLO_MODEL_PATH)
        _model.set_classes(YOLO_CLASSES)
    return _model


def detect_objects(frame_path: str | Path) -> list[DetectedObject]:
    model = _get_model()
    results = model.predict(source=str(frame_path), verbose=False, conf=YOLO_CONFIDENCE)
    result = results[0]

    detections = []
    for box in result.boxes:
        class_id = int(box.cls.item())
        class_name = result.names[class_id]
        confidence = float(box.conf.item())
        x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
        detections.append(
            DetectedObject(
                class_name=class_name,
                confidence=confidence,
                bbox=(x1, y1, x2, y2),
            )
        )
    return detections
