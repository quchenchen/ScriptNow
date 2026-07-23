from pydantic import BaseModel, ConfigDict, Field

from scriptflow_v7.novel.contracts import NovelBlock


class NovelPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    base_revision_id: str
    block_id: str
    expected_text: str
    replacement: tuple[NovelBlock, ...] = Field(min_length=1)
