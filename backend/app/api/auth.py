"""Auth API — JWT + Password"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime, timedelta
import hashlib, secrets, aiosqlite, jwt, os
from app.main import DB_PATH

router = APIRouter()
JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(32))


def hash_password(password: str, salt: str = "") -> tuple[str, str]:
    if not salt: salt = secrets.token_hex(16)
    h = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return h, salt


class RegisterRequest(BaseModel): username: str; password: str
class LoginRequest(BaseModel): username: str; password: str
class LoginResponse(BaseModel): token: str; user_id: int; nickname: str; membership_tier: str; points: int; is_new: bool


async def _find_user(username: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE phone = ? OR nickname = ?", (username, username))
        row = await cur.fetchone()
        return dict(row) if row else None


@router.post("/register", response_model=LoginResponse)
async def register(req: RegisterRequest):
    if len(req.username) < 2 or len(req.password) < 4: raise HTTPException(400, "用户名至少2位，密码至少4位")
    if await _find_user(req.username): raise HTTPException(400, "用户名已存在")
    pwd_hash, salt = hash_password(req.password)
    phone = req.username if req.username.isdigit() and len(req.username) == 11 else f"u_{req.username}"
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO users (phone, nickname, password_hash, membership_tier, points) VALUES (?,?,?,?,?)",
            (phone, req.username, f"{salt}:{pwd_hash}", "expert", 100))
        await db.commit()
        uid = cur.lastrowid
    payload = {"uid": uid, "exp": (datetime.now() + timedelta(days=7)).isoformat(), "role": "expert"}
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    return LoginResponse(token=token, user_id=uid, nickname=req.username, membership_tier="expert", points=100, is_new=True)


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    user = await _find_user(req.username)
    if not user: raise HTTPException(401, "用户名或密码错误")
    pwd_data = (user.get("password_hash") or "").split(":", 1)
    if len(pwd_data) == 2:
        salt, stored_hash = pwd_data
        computed_hash, _ = hash_password(req.password, salt)
        if stored_hash != computed_hash: raise HTTPException(401, "用户名或密码错误")
    payload = {"uid": user["id"], "exp": (datetime.now() + timedelta(days=7)).isoformat(), "role": user["membership_tier"]}
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    return LoginResponse(token=token, user_id=user["id"], nickname=user["nickname"] or f"用户{user['phone'][-4:]}",
                         membership_tier=user["membership_tier"], points=user["points"], is_new=False)
