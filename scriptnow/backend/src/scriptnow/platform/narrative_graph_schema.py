from __future__ import annotations

import re
from enum import StrEnum


class NarrativeNodeType(StrEnum):
    CHARACTER = "character"
    EVENT = "event"
    ORGANIZATION = "organization"
    LOCATION = "location"
    OBJECT = "object"
    CONCEPT = "concept"
    RELATIONSHIP = "relationship"
    STORY_THREAD = "story_thread"


class NarrativeRelationType(StrEnum):
    CAUSAL = "causal"
    EMOTIONAL = "emotional"
    CONFLICT = "conflict"
    FORESHADOWING = "foreshadowing"
    CONSTRAINT = "constraint"
    AFFILIATION = "affiliation"


NODE_TYPE_VALUES = tuple(item.value for item in NarrativeNodeType)
RELATION_TYPE_VALUES = tuple(item.value for item in NarrativeRelationType)

_NODE_ALIASES = {
    "character": NarrativeNodeType.CHARACTER,
    "person": NarrativeNodeType.CHARACTER,
    "event": NarrativeNodeType.EVENT,
    "plot_event": NarrativeNodeType.EVENT,
    "faction": NarrativeNodeType.ORGANIZATION,
    "organization": NarrativeNodeType.ORGANIZATION,
    "organisation": NarrativeNodeType.ORGANIZATION,
    "group": NarrativeNodeType.ORGANIZATION,
    "location": NarrativeNodeType.LOCATION,
    "place": NarrativeNodeType.LOCATION,
    "object": NarrativeNodeType.OBJECT,
    "artifact": NarrativeNodeType.OBJECT,
    "prop": NarrativeNodeType.OBJECT,
    "concept": NarrativeNodeType.CONCEPT,
    "motif": NarrativeNodeType.CONCEPT,
    "theme": NarrativeNodeType.CONCEPT,
    "world_rule": NarrativeNodeType.CONCEPT,
    "world-rule": NarrativeNodeType.CONCEPT,
    "worldrule": NarrativeNodeType.CONCEPT,
    "rule": NarrativeNodeType.CONCEPT,
    "relationship": NarrativeNodeType.RELATIONSHIP,
    "relation": NarrativeNodeType.RELATIONSHIP,
    "story_thread": NarrativeNodeType.STORY_THREAD,
    "story-thread": NarrativeNodeType.STORY_THREAD,
    "foreshadow": NarrativeNodeType.STORY_THREAD,
    "setup": NarrativeNodeType.STORY_THREAD,
    "promise": NarrativeNodeType.STORY_THREAD,
    "mystery": NarrativeNodeType.STORY_THREAD,
}

_RELATION_PATTERNS = (
    (
        NarrativeRelationType.CONFLICT,
        re.compile(r"conflict|oppose|threat|reject|attack|kill|betray|rival", re.I),
    ),
    (
        NarrativeRelationType.CAUSAL,
        re.compile(
            r"cause|lead|trigger|result|change|reveal|discover|find|learn|enable|prevent|progress",
            re.I,
        ),
    ),
    (
        NarrativeRelationType.EMOTIONAL,
        re.compile(r"bond|love|trust|protect|family|kin|emotion", re.I),
    ),
    (
        NarrativeRelationType.FORESHADOWING,
        re.compile(r"foreshadow|setup|payoff|promise|echo|motif", re.I),
    ),
    (
        NarrativeRelationType.CONSTRAINT,
        re.compile(r"rule|govern|constrain|require|forbid|permit|limit", re.I),
    ),
    (
        NarrativeRelationType.AFFILIATION,
        re.compile(r"member|belong|locat|contain|part.?of|affiliat|participat|ally", re.I),
    ),
)


def canonical_node_type(value: str) -> NarrativeNodeType:
    normalized = value.strip().casefold().replace(" ", "_")
    try:
        return _NODE_ALIASES[normalized]
    except KeyError as error:
        raise ValueError(f"unsupported narrative node type: {value}") from error


def canonical_relation_type(value: str) -> NarrativeRelationType:
    normalized = value.strip().casefold().replace(" ", "_")
    try:
        return NarrativeRelationType(normalized)
    except ValueError:
        for relation_type, pattern in _RELATION_PATTERNS:
            if pattern.search(normalized):
                return relation_type
    raise ValueError(f"unsupported narrative relation type: {value}")


def compatible_node_type(value: object) -> NarrativeNodeType:
    """Read legacy/corrupt rows without making the complete graph unavailable."""
    if isinstance(value, str):
        try:
            return canonical_node_type(value)
        except ValueError:
            pass
    return NarrativeNodeType.CONCEPT


def compatible_relation_type(value: object) -> NarrativeRelationType:
    """Collapse unknown historical relationships into the generic affiliation edge."""
    if isinstance(value, str):
        try:
            return canonical_relation_type(value)
        except ValueError:
            pass
    return NarrativeRelationType.AFFILIATION
