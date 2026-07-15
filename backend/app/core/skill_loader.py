"""
Skill Loader — Load Markdown skill files as Agent system prompts.
"""
from pathlib import Path
from .config import SKILLS_DIR


class SkillLoader:
    """Load and manage Agent Skill markdown files."""

    def __init__(self, skills_dir: Path = SKILLS_DIR):
        self.skills_dir = Path(skills_dir)
        self._cache: dict[str, str] = {}

    def load(self, name: str) -> str:
        """Load a skill by name. Returns the markdown content."""
        if name in self._cache:
            return self._cache[name]

        skill_path = self.skills_dir / f"{name}.md"
        if not skill_path.exists():
            raise FileNotFoundError(f"Skill not found: {skill_path}")

        content = skill_path.read_text(encoding="utf-8")
        self._cache[name] = content
        return content

    def load_multi(self, names: list[str]) -> str:
        """Load multiple skills and concatenate them."""
        contents = []
        for name in names:
            try:
                contents.append(self.load(name))
            except FileNotFoundError:
                continue
        return "\n\n---\n\n".join(contents)


_skill_loader: SkillLoader | None = None


def get_skill_loader() -> SkillLoader:
    global _skill_loader
    if _skill_loader is None:
        _skill_loader = SkillLoader()
    return _skill_loader
