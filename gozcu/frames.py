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


def extract_frames_for_windows(
    video_path: str | Path,
    output_dir: str | Path,
    windows: list[tuple[float, float]],
    fps: float = None,
    width: int = None,
) -> list[Frame]:
    """`extract_frames` ile aynı sözleşme, ama videonun TAMAMI yerine yalnız
    verilen `(başlangıç_s, bitiş_s)` aralıklarında çalışır — `gozcu.entropy_scan`
    gibi bir ön-taramanın bulduğu aday pencereleri, videonun tamamını
    ffmpeg'den geçirmeden işlemek için.

    Her aralık AYRI bir ffmpeg çağrısıyla kesiliyor, `-ss` girdiden (`-i`)
    ÖNCE veriliyor — hızlı ama keyframe'e yuvarlanabilen arama. Bilerek: kesin
    kareye değil, hıza ihtiyacımız var; çağıran taraf (`gozcu.entropy_scan`)
    zaten pencerelere `PAD_S` kadar tampon bırakıyor, o tampon bu yuvarlamayı
    yutuyor.

    Kare zaman damgaları aralığın kendi başlangıcına göre DEĞİL, **videonun
    başına göre mutlak** — döngünün geri kalanı (episode `start_ts`, gözlem
    sıralaması, `motion.build_motion_for`'un zaman damgası eşlemesi) bunu
    varsayıyor.

    Aralık listesi boşsa `extract_frames`'e (tüm video) düşülür: kısmi bir
    sonucu sessizce "tüm video tarandı" gibi sunmak yerine güvenli
    varsayılana dönmek tercih edildi.
    """
    from gozcu.config import FRAME_FPS, FRAME_WIDTH

    fps = FRAME_FPS if fps is None else fps
    width = FRAME_WIDTH if width is None else width

    if not windows:
        return extract_frames(video_path, output_dir, fps=fps, width=width)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for stale_frame in output_dir.glob("seg*_frame_*.jpg"):
        stale_frame.unlink()

    all_frames: list[Frame] = []
    next_index = 0
    for seg_i, (start_s, end_s) in enumerate(sorted(windows)):
        if end_s <= start_s:
            continue
        pattern = str(output_dir / f"seg{seg_i:03d}_frame_%04d.jpg")
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{max(start_s, 0.0):.3f}",
                "-to",
                f"{end_s:.3f}",
                "-i",
                str(video_path),
                "-vf",
                f"fps={fps},scale={width}:-2",
                pattern,
            ],
            check=True,
            capture_output=True,
        )
        seg_paths = sorted(output_dir.glob(f"seg{seg_i:03d}_frame_*.jpg"))
        for local_i, p in enumerate(seg_paths):
            all_frames.append(Frame(
                path=p,
                timestamp_s=max(start_s, 0.0) + local_i / fps,
                index=next_index))
            next_index += 1

    return all_frames
