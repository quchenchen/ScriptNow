"""Tests for auth helpers (JWT + password hashing).

Guarantees:
- Tokens carry an int Unix ``exp`` claim (not ISO string).
- Round-trip encode/decode returns the same user id.
- Expired tokens are rejected.
- Tampered tokens are rejected.
"""
from __future__ import annotations

import time

import pytest


def test_password_hash_verify_round_trip():
    from app.security import hash_password, verify_password

    hashed, salt = hash_password("hunter2")
    assert verify_password("hunter2", hashed, salt) is True
    assert verify_password("wrong", hashed, salt) is False


def test_access_token_exp_is_int_unix_seconds(monkeypatch):
    """The ``exp`` claim is an int Unix timestamp — required by PyJWT verify."""
    from app.security import create_access_token, decode_access_token

    token = create_access_token(user_id=42, role="expert", expires_in_seconds=3600)
    payload = decode_access_token(token)

    assert payload["uid"] == 42
    assert payload["role"] == "expert"
    assert isinstance(payload["exp"], int)
    # exp should be roughly (now + 3600) — allow 5s tolerance
    assert abs(payload["exp"] - (int(time.time()) + 3600)) < 5


def test_expired_token_is_rejected():
    from app.security import InvalidTokenError, create_access_token, decode_access_token

    # Issue a token that has already expired
    token = create_access_token(user_id=1, role="free", expires_in_seconds=-10)

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_tampered_token_is_rejected():
    from app.security import InvalidTokenError, create_access_token, decode_access_token

    token = create_access_token(user_id=1, role="free", expires_in_seconds=60)
    # Tamper: change the last char
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

    with pytest.raises(InvalidTokenError):
        decode_access_token(tampered)
