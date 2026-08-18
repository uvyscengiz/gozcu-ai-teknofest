from pathlib import Path

from openai import OpenAI

from gozcu.config import VLM_BASE_URL, VLM_MODEL
from gozcu.schema import FrameEvent
from gozcu.signals import FrameSignals

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
    """Clean up a string field (e.g. `description` or `notable_event`) that may
    have been forcibly cut off by the VLM's strict-JSON-schema decoder
    enforcing `maxLength` character-by-character during generation (not just
    at validation time). Despite the name, this is generic over any
    max-length-constrained string field produced by the same decoding path —
    pass that field's own schema `maxLength` as `max_length`.

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


def _signals_summary(signals: FrameSignals) -> str:
    parts = []
    if signals.velocities:
        moving = ", ".join(
            f"object #{track_id} moving ~{velocity:.0f}px/s"
            for track_id, velocity in signals.velocities.items()
        )
        parts.append(moving)
    if signals.vanished_tracks:
        parts.append(
            f"object(s) {signals.vanished_tracks} present in the previous frame "
            "are no longer detected"
        )
    if signals.person_count_delta > 0:
        parts.append(
            f"person count rose by {signals.person_count_delta} to "
            f"{signals.person_count} since the last frame"
        )
    elif signals.person_count_delta < 0:
        parts.append(
            f"person count fell by {abs(signals.person_count_delta)} to "
            f"{signals.person_count} since the last frame"
        )
    if not parts:
        return "no significant motion or count changes detected"
    return "; ".join(parts)


def describe_frame(
    frame_path: str | Path,
    detected_objects: list[str],
    signals: FrameSignals,
    timestamp_s: float,
    client: OpenAI | None = None,
) -> FrameEvent:
    client = client or _get_client()

    objects_line = ", ".join(detected_objects) if detected_objects else "none"
    signals_line = _signals_summary(signals)
    prompt = (
        f"Confirmed objects detected in this frame by a separate detector: {objects_line}.\n"
        f"Computed motion data for this frame, from object tracking across the video "
        f"(not guaranteed to be meaningful on its own): {signals_line}.\n"
        "Describe only what is visible in the image. Do not state a location, "
        "casualty count, or any statistic unless it is directly and unambiguously "
        "readable from the image itself. If you are not sure, do not guess.\n"
        "Separately, in 'notable_event': if the image and/or the motion data together "
        "indicate a specific notable event — a collision, a gathering of people, a new "
        "person or vehicle arriving, an object stopping suddenly — describe that event "
        "in your own words in one short sentence, e.g. 'a person walks toward the fire' "
        "or 'the train comes to a stop'. Only report an event with real evidence in the "
        "image or the motion data. If nothing notable is happening, or you are not sure, "
        "set 'notable_event' to null. Do not invent an event type this data doesn't "
        "support. Never output the literal words 'notable event', the field name, or "
        "any other placeholder text as the value — either write a real, specific "
        "sentence describing what is happening, or use null."
    )

    schema = FrameEvent.model_json_schema()
    schema["required"] = [
        "timestamp_s",
        "detected_objects",
        "description",
        "notable_event",
    ]
    # The bare field name alone (as auto-titled by pydantic, "Notable Event") gave the
    # small local VLM nothing to anchor content generation on beyond the property key
    # itself — empirically, it started literally echoing "notable_event" back as the
    # string value on frames with weak/ambiguous motion signals (reproduced 4/4 times
    # on one real frame). Overriding the schema's title/description here to spell out
    # what a valid value looks like (or null) closes that loop without touching
    # gozcu/schema.py, which stays a plain data model.
    schema["properties"]["notable_event"]["description"] = (
        "A short, specific sentence describing a real notable event grounded in the "
        "image or motion data, or null if there is none. Must never be the literal "
        "text 'notable_event' or any other placeholder."
    )
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
    # `notable_event` is under the exact same strict-JSON-schema maxLength-enforced
    # decoding path as `description` and carries the identical truncation risk
    # (trailing control chars, mid-word cutoffs). Unlike `description`, there is no
    # ground-truth overwrite afterward for `notable_event` — it's the VLM's own
    # interpretation and nothing replaces it — so a truncation artifact here has no
    # other safety net catching it. Sanitize it the same way whenever it's non-null.
    if event.notable_event is not None:
        max_notable_event_length = schema["properties"]["notable_event"].get("maxLength", 200)
        event.notable_event = _sanitize_description(event.notable_event, max_notable_event_length)
    event.timestamp_s = timestamp_s
    event.detected_objects = detected_objects
    return event
