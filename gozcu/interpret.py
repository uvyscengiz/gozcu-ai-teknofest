from pathlib import Path

from openai import OpenAI

from gozcu.config import VLM_BASE_URL, VLM_MODEL
from gozcu.schema import FrameEvent

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=VLM_BASE_URL, api_key="not-needed")
    return _client


def describe_frame(
    frame_path: str | Path,
    detected_objects: list[str],
    timestamp_s: float,
    client: OpenAI | None = None,
) -> FrameEvent:
    client = client or _get_client()

    objects_line = ", ".join(detected_objects) if detected_objects else "none"
    prompt = (
        f"Confirmed objects detected in this frame by a separate detector: {objects_line}.\n"
        "Describe only what is visible in the image. Do not state a location, "
        "casualty count, or any statistic unless it is directly and unambiguously "
        "readable from the image itself. If you are not sure, do not guess."
    )

    schema = FrameEvent.model_json_schema()
    schema["required"] = ["timestamp_s", "detected_objects", "description"]
    # Without an upper bound, the local VLM's strict-JSON-schema decoding gets stuck
    # in a runaway repetition loop inside the detected_objects array (observed
    # empirically: it repeats invented labels until max_tokens is exhausted and the
    # JSON never closes, so `description` is never reached). detected_objects is
    # discarded and overwritten with the YOLO ground truth below regardless of what
    # the model emits here, so bounding it to the true count (min 1, since the array
    # can't be required-but-empty) only constrains filler the model throws away.
    schema["properties"]["detected_objects"]["maxItems"] = max(1, len(detected_objects))

    response = client.chat.completions.create(
        model=VLM_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": str(frame_path)}},
                ],
            }
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "FrameEvent", "strict": True, "schema": schema},
        },
        max_tokens=300,
        temperature=0.3,
    )

    event = FrameEvent.model_validate_json(response.choices[0].message.content)
    event.timestamp_s = timestamp_s
    event.detected_objects = detected_objects
    return event
