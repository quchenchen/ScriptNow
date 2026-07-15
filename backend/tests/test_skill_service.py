"""Unit tests for :mod:`app.services.skill_service`.

Cover:
- Frontmatter parsing (well-formed, missing fields, quotes handled)
- list_available_skills scans recursively
- activate_skill returns body + resource list
- read_skill_file blocks ../ traversal + absolute paths
- SkillNotFound / SkillPathViolation raised where expected
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services import skill_service as sk


def _write_skill(root: Path, rel: str, name: str, desc: str, body: str = "正文") -> Path:
    """Convenience: write a well-formed SKILL.md at ``root/rel``."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nname: {name}\ndescription: {desc}\n---\n\n{body}",
        encoding="utf-8",
    )
    return path


# ── parse_frontmatter ────────────────────────────────────────

def test_parse_frontmatter_extracts_name_and_description():
    fm = sk.parse_frontmatter("---\nname: 灵感孵化 Agent\ndescription: 一句话描述\n---\n正文")
    assert fm["name"] == "灵感孵化 Agent"
    assert fm["description"] == "一句话描述"


def test_parse_frontmatter_strips_surrounding_quotes():
    fm = sk.parse_frontmatter('---\nname: "A"\ndescription: \'B\'\n---\n')
    assert fm["name"] == "A"
    assert fm["description"] == "B"


def test_parse_frontmatter_missing_block_raises():
    with pytest.raises(sk.SkillFrontmatterError):
        sk.parse_frontmatter("no frontmatter here")


def test_parse_frontmatter_missing_required_field_raises():
    with pytest.raises(sk.SkillFrontmatterError):
        sk.parse_frontmatter("---\nname: only\n---\n")


# ── list_available_skills ────────────────────────────────────

def test_list_available_skills_returns_root_mds(tmp_path):
    _write_skill(tmp_path, "a.md", "TechA", "does A")
    _write_skill(tmp_path, "b.md", "TechB", "does B")
    (tmp_path / "no_frontmatter.md").write_text("just a note", encoding="utf-8")

    metas = sk.list_available_skills(tmp_path)
    names = {m.name for m in metas}
    assert names == {"TechA", "TechB"}


def test_list_available_skills_recurses_into_subdirs(tmp_path):
    _write_skill(tmp_path, "root_skill.md", "Root", "root")
    _write_skill(tmp_path, "story_skills/pack/README.md", "PackA", "pack A")
    _write_skill(
        tmp_path,
        "story_skills/pack/director_skills/deep.md",
        "Deep", "deep skill",
    )
    metas = sk.list_available_skills(tmp_path)
    names = {m.name for m in metas}
    assert names == {"Root", "PackA", "Deep"}


def test_list_available_skills_empty_root(tmp_path):
    assert sk.list_available_skills(tmp_path) == []


# ── build_skill_menu_prompt ──────────────────────────────────

def test_menu_prompt_contains_available_skills_tag(tmp_path):
    _write_skill(tmp_path, "x.md", "Alpha", "does alpha")
    prompt = sk.build_skill_menu_prompt(tmp_path)
    assert "<available_skills>" in prompt
    assert "<name>Alpha</name>" in prompt
    assert "<description>does alpha</description>" in prompt


def test_menu_prompt_empty_when_no_skills(tmp_path):
    assert sk.build_skill_menu_prompt(tmp_path) == ""


# ── activate_skill ───────────────────────────────────────────

def test_activate_skill_returns_body_stripped(tmp_path):
    _write_skill(tmp_path, "a.md", "Alpha", "d", body="# Body\n\n主体内容。")
    result = sk.activate_skill("Alpha", root=tmp_path)
    assert result["name"] == "Alpha"
    assert "Body" in result["body"]
    assert "---" not in result["body"]  # frontmatter stripped
    assert result["filename"] == "a.md"


def test_activate_skill_unknown_raises(tmp_path):
    _write_skill(tmp_path, "a.md", "Alpha", "d")
    with pytest.raises(sk.SkillNotFound):
        sk.activate_skill("DoesNotExist", root=tmp_path)


def test_activate_skill_lists_same_folder_resources(tmp_path):
    _write_skill(tmp_path, "story_skills/pack/README.md", "PackA", "pack A")
    _write_skill(
        tmp_path,
        "story_skills/pack/director_skills/deep.md",
        "Deep", "deep",
    )
    # non-frontmatter resource still counted (rglob picks all .md)
    (tmp_path / "story_skills/pack/notes.md").write_text("misc notes", encoding="utf-8")

    result = sk.activate_skill("PackA", root=tmp_path)
    assert any("director_skills" in r for r in result["resources"])
    assert any(r.endswith("notes.md") for r in result["resources"])


# ── read_skill_file ──────────────────────────────────────────

def test_read_skill_file_returns_content(tmp_path):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes/a.md").write_text("hello", encoding="utf-8")
    assert sk.read_skill_file("notes/a.md", root=tmp_path) == "hello"


def test_read_skill_file_blocks_parent_dir_traversal(tmp_path):
    # Attempt to escape via ../
    (tmp_path.parent / "secret.md").write_text("top secret", encoding="utf-8")
    with pytest.raises(sk.SkillPathViolation):
        sk.read_skill_file("../secret.md", root=tmp_path)


def test_read_skill_file_blocks_absolute_path(tmp_path):
    with pytest.raises(sk.SkillPathViolation):
        sk.read_skill_file("/etc/passwd", root=tmp_path)


def test_read_skill_file_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        sk.read_skill_file("nope.md", root=tmp_path)


def test_read_skill_file_empty_rel_raises(tmp_path):
    with pytest.raises(ValueError):
        sk.read_skill_file("", root=tmp_path)


# ── real skills/ directory smoke test ────────────────────────

def test_real_skills_directory_lists_execution_skills():
    """The 4 execution skill files ship with the repo — the loader must find them."""
    metas = sk.list_available_skills()
    names = {m.name for m in metas}
    for expected in ("灵感孵化 Agent", "三幕架构 Agent", "剧本撰写 Agent", "剧本审核 Agent"):
        assert expected in names, f"missing shipped skill: {expected}"


def test_real_skills_directory_activates_story_skill():
    """Story-skill packs (README.md at subdir root) should activate cleanly."""
    result = sk.activate_skill("男频爽文短剧")
    assert result["body"]
    # The male_lead_shuang pack ships one director skill file
    assert any("director_planning_narrative" in r for r in result["resources"])
