import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import func, select

from scriptflow_v7.novel.domain import NovelDocumentRevisionModel, NovelQualityReportModel
from scriptflow_v7.platform.config import Settings
from scriptflow_v7.platform.database import Database
from scriptflow_v7.platform.models import (
    DistillationDecision,
    ProjectMedium,
    ProjectModel,
    RagChunkModel,
    SourceDistillationModel,
    SourceProfileModel,
    WorkspaceFileModel,
)
from scriptflow_v7.platform.skills import SkillCatalog


@dataclass(frozen=True, slots=True)
class CompletionGate:
    key: str
    passed: bool
    evidence: str


def completion_status(gates: list[CompletionGate]) -> str:
    return "complete" if gates and all(item.passed for item in gates) else "incomplete"


async def audit_project(database: Database, project_id: str) -> dict[str, object]:
    skills_root = Path(__file__).parents[3] / "skills"
    catalog = SkillCatalog(skills_root)
    optional_novel_skills = [item for item in catalog.for_domain("novel") if item.roles]
    unadmitted = [item.name for item in optional_novel_skills if item.admission_status != "admitted"]

    async with database.session() as session:
        project = await session.get(ProjectModel, project_id)
        if project is None or project.medium != ProjectMedium.NOVEL:
            raise RuntimeError("target Novel project does not exist")
        files = list(
            await session.scalars(
                select(WorkspaceFileModel).where(WorkspaceFileModel.project_id == project_id)
            )
        )
        chunk_count = int(
            await session.scalar(
                select(func.count(RagChunkModel.id)).where(RagChunkModel.project_id == project_id)
            )
            or 0
        )
        distillations = list(
            await session.scalars(
                select(SourceDistillationModel).where(
                    SourceDistillationModel.project_id == project_id
                )
            )
        )
        profiles = list(
            await session.scalars(
                select(SourceProfileModel)
                .where(SourceProfileModel.project_id == project_id)
                .order_by(SourceProfileModel.version.desc())
            )
        )
        revisions = list(
            await session.scalars(
                select(NovelDocumentRevisionModel)
                .where(
                    NovelDocumentRevisionModel.project_id == project_id,
                    NovelDocumentRevisionModel.chapter_id == "chapter-1",
                    NovelDocumentRevisionModel.status.in_(("candidate", "adopted")),
                )
                .order_by(NovelDocumentRevisionModel.revision_number.desc())
            )
        )
        reports = list(
            await session.scalars(
                select(NovelQualityReportModel)
                .where(
                    NovelQualityReportModel.project_id == project_id,
                    NovelQualityReportModel.chapter_id == "chapter-1",
                )
                .order_by(NovelQualityReportModel.created_at.desc())
            )
        )

    complete_contract_runs = [
        item
        for item in distillations
        if "local-contract" in item.idempotency_key
        and int(item.coverage.get("processed_chunks") or 0)
        == int(item.coverage.get("total_chunks") or -1)
        and item.pass_key == "human_decision"
    ]
    complete_real_runs = [
        item
        for item in distillations
        if "real" in item.idempotency_key
        and int(item.coverage.get("processed_chunks") or 0)
        == int(item.coverage.get("total_chunks") or -1)
        and item.pass_key == "human_decision"
    ]
    approved = next(
        (item for item in profiles if item.decision == DistillationDecision.APPROVED), None
    )
    latest_revision = revisions[0] if revisions else None
    latest_report = next(
        (item for item in reports if latest_revision and item.revision_id == latest_revision.id), None
    )
    prose_size = (
        sum(len(str(item.get("text") or "")) for item in latest_revision.blocks)
        if latest_revision
        else 0
    )
    regression_path = skills_root / "evaluations" / "defect-regressions.json"
    regression_ids: set[str] = set()
    if regression_path.exists():
        raw = json.loads(regression_path.read_text(encoding="utf-8"))
        regression_ids = {
            str(item.get("quality_report_id"))
            for item in list(raw.get("cases") or [])
            if isinstance(item, dict)
        }

    gates = [
        CompletionGate(
            "skill_admission",
            bool(optional_novel_skills) and not unadmitted,
            f"{len(optional_novel_skills)} admitted; missing={unadmitted}",
        ),
        CompletionGate(
            "source_index",
            bool(files) and all(item.status == "ready" for item in files) and chunk_count > 0,
            f"ready_files={sum(item.status == 'ready' for item in files)}/{len(files)}; chunks={chunk_count}",
        ),
        CompletionGate(
            "rag_loop_contract",
            bool(complete_contract_runs),
            f"complete_contract_runs={[item.id for item in complete_contract_runs]}",
        ),
        CompletionGate(
            "real_model_distillation",
            bool(complete_real_runs),
            f"complete_real_runs={[item.id for item in complete_real_runs]}",
        ),
        CompletionGate(
            "approved_source_profile",
            approved is not None,
            f"approved_profile={approved.id if approved else None}",
        ),
        CompletionGate(
            "chapter_one_effective_revision",
            latest_revision is not None and prose_size >= 1_000,
            (
                f"revision={latest_revision.id if latest_revision else None}; "
                f"revision_number={latest_revision.revision_number if latest_revision else None}; "
                f"characters={prose_size}"
            ),
        ),
        CompletionGate(
            "chapter_one_quality",
            bool(
                latest_report
                and latest_report.overall_status == "ready"
                and approved
                and latest_report.source_profile_version == str(approved.version)
            ),
            (
                f"report={latest_report.id if latest_report else None}; "
                f"status={latest_report.overall_status if latest_report else None}; "
                f"source_profile_version={latest_report.source_profile_version if latest_report else None}"
            ),
        ),
        CompletionGate(
            "defect_regression_feedback",
            bool(latest_report and latest_report.id in regression_ids),
            f"quality_report_in_regression_set={bool(latest_report and latest_report.id in regression_ids)}",
        ),
    ]
    return {
        "project_id": project.id,
        "project_name": project.name,
        "status": completion_status(gates),
        "gates": [asdict(item) for item in gates],
    }


async def _main(project_id: str, database_url: str) -> int:
    database = Database.create(database_url)
    try:
        report = await audit_project(database, project_id)
    finally:
        await database.dispose()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "complete" else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit the Novel Skill end-to-end goal")
    parser.add_argument("project_id")
    parser.add_argument("--database-url", default=Settings().database_url)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_main(args.project_id, args.database_url)))


if __name__ == "__main__":
    main()
