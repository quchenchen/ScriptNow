from __future__ import annotations

import difflib
import hashlib
import json
from uuid import uuid4

from sqlalchemy import func, select

from scriptflow_v7.novel.contracts import NovelBlock
from scriptflow_v7.novel.domain import (
    NovelDocumentRevisionModel,
    NovelRevisionStatus,
    NovelSnapshotContentModel,
)
from scriptflow_v7.platform.database import Database
from scriptflow_v7.platform.models import ProjectEventModel, ProjectModel, ProjectSnapshotModel


class NovelHistoryError(RuntimeError):
    pass


class NovelHistoryConflict(NovelHistoryError):
    pass


class NovelHistoryService:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def create_snapshot(
        self, *, tenant_id: str, project_id: str, name: str
    ) -> ProjectSnapshotModel:
        if not name.strip():
            raise NovelHistoryError("snapshot name is required")
        async with self.database.session() as session:
            await _project(session, tenant_id, project_id)
            documents = await _current_documents(session, project_id)
            if not documents:
                raise NovelHistoryError("snapshot requires adopted Novel chapters")
            version = (
                int(
                    await session.scalar(
                        select(func.coalesce(func.max(ProjectSnapshotModel.version), 0)).where(
                            ProjectSnapshotModel.project_id == project_id
                        )
                    )
                    or 0
                )
                + 1
            )
            previous = (
                await session.scalars(
                    select(ProjectSnapshotModel)
                    .where(ProjectSnapshotModel.project_id == project_id)
                    .order_by(ProjectSnapshotModel.version.desc())
                )
            ).first()
            snapshot = ProjectSnapshotModel(
                tenant_id=tenant_id,
                project_id=project_id,
                medium="novel",
                version=version,
                name=name.strip(),
                scope=[str(item["unit_id"]) for item in documents],
                word_count=sum(
                    len(str(block["text"])) for item in documents for block in item["blocks"]
                ),
                content_hash=_hash(documents),
                base_snapshot_id=previous.id if previous else None,
            )
            session.add(snapshot)
            await session.flush()
            session.add(NovelSnapshotContentModel(snapshot_id=snapshot.id, documents=documents))
            await _event(
                session,
                tenant_id,
                project_id,
                event_key=f"novel:snapshot:create:{snapshot.id}",
                action="novel_snapshot.created",
                aggregate_id=snapshot.id,
                idempotency_key=snapshot.id,
                payload={
                    "version": version,
                    "name": snapshot.name,
                    "content_hash": snapshot.content_hash,
                },
            )
            return snapshot

    async def list(self, *, tenant_id: str, project_id: str) -> list[ProjectSnapshotModel]:
        async with self.database.session() as session:
            await _project(session, tenant_id, project_id)
            return list(
                await session.scalars(
                    select(ProjectSnapshotModel)
                    .where(
                        ProjectSnapshotModel.project_id == project_id,
                        ProjectSnapshotModel.medium == "novel",
                    )
                    .order_by(ProjectSnapshotModel.version.desc())
                )
            )

    async def diff(self, *, tenant_id: str, project_id: str, snapshot_id: str) -> dict[str, object]:
        async with self.database.session() as session:
            snapshot, content = await _snapshot(session, tenant_id, project_id, snapshot_id)
            current = await _current_documents(session, project_id, set(snapshot.scope))
            return _diff(content.documents, current, snapshot.content_hash)

    async def rollback(
        self,
        *,
        tenant_id: str,
        project_id: str,
        snapshot_id: str,
        expected_current_hash: str,
        idempotency_key: str,
    ) -> list[NovelDocumentRevisionModel]:
        async with self.database.session() as session:
            snapshot, content = await _snapshot(session, tenant_id, project_id, snapshot_id)
            replay_keys = [
                f"snapshot:{idempotency_key}:{document['unit_id']}"
                for document in content.documents
            ]
            existing = list(
                await session.scalars(
                    select(NovelDocumentRevisionModel).where(
                        NovelDocumentRevisionModel.project_id == project_id,
                        NovelDocumentRevisionModel.idempotency_key.in_(replay_keys),
                    )
                )
            )
            if existing:
                return existing
            current = await _current_documents(session, project_id, set(snapshot.scope))
            if _hash(current) != expected_current_hash:
                raise NovelHistoryConflict("Novel changed after rollback preview")
            current_by_unit = {str(item["unit_id"]): item for item in current}
            created = []
            rollback_id = uuid4().hex
            for document in content.documents:
                unit_id = str(document["unit_id"])
                blocks = [
                    NovelBlock.model_validate(item).model_dump(mode="json")
                    for item in document["blocks"]
                ]
                current_document = current_by_unit.get(unit_id)
                if current_document:
                    adopted = await session.get(
                        NovelDocumentRevisionModel, str(current_document["revision_id"])
                    )
                    if adopted:
                        adopted.status = NovelRevisionStatus.SUPERSEDED
                number = (
                    int(
                        await session.scalar(
                            select(
                                func.coalesce(
                                    func.max(NovelDocumentRevisionModel.revision_number), 0
                                )
                            ).where(
                                NovelDocumentRevisionModel.project_id == project_id,
                                NovelDocumentRevisionModel.chapter_id == unit_id,
                            )
                        )
                        or 0
                    )
                    + 1
                )
                revision = NovelDocumentRevisionModel(
                    project_id=project_id,
                    chapter_id=unit_id,
                    revision_number=number,
                    base_revision_id=str(current_document["revision_id"])
                    if current_document
                    else None,
                    blocks=blocks,
                    status=NovelRevisionStatus.ADOPTED,
                    idempotency_key=f"snapshot:{idempotency_key}:{unit_id}",
                )
                session.add(revision)
                created.append(revision)
            await session.flush()
            await _event(
                session,
                tenant_id,
                project_id,
                event_key=f"novel:snapshot:rollback:{idempotency_key}",
                action="novel_snapshot.rolled_back",
                aggregate_id=snapshot.id,
                idempotency_key=idempotency_key,
                payload={
                    "snapshot_id": snapshot.id,
                    "rollback_id": rollback_id,
                    "revision_ids": [item.id for item in created],
                },
            )
            return created


async def _project(session, tenant_id: str, project_id: str) -> ProjectModel:
    project = await session.get(ProjectModel, project_id)
    if project is None or project.tenant_id != tenant_id or project.medium != "novel":
        raise NovelHistoryError("Novel project is outside tenant scope")
    return project


async def _snapshot(session, tenant_id, project_id, snapshot_id):
    await _project(session, tenant_id, project_id)
    snapshot = await session.get(ProjectSnapshotModel, snapshot_id)
    content = await session.get(NovelSnapshotContentModel, snapshot_id)
    if (
        snapshot is None
        or snapshot.project_id != project_id
        or snapshot.medium != "novel"
        or content is None
    ):
        raise NovelHistoryError("Novel snapshot is unavailable")
    return snapshot, content


async def _current_documents(session, project_id: str, scope: set[str] | None = None):
    query = select(NovelDocumentRevisionModel).where(
        NovelDocumentRevisionModel.project_id == project_id,
        NovelDocumentRevisionModel.status == NovelRevisionStatus.ADOPTED,
    )
    if scope is not None:
        query = query.where(NovelDocumentRevisionModel.chapter_id.in_(scope))
    records = list(await session.scalars(query.order_by(NovelDocumentRevisionModel.chapter_id)))
    return [
        {"unit_id": item.chapter_id, "revision_id": item.id, "blocks": item.blocks}
        for item in records
    ]


def _hash(documents) -> str:
    normalized = [
        {"unit_id": item["unit_id"], "blocks": item["blocks"]}
        for item in sorted(documents, key=lambda value: str(value["unit_id"]))
    ]
    return hashlib.sha256(
        json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _diff(snapshot_documents, current_documents, snapshot_hash):
    old = {str(item["unit_id"]): item for item in snapshot_documents}
    new = {str(item["unit_id"]): item for item in current_documents}
    units = []
    for unit_id in sorted(set(old) | set(new)):
        before = "\n".join(str(block["text"]) for block in old.get(unit_id, {}).get("blocks", []))
        after = "\n".join(str(block["text"]) for block in new.get(unit_id, {}).get("blocks", []))
        status = (
            "same"
            if before == after
            else "added"
            if not before
            else "removed"
            if not after
            else "changed"
        )
        units.append(
            {
                "unit_id": unit_id,
                "status": status,
                "lines": list(difflib.ndiff(before.splitlines(), after.splitlines())),
            }
        )
    return {
        "snapshot_hash": snapshot_hash,
        "current_hash": _hash(current_documents),
        "units": units,
    }


async def _event(
    session, tenant_id, project_id, *, event_key, action, aggregate_id, idempotency_key, payload
):
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
    session.add(
        ProjectEventModel(
            tenant_id=tenant_id,
            project_id=project_id,
            stream_key=stream_key,
            sequence=sequence,
            event_key=event_key,
            event_type="decision",
            actor={"type": "user", "id": tenant_id},
            aggregate={"type": "novel_snapshot", "id": aggregate_id},
            correlation_id=aggregate_id,
            idempotency_key=idempotency_key,
            payload={"action": action, **payload},
        )
    )
