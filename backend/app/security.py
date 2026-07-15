"""Security helpers — password hashing and JWT tokens.

Public surface (the one tests and callers should use):
- ``hash_password(password) -> (hash, salt)``
- ``verify_password(password, expected_hash, salt) -> bool``
- ``create_access_token(user_id, role, expires_in_seconds=None) -> str``
- ``decode_access_token(token) -> payload``
- ``InvalidTokenError`` — raised by decode_access_token on any failure
  (expired, tampered, malformed, missing claims).

Design notes:
- ``exp`` is stored as **int Unix seconds** — PyJWT verifies this natively.
  The previous code stored ``exp`` as an ISO datetime string; PyJWT rejected
  it silently in some paths and worked by accident in others.
- ``JWT_SECRET`` is resolved via ``app.config.get_settings()``, so tests can
  inject a stable secret via env.
"""
from __future__ import annotations

import hashlib
import secrets
import time

import jwt

from app.config import get_settings


class InvalidTokenError(Exception):
    """Raised when a token is missing, tampered, expired, or malformed."""


def hash_password(password: str, salt: str = "") -> tuple[str, str]:
    """Hash a password with a per-user salt. Returns (hash, salt)."""
    if not salt:
        salt = secrets.token_hex(16)
    h = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return h, salt


def verify_password(password: str, expected_hash: str, salt: str) -> bool:
    """Constant-time-ish comparison of a password against a stored (hash, salt)."""
    computed, _ = hash_password(password, salt)
    return secrets.compare_digest(computed, expected_hash)


def create_access_token(user_id: int, role: str, expires_in_seconds: int | None = None) -> str:
    """Issue a signed access token carrying user id + role."""
    settings = get_settings()
    if expires_in_seconds is None:
        expires_in_seconds = settings.JWT_EXPIRE_SECONDS

    now = int(time.time())
    payload: dict = {
        "uid": user_id,
        "role": role,
        "iat": now,
        "exp": now + int(expires_in_seconds),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode + verify (signature, exp). Raise ``InvalidTokenError`` on any issue."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as e:
        raise InvalidTokenError("token expired") from e
    except jwt.InvalidTokenError as e:
        raise InvalidTokenError(f"invalid token: {e}") from e

    if "uid" not in payload:
        raise InvalidTokenError("token missing uid claim")

    return payload
