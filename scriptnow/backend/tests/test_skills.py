import json
from pathlib import Path

import pytest

from scriptnow.platform.skills import (
    CreativeProfile,
    SkillCatalog,
    SkillCatalogError,
    SkillConflictError,
    SkillResolver,
    resolve_skills_root,
)

SKILLS_ROOT = Path(__file__).parents[1] / "skills"


def test_skills_root_honors_runtime_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SCRIPTNOW_SKILLS_ROOT", str(tmp_path))
    assert resolve_skills_root() == tmp_path.resolve()


def test_catalog_is_valid_and_keeps_creative_domains_isolated() -> None:
    catalog = SkillCatalog(SKILLS_ROOT)
    all_skills = catalog.scan()
    assert {item.domain for item in all_skills} >= {"platform", "novel", "script"}
    novel = {item.name for item in catalog.for_domain("novel")}
    script = {item.name for item in catalog.for_domain("script")}
    assert "novel-write" in novel and "script-write" not in novel
    assert "script-write" in script and "novel-write" not in script
    assert "project-diagnose" in novel & script


def test_editor_skills_can_coexist_without_entering_creative_domains(tmp_path: Path) -> None:
    documents = {
        "platform/project-diagnose": (
            "---\nname: project-diagnose\ndescription: Diagnose\n---\nDiagnose."
        ),
        "script/script-write": "---\nname: script-write\ndescription: Write script\n---\nWrite.",
        "novel/novel-write": "---\nname: novel-write\ndescription: Write novel\n---\nWrite.",
        "editor/editorial-source-selection": (
            "---\nname: editorial-source-selection\n"
            "description: Select editorial sources\n---\nSelect sources."
        ),
    }
    for relative, content in documents.items():
        path = tmp_path / relative / "SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text(content, encoding="utf-8")

    catalog = SkillCatalog(tmp_path)

    assert {item.name for item in catalog.for_domain("editor")} == {
        "editorial-source-selection",
        "project-diagnose",
    }
    assert "editorial-source-selection" not in {
        item.name for item in catalog.for_domain("script")
    }
    assert "editorial-source-selection" not in {
        item.name for item in catalog.for_domain("novel")
    }


@pytest.mark.asyncio
async def test_catalog_builds_agentscope_progressive_loader() -> None:
    catalog = SkillCatalog(SKILLS_ROOT)
    loaded = await catalog.loader("novel").list_skills()
    assert {item.name for item in loaded} >= {
        "novel-ideate",
        "novel-plan",
        "novel-write",
        "novel-review",
    }


@pytest.mark.asyncio
async def test_plan_loader_exposes_only_selected_skills() -> None:
    catalog = SkillCatalog(SKILLS_ROOT)
    loaders = catalog.loaders_for_plan(
        domain="novel", skill_keys=["novel-write", "project-diagnose"]
    )
    loaded = [skill for loader in loaders for skill in await loader.list_skills()]

    assert {skill.name for skill in loaded} == {"novel-write", "project-diagnose"}
    with pytest.raises(SkillCatalogError, match="unknown skills"):
        catalog.loaders_for_plan(domain="novel", skill_keys=["script-write"])


def test_role_selection_and_fingerprint_are_deterministic() -> None:
    catalog = SkillCatalog(SKILLS_ROOT)
    writer = catalog.for_role(domain="novel", role_key="writer")
    assert [item.name for item in writer] == ["novel-write", "project-diagnose"]
    assert catalog.fingerprint(domain="novel", role_key="writer") == catalog.fingerprint(
        domain="novel", role_key="writer"
    )


def test_director_and_architect_use_runtime_role_keys() -> None:
    catalog = SkillCatalog(SKILLS_ROOT)
    director = {item.name for item in catalog.for_role(domain="script", role_key="director")}
    architect = {item.name for item in catalog.for_role(domain="script", role_key="architect")}

    assert "script-develop" in director
    assert "script-storymap" in architect


def test_catalog_rejects_reference_path_escape(tmp_path: Path) -> None:
    skill = tmp_path / "novel" / "unsafe"
    skill.mkdir(parents=True)
    (tmp_path / "secret.md").write_text("secret", encoding="utf-8")
    (skill / "SKILL.md").write_text(
        "---\nname: unsafe\ndescription: unsafe\n---\n[escape](../../secret.md)", encoding="utf-8"
    )
    with pytest.raises(SkillCatalogError, match="escapes"):
        SkillCatalog(tmp_path).scan()


def test_skill_update_is_validated_and_uses_digest_concurrency(tmp_path: Path) -> None:
    skill = tmp_path / "platform" / "editable"
    skill.mkdir(parents=True)
    (skill / "guide.md").write_text("guide", encoding="utf-8")
    (skill / "SKILL.md").write_text(
        "---\nname: editable\ndescription: Before\n---\nRead [guide](guide.md).\n",
        encoding="utf-8",
    )
    catalog = SkillCatalog(tmp_path)
    before, _ = catalog.detail("editable")

    after = catalog.update(
        name="editable",
        description="After",
        instructions="Updated instructions with [guide](guide.md).",
        expected_digest=before.digest,
    )

    assert after.description == "After"
    assert after.digest != before.digest
    assert catalog.detail("editable")[1] == "Updated instructions with [guide](guide.md)."
    with pytest.raises(SkillConflictError, match="changed"):
        catalog.update(
            name="editable",
            description="Stale",
            instructions="Stale instructions",
            expected_digest=before.digest,
        )


def test_skill_resolver_selects_role_stage_and_creative_style(tmp_path: Path) -> None:
    documents = {
        "platform/project-diagnose": "---\nname: project-diagnose\ndescription: Diagnose\n---\nDiagnose.",
        "novel/novel-write": "---\nname: novel-write\ndescription: Write\n---\nWrite.",
        "novel/novel-scifi-intimacy": (
            "---\nname: novel-scifi-intimacy\ndescription: Style pack\n"
            "roles: [writer]\nstages: [writing]\ngenres: [science-fiction]\n"
            "themes: [human-ai]\nstyles: [restrained]\nselection_priority: 5\n---\nAdapt style."
        ),
        "novel/novel-romance-comedy": (
            "---\nname: novel-romance-comedy\ndescription: Wrong pack\n"
            "roles: [writer]\nstages: [writing]\ngenres: [romcom]\n---\nWrong style."
        ),
    }
    for relative, content in documents.items():
        directory = tmp_path / relative
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(content, encoding="utf-8")
    profile = CreativeProfile.from_direction(
        medium="novel",
        direction={
            "language": "en-US",
            "world_setting": "记忆可以复制，但人格不可复制。",
            "genre": "science fiction, science-fiction",
            "theme": "human-ai",
            "tone": "restrained",
        },
    )

    assert profile.language == "en-US"
    assert profile.as_dict()["language"] == "en-US"
    assert profile.world_setting == "记忆可以复制，但人格不可复制。"

    plan = SkillResolver(SkillCatalog(tmp_path)).resolve(
        profile=profile, role_key="writer", stage="writing"
    )

    assert [item.skill.name for item in plan.selections] == [
        "novel-write",
        "project-diagnose",
        "novel-scifi-intimacy",
    ]
    assert plan.selections[-1].layer == "style_pack"
    assert plan.selections[-1].score == 95
    assert "novel-romance-comedy" not in {item.skill.name for item in plan.selections}


def test_structure_selection_mounts_the_domain_structure_skill() -> None:
    profile = CreativeProfile.from_direction(
        medium="script", direction={"structure": "eight_sequence"}
    )

    plan = SkillResolver(SkillCatalog(SKILLS_ROOT)).resolve(
        profile=profile, role_key="architect", stage="planning"
    )

    selection = next(
        item for item in plan.selections if item.skill.name == "script-structure-planning"
    )
    assert selection.layer == "style_pack"
    assert "结构匹配：eight-sequence" in selection.reasons


@pytest.mark.parametrize(
    ("script_format", "expected", "excluded"),
    [
        ("chinese", "script-format-chinese", "script-format-hollywood"),
        ("hollywood", "script-format-hollywood", "script-format-chinese"),
    ],
)
def test_script_writer_mounts_only_the_selected_delivery_format(
    script_format: str, expected: str, excluded: str
) -> None:
    profile = CreativeProfile.from_direction(
        medium="script",
        direction={
            "language": "zh-CN" if script_format == "chinese" else "en-US",
            "script_format": script_format,
        },
    )

    plan = SkillResolver(SkillCatalog(SKILLS_ROOT)).resolve(
        profile=profile, role_key="writer", stage="writing"
    )
    selected = {item.skill.name for item in plan.selections}

    assert profile.formats == (script_format,)
    assert profile.as_dict()["formats"] == [script_format]
    assert {"script-write", expected} <= selected
    assert excluded not in selected
    format_selection = next(item for item in plan.selections if item.skill.name == expected)
    assert format_selection.layer == "style_pack"
    assert f"格式匹配：{script_format}" in format_selection.reasons


def test_script_reviewer_uses_same_locked_format_as_writer() -> None:
    profile = CreativeProfile.from_direction(
        medium="script", direction={"script_format": "hollywood"}
    )

    plan = SkillResolver(SkillCatalog(SKILLS_ROOT)).resolve(
        profile=profile, role_key="reviewer", stage="review"
    )
    selected = {item.skill.name for item in plan.selections}

    assert {"script-review", "script-format-hollywood"} <= selected
    assert "script-format-chinese" not in selected


def test_gothic_werewolf_project_mounts_voice_specific_writer_and_reviewer() -> None:
    profile = CreativeProfile.from_direction(
        medium="novel",
        direction={
            "language": "en-US",
            "genre": "奇幻, 爱情, 悬疑, 暗黑奇幻, 狼人, 哥特悬疑",
            "tone": "成熟、幽暗、感官克制、人物关系驱动",
            "structure": "three_act",
        },
    )

    writer = SkillResolver(SkillCatalog(SKILLS_ROOT)).resolve(
        profile=profile, role_key="writer", stage="writing"
    )
    reviewer = SkillResolver(SkillCatalog(SKILLS_ROOT)).resolve(
        profile=profile, role_key="reviewer", stage="review"
    )

    assert "novel-gothic-bond-writer" in {item.skill.name for item in writer.selections}
    assert "novel-gothic-bond-reviewer" in {item.skill.name for item in reviewer.selections}
    assert profile.genres == (
        "fantasy",
        "romance",
        "mystery",
        "dark-fantasy",
        "werewolf",
        "gothic-mystery",
    )


def test_chinese_fanqie_project_composes_platform_genre_and_quality_layers() -> None:
    profile = CreativeProfile.from_direction(
        medium="novel",
        direction={"language": "zh-CN", "genre": "都市脑洞, 系统", "platform": "番茄"},
    )

    writer = SkillResolver(SkillCatalog(SKILLS_ROOT)).resolve(
        profile=profile, role_key="writer", stage="writing"
    )
    selected = {item.skill.name for item in writer.selections}

    assert profile.platforms == ("fanqie",)
    assert {
        "novel-platform-fanqie",
        "novel-cn-urban-power",
        "novel-serial-quality-review",
    } <= selected
    assert "novel-platform-global-serial" not in selected
    assert not any(name.startswith("novel-en-") for name in selected)


def test_english_werewolf_project_uses_global_and_paranormal_skills_only() -> None:
    profile = CreativeProfile.from_direction(
        medium="novel",
        direction={
            "language": "en_US",
            "genre": "werewolf romance, paranormal romance",
            "target_platform": "Webnovel",
        },
    )

    writer = SkillResolver(SkillCatalog(SKILLS_ROOT)).resolve(
        profile=profile, role_key="writer", stage="writing"
    )
    selected = {item.skill.name for item in writer.selections}

    assert profile.language == "en-US"
    assert profile.platforms == ("webnovel",)
    assert "novel-platform-global-serial" in selected
    assert "novel-en-paranormal-romance" in selected
    assert "novel-serial-quality-review" in selected
    assert "novel-platform-fanqie" not in selected
    assert not any(name.startswith("novel-cn-") for name in selected)


def test_language_specific_skill_is_ineligible_even_when_genre_matches(tmp_path: Path) -> None:
    documents = {
        "platform/project-diagnose": "---\nname: project-diagnose\ndescription: Diagnose\n---\nDiagnose.",
        "novel/novel-write": "---\nname: novel-write\ndescription: Write\n---\nWrite.",
        "novel/english-only": (
            "---\nname: english-only\ndescription: English\nroles: [writer]\n"
            "stages: [writing]\ngenres: [romance]\nlanguages: [en-US]\n---\nEnglish."
        ),
    }
    for relative, content in documents.items():
        directory = tmp_path / relative
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(content, encoding="utf-8")

    profile = CreativeProfile.from_direction(
        medium="novel", direction={"language": "zh-CN", "genre": "romance"}
    )
    plan = SkillResolver(SkillCatalog(tmp_path)).resolve(
        profile=profile, role_key="writer", stage="writing"
    )

    assert "english-only" not in {item.skill.name for item in plan.selections}


def test_runtime_novel_skills_do_not_contain_scaffold_placeholders() -> None:
    catalog = SkillCatalog(SKILLS_ROOT)

    for skill in catalog.for_domain("novel"):
        _, instructions = catalog.detail(skill.name)
        assert "[TODO" not in skill.description
        assert "[TODO" not in instructions


@pytest.mark.parametrize(
    ("direction", "expected", "excluded"),
    [
        (
            {"language": "zh-CN", "platform": "番茄", "genre": "玄幻, 升级"},
            {"novel-platform-fanqie", "novel-cn-fantasy-progression"},
            {"novel-platform-global-serial", "novel-en-speculative-serial"},
        ),
        (
            {"language": "en-US", "platform": "Webnovel", "genre": "science fiction"},
            {"novel-platform-global-serial", "novel-en-speculative-serial"},
            {"novel-platform-fanqie", "novel-cn-fantasy-progression"},
        ),
        (
            {"language": "en-GB", "platform": "Wattpad", "genre": "romance"},
            {"novel-platform-global-serial", "novel-en-commercial-romance"},
            {"novel-platform-fanqie", "novel-cn-romance-relations"},
        ),
        (
            {"language": "en-US", "platform": "GoodNovel", "genre": "重生, 现代言情, 追妻"},
            {"novel-platform-global-serial", "novel-en-commercial-romance"},
            {"novel-platform-fanqie", "novel-cn-romance-relations"},
        ),
    ],
)
def test_novel_skill_selection_matrix(
    direction: dict[str, str], expected: set[str], excluded: set[str]
) -> None:
    profile = CreativeProfile.from_direction(medium="novel", direction=direction)
    plan = SkillResolver(SkillCatalog(SKILLS_ROOT)).resolve(
        profile=profile, role_key="writer", stage="writing"
    )
    selected = {item.skill.name for item in plan.selections}

    assert expected <= selected
    assert not selected & excluded


def test_source_distiller_is_explicit_and_stage_scoped() -> None:
    profile = CreativeProfile.from_direction(
        medium="novel",
        direction={"language": "en-US", "platform": "Webnovel", "genre": "werewolf romance"},
    )
    resolver = SkillResolver(SkillCatalog(SKILLS_ROOT))

    ordinary = resolver.resolve(profile=profile, role_key="reviewer", stage="review")
    assert "novel-source-distiller" not in {
        selection.skill.name for selection in ordinary.selections
    }
    explicit = resolver.resolve(
        profile=profile,
        role_key="reviewer",
        stage="source-analysis",
        explicit_skill_keys=("novel-source-distiller",),
    )
    selected = {selection.skill.name: selection for selection in explicit.selections}
    assert selected["novel-source-distiller"].layer == "explicit"
    with pytest.raises(SkillCatalogError, match="does not support stage"):
        resolver.resolve(
            profile=profile,
            role_key="reviewer",
            stage="review",
            explicit_skill_keys=("novel-source-distiller",),
        )


def test_novel_optional_skills_require_executable_admission_baseline() -> None:
    catalog = SkillCatalog(SKILLS_ROOT)
    optional = [skill for skill in catalog.for_domain("novel") if skill.roles]

    assert optional
    for skill in optional:
        assert skill.admission_status == "admitted", skill.name
        assert skill.admission_baseline == "novel-skill-baseline-v1", skill.name
        assert len(skill.admission_cases) == 3, skill.name
        assert any("positive" in case or "explicit" in case for case in skill.admission_cases)
        assert any("negative" in case for case in skill.admission_cases)
        assert any("regression" in case for case in skill.admission_cases)


def test_script_skills_require_executable_admission_baseline() -> None:
    catalog = SkillCatalog(SKILLS_ROOT)
    routed = [skill for skill in catalog.for_domain("script") if skill.roles]

    assert {skill.name for skill in routed} == {
        "script-cn-short-drama",
        "script-develop",
        "script-doctor-roundtable",
        "script-format-chinese",
        "script-format-hollywood",
        "script-review",
        "script-screen-creative-review",
        "script-source-distiller",
        "script-storymap",
        "script-structure-planning",
        "script-write",
    }
    for skill in routed:
        assert skill.admission_status == "admitted", skill.name
        assert skill.admission_baseline == "script-skill-baseline-v1", skill.name
        assert len(skill.admission_cases) == 3, skill.name
        assert "positive" in skill.admission_cases[0], skill.name
        assert "negative" in skill.admission_cases[1], skill.name
        assert skill.admission_cases[2].endswith("regression"), skill.name
        assert skill.stages, skill.name


def test_unadmitted_script_skill_cannot_be_auto_or_explicitly_mounted(
    tmp_path: Path,
) -> None:
    documents = {
        "platform/project-diagnose": (
            "---\nname: project-diagnose\ndescription: Diagnose\n---\nDiagnose."
        ),
        "script/script-write": (
            "---\nname: script-write\ndescription: Write\n"
            "metadata:\n  scriptnow:\n    roles: [writer]\n    stages: [writing]\n"
            "---\nWrite."
        ),
        "script/candidate-format": (
            "---\nname: candidate-format\ndescription: Candidate\n"
            "metadata:\n  scriptnow:\n    roles: [writer]\n    stages: [writing]\n"
            "    formats: [chinese]\n---\nCandidate."
        ),
    }
    for relative, content in documents.items():
        directory = tmp_path / relative
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(content, encoding="utf-8")
    (tmp_path / "admission.json").write_text(
        json.dumps(
            {
                "version": 1,
                "domains": {
                    "script": {
                        "script-write": {
                            "status": "admitted",
                            "baseline": "test-v1",
                            "cases": ["positive", "negative", "regression"],
                        },
                        "candidate-format": {
                            "status": "incubating",
                            "baseline": "test-v1",
                            "cases": [],
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    resolver = SkillResolver(SkillCatalog(tmp_path))
    profile = CreativeProfile.from_direction(
        medium="script", direction={"script_format": "chinese"}
    )

    automatic = resolver.resolve(profile=profile, role_key="writer", stage="writing")
    assert "candidate-format" not in {item.skill.name for item in automatic.selections}
    with pytest.raises(SkillCatalogError, match="has not passed admission"):
        resolver.resolve(
            profile=profile,
            role_key="writer",
            stage="writing",
            explicit_skill_keys=("candidate-format",),
        )
    with pytest.raises(SkillCatalogError, match="unadmitted skills"):
        resolver.catalog.loaders_for_plan(
            domain="script", skill_keys=["candidate-format"]
        )


def test_foundational_novel_review_skill_has_an_admission_record() -> None:
    catalog = SkillCatalog(SKILLS_ROOT)
    skill = next(item for item in catalog.for_domain("novel") if item.name == "novel-review")

    assert skill.admission_status == "admitted"
    assert skill.admission_baseline == "novel-skill-baseline-v1"
    assert skill.admission_cases == (
        "novel-review-explicit",
        "wrong-domain-negative",
        "novel-review-regression",
    )


def test_admitted_novel_skills_execute_positive_and_negative_routing_cases() -> None:
    catalog = SkillCatalog(SKILLS_ROOT)
    resolver = SkillResolver(catalog, optional_limit=20)
    optional = [skill for skill in catalog.for_domain("novel") if skill.roles]

    for skill in optional:
        language = skill.languages[0] if skill.languages else "en-US"
        direction: dict[str, object] = {
            "language": language,
            "platforms": list(skill.platforms),
            "genres": list(skill.genres),
            "themes": list(skill.themes),
            "styles": list(skill.styles),
            "structures": list(skill.structures),
        }
        profile = CreativeProfile.from_direction(medium="novel", direction=direction)
        explicit = (
            (skill.name,)
            if skill.name in {"novel-source-distiller", "novel-build-story-graph"}
            else ()
        )
        positive = resolver.resolve(
            profile=profile,
            role_key=skill.roles[0],
            stage=skill.stages[0],
            explicit_skill_keys=explicit,
        )
        assert skill.name in {item.skill.name for item in positive.selections}, skill.name

        alternative_language = next(
            (
                candidate
                for candidate in ("zh-CN", "en-US", "ja-JP")
                if not any(candidate.split("-")[0] == item.split("-")[0] for item in skill.languages)
            ),
            None,
        )
        if skill.languages and alternative_language:
            negative_profile = CreativeProfile.from_direction(
                medium="novel",
                direction={**direction, "language": alternative_language},
            )
            negative = resolver.resolve(
                profile=negative_profile,
                role_key=skill.roles[0],
                stage=skill.stages[0],
            )
            assert skill.name not in {item.skill.name for item in negative.selections}, skill.name
        else:
            wrong_stage = next(
                stage
                for stage in ("ideation", "planning", "writing", "review", "source-analysis")
                if stage not in skill.stages
            )
            negative = resolver.resolve(
                profile=profile,
                role_key=skill.roles[0],
                stage=wrong_stage,
            )
            assert skill.name not in {item.skill.name for item in negative.selections}, skill.name


def test_admitted_novel_skill_regression_contracts_are_reviewable() -> None:
    catalog = SkillCatalog(SKILLS_ROOT)

    for skill in catalog.for_domain("novel"):
        if not skill.roles:
            continue
        _, instructions = catalog.detail(skill.name)
        assert skill.description.lower().startswith(
            ("use ", "review ", "write ", "plan ", "apply ")
        ), skill.name
        assert len(instructions) >= 120, skill.name
        assert skill.stages, skill.name
        assert skill.admission_cases[-1].endswith("regression"), skill.name
        assert skill.references or len(instructions) >= 500, skill.name


def test_unadmitted_novel_skill_cannot_be_auto_or_explicitly_mounted(tmp_path: Path) -> None:
    documents = {
        "platform/project-diagnose": "---\nname: project-diagnose\ndescription: Diagnose\n---\nDiagnose.",
        "novel/novel-write": "---\nname: novel-write\ndescription: Write\n---\nWrite.",
        "novel/candidate-pack": (
            "---\nname: candidate-pack\ndescription: Candidate\nroles: [writer]\n"
            "stages: [writing]\ngenres: [romance]\n---\nCandidate."
        ),
    }
    for relative, content in documents.items():
        directory = tmp_path / relative
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(content, encoding="utf-8")
    (tmp_path / "admission.json").write_text(
        json.dumps(
            {
                "version": 1,
                "domains": {
                    "novel": {
                        "candidate-pack": {
                            "status": "incubating",
                            "baseline": "test-v1",
                            "cases": [],
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    resolver = SkillResolver(SkillCatalog(tmp_path))
    profile = CreativeProfile.from_direction(
        medium="novel", direction={"language": "en-US", "genre": "romance"}
    )

    automatic = resolver.resolve(profile=profile, role_key="writer", stage="writing")
    assert "candidate-pack" not in {item.skill.name for item in automatic.selections}
    with pytest.raises(SkillCatalogError, match="has not passed admission"):
        resolver.resolve(
            profile=profile,
            role_key="writer",
            stage="writing",
            explicit_skill_keys=("candidate-pack",),
        )
    with pytest.raises(SkillCatalogError, match="unadmitted skills"):
        resolver.catalog.loaders_for_plan(domain="novel", skill_keys=["candidate-pack"])


def test_chinese_genre_keywords_select_the_matching_style_skill() -> None:
    catalog = SkillCatalog(SKILLS_ROOT)
    profile = CreativeProfile.from_direction(
        medium="novel",
        direction={"genre": "现代奇幻/悬疑/轻言情", "world_setting": "数据世界崩塌", "language": "zh-CN"},
    )
    plan = SkillResolver(catalog).resolve(profile=profile, role_key="writer", stage="writing")
    suspense = next(
        (
            item
            for item in plan.selections
            if item.skill.name == "novel-cn-suspense-survival"
        ),
        None,
    )
    assert suspense is not None
    assert suspense.layer == "style_pack"
    assert any("题材关键词匹配" in reason for reason in suspense.reasons)


def test_core_skills_are_role_bound_and_immune_to_optional_limit() -> None:
    catalog = SkillCatalog(SKILLS_ROOT)
    profile = CreativeProfile.from_direction(medium="novel", direction={"language": "zh-CN"})
    plan = SkillResolver(catalog, optional_limit=0).resolve(
        profile=profile, role_key="writer", stage="writing"
    )
    selected = {item.skill.name for item in plan.selections}
    assert {
        "novel-write",
        "novel-continuity-check",
        "novel-emotional-depth",
        "novel-pacing-check",
        "project-diagnose",
    } <= selected
    assert all(item.layer == "core" for item in plan.selections)
    assert not {"novel-ideate", "novel-plan", "novel-review"} & selected


def test_instructions_for_renders_selected_skills_with_budget() -> None:
    catalog = SkillCatalog(SKILLS_ROOT)
    items = catalog.instructions_for(
        domain="novel",
        skill_keys=["novel-write", "novel-pacing-check"],
        max_chars=300,
    )
    assert items and items[0][0] == "novel-write"
    rendered = "\n".join(text for _, text in items)
    assert "Write a novel chapter" in rendered
    assert len(rendered) <= 340
    assert "截断" in rendered


def test_retention_and_voice_craft_skills_are_keyword_matched() -> None:
    catalog = SkillCatalog(SKILLS_ROOT)
    profile = CreativeProfile.from_direction(
        medium="novel",
        direction={
            "genre": "现代言情/甜宠",
            "style": "钩子密集, 爽点, 口吻差异化, 命名同质化",
            "language": "zh-CN",
        },
    )
    plan = SkillResolver(catalog, optional_limit=3).resolve(
        profile=profile, role_key="writer", stage="writing"
    )
    selected = {item.skill.name for item in plan.selections}
    assert "novel-cn-retention" in selected
    assert "novel-voice-craft" in selected
    retention = next(
        item for item in plan.selections if item.skill.name == "novel-cn-retention"
    )
    assert any("题材关键词匹配" in reason for reason in retention.reasons)


def test_short_drama_skill_is_keyword_matched_for_vertical_scripts() -> None:
    catalog = SkillCatalog(SKILLS_ROOT)
    profile = CreativeProfile.from_direction(
        medium="script",
        direction={
            "genre": "都市逆袭",
            "style": "竖屏短剧, 情绪卡点, 爽点密集",
            "language": "zh-CN",
            "script_format": "chinese",
        },
    )
    plan = SkillResolver(catalog, optional_limit=3).resolve(
        profile=profile, role_key="writer", stage="writing"
    )
    selected = {item.skill.name for item in plan.selections}
    assert "script-cn-short-drama" in selected
    short_drama = next(
        item for item in plan.selections if item.skill.name == "script-cn-short-drama"
    )
    assert any("题材关键词匹配" in reason for reason in short_drama.reasons)


def test_roundtable_doctor_skill_is_keyword_matched_for_review() -> None:
    catalog = SkillCatalog(SKILLS_ROOT)
    profile = CreativeProfile.from_direction(
        medium="script",
        direction={
            "genre": "都市逆袭",
            "style": "剧本医生, 圆桌会诊, 多视角评估",
            "language": "zh-CN",
            "script_format": "chinese-short",
        },
    )
    plan = SkillResolver(catalog, optional_limit=3).resolve(
        profile=profile, role_key="reviewer", stage="review"
    )
    selected = {item.skill.name for item in plan.selections}
    assert "script-doctor-roundtable" in selected
