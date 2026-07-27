from types import SimpleNamespace

import pytest

from scriptnow.script.generator import ScriptCreativeGenerator, normalize_blueprint_kind


@pytest.mark.asyncio
async def test_story_cores_accepts_one_complete_narrative_engine(monkeypatch):
    generator = ScriptCreativeGenerator.__new__(ScriptCreativeGenerator)
    candidates = [
        {
            "title": f"方向 {index}",
            "concept": "一个具体而完整的剧本方向，包含人物选择、持续升级的阻力、关系变化以及不可逆的终局代价。" * 2,
            "angles": ["欲望", "阻力", "关系变化", "终局代价", "最终选择"],
            "narrative_engine": ["每次追查都会揭开真相，同时让主角失去一条退路。"],
            "viewpoint_anchor": ["跟随主角限知视角"],
            "pacing_recipe": ["发现、受阻、选择"],
            "market_judgement": ["优势明确", "风险可控"],
        }
        for index in range(1, 4)
    ]

    async def fake_json(*_args, **_kwargs):
        return {"candidates": candidates}

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
    assert result[0].details.narrative_engine == (
        "每次追查都会揭开真相，同时让主角失去一条退路。",
    )


@pytest.mark.asyncio
async def test_blueprint_revision_includes_current_candidate_as_revision_base(monkeypatch):
    generator = ScriptCreativeGenerator.__new__(ScriptCreativeGenerator)
    captured: dict[str, object] = {}

    async def fake_json(_tenant_id, _project_id, _role, prompt, context):
        captured["prompt"] = prompt
        captured["context"] = context
        return {
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
    ):
        attempts.append((prompt, context))
        if len(attempts) == 2:
            assert skills_enabled is False
        if len(attempts) == 1:
            return {
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
        return {
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


@pytest.mark.asyncio
async def test_scene_document_returns_structured_candidate_without_adopting(monkeypatch):
    generator = ScriptCreativeGenerator.__new__(ScriptCreativeGenerator)

    async def fake_json(*_args, **_kwargs):
        return {
            "blocks": [
                {"type": "slugline", "text": "内景 记忆诊所 夜"},
                {"type": "action", "text": "冷蓝终端逐层亮起。"},
                {"type": "character", "text": "林深"},
                {"type": "dialogue", "text": "把最深的一层打开。"},
            ]
        }

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
