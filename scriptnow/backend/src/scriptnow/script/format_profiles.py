from __future__ import annotations

import re
from typing import Literal

from scriptnow.script.contracts import ScriptBlock

ScriptFormat = Literal["chinese", "chinese-short", "hollywood"]

_DIALOGUE_JOINER = "，"

_CHINESE_TIME = re.compile(
    r"(?:^|[\s·-])(?:日|夜|晨|黄昏)(?=$|[\s·\-（(])"
)
_CHINESE_SPACE = re.compile(r"(?:^|\s)(?:内|外|内景|外景)(?:\s|$)")
_HOLLYWOOD_SLUGLINE = re.compile(r"^(?:INT\.|EXT\.|INT\./EXT\.|I/E\.)\s+", re.I)
_EMBEDDED_BLOCK_JSON = re.compile(
    r'(?:^|["}\]])\s*,?\s*\{\s*["\\]?type["\\]?\s*:', re.I
)


def generation_instructions(script_format: str) -> str:
    if script_format == "chinese-short":
        return """
采用竖屏短剧剧本交付规范（1-2 分钟/集，分镜式书写）：

【视听语言铁律——优先于格式规则】
以下写法判定为不合格，禁止出现在 action 块中：
- 小说式心理描写：禁用「心想」「感到」「内心」「回忆」「情绪」「心情」等词。只写角色做了什么、在哪儿、怎么做的。
  错误：「她内心感到一阵不安，仿佛预感到危机的来临。」
  正确：「她盯着账本。没翻页。」或「她把账本合上。力气大了点——啪的一声。」
- 身体隐喻式动作：禁用「骨节发白」「指尖泛白」「指甲掐进掌心」「喉头发紧」等文学修辞。只写角色的动作本身。
  错误：「她攥紧账本，骨节发白。」
  正确：「她盯着账本。没翻页。」或「她把账本合上——啪的一声。」
- 抽象氛围概括：禁用「气氛紧张」「命运」「宿命」「人生」「时光」「精致」「奢华」。写出具体视听元素。
  错误：「两人之间气氛紧张起来。」
  正确：「他放下筷子。她也放下。两双筷子搁在碗沿，谁都没再动。」
- 机械悬念句：禁用「他不知道……」「殊不知……」「命运的齿轮……」——直接删除，不替换。
- 情绪宣告式对白：人物不直接宣布情绪（「我恨你」「我好痛苦」）。情绪通过行动和选择呈现。

【格式规范】
1. slugline 只写"场号-分镜号 地点·细地点 时间 内/外"，如"1-1 相府偏院·院墙外 清晨 外"；不要重复集数。
2. action 是单个可拍画面；仅关键分镜（特写、闪回、动作节拍）用"▲"或"▲【…】"开头标记，常规画面描述不加▲或使用"△"，严禁每个段落都加▲。示例：常规"她盯着账本。没翻页。"；关键"▲【特写】账本缺页的一角"。
3. 每段 dialogue 前必须紧邻 character；character 写"人物（语气/动作）"，如"林昭宁（OS，迷糊）"。OS=内心独白，VO=画外旁白；旁白每 25-35 个分镜才出现一次，单段不超过 30 字。
4. 每个分镜组画面描述控制在 20-30 字以内；台词必须是自然连贯的完整句子：同一人物的一段完整台词写成一条 dialogue，用逗号/顿号/破折号组织成连贯语句。严禁电报式短句堆叠（如"坐下。从第一页看。三年前。我做的。"应写成"坐下，从第一页看——三年前宋家尽调是我做的。"）。列举信息写成一条连贯台词；单条台词长度不限。
5. 场景开头用 action 块输出"出场人物：×××、×××"。
6. 全集开头如有新人物，用 action 块输出"人设/声线"要点（角色名 + 关键视觉/声音特征）。
7. 不要输出 Markdown、解释或小说式心理分析。
""".strip()
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

【视听语言铁律——写作前必读】
以下为中文剧本常见AI写作错误，禁止产出：
- 心理描写词禁用：「心想」「感到」「内心」「回忆」「情绪」「心情」「意识」「浮现」
  错误：「她内心感到一阵不安，仿佛预感到危机的来临。」
  正确：「她盯着账本。没翻页。」或「她把账本合上——啪的一声。」
- 身体隐喻禁用：「骨节发白」「指尖泛白」「指甲掐进掌心」「喉头发紧」——只写动作本身。
  错误：「她攥紧账本，骨节发白。」
  正确：「她盯着账本。没翻页。窗外有车灯扫过——她缩了一下。」
- 抽象氛围词禁用：「气氛紧张」「命运」「宿命」「人生」「时光」「精致」「奢华」
  错误：「两人之间气氛突然变得紧张起来。」
  正确：「他放下筷子。她也放下。两双筷子搁在碗沿，谁都没再动。」
- 机械悬念句禁用：「他不知道……」「殊不知……」「命运的齿轮……」——直接删除。
- 情绪宣告对白禁用：「我恨你」「我好痛苦」「太可怕了」（除非伴随当场可见的后果行动）

【场景创作流程】
1. 明确本场在整集与全剧中的唯一功能；若删掉本场不会改变因果、关系或信息边界，就重写场景设计。
2. 写清进入状态、主行动人物的当下目标、可执行策略与具体阻力。冲突必须发生在人物行动之间，不能只靠说明。
3. 每一次对白都是一种策略；让潜台词、回避、误解、权力差和未说出口的需要推动交流，避免人物替作者解释剧情。
4. 台词必须是人话：自然、完整、有节奏。同一人物的一段完整台词写为一条 dialogue，用逗号/顿号/破折号组织成连贯语句；列举信息写成一个完整的句子。短句是节奏落点而非默认形态，严禁电报式短句堆叠（如“坐下。从第一页看。三年前。我做的。”应写成“坐下，从第一页看——三年前宋家尽调是我做的。”）。
5. 场景中必须发生可观察的转折：目标、权力、关系、知识或风险至少一项改变。
6. 结尾落在人物选择及其后果上，把新的压力交给下一 Story Beat；不要机械添加悬念句。
7. 只写摄像机和声音能够呈现的内容。心理活动必须转化为行为、选择、节奏、道具、空间或声音。
8. 先满足已采纳蓝图、StoryMap、人物连续性和伏笔回收，再选择具体措辞与交付格式。
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


def _speaker_key(text: str) -> str:
    """Extract the speaker name from a character block, ignoring emotion/action notes."""
    name = text.strip()
    for marker in ("（", "(", "："):
        name = name.split(marker, 1)[0]
    return name.strip()


def _join_fragments(fragments: list[str]) -> str:
    parts: list[str] = []
    for text in fragments:
        text = text.strip()
        if parts and not parts[-1].endswith(("。", "！", "？", "…", "：", "，", "、", ";")):
            parts[-1] = parts[-1] + _DIALOGUE_JOINER
        parts.append(text)
    return "".join(parts)


def merge_same_speaker_dialogue(
    blocks: tuple[ScriptBlock, ...],
) -> tuple[ScriptBlock, ...]:
    """Join one speaker's consecutive fragments into a single complete dialogue line.

    The platform parser requires “人名：完整台词”. Models sometimes split one
    utterance into short fragments, each preceded by its own character block
    (…character A, dialogue X, [action], character A, dialogue Y…), with at most
    a couple of storyboard action blocks in between. This normalization merges
    X and Y into one dialogue block under A, keeping interleaved action blocks
    after the complete line.
    """
    result: list[ScriptBlock] = []
    index = 0
    while index < len(blocks):
        block = blocks[index]
        if not (
            block.type == "character"
            and index + 1 < len(blocks)
            and blocks[index + 1].type == "dialogue"
        ):
            result.append(block)
            index += 1
            continue

        speaker = _speaker_key(block.text)
        fragments = [blocks[index + 1].text]
        collected_actions: list[ScriptBlock] = []
        cursor = index + 2
        while cursor < len(blocks):
            actions: list[ScriptBlock] = []
            look = cursor
            while (
                look < len(blocks)
                and blocks[look].type == "action"
                and len(actions) < 2
            ):
                actions.append(blocks[look])
                look += 1
            if not (
                look + 1 < len(blocks)
                and blocks[look].type == "character"
                and blocks[look + 1].type == "dialogue"
                and _speaker_key(blocks[look].text) == speaker
            ):
                collected_actions.extend(actions)
                cursor = look
                break
            collected_actions.extend(actions)
            fragments.append(blocks[look + 1].text)
            cursor = look + 2

        result.append(block)
        result.append(
            blocks[index + 1].model_copy(
                update={"text": _join_fragments(fragments)}
            )
        )
        result.extend(collected_actions)
        index = cursor
    return tuple(result)


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
