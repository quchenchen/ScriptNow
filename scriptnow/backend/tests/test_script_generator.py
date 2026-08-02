from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from scriptnow.platform.agent_runtime import AgentRuntimeResult
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    ProjectMedium,
    ProjectModel,
    ReservationState,
    RunStatus,
    TenantModel,
    TokenAccountModel,
    TokenUsageModel,
    UsageReservationModel,
)
from scriptnow.script.generator import (
    ScriptCreativeGenerator,
    _anchor_aliases,
    _validate_story_map_contract,
    _validate_story_map_payload,
    normalize_blueprint_kind,
)


def _core_candidates() -> list[dict[str, object]]:
    return [
        {
            "title": f"方向 {index}",
            "concept": "一个具体而完整的剧本方向，包含人物选择、持续升级的阻力、关系变化以及不可逆的终局代价。"
            * 2,
            "angles": ["欲望", "阻力", "关系变化", "终局代价", "最终选择"],
            "narrative_engine": ["每次追查都会揭开真相，同时让主角失去一条退路。"],
            "viewpoint_anchor": ["跟随主角限知视角"],
            "pacing_recipe": ["发现、受阻、选择"],
            "market_judgement": ["优势明确", "风险可控"],
        }
        for index in range(1, 4)
    ]


@pytest.mark.asyncio
async def test_script_generation_records_usage_reservation(tmp_path, monkeypatch) -> None:
    database = Database.create(f"sqlite+aiosqlite:///{tmp_path / 'script_billing.db'}")
    await database.create_schema()
    async with database.session() as session:
        tenant = TenantModel(name="Studio", tier="plus")
        session.add(tenant)
        await session.flush()
        project = ProjectModel(
            tenant_id=tenant.id,
            name="回声诊所",
            medium=ProjectMedium.SCRIPT,
            direction={"genre": "悬疑", "language": "zh-CN"},
        )
        session.add(project)
        await session.flush()
        session.add(
            TokenAccountModel(
                tenant_id=tenant.id,
                tier="plus",
                period_key="2026-08",
                monthly_available=100_000,
                credits_available=0,
            )
        )
        await session.flush()
        tenant_id, project_id = tenant.id, project.id

    generator = ScriptCreativeGenerator(database, Settings())

    async def fake_generate(**kwargs) -> AgentRuntimeResult:
        import json

        return AgentRuntimeResult(
            text=json.dumps({"candidates": _core_candidates()}, ensure_ascii=False),
            runtime="agentscope",
            model_key="deepseek-v4-pro",
            input_tokens=1200,
            output_tokens=400,
            input_price_per_million=Decimal("3"),
            output_price_per_million=Decimal("6"),
        )

    monkeypatch.setattr(generator.runtime, "generate", fake_generate)
    async with database.session() as session:
        project = await session.get(ProjectModel, project_id)
        drafts = await generator.story_cores(
            tenant_id=tenant_id,
            project=project,
            feedback=None,
        )
    assert len(drafts) == 3

    async with database.session() as session:
        reservations = (await session.scalars(select(UsageReservationModel))).all()
        usage = (await session.scalars(select(TokenUsageModel))).all()
        assert len(reservations) == 1
        assert reservations[0].status == ReservationState.FINALIZED
        assert len(usage) == 1
        assert usage[0].agent_role == "director"
        assert usage[0].model_key == "deepseek-v4-pro"
        assert usage[0].input_tokens == 1200
    await database.dispose()


@pytest.mark.asyncio
async def test_story_cores_accepts_one_complete_narrative_engine(monkeypatch):
    generator = ScriptCreativeGenerator.__new__(ScriptCreativeGenerator)
    candidates = [
        {
            "title": f"方向 {index}",
            "concept": "一个具体而完整的剧本方向，包含人物选择、持续升级的阻力、关系变化以及不可逆的终局代价。"
            * 2,
            "angles": ["欲望", "阻力", "关系变化", "终局代价", "最终选择"],
            "narrative_engine": ["每次追查都会揭开真相，同时让主角失去一条退路。"],
            "viewpoint_anchor": ["跟随主角限知视角"],
            "pacing_recipe": ["发现、受阻、选择"],
            "market_judgement": ["优势明确", "风险可控"],
        }
        for index in range(1, 4)
    ]

    async def fake_json(*_args, validator, **_kwargs):
        return validator({"candidates": candidates})

    monkeypatch.setattr(generator, "_json", fake_json)
    project = SimpleNamespace(
        id="project-id",
        name="回声诊所",
        direction={"medium": "script", "creative_language": "zh-CN"},
    )

    result = await generator.story_cores(
        tenant_id="tenant-id",
        project=project,
        feedback=None,
    )

    assert len(result) == 3
    assert result[0].details.narrative_engine == ("每次追查都会揭开真相，同时让主角失去一条退路。",)


@pytest.mark.asyncio
async def test_blueprint_revision_includes_current_candidate_as_revision_base(monkeypatch):
    generator = ScriptCreativeGenerator.__new__(ScriptCreativeGenerator)
    captured: dict[str, object] = {}

    async def fake_json(_tenant_id, _project_id, _role, prompt, context, *, validator):
        captured["prompt"] = prompt
        captured["context"] = context
        return validator(
            {
                "anchors": [
                    {
                        "id": "event:inciting",
                        "kind": "event",
                        "name": "The patient returns",
                        "payload": {"description": "The sealed memory speaks."},
                    },
                    *[
                        {
                            "id": f"event:{index}",
                            "kind": "event",
                            "name": f"Event {index}",
                            "payload": {"description": f"Beat {index}"},
                        }
                        for index in range(7)
                    ],
                ]
            }
        )

    monkeypatch.setattr(generator, "_json", fake_json)
    project = SimpleNamespace(
        id="project-id",
        direction={"medium": "script", "creative_language": "zh-CN"},
    )
    existing = [
        {
            "id": "event:inciting",
            "kind": "event",
            "name": "The patient returns",
            "payload": {"description": "The sealed memory speaks."},
        }
    ]

    result = await generator.blueprint(
        tenant_id="tenant-id",
        project=project,
        story_core={"title": "Last Patient"},
        existing_anchors=existing,
        feedback="Add a stronger midpoint reversal.",
    )

    assert len(result.anchors) == 8
    assert captured["context"]["existing_blueprint_anchors"] == existing
    assert "The patient returns" in str(captured["prompt"])
    assert "不能只返回差异" in str(captured["prompt"])


@pytest.mark.asyncio
async def test_blueprint_revision_retries_contract_or_cross_project_contamination(
    monkeypatch,
):
    generator = ScriptCreativeGenerator.__new__(ScriptCreativeGenerator)
    attempts: list[tuple[str, dict[str, object]]] = []

    async def fake_json(
        _tenant_id,
        _project_id,
        _role,
        prompt,
        context,
        *,
        skills_enabled=True,
        validator,
    ):
        attempts.append((prompt, context))
        if len(attempts) == 2:
            assert skills_enabled is False
        if len(attempts) == 1:
            return validator(
                {
                    "anchors": [
                        {
                            "id": f"unrelated:{index}",
                            "kind": "event",
                            "label": f"Other project {index}",
                            "payload": {"description": "contaminated"},
                        }
                        for index in range(8)
                    ]
                }
            )
        return validator(
            {
                "anchors": [
                    {
                        "id": "event:inciting",
                        "kind": "event",
                        "name": "The patient returns",
                        "payload": {"description": "The sealed memory speaks."},
                    },
                    *[
                        {
                            "id": f"event:{index}",
                            "kind": "event",
                            "name": f"Event {index}",
                            "payload": {"description": f"Beat {index}"},
                        }
                        for index in range(7)
                    ],
                ]
            }
        )

    monkeypatch.setattr(generator, "_json", fake_json)
    project = SimpleNamespace(
        id="project-id",
        direction={"medium": "script", "creative_language": "zh-CN"},
    )
    existing = [
        {
            "id": "event:inciting",
            "kind": "event",
            "name": "The patient returns",
            "payload": {"description": "The sealed memory speaks."},
        }
    ]

    result = await generator.blueprint(
        tenant_id="tenant-id",
        project=project,
        story_core={"title": "Last Patient"},
        existing_anchors=existing,
        feedback="Strengthen the midpoint.",
    )

    assert len(attempts) == 2
    assert attempts[1][1]["contract_retry"] is True
    assert "绝不能使用 label" in attempts[1][0]
    assert result.anchors[0].id == "event:inciting"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("world_rule", "worldview"),
        ("relationship", "character"),
        ("key-event", "event"),
        ("setup", "foreshadow"),
        ("character_arc", "character_arc"),
    ],
)
def test_blueprint_kind_normalizes_provider_aliases(source, expected):
    assert normalize_blueprint_kind(source) == expected


def test_blueprint_kind_rejects_unknown_provider_category():
    with pytest.raises(ValueError, match="unsupported script blueprint kind"):
        normalize_blueprint_kind("location")


def test_blueprint_revision_accepts_rebuilt_ids_when_semantic_anchors_remain():
    existing = [
        {
            "id": "character:protagonist",
            "kind": "character",
            "name": "苏默——失声的急诊医生",
            "payload": {"description": "她守着旧秘密。"},
        },
        {
            "id": "character:witness",
            "kind": "character",
            "name": "姜寻——归来的证人",
            "payload": {"description": "他要求真相。"},
        },
    ]
    value = {
        "anchors": [
            {
                "id": f"event:rebuilt-{index}",
                "kind": "event",
                "name": (
                    "苏默在终端前选择"
                    if index == 0
                    else "姜寻交出证据"
                    if index == 1
                    else f"当前项目事件 {index}"
                ),
                "payload": {"description": f"当前项目叙事节点 {index}"},
            }
            for index in range(8)
        ]
    }

    payload = ScriptCreativeGenerator._validate_blueprint_payload(
        value,
        existing_anchors=existing,
    )

    assert len(payload.anchors) == 8


def test_story_map_accepts_semantically_equivalent_provider_envelope():
    payload = _validate_story_map_payload(
        {
            "storymap": {
                "episodes": [
                    {
                        "title": "证言室",
                        "scenes": [
                            {
                                "title": "证人归来",
                                "beats": [
                                    {
                                        "objective": "证人交出能够改变调查方向的原始记录",
                                        "anchor_ids": ["event:witness-returns"],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        }
    )

    assert payload.episodes[0].title == "证言室"


def test_story_map_accepts_nested_provider_result_envelope():
    payload = _validate_story_map_payload(
        {
            "result": {
                "story_map": {
                    "episodes": [
                        {
                            "title": "证言室",
                            "scenes": [
                                {
                                    "title": "证人归来",
                                    "beats": [
                                        {
                                            "objective": "证人交出能够改变调查方向的原始记录",
                                            "anchor_ids": ["event:witness-returns"],
                                        }
                                    ],
                                }
                            ],
                        }
                    ]
                }
            }
        }
    )

    assert payload.episodes[0].scenes[0].title == "证人归来"


def test_story_map_contract_rejects_unknown_blueprint_anchor():
    with pytest.raises(ValueError, match="unknown blueprint anchor ids"):
        _validate_story_map_contract(
            {
                "episodes": [
                    {
                        "title": "证言室",
                        "scenes": [
                            {
                                "title": "证人归来",
                                "beats": [
                                    {
                                        "objective": "证人交出能够改变调查方向的原始记录",
                                        "anchor_ids": ["discovery_footage"],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
            episode_count=1,
            scenes_per_episode=1,
            anchor_ids={"event:witness-returns"},
        )


def test_story_map_normalizes_only_unambiguous_provider_anchor_aliases():
    aliases = _anchor_aliases(
        [
            {
                "id": "event:footage_discovery",
                "kind": "event",
                "name": "发现停电前影像",
                "payload": {},
            },
            {
                "id": "event:first_confrontation",
                "kind": "event",
                "name": "第一次对峙",
                "payload": {},
            },
        ]
    )

    payload = _validate_story_map_contract(
        {
            "episodes": [
                {
                    "title": "证言室",
                    "scenes": [
                        {
                            "title": "证人归来",
                            "beats": [
                                {
                                    "objective": "医生从离线终端调出关键监控影像",
                                    "anchor_ids": ["discovery_footage"],
                                }
                            ],
                        }
                    ],
                }
            ]
        },
        episode_count=1,
        scenes_per_episode=1,
        anchor_ids={"event:footage_discovery", "event:first_confrontation"},
        anchor_aliases=aliases,
    )

    assert payload.episodes[0].scenes[0].beats[0].anchor_ids == ("event:footage_discovery",)


@pytest.mark.asyncio
async def test_story_map_retries_invalid_contract_without_exposing_validation_details(
    monkeypatch,
):
    generator = ScriptCreativeGenerator.__new__(ScriptCreativeGenerator)
    attempts: list[tuple[str, dict[str, object], bool]] = []

    async def fake_json(
        _tenant_id,
        _project_id,
        _role,
        prompt,
        context,
        *,
        skills_enabled=True,
        validator,
    ):
        attempts.append((prompt, context, skills_enabled))
        if len(attempts) == 1:
            return validator({"meta": {"title": "invalid"}})
        return validator(
            {
                "episodes": [
                    {
                        "title": "证言室",
                        "scenes": [
                            {
                                "title": "证人归来",
                                "beats": [
                                    {
                                        "objective": "证人交出能够改变调查方向的原始记录",
                                        "anchor_ids": ["A01"],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        )

    monkeypatch.setattr(generator, "_json", fake_json)
    project = SimpleNamespace(
        id="project-id",
        direction={"volume_one": 1, "volume_two": 1, "volume_three": 3},
    )

    episodes = await generator.story_map(
        tenant_id="tenant-id",
        project=project,
        story_core={"title": "证言室"},
        anchors=[
            {
                "id": "event:witness-returns",
                "kind": "event",
                "name": "证人归来",
                "payload": {"description": "证人带回原始记录。"},
            }
        ],
        feedback=None,
    )

    assert len(attempts) == 2
    assert attempts[1][1]["contract_retry"] is True
    assert attempts[1][2] is False
    assert "具体拒绝原因" in attempts[1][0]
    assert '"ref": "A01"' in attempts[1][0]
    assert episodes[0].scenes[0].beats[0].anchor_ids == ("event:witness-returns",)
    assert episodes[0].title == "证言室"


@pytest.mark.asyncio
async def test_scene_document_returns_structured_candidate_without_adopting(monkeypatch):
    generator = ScriptCreativeGenerator.__new__(ScriptCreativeGenerator)

    async def fake_json(*_args, validator, **_kwargs):
        return validator(
            {
                "blocks": [
                    {"type": "slugline", "text": "内景 记忆诊所 夜"},
                    {"type": "action", "text": "冷蓝终端逐层亮起。"},
                    {"type": "character", "text": "林深"},
                    {"type": "dialogue", "text": "把最深的一层打开。"},
                ]
            }
        )

    monkeypatch.setattr(generator, "_json", fake_json)
    project = SimpleNamespace(
        id="project-id",
        direction={
            "creative_language": "zh-CN",
            "script_format": "chinese",
            "volume_three": 3,
        },
    )

    blocks = await generator.scene_document(
        tenant_id="tenant-id",
        project=project,
        scene={"id": "scene-1-1", "duration_seconds_target": 180},
        context={"anchors": [], "adopted_scenes": []},
        feedback=None,
    )

    assert [block.type for block in blocks] == [
        "slugline",
        "action",
        "character",
        "dialogue",
    ]
    assert blocks[0].text == "内景 记忆诊所 夜"


@pytest.mark.asyncio
async def test_json_marks_run_failed_until_domain_contract_validates():
    generator = ScriptCreativeGenerator.__new__(ScriptCreativeGenerator)
    transitions: list[tuple[RunStatus, str | None]] = []

    class FakeRuns:
        async def enqueue(self, **_kwargs):
            return SimpleNamespace(id="run-id")

        async def transition(self, *, target, error_code=None, **_kwargs):
            transitions.append((target, error_code))

    class FakeRuntime:
        async def generate(self, **_kwargs):
            return SimpleNamespace(text='{"episodes":[]}')

    generator.runs = FakeRuns()
    generator.runtime = FakeRuntime()
    async def fake_reserve(*_args, **_kwargs) -> None:
        return None

    async def fake_settle(*_args, **_kwargs) -> None:
        return None

    async def fake_release(*_args, **_kwargs) -> None:
        return None

    generator._reserve = fake_reserve  # type: ignore[method-assign]
    generator._settle = fake_settle  # type: ignore[method-assign]
    generator._release = fake_release  # type: ignore[method-assign]

    with pytest.raises(ValidationError):
        await generator._json(
            "tenant-id",
            "project-id",
            "architect",
            "prompt",
            {},
            validator=_validate_story_map_payload,
        )

    assert transitions == [
        (RunStatus.RUNNING, None),
        (RunStatus.FAILED, "script_contract_invalid"),
    ]
