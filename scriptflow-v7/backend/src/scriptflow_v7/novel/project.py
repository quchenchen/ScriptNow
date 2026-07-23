from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from scriptflow_v7.platform.database import Base
from scriptflow_v7.platform.models import ProjectModel, new_id


class NovelPlanModel(Base):
    __tablename__ = "novel_plans"
    __table_args__ = (UniqueConstraint("project_id", name="uq_novel_plan_project"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    direction: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="seeded")


class NovelStoryMapModel(Base):
    __tablename__ = "novel_story_maps"
    __table_args__ = (UniqueConstraint("project_id", name="uq_novel_story_map_project"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    volumes: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)


async def initialize_novel_project(session: AsyncSession, project: ProjectModel) -> None:
    session.add(NovelPlanModel(project_id=project.id, direction=dict(project.direction)))
    session.add(NovelStoryMapModel(project_id=project.id, volumes=[]))
