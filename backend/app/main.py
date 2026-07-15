"""ScriptFlow Backend — FastAPI Application"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import aiosqlite
from pathlib import Path

from app.core.config import settings

DB_PATH = str(Path(__file__).parent / "data" / "scriptflow.db")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT UNIQUE NOT NULL,
                nickname TEXT DEFAULT '',
                password_hash TEXT DEFAULT '',
                membership_tier TEXT DEFAULT 'free',
                membership_expires TEXT,
                points INTEGER DEFAULT 100,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                type TEXT DEFAULT 'script',
                genre TEXT DEFAULT '[]',
                target_audience TEXT DEFAULT '',
                cultural_background TEXT DEFAULT '国内',
                status TEXT DEFAULT 'draft',
                current_stage TEXT DEFAULT 'ideation',
                total_episodes INTEGER DEFAULT 80,
                style_preference TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS script_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                stage TEXT NOT NULL,
                version INTEGER DEFAULT 1,
                content TEXT DEFAULT '{}',
                agent_name TEXT DEFAULT '',
                review_score REAL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                version_id INTEGER,
                episode_number INTEGER NOT NULL,
                title TEXT DEFAULT '',
                scenes TEXT DEFAULT '[]',
                word_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                review_score REAL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                episode_id INTEGER,
                overall_score REAL DEFAULT 0,
                dimensions TEXT DEFAULT '{}',
                issues TEXT DEFAULT '[]',
                retry_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );
            CREATE TABLE IF NOT EXISTS characters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                role TEXT DEFAULT 'supporting',
                traits TEXT DEFAULT '',
                arc TEXT DEFAULT '',
                age TEXT DEFAULT '',
                gender TEXT DEFAULT '',
                personality TEXT DEFAULT '',
                background TEXT DEFAULT '',
                appearance TEXT DEFAULT '',
                current_state TEXT DEFAULT '',
                state_episode INTEGER DEFAULT 0,
                is_organization INTEGER DEFAULT 0,
                org_type TEXT DEFAULT '',
                org_purpose TEXT DEFAULT '',
                org_members TEXT DEFAULT '',
                career_id INTEGER,
                career_stage INTEGER DEFAULT 1,
                status TEXT DEFAULT 'active',
                status_episode INTEGER DEFAULT 0,
                first_appearance INTEGER DEFAULT 0,
                last_appearance INTEGER DEFAULT 0,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );
            CREATE TABLE IF NOT EXISTS foreshadows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                hint_text TEXT DEFAULT '',
                resolution_text TEXT DEFAULT '',
                category TEXT DEFAULT 'mystery',
                status TEXT DEFAULT 'pending',
                importance REAL DEFAULT 0.5,
                strength INTEGER DEFAULT 5,
                subtlety INTEGER DEFAULT 5,
                urgency INTEGER DEFAULT 0,
                is_long_term INTEGER DEFAULT 0,
                plant_episode INTEGER,
                target_episode INTEGER,
                actual_episode INTEGER,
                remind_before INTEGER DEFAULT 5,
                auto_remind INTEGER DEFAULT 1,
                include_context INTEGER DEFAULT 1,
                related_characters TEXT DEFAULT '[]',
                related_foreshadow_ids TEXT DEFAULT '[]',
                tags TEXT DEFAULT '[]',
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );
            CREATE TABLE IF NOT EXISTS scene_assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                asset_type TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                first_used INTEGER DEFAULT 0,
                usage_count INTEGER DEFAULT 1,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                agent_name TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );
        """)
        await db.commit()

        # Seed admin user
        import hashlib, secrets
        salt = secrets.token_hex(16)
        pwd = hashlib.sha256(f"{salt}:admin123".encode()).hexdigest()
        await db.execute(
            "INSERT OR IGNORE INTO users (phone, nickname, password_hash, membership_tier, points) VALUES (?,?,?,?,?)",
            ("admin", "admin", f"{salt}:{pwd}", "expert", 9999))
        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    await init_db()
    yield


app = FastAPI(title="ScriptFlow", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "ScriptFlow"}


# Register routers
from app.api import auth, projects, workspace, llm_config, memory_api
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(workspace.router, prefix="/api/workspace", tags=["workspace"])
app.include_router(llm_config.router, prefix="/api/llm", tags=["llm"])
app.include_router(memory_api.router, prefix="/api/memory", tags=["memory"])
