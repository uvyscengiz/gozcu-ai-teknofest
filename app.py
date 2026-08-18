import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

import gradio as gr
from openai import OpenAI
from PIL import Image, ImageDraw

from gozcu.config import VLM_BASE_URL, VLM_MODEL
from gozcu.detect import detect_objects
from gozcu.run import run_pipeline

_server_process = None

_LOCAL_HOSTNAMES = ("localhost", "127.0.0.1")
_DEFAULT_LOCAL_PORT = 8000


def _ensure_server_running():
    global _server_process
    client = OpenAI(base_url=VLM_BASE_URL, api_key="not-needed")
    try:
        client.models.list()
        return
    except Exception:
        pass

    hostname = urlsplit(VLM_BASE_URL).hostname
    if hostname not in _LOCAL_HOSTNAMES:
        raise RuntimeError(
            f"VLM server at {VLM_BASE_URL} is unreachable and is not localhost — "
            "auto-start only works for local servers. Start it manually or fix the URL."
        )

    port = urlsplit(VLM_BASE_URL).port
    port = str(port) if port is not None else str(_DEFAULT_LOCAL_PORT)
    _server_process = subprocess.Popen(
        ["uv", "run", "mlx_vlm.server", "--model", VLM_MODEL, "--port", port]
    )

    for _ in range(60):
        try:
            client.models.list()
            return
        except Exception:
            time.sleep(2)
    raise RuntimeError(
        f"mlx_vlm.server did not become reachable at {VLM_BASE_URL} within 120s"
    )


def _annotate_frame(frame_path: Path) -> Image.Image:
    image = Image.open(frame_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    for detection in detect_objects(frame_path):
        draw.rectangle(detection.bbox, outline="red", width=3)
        draw.text(
            (detection.bbox[0], max(0, detection.bbox[1] - 12)),
            detection.class_name,
            fill="red",
        )
    return image


def _annotate_all_frames(result, frame_dir: Path) -> list[tuple[Image.Image, str]]:
    gallery = []
    for index, event in enumerate(result.events):
        frame_path = frame_dir / f"frame_{index + 1:04d}.jpg"
        if not frame_path.exists():
            continue
        image = _annotate_frame(frame_path)
        caption = (
            f"t={event.timestamp_s}s | objects: {event.detected_objects} | "
            f"{event.description}"
        )
        gallery.append((image, caption))
    return gallery


def process_video(video_path):
    _ensure_server_running()
    result, frame_dir = run_pipeline(video_path)
    return _annotate_all_frames(result, frame_dir)


demo = gr.Interface(
    fn=process_video,
    inputs=gr.Video(label="Upload a video"),
    outputs=gr.Gallery(label="Frame-by-frame results", columns=3, object_fit="contain"),
    title="gözcü-ai — Stage 1 MVP",
)

if __name__ == "__main__":
    demo.launch()
