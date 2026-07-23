import pytest
from pydantic import ValidationError

from scriptflow_v7.novel import NovelBlock
from scriptflow_v7.script import ScriptBlock


def test_script_rejects_novel_block_type() -> None:
    with pytest.raises(ValidationError):
        ScriptBlock(para_id="p1", type="prose", text="A paragraph")


def test_novel_rejects_script_block_type() -> None:
    with pytest.raises(ValidationError):
        NovelBlock(block_id="b1", type="slugline", text="INT. ROOM - DAY")
