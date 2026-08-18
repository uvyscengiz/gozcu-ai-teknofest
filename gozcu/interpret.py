from pathlib import Path

from openai import OpenAI

from gozcu.config import VLM_BASE_URL, VLM_MODEL
from gozcu.schema import FrameEvent

_client = None

_SENTENCE_END = (".", "!", "?")
# How close to the schema's maxLength (in characters) counts as "cut off at the
# boundary" for word-trimming purposes. The decoder doesn't always land on the
# exact limit before forcing the string closed (observed: one frame cut at
# exactly 300 chars, another at 296) — a fixed 1-char tolerance misses the
# looser case, so this uses a small window instead.
_BOUNDARY_SLACK = 10


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=VLM_BASE_URL, api_key="not-needed")
    return _client


def _sanitize_description(text: str, max_length: int) -> str:
    """Clean up a `description` that may have been forcibly cut off by the VLM's
    strict-JSON-schema decoder enforcing `maxLength` character-by-character
    during generation (not just at validation time).

    Two symptoms observed empirically on real frames, both of which still pass
    pydantic validation silently:
    - a raw trailing control character padded onto the string right before the
      closing quote (e.g. frame 0011: "...roof of the building. There\\x01")
    - a hard cutoff mid-word at exactly `max_length` characters, no error
      (e.g. frame 0005: "...a building in the")

    This sanitizes the already-parsed value in place; it does not retry or
    re-request generation.
    """
    original_length = len(text)

    cleaned = text
    while cleaned and not cleaned[-1].isprintable():
        cleaned = cleaned[:-1]
    cleaned = cleaned.rstrip()

    # If the raw text landed at (or essentially at) the schema's length limit
    # and doesn't already end on a sentence boundary, it was very likely cut
    # off mid-word/mid-sentence by the decoder — trim back to the last whole
    # word rather than leave a dangling fragment.
    at_boundary = original_length >= max_length - _BOUNDARY_SLACK
    if at_boundary and not cleaned.endswith(_SENTENCE_END):
        trimmed, _, _ = cleaned.rpartition(" ")
        if trimmed:
            cleaned = trimmed.rstrip()

    return cleaned


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
        # NOTE: the spec mandates repetition_penalty=1.3, repetition_context_size=40
        # in addition to temperature. This was tried via extra_body={"repetition_penalty":
        # 1.3, "repetition_context_size": 40} and mlx_vlm.server's OpenAI-compatible
        # endpoint accepts it without a 400 error — but empirically it makes output
        # *worse* under this strict-JSON-schema decoding path: A/B tested across 8 real
        # frames, every single response came back with the description wrapped in stray
        # "[...]" brackets, and one frame that was clean English without these params
        # leaked Chinese characters ("烟雾") with them. Reverted; see
        # docs/05-decisions/action-items.md (2026-08-18 entry) for the escalated finding.
    )

    event = FrameEvent.model_validate_json(response.choices[0].message.content)
    max_description_length = schema["properties"]["description"].get("maxLength", 300)
    event.description = _sanitize_description(event.description, max_description_length)
    event.timestamp_s = timestamp_s
    event.detected_objects = detected_objects
    return event
