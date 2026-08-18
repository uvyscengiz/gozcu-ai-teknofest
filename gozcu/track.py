from dataclasses import dataclass
from pathlib import Path

import cv2
from ultralytics import YOLO

from gozcu.config import YOLO_MODEL_PATH
from gozcu.detect import DetectedObject


@dataclass
class TrackedObject(DetectedObject):
    track_id: int


def track_video(frame_paths: list[str | Path]) -> list[list[TrackedObject]]:
    # A fresh model instance per call, not gozcu.detect's cached one — persist=True
    # carries tracker state on the model object across calls, and reusing a
    # long-lived model across different videos would leak track IDs between them.
    model = YOLO(YOLO_MODEL_PATH)

    all_tracked = []
    for frame_path in frame_paths:
        # Load frame as image (not as source path) — persist=True only works correctly
        # when passing loaded frames, not file paths (which are treated as separate video sources)
        frame = cv2.imread(str(frame_path))
        results = model.track(frame, persist=True, tracker="botsort.yaml", verbose=False)
        result = results[0]

        tracked = []
        if result.boxes is not None:
            for box in result.boxes:
                if box.id is None:
                    continue
                class_id = int(box.cls.item())
                class_name = result.names[class_id]
                confidence = float(box.conf.item())
                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
                track_id = int(box.id.item())
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
