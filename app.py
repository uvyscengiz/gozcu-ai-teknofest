import subprocess
import time
from pathlib import Path

import gradio as gr
from openai import OpenAI
from PIL import Image, ImageDraw

from gozcu.config import VLM_BASE_URL, VLM_MODEL
from gozcu.detect import detect_objects
from gozcu.run import run_pipeline

_server_process = None


def _ensure_server_running():
    global _server_process
    client = OpenAI(base_url=VLM_BASE_URL, api_key="not-needed")
    try:
        client.models.list()
        return
    except Exception:
        pass

    port = VLM_BASE_URL.rstrip("/").split(":")[-1].split("/")[0]
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


def _annotate_sample_frame(result, frame_dir: Path) -> Image.Image | None:
    for index, event in enumerate(result.events):
        if not event.detected_objects:
            continue
        frame_path = frame_dir / f"frame_{index + 1:04d}.jpg"
        if not frame_path.exists():
            continue
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
    return None


def process_video(video_path):
    _ensure_server_running()
    result, frame_dir = run_pipeline(video_path)
    annotated = _annotate_sample_frame(result, frame_dir)
    return result.model_dump_json(indent=2), annotated


demo = gr.Interface(
    fn=process_video,
    inputs=gr.Video(label="Upload a video"),
    outputs=[
        gr.Textbox(label="Pipeline JSON output", lines=30),
        gr.Image(label="Sample annotated frame"),
    ],
    title="gözcü-ai — Stage 1 MVP",
)

if __name__ == "__main__":
    demo.launch()
