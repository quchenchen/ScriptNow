"""FastAPI Dependencies — the seam between HTTP requests and domain logic.

Public surface:
- ``get_current_user`` — parses Bearer token, verifies, loads user from DB.
  Raises 401 on missing / invalid / expired token, 404 on unknown uid.
- ``get_owned_project`` — verifies the caller owns the project referenced by
  path param ``project_id``. Raises 404 if the project doesn't exist *or*
  isn't the caller's — same status code for both to prevent enumeration.

Adding a new authenticated endpoint::

    from fastapi import Depends
    from app.deps import CurrentUser

    @router.get("/foo")
    async def foo(user: CurrentUser):
        return {"me": user["nickname"]}

Adding a project-scoped endpoint::

    from app.deps import OwnedProject

    @router.get("/{project_id}/bar")
    async def bar(project: OwnedProject):
        return {"pid": project["id"]}
"""
from __future__ import annotations

from typing import Annotated

import aiosqlite
from fastapi import Depends, HTTPException, Path, Request

from app.db import DB_PATH
from app.security import InvalidTokenError, decode_access_token


async def _load_user_by_id(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_current_user(request: Request) -> dict:
    """FastAPI Dependency: return the current authenticated user.

    Raises 401 for any auth failure (missing header, bad scheme, invalid or
    expired token, unknown user). Does *not* differentiate reasons to the
    client — every failure looks the same to prevent user enumeration.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="未认证")

    token = auth.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="未认证") from None

    user = await _load_user_by_id(int(payload["uid"]))
    if not user:
        raise HTTPException(status_code=401, detail="未认证")

    return user


# Convenience type alias for endpoints
CurrentUser = Annotated[dict, Depends(get_current_user)]


async def get_owned_project(
    project_id: int = Path(..., description="Project ID"),
    user: dict = Depends(get_current_user),
) -> dict:
    """Verify the current user owns ``project_id`` and return the project.

    Returns 404 if the project doesn't exist OR the caller isn't the owner —
    same status code for both so callers can't tell which case they hit.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM projects WHERE id = ? AND user_id = ?", (project_id, user["id"])
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="项目不存在")
        return dict(row)


OwnedProject = Annotated[dict, Depends(get_owned_project)]
