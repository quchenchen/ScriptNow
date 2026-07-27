import json
from pathlib import Path

from scriptnow.platform.skills import TAG_ALIASES, SkillCatalog


def creative_genre_options(catalog: SkillCatalog, *, medium: str) -> list[dict[str, object]]:
    """Expose only genre tags backed by a currently available skill."""
    descriptors = catalog.for_domain(medium)
    owners_by_genre: dict[str, list[str]] = {}
    for descriptor in descriptors:
        if medium == "novel" and descriptor.admission_status != "admitted":
            continue
        for genre in descriptor.genres:
            owners_by_genre.setdefault(genre, []).append(descriptor.name)

    source_labels: dict[str, str] = {}
    if medium == "novel":
        capability_map = (
            Path(__file__).parents[3]
            / "skills"
            / "benchmarks"
            / "novel-genre-capability-map-v1.json"
        )
        if capability_map.exists():
            payload = json.loads(capability_map.read_text(encoding="utf-8"))
            for item in payload.get("categories", []):
                canonical = str(item.get("canonical") or "")
                owner = str(item.get("owner") or "")
                if canonical in owners_by_genre and owner in owners_by_genre[canonical]:
                    source_labels[canonical] = str(item.get("source_label") or canonical)

    aliases_by_tag: dict[str, list[str]] = {}
    for label, canonical in TAG_ALIASES.items():
        if any("\u4e00" <= char <= "\u9fff" for char in label):
            aliases_by_tag.setdefault(canonical, []).append(label)

    options = []
    for canonical, owners in owners_by_genre.items():
        labels = aliases_by_tag.get(canonical, [])
        label_zh = source_labels.get(canonical) or (min(labels, key=len) if labels else canonical)
        options.append(
            {
                "key": canonical,
                "label_zh": label_zh,
                "label_en": canonical.replace("-", " ").title(),
                "skill_keys": sorted(set(owners)),
            }
        )
    return sorted(options, key=lambda item: (str(item["label_zh"]), str(item["key"])))
