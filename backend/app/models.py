"""SQLAlchemy ORM models — single source of truth for DB schema."""
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, JSON, create_engine
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
import os
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "scriptflow.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    phone = Column(String(20), unique=True, nullable=False)
    nickname = Column(String(50), default="")
    password_hash = Column(String(200), default="")
    membership_tier = Column(String(20), default="free")
    membership_expires = Column(DateTime(timezone=True), nullable=True)
    points = Column(Integer, default=100)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(200), nullable=False)
    type = Column(String(20), default="script")
    genre = Column(Text, default="[]")
    target_audience = Column(String(50), default="")
    cultural_background = Column(String(50), default="国内")
    status = Column(String(20), default="draft")
    current_stage = Column(String(20), default="ideation")
    total_episodes = Column(Integer, default=80)
    style_preference = Column(String(100), default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Episode(Base):
    __tablename__ = "episodes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    episode_number = Column(Integer, nullable=False)
    title = Column(String(200), default="")
    scenes = Column(Text, default="[]")
    content = Column(Text, default="")
    word_count = Column(Integer, default=0)
    status = Column(String(20), default="pending")
    review_score = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Character(Base):
    __tablename__ = "characters"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    role = Column(String(20), default="supporting")
    traits = Column(Text, default="")
    arc = Column(Text, default="")
    age = Column(String(20), default="")
    gender = Column(String(20), default="")
    personality = Column(Text, default="")
    background = Column(Text, default="")
    appearance = Column(Text, default="")
    current_state = Column(Text, default="")
    state_episode = Column(Integer, default=0)
    is_organization = Column(Integer, default=0)
    org_type = Column(String(100), default="")
    org_purpose = Column(String(500), default="")
    org_members = Column(Text, default="")
    career_id = Column(Integer, nullable=True)
    career_stage = Column(Integer, default=1)
    status = Column(String(20), default="active")
    status_episode = Column(Integer, default=0)
    first_appearance = Column(Integer, default=0)
    last_appearance = Column(Integer, default=0)


class Foreshadow(Base):
    __tablename__ = "foreshadows"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    hint_text = Column(Text, default="")
    resolution_text = Column(Text, default="")
    category = Column(String(20), default="mystery")
    status = Column(String(20), default="pending")
    importance = Column(Float, default=0.5)
    strength = Column(Integer, default=5)
    subtlety = Column(Integer, default=5)
    urgency = Column(Integer, default=0)
    is_long_term = Column(Integer, default=0)
    plant_episode = Column(Integer, nullable=True)
    target_episode = Column(Integer, nullable=True)
    actual_episode = Column(Integer, nullable=True)
    remind_before = Column(Integer, default=5)
    auto_remind = Column(Integer, default=1)
    include_context = Column(Integer, default=1)
    related_characters = Column(Text, default="[]")
    related_foreshadow_ids = Column(Text, default="[]")
    tags = Column(Text, default="[]")


class ScriptVersion(Base):
    __tablename__ = "script_versions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    stage = Column(String(50), default="")
    content = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(10), nullable=False)
    content = Column(Text, nullable=False)
    agent_name = Column(String(50), default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SceneAsset(Base):
    __tablename__ = "scene_assets"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    asset_type = Column(String(20), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    first_used = Column(Integer, default=0)
    usage_count = Column(Integer, default=1)


class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    episode_number = Column(Integer, nullable=False)
    score = Column(Integer, default=0)
    feedback = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# Create all tables
def init_db():
    engine = create_engine(DATABASE_URL.replace("+aiosqlite", ""))
    Base.metadata.create_all(engine)
    return engine
