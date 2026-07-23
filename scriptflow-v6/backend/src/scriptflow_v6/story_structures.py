"""Story structure templates — globally recognized narrative frameworks.
Each structure defines arc names, count, and purpose descriptions.
These replace LLM-hallucinated arc names like '初环/叠环/终环'."""
from __future__ import annotations

from typing import NamedTuple


class StoryStructure(NamedTuple):
    key: str
    label: str
    label_en: str
    origin: str
    arc_count: int
    arc_names: list[str]
    arc_purposes: list[str]
    description: str
    best_for: str


STRUCTURES: list[StoryStructure] = [
    StoryStructure(
        key="three-act",
        label="三幕结构",
        label_en="Three-Act Structure",
        origin="亚里士多德 → 悉德·菲尔德 (1979)",
        arc_count=3,
        arc_names=["建置 (Setup)", "对抗 (Confrontation)", "解决 (Resolution)"],
        arc_purposes=[
            "建立世界观·引入主角·触发激励事件·第一幕转折点(约25%处)",
            "主角面对障碍·冲突升级·中点转折·最黑暗时刻·第二幕转折点(约75%处)",
            "高潮·冲突解决·新平衡建立·主题揭示",
        ],
        description="最经典的叙事结构。第一幕引入人物和冲突，第二幕让冲突升级到不可调和，第三幕在决战中达到高潮并回归新平衡。",
        best_for="电影剧本、电视剧、商业类型片",
    ),
    StoryStructure(
        key="five-act",
        label="五幕结构",
        label_en="Five-Act Structure",
        origin="莎士比亚 → 古斯塔夫·弗赖塔格 (1863)",
        arc_count=5,
        arc_names=["序幕 (Exposition)", "上升 (Rising Action)", "高潮 (Climax)", "下降 (Falling Action)", "结局 (Denouement)"],
        arc_purposes=[
            "介绍背景·人物·核心冲突种子",
            "冲突逐步升级·障碍增加·张力累积",
            "冲突达到顶点·不可逆转的转折",
            "高潮后果展开·余波与清算",
            "最终解决·新秩序·主题完成",
        ],
        description="弗赖塔格金字塔。比三幕更细的划分——把'对抗'拆成上升和下降两个阶段，为悲剧和史诗提供了更精确的节奏控制。",
        best_for="史诗/悲剧/严肃文学改编",
    ),
    StoryStructure(
        key="kishotenketsu",
        label="起承转合",
        label_en="Kishōtenketsu",
        origin="中国古典诗学 → 日本叙事传统",
        arc_count=4,
        arc_names=["起 (Ki) ", "承 (Shō) ", "转 (Ten) ", "合 (Ketsu) "],
        arc_purposes=[
            "引入人物、场景和初始情境——建立读者预期",
            "在前述基础上展开和深化——看似延续但不重复",
            "引入一个看似无关的转折或新角度——颠覆预期但保持内在逻辑",
            "前三部分的合流——揭示隐藏联系，形成统一理解",
        ],
        description="东亚叙事核心。与西方冲突驱动不同，起承转合不依赖对抗，而是通过视角转换和内在联系推进。'转'不是高潮，是重新定义问题的角度。",
        best_for="竖屏短剧、文学改编、以情感/关系为核心的叙事",
    ),
    StoryStructure(
        key="hero-journey",
        label="英雄之旅",
        label_en="The Hero's Journey",
        origin="约瑟夫·坎贝尔 (1949) → 克里斯托弗·沃格勒 (1992)",
        arc_count=4,
        arc_names=["启程 (Departure)", "启蒙 (Initiation)", "考验 (Ordeal)", "归来 (Return)"],
        arc_purposes=[
            "平凡世界→冒险召唤→拒绝召唤→遇见导师→跨越第一道门槛",
            "考验·盟友·敌人→接近最深洞穴→核心磨难",
            " reward → 返回之路→复活→携万能药归来",
            "新自我在新世界中的位置·旅程的完成",
        ],
        description="单主角成长弧线的经典模板。四个阶段对应12个具体节拍，强调主角从平凡到非凡的内外转变。",
        best_for="冒险/奇幻/动作/个人成长题材",
    ),
    StoryStructure(
        key="save-the-cat",
        label="救猫咪节拍表",
        label_en="Save the Cat! Beat Sheet",
        origin="布莱克·斯奈德 (2005)",
        arc_count=4,
        arc_names=["设定 (Setup)", "新世界 (New World)", "坏蛋逼近 (Bad Guys Close In)", "终局 (Finale)"],
        arc_purposes=[
            "开场画面→主题陈述→催化剂→争执（约占25%）",
            "第二幕衔接点→B故事→游戏时间→中点→坏蛋逼近（约占25%-75%）",
            "一无所有→灵魂黑夜→第三幕衔接点（约占75%）",
            "终局→最终画面（约占最后25%）",
        ],
        description="好莱坞最广泛使用的商业剧本结构。15个精确节拍，强调情绪节奏和观众体验，以'救人猫咪'命名——意指主角必须有一个让观众喜欢他的时刻。",
        best_for="商业电影、竖屏短剧、类型电视剧",
    ),
    StoryStructure(
        key="eight-sequence",
        label="八序列法",
        label_en="Eight-Sequence Method",
        origin="弗兰克·丹尼尔 → 古拉克 (USC电影学院)",
        arc_count=4,
        arc_names=["第一幕 (Act I)", "第二幕前半 (Act II-A)", "第二幕后半 (Act II-B)", "第三幕 (Act III)"],
        arc_purposes=[
            "序列1: 现状与激励事件·序列2: 主角做出不可逆决定（占25%）",
            "序列3: 新世界探索·序列4: 中点——赌注提高（占25%-50%）",
            "序列5: 冲突最激烈·序列6: 低谷——看似失败（占50%-75%）",
            "序列7: 反击——新力量·序列8: 高潮与解决（占最后25%）",
        ],
        description="把三幕拆成八个15分钟序列，每序列有独立的小高潮。USC电影学院标准教学法，适合精确控制节奏的创作。",
        best_for="电视剧集、网剧、需要严格时长控制的项目",
    ),
    StoryStructure(
        key="syd-field",
        label="菲尔德范式",
        label_en="Syd Field Paradigm",
        origin="悉德·菲尔德 (1979)",
        arc_count=3,
        arc_names=["建置 (Setup)", "对抗 (Confrontation)", "解决 (Resolution)"],
        arc_purposes=[
            "前25%: 引入主要人物·戏剧性前提·戏剧性情境·情节点1",
            "中间50%: 对抗·障碍·人物弧线展开·情节点2",
            "后25%: 解决·高潮·结局",
        ],
        description="三幕结构的行业标准化版本。明确定义了'情节点'(Plot Point)——推动故事进入下一幕的关键事件。每一幕都有精确的页数比例。",
        best_for="标准长片剧本、商业类型片",
    ),
]


def get_structure(key: str) -> StoryStructure:
    for s in STRUCTURES:
        if s.key == key:
            return s
    return STRUCTURES[0]  # default: three-act


def structure_labels() -> list[dict]:
    return [{"key": s.key, "label": s.label, "label_en": s.label_en,
             "description": s.description, "best_for": s.best_for} for s in STRUCTURES]
