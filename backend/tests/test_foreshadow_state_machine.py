"""Tests for the foreshadow state machine (pure functions).

Coverage:
- All legal transitions succeed
- Every illegal transition raises
- ``is_overdue`` reflects target_episode/remind_before/current_episode correctly
- ``is_terminal`` marks resolved/abandoned as terminal
"""
from __future__ import annotations

import pytest

LEGAL = [
    ("pending", "planted"),
    ("pending", "abandoned"),
    ("planted", "partially_resolved"),
    ("planted", "resolved"),
    ("planted", "abandoned"),
    ("partially_resolved", "resolved"),
    ("partially_resolved", "abandoned"),
]

ILLEGAL = [
    ("pending", "resolved"),
    ("pending", "partially_resolved"),
    ("pending", "pending"),
    ("planted", "pending"),
    ("resolved", "planted"),
    ("resolved", "abandoned"),
    ("abandoned", "planted"),
    ("abandoned", "resolved"),
    ("planted", "not-a-state"),
]


@pytest.mark.parametrize("cur, tgt", LEGAL)
def test_legal_transitions_pass(cur, tgt):
    from app.services.foreshadow_state import can_transition, transition

    assert can_transition(cur, tgt) is True
    assert transition(cur, tgt).value == tgt


@pytest.mark.parametrize("cur, tgt", ILLEGAL)
def test_illegal_transitions_raise(cur, tgt):
    from app.services.foreshadow_state import (
        InvalidStateTransition,
        can_transition,
        transition,
    )

    assert can_transition(cur, tgt) is False
    with pytest.raises(InvalidStateTransition):
        transition(cur, tgt)


def test_is_terminal():
    from app.services.foreshadow_state import is_terminal

    assert is_terminal("resolved") is True
    assert is_terminal("abandoned") is True
    assert is_terminal("planted") is False
    assert is_terminal("pending") is False
    assert is_terminal("garbage") is False


def test_is_overdue_when_target_is_close():
    from app.services.foreshadow_state import is_overdue

    # target_ep 10, current 6, remind_before 5 → overdue (10-6=4, ≤5)
    assert is_overdue("planted", target_episode=10, current_episode=6) is True


def test_is_overdue_false_when_target_far_away():
    from app.services.foreshadow_state import is_overdue

    assert is_overdue("planted", target_episode=20, current_episode=6) is False


def test_is_overdue_false_when_resolved():
    from app.services.foreshadow_state import is_overdue

    # Terminal states are never overdue
    assert is_overdue("resolved", target_episode=5, current_episode=10) is False
    assert is_overdue("abandoned", target_episode=5, current_episode=10) is False


def test_is_overdue_false_without_target():
    from app.services.foreshadow_state import is_overdue

    assert is_overdue("planted", target_episode=None, current_episode=10) is False
