from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scriptnow.novel.cross_cultural_recreation.domain import (
    CrossCulturalArtifactModel,
    CrossCulturalRecreationModel,
    RecreationArtifactKind,
    RecreationProductionUnitModel,
)
from scriptnow.novel.domain import (
    NovelBlueprintModel,
    NovelDocumentRevisionModel,
    NovelExportManifestModel,
    NovelQualityReportModel,
    NovelStoryCoreCandidateModel,
)
from scriptnow.novel.project import NovelStoryMapModel
from scriptnow.platform.creative_flow_audit import (
    FlowObservation,
    GoldenScenario,
    ObservedArtifact,
    ObservedDecision,
    ObservedStage,
)
from scriptnow.platform.models import (
    CreativeDeliveryArtifactModel,
    ProjectMedium,
    ProjectModel,
    ProjectRunModel,
    ProjectSnapshotModel,
    ProjectWorkflow,
    RunStatus,
    WorkPackageModel,
)
from scriptnow.script.domain import (
    ScriptBlueprintModel,
    ScriptDocumentRevisionModel,
    ScriptExportManifestModel,
    ScriptStoryCoreCandidateModel,
)
from scriptnow.script.project import ScriptStoryMapModel
from scriptnow.translation.domain import (
    TranslationGlossaryTermModel,
    TranslationSnapshotContentModel,
)


def _artifact(
    *,
    artifact_id: str,
    kind: str,
    revision: str,
    readable: bool,
    next_stage_consumable: bool,
) -> ObservedArtifact:
    return ObservedArtifact(
        id=artifact_id,
        kind=kind,
        revision=revision,
        readable=readable,
        persisted=True,
        next_stage_consumable=next_stage_consumable,
    )


def _stage(stage_id: str, artifacts: Sequence[ObservedArtifact]) -> ObservedStage:
    materialized = list(artifacts)
    # Superseded and rejected revisions remain useful history. A stage is
    # complete once at least one persisted artifact is consumable downstream.
    valid = bool(materialized) and any(
        item.persisted and item.readable and item.next_stage_consumable
        for item in materialized
    )
    return ObservedStage(
        id=stage_id,
        status="succeeded" if valid else "partial",
        artifacts=materialized,
    )


def _adoption_decision(
    *,
    stage_id: str,
    artifact_id: str,
    adopted_count: int,
) -> ObservedDecision:
    return ObservedDecision(
        stage_id=stage_id,
        request_id=f"adoption:{artifact_id}",
        resolved=adopted_count == 1,
        resolution_count=adopted_count,
    )


async def _novel_evidence(
    session: AsyncSession, project: ProjectModel
) -> tuple[list[ObservedStage], list[ObservedDecision]]:
    project_id = project.id
    core = (
        await session.scalars(
            select(NovelStoryCoreCandidateModel).where(
                NovelStoryCoreCandidateModel.project_id == project_id,
                NovelStoryCoreCandidateModel.status == "adopted",
            )
        )
    ).all()
    blueprints = (
        await session.scalars(
            select(NovelBlueprintModel).where(
                NovelBlueprintModel.project_id == project_id,
                NovelBlueprintModel.adopted.is_(True),
            )
        )
    ).all()
    story_map = (
        await session.scalars(
            select(NovelStoryMapModel).where(NovelStoryMapModel.project_id == project_id)
        )
    ).one_or_none()
    revisions = (
        await session.scalars(
            select(NovelDocumentRevisionModel).where(
                NovelDocumentRevisionModel.project_id == project_id,
                NovelDocumentRevisionModel.status == "adopted",
            )
        )
    ).all()
    reports = (
        await session.scalars(
            select(NovelQualityReportModel).where(
                NovelQualityReportModel.project_id == project_id
            )
        )
    ).all()
    packages = (
        await session.scalars(
            select(WorkPackageModel).where(WorkPackageModel.project_id == project_id)
        )
    ).all()
    exports = (
        await session.scalars(
            select(NovelExportManifestModel).where(
                NovelExportManifestModel.project_id == project_id,
                NovelExportManifestModel.status == "succeeded",
            )
        )
    ).all()

    stages = [
        _stage(
            "ideation",
            [
                _artifact(
                    artifact_id=item.id,
                    kind="novel_story_core",
                    revision=f"generation-{item.generation}",
                    readable=bool(item.premise),
                    next_stage_consumable=bool(item.angles),
                )
                for item in core
            ],
        ),
        _stage(
            "blueprint",
            [
                _artifact(
                    artifact_id=item.id,
                    kind="novel_blueprint",
                    revision=f"v{item.version}",
                    readable=True,
                    next_stage_consumable=True,
                )
                for item in blueprints
            ],
        ),
        _stage(
            "story_map",
            (
                [
                    _artifact(
                        artifact_id=story_map.id,
                        kind="novel_story_map",
                        revision=f"v{story_map.version}",
                        readable=bool(story_map.volumes),
                        next_stage_consumable=bool(story_map.volumes),
                    )
                ]
                if story_map is not None
                else []
            ),
        ),
        _stage(
            "chapter_write",
            [
                _artifact(
                    artifact_id=item.id,
                    kind="chapter_revision",
                    revision=f"v{item.revision_number}",
                    readable=bool(item.blocks),
                    next_stage_consumable=bool(item.blocks),
                )
                for item in revisions
            ],
        ),
        _stage(
            "quality_review",
            [
                _artifact(
                    artifact_id=item.id,
                    kind="novel_quality_report",
                    revision=item.rubric_version,
                    readable=bool(item.dimensions),
                    next_stage_consumable=bool(item.summary),
                )
                for item in reports
            ],
        ),
        _stage(
            "packaging",
            [
                _artifact(
                    artifact_id=item.id,
                    kind="novel_package",
                    revision=f"v{item.version}",
                    readable=bool(item.synopsis),
                    next_stage_consumable=bool(item.title and item.cover_prompt),
                )
                for item in packages
            ],
        ),
        _stage(
            "export",
            [
                _artifact(
                    artifact_id=item.id,
                    kind="novel_export_manifest",
                    revision="v1",
                    readable=bool(item.artifact and item.artifact_sha256),
                    next_stage_consumable=bool(item.artifact and item.byte_size),
                )
                for item in exports
            ],
        ),
    ]
    decisions = [
        *(
            [
                _adoption_decision(
                    stage_id="ideation",
                    artifact_id=core[0].id,
                    adopted_count=len(core),
                )
            ]
            if core
            else []
        ),
        *(
            [
                _adoption_decision(
                    stage_id="blueprint",
                    artifact_id=blueprints[0].id,
                    adopted_count=len(blueprints),
                )
            ]
            if blueprints
            else []
        ),
        *(
            [
                _adoption_decision(
                    stage_id="story_map",
                    artifact_id=story_map.id,
                    adopted_count=1,
                )
            ]
            if story_map is not None
            else []
        ),
        *[
            _adoption_decision(
                stage_id="chapter_write",
                artifact_id=item.id,
                adopted_count=1,
            )
            for item in revisions
        ],
    ]
    return stages, decisions


async def _script_evidence(
    session: AsyncSession, project: ProjectModel
) -> tuple[list[ObservedStage], list[ObservedDecision]]:
    project_id = project.id
    core = (
        await session.scalars(
            select(ScriptStoryCoreCandidateModel).where(
                ScriptStoryCoreCandidateModel.project_id == project_id,
                ScriptStoryCoreCandidateModel.status == "adopted",
            )
        )
    ).all()
    blueprints = (
        await session.scalars(
            select(ScriptBlueprintModel).where(
                ScriptBlueprintModel.project_id == project_id,
                ScriptBlueprintModel.adopted.is_(True),
            )
        )
    ).all()
    story_map = (
        await session.scalars(
            select(ScriptStoryMapModel).where(ScriptStoryMapModel.project_id == project_id)
        )
    ).one_or_none()
    revisions = (
        await session.scalars(
            select(ScriptDocumentRevisionModel).where(
                ScriptDocumentRevisionModel.project_id == project_id,
                ScriptDocumentRevisionModel.status == "adopted",
            )
        )
    ).all()
    packages = (
        await session.scalars(
            select(WorkPackageModel).where(WorkPackageModel.project_id == project_id)
        )
    ).all()
    exports = (
        await session.scalars(
            select(ScriptExportManifestModel).where(
                ScriptExportManifestModel.project_id == project_id,
                ScriptExportManifestModel.status == "succeeded",
            )
        )
    ).all()
    quality_reports = (
        await session.scalars(
            select(CreativeDeliveryArtifactModel).where(
                CreativeDeliveryArtifactModel.project_id == project_id,
                CreativeDeliveryArtifactModel.domain == "script",
                CreativeDeliveryArtifactModel.stage == "quality_review",
                CreativeDeliveryArtifactModel.status == "succeeded",
            )
        )
    ).all()
    stages = [
        _stage(
            "ideation",
            [
                _artifact(
                    artifact_id=item.id,
                    kind="script_story_core",
                    revision=f"generation-{item.generation}",
                    readable=bool(item.concept),
                    next_stage_consumable=bool(item.angles),
                )
                for item in core
            ],
        ),
        _stage(
            "blueprint",
            [
                _artifact(
                    artifact_id=item.id,
                    kind="script_blueprint",
                    revision=f"v{item.version}",
                    readable=True,
                    next_stage_consumable=True,
                )
                for item in blueprints
            ],
        ),
        _stage(
            "story_map",
            (
                [
                    _artifact(
                        artifact_id=story_map.id,
                        kind="script_story_map",
                        revision=f"v{story_map.version}",
                        readable=bool(story_map.episodes),
                        next_stage_consumable=bool(story_map.episodes),
                    )
                ]
                if story_map is not None
                else []
            ),
        ),
        _stage(
            "scene_write",
            [
                _artifact(
                    artifact_id=item.id,
                    kind="scene_revision",
                    revision=f"v{item.revision_number}",
                    readable=bool(item.blocks),
                    next_stage_consumable=bool(item.blocks),
                )
                for item in revisions
            ],
        ),
        _stage(
            "quality_review",
            [
                _artifact(
                    artifact_id=item.id,
                    kind="script_quality_report",
                    revision=f"v{item.version}",
                    readable=bool(item.payload.get("diagnosis")),
                    next_stage_consumable=bool(item.payload.get("suggestion")),
                )
                for item in quality_reports
            ],
        ),
        _stage(
            "packaging",
            [
                _artifact(
                    artifact_id=item.id,
                    kind="script_package",
                    revision=f"v{item.version}",
                    readable=bool(item.synopsis),
                    next_stage_consumable=bool(item.title and item.cover_prompt),
                )
                for item in packages
            ],
        ),
        _stage(
            "export",
            [
                _artifact(
                    artifact_id=item.id,
                    kind="script_export_manifest",
                    revision="v1",
                    readable=bool(item.artifact and item.artifact_sha256),
                    next_stage_consumable=bool(item.artifact and item.byte_size),
                )
                for item in exports
            ],
        ),
    ]
    decisions = [
        *(
            [
                _adoption_decision(
                    stage_id="ideation",
                    artifact_id=core[0].id,
                    adopted_count=len(core),
                )
            ]
            if core
            else []
        ),
        *(
            [
                _adoption_decision(
                    stage_id="blueprint",
                    artifact_id=blueprints[0].id,
                    adopted_count=len(blueprints),
                )
            ]
            if blueprints
            else []
        ),
        *(
            [
                _adoption_decision(
                    stage_id="story_map",
                    artifact_id=story_map.id,
                    adopted_count=1,
                )
            ]
            if story_map is not None
            else []
        ),
        *[
            _adoption_decision(
                stage_id="scene_write",
                artifact_id=item.id,
                adopted_count=1,
            )
            for item in revisions
        ],
    ]
    return stages, decisions


async def _translation_evidence(
    session: AsyncSession, project: ProjectModel
) -> tuple[list[ObservedStage], list[ObservedDecision]]:
    source_project_id = str(project.direction.get("source_project_id") or "")
    source_project = await session.get(ProjectModel, source_project_id) if source_project_id else None
    revisions = (
        await session.scalars(
            select(NovelDocumentRevisionModel).where(
                NovelDocumentRevisionModel.project_id == project.id,
                NovelDocumentRevisionModel.status == "adopted",
            )
        )
    ).all()
    glossary = (
        await session.scalars(
            select(TranslationGlossaryTermModel).where(
                TranslationGlossaryTermModel.project_id == project.id,
                TranslationGlossaryTermModel.status == "confirmed",
            )
        )
    ).all()
    snapshots = (
        await session.scalars(
            select(ProjectSnapshotModel).where(
                ProjectSnapshotModel.project_id == project.id,
                ProjectSnapshotModel.medium == "translation",
            )
        )
    ).all()
    snapshot_contents = {
        item.snapshot_id: item
        for item in (
            await session.scalars(
                select(TranslationSnapshotContentModel).where(
                    TranslationSnapshotContentModel.snapshot_id.in_(
                        [snapshot.id for snapshot in snapshots]
                    )
                )
            )
        ).all()
    }
    exports = (
        await session.scalars(
            select(CreativeDeliveryArtifactModel).where(
                CreativeDeliveryArtifactModel.project_id == project.id,
                CreativeDeliveryArtifactModel.domain == "translation",
                CreativeDeliveryArtifactModel.stage == "export",
                CreativeDeliveryArtifactModel.status == "succeeded",
            )
        )
    ).all()
    stages = [
        _stage(
            "source_import",
            (
                [
                    _artifact(
                        artifact_id=source_project.id,
                        kind="translation_source",
                        revision="project",
                        readable=not bool(source_project.deleted_at),
                        next_stage_consumable=not bool(source_project.deleted_at),
                    )
                ]
                if source_project is not None
                else []
            ),
        ),
        _stage(
            "chapter_translate",
            [
                _artifact(
                    artifact_id=item.id,
                    kind="translation_revision",
                    revision=f"v{item.revision_number}",
                    readable=bool(item.blocks),
                    next_stage_consumable=bool(item.blocks),
                )
                for item in revisions
            ],
        ),
        _stage(
            "glossary_review",
            [
                _artifact(
                    artifact_id=item.id,
                    kind="translation_glossary",
                    revision="confirmed",
                    readable=bool(item.source_term and item.target_term),
                    next_stage_consumable=bool(item.target_term),
                )
                for item in glossary
            ],
        ),
        _stage(
            "history_snapshot",
            [
                _artifact(
                    artifact_id=item.id,
                    kind="translation_snapshot",
                    revision=f"v{item.version}",
                    readable=bool(
                        snapshot_contents.get(item.id)
                        and snapshot_contents[item.id].documents
                    ),
                    next_stage_consumable=bool(item.scope),
                )
                for item in snapshots
            ],
        ),
        _stage(
            "export",
            [
                _artifact(
                    artifact_id=item.id,
                    kind="translation_export_manifest",
                    revision=f"v{item.version}",
                    readable=bool(item.artifact and item.artifact_sha256),
                    next_stage_consumable=bool(item.artifact and item.byte_size),
                )
                for item in exports
            ],
        ),
    ]
    decisions = [
        *[
            _adoption_decision(
                stage_id="chapter_translate",
                artifact_id=item.id,
                adopted_count=1,
            )
            for item in revisions
        ],
        *[
            _adoption_decision(
                stage_id="glossary_review",
                artifact_id=item.id,
                adopted_count=1,
            )
            for item in glossary
        ],
    ]
    return stages, decisions


async def _recreation_evidence(
    session: AsyncSession, project: ProjectModel
) -> tuple[list[ObservedStage], list[ObservedDecision]]:
    recreation = (
        await session.scalars(
            select(CrossCulturalRecreationModel).where(
                CrossCulturalRecreationModel.project_id == project.id
            )
        )
    ).one_or_none()
    if recreation is None:
        return [], []
    artifacts = (
        await session.scalars(
            select(CrossCulturalArtifactModel).where(
                CrossCulturalArtifactModel.recreation_id == recreation.id,
                CrossCulturalArtifactModel.status == "adopted",
            )
        )
    ).all()
    by_kind = {item.kind: item for item in artifacts}
    units = (
        await session.scalars(
            select(RecreationProductionUnitModel).where(
                RecreationProductionUnitModel.recreation_id == recreation.id,
                RecreationProductionUnitModel.status == "adopted",
            )
        )
    ).all()
    delivery_artifacts = (
        await session.scalars(
            select(CreativeDeliveryArtifactModel).where(
                CreativeDeliveryArtifactModel.project_id == project.id,
                CreativeDeliveryArtifactModel.domain == "recreation",
                CreativeDeliveryArtifactModel.status == "succeeded",
            )
        )
    ).all()
    packages = [item for item in delivery_artifacts if item.stage == "packaging"]
    exports = [item for item in delivery_artifacts if item.stage == "export"]
    stage_kinds = {
        "source_analysis": (
            RecreationArtifactKind.SOURCE_STORY_MODEL,
            "recreation_source_analysis",
        ),
        "target_contract": (
            RecreationArtifactKind.TARGET_STORY_CONTRACT,
            "recreation_target_contract",
        ),
        "strategy": (
            RecreationArtifactKind.RECREATION_STRATEGY,
            "recreation_strategy",
        ),
        "sample": (RecreationArtifactKind.PILOT, "recreation_sample"),
        "blueprint": (RecreationArtifactKind.SCALE_PLAN, "recreation_blueprint"),
    }
    stages: list[ObservedStage] = []
    decisions: list[ObservedDecision] = []
    for stage_id, (artifact_kind, evidence_kind) in stage_kinds.items():
        item = by_kind.get(artifact_kind)
        stages.append(
            _stage(
                stage_id,
                (
                    [
                        _artifact(
                            artifact_id=item.id,
                            kind=evidence_kind,
                            revision=f"v{item.version}",
                            readable=bool(item.payload),
                            next_stage_consumable=bool(item.payload),
                        )
                    ]
                    if item is not None
                    else []
                ),
            )
        )
        if item is not None and stage_id != "source_analysis":
            decisions.append(
                _adoption_decision(
                    stage_id=stage_id,
                    artifact_id=item.id,
                    adopted_count=1,
                )
            )
    stages.extend(
        [
            _stage(
                "production_unit",
                [
                    _artifact(
                        artifact_id=item.id,
                        kind="recreation_unit_revision",
                        revision=f"v{item.version}",
                        readable=bool(item.payload),
                        next_stage_consumable=bool(item.payload),
                    )
                    for item in units
                ],
            ),
            _stage(
                "quality_review",
                [
                    _artifact(
                        artifact_id=item.id,
                        kind="recreation_quality_report",
                        revision=f"v{item.version}",
                        readable=bool(item.review_report),
                        next_stage_consumable=bool(item.review_report),
                    )
                    for item in units
                    if item.review_report
                ],
            ),
            _stage(
                "packaging",
                [
                    _artifact(
                        artifact_id=item.id,
                        kind="recreation_package",
                        revision=f"v{item.version}",
                        readable=bool(item.payload.get("section_count")),
                        next_stage_consumable=bool(item.payload.get("sections")),
                    )
                    for item in packages
                ],
            ),
            _stage(
                "export",
                [
                    _artifact(
                        artifact_id=item.id,
                        kind="recreation_export_manifest",
                        revision=f"v{item.version}",
                        readable=bool(item.artifact and item.artifact_sha256),
                        next_stage_consumable=bool(item.artifact and item.byte_size),
                    )
                    for item in exports
                ],
            ),
        ]
    )
    decisions.extend(
        _adoption_decision(
            stage_id="production_unit",
            artifact_id=item.id,
            adopted_count=1,
        )
        for item in units
    )
    return stages, decisions


async def collect_persisted_evidence(
    session: AsyncSession,
    *,
    scenario: GoldenScenario,
    project_id: str,
) -> FlowObservation:
    project = await session.get(ProjectModel, project_id)
    if project is None or project.deleted_at is not None:
        raise ValueError("project does not exist or has been deleted")
    expected_medium = {
        "novel": ProjectMedium.NOVEL,
        "script": ProjectMedium.SCRIPT,
        "translation": ProjectMedium.TRANSLATION,
        "recreation": ProjectMedium.NOVEL,
    }[scenario.domain]
    if project.medium != expected_medium:
        raise ValueError("project medium does not match the golden scenario")
    if (
        scenario.domain == "recreation"
        and project.workflow_kind != ProjectWorkflow.CROSS_CULTURAL_RECREATION
    ):
        raise ValueError("project workflow does not match the recreation scenario")
    latest_successful_run = (
        await session.scalars(
            select(ProjectRunModel)
            .where(
                ProjectRunModel.project_id == project_id,
                ProjectRunModel.status == RunStatus.SUCCEEDED,
            )
            .order_by(ProjectRunModel.updated_at.desc())
        )
    ).first()
    if scenario.domain == "novel":
        stages, decisions = await _novel_evidence(session, project)
    elif scenario.domain == "script":
        stages, decisions = await _script_evidence(session, project)
    elif scenario.domain == "translation":
        stages, decisions = await _translation_evidence(session, project)
    else:
        stages, decisions = await _recreation_evidence(session, project)

    expected_ids = [item.id for item in scenario.stages]
    stages_by_id = {item.id: item for item in stages}
    ordered_stages = [
        stages_by_id.get(stage_id, ObservedStage(id=stage_id, status="partial"))
        for stage_id in expected_ids
    ]
    all_complete = all(item.status == "succeeded" for item in ordered_stages)
    operation_status = (
        "succeeded"
        if latest_successful_run is not None and all_complete
        else "partial"
    )
    return FlowObservation(
        schema_version="creative-flow-observation/v1",
        scenario_id=scenario.id,
        operation_id=(
            latest_successful_run.id
            if latest_successful_run is not None
            else f"untracked-project:{project.id}"
        ),
        status=operation_status,
        stages=ordered_stages,
        decisions=decisions,
    )
