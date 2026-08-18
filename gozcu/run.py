import tempfile
from pathlib import Path

from gozcu.detect import detect_objects
from gozcu.frames import extract_frames
from gozcu.interpret import describe_frame
from gozcu.schema import PipelineResult
from gozcu.signals import compute_signals
from gozcu.track import track_video


def run_pipeline(
    video_path: str | Path,
    output_dir: str | Path | None = None,
) -> tuple[PipelineResult, Path]:
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="gozcu_frames_")
    output_dir = Path(output_dir)

    frames = extract_frames(video_path, output_dir)
    tracked_frames = track_video([frame.path for frame in frames])
    signals = compute_signals(tracked_frames, [frame.timestamp_s for frame in frames])

    events = []
    for frame, _tracked, frame_signals in zip(frames, tracked_frames, signals, strict=True):
        # detected_objects is derived from the ground-truth detector (matches what's
        # drawn on screen in app.py's _annotate_frame), not from the ByteTrack tracker
        # output — tracker output is only used above for signal computation
        # (velocity/vanished/person-count). ByteTrack only marks a track as
        # `is_activated` starting from its second observed frame internally, so an
        # object newly detected on this frame would be withheld from `tracked` even
        # though a box for it is drawn on screen this same frame.
        class_names = sorted({obj.class_name for obj in detect_objects(frame.path)})
        event = describe_frame(frame.path, class_names, frame_signals, frame.timestamp_s)
        events.append(event)

    return PipelineResult(video_path=str(video_path), events=events), output_dir
