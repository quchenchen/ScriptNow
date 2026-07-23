import ast
import re
from pathlib import Path

PACKAGE_ROOT = Path(__file__).parents[1] / "src" / "scriptflow_v7"
CREATOR_ROOT = Path(__file__).parents[2] / "frontend" / "apps" / "creator" / "src"

FORBIDDEN_IMPORTS = {
    "platform": ("scriptflow_v7.script", "scriptflow_v7.novel"),
    "script": ("scriptflow_v7.novel", "scriptflow_v6", "backend.app"),
    "novel": ("scriptflow_v7.script", "scriptflow_v6", "backend.app"),
}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_domain_import_boundaries() -> None:
    violations: list[str] = []
    for area, forbidden_prefixes in FORBIDDEN_IMPORTS.items():
        for path in (PACKAGE_ROOT / area).rglob("*.py"):
            for module in imported_modules(path):
                if module.startswith(forbidden_prefixes):
                    violations.append(f"{path.relative_to(PACKAGE_ROOT)} imports {module}")

    assert violations == []


def test_novel_frontend_does_not_import_script_capabilities() -> None:
    novel_files = [
        CREATOR_ROOT / "stores" / "novel.ts",
        CREATOR_ROOT / "components" / "NovelStudio.vue",
    ]
    violations = []
    for path in novel_files:
        specifiers = re.findall(r"\bfrom\s+['\"]([^'\"]+)['\"]", path.read_text(encoding="utf-8"))
        relative_parts = [
            part.casefold()
            for specifier in specifiers
            if specifier.startswith(".")
            for part in specifier.replace("\\", "/").split("/")
        ]
        if any(part == "script" or part.startswith("scriptstudio") for part in relative_parts):
            violations.append(str(path.relative_to(CREATOR_ROOT)))
    assert violations == []


def test_v7_runtime_has_no_legacy_import_or_reference() -> None:
    roots = [PACKAGE_ROOT, CREATOR_ROOT, CREATOR_ROOT.parents[1] / "admin" / "src"]
    violations: list[str] = []
    legacy_markers = ("scriptflow_v6", "scriptflow-v6", "backend.app")
    for root in roots:
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".ts", ".vue", ".js"}:
                continue
            content = path.read_text(encoding="utf-8").lower()
            if any(marker in content for marker in legacy_markers):
                violations.append(str(path))
    assert violations == []
