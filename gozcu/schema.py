from pydantic import BaseModel, ConfigDict, Field


class FrameEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp_s: float
    detected_objects: list[str]
    description: str = Field(max_length=300)
    notable_event: str | None = Field(default=None, max_length=200)


class PipelineResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    video_path: str
    events: list[FrameEvent]
