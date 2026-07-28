from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scriptnow.platform.models import (
    CreativeArtifactRefModel,
    CreativeContextManifestModel,
    CreativeDecisionRequestModel,
    CreativeOperationModel,
    CreativeTurnModel,
    DecisionRequestStatus,
    ProjectModel,
)

CONTEXT_MANIFEST_SCHEMA_VERSION = 1


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def content_digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ContextManifestView:
    id: str
    content_digest: str
    content: dict[str, object]
    source_versions: dict[str, object]


class ContextManifestStore:
    """Build and load immutable manifests without importing domain implementations."""

    async def build(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        project: ProjectModel,
        session_id: str,
        turn_id: str | None,
        domain: str,
        stage: str,
        policy_snapshot: dict[str, object],
    ) -> CreativeContextManifestModel:
        turn_input: dict[str, object] | None = None
        if turn_id is not None:
            turn = await session.get(CreativeTurnModel, turn_id)
            if turn is None or turn.session_id != session_id:
                raise ValueError("turn is outside creative session")
            turn_input = turn.input

        artifact_rows = list(
            await session.scalars(
                select(CreativeArtifactRefModel)
                .join(
                    CreativeOperationModel,
                    CreativeOperationModel.id == CreativeArtifactRefModel.operation_id,
                )
                .where(
                    CreativeOperationModel.tenant_id == tenant_id,
                    CreativeOperationModel.project_id == project.id,
                    CreativeOperationModel.domain == domain,
                    CreativeArtifactRefModel.status.in_(("adopted", "accepted", "ready")),
                )
                .order_by(
                    CreativeArtifactRefModel.artifact_type,
                    CreativeArtifactRefModel.artifact_id,
                    CreativeArtifactRefModel.revision.desc(),
                )
            )
        )
        latest_artifacts: dict[tuple[str, str], CreativeArtifactRefModel] = {}
        for artifact in artifact_rows:
            latest_artifacts.setdefault(
                (artifact.artifact_type, artifact.artifact_id),
                artifact,
            )

        decisions = list(
            await session.scalars(
                select(CreativeDecisionRequestModel)
                .join(
                    CreativeOperationModel,
                    CreativeOperationModel.id == CreativeDecisionRequestModel.operation_id,
                )
                .where(
                    CreativeOperationModel.tenant_id == tenant_id,
                    CreativeOperationModel.project_id == project.id,
                    CreativeOperationModel.domain == domain,
                    CreativeDecisionRequestModel.status.in_(
                        (
                            DecisionRequestStatus.APPROVED,
                            DecisionRequestStatus.REJECTED,
                        )
                    ),
                )
                .order_by(CreativeDecisionRequestModel.decided_at)
            )
        )

        source_versions: dict[str, object] = {
            "project": content_digest(
                {
                    "name": project.name,
                    "medium": project.medium,
                    "source_mode": project.source_mode,
                    "workflow_kind": project.workflow_kind,
                    "direction": project.direction,
                }
            ),
            "artifacts": {
                f"{item.artifact_type}:{item.artifact_id}": {
                    "revision": item.revision,
                    "input_digest": item.input_digest,
                }
                for item in latest_artifacts.values()
            },
        }
        content: dict[str, object] = {
            "schema_version": CONTEXT_MANIFEST_SCHEMA_VERSION,
            "project": {
                "id": project.id,
                "name": project.name,
                "medium": project.medium,
                "source_mode": project.source_mode,
                "workflow_kind": project.workflow_kind,
                "direction": project.direction,
            },
            "operation": {
                "domain": domain,
                "stage": stage,
                "policy": policy_snapshot,
            },
            "turn_input": turn_input,
            "adopted_artifacts": [
                {
                    "domain": item.domain,
                    "artifact_type": item.artifact_type,
                    "artifact_id": item.artifact_id,
                    "revision": item.revision,
                    "schema_version": item.schema_version,
                    "input_digest": item.input_digest,
                    "dependency_versions": item.dependency_versions,
                }
                for item in latest_artifacts.values()
            ],
            "decisions": [
                {
                    "kind": item.kind,
                    "status": item.status,
                    "decision": item.decision,
                    "decided_at": item.decided_at.isoformat() if item.decided_at else None,
                }
                for item in decisions
            ],
        }
        digest = content_digest(content)
        existing = (
            await session.scalars(
                select(CreativeContextManifestModel).where(
                    CreativeContextManifestModel.tenant_id == tenant_id,
                    CreativeContextManifestModel.project_id == project.id,
                    CreativeContextManifestModel.content_digest == digest,
                )
            )
        ).one_or_none()
        if existing is not None:
            return existing
        manifest = CreativeContextManifestModel(
            tenant_id=tenant_id,
            project_id=project.id,
            session_id=session_id,
            turn_id=turn_id,
            domain=domain,
            stage=stage,
            schema_version=CONTEXT_MANIFEST_SCHEMA_VERSION,
            content_digest=digest,
            content=content,
            source_versions=source_versions,
        )
        session.add(manifest)
        await session.flush()
        return manifest

    async def load(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        manifest_id: str,
    ) -> ContextManifestView:
        manifest = await session.get(CreativeContextManifestModel, manifest_id)
        if manifest is None or manifest.tenant_id != tenant_id:
            raise ValueError("context manifest is outside tenant scope")
        if content_digest(manifest.content) != manifest.content_digest:
            raise ValueError("context manifest digest does not match immutable content")
        return ContextManifestView(
            id=manifest.id,
            content_digest=manifest.content_digest,
            content=manifest.content,
            source_versions=manifest.source_versions,
        )
