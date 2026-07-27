from __future__ import annotations

import re
from typing import Literal

from scriptnow.script.contracts import ScriptBlock

ScriptFormat = Literal["chinese", "hollywood"]

_CHINESE_TIME = re.compile(
    r"(?:^|[\s·-])(?:日|夜|晨|黄昏)(?=$|[\s·\-（(])"
)
_CHINESE_SPACE = re.compile(r"(?:^|\s)(?:内|外|内景|外景)(?:\s|$)")
_HOLLYWOOD_SLUGLINE = re.compile(r"^(?:INT\.|EXT\.|INT\./EXT\.|I/E\.)\s+", re.I)
_EMBEDDED_BLOCK_JSON = re.compile(
    r'(?:^|["}\]])\s*,?\s*\{\s*["\\]?type["\\]?\s*:', re.I
)


def generation_instructions(script_format: str) -> str:
    if script_format == "chinese":
        return """
采用中文平台剧本交付规范：
1. slugline 只写“地点 + 时间（日/夜/晨/黄昏）+ 内外景（内/外）”，三项必须齐全。
2. action 是可拍摄的画面、动作与神态；不要在正文中重复集数、场号或“人物：”，系统会在导出时生成。
3. 每段 dialogue 前必须紧邻 character。character 可写“人物（情绪）”；内心独白使用“人物（OS）”，画外音使用“人物（VO）”。
4. 闪回使用 transition 的“【闪回】”开始，并用“【闪出】”结束，必须成对出现。
5. 不要输出 Markdown、解释或小说式心理分析。
""".strip()
    if script_format == "hollywood":
        return """
Use a Hollywood spec/master-scene screenplay, not a numbered shooting script:
1. Every slugline begins with INT., EXT., INT./EXT., or I/E., followed by location and DAY/NIGHT.
2. Use action only for visible or audible material. Keep action paragraphs concise.
3. Put every spoken line in a dialogue block immediately after a character block. Character cues are uppercase; append (V.O.) or (O.S.) when needed.
4. Use transition blocks sparingly. Do not add scene numbers, camera-shot lists, a cast list, or production notes.
5. Return screenplay content only, without Markdown or analysis.
""".strip()
    raise ValueError("unsupported Script format")


def scene_craft_instructions() -> str:
    return """
先按戏剧场景而不是文档格式完成创作判断：
1. 明确本场在整集与全剧中的唯一功能；若删掉本场不会改变因果、关系或信息边界，就重写场景设计。
2. 写清进入状态、主行动人物的当下目标、可执行策略与具体阻力。冲突必须发生在人物行动之间，不能只靠说明。
3. 每一次对白都是一种策略；让潜台词、回避、误解、权力差和未说出口的需要推动交流，避免人物替作者解释剧情。
4. 场景中必须发生可观察的转折：目标、权力、关系、知识或风险至少一项改变。
5. 结尾落在人物选择及其后果上，把新的压力交给下一 Story Beat；不要机械添加悬念句。
6. 只写摄像机和声音能够呈现的内容。心理活动必须转化为行为、选择、节奏、道具、空间或声音。
7. 先满足已采纳蓝图、StoryMap、人物连续性和伏笔回收，再选择具体措辞与交付格式。
""".strip()


def validate_script_structure(blocks: tuple[ScriptBlock, ...]) -> tuple[str, ...]:
    issues: list[str] = []
    if not blocks or blocks[0].type != "slugline":
        issues.append("场次必须以场景标题（slugline）开始")
        return tuple(issues)
    if len({block.para_id for block in blocks}) != len(blocks):
        issues.append("段落标识必须唯一")
    if not any(block.type == "action" for block in blocks):
        issues.append("场次缺少可拍摄的画面或动作")
    if not any(block.type == "dialogue" for block in blocks):
        issues.append("场次缺少台词")
    for index, block in enumerate(blocks):
        if _EMBEDDED_BLOCK_JSON.search(block.text):
            issues.append("段落正文混入了未解析的结构化剧本块")
        if block.type == "dialogue" and (
            index == 0 or blocks[index - 1].type != "character"
        ):
            issues.append("每段台词前必须紧邻说话人物")
    return tuple(dict.fromkeys(issues))


def validate_script_blocks(
    blocks: tuple[ScriptBlock, ...], script_format: str
) -> tuple[str, ...]:
    issues = list(validate_script_structure(blocks))
    if not blocks or blocks[0].type != "slugline":
        return tuple(issues)

    slugline = blocks[0].text.strip()
    if script_format == "chinese":
        if not _CHINESE_TIME.search(slugline):
            issues.append("中文场景标题缺少日、夜等时间标识")
        if not _CHINESE_SPACE.search(slugline):
            issues.append("中文场景标题缺少内景或外景标识")
        transitions = [block.text.strip() for block in blocks if block.type == "transition"]
        if transitions.count("【闪回】") != transitions.count("【闪出】"):
            issues.append("【闪回】与【闪出】必须成对出现")
    elif script_format == "hollywood":
        if not _HOLLYWOOD_SLUGLINE.match(slugline):
            issues.append("Hollywood scene heading must begin with INT., EXT., INT./EXT., or I/E.")
    else:
        issues.append("项目剧本格式无效")
    return tuple(dict.fromkeys(issues))
