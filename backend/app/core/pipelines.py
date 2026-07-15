"""Pipeline definitions for three project types: novel, script, video_prompt."""

PIPELINES = {
    "novel": {
        "label": "小说创作",
        "stages": [
            {"key": "story_design", "label": "故事设计", "skill": "novel/story.md",
             "desc": "世界观+主线+爽点设计"},
            {"key": "characters", "label": "角色塑造", "skill": "novel/characters.md",
             "desc": "主角+配角+反派+关系网"},
            {"key": "outline", "label": "章节大纲", "skill": "novel/outline.md",
             "desc": "分卷章节+章节钩子"},
            {"key": "writing", "label": "逐章撰写", "skill": "novel/writing.md",
             "desc": "Agent 逐章撰写，表格管理"},
            {"key": "proofread", "label": "智能校对", "skill": "novel/proofread.md",
             "desc": "错别字+逻辑+一致性检查"},
            {"key": "polish", "label": "润色定稿", "skill": "novel/polish.md",
             "desc": "文风统一+节奏优化"},
        ],
        "default_units": 100,  # chapters
        "unit_label": "章",
    },
    "script": {
        "label": "剧本创作",
        "stages": [
            {"key": "ideation", "label": "灵感孵化", "skill": "ideation/main.md",
             "desc": "生成3个差异化创意方案"},
            {"key": "structure", "label": "故事架构", "skill": "structure/main.md",
             "desc": "角色+大纲+爽点分布"},
            {"key": "writing", "label": "剧本撰写", "skill": "writing/main.md",
             "desc": "Agent 逐集撰写短剧剧本"},
            {"key": "review", "label": "质量审核", "skill": "review/main.md",
             "desc": "六维评估+问题列表"},
            {"key": "polish", "label": "润色", "skill": "writing/main.md",
             "desc": "对白优化+格式统一"},
            {"key": "assets", "label": "资产提取", "skill": "asset_prompt/main.md",
             "desc": "角色·场景·道具资产"},
            {"key": "prompts", "label": "提示词", "skill": "asset_prompt/main.md",
             "desc": "Seedance 视频提示词"},
        ],
        "default_units": 80,  # episodes
        "unit_label": "集",
    },
    "video_prompt": {
        "label": "视频提示词制作",
        "stages": [
            {"key": "script_analysis", "label": "剧本分析", "skill": "video/analysis.md",
             "desc": "识别关键场景+情绪节点"},
            {"key": "shot_design", "label": "镜头设计", "skill": "video/shot.md",
             "desc": "景别·运镜·机位方案"},
            {"key": "prompt_gen", "label": "提示词生成", "skill": "video/prompt.md",
             "desc": "生成 Seedance 2.0 提示词"},
            {"key": "sound_design", "label": "音效方案", "skill": "video/sound.md",
             "desc": "音效·动效·配乐"},
            {"key": "export", "label": "导出打包", "skill": None,
             "desc": "视频制作清单+提示词打包"},
        ],
        "default_units": 0,  # N/A
        "unit_label": "场景",
    },
}


def get_pipeline(project_type: str) -> dict | None:
    return PIPELINES.get(project_type)


def get_stages(project_type: str) -> list:
    pipeline = PIPELINES.get(project_type, PIPELINES["script"])
    return pipeline["stages"]
