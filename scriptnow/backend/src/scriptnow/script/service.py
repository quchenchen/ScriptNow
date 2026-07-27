import hashlib
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select

from scriptnow.platform.database import Database
from scriptnow.platform.models import ProjectEventModel, ProjectMedium, ProjectModel
from scriptnow.platform.run_events import RunEventType
from scriptnow.script.contracts import ScriptBlock
from scriptnow.script.domain import (
    BlueprintDraft,
    CandidateStatus,
    RevisionStatus,
    ScriptBlueprintAnchorModel,
    ScriptBlueprintCandidateModel,
    ScriptBlueprintModel,
    ScriptDocumentRevisionModel,
    ScriptStoryCoreCandidateModel,
    ScriptStructureCandidateModel,
    StoryCoreDraft,
)
from scriptnow.script.format_profiles import validate_script_structure
from scriptnow.script.project import ScriptPlanModel, ScriptStoryMapModel
from scriptnow.script.story_map import Episode


class ScriptDomainError(RuntimeError):
    pass


class ScriptConflict(ScriptDomainError):
    pass


@dataclass(frozen=True, slots=True)
class StructureImpact:
    added_units: int
    removed_units: int
    retained_units: int


class ScriptService:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def generate_story_cores(
        self,
        *,
        tenant_id: str,
        project_id: str,
        drafts: tuple[StoryCoreDraft, ...],
        revision_feedback: str | None = None,
        idempotency_key: str | None = None,
    ) -> list[ScriptStoryCoreCandidateModel]:
        if len(drafts) != 3:
            raise ScriptDomainError("exactly three StoryCore candidates are required")
        async with self.database.session() as session:
            await self._project(session, tenant_id, project_id)
            adopted = (
                await session.scalars(
                    select(ScriptStoryCoreCandidateModel).where(
                        ScriptStoryCoreCandidateModel.project_id == project_id,
                        ScriptStoryCoreCandidateModel.status == CandidateStatus.ADOPTED,
                    )
                )
            ).first()
            if adopted:
                raise ScriptConflict("adopted StoryCore locks the divergence phase")
            request_key = idempotency_key or str(uuid4())
            existing = list(
                await session.scalars(
                    select(ScriptStoryCoreCandidateModel)
                    .where(
                        ScriptStoryCoreCandidateModel.project_id == project_id,
                        ScriptStoryCoreCandidateModel.idempotency_key == request_key,
                    )
                    .order_by(ScriptStoryCoreCandidateModel.ordinal)
                )
            )
            if existing:
                return existing
            active = (
                await session.scalars(
                    select(ScriptStoryCoreCandidateModel).where(
                        ScriptStoryCoreCandidateModel.project_id == project_id,
                        ScriptStoryCoreCandidateModel.status == CandidateStatus.ACTIVE,
                    )
                )
            ).all()
            for item in active:
                item.status = CandidateStatus.EXPIRED
                item.revision_feedback = revision_feedback
            generation = (
                int(
                    await session.scalar(
                        select(
                            func.coalesce(func.max(ScriptStoryCoreCandidateModel.generation), 0)
                        ).where(ScriptStoryCoreCandidateModel.project_id == project_id)
                    )
                    or 0
                )
                + 1
            )
            records = [
                ScriptStoryCoreCandidateModel(
                    project_id=project_id,
                    generation=generation,
                    ordinal=index,
                    idempotency_key=request_key,
                    title=draft.title,
                    concept=draft.concept,
                    angles=list(draft.angles),
                    details=draft.details.model_dump(mode="json"),
                )
                for index, draft in enumerate(drafts, 1)
            ]
            session.add_all(records)
            await session.flush()
            await self._event(
                session,
                project_id,
                event_key=f"script:story-core:propose:{request_key}",
                event_type=RunEventType.CONVERSATION,
                payload={
                    "action": "script_story_core.propose",
                    "title": "灵感导演带来了三个故事发动方式",
                    "content": "可以比较人物欲望、主要阻力、推进机制与终局代价，再决定采用哪一个完整方向。",
                    "generation": generation,
                    "feedback": revision_feedback,
                    "candidates": [
                        {
                            "id": item.id,
                            "ordinal": item.ordinal,
                            "title": item.title,
                            "summary": item.concept,
                            "angles": list(item.angles),
                        }
                        for item in records
                    ],
                },
                actor={"type": "agent", "role": "director"},
            )
            return records

    async def adopt_story_core(
        self, *, tenant_id: str, project_id: str, candidate_id: str
    ) -> ScriptStoryCoreCandidateModel:
        async with self.database.session() as session:
            await self._project(session, tenant_id, project_id)
            candidate = await session.get(ScriptStoryCoreCandidateModel, candidate_id)
            if (
                candidate is None
                or candidate.project_id != project_id
                or candidate.status != CandidateStatus.ACTIVE
            ):
                raise ScriptConflict("StoryCore candidate is unavailable")
            adopted = (
                await session.scalars(
                    select(ScriptStoryCoreCandidateModel).where(
                        ScriptStoryCoreCandidateModel.project_id == project_id,
                        ScriptStoryCoreCandidateModel.status == CandidateStatus.ADOPTED,
                    )
                )
            ).first()
            if adopted:
                raise ScriptConflict("StoryCore is already adopted")
            siblings = (
                await session.scalars(
                    select(ScriptStoryCoreCandidateModel).where(
                        ScriptStoryCoreCandidateModel.project_id == project_id,
                        ScriptStoryCoreCandidateModel.generation == candidate.generation,
                    )
                )
            ).all()
            for item in siblings:
                item.status = (
                    CandidateStatus.ADOPTED if item.id == candidate.id else CandidateStatus.EXPIRED
                )
            plan = await self._plan(session, project_id)
            plan.status = "story_core_adopted"
            await self._event(
                session,
                project_id,
                event_key=f"script:story-core:adopt:{candidate.id}",
                event_type=RunEventType.DECISION,
                payload={
                    "action": "story_core.adopt",
                    "title": "你选择了剧本创意方向",
                    "content": "这条方向现在成为后续蓝图、StoryMap 与写作搭档共同遵循的创作核心。",
                    "candidate_id": candidate.id,
                    "candidate": {
                        "id": candidate.id,
                        "ordinal": candidate.ordinal,
                        "title": candidate.title,
                        "summary": candidate.concept,
                        "angles": list(candidate.angles),
                    },
                },
                actor={"type": "user"},
            )
            return candidate

    async def adopt_blueprint(
        self, *, tenant_id: str, project_id: str, draft: BlueprintDraft
    ) -> ScriptBlueprintModel:
        candidate = await self.propose_blueprint(
            tenant_id=tenant_id,
            project_id=project_id,
            draft=draft,
            idempotency_key=(
                "direct:" + hashlib.sha256(draft.model_dump_json().encode("utf-8")).hexdigest()
            ),
        )
        return await self.adopt_blueprint_candidate(
            tenant_id=tenant_id, project_id=project_id, candidate_id=candidate.id
        )

    async def propose_blueprint(
        self,
        *,
        tenant_id: str,
        project_id: str,
        draft: BlueprintDraft,
        idempotency_key: str,
        revision_feedback: str | None = None,
    ) -> ScriptBlueprintCandidateModel:
        async with self.database.session() as session:
            await self._project(session, tenant_id, project_id)
            existing = (
                await session.scalars(
                    select(ScriptBlueprintCandidateModel).where(
                        ScriptBlueprintCandidateModel.project_id == project_id,
                        ScriptBlueprintCandidateModel.idempotency_key == idempotency_key,
                    )
                )
            ).one_or_none()
            if existing:
                return existing
            core = (
                await session.scalars(
                    select(ScriptStoryCoreCandidateModel).where(
                        ScriptStoryCoreCandidateModel.project_id == project_id,
                        ScriptStoryCoreCandidateModel.status == CandidateStatus.ADOPTED,
                    )
                )
            ).one_or_none()
            if core is None:
                raise ScriptConflict("adopt StoryCore before blueprint")
            if len({anchor.id for anchor in draft.anchors}) != len(draft.anchors):
                raise ScriptDomainError("blueprint anchor IDs must be unique")
            active_candidates = list(
                await session.scalars(
                    select(ScriptBlueprintCandidateModel).where(
                        ScriptBlueprintCandidateModel.project_id == project_id,
                        ScriptBlueprintCandidateModel.status == CandidateStatus.ACTIVE,
                    )
                )
            )
            for active_candidate in active_candidates:
                active_candidate.status = CandidateStatus.EXPIRED
            candidate = ScriptBlueprintCandidateModel(
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
                event_key=f"script:blueprint:propose:{candidate.id}",
                event_type=RunEventType.NODE,
                payload={
                    "action": "blueprint.revise" if revision_feedback else "blueprint.propose",
                    "candidate_id": candidate.id,
                    "role": "architect",
                    "feedback": revision_feedback,
                },
            )
            return candidate

    async def adopt_blueprint_candidate(
        self, *, tenant_id: str, project_id: str, candidate_id: str
    ) -> ScriptBlueprintModel:
        async with self.database.session() as session:
            await self._project(session, tenant_id, project_id)
            candidate = await session.get(ScriptBlueprintCandidateModel, candidate_id)
            if (
                candidate is None
                or candidate.project_id != project_id
                or candidate.status != CandidateStatus.ACTIVE
            ):
                raise ScriptConflict("blueprint candidate is unavailable")
            core = (
                await session.scalars(
                    select(ScriptStoryCoreCandidateModel).where(
                        ScriptStoryCoreCandidateModel.project_id == project_id,
                        ScriptStoryCoreCandidateModel.status == CandidateStatus.ADOPTED,
                    )
                )
            ).one_or_none()
            if core is None or core.id != candidate.story_core_candidate_id:
                candidate.status = CandidateStatus.EXPIRED
                raise ScriptConflict("blueprint candidate is stale")
            previous = (
                await session.scalars(
                    select(ScriptBlueprintModel).where(
                        ScriptBlueprintModel.project_id == project_id,
                        ScriptBlueprintModel.adopted.is_(True),
                    )
                )
            ).one_or_none()
            if previous:
                previous.adopted = False
            version = (previous.version + 1) if previous else 1
            blueprint = ScriptBlueprintModel(
                project_id=project_id,
                version=version,
                story_core_candidate_id=candidate.story_core_candidate_id,
            )
            session.add(blueprint)
            await session.flush()
            draft = BlueprintDraft.model_validate(candidate.draft)
            session.add_all(
                [
                    ScriptBlueprintAnchorModel(
                        blueprint_id=blueprint.id,
                        anchor_key=item.id,
                        kind=item.kind,
                        name=item.name,
                        payload=item.payload,
                    )
                    for item in draft.anchors
                ]
            )
            plan = await self._plan(session, project_id)
            plan.status = "blueprint_adopted"
            candidate.status = CandidateStatus.ADOPTED
            await self._event(
                session,
                project_id,
                event_key=f"script:blueprint:adopt:{blueprint.id}",
                event_type=RunEventType.DECISION,
                payload={"action": "blueprint.adopt", "blueprint_id": blueprint.id},
            )
            return blueprint

    async def propose_structure(
        self,
        *,
        tenant_id: str,
        project_id: str,
        expected_version: int,
        episodes: tuple[Episode, ...],
        idempotency_key: str,
    ) -> ScriptStructureCandidateModel:
        async with self.database.session() as session:
            await self._project(session, tenant_id, project_id)
            existing = (
                await session.scalars(
                    select(ScriptStructureCandidateModel).where(
                        ScriptStructureCandidateModel.project_id == project_id,
                        ScriptStructureCandidateModel.idempotency_key == idempotency_key,
                    )
                )
            ).one_or_none()
            if existing:
                return existing
            story_map = await self._story_map(session, project_id)
            if story_map.version != expected_version:
                raise ScriptConflict("StoryMap version conflict")
            await self._validate_anchors(session, project_id, episodes)
            current_ids = self._unit_ids(story_map.episodes)
            proposed = [episode.model_dump(mode="json") for episode in episodes]
            proposed_ids = self._unit_ids(proposed)
            impact = StructureImpact(
                added_units=len(proposed_ids - current_ids),
                removed_units=len(current_ids - proposed_ids),
                retained_units=len(current_ids & proposed_ids),
            )
            active_candidates = list(
                await session.scalars(
                    select(ScriptStructureCandidateModel).where(
                        ScriptStructureCandidateModel.project_id == project_id,
                        ScriptStructureCandidateModel.status == CandidateStatus.ACTIVE,
                    )
                )
            )
            for active_candidate in active_candidates:
                active_candidate.status = CandidateStatus.EXPIRED
            candidate = ScriptStructureCandidateModel(
                project_id=project_id,
                base_version=expected_version,
                proposed_episodes=proposed,
                impact={
                    "added_units": impact.added_units,
                    "removed_units": impact.removed_units,
                    "retained_units": impact.retained_units,
                },
                idempotency_key=idempotency_key,
            )
            session.add(candidate)
            await session.flush()
            return candidate

    async def adopt_structure(
        self, *, tenant_id: str, project_id: str, candidate_id: str
    ) -> ScriptStoryMapModel:
        stale = False
        result: ScriptStoryMapModel | None = None
        async with self.database.session() as session:
            await self._project(session, tenant_id, project_id)
            candidate = await session.get(ScriptStructureCandidateModel, candidate_id)
            if (
                candidate is None
                or candidate.project_id != project_id
                or candidate.status != CandidateStatus.ACTIVE
            ):
                raise ScriptConflict("structure candidate is unavailable")
            story_map = await self._story_map(session, project_id)
            if story_map.version != candidate.base_version:
                candidate.status = CandidateStatus.EXPIRED
                stale = True
            else:
                story_map.episodes = candidate.proposed_episodes
                story_map.version += 1
                candidate.status = CandidateStatus.ADOPTED
                plan = await self._plan(session, project_id)
                plan.status = "writing"
                await self._event(
                    session,
                    project_id,
                    event_key=f"script:story-map:adopt:{candidate.id}",
                    event_type=RunEventType.DECISION,
                    payload={
                        "action": "story_map.adopt",
                        "candidate_id": candidate.id,
                        "version": story_map.version,
                        "impact": candidate.impact,
                    },
                )
                result = story_map
        if stale:
            raise ScriptConflict("structure candidate is stale")
        assert result is not None
        return result

    async def propose_document(
        self,
        *,
        tenant_id: str,
        project_id: str,
        scene_id: str,
        blocks: tuple[ScriptBlock, ...],
        idempotency_key: str,
    ) -> ScriptDocumentRevisionModel:
        async with self.database.session() as session:
            await self._project(session, tenant_id, project_id)
            self._validate_blocks(blocks)
            existing = (
                await session.scalars(
                    select(ScriptDocumentRevisionModel).where(
                        ScriptDocumentRevisionModel.project_id == project_id,
                        ScriptDocumentRevisionModel.idempotency_key == idempotency_key,
                    )
                )
            ).one_or_none()
            if existing:
                return existing
            story_map = await self._story_map(session, project_id)
            if scene_id not in self._scene_ids(story_map.episodes):
                raise ScriptDomainError("scene is not present in Script StoryMap")
            adopted = (
                await session.scalars(
                    select(ScriptDocumentRevisionModel).where(
                        ScriptDocumentRevisionModel.project_id == project_id,
                        ScriptDocumentRevisionModel.scene_id == scene_id,
                        ScriptDocumentRevisionModel.status == RevisionStatus.ADOPTED,
                    )
                )
            ).one_or_none()
            revision_number = (
                int(
                    await session.scalar(
                        select(
                            func.coalesce(func.max(ScriptDocumentRevisionModel.revision_number), 0)
                        ).where(
                            ScriptDocumentRevisionModel.project_id == project_id,
                            ScriptDocumentRevisionModel.scene_id == scene_id,
                        )
                    )
                    or 0
                )
                + 1
            )
            record = ScriptDocumentRevisionModel(
                project_id=project_id,
                scene_id=scene_id,
                revision_number=revision_number,
                base_revision_id=adopted.id if adopted else None,
                blocks=[block.model_dump(mode="json") for block in blocks],
                idempotency_key=idempotency_key,
            )
            session.add(record)
            await session.flush()
            return record

    async def adopt_document(
        self, *, tenant_id: str, project_id: str, revision_id: str
    ) -> ScriptDocumentRevisionModel:
        stale = False
        result: ScriptDocumentRevisionModel | None = None
        async with self.database.session() as session:
            await self._project(session, tenant_id, project_id)
            revision = await session.get(ScriptDocumentRevisionModel, revision_id)
            if (
                revision is None
                or revision.project_id != project_id
                or revision.status != RevisionStatus.CANDIDATE
            ):
                raise ScriptConflict("document candidate is unavailable")
            adopted = (
                await session.scalars(
                    select(ScriptDocumentRevisionModel).where(
                        ScriptDocumentRevisionModel.project_id == project_id,
                        ScriptDocumentRevisionModel.scene_id == revision.scene_id,
                        ScriptDocumentRevisionModel.status == RevisionStatus.ADOPTED,
                    )
                )
            ).one_or_none()
            current_id = adopted.id if adopted else None
            if revision.base_revision_id != current_id:
                revision.status = RevisionStatus.SUPERSEDED
                stale = True
            else:
                if adopted:
                    adopted.status = RevisionStatus.SUPERSEDED
                    await session.flush()
                revision.status = RevisionStatus.ADOPTED
                await self._event(
                    session,
                    project_id,
                    event_key=f"script:document:adopt:{revision.id}",
                    event_type=RunEventType.DECISION,
                    payload={
                        "action": "script_document.adopt",
                        "scene_id": revision.scene_id,
                        "revision_id": revision.id,
                    },
                )
                result = revision
        if stale:
            raise ScriptConflict("document candidate base revision is stale")
        assert result is not None
        return result

    async def context_pack(
        self, *, tenant_id: str, project_id: str, scene_id: str
    ) -> dict[str, object]:
        async with self.database.session() as session:
            await self._project(session, tenant_id, project_id)
            story_map = await self._story_map(session, project_id)
            ordered_scenes = [
                scene
                for episode in story_map.episodes
                for scene in episode.get("scenes", [])  # type: ignore[union-attr]
            ]
            scene_index = next(
                (
                    index
                    for index, scene in enumerate(ordered_scenes)
                    if str(scene.get("id")) == scene_id
                ),
                None,
            )
            if scene_index is None:
                raise ScriptDomainError("scene is outside the adopted StoryMap")
            current_scene = ordered_scenes[scene_index]
            referenced_anchor_ids = {
                str(anchor_id)
                for beat in current_scene.get("beats", [])  # type: ignore[union-attr]
                for anchor_id in beat.get("anchor_ids", [])
            }
            continuity_scene_ids = {scene_id}
            if scene_index > 0:
                continuity_scene_ids.add(str(ordered_scenes[scene_index - 1]["id"]))
            blueprint = (
                await session.scalars(
                    select(ScriptBlueprintModel).where(
                        ScriptBlueprintModel.project_id == project_id,
                        ScriptBlueprintModel.adopted.is_(True),
                    )
                )
            ).one_or_none()
            anchors = []
            if blueprint:
                anchors = list(
                    await session.scalars(
                        select(ScriptBlueprintAnchorModel).where(
                            ScriptBlueprintAnchorModel.blueprint_id == blueprint.id,
                            ScriptBlueprintAnchorModel.anchor_key.in_(referenced_anchor_ids),
                        )
                    )
                )
            documents = list(
                await session.scalars(
                    select(ScriptDocumentRevisionModel).where(
                        ScriptDocumentRevisionModel.project_id == project_id,
                        ScriptDocumentRevisionModel.status == RevisionStatus.ADOPTED,
                        ScriptDocumentRevisionModel.scene_id.in_(continuity_scene_ids),
                    )
                )
            )
            return {
                "scene_id": scene_id,
                "anchors": [
                    {
                        "id": item.anchor_key,
                        "kind": item.kind,
                        "name": item.name,
                        "payload": self._writer_anchor_projection(item.payload),
                    }
                    for item in anchors
                ],
                "adopted_scenes": [
                    {"scene_id": item.scene_id, "revision_id": item.id, "blocks": item.blocks}
                    for item in documents
                ],
            }

    @staticmethod
    def _writer_anchor_projection(payload: dict[str, Any]) -> dict[str, object]:
        """Keep the writer prompt focused without altering the adopted blueprint."""

        preferred_keys = (
            "description",
            "arc_statement",
            "event",
            "purpose",
            "rule",
            "setup",
            "payoff",
        )
        projected: dict[str, object] = {}
        for key in preferred_keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                projected[key] = value[:1200]
        if projected:
            return projected

        for key, value in payload.items():
            if len(projected) >= 4:
                break
            if isinstance(value, str) and value.strip():
                projected[key] = value[:800]
            elif isinstance(value, int | float | bool):
                projected[key] = value
            elif isinstance(value, list):
                projected[key] = [
                    item[:300] if isinstance(item, str) else item
                    for item in value[:6]
                    if isinstance(item, str | int | float | bool)
                ]
        return projected

    @staticmethod
    async def _project(session, tenant_id: str, project_id: str) -> ProjectModel:
        project = await session.get(ProjectModel, project_id)
        if (
            project is None
            or project.tenant_id != tenant_id
            or project.medium != ProjectMedium.SCRIPT
        ):
            raise ScriptDomainError("project is outside Script tenant scope")
        return project

    @staticmethod
    async def _plan(session, project_id: str) -> ScriptPlanModel:
        plan = (
            await session.scalars(
                select(ScriptPlanModel).where(ScriptPlanModel.project_id == project_id)
            )
        ).one()
        return plan

    @staticmethod
    async def _story_map(session, project_id: str) -> ScriptStoryMapModel:
        story_map = (
            await session.scalars(
                select(ScriptStoryMapModel).where(ScriptStoryMapModel.project_id == project_id)
            )
        ).one()
        return story_map

    @staticmethod
    async def _validate_anchors(session, project_id: str, episodes: tuple[Episode, ...]) -> None:
        blueprint = (
            await session.scalars(
                select(ScriptBlueprintModel).where(
                    ScriptBlueprintModel.project_id == project_id,
                    ScriptBlueprintModel.adopted.is_(True),
                )
            )
        ).one_or_none()
        if blueprint is None:
            raise ScriptConflict("adopt blueprint before StoryMap")
        valid = set(
            await session.scalars(
                select(ScriptBlueprintAnchorModel.anchor_key).where(
                    ScriptBlueprintAnchorModel.blueprint_id == blueprint.id
                )
            )
        )
        referenced = {
            anchor
            for episode in episodes
            for scene in episode.scenes
            for beat in scene.beats
            for anchor in beat.anchor_ids
        }
        if not referenced <= valid:
            raise ScriptDomainError("StoryMap references unknown blueprint anchors")

    @staticmethod
    def _unit_ids(episodes: list[dict[str, object]]) -> set[str]:
        ids = set()
        for episode in episodes:
            ids.add(str(episode["id"]))
            for scene in episode.get("scenes", []):  # type: ignore[union-attr]
                ids.add(str(scene["id"]))
                ids.update(str(beat["id"]) for beat in scene.get("beats", []))
        return ids

    @staticmethod
    def _scene_ids(episodes: list[dict[str, object]]) -> set[str]:
        return {
            str(scene["id"])
            for episode in episodes
            for scene in episode.get("scenes", [])  # type: ignore[union-attr]
        }

    @staticmethod
    def _validate_blocks(blocks: tuple[ScriptBlock, ...]) -> None:
        issues = validate_script_structure(blocks)
        if issues:
            raise ScriptDomainError("；".join(issues))

    @staticmethod
    async def _event(
        session,
        project_id: str,
        *,
        event_key: str,
        event_type: RunEventType,
        payload: dict[str, object],
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
                event_type=event_type,
                schema_version=1,
                actor=actor or {"type": "system"},
                aggregate={"type": "script_project", "id": project_id},
                causation_id=None,
                correlation_id=project_id,
                idempotency_key=event_key,
                payload=payload,
            )
        )
