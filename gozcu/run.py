import tempfile
from pathlib import Path

from gozcu.detect import detect_objects
from gozcu.frames import extract_frames
from gozcu.interpret import describe_frame
from gozcu.schema import PipelineResult


def run_pipeline(
    video_path: str | Path,
    output_dir: str | Path | None = None,
) -> PipelineResult:
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="gozcu_frames_")

    frames = extract_frames(video_path, output_dir)

    events = []
    for frame in frames:
        detections = detect_objects(frame.path)
        class_names = sorted({d.class_name for d in detections})
        event = describe_frame(frame.path, class_names, frame.timestamp_s)
        events.append(event)

    return PipelineResult(video_path=str(video_path), events=events)
