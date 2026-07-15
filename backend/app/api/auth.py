"""Auth API — register / login endpoints.

Token semantics:
- ``exp`` is an int Unix timestamp (verified natively by PyJWT).
- Secret comes from ``JWT_SECRET`` env; app refuses to boot without it.
- Tokens carry ``uid`` (user id) and ``role`` (membership tier).
"""
from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import DB_PATH
from app.security import create_access_token, hash_password, verify_password

router = APIRouter()


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user_id: int
    nickname: str
    membership_tier: str
    points: int
    is_new: bool


async def _find_user(username: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM users WHERE phone = ? OR nickname = ?", (username, username)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


@router.post("/register", response_model=LoginResponse)
async def register(req: RegisterRequest):
    if len(req.username) < 2 or len(req.password) < 4:
        raise HTTPException(400, "用户名至少2位，密码至少4位")
    if await _find_user(req.username):
        raise HTTPException(400, "用户名已存在")

    pwd_hash, salt = hash_password(req.password)
    phone = req.username if req.username.isdigit() and len(req.username) == 11 else f"u_{req.username}"

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO users (phone, nickname, password_hash, membership_tier, points) "
            "VALUES (?,?,?,?,?)",
            (phone, req.username, f"{salt}:{pwd_hash}", "expert", 100),
        )
        await db.commit()
        uid = cur.lastrowid

    token = create_access_token(user_id=uid, role="expert")
    return LoginResponse(
        token=token,
        user_id=uid,
        nickname=req.username,
        membership_tier="expert",
        points=100,
        is_new=True,
    )


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    user = await _find_user(req.username)
    if not user:
        raise HTTPException(401, "用户名或密码错误")

    pwd_data = (user.get("password_hash") or "").split(":", 1)
    if len(pwd_data) != 2:
        raise HTTPException(401, "用户名或密码错误")
    salt, stored_hash = pwd_data
    if not verify_password(req.password, stored_hash, salt):
        raise HTTPException(401, "用户名或密码错误")

    token = create_access_token(user_id=user["id"], role=user["membership_tier"])
    return LoginResponse(
        token=token,
        user_id=user["id"],
        nickname=user["nickname"] or f"用户{user['phone'][-4:]}",
        membership_tier=user["membership_tier"],
        points=user["points"],
        is_new=False,
    )
