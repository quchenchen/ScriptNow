from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select

from scriptnow.platform.database import Database
from scriptnow.platform.models import ProjectEventModel, ProjectModel
from scriptnow.platform.run_events import RunEventType
from scriptnow.review.domain import (
    FindingDraft,
    FindingSource,
    FindingStatus,
    ReviewFindingModel,
)


class ReviewError(RuntimeError):
    pass


class ReviewConflict(ReviewError):
    pass


@dataclass(frozen=True, slots=True)
class ReviewDomainAdapter:
    medium: str
    revision_model: type
    unit_field: str
    element_field: str
    adopted_status: str
    candidate_status: str
    superseded_status: str
    anchor_model: type
    anchor_blueprint_field: str
    anchor_key_field: str
    blueprint_model: type
    block_model: type
    validate_blocks: object


class ReviewService:
    def __init__(self, database: Database, adapter: ReviewDomainAdapter) -> None:
        self.database = database
        self.adapter = adapter

    async def scan_with_retry(
        self,
        *,
        tenant_id: str,
        project_id: str,
        unit_id: str,
        base_revision_id: str,
        drafts: tuple[FindingDraft, ...],
        author: str,
        idempotency_key: str,
    ) -> ReviewFindingModel:
        last_error: ReviewError | None = None
        for attempt, draft in enumerate(drafts[:3], 1):
            try:
                return await self.create(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    unit_id=unit_id,
                    base_revision_id=base_revision_id,
                    draft=draft,
                    source=FindingSource.AI,
                    author=author,
                    idempotency_key=f"{idempotency_key}:attempt:{attempt}",
                )
            except ReviewError as error:
                last_error = error
        raise ReviewError("review scan exhausted schema retries") from last_error

    async def create(
        self,
        *,
        tenant_id: str,
        project_id: str,
        unit_id: str,
        base_revision_id: str,
        draft: FindingDraft,
        source: FindingSource,
        author: str,
        idempotency_key: str,
    ) -> ReviewFindingModel:
        async with self.database.session() as session:
            await self._project(session, tenant_id, project_id)
            existing = (
                await session.scalars(
                    select(ReviewFindingModel).where(
                        ReviewFindingModel.project_id == project_id,
                        ReviewFindingModel.idempotency_key == idempotency_key,
                    )
                )
            ).one_or_none()
            if existing:
                return existing
            revision = await session.get(self.adapter.revision_model, base_revision_id)
            if (
                revision is None
                or revision.project_id != project_id
                or getattr(revision, self.adapter.unit_field) != unit_id
            ):
                raise ReviewError("base revision is outside the requested unit")
            await self._validate_anchor(session, project_id, draft.anchor_id)
            blocks = revision.blocks
            block = next(
                (
                    item
                    for item in blocks
                    if item.get(self.adapter.element_field) == draft.element_id
                ),
                None,
            )
            if block is None or draft.original_excerpt not in str(block.get("text", "")):
                raise ReviewError("original_excerpt cannot be located in base revision")
            item = ReviewFindingModel(
                tenant_id=tenant_id,
                project_id=project_id,
                medium=self.adapter.medium,
                unit_id=unit_id,
                base_revision_id=base_revision_id,
                element_id=draft.element_id,
                domain=draft.domain,
                severity=draft.severity,
                source=source,
                author=author,
                anchor_type=draft.anchor_type,
                anchor_id=draft.anchor_id,
                anchor_note=draft.anchor_note,
                original_excerpt=draft.original_excerpt,
                locator=draft.locator,
                diagnosis=draft.diagnosis,
                suggestion=draft.suggestion,
                suggested_patch=draft.suggested_patch,
                confidence=draft.confidence,
                idempotency_key=idempotency_key,
            )
            session.add(item)
            await session.flush()
            await self._event(
                session,
                project_id,
                f"review:create:{item.id}",
                {
                    "action": "review_finding.create",
                    "finding_id": item.id,
                    "source": source,
                },
            )
            return item

    async def list(
        self, *, tenant_id: str, project_id: str, filters: dict[str, str | None]
    ) -> list[ReviewFindingModel]:
        async with self.database.session() as session:
            await self._project(session, tenant_id, project_id)
            query = select(ReviewFindingModel).where(ReviewFindingModel.project_id == project_id)
            for key in ("domain", "severity", "source", "status", "unit_id"):
                if value := filters.get(key):
                    query = query.where(getattr(ReviewFindingModel, key) == value)
            return list(await session.scalars(query.order_by(ReviewFindingModel.created_at.desc())))

    async def dismiss(
        self, *, tenant_id: str, project_id: str, finding_id: str
    ) -> ReviewFindingModel:
        async with self.database.session() as session:
            item = await self._open(session, tenant_id, project_id, finding_id)
            item.status = FindingStatus.DISMISSED
            item.decided_at = datetime.now(UTC)
            await self._event(
                session,
                project_id,
                f"review:dismiss:{item.id}",
                {
                    "action": "review_finding.dismiss",
                    "finding_id": item.id,
                },
            )
            return item

    async def accept(
        self, *, tenant_id: str, project_id: str, finding_id: str
    ) -> ReviewFindingModel:
        stale_reason = None
        async with self.database.session() as session:
            item = await self._open(session, tenant_id, project_id, finding_id)
            current = (
                await session.scalars(
                    select(self.adapter.revision_model).where(
                        self.adapter.revision_model.project_id == project_id,
                        getattr(self.adapter.revision_model, self.adapter.unit_field)
                        == item.unit_id,
                        self.adapter.revision_model.status == self.adapter.adopted_status,
                    )
                )
            ).one_or_none()
            if current is None or current.id != item.base_revision_id:
                item.status = FindingStatus.STALE
                item.stale_reason = "base_revision_changed"
                item.decided_at = datetime.now(UTC)
                stale_reason = item.stale_reason
            else:
                patch = item.suggested_patch
                blocks = list(current.blocks)
                index = next(
                    (
                        i
                        for i, block in enumerate(blocks)
                        if block.get(self.adapter.element_field) == item.element_id
                    ),
                    None,
                )
                if index is None or blocks[index].get("text") != patch.get("expected_text"):
                    item.status = FindingStatus.STALE
                    item.stale_reason = "expected_text_changed"
                    item.decided_at = datetime.now(UTC)
                    stale_reason = item.stale_reason
                else:
                    replacement = patch.get("replacement")
                    if not isinstance(replacement, list) or not replacement:
                        raise ReviewError("structured patch replacement is invalid")
                    new_blocks = blocks[:index] + replacement + blocks[index + 1 :]
                    try:
                        validated = tuple(
                            self.adapter.block_model.model_validate(block) for block in new_blocks
                        )
                        self.adapter.validate_blocks(validated)
                    except (ValueError, RuntimeError) as error:
                        raise ReviewError(
                            "structured patch violates domain document contract"
                        ) from error
                    new_blocks = [block.model_dump(mode="json") for block in validated]
                    number = (
                        int(
                            await session.scalar(
                                select(
                                    func.coalesce(
                                        func.max(self.adapter.revision_model.revision_number), 0
                                    )
                                ).where(
                                    self.adapter.revision_model.project_id == project_id,
                                    getattr(self.adapter.revision_model, self.adapter.unit_field)
                                    == item.unit_id,
                                )
                            )
                            or 0
                        )
                        + 1
                    )
                    current.status = self.adapter.superseded_status
                    await session.flush()
                    values = {
                        "project_id": project_id,
                        self.adapter.unit_field: item.unit_id,
                        "revision_number": number,
                        "base_revision_id": current.id,
                        "blocks": new_blocks,
                        "status": self.adapter.adopted_status,
                        "idempotency_key": f"finding:{item.id}:accept",
                    }
                    revision = self.adapter.revision_model(**values)
                    session.add(revision)
                    await session.flush()
                    item.status = FindingStatus.ACCEPTED
                    item.superseded_by = revision.id
                    item.decided_at = datetime.now(UTC)
                    await self._event(
                        session,
                        project_id,
                        f"review:accept:{item.id}",
                        {
                            "action": "review_finding.accept",
                            "finding_id": item.id,
                            "revision_id": revision.id,
                        },
                    )
        if stale_reason:
            raise ReviewConflict(stale_reason)
        return item

    async def rollback(
        self, *, tenant_id: str, project_id: str, finding_id: str
    ) -> ReviewFindingModel:
        async with self.database.session() as session:
            await self._project(session, tenant_id, project_id)
            item = await session.get(ReviewFindingModel, finding_id)
            if (
                item is None
                or item.project_id != project_id
                or item.status != FindingStatus.ACCEPTED
            ):
                raise ReviewConflict("accepted finding is unavailable for rollback")
            current = (
                await session.scalars(
                    select(self.adapter.revision_model).where(
                        self.adapter.revision_model.project_id == project_id,
                        getattr(self.adapter.revision_model, self.adapter.unit_field)
                        == item.unit_id,
                        self.adapter.revision_model.status == self.adapter.adopted_status,
                    )
                )
            ).one_or_none()
            base = await session.get(self.adapter.revision_model, item.base_revision_id)
            if current is None or current.id != item.superseded_by or base is None:
                raise ReviewConflict("revision history advanced after finding acceptance")
            current.status = self.adapter.superseded_status
            await session.flush()
            number = (
                int(
                    await session.scalar(
                        select(
                            func.coalesce(func.max(self.adapter.revision_model.revision_number), 0)
                        ).where(
                            self.adapter.revision_model.project_id == project_id,
                            getattr(self.adapter.revision_model, self.adapter.unit_field)
                            == item.unit_id,
                        )
                    )
                    or 0
                )
                + 1
            )
            revision = self.adapter.revision_model(
                **{
                    "project_id": project_id,
                    self.adapter.unit_field: item.unit_id,
                    "revision_number": number,
                    "base_revision_id": current.id,
                    "blocks": base.blocks,
                    "status": self.adapter.adopted_status,
                    "idempotency_key": f"finding:{item.id}:rollback",
                }
            )
            session.add(revision)
            await session.flush()
            await self._event(
                session,
                project_id,
                f"review:rollback:{item.id}",
                {
                    "action": "review_finding.rollback",
                    "finding_id": item.id,
                    "revision_id": revision.id,
                },
            )
            return item

    async def _project(self, session, tenant_id: str, project_id: str) -> ProjectModel:
        project = await session.get(ProjectModel, project_id)
        if (
            project is None
            or project.tenant_id != tenant_id
            or project.medium != self.adapter.medium
        ):
            raise ReviewError("project is outside review tenant scope")
        return project

    async def _open(
        self, session, tenant_id: str, project_id: str, finding_id: str
    ) -> ReviewFindingModel:
        await self._project(session, tenant_id, project_id)
        item = await session.get(ReviewFindingModel, finding_id)
        if item is None or item.project_id != project_id or item.status != FindingStatus.OPEN:
            raise ReviewConflict("finding is unavailable")
        return item

    async def _validate_anchor(self, session, project_id: str, anchor_id: str) -> None:
        blueprint = (
            await session.scalars(
                select(self.adapter.blueprint_model).where(
                    self.adapter.blueprint_model.project_id == project_id,
                    self.adapter.blueprint_model.adopted.is_(True),
                )
            )
        ).one_or_none()
        if blueprint is None:
            raise ReviewError("adopted blueprint is required")
        anchor = (
            await session.scalars(
                select(self.adapter.anchor_model).where(
                    getattr(self.adapter.anchor_model, self.adapter.anchor_blueprint_field)
                    == blueprint.id,
                    getattr(self.adapter.anchor_model, self.adapter.anchor_key_field) == anchor_id,
                )
            )
        ).one_or_none()
        if anchor is None:
            raise ReviewError("finding references an unknown anchor")

    @staticmethod
    async def _event(session, project_id: str, event_key: str, payload: dict[str, object]) -> None:
        stream_key = f"project:{project_id}"
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
        session.add(
            ProjectEventModel(
                tenant_id=project.tenant_id,
                project_id=project_id,
                run_id=None,
                stream_key=stream_key,
                sequence=sequence,
                event_key=event_key,
                event_type=RunEventType.DECISION,
                schema_version=1,
                actor={"type": "system"},
                aggregate={
                    "type": "review_finding",
                    "id": str(payload.get("finding_id", project_id)),
                },
                causation_id=str(payload["revision_id"]) if payload.get("revision_id") else None,
                correlation_id=project_id,
                idempotency_key=event_key,
                payload=payload,
            )
        )
