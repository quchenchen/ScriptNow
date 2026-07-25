"""Translation glossary — maintains source→target term mappings for consistency.

Built up incrementally as chapters are translated. Injected into the translation
prompt to ensure character names, locations, and key terms are translated consistently.
"""

import re
from dataclasses import dataclass, field


@dataclass
class TranslationGlossary:
    """Per-project term glossary. Terms are source_lang → target_lang mappings."""

    project_id: str
    source_language: str = "en-US"
    target_language: str = ""
    terms: dict[str, str] = field(default_factory=dict)  # source_term → translated_term
    _manual: set[str] = field(default_factory=set)  # manually confirmed terms

    def add(self, source: str, translated: str, *, confirmed: bool = False) -> None:
        if source.strip() and translated.strip():
            self.terms[source.strip()] = translated.strip()
            if confirmed:
                self._manual.add(source.strip())

    def add_batch(self, pairs: dict[str, str]) -> None:
        for src, tgt in pairs.items():
            self.add(src, tgt)

    def get(self, source: str) -> str | None:
        return self.terms.get(source.strip())

    def to_prompt_block(self) -> str:
        """Render glossary as a compact prompt injection for the translator."""
        if not self.terms:
            return ""
        lines = [
            f"## Translation Glossary ({self.source_language} → {self.target_language})",
            "Use these established translations for consistency:",
        ]
        for src, tgt in sorted(self.terms.items()):
            lines.append(f"- {src} → {tgt}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "term_count": len(self.terms),
            "terms": self.terms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TranslationGlossary":
        g = cls(
            project_id=data.get("project_id", ""),
            source_language=data.get("source_language", "en-US"),
            target_language=data.get("target_language", ""),
        )
        g.terms = data.get("terms", {})
        return g

    def extract_from_text_pair(
        self, source_text: str, translated_text: str
    ) -> int:
        """Heuristic extraction: find capitalized proper nouns in source
        and attempt to match them in translated text.
        Returns number of new terms added.
        """
        # Extract capitalized multi-word names and single capitalized words
        proper_nouns = set(re.findall(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*", source_text))
        # Filter out common words
        common = {"The", "A", "An", "It", "He", "She", "They", "We", "I", "You",
                  "This", "That", "There", "Here", "When", "Where", "What", "How",
                  "Not", "But", "And", "Or", "For", "With", "From", "Into", "Over"}
        proper_nouns -= common

        new_terms = 0
        for noun in proper_nouns:
            if noun in self.terms:
                continue
            if len(noun) < 3:
                continue
            # For Japanese/Korean/Chinese target, proper nouns are often kept
            # as-is or transliterated. Add a placeholder that the AI can override.
            self.terms[noun] = ""  # empty = needs translation
            new_terms += 1
        return new_terms


# In-memory cache per project
_glossary_cache: dict[str, TranslationGlossary] = {}


def get_glossary(project_id: str) -> TranslationGlossary | None:
    return _glossary_cache.get(project_id)


def create_glossary(
    project_id: str, source_language: str, target_language: str
) -> TranslationGlossary:
    glossary = TranslationGlossary(
        project_id=project_id,
        source_language=source_language,
        target_language=target_language,
    )
    _glossary_cache[project_id] = glossary
    return glossary
