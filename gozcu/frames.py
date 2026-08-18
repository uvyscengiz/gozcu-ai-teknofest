import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Frame:
    path: Path
    timestamp_s: float
    index: int


def extract_frames(
    video_path: str | Path,
    output_dir: str | Path,
    fps: float = None,
    width: int = None,
) -> list[Frame]:
    from gozcu.config import FRAME_FPS, FRAME_WIDTH

    fps = FRAME_FPS if fps is None else fps
    width = FRAME_WIDTH if width is None else width

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for stale_frame in output_dir.glob("frame_*.jpg"):
        stale_frame.unlink()

    pattern = str(output_dir / "frame_%04d.jpg")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"fps={fps},scale={width}:-2",
            pattern,
        ],
        check=True,
        capture_output=True,
    )

    frame_paths = sorted(output_dir.glob("frame_*.jpg"))
    return [
        Frame(path=p, timestamp_s=i / fps, index=i)
        for i, p in enumerate(frame_paths)
    ]
