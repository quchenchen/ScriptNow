from pydantic import BaseModel, ConfigDict, Field


class NovelStoryBeat(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    objective: str
    anchor_ids: tuple[str, ...] = ()


class Chapter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    ordinal: int = Field(ge=1)
    title: str
    target_words: int = Field(gt=0)
    point_of_view: str | None = None
    beats: tuple[NovelStoryBeat, ...] = ()


class Volume(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    ordinal: int = Field(ge=1)
    title: str
    chapters: tuple[Chapter, ...] = ()
