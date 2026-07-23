from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class NovelBlockType(StrEnum):
    HEADING = "heading"
    PROSE = "prose"
    DIALOGUE = "dialogue"
    QUOTE = "quote"
    DIVIDER = "divider"


NOVEL_BLOCK_TYPES = frozenset(item.value for item in NovelBlockType)


class NovelBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    block_id: str
    type: NovelBlockType
    text: str
