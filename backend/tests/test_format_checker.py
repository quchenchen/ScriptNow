"""Tests for the script format checker."""
from __future__ import annotations


def test_clean_script_scores_100():
    from app.services.format_checker import check

    text = (
        "【场景1】咖啡馆·白天\n"
        "△推门。\n"
        "阿明：你终于来了。\n"
        "小红：还好吧？\n"
        "\n"
        "【场景2】街道·夜\n"
        "△下雨。\n"
        "阿明：走吧。\n"
    )
    r = check(text)
    assert r["score"] == 100
    assert r["issues"] == []


def test_missing_scene_heading_flagged():
    from app.services.format_checker import check

    text = "阿明：你终于来了。\n△推门。\n"
    r = check(text)
    types = {iss["type"] for iss in r["issues"]}
    assert "missing_scene_heading" in types


def test_markdown_residue_flagged():
    from app.services.format_checker import check

    text = (
        "【场景1】咖啡馆·白天\n"
        "△**推门**。\n"
        "阿明：你 `终于` 来了。\n"
    )
    r = check(text)
    types = {iss["type"] for iss in r["issues"]}
    assert "markdown_residue" in types


def test_markdown_heading_flagged():
    from app.services.format_checker import check

    text = "# 剧集标题\n【场景1】家·晚\n阿明：早。\n"
    r = check(text)
    types = {iss["type"] for iss in r["issues"]}
    assert "markdown_residue" in types


def test_markdown_code_fence_flagged():
    from app.services.format_checker import check

    text = "```\n【场景1】家·晚\n阿明：早。\n```\n"
    r = check(text)
    types = {iss["type"] for iss in r["issues"]}
    assert "markdown_residue" in types


def test_half_width_colon_in_dialog_flagged():
    from app.services.format_checker import check

    text = (
        "【场景1】家·晚\n"
        "阿明:你好。\n"
        "小红:早。\n"
    )
    r = check(text)
    types = {iss["type"] for iss in r["issues"]}
    assert "dialog_half_width_colon" in types


def test_placeholder_left_in_flagged():
    from app.services.format_checker import check

    text = (
        "【场景1】家·晚\n"
        "对白：\n"
        "阿明：好的。\n"
    )
    r = check(text)
    types = {iss["type"] for iss in r["issues"]}
    assert "placeholder_left_in" in types


def test_excessive_blank_lines_flagged():
    from app.services.format_checker import check

    text = (
        "【场景1】家·晚\n"
        "阿明：早。\n\n\n\n\n"
        "小红：早。\n"
    )
    r = check(text)
    types = {iss["type"] for iss in r["issues"]}
    assert "excessive_blank_lines" in types


def test_empty_text_scores_100_no_issues():
    from app.services.format_checker import check

    r = check("")
    assert r["score"] == 100
    assert r["issues"] == []


def test_combined_issues_stack_up_score():
    from app.services.format_checker import check

    text = (
        "# 第 1 集\n"
        "```\n"
        "阿明:**好**\n"
        "对白：\n"
        "```\n"
    )
    r = check(text)
    # Missing scene head (high=15) + markdown_residue (high=15) +
    # half-width colon (medium=10) + placeholder (high=15) → 100-55 = 45
    assert r["score"] <= 60
    types = {iss["type"] for iss in r["issues"]}
    assert "missing_scene_heading" in types
    assert "markdown_residue" in types
    assert "placeholder_left_in" in types


def test_issues_for_ralph_returns_ralph_shape():
    from app.services.format_checker import issues_for_ralph

    text = "**bold**"
    issues = issues_for_ralph(text)
    assert issues
    keys = set(issues[0].keys())
    for required in ("severity", "type", "description", "suggestion"):
        assert required in keys
