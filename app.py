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


def _annotate_all_frames(
    result, frame_dir: Path
) -> tuple[list[tuple[Image.Image, str]], list[str]]:
    thumbnails = []
    details = []
    for index, event in enumerate(result.events):
        frame_path = frame_dir / f"frame_{index + 1:04d}.jpg"
        if not frame_path.exists():
            continue
        image = _annotate_frame(frame_path)
        thumbnails.append((image, f"t={event.timestamp_s}s"))
        detail_text = (
            f"**t={event.timestamp_s}s**\n\n"
            f"**Detected objects:** {event.detected_objects}\n\n"
            f"**Description:** {event.description}"
        )
        if event.notable_event:
            detail_text += f"\n\n**Notable event:** {event.notable_event}"
        details.append(detail_text)
    return thumbnails, details


def process_video(video_path):
    _ensure_server_running()
    result, frame_dir = run_pipeline(video_path)
    thumbnails, details = _annotate_all_frames(result, frame_dir)
    placeholder = "Click a frame above to see its full detection and description."
    return thumbnails, details, placeholder, result.model_dump_json(indent=2)


def show_frame_details(details: list[str], evt: gr.SelectData) -> str:
    if evt.index is None or evt.index >= len(details):
        return "No details available for this frame."
    return details[evt.index]


with gr.Blocks(title="gözcü-ai — Stage 1 MVP") as demo:
    gr.Markdown("# gözcü-ai — Stage 1 MVP")
    video_input = gr.Video(label="Upload a video")
    submit_btn = gr.Button("Process", variant="primary")
    gallery = gr.Gallery(
        label="Frame-by-frame results",
        columns=6,
        object_fit="contain",
        allow_preview=False,
    )
    details_state = gr.State([])
    detail_panel = gr.Markdown("Click a frame above to see its full detection and description.")
    json_output = gr.Code(label="Full pipeline JSON output", language="json")

    submit_btn.click(
        fn=process_video,
        inputs=video_input,
        outputs=[gallery, details_state, detail_panel, json_output],
    )
    gallery.select(fn=show_frame_details, inputs=details_state, outputs=detail_panel)

if __name__ == "__main__":
    demo.launch()
