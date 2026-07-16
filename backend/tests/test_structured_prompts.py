"""Tests for app.agents.prompts — structured interaction protocol."""
import json
import re

import pytest

from app.agents.prompts import (
    INTERACTION_PROTOCOL,
    STAGE_PROMPTS,
    build_structured_prompt,
    wrap_choice,
    wrap_confirm,
    wrap_status,
)


class TestWrapHelpers:
    """Ensure the wrap_* helpers produce parseable blocks."""

    def test_wrap_choice_produces_valid_json(self):
        block = wrap_choice("Pick one", [
            {"id": "A", "title": "Foo", "desc": "bar"},
            {"id": "B", "title": "Baz", "desc": "qux"},
        ], default="A")
        assert "<!--SF:CHOICE-->" in block
        assert "<!--/SF:CHOICE-->" in block
        # Extract and parse JSON
        match = re.search(r"<!--SF:CHOICE-->\n(.+?)\n<!--/SF:CHOICE-->", block, re.S)
        assert match
        data = json.loads(match.group(1))
        assert data["question"] == "Pick one"
        assert len(data["options"]) == 2
        assert data["default"] == "A"

    def test_wrap_status(self):
        block = wrap_status("创意孵化", "生成方案", "3 个差异化")
        match = re.search(r"<!--SF:STATUS-->\n(.+?)\n<!--/SF:STATUS-->", block, re.S)
        assert match
        data = json.loads(match.group(1))
        assert data["stage"] == "创意孵化"
        assert data["step"] == "生成方案"
        assert data["detail"] == "3 个差异化"

    def test_wrap_confirm(self):
        block = wrap_confirm("架构已生成", ["梗概OK", "角色5人"])
        match = re.search(r"<!--SF:CONFIRM-->\n(.+?)\n<!--/SF:CONFIRM-->", block, re.S)
        assert match
        data = json.loads(match.group(1))
        assert data["summary"] == "架构已生成"
        assert len(data["items"]) == 2


class TestBuildStructuredPrompt:
    """Verify the composed prompt includes protocol + stage instructions."""

    def test_ideation_includes_protocol_and_stage(self):
        prompt = build_structured_prompt("ideation")
        assert "交互协议" in prompt
        assert "创意孵化阶段" in prompt
        assert "SF:CHOICE" in prompt

    def test_structure_includes_confirm_example(self):
        prompt = build_structured_prompt("structure")
        assert "SF:CONFIRM" in prompt
        assert "角色设定" in prompt

    def test_writing_is_minimal(self):
        prompt = build_structured_prompt("writing")
        assert "剧本撰写阶段" in prompt
        # Writing stage doesn't push a choice block
        assert "SF:CHOICE" not in STAGE_PROMPTS["writing"]

    def test_unknown_stage_still_gets_protocol(self):
        prompt = build_structured_prompt("unknown_thing")
        assert "交互协议" in prompt
        # But no stage-specific section
        assert "阶段" not in prompt.split("交互协议")[0]

    def test_protocol_contains_format_rules(self):
        assert "每次回复最多包含" in INTERACTION_PROTOCOL
        assert "1 个选择块" in INTERACTION_PROTOCOL
