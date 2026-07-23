from pydantic import BaseModel, ConfigDict, Field

from scriptflow_v7.script.contracts import ScriptBlock


class ScriptPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    base_revision_id: str
    para_id: str
    expected_text: str
    replacement: tuple[ScriptBlock, ...] = Field(min_length=1)
