import pytest

from scriptnow.script.contracts import ScriptBlock
from scriptnow.script.format_profiles import (
    generation_instructions,
    merge_same_speaker_dialogue,
    scene_craft_instructions,
    validate_script_blocks,
    validate_script_structure,
)
from scriptnow.script.generator import (
    _restore_embedded_scene_blocks,
    _ScriptBlockPayload,
    _validate_scene_document_payload,
)


def _blocks(slugline: str, transitions: tuple[str, ...] = ()) -> tuple[ScriptBlock, ...]:
    values = [
        ScriptBlock(para_id="p1", type="slugline", text=slugline),
        ScriptBlock(para_id="p2", type="action", text="门缓缓打开。"),
        ScriptBlock(para_id="p3", type="character", text="林深（克制）"),
        ScriptBlock(para_id="p4", type="dialogue", text="我回来取走真相。"),
    ]
    values.extend(
        ScriptBlock(para_id=f"t{index}", type="transition", text=text)
        for index, text in enumerate(transitions, 1)
    )
    return tuple(values)


def test_chinese_profile_accepts_location_time_and_interior_exterior() -> None:
    assert validate_script_blocks(_blocks("记忆诊所 夜 内"), "chinese") == ()


def test_chinese_profile_accepts_parenthetical_time_qualifier() -> None:
    assert (
        validate_script_blocks(_blocks("诊所·档案室 - 日（次日）- 内"), "chinese")
        == ()
    )


def test_chinese_profile_requires_paired_flashback_markers() -> None:
    issues = validate_script_blocks(_blocks("记忆诊所 夜 内", ("【闪回】",)), "chinese")
    assert "【闪回】与【闪出】必须成对出现" in issues


def test_hollywood_profile_requires_master_scene_heading() -> None:
    assert validate_script_blocks(_blocks("INT. MEMORY CLINIC - NIGHT"), "hollywood") == ()
    issues = validate_script_blocks(_blocks("MEMORY CLINIC NIGHT"), "hollywood")
    assert any("INT." in issue for issue in issues)


def test_generation_profiles_do_not_mix_numbered_chinese_and_hollywood_rules() -> None:
    short_instructions = generation_instructions("chinese-short")
    assert "▲" in short_instructions
    assert "出场人物" in short_instructions
    assert "OS" in short_instructions and "VO" in short_instructions
    assert "拆成多段" not in short_instructions
    assert "完整台词" in short_instructions
    assert "严禁每个段落都加▲" in short_instructions
    assert "严禁电报式短句堆叠" in short_instructions
    chinese = generation_instructions("chinese")
    hollywood = generation_instructions("hollywood")
    assert "人物（情绪）" in chinese
    assert "master-scene" in hollywood
    assert "Do not add scene numbers" in hollywood


def test_scene_craft_contract_precedes_format_and_requires_a_dramatic_turn() -> None:
    craft = scene_craft_instructions()
    assert "本场在整集与全剧中的唯一功能" in craft
    assert "潜台词" in craft
    assert "可观察的转折" in craft
    assert "交付格式" in craft


def test_creation_structure_does_not_reject_a_scene_only_for_delivery_spelling() -> None:
    blocks = _blocks("记忆诊所")
    assert validate_script_structure(blocks) == ()
    assert validate_script_blocks(blocks, "chinese")


def test_creation_structure_rejects_serialized_blocks_embedded_in_prose() -> None:
    blocks = list(_blocks("记忆诊所 夜 内"))
    blocks[1] = ScriptBlock(
        para_id="p2",
        type="action",
        text='她转身。"},{"type":"character","text":"何铭"}',
    )

    assert "段落正文混入了未解析的结构化剧本块" in validate_script_structure(
        tuple(blocks)
    )


def test_chinese_short_golden_structure_matches_storyboard_convention() -> None:
    import re

    from scriptnow.script.contracts import ScriptBlock

    blocks = (
        ScriptBlock(para_id="s1", type="slugline", text="1-1-1 酒店宴会厅·主舞台 傍晚 内"),
        ScriptBlock(para_id="a1", type="action", text="▲ 出场人物：顾念、宋司衡、陆沉。"),
        ScriptBlock(para_id="a2", type="action", text="▲ 宴会厅水晶灯璀璨，宾客满座。"),
        ScriptBlock(para_id="a3", type="action", text="▲【特写】顾念手中紧攥订婚戒指盒。"),
        ScriptBlock(para_id="c1", type="character", text="宋司衡（冷声）"),
        ScriptBlock(para_id="d1", type="dialogue", text="取消。"),
    )
    assert validate_script_structure(blocks) == ()
    slugline = blocks[0].text
    assert re.match(
        r"^\d+-\d+-\d+\s+\S+·\S+\s+(?:清晨|黎明|晨|上午|中午|下午|傍晚|黄昏|日|夜)\s+(?:内|外)$",
        slugline,
    )
    assert "出场人物" in blocks[1].text
    assert all(b.text.startswith("▲") for b in blocks[1:4])
    assert len(blocks[5].text) <= 15


def test_merge_same_speaker_dialogue_joins_fragmented_utterance() -> None:
    blocks = (
        ScriptBlock(para_id="s1", type="slugline", text="1-1 宴会厅 夜 内"),
        ScriptBlock(para_id="a1", type="action", text="▲ 众人屏息。"),
        ScriptBlock(para_id="c1", type="character", text="宋晚"),
        ScriptBlock(para_id="d1", type="dialogue", text="下调后的价格"),
        ScriptBlock(para_id="c2", type="character", text="宋晚"),
        ScriptBlock(para_id="d2", type="dialogue", text="刚好落在B轮买方"),
        ScriptBlock(para_id="c3", type="character", text="宋晚（稳）"),
        ScriptBlock(para_id="d3", type="dialogue", text="出价区间。"),
    )

    merged = merge_same_speaker_dialogue(blocks)

    speakers = [block for block in merged if block.type == "character"]
    dialogues = [block for block in merged if block.type == "dialogue"]
    assert len(speakers) == 1
    assert len(dialogues) == 1
    assert dialogues[0].text == "下调后的价格，刚好落在B轮买方，出价区间。"


def test_merge_same_speaker_dialogue_keeps_distinct_speakers_untouched() -> None:
    blocks = (
        ScriptBlock(para_id="s1", type="slugline", text="1-1 宴会厅 夜 内"),
        ScriptBlock(para_id="c1", type="character", text="宋晚"),
        ScriptBlock(para_id="d1", type="dialogue", text="下调后的价格。"),
        ScriptBlock(para_id="c2", type="character", text="沈聿"),
        ScriptBlock(para_id="d2", type="dialogue", text="继续。"),
        ScriptBlock(para_id="c3", type="character", text="宋晚（稳）"),
        ScriptBlock(para_id="d3", type="dialogue", text="出价区间。"),
    )

    merged = merge_same_speaker_dialogue(blocks)

    assert [block.text for block in merged if block.type == "character"] == [
        "宋晚",
        "沈聿",
        "宋晚（稳）",
    ]
    assert [block.text for block in merged if block.type == "dialogue"] == [
        "下调后的价格。",
        "继续。",
        "出价区间。",
    ]


def test_merge_same_speaker_dialogue_bridges_storyboard_action_blocks() -> None:
    blocks = (
        ScriptBlock(para_id="s1", type="slugline", text="3-1 茶室 日 内"),
        ScriptBlock(para_id="c1", type="character", text="姜淮（量角器微笑）"),
        ScriptBlock(para_id="d1", type="dialogue", text="老宋的女儿。"),
        ScriptBlock(para_id="a1", type="action", text="▲ 他把茶杯推到她面前。"),
        ScriptBlock(para_id="c2", type="character", text="姜淮"),
        ScriptBlock(para_id="d2", type="dialogue", text="坐。就当陪叔叔喝杯茶。"),
        ScriptBlock(para_id="a2", type="action", text="▲ 宋晚没碰杯子。"),
    )

    merged = merge_same_speaker_dialogue(blocks)

    types = [block.type for block in merged]
    assert types == ["slugline", "character", "dialogue", "action", "action"]
    dialogue = next(block for block in merged if block.type == "dialogue")
    assert dialogue.text == "老宋的女儿。坐。就当陪叔叔喝杯茶。"
    actions = [block.text for block in merged if block.type == "action"]
    assert "推到她面前" in actions[0]
    assert "宋晚没碰杯子" in actions[1]


def test_provider_json_repair_can_restore_an_exact_embedded_block_tail() -> None:
    repaired = (
        _ScriptBlockPayload(type="slugline", text="诊所 夜 内"),
        _ScriptBlockPayload(
            type="action",
            text='她转身。"},{"type":"character","text":"何铭"},'
            '{"type":"dialogue","text":"午夜之前，你还有选择。"}',
        ),
    )

    restored = _restore_embedded_scene_blocks(repaired)

    assert [(item.type, item.text) for item in restored] == [
        ("slugline", "诊所 夜 内"),
        ("action", "她转身。"),
        ("character", "何铭"),
        ("dialogue", "午夜之前，你还有选择。"),
    ]


def test_provider_block_recovery_tolerates_unescaped_quotes_in_text() -> None:
    repaired = (
        _ScriptBlockPayload(
            type="action",
            text='她说"三年前"。"},{"type":"action","text":"屏幕显示她在"小时候"。"}',
        ),
    )

    restored = _restore_embedded_scene_blocks(repaired)

    assert [(item.type, item.text) for item in restored] == [
        ("action", '她说"三年前"。'),
        ("action", '屏幕显示她在"小时候"。'),
    ]


def test_scene_payload_accepts_equivalent_top_level_block_array() -> None:
    payload = _validate_scene_document_payload(
        [
            {"type": "slugline", "text": "诊所 夜 内"},
            {"type": "action", "text": "灯灭。"},
            {"type": "character", "text": "林深"},
            {"type": "dialogue", "text": "现在。"},
        ]
    )

    assert len(payload.blocks) == 4


def test_scene_payload_ignores_envelope_metadata_and_has_no_business_size_cap() -> None:
    blocks = [
        {"type": "slugline", "text": "诊所 夜 内"},
        *({"type": "action", "text": f"动作 {index}"} for index in range(180)),
        {"type": "character", "text": "林深"},
        {"type": "dialogue", "text": "现在。"},
    ]

    payload = _validate_scene_document_payload(
        {
            "scene_id": "scene-1-3",
            "title": "第三集",
            "duration_seconds": 180,
            "blocks": blocks,
        }
    )

    assert len(payload.blocks) == 183


def test_scene_payload_normalizes_content_envelope_with_external_slugline() -> None:
    payload = _validate_scene_document_payload(
        {
            "scene_number": "1-3",
            "slugline": "档案室 深夜 内",
            "content": [
                {"type": "action", "text": "灯灭。"},
                {"type": "character", "text": "林深"},
                {"type": "dialogue", "text": "现在。"},
            ],
        }
    )

    assert [(block.type, block.text) for block in payload.blocks] == [
        ("slugline", "档案室 深夜 内"),
        ("action", "灯灭。"),
        ("character", "林深"),
        ("dialogue", "现在。"),
    ]


def test_unknown_script_format_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported Script format"):
        generation_instructions("unknown")
