"""SKILL.md 三层懒加载系统，仿 Toonflow / Anthropic / Matt Pocock 规范。

三层结构:
- **主技能** — ``backend/skills/*.md``，Agent 启动时只把 name+description 注入到
  system prompt 做"菜单"。
- **次级技能** — 主技能激活后，同目录下的 workspace / 子目录里的 md 文件作为
  资源列表暴露给 Agent。
- **三级技能** — 递归子目录里所有 md，Agent 用 ``read_skill_file`` 按需读。

Frontmatter 格式（跟 Anthropic Skill 一致）:
    ---
    name: <技能名, 中文短句>
    description: <一句话描述>
    ---
    正文...

设计约束:
- 只读 skills 目录内的 md 文件；任何路径穿越（``../``）一律拒绝。
- 内容纯 UTF-8；不做任何 render/HTML 转义 —— 交给上层 Agent。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parent.parent.parent / "skills"


class SkillNotFound(FileNotFoundError):
    """主技能文件不存在，或名字不匹配 frontmatter。"""


class SkillPathViolation(PermissionError):
    """请求的路径超出 skills 目录范围（防止 ../ 攻击）。"""


class SkillFrontmatterError(ValueError):
    """SKILL.md 缺少 frontmatter 或 name / description 字段。"""


@dataclass
class SkillMeta:
    """主技能的目录卡片 — 只装 name + description，用于 Agent 选择。"""
    name: str
    description: str
    filename: str  # 相对 SKILLS_ROOT，例如 "script_execution_ideation.md"


_FRONTMATTER_RE = re.compile(r"^\ufeff?---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", re.DOTALL)


def parse_frontmatter(content: str) -> dict[str, str]:
    """从 SKILL.md 头部的 ``---`` 块里抠出 name / description。

    简易实现：只支持单行标量值和双引号，不支持嵌套 YAML — 我们的技能文件都用
    单行；如果后续需要更复杂结构再上 PyYAML。

    Raises :class:`SkillFrontmatterError` 如果缺 frontmatter 或必要字段。
    """
    m = _FRONTMATTER_RE.match(content)
    if not m:
        raise SkillFrontmatterError("缺少 --- 包裹的 frontmatter")

    fields: dict[str, str] = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        # 去掉两端引号
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        fields[key] = val

    if "name" not in fields or "description" not in fields:
        raise SkillFrontmatterError("frontmatter 必须同时包含 name 和 description")
    return fields


def _strip_frontmatter(content: str) -> str:
    """把 frontmatter 头砍掉，只留正文。"""
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return content
    return content[m.end():]


def _is_inside(child: Path, parent: Path) -> bool:
    """child 是否在 parent 目录下（防 ../ 穿越）。"""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _skills_root() -> Path:
    return SKILLS_ROOT


def list_available_skills(root: Path | None = None) -> list[SkillMeta]:
    """扫描 skills 根目录（递归）里所有带 frontmatter 的 ``*.md``。

    Toonflow 只把根目录的 md 当主技能；我们简化为「凡是有 frontmatter 的 md
    都是主技能」——包括根目录的 execution skills 和 ``story_skills/xxx/README.md``
    这类专家包入口。Agent 拿到一份统一的技能菜单，通过 name 激活。
    """
    root = root or _skills_root()
    if not root.exists():
        return []
    metas: list[SkillMeta] = []
    for path in sorted(root.rglob("*.md")):
        if not path.is_file():
            continue
        try:
            fm = parse_frontmatter(path.read_text(encoding="utf-8"))
        except SkillFrontmatterError:
            continue  # 允许无-frontmatter 的散装 md（如 director_skills 里的技法文件）
        metas.append(SkillMeta(
            name=fm["name"],
            description=fm["description"],
            filename=str(path.relative_to(root)),
        ))
    return metas


def build_skill_menu_prompt(root: Path | None = None) -> str:
    """构造要注入到 Agent system prompt 的 ``<available_skills>`` 目录块。

    Agent 看到 name + description 就能判断当前任务该激活哪个技能，然后调用
    ``activate_skill`` 拿到完整指令。
    """
    metas = list_available_skills(root)
    if not metas:
        return ""
    entries = "\n".join(
        f"  <skill>\n"
        f"    <name>{m.name}</name>\n"
        f"    <description>{m.description}</description>\n"
        f"  </skill>"
        for m in metas
    )
    return (
        "## Skills\n"
        "以下技能提供了专业任务的专用指令。\n"
        "当任务与某个技能的描述匹配时，调用 activate_skill 工具并传入技能名称加载完整指令。\n"
        "加载后遵循技能指令执行任务，需要时调用 read_skill_file 读取资源文件内容。\n\n"
        "<available_skills>\n"
        f"{entries}\n"
        "</available_skills>"
    )


def _find_skill_by_name(name: str, root: Path) -> Path:
    """按 frontmatter.name 反查主技能文件路径。"""
    for meta in list_available_skills(root):
        if meta.name == name:
            return root / meta.filename
    raise SkillNotFound(f"技能 '{name}' 未找到")


def list_resources(main_skill_path: Path, root: Path) -> list[str]:
    """列出主技能同名目录下的所有资源文件（递归）。

    约定：``script_execution_ideation.md`` 的资源目录是同目录下同名子文件夹，
    或者 ``story_skills/<name>/`` 这种独立包目录。这里做通用扫描 —
    如果 md 文件本身在一个子目录里（如 ``story_skills/male_lead_shuang/README.md``），
    就返回该子目录下的所有 md 相对路径。
    """
    resources: list[str] = []
    # 情况 A：主技能是根目录下的独立 md — 找同名子目录
    same_name_dir = main_skill_path.parent / main_skill_path.stem
    if same_name_dir.is_dir():
        for p in same_name_dir.rglob("*.md"):
            resources.append(str(p.relative_to(root)))
    # 情况 B：主技能就在一个子目录里（如 story_skills/xxx/README.md） — 返回同目录内其他 md
    elif main_skill_path.parent != root:
        for p in main_skill_path.parent.rglob("*.md"):
            if p == main_skill_path:
                continue
            resources.append(str(p.relative_to(root)))
    return sorted(resources)


def activate_skill(name: str, root: Path | None = None) -> dict:
    """加载指定主技能的完整正文 + 资源清单。

    Agent 调用后应把返回的 ``content`` 作为新的 turn message 放入上下文，
    然后按需调 ``read_skill_file`` 拉具体资源。
    """
    root = root or _skills_root()
    skill_path = _find_skill_by_name(name, root)
    if not _is_inside(skill_path, root):
        raise SkillPathViolation(f"技能路径越界: {skill_path}")

    raw = skill_path.read_text(encoding="utf-8")
    body = _strip_frontmatter(raw).strip() or "该技能文件无正文内容。"
    resources = list_resources(skill_path, root)

    return {
        "name": name,
        "body": body,
        "resources": resources,
        "filename": str(skill_path.relative_to(root)),
    }


def read_skill_file(rel_path: str, root: Path | None = None) -> str:
    """读 skills 目录内的资源文件（安全边界检查）。

    ``rel_path`` 必须是 skills 根目录下的相对路径。任何绝对路径、``../``
    或指向根外的软链都会被拒绝。
    """
    root = root or _skills_root()
    if not rel_path or rel_path.strip() == "":
        raise ValueError("rel_path 不能为空")

    # 关键：先拼再 resolve，用 _is_inside 校验
    target = (root / rel_path).resolve()
    if not _is_inside(target, root):
        raise SkillPathViolation(f"路径越界: {rel_path}")
    if not target.is_file():
        raise FileNotFoundError(f"文件不存在: {rel_path}")

    text = target.read_text(encoding="utf-8")
    return text or "该资源文件为空。"
