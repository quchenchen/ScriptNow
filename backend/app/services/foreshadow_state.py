"""Foreshadow state machine.

States (see PRD-V5 §User Stories #14-#17):

    pending ──plant──▶ planted ──partial──▶ partially_resolved ──resolve──▶ resolved
                          │                       │
                          └──resolve──▶ resolved  ├──abandon──▶ abandoned
                          │                       │
                          └──abandon──▶ abandoned └──abandon──▶ abandoned

- ``pending`` — recorded by the writer but not yet placed in an episode
- ``planted`` — the hint has been placed; awaiting payoff
- ``partially_resolved`` — foreshadow_1 of N revealed (for compound foreshadows)
- ``resolved`` — fully paid off
- ``abandoned`` — explicitly dropped (writer changed mind)

Callers use :func:`can_transition` to check legality and :func:`transition`
to perform the change with validation. Illegal transitions raise
``InvalidStateTransition``.
"""
from __future__ import annotations

from enum import Enum


class ForeshadowState(str, Enum):
    PENDING = "pending"
    PLANTED = "planted"
    PARTIALLY_RESOLVED = "partially_resolved"
    RESOLVED = "resolved"
    ABANDONED = "abandoned"


# Directed adjacency of legal transitions.
_ALLOWED: dict[ForeshadowState, set[ForeshadowState]] = {
    ForeshadowState.PENDING: {ForeshadowState.PLANTED, ForeshadowState.ABANDONED},
    ForeshadowState.PLANTED: {
        ForeshadowState.PARTIALLY_RESOLVED,
        ForeshadowState.RESOLVED,
        ForeshadowState.ABANDONED,
    },
    ForeshadowState.PARTIALLY_RESOLVED: {
        ForeshadowState.RESOLVED,
        ForeshadowState.ABANDONED,
    },
    ForeshadowState.RESOLVED: set(),  # terminal
    ForeshadowState.ABANDONED: set(),  # terminal
}


class InvalidStateTransition(ValueError):
    """Raised when a caller attempts an illegal state transition."""


def can_transition(current: str, target: str) -> bool:
    """Return True if the transition ``current → target`` is legal."""
    try:
        cur = ForeshadowState(current)
        tgt = ForeshadowState(target)
    except ValueError:
        return False
    return tgt in _ALLOWED[cur]


def transition(current: str, target: str) -> ForeshadowState:
    """Validate + return the target state as a ForeshadowState enum.

    Raises :class:`InvalidStateTransition` when illegal.
    """
    if not can_transition(current, target):
        raise InvalidStateTransition(
            f"illegal foreshadow transition: {current} → {target}"
        )
    return ForeshadowState(target)


def is_terminal(state: str) -> bool:
    """Whether the state has no legal outbound transitions."""
    try:
        return not _ALLOWED[ForeshadowState(state)]
    except ValueError:
        return False


def is_overdue(state: str, target_episode: int | None, current_episode: int, remind_before: int = 5) -> bool:
    """Compute whether a planted foreshadow is running out of time to pay off.

    ``target_episode - current_episode <= remind_before`` and still not resolved.
    """
    if state not in (ForeshadowState.PENDING.value, ForeshadowState.PLANTED.value,
                     ForeshadowState.PARTIALLY_RESOLVED.value):
        return False
    if not target_episode:
        return False
    return (target_episode - current_episode) <= remind_before
