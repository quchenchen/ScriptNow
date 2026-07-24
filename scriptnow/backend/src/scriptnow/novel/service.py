from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import func, select

from scriptnow.novel.continuity import latest_effective_revisions
from scriptnow.novel.contracts import NovelBlock
from scriptnow.novel.domain import (
    NovelBlueprintAnchorModel,
    NovelBlueprintCandidateModel,
    NovelBlueprintDraft,
    NovelBlueprintModel,
    NovelCandidateStatus,
    NovelDocumentRevisionModel,
    NovelRevisionStatus,
    NovelStoryCoreCandidateModel,
    NovelStoryCoreDraft,
    NovelStructureCandidateModel,
)
from scriptnow.novel.project import NovelPlanModel, NovelStoryMapModel
from scriptnow.novel.story_map import Volume
from scriptnow.platform.database import Database
from scriptnow.platform.models import ProjectEventModel, ProjectMedium, ProjectModel
from scriptnow.platform.run_events import RunEventType


class NovelDomainError(RuntimeError):
    pass


class NovelConflict(NovelDomainError):
    pass


@dataclass(frozen=True, slots=True)
class NovelStructureImpact:
    added_units: int
    removed_units: int
    retained_units: int


class NovelService:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def generate_story_cores(
        self,
        *,
        tenant_id: str,
        project_id: str,
        drafts: tuple[NovelStoryCoreDraft, ...],
        idempotency_key: str | None = None,
        revision_feedback: str | None = None,
    ) -> list[NovelStoryCoreCandidateModel]:
        if len(drafts) != 3:
            raise NovelDomainError("exactly three Novel StoryCore candidates are required")
        async with self.database.session() as session:
            await self._project(session, tenant_id, project_id)
            adopted = (
                await session.scalars(
                    select(NovelStoryCoreCandidateModel).where(
                        NovelStoryCoreCandidateModel.project_id == project_id,
                        NovelStoryCoreCandidateModel.status == NovelCandidateStatus.ADOPTED,
                    )
                )
            ).first()
            if adopted:
                raise NovelConflict("adopted Novel StoryCore locks the divergence phase")
            request_key = idempotency_key or str(uuid4())
            existing = list(
                await session.scalars(
                    select(NovelStoryCoreCandidateModel)
                    .where(
                        NovelStoryCoreCandidateModel.project_id == project_id,
                        NovelStoryCoreCandidateModel.idempotency_key == request_key,
                    )
                    .order_by(NovelStoryCoreCandidateModel.ordinal)
                )
            )
            if existing:
                return existing
            active = list(
                await session.scalars(
                    select(NovelStoryCoreCandidateModel).where(
                        NovelStoryCoreCandidateModel.project_id == project_id,
                        NovelStoryCoreCandidateModel.status == NovelCandidateStatus.ACTIVE,
                    )
                )
            )
            for item in active:
                item.status = NovelCandidateStatus.EXPIRED
                item.revision_feedback = revision_feedback
            generation = (
                int(
                    await session.scalar(
                        select(
                            func.coalesce(func.max(NovelStoryCoreCandidateModel.generation), 0)
                        ).where(NovelStoryCoreCandidateModel.project_id == project_id)
                    )
                    or 0
                )
                + 1
            )
            records = [
                NovelStoryCoreCandidateModel(
                    project_id=project_id,
                    generation=generation,
                    ordinal=index,
                    idempotency_key=request_key,
                    title=draft.title,
                    premise=draft.premise,
                    point_of_view=draft.point_of_view,
                    narrative_constraints=list(draft.narrative_constraints),
                    angles=list(draft.angles),
                )
                for index, draft in enumerate(drafts, 1)
            ]
            session.add_all(records)
            await session.flush()
            await self._event(
                session,
                project_id,
                f"novel:story-core:propose:{request_key}",
                {
                    "action": "novel_story_core.propose",
                    "title": "灵感导演带来了三个创意方向",
                    "content": "可以比较每个方向的核心设想、叙述视角与长期变化，再决定让哪一条继续生长。",
                    "generation": generation,
                    "feedback": revision_feedback,
                    "candidates": [
                        {
                            "id": item.id,
                            "ordinal": item.ordinal,
                            "title": item.title,
                            "summary": item.premise,
                            "point_of_view": item.point_of_view,
                            "angles": list(item.angles),
                        }
                        for item in records
                    ],
                },
                type=RunEventType.CONVERSATION,
                actor={"type": "agent", "role": "director"},
            )
            return records

    async def adopt_story_core(
        self, *, tenant_id: str, project_id: str, candidate_id: str
    ) -> NovelStoryCoreCandidateModel:
        async with self.database.session() as session:
            await self._project(session, tenant_id, project_id)
            candidate = await session.get(NovelStoryCoreCandidateModel, candidate_id)
            if (
                candidate is None
                or candidate.project_id != project_id
                or candidate.status != NovelCandidateStatus.ACTIVE
            ):
                raise NovelConflict("Novel StoryCore candidate is unavailable")
            siblings = list(
                await session.scalars(
                    select(NovelStoryCoreCandidateModel).where(
                        NovelStoryCoreCandidateModel.project_id == project_id,
                        NovelStoryCoreCandidateModel.generation == candidate.generation,
                    )
                )
            )
            for item in siblings:
                item.status = (
                    NovelCandidateStatus.ADOPTED
                    if item.id == candidate.id
                    else NovelCandidateStatus.EXPIRED
                )
            plan = await self._plan(session, project_id)
            plan.status = "story_core_adopted"
            await self._event(
                session,
                project_id,
                f"novel:story-core:adopt:{candidate.id}",
                {
                    "action": "novel_story_core.adopt",
                    "title": "你选择了小说创意方向",
                    "content": "这条方向现在成为后续蓝图、StoryMap 与写作搭档共同遵循的创作核心。",
                    "candidate_id": candidate.id,
                    "candidate": {
                        "id": candidate.id,
                        "ordinal": candidate.ordinal,
                        "title": candidate.title,
                        "summary": candidate.premise,
                        "point_of_view": candidate.point_of_view,
                        "angles": list(candidate.angles),
                    },
                },
                actor={"type": "user"},
            )
            return candidate

    async def propose_blueprint(
        self,
        *,
        tenant_id: str,
        project_id: str,
        draft: NovelBlueprintDraft,
        idempotency_key: str,
    ) -> NovelBlueprintCandidateModel:
        if len({item.id for item in draft.anchors}) != len(draft.anchors):
            raise NovelDomainError("Novel blueprint anchor IDs must be unique")
        async with self.database.session() as session:
            await self._project(session, tenant_id, project_id)
            existing = (
                await session.scalars(
                    select(NovelBlueprintCandidateModel).where(
                        NovelBlueprintCandidateModel.project_id == project_id,
                        NovelBlueprintCandidateModel.idempotency_key == idempotency_key,
                    )
                )
            ).one_or_none()
            if existing:
                return existing
            core = (
                await session.scalars(
                    select(NovelStoryCoreCandidateModel).where(
                        NovelStoryCoreCandidateModel.project_id == project_id,
                        NovelStoryCoreCandidateModel.status == NovelCandidateStatus.ADOPTED,
                    )
                )
            ).one_or_none()
            if core is None:
                raise NovelConflict("adopt Novel StoryCore before blueprint")
            candidate = NovelBlueprintCandidateModel(
                project_id=project_id,
                story_core_candidate_id=core.id,
                draft=draft.model_dump(mode="json"),
                idempotency_key=idempotency_key,
            )
            session.add(candidate)
            await session.flush()
            await self._event(
                session,
                project_id,
                f"novel:blueprint:propose:{candidate.id}",
                {
                    "action": "novel_blueprint.propose",
                    "candidate_id": candidate.id,
                    "anchor_count": len(draft.anchors),
                },
                type=RunEventType.NODE,
            )
            return candidate

    async def adopt_blueprint(
        self, *, tenant_id: str, project_id: str, candidate_id: str
    ) -> NovelBlueprintModel:
        async with self.database.session() as session:
            await self._project(session, tenant_id, project_id)
            candidate = await session.get(NovelBlueprintCandidateModel, candidate_id)
            if (
                candidate is None
                or candidate.project_id != project_id
                or candidate.status != NovelCandidateStatus.ACTIVE
            ):
                raise NovelConflict("Novel blueprint candidate is unavailable")
            previous = (
                await session.scalars(
                    select(NovelBlueprintModel).where(
                        NovelBlueprintModel.project_id == project_id,
                        NovelBlueprintModel.adopted.is_(True),
                    )
                )
            ).one_or_none()
            if previous:
                previous.adopted = False
            blueprint = NovelBlueprintModel(
                project_id=project_id,
                version=previous.version + 1 if previous else 1,
                story_core_candidate_id=candidate.story_core_candidate_id,
            )
            session.add(blueprint)
            await session.flush()
            draft = NovelBlueprintDraft.model_validate(candidate.draft)
            session.add_all(
                [
                    NovelBlueprintAnchorModel(
                        blueprint_id=blueprint.id,
                        anchor_key=item.id,
                        kind=item.kind,
                        name=item.name,
                        payload=item.payload,
                    )
                    for item in draft.anchors
                ]
            )
            candidate.status = NovelCandidateStatus.ADOPTED
            plan = await self._plan(session, project_id)
            plan.status = "blueprint_adopted"
            await self._event(
                session,
                project_id,
                f"novel:blueprint:adopt:{blueprint.id}",
                {"action": "novel_blueprint.adopt", "blueprint_id": blueprint.id},
            )
            return blueprint

    async def propose_structure(
        self,
        *,
        tenant_id: str,
        project_id: str,
        expected_version: int,
        volumes: tuple[Volume, ...],
        idempotency_key: str,
    ) -> NovelStructureCandidateModel:
        async with self.database.session() as session:
            await self._project(session, tenant_id, project_id)
            existing = (
                await session.scalars(
                    select(NovelStructureCandidateModel).where(
                        NovelStructureCandidateModel.project_id == project_id,
                        NovelStructureCandidateModel.idempotency_key == idempotency_key,
                    )
                )
            ).one_or_none()
            if existing:
                return existing
            story_map = await self._story_map(session, project_id)
            if story_map.version != expected_version:
                raise NovelConflict("Novel StoryMap version conflict")
            await self._validate_anchors(session, project_id, volumes)
            current_ids = self._unit_ids(story_map.volumes)
            proposed = [volume.model_dump(mode="json") for volume in volumes]
            proposed_ids = self._unit_ids(proposed)
            impact = NovelStructureImpact(
                len(proposed_ids - current_ids),
                len(current_ids - proposed_ids),
                len(current_ids & proposed_ids),
            )
            active_candidates = list(
                await session.scalars(
                    select(NovelStructureCandidateModel).where(
                        NovelStructureCandidateModel.project_id == project_id,
                        NovelStructureCandidateModel.status == NovelCandidateStatus.ACTIVE,
                    )
                )
            )
            for active_candidate in active_candidates:
                active_candidate.status = NovelCandidateStatus.EXPIRED
            candidate = NovelStructureCandidateModel(
                project_id=project_id,
                base_version=expected_version,
                proposed_volumes=proposed,
                impact={
                    "added_units": impact.added_units,
                    "removed_units": impact.removed_units,
                    "retained_units": impact.retained_units,
                },
                idempotency_key=idempotency_key,
            )
            session.add(candidate)
            await session.flush()
            await self._event(
                session,
                project_id,
                f"novel:story-map:propose:{candidate.id}",
                {
                    "action": "novel_story_map.propose",
                    "candidate_id": candidate.id,
                    "volume_count": len(volumes),
                    "chapter_count": sum(len(volume.chapters) for volume in volumes),
                },
                type=RunEventType.NODE,
            )
            return candidate

    async def adopt_structure(
        self, *, tenant_id: str, project_id: str, candidate_id: str
    ) -> NovelStoryMapModel:
        stale = False
        result = None
        async with self.database.session() as session:
            await self._project(session, tenant_id, project_id)
            candidate = await session.get(NovelStructureCandidateModel, candidate_id)
            if (
                candidate is None
                or candidate.project_id != project_id
                or candidate.status != NovelCandidateStatus.ACTIVE
            ):
                raise NovelConflict("Novel structure candidate is unavailable")
            story_map = await self._story_map(session, project_id)
            if story_map.version != candidate.base_version:
                candidate.status = NovelCandidateStatus.EXPIRED
                stale = True
            else:
                story_map.volumes = candidate.proposed_volumes
                story_map.version += 1
                candidate.status = NovelCandidateStatus.ADOPTED
                plan = await self._plan(session, project_id)
                plan.status = "writing"
                await self._event(
                    session,
                    project_id,
                    f"novel:story-map:adopt:{candidate.id}",
                    {
                        "action": "novel_story_map.adopt",
                        "candidate_id": candidate.id,
                        "version": story_map.version,
                        "impact": candidate.impact,
                    },
                )
                result = story_map
        if stale:
            raise NovelConflict("Novel structure candidate is stale")
        assert result is not None
        return result

    async def propose_document(
        self,
        *,
        tenant_id: str,
        project_id: str,
        chapter_id: str,
        blocks: tuple[NovelBlock, ...],
        idempotency_key: str,
        parent_revision_id: str | None = None,
        source: str = "agent",
    ) -> NovelDocumentRevisionModel:
        self._validate_blocks(blocks)
        if source not in {"agent", "human"}:
            raise NovelDomainError("Novel document revision source is invalid")
        async with self.database.session() as session:
            await self._project(session, tenant_id, project_id)
            existing = (
                await session.scalars(
                    select(NovelDocumentRevisionModel).where(
                        NovelDocumentRevisionModel.project_id == project_id,
                        NovelDocumentRevisionModel.idempotency_key == idempotency_key,
                    )
                )
            ).one_or_none()
            if existing:
                return existing
            story_map = await self._story_map(session, project_id)
            if chapter_id not in self._chapter_ids(story_map.volumes):
                raise NovelDomainError("chapter is not present in Novel StoryMap")
            parent = (
                await session.get(NovelDocumentRevisionModel, parent_revision_id)
                if parent_revision_id
                else None
            )
            if parent_revision_id and (
                parent is None or parent.project_id != project_id or parent.chapter_id != chapter_id
            ):
                raise NovelConflict("Novel parent revision is unavailable")
            adopted = (
                await session.scalars(
                    select(NovelDocumentRevisionModel).where(
                        NovelDocumentRevisionModel.project_id == project_id,
                        NovelDocumentRevisionModel.chapter_id == chapter_id,
                        NovelDocumentRevisionModel.status == NovelRevisionStatus.ADOPTED,
                    )
                )
            ).one_or_none()
            number = (
                int(
                    await session.scalar(
                        select(
                            func.coalesce(func.max(NovelDocumentRevisionModel.revision_number), 0)
                        ).where(
                            NovelDocumentRevisionModel.project_id == project_id,
                            NovelDocumentRevisionModel.chapter_id == chapter_id,
                        )
                    )
                    or 0
                )
                + 1
            )
            record = NovelDocumentRevisionModel(
                project_id=project_id,
                chapter_id=chapter_id,
                revision_number=number,
                base_revision_id=adopted.id if adopted else None,
                parent_revision_id=parent.id if parent else None,
                source=source,
                blocks=[item.model_dump(mode="json") for item in blocks],
                idempotency_key=idempotency_key,
            )
            session.add(record)
            await session.flush()
            return record

    async def adopt_document(
        self, *, tenant_id: str, project_id: str, revision_id: str
    ) -> NovelDocumentRevisionModel:
        stale = False
        result = None
        async with self.database.session() as session:
            await self._project(session, tenant_id, project_id)
            revision = await session.get(NovelDocumentRevisionModel, revision_id)
            if (
                revision is None
                or revision.project_id != project_id
                or revision.status != NovelRevisionStatus.CANDIDATE
            ):
                raise NovelConflict("Novel document candidate is unavailable")
            adopted = (
                await session.scalars(
                    select(NovelDocumentRevisionModel).where(
                        NovelDocumentRevisionModel.project_id == project_id,
                        NovelDocumentRevisionModel.chapter_id == revision.chapter_id,
                        NovelDocumentRevisionModel.status == NovelRevisionStatus.ADOPTED,
                    )
                )
            ).one_or_none()
            if revision.base_revision_id != (adopted.id if adopted else None):
                revision.status = NovelRevisionStatus.SUPERSEDED
                stale = True
            else:
                if adopted:
                    adopted.status = NovelRevisionStatus.SUPERSEDED
                    await session.flush()
                revision.status = NovelRevisionStatus.ADOPTED
                await self._event(
                    session,
                    project_id,
                    f"novel:document:adopt:{revision.id}",
                    {
                        "action": "novel_document.adopt",
                        "chapter_id": revision.chapter_id,
                        "revision_id": revision.id,
                    },
                )
                result = revision
        if stale:
            raise NovelConflict("Novel document candidate base revision is stale")
        assert result is not None
        return result

    async def context_pack(
        self, *, tenant_id: str, project_id: str, chapter_id: str
    ) -> dict[str, object]:
        async with self.database.session() as session:
            await self._project(session, tenant_id, project_id)
            blueprint = (
                await session.scalars(
                    select(NovelBlueprintModel).where(
                        NovelBlueprintModel.project_id == project_id,
                        NovelBlueprintModel.adopted.is_(True),
                    )
                )
            ).one_or_none()
            anchors = (
                list(
                    await session.scalars(
                        select(NovelBlueprintAnchorModel).where(
                            NovelBlueprintAnchorModel.blueprint_id == blueprint.id
                        )
                    )
                )
                if blueprint
                else []
            )
            documents = list(
                await session.scalars(
                    select(NovelDocumentRevisionModel).where(
                        NovelDocumentRevisionModel.project_id == project_id,
                    )
                )
            )
            story_map = (
                await session.scalars(
                    select(NovelStoryMapModel).where(NovelStoryMapModel.project_id == project_id)
                )
            ).one_or_none()
            chapter_ids = (
                [
                    str(dict(chapter).get("id"))
                    for volume in story_map.volumes
                    for chapter in list(dict(volume).get("chapters") or [])
                ]
                if story_map
                else []
            )
            effective = latest_effective_revisions(documents, chapter_ids=chapter_ids)
            return {
                "chapter_id": chapter_id,
                "anchors": [
                    {"id": item.anchor_key, "kind": item.kind, "name": item.name}
                    for item in anchors
                ],
                "adopted_chapters": [
                    {"chapter_id": item.chapter_id, "revision_id": item.id, "blocks": item.blocks}
                    for item in documents
                    if item.status == NovelRevisionStatus.ADOPTED
                ],
                "effective_chapters": [
                    {
                        "chapter_id": item.chapter_id,
                        "revision_id": item.id,
                        "revision_number": item.revision_number,
                        "source": item.source,
                        "status": item.status,
                        "blocks": item.blocks,
                    }
                    for item in effective
                ],
            }

    @staticmethod
    async def _project(session, tenant_id: str, project_id: str) -> ProjectModel:
        project = await session.get(ProjectModel, project_id)
        if (
            project is None
            or project.tenant_id != tenant_id
            or project.medium != ProjectMedium.NOVEL
        ):
            raise NovelDomainError("project is outside Novel tenant scope")
        return project

    @staticmethod
    async def _plan(session, project_id: str) -> NovelPlanModel:
        return (
            await session.scalars(
                select(NovelPlanModel).where(NovelPlanModel.project_id == project_id)
            )
        ).one()

    @staticmethod
    async def _story_map(session, project_id: str) -> NovelStoryMapModel:
        return (
            await session.scalars(
                select(NovelStoryMapModel).where(NovelStoryMapModel.project_id == project_id)
            )
        ).one()

    @staticmethod
    async def _validate_anchors(session, project_id: str, volumes: tuple[Volume, ...]) -> None:
        blueprint = (
            await session.scalars(
                select(NovelBlueprintModel).where(
                    NovelBlueprintModel.project_id == project_id,
                    NovelBlueprintModel.adopted.is_(True),
                )
            )
        ).one_or_none()
        if blueprint is None:
            raise NovelConflict("adopt Novel blueprint before StoryMap")
        valid = set(
            await session.scalars(
                select(NovelBlueprintAnchorModel.anchor_key).where(
                    NovelBlueprintAnchorModel.blueprint_id == blueprint.id
                )
            )
        )
        referenced = {
            anchor
            for volume in volumes
            for chapter in volume.chapters
            for beat in chapter.beats
            for anchor in beat.anchor_ids
        }
        if not referenced <= valid:
            raise NovelDomainError("Novel StoryMap references unknown blueprint anchors")

    @staticmethod
    def _unit_ids(volumes: list[dict[str, object]]) -> set[str]:
        ids = set()
        for volume in volumes:
            ids.add(str(volume["id"]))
            for chapter in volume.get("chapters", []):  # type: ignore[union-attr]
                ids.add(str(chapter["id"]))
                ids.update(str(beat["id"]) for beat in chapter.get("beats", []))
        return ids

    @staticmethod
    def _chapter_ids(volumes: list[dict[str, object]]) -> set[str]:
        return {
            str(chapter["id"])
            for volume in volumes
            for chapter in volume.get("chapters", [])  # type: ignore[union-attr]
        }

    @staticmethod
    def _validate_blocks(blocks: tuple[NovelBlock, ...]) -> None:
        if not blocks or blocks[0].type != "heading":
            raise NovelDomainError("Novel chapter must begin with a heading")
        if len({block.block_id for block in blocks}) != len(blocks):
            raise NovelDomainError("Novel block_id values must be unique")
        for block in blocks:
            if block.type == "divider" and block.text.strip():
                raise NovelDomainError("Novel divider block must have empty text")

    @staticmethod
    async def _event(
        session,
        project_id: str,
        event_key: str,
        payload: dict[str, object],
        *,
        type: RunEventType = RunEventType.DECISION,
        actor: dict[str, object] | None = None,
    ) -> None:
        stream_key = f"project:{project_id}"
        existing = (
            await session.scalars(
                select(ProjectEventModel).where(
                    ProjectEventModel.stream_key == stream_key,
                    ProjectEventModel.event_key == event_key,
                )
            )
        ).one_or_none()
        if existing:
            return
        sequence = (
            int(
                await session.scalar(
                    select(func.coalesce(func.max(ProjectEventModel.sequence), 0)).where(
                        ProjectEventModel.stream_key == stream_key
                    )
                )
                or 0
            )
            + 1
        )
        project = await session.get(ProjectModel, project_id)
        assert project is not None
        session.add(
            ProjectEventModel(
                tenant_id=project.tenant_id,
                project_id=project_id,
                run_id=None,
                stream_key=stream_key,
                sequence=sequence,
                event_key=event_key,
                event_type=type,
                schema_version=1,
                actor=actor or {"type": "system"},
                aggregate={"type": "novel_project", "id": project_id},
                causation_id=None,
                correlation_id=project_id,
                idempotency_key=event_key,
                payload=payload,
            )
        )
