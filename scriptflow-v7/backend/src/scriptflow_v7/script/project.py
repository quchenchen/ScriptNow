from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from scriptflow_v7.platform.database import Base
from scriptflow_v7.platform.models import ProjectModel, new_id


class ScriptPlanModel(Base):
    __tablename__ = "script_plans"
    __table_args__ = (UniqueConstraint("project_id", name="uq_script_plan_project"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    direction: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="seeded")


class ScriptStoryMapModel(Base):
    __tablename__ = "script_story_maps"
    __table_args__ = (UniqueConstraint("project_id", name="uq_script_story_map_project"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    episodes: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)


async def initialize_script_project(session: AsyncSession, project: ProjectModel) -> None:
    session.add(ScriptPlanModel(project_id=project.id, direction=dict(project.direction)))
    session.add(ScriptStoryMapModel(project_id=project.id, episodes=[]))
