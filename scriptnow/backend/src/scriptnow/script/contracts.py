from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ScriptBlockType(StrEnum):
    SLUGLINE = "slugline"
    ACTION = "action"
    CHARACTER = "character"
    DIALOGUE = "dialogue"
    TRANSITION = "transition"


SCRIPT_BLOCK_TYPES = frozenset(item.value for item in ScriptBlockType)


class ScriptBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    para_id: str
    type: ScriptBlockType
    text: str
