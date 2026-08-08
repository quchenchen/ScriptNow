from pydantic import BaseModel, ConfigDict, Field


class ScriptStoryBeat(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    objective: str
    anchor_ids: tuple[str, ...] = ()


class Scene(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    ordinal: int = Field(ge=1)
    title: str
    duration_seconds_target: int = Field(ge=0)
    beats: tuple[ScriptStoryBeat, ...] = ()


class Episode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    ordinal: int = Field(ge=1)
    title: str
    scenes: tuple[Scene, ...] = ()
