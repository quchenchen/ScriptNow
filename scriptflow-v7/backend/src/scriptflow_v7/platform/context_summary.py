from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ContextSummary:
    creative_decisions: tuple[str, ...]
    user_preferences: tuple[str, ...]
    forbidden_terms: tuple[str, ...]
    narrative_summary: str

    @classmethod
    def validate(cls, value: dict[str, object]) -> "ContextSummary":
        required = ("creative_decisions", "user_preferences", "forbidden_terms")
        if any(key not in value or not isinstance(value[key], list) for key in required):
            raise ValueError(
                "compressed context must preserve decisions, preferences, and forbidden terms"
            )
        return cls(
            creative_decisions=tuple(str(item) for item in value["creative_decisions"]),  # type: ignore[union-attr]
            user_preferences=tuple(str(item) for item in value["user_preferences"]),  # type: ignore[union-attr]
            forbidden_terms=tuple(str(item) for item in value["forbidden_terms"]),  # type: ignore[union-attr]
            narrative_summary=str(value.get("narrative_summary", "")),
        )
