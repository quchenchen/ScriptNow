from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import frontmatter
from agentscope.skill import LocalSkillLoader

SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# Product domains stay isolated at resolution time.  Editor skills support
# translation/localisation workflows and may coexist in the shared catalog,
# but are never mounted into novel or script agents unless that domain is
# requested explicitly.
ALLOWED_DOMAINS = frozenset({"platform", "novel", "script", "editor"})


def resolve_skills_root() -> Path:
    """Resolve the skill catalog for source checkouts and packaged runtimes."""
    configured = os.getenv("SCRIPTNOW_SKILLS_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()

    candidates = (
        Path(__file__).resolve().parents[3] / "skills",
        Path.cwd() / "skills",
        Path("/app/skills"),
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    return candidates[0].resolve()
TAG_ALIASES = {
    "奇幻": "fantasy",
    "爱情": "romance",
    "悬疑": "mystery",
    "侦探": "mystery",
    "怪谈": "rules-horror",
    "言情": "romance",
    "恋爱": "romance",
    "霸总": "billionaire-romance",
    "宫斗": "palace-intrigue",
    "都市": "urban-power",
    "赘婿": "wealth-fantasy",
    "修仙": "cultivation",
    "直播": "livestream",
    "竞技": "gaming-sports",
    "历史": "historical-fiction",
    "民国": "republican-romance",
    "暗黑奇幻": "dark-fantasy",
    "狼人": "werewolf",
    "哥特悬疑": "gothic-mystery",
    "成熟": "mature",
    "幽暗": "dark",
    "感官克制": "sensual-restraint",
    "人物关系驱动": "relationship-driven",
    "番茄": "fanqie",
    "番茄小说": "fanqie",
    "tomato": "fanqie",
    "海外连载": "global-serial",
    "都市脑洞": "urban-power",
    "都市日常": "urban-life",
    "都市高武": "urban-martial-arts",
    "神豪": "wealth-fantasy",
    "职场": "workplace",
    "现实": "realist",
    "系统": "system-progression",
    "玄幻": "xuanhuan",
    "东方玄幻": "eastern-fantasy",
    "仙侠": "xianxia",
    "东方仙侠": "xianxia",
    "修炼": "cultivation",
    "升级": "progression",
    "现代言情": "contemporary-romance",
    "古代言情": "historical-romance",
    "豪门": "billionaire-romance",
    "婚恋": "marriage-romance",
    "甜宠": "sweet-romance",
    "虐恋": "angst-romance",
    "重生": "rebirth-romance",
    "背叛": "betrayal-romance",
    "追妻": "regret-romance",
    "宫斗宅斗": "palace-intrigue",
    "推理": "detective",
    "末世": "post-apocalyptic",
    "科幻末世": "post-apocalyptic",
    "无限流": "infinite-flow",
    "规则怪谈": "rules-horror",
    "狼人爱情": "werewolf-romance",
    "超自然爱情": "paranormal-romance",
    "吸血鬼": "vampire",
    "浪漫奇幻": "romantasy",
    "亿万富翁": "billionaire-romance",
    "黑帮爱情": "mafia-romance",
    "黑暗爱情": "dark-romance",
    "浪漫悬疑": "romantic-suspense",
    "惊悚": "thriller",
    "犯罪": "crime",
    "恐怖": "horror",
    "科幻": "science-fiction",
    "克苏鲁": "cosmic-horror",
    "历史古代": "historical-fiction",
    "历史脑洞": "historical-imagination",
    "古言": "historical-romance",
    "多子多福": "family-progression",
    "女频悬疑": "female-led-mystery",
    "年代": "era-fiction",
    "幻想言情": "fantasy-romance",
    "悬疑灵异": "supernatural-mystery",
    "悬疑脑洞": "suspense-concept",
    "抗战谍战": "resistance-espionage",
    "替身文": "substitute-romance",
    "民国言情": "republican-romance",
    "游戏体育": "gaming-sports",
    "狗血言情": "melodramatic-romance",
    "现实题材": "realist",
    "现言脑洞": "contemporary-romance-concept",
    "电竞": "esports",
    "直播文": "livestream",
    "知乎短篇": "zhihu-short",
    "种田": "farming",
    "系统流": "system-progression",
    "职场婚恋": "workplace-romance",
    "西幻": "western-fantasy",
    "豪门总裁": "billionaire-romance",
    "都市异能": "urban-power",
    "青春甜宠": "youth-sweet-romance",
    "高武": "high-martial-arts",
    "黑暗题材": "dark-fiction",
}
ROLE_SKILLS: dict[str, tuple[str, ...]] = {
    "director": ("novel-ideate", "script-develop"),
    "architect": ("novel-plan", "script-storymap"),
    "writer": ("novel-write", "script-write"),
    "reviewer": ("novel-review", "script-review"),
}


class SkillCatalogError(RuntimeError):
    pass


class SkillConflictError(SkillCatalogError):
    pass


@dataclass(frozen=True, slots=True)
class SkillDescriptor:
    name: str
    description: str
    domain: str
    root: Path
    references: tuple[str, ...]
    digest: str
    keywords: tuple[str, ...] = ()
    core: bool = False
    roles: tuple[str, ...] = ()
    stages: tuple[str, ...] = ()
    genres: tuple[str, ...] = ()
    themes: tuple[str, ...] = ()
    styles: tuple[str, ...] = ()
    structures: tuple[str, ...] = ()
    formats: tuple[str, ...] = ()
    platforms: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    selection_priority: int = 0
    admission_status: str = "legacy"
    admission_baseline: str | None = None
    admission_cases: tuple[str, ...] = ()
    quality_status: str = "not_measured"
    benchmark_suite: str | None = None
    benchmark_report: str | None = None


@dataclass(frozen=True, slots=True)
class CreativeProfile:
    medium: str
    language: str
    platforms: tuple[str, ...]
    world_setting: str | None
    genres: tuple[str, ...]
    themes: tuple[str, ...]
    styles: tuple[str, ...]
    structures: tuple[str, ...]
    formats: tuple[str, ...]
    pov: str | None
    audience: str | None
    constraints: tuple[str, ...]
    preferences: dict[str, str] | None
    fingerprint: str

    @classmethod
    def from_direction(cls, *, medium: str, direction: dict[str, object]) -> CreativeProfile:
        language = _normalise_language(_optional_text(direction.get("language")) or "zh-CN")
        platforms = _direction_tags(
            direction,
            "platforms",
            "platform",
            "target_platform",
            "distribution_platform",
        )
        if not platforms:
            platforms = ("fanqie",) if language.startswith("zh") else ("global-serial",)
        values = {
            "medium": medium,
            "language": language,
            "platforms": platforms,
            "world_setting": _optional_text(direction.get("world_setting")),
            "genres": _direction_tags(direction, "genres", "genre"),
            "themes": _direction_tags(direction, "themes", "theme"),
            "styles": _direction_tags(direction, "styles", "style", "tone"),
            "structures": _direction_tags(
                direction, "structures", "structure", "narrative_structure"
            ),
            "formats": _direction_tags(direction, "formats", "format", "script_format"),
            "pov": _optional_text(direction.get("pov")),
            "audience": _optional_text(direction.get("audience")),
            "constraints": _direction_tags(direction, "constraints", "must_keep", "forbidden"),
            "preferences": _preferences(direction),
        }
        fingerprint = hashlib.sha256(
            json.dumps(values, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return cls(fingerprint=fingerprint, **values)

    def as_dict(self) -> dict[str, object]:
        return {
            "medium": self.medium,
            "language": self.language,
            "platforms": list(self.platforms),
            "world_setting": self.world_setting,
            "genres": list(self.genres),
            "themes": list(self.themes),
            "styles": list(self.styles),
            "structures": list(self.structures),
            "formats": list(self.formats),
            "pov": self.pov,
            "audience": self.audience,
            "constraints": list(self.constraints),
            "preferences": self.preferences,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class SkillSelection:
    skill: SkillDescriptor
    layer: str
    score: int
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.skill.name,
            "digest": self.skill.digest,
            "layer": self.layer,
            "score": self.score,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class SkillPlan:
    medium: str
    role_key: str
    stage: str
    creative_profile_fingerprint: str
    selections: tuple[SkillSelection, ...]
    resolver_version: int = 1

    def as_dict(self) -> dict[str, object]:
        return {
            "medium": self.medium,
            "role_key": self.role_key,
            "stage": self.stage,
            "creative_profile_fingerprint": self.creative_profile_fingerprint,
            "resolver_version": self.resolver_version,
            "selections": [selection.as_dict() for selection in self.selections],
        }


class SkillResolver:
    def __init__(self, catalog: SkillCatalog, *, optional_limit: int = 6) -> None:
        self.catalog = catalog
        self.optional_limit = optional_limit

    def resolve(
        self,
        *,
        profile: CreativeProfile,
        role_key: str,
        stage: str,
        explicit_skill_keys: tuple[str, ...] = (),
    ) -> SkillPlan:
        domain_skills = self.catalog.for_domain(profile.medium)
        core = tuple(
            item
            for item in domain_skills
            if item.core
            and (not item.roles or role_key in item.roles)
            and (not item.stages or stage in item.stages)
            and (not item.languages or _language_matches(profile.language, item.languages))
        )
        if not core:
            core = self.catalog.for_role(domain=profile.medium, role_key=role_key)
        core_names = {item.name for item in core}
        selections = [
            SkillSelection(item, "core", 10_000, ("角色与领域核心绑定",)) for item in core
        ]
        available = {item.name: item for item in domain_skills}
        for key in dict.fromkeys(explicit_skill_keys):
            skill = available.get(key)
            if skill is None:
                raise SkillCatalogError(f"explicit skill is unavailable in domain: {key}")
            if skill.roles and role_key not in skill.roles:
                raise SkillCatalogError(f"explicit skill does not support role {role_key}: {key}")
            if skill.stages and stage not in skill.stages:
                raise SkillCatalogError(f"explicit skill does not support stage {stage}: {key}")
            if skill.languages and not _language_matches(profile.language, skill.languages):
                raise SkillCatalogError(f"explicit skill does not support language: {key}")
            if (
                self.catalog.admission_enforced_for(profile.medium)
                and self.catalog.admission_enforced
                and skill.admission_status != "admitted"
            ):
                raise SkillCatalogError(f"explicit skill has not passed admission: {key}")
            if key not in core_names:
                selections.append(
                    SkillSelection(skill, "explicit", 20_000, ("用户发起的显式能力操作",))
                )
                core_names.add(key)
        optional: list[SkillSelection] = []
        for skill in domain_skills:
            if skill.name in core_names or not skill.roles or role_key not in skill.roles:
                continue
            if (
                self.catalog.admission_enforced_for(profile.medium)
                and self.catalog.admission_enforced
                and skill.admission_status != "admitted"
            ):
                continue
            if skill.stages and stage not in skill.stages:
                continue
            score, reasons = _match_skill(skill, profile)
            if reasons:
                optional.append(
                    SkillSelection(skill, "style_pack", score + skill.selection_priority, reasons)
                )
        optional.sort(key=lambda item: (-item.score, item.skill.name))
        selections.extend(optional[: self.optional_limit])
        return SkillPlan(
            medium=profile.medium,
            role_key=role_key,
            stage=stage,
            creative_profile_fingerprint=profile.fingerprint,
            selections=tuple(selections),
        )


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _normalise_tag(value: object) -> str:
    normalized = re.sub(r"[-_\s]+", "-", str(value).strip().lower()).strip("-")
    return TAG_ALIASES.get(normalized, normalized)


def _raw_tags(value: object) -> tuple[str, ...]:
    """Split tag lists without alias normalisation so Chinese compounds survive."""
    if isinstance(value, str):
        raw = re.split(r"[,，、;/]+", value)
    elif isinstance(value, list | tuple | set):
        raw = list(value)
    elif value is None:
        raw = []
    else:
        raw = [value]
    return tuple(
        dict.fromkeys(
            tag
            for item in raw
            if (tag := re.sub(r"[-_\s]+", "-", str(item).strip()).strip("-"))
        )
    )


def _preferences(direction: dict[str, object]) -> dict[str, str] | None:
    raw = direction.get("preferences")
    if not isinstance(raw, dict):
        return None
    return {str(k): str(v) for k, v in raw.items() if v is not None}


def _normalise_language(value: str) -> str:
    parts = re.split(r"[-_]", value.strip())
    if not parts:
        return "zh-CN"
    language = parts[0].lower()
    return language if len(parts) == 1 else f"{language}-{parts[1].upper()}"


def _tag_values(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        raw = re.split(r"[,，、;/]+", value)
    elif isinstance(value, list | tuple | set):
        raw = list(value)
    elif value is None:
        raw = []
    else:
        raw = [value]
    return tuple(dict.fromkeys(tag for item in raw if (tag := _normalise_tag(item))))


def _direction_tags(direction: dict[str, object], *keys: str) -> tuple[str, ...]:
    result: list[str] = []
    for key in keys:
        result.extend(_tag_values(direction.get(key)))
    return tuple(dict.fromkeys(result))


def _match_skill(skill: SkillDescriptor, profile: CreativeProfile) -> tuple[int, tuple[str, ...]]:
    if skill.languages and not _language_matches(profile.language, skill.languages):
        return 0, ()
    dimensions = (
        ("平台", set(skill.platforms), set(profile.platforms), 50),
        ("题材", set(skill.genres), set(profile.genres), 40),
        ("主题", set(skill.themes), set(profile.themes), 30),
        ("风格", set(skill.styles), set(profile.styles), 20),
        ("结构", set(skill.structures), set(profile.structures), 30),
        ("格式", set(skill.formats), set(profile.formats), 60),
    )
    score = 0
    reasons: list[str] = []
    for label, expected, actual, weight in dimensions:
        matched = sorted(expected & actual)
        if matched:
            score += weight * len(matched)
            reasons.append(f"{label}匹配：{'、'.join(matched)}")
    query_raw = set(profile.genres) | set(profile.themes) | set(profile.styles)
    if profile.world_setting:
        query_raw.update(_raw_tags(profile.world_setting))
    query_norm = {_normalise_tag(tag) for tag in query_raw}
    keyword_hits: list[str] = []
    for keyword in skill.keywords:
        normalized = _normalise_tag(keyword)
        for token in query_raw:
            if keyword == token or normalized == token or keyword in token or token in keyword:
                keyword_hits.append(keyword)
                break
        else:
            if normalized in query_norm:
                keyword_hits.append(keyword)
    if keyword_hits:
        score += 45 * len(keyword_hits)
        reasons.append("题材关键词匹配：" + "、".join(sorted(set(keyword_hits))))
    if not any(expected for _, expected, _, _ in dimensions):
        reasons.append("阶段通用能力")
    return score, tuple(reasons)


def _language_matches(language: str, expected: tuple[str, ...]) -> bool:
    actual = language.lower()
    return any(
        actual == item.lower() or actual.split("-", 1)[0] == item.lower().split("-", 1)[0]
        for item in expected
    )


class SkillCatalog:
    """Filesystem is the source of truth; the catalog validates before runtime use."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self._admission_registry = self._read_admission_registry()
        self.admission_enforced = bool(self._admission_registry)

    def scan(self) -> tuple[SkillDescriptor, ...]:
        if not self.root.is_dir():
            raise SkillCatalogError(f"skill root does not exist: {self.root}")
        found: list[SkillDescriptor] = []
        names: set[str] = set()
        for path in sorted(self.root.glob("*/*/SKILL.md")):
            descriptor = self._read(path)
            if descriptor.name in names:
                raise SkillCatalogError(f"duplicate skill name: {descriptor.name}")
            names.add(descriptor.name)
            found.append(descriptor)
        if not found:
            raise SkillCatalogError("skill catalog is empty")
        return tuple(found)

    def for_domain(self, domain: str) -> tuple[SkillDescriptor, ...]:
        if domain not in ALLOWED_DOMAINS:
            raise SkillCatalogError(f"unsupported skill domain: {domain}")
        return tuple(item for item in self.scan() if item.domain in {"platform", domain})

    def admission_enforced_for(self, domain: str) -> bool:
        return bool(self._admission_registry.get(domain))

    def detail(self, name: str) -> tuple[SkillDescriptor, str]:
        descriptor = next((item for item in self.scan() if item.name == name), None)
        if descriptor is None:
            raise SkillCatalogError(f"skill not found: {name}")
        post = frontmatter.loads((descriptor.root / "SKILL.md").read_text(encoding="utf-8"))
        return descriptor, post.content

    def instructions_for(
        self,
        *,
        domain: str,
        skill_keys: tuple[str, ...] | list[str],
        max_chars: int = 6_000,
    ) -> list[tuple[str, str]]:
        """Render selected skill instructions for prompt injection, in plan order."""
        allowed = {item.name: item for item in self.for_domain(domain)}
        result: list[tuple[str, str]] = []
        budget = int(max_chars)
        for key in dict.fromkeys(skill_keys):
            descriptor = allowed.get(str(key))
            if descriptor is None or budget <= 0:
                continue
            post = frontmatter.loads(
                (descriptor.root / "SKILL.md").read_text(encoding="utf-8")
            )
            text = post.content.strip()
            if not text:
                continue
            if len(text) > budget:
                text = text[:budget] + "\n……（本节为截断，完整版本可通过技能工具读取）"
            result.append((descriptor.name, text))
            budget -= len(text)
        return result

    def update(
        self, *, name: str, description: str, instructions: str, expected_digest: str
    ) -> SkillDescriptor:
        descriptor, _ = self.detail(name)
        if descriptor.digest != expected_digest:
            raise SkillConflictError("skill changed since it was opened")
        path = descriptor.root / "SKILL.md"
        post = frontmatter.loads(path.read_text(encoding="utf-8"))
        post["description"] = description.strip()
        post.content = instructions.strip()
        if not post["description"] or not post.content:
            raise SkillCatalogError("skill requires description and instructions")
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent, prefix=".skill-", delete=False
            ) as temporary:
                temporary.write(frontmatter.dumps(post))
                temporary.write("\n")
                temporary_path = Path(temporary.name)
            validated = self._read(temporary_path)
            os.replace(temporary_path, path)
            return SkillDescriptor(
                name=validated.name,
                description=validated.description,
                domain=validated.domain,
                root=path.parent,
                references=validated.references,
                digest=self._read(path).digest,
                keywords=validated.keywords,
                core=validated.core,
                roles=validated.roles,
                stages=validated.stages,
                genres=validated.genres,
                themes=validated.themes,
                styles=validated.styles,
                structures=validated.structures,
                formats=validated.formats,
                platforms=validated.platforms,
                languages=validated.languages,
                selection_priority=validated.selection_priority,
                admission_status=validated.admission_status,
                admission_baseline=validated.admission_baseline,
                admission_cases=validated.admission_cases,
                quality_status=validated.quality_status,
                benchmark_suite=validated.benchmark_suite,
                benchmark_report=validated.benchmark_report,
            )
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    def for_role(self, *, domain: str, role_key: str) -> tuple[SkillDescriptor, ...]:
        allowed = {item.name: item for item in self.for_domain(domain)}
        requested = (*ROLE_SKILLS.get(role_key, ()), "project-diagnose")
        return tuple(allowed[name] for name in requested if name in allowed)

    def loader(self, domain: str) -> LocalSkillLoader:
        domain_root = (self.root / domain).resolve()
        if domain_root.parent != self.root or not domain_root.is_dir():
            raise SkillCatalogError(f"skill domain does not exist: {domain}")
        return LocalSkillLoader(str(domain_root), scan_subdir=True)

    def loaders_for_plan(
        self, *, domain: str, skill_keys: list[object]
    ) -> tuple[LocalSkillLoader, ...]:
        allowed = {item.name: item for item in self.for_domain(domain)}
        requested = list(dict.fromkeys(str(key) for key in skill_keys))
        unknown = [key for key in requested if key not in allowed]
        if unknown:
            raise SkillCatalogError(f"skill plan references unknown skills: {', '.join(unknown)}")
        unadmitted = [
            key
            for key in requested
            if self.admission_enforced_for(domain)
            and self.admission_enforced
            and allowed[key].roles
            and allowed[key].admission_status != "admitted"
        ]
        if unadmitted:
            raise SkillCatalogError(
                f"skill plan references unadmitted skills: {', '.join(unadmitted)}"
            )
        return tuple(LocalSkillLoader(str(allowed[key].root)) for key in requested)

    def fingerprint(self, *, domain: str, role_key: str) -> str:
        payload = "\n".join(
            f"{item.name}:{item.digest}" for item in self.for_role(domain=domain, role_key=role_key)
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def _read(self, path: Path) -> SkillDescriptor:
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(self.root)
        except ValueError as error:
            raise SkillCatalogError(f"skill escapes catalog: {path}") from error
        domain = relative.parts[0]
        folder_name = relative.parts[1]
        if domain not in ALLOWED_DOMAINS:
            raise SkillCatalogError(f"unsupported skill domain: {domain}")
        try:
            post = frontmatter.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as error:
            raise SkillCatalogError(f"invalid skill document: {resolved}") from error
        name = str(post.get("name", "")).strip()
        description = str(post.get("description", "")).strip()
        if not SKILL_NAME.fullmatch(name) or name != folder_name:
            raise SkillCatalogError(f"invalid or mismatched skill name: {name or folder_name}")
        if not description or not post.content.strip():
            raise SkillCatalogError(f"skill requires description and instructions: {name}")
        references: list[str] = []
        for match in re.finditer(r"\[[^]]+\]\(([^)]+)\)", post.content):
            target = match.group(1).split("#", 1)[0]
            if not target or "://" in target or target.startswith("#"):
                continue
            ref = (resolved.parent / target).resolve()
            try:
                ref.relative_to(resolved.parent)
            except ValueError as error:
                raise SkillCatalogError(
                    f"reference escapes skill root: {name}: {target}"
                ) from error
            if not ref.is_file():
                raise SkillCatalogError(f"missing skill reference: {name}: {target}")
            references.append(ref.relative_to(resolved.parent).as_posix())
        digest = hashlib.sha256()
        digest.update(resolved.read_bytes())
        for reference in sorted(set(references)):
            digest.update(reference.encode())
            digest.update((resolved.parent / reference).read_bytes())
        metadata = post.get("metadata")
        product_metadata: dict[str, object] = {}
        if isinstance(metadata, dict):
            legacy_metadata = metadata.get("scriptflow", {})
            current_metadata = metadata.get("scriptnow", {})
            if isinstance(legacy_metadata, dict):
                product_metadata.update(legacy_metadata)
            if isinstance(current_metadata, dict):
                product_metadata.update(current_metadata)

        def product_value(key: str, default: object = None) -> object:
            # New skills write the ScriptNow namespace. Imported skills created
            # before the rename remain readable without keeping the old name in
            # the active catalog.
            return product_metadata.get(key, post.get(key, default))

        admission = self._admission_registry.get(domain, {}).get(name, {})
        if not isinstance(admission, dict):
            raise SkillCatalogError(f"invalid admission record: {name}")
        if admission:
            digest.update(json.dumps(admission, sort_keys=True).encode())

        return SkillDescriptor(
            name=name,
            description=description,
            domain=domain,
            root=resolved.parent,
            references=tuple(sorted(set(references))),
            digest=digest.hexdigest(),
            keywords=_raw_tags(product_value("keywords")),
            core=bool(product_value("core", False)),
            roles=_tag_values(product_value("roles")),
            stages=_tag_values(product_value("stages")),
            genres=_tag_values(product_value("genres")),
            themes=_tag_values(product_value("themes")),
            styles=_tag_values(product_value("styles")),
            structures=_tag_values(product_value("structures")),
            formats=_tag_values(product_value("formats")),
            platforms=_tag_values(product_value("platforms")),
            languages=tuple(
                _normalise_language(item) for item in _tag_values(product_value("languages"))
            ),
            selection_priority=int(product_value("selection_priority", 0)),
            admission_status=str(admission.get("status") or "legacy"),
            admission_baseline=(
                str(admission["baseline"]) if admission.get("baseline") else None
            ),
            admission_cases=tuple(str(item) for item in admission.get("cases") or []),
            quality_status=str(admission.get("quality_status") or "not_measured"),
            benchmark_suite=(
                str(admission["benchmark_suite"]) if admission.get("benchmark_suite") else None
            ),
            benchmark_report=(
                str(admission["benchmark_report"]) if admission.get("benchmark_report") else None
            ),
        )

    def _read_admission_registry(self) -> dict[str, dict[str, dict[str, object]]]:
        path = self.root / "admission.json"
        if not path.is_file():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise SkillCatalogError("invalid skill admission registry") from error
        domains = value.get("domains") if isinstance(value, dict) else None
        if not isinstance(domains, dict):
            raise SkillCatalogError("skill admission registry requires domains")
        result: dict[str, dict[str, dict[str, object]]] = {}
        for domain, records in domains.items():
            if domain not in ALLOWED_DOMAINS or not isinstance(records, dict):
                raise SkillCatalogError(f"invalid admission domain: {domain}")
            result[domain] = records
        return result
