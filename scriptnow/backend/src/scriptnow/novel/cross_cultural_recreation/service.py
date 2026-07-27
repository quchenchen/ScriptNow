from sqlalchemy import func, select, update

from scriptnow.novel.cross_cultural_recreation.domain import (
    ChapterPipelineStatus,
    ChapterRevisionKind,
    CrossCulturalArtifactModel,
    CrossCulturalRecreationModel,
    RecreationArtifactKind,
    RecreationArtifactStatus,
    RecreationProductionUnitModel,
    RecreationStatus,
)
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    ProjectEventModel,
    ProjectMedium,
    ProjectModel,
    ProjectWorkflow,
)
from scriptnow.platform.run_events import RunEventType


class CrossCulturalRecreationError(RuntimeError):
    pass


class CrossCulturalRecreationService:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def create(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source_language: str,
        target_language: str,
        target_market: str,
        target_audience: str,
        distribution_context: str,
    ) -> CrossCulturalRecreationModel:
        async with self.database.session() as session:
            project = await session.get(ProjectModel, project_id)
            if (
                project is None
                or project.tenant_id != tenant_id
                or str(project.medium) != ProjectMedium.NOVEL.value
                or str(project.workflow_kind) != ProjectWorkflow.CROSS_CULTURAL_RECREATION.value
            ):
                raise CrossCulturalRecreationError("故事归化只能绑定已创建的小说归化项目")
            existing = (
                await session.scalars(
                    select(CrossCulturalRecreationModel).where(
                        CrossCulturalRecreationModel.project_id == project_id
                    )
                )
            ).one_or_none()
            if existing is not None:
                return existing
            record = CrossCulturalRecreationModel(
                tenant_id=tenant_id,
                project_id=project_id,
                source_language=source_language,
                target_language=target_language,
                target_market=target_market.strip(),
                target_audience=target_audience.strip(),
                distribution_context=distribution_context.strip(),
            )
            session.add(record)
            await session.flush()
            return record

    async def get(self, *, tenant_id: str, project_id: str) -> CrossCulturalRecreationModel:
        async with self.database.session() as session:
            record = (
                await session.scalars(
                    select(CrossCulturalRecreationModel).where(
                        CrossCulturalRecreationModel.tenant_id == tenant_id,
                        CrossCulturalRecreationModel.project_id == project_id,
                    )
                )
            ).one_or_none()
            if record is None:
                raise CrossCulturalRecreationError("故事归化项目不存在")
            return record

    async def artifacts(self, *, recreation_id: str) -> list[CrossCulturalArtifactModel]:
        async with self.database.session() as session:
            return list(
                await session.scalars(
                    select(CrossCulturalArtifactModel)
                    .where(CrossCulturalArtifactModel.recreation_id == recreation_id)
                    .order_by(
                        CrossCulturalArtifactModel.kind,
                        CrossCulturalArtifactModel.version,
                        CrossCulturalArtifactModel.ordinal,
                    )
                )
            )

    async def production_units(self, *, recreation_id: str) -> list[RecreationProductionUnitModel]:
        async with self.database.session() as session:
            return list(
                await session.scalars(
                    select(RecreationProductionUnitModel)
                    .where(RecreationProductionUnitModel.recreation_id == recreation_id)
                    .order_by(
                        RecreationProductionUnitModel.work_package_key,
                        RecreationProductionUnitModel.version,
                    )
                )
            )

    async def sync_project_events(
        self,
        *,
        tenant_id: str,
        project_id: str,
    ) -> None:
        """Backfill the durable Dock history for records created before the event bridge.

        The domain records remain the source of truth. Event keys are derived from
        immutable artifact/unit ids, so calling this method on every state load is
        idempotent and never duplicates the author's activity history.
        """
        async with self.database.session() as session:
            recreation = (
                await session.scalars(
                    select(CrossCulturalRecreationModel).where(
                        CrossCulturalRecreationModel.tenant_id == tenant_id,
                        CrossCulturalRecreationModel.project_id == project_id,
                    )
                )
            ).one_or_none()
            if recreation is None:
                raise CrossCulturalRecreationError("故事归化项目不存在")
            artifacts = list(
                await session.scalars(
                    select(CrossCulturalArtifactModel)
                    .where(CrossCulturalArtifactModel.recreation_id == recreation.id)
                    .order_by(
                        CrossCulturalArtifactModel.created_at,
                        CrossCulturalArtifactModel.version,
                        CrossCulturalArtifactModel.ordinal,
                    )
                )
            )
            units = list(
                await session.scalars(
                    select(RecreationProductionUnitModel)
                    .where(RecreationProductionUnitModel.recreation_id == recreation.id)
                    .order_by(
                        RecreationProductionUnitModel.created_at,
                        RecreationProductionUnitModel.work_package_key,
                        RecreationProductionUnitModel.version,
                    )
                )
            )
            for artifact in artifacts:
                await self._append_artifact_event(
                    session, recreation=recreation, artifact=artifact, adopted=False
                )
                if str(artifact.status) == RecreationArtifactStatus.ADOPTED:
                    await self._append_artifact_event(
                        session, recreation=recreation, artifact=artifact, adopted=True
                    )
            for unit in units:
                pipeline_status = str(unit.pipeline_status)
                if pipeline_status in {
                    ChapterPipelineStatus.DRAFTING,
                    ChapterPipelineStatus.VALIDATING,
                }:
                    await self._append_pipeline_event(
                        session,
                        recreation=recreation,
                        unit=unit,
                        action="start",
                        title="主笔正在生成章节候选",
                    )
                elif pipeline_status == ChapterPipelineStatus.FAILED:
                    await self._append_pipeline_event(
                        session,
                        recreation=recreation,
                        unit=unit,
                        action="failed",
                        title="章节生成未完成，可重新尝试",
                    )
                elif unit.payload:
                    await self._append_production_event(
                        session, recreation=recreation, unit=unit, adopted=False
                    )
                if str(unit.status) == RecreationArtifactStatus.ADOPTED:
                    await self._append_production_event(
                        session, recreation=recreation, unit=unit, adopted=True
                    )

    async def record_generation_failure(
        self,
        *,
        tenant_id: str,
        project_id: str,
        stage: str,
        run_id: str,
        message: str,
    ) -> None:
        async with self.database.session() as session:
            recreation = (
                await session.scalars(
                    select(CrossCulturalRecreationModel).where(
                        CrossCulturalRecreationModel.tenant_id == tenant_id,
                        CrossCulturalRecreationModel.project_id == project_id,
                    )
                )
            ).one_or_none()
            if recreation is None:
                return
            await self._append_project_event(
                session,
                recreation=recreation,
                event_key=f"cross-cultural:generation:{run_id}:failed",
                event_type=RunEventType.SYSTEM,
                actor_id="system",
                aggregate_type="cross_cultural_recreation",
                aggregate_id=recreation.id,
                payload={
                    "action": "cross_cultural.generation.failed",
                    "title": "本次归化创作未完成",
                    "content": message,
                    "stage": stage,
                    "status": "failed",
                    "run_id": run_id,
                    "workflow_kind": "cross_cultural_recreation",
                    "schema_version": 1,
                },
            )

    async def record_production_unit(
        self,
        *,
        recreation_id: str,
        scale_plan_artifact_id: str,
        work_package_key: str,
        payload: dict[str, object],
        idempotency_key: str,
        feedback: str | None = None,
        context_snapshot: dict[str, object] | None = None,
        revision_kind: ChapterRevisionKind = ChapterRevisionKind.AGENT,
        source_unit_id: str | None = None,
        pipeline_status: ChapterPipelineStatus = ChapterPipelineStatus.READY_FOR_DECISION,
    ) -> RecreationProductionUnitModel:
        async with self.database.session() as session:
            existing = (
                await session.scalars(
                    select(RecreationProductionUnitModel).where(
                        RecreationProductionUnitModel.recreation_id == recreation_id,
                        RecreationProductionUnitModel.work_package_key == work_package_key,
                        RecreationProductionUnitModel.idempotency_key == idempotency_key,
                    )
                )
            ).one_or_none()
            if existing is not None:
                return existing
            version = (
                await session.scalar(
                    select(func.max(RecreationProductionUnitModel.version)).where(
                        RecreationProductionUnitModel.recreation_id == recreation_id,
                        RecreationProductionUnitModel.scale_plan_artifact_id
                        == scale_plan_artifact_id,
                        RecreationProductionUnitModel.work_package_key == work_package_key,
                    )
                )
                or 0
            ) + 1
            record = RecreationProductionUnitModel(
                recreation_id=recreation_id,
                scale_plan_artifact_id=scale_plan_artifact_id,
                work_package_key=work_package_key,
                version=version,
                payload=payload,
                context_snapshot=context_snapshot or {},
                revision_kind=revision_kind,
                source_unit_id=source_unit_id,
                pipeline_status=pipeline_status,
                feedback=feedback,
                idempotency_key=idempotency_key,
            )
            session.add(record)
            recreation = await session.get(CrossCulturalRecreationModel, recreation_id)
            if recreation is None:
                raise CrossCulturalRecreationError("故事归化项目不存在")
            recreation.status = RecreationStatus.PRODUCTION_IN_PROGRESS
            await session.flush()
            if pipeline_status != ChapterPipelineStatus.DRAFTING:
                await self._append_production_event(
                    session, recreation=recreation, unit=record, adopted=False
                )
            else:
                await self._append_pipeline_event(
                    session,
                    recreation=recreation,
                    unit=record,
                    action="start",
                    title=f"开始生成章节 {work_package_key}",
                )
            return record

    async def start_production_unit(
        self,
        *,
        recreation_id: str,
        scale_plan_artifact_id: str,
        work_package_key: str,
        idempotency_key: str,
        context_snapshot: dict[str, object],
        feedback: str | None = None,
    ) -> RecreationProductionUnitModel:
        return await self.record_production_unit(
            recreation_id=recreation_id,
            scale_plan_artifact_id=scale_plan_artifact_id,
            work_package_key=work_package_key,
            payload={},
            context_snapshot=context_snapshot,
            idempotency_key=idempotency_key,
            feedback=feedback,
            pipeline_status=ChapterPipelineStatus.DRAFTING,
        )

    async def complete_production_unit(
        self,
        *,
        unit_id: str,
        payload: dict[str, object],
    ) -> RecreationProductionUnitModel:
        async with self.database.session() as session:
            unit = await session.get(RecreationProductionUnitModel, unit_id)
            if unit is None:
                raise CrossCulturalRecreationError("章节运行不存在")
            unit.pipeline_status = ChapterPipelineStatus.REVIEW_PENDING
            unit.payload = payload
            unit.failure_reason = None
            await session.flush()
            recreation = await session.get(CrossCulturalRecreationModel, unit.recreation_id)
            if recreation is None:
                raise CrossCulturalRecreationError("故事归化项目不存在")
            await self._append_production_event(
                session, recreation=recreation, unit=unit, adopted=False
            )
            return unit

    async def fail_production_unit(
        self, *, unit_id: str, reason: str
    ) -> RecreationProductionUnitModel:
        async with self.database.session() as session:
            unit = await session.get(RecreationProductionUnitModel, unit_id)
            if unit is None:
                raise CrossCulturalRecreationError("章节运行不存在")
            unit.pipeline_status = ChapterPipelineStatus.FAILED
            unit.failure_reason = reason
            recreation = await session.get(CrossCulturalRecreationModel, unit.recreation_id)
            if recreation is None:
                raise CrossCulturalRecreationError("故事归化项目不存在")
            await session.flush()
            await self._append_pipeline_event(
                session,
                recreation=recreation,
                unit=unit,
                action="failed",
                title="章节生成未完成，可重新尝试",
            )
            return unit

    async def review_production_unit(
        self,
        *,
        tenant_id: str,
        project_id: str,
        unit_id: str,
    ) -> RecreationProductionUnitModel:
        async with self.database.session() as session:
            recreation = (
                await session.scalars(
                    select(CrossCulturalRecreationModel).where(
                        CrossCulturalRecreationModel.tenant_id == tenant_id,
                        CrossCulturalRecreationModel.project_id == project_id,
                    )
                )
            ).one_or_none()
            unit = await session.get(RecreationProductionUnitModel, unit_id)
            if recreation is None or unit is None or unit.recreation_id != recreation.id:
                raise CrossCulturalRecreationError("章节候选不存在")
            if str(unit.pipeline_status) not in {
                ChapterPipelineStatus.REVIEW_PENDING,
                ChapterPipelineStatus.REVISION_REQUIRED,
            }:
                raise CrossCulturalRecreationError("当前章节版本不在待审读状态")

            payload = dict(unit.payload)
            findings: list[dict[str, str]] = []
            draft = str(payload.get("target_language_draft") or "").strip()
            if not draft:
                findings.append({"severity": "blocking", "message": "候选稿没有正文内容"})
            for field, label in (
                ("recreation_rationale", "再创作依据"),
                ("gene_trace", "故事基因追踪"),
                ("quality_self_check", "质量自检"),
            ):
                if not payload.get(field):
                    findings.append({"severity": "blocking", "message": f"缺少{label}"})
            for check in payload.get("quality_self_check", []):
                if not isinstance(check, dict):
                    continue
                result = str(check.get("result") or "").lower()
                if result in {"fail", "failed", "false", "不通过"}:
                    findings.append(
                        {
                            "severity": "blocking",
                            "message": str(check.get("gate") or "质量门禁未通过"),
                        }
                    )
            verdict = "revise" if findings else "pass"
            unit.review_report = {
                "verdict": verdict,
                "findings": findings,
                "reviewed_revision": unit.version,
                "review_basis": "chapter_contract",
            }
            unit.pipeline_status = (
                ChapterPipelineStatus.REVISION_REQUIRED
                if findings
                else ChapterPipelineStatus.READY_FOR_DECISION
            )
            await session.flush()
            await self._append_pipeline_event(
                session,
                recreation=recreation,
                unit=unit,
                action="review",
                title=("章节审读发现需要修订" if findings else "章节审读通过，可由作者决定"),
            )
            return unit

    async def revise_production_unit(
        self,
        *,
        tenant_id: str,
        project_id: str,
        unit_id: str,
        title: str,
        draft: str,
        idempotency_key: str,
    ) -> RecreationProductionUnitModel:
        async with self.database.session() as session:
            recreation = (
                await session.scalars(
                    select(CrossCulturalRecreationModel).where(
                        CrossCulturalRecreationModel.tenant_id == tenant_id,
                        CrossCulturalRecreationModel.project_id == project_id,
                    )
                )
            ).one_or_none()
            source = await session.get(RecreationProductionUnitModel, unit_id)
            if recreation is None or source is None or source.recreation_id != recreation.id:
                raise CrossCulturalRecreationError("章节候选不存在")
            if str(source.pipeline_status) in {
                ChapterPipelineStatus.DRAFTING,
                ChapterPipelineStatus.VALIDATING,
            }:
                raise CrossCulturalRecreationError("章节仍在生成，完成后才能人工修订")
        payload = {**dict(source.payload)}
        payload["title"] = title.strip()
        payload["target_language_draft"] = draft.strip()
        return await self.record_production_unit(
            recreation_id=source.recreation_id,
            scale_plan_artifact_id=source.scale_plan_artifact_id,
            work_package_key=source.work_package_key,
            payload=payload,
            context_snapshot=dict(source.context_snapshot),
            idempotency_key=idempotency_key,
            feedback="作者人工修订",
            revision_kind=ChapterRevisionKind.MANUAL,
            source_unit_id=source.id,
            pipeline_status=ChapterPipelineStatus.REVIEW_PENDING,
        )

    async def adopt_production_unit(
        self,
        *,
        tenant_id: str,
        project_id: str,
        unit_id: str,
    ) -> RecreationProductionUnitModel:
        async with self.database.session() as session:
            recreation = (
                await session.scalars(
                    select(CrossCulturalRecreationModel).where(
                        CrossCulturalRecreationModel.tenant_id == tenant_id,
                        CrossCulturalRecreationModel.project_id == project_id,
                    )
                )
            ).one_or_none()
            unit = await session.get(RecreationProductionUnitModel, unit_id)
            if recreation is None or unit is None or unit.recreation_id != recreation.id:
                raise CrossCulturalRecreationError("再创作工作包候选不存在")
            plan = await session.get(CrossCulturalArtifactModel, unit.scale_plan_artifact_id)
            if (
                plan is None
                or str(plan.kind) != RecreationArtifactKind.SCALE_PLAN
                or str(plan.status) != RecreationArtifactStatus.ADOPTED
            ):
                raise CrossCulturalRecreationError("工作包候选不属于当前已确认的整书方案")
            if str(unit.pipeline_status) != ChapterPipelineStatus.READY_FOR_DECISION:
                raise CrossCulturalRecreationError("请先完成章节审读，再决定是否采纳")
            package_keys = {
                str(item.get("order"))
                for item in (plan.payload or {}).get("work_packages", [])
                if isinstance(item, dict) and item.get("order") is not None
            }
            if unit.work_package_key not in package_keys:
                raise CrossCulturalRecreationError("工作包候选不属于当前已确认的整书方案")
            await session.execute(
                update(RecreationProductionUnitModel)
                .where(
                    RecreationProductionUnitModel.recreation_id == recreation.id,
                    RecreationProductionUnitModel.scale_plan_artifact_id
                    == unit.scale_plan_artifact_id,
                    RecreationProductionUnitModel.work_package_key == unit.work_package_key,
                    RecreationProductionUnitModel.status == RecreationArtifactStatus.ADOPTED,
                )
                .values(status=RecreationArtifactStatus.SUPERSEDED)
            )
            unit.status = RecreationArtifactStatus.ADOPTED
            unit.pipeline_status = ChapterPipelineStatus.ADOPTED
            adopted_keys = set(
                await session.scalars(
                    select(RecreationProductionUnitModel.work_package_key).where(
                        RecreationProductionUnitModel.recreation_id == recreation.id,
                        RecreationProductionUnitModel.scale_plan_artifact_id
                        == unit.scale_plan_artifact_id,
                        RecreationProductionUnitModel.status == RecreationArtifactStatus.ADOPTED,
                    )
                )
            )
            adopted_keys.add(unit.work_package_key)
            recreation.status = (
                RecreationStatus.PRODUCTION_COMPLETE
                if package_keys and package_keys <= adopted_keys
                else RecreationStatus.PRODUCTION_IN_PROGRESS
            )
            await session.flush()
            await self._append_production_event(
                session, recreation=recreation, unit=unit, adopted=True
            )
            return unit

    async def record_artifacts(
        self,
        *,
        recreation_id: str,
        kind: RecreationArtifactKind,
        payloads: tuple[dict[str, object], ...],
        idempotency_key: str,
        feedback: str | None = None,
        adopt: bool = False,
    ) -> tuple[CrossCulturalArtifactModel, ...]:
        async with self.database.session() as session:
            existing = list(
                await session.scalars(
                    select(CrossCulturalArtifactModel)
                    .where(
                        CrossCulturalArtifactModel.recreation_id == recreation_id,
                        CrossCulturalArtifactModel.kind == kind,
                        CrossCulturalArtifactModel.idempotency_key == idempotency_key,
                    )
                    .order_by(CrossCulturalArtifactModel.ordinal)
                )
            )
            if existing:
                return tuple(existing)
            version = (
                await session.scalar(
                    select(func.max(CrossCulturalArtifactModel.version)).where(
                        CrossCulturalArtifactModel.recreation_id == recreation_id,
                        CrossCulturalArtifactModel.kind == kind,
                    )
                )
                or 0
            ) + 1
            if adopt:
                await session.execute(
                    update(CrossCulturalArtifactModel)
                    .where(
                        CrossCulturalArtifactModel.recreation_id == recreation_id,
                        CrossCulturalArtifactModel.kind == kind,
                        CrossCulturalArtifactModel.status == RecreationArtifactStatus.ADOPTED,
                    )
                    .values(status=RecreationArtifactStatus.SUPERSEDED)
                )
            records = tuple(
                CrossCulturalArtifactModel(
                    recreation_id=recreation_id,
                    kind=kind,
                    version=version,
                    ordinal=ordinal,
                    status=(
                        RecreationArtifactStatus.ADOPTED
                        if adopt
                        else RecreationArtifactStatus.CANDIDATE
                    ),
                    payload=payload,
                    feedback=feedback,
                    idempotency_key=idempotency_key,
                )
                for ordinal, payload in enumerate(payloads, start=1)
            )
            session.add_all(records)
            recreation = await session.get(CrossCulturalRecreationModel, recreation_id)
            if recreation is None:
                raise CrossCulturalRecreationError("故事归化项目不存在")
            recreation.status = self._next_status(kind, adopt=adopt)
            await session.flush()
            for record in records:
                await self._append_artifact_event(
                    session, recreation=recreation, artifact=record, adopted=False
                )
                if adopt:
                    await self._append_artifact_event(
                        session, recreation=recreation, artifact=record, adopted=True
                    )
            return records

    async def adopt(
        self,
        *,
        tenant_id: str,
        project_id: str,
        artifact_id: str,
    ) -> CrossCulturalArtifactModel:
        async with self.database.session() as session:
            recreation = (
                await session.scalars(
                    select(CrossCulturalRecreationModel).where(
                        CrossCulturalRecreationModel.tenant_id == tenant_id,
                        CrossCulturalRecreationModel.project_id == project_id,
                    )
                )
            ).one_or_none()
            artifact = await session.get(CrossCulturalArtifactModel, artifact_id)
            if recreation is None or artifact is None or artifact.recreation_id != recreation.id:
                raise CrossCulturalRecreationError("候选不存在")
            await session.execute(
                update(CrossCulturalArtifactModel)
                .where(
                    CrossCulturalArtifactModel.recreation_id == recreation.id,
                    CrossCulturalArtifactModel.kind == artifact.kind,
                    CrossCulturalArtifactModel.status == RecreationArtifactStatus.ADOPTED,
                )
                .values(status=RecreationArtifactStatus.SUPERSEDED)
            )
            artifact.status = RecreationArtifactStatus.ADOPTED
            recreation.status = self._next_status(
                RecreationArtifactKind(str(artifact.kind)), adopt=True
            )
            await session.flush()
            await self._append_artifact_event(
                session, recreation=recreation, artifact=artifact, adopted=True
            )
            return artifact

    @classmethod
    async def _append_artifact_event(
        cls,
        session,
        *,
        recreation: CrossCulturalRecreationModel,
        artifact: CrossCulturalArtifactModel,
        adopted: bool,
    ) -> None:
        kind = RecreationArtifactKind(str(artifact.kind))
        labels = {
            RecreationArtifactKind.SOURCE_STORY_MODEL: "源作品分析",
            RecreationArtifactKind.TARGET_STORY_CONTRACT: "目标故事契约",
            RecreationArtifactKind.RECREATION_STRATEGY: "归化策略",
            RecreationArtifactKind.PILOT: "代表性试写",
            RecreationArtifactKind.SCALE_PLAN: "整书扩展方案",
        }
        roles = {
            RecreationArtifactKind.SOURCE_STORY_MODEL: "director",
            RecreationArtifactKind.TARGET_STORY_CONTRACT: "director",
            RecreationArtifactKind.RECREATION_STRATEGY: "architect",
            RecreationArtifactKind.PILOT: "writer",
            RecreationArtifactKind.SCALE_PLAN: "architect",
        }
        label = labels[kind]
        payload: dict[str, object] = {
            "action": (
                f"cross_cultural.{kind.value}.adopt"
                if adopted
                else f"cross_cultural.{kind.value}.propose"
            ),
            "title": f"{'已确认' if adopted else '已生成'}{label}",
            "content": cls._artifact_summary(kind, dict(artifact.payload)),
            "role": roles[kind],
            "version": artifact.version,
            "ordinal": artifact.ordinal,
            "artifact_id": artifact.id,
            "workflow_kind": "cross_cultural_recreation",
            "schema_version": 1,
        }
        await cls._append_project_event(
            session,
            recreation=recreation,
            event_key=(
                f"cross-cultural:artifact:{artifact.id}:" f"{'adopted' if adopted else 'generated'}"
            ),
            event_type=(RunEventType.DECISION if adopted else RunEventType.CONVERSATION),
            actor_id=roles[kind],
            aggregate_type="cross_cultural_artifact",
            aggregate_id=artifact.id,
            payload=payload,
        )

    @classmethod
    async def _append_production_event(
        cls,
        session,
        *,
        recreation: CrossCulturalRecreationModel,
        unit: RecreationProductionUnitModel,
        adopted: bool,
    ) -> None:
        title = str(unit.payload.get("title") or f"工作包 {unit.work_package_key}")
        is_manual_revision = str(unit.revision_kind) == ChapterRevisionKind.MANUAL and not adopted
        await cls._append_project_event(
            session,
            recreation=recreation,
            event_key=(
                f"cross-cultural:production:{unit.id}:" f"{'adopted' if adopted else 'generated'}"
            ),
            event_type=(RunEventType.DECISION if adopted else RunEventType.CONVERSATION),
            actor_id="writer",
            aggregate_type="cross_cultural_production_unit",
            aggregate_id=unit.id,
            payload={
                "action": (
                    "cross_cultural.production.adopt"
                    if adopted
                    else (
                        "cross_cultural.production.manual_revision"
                        if is_manual_revision
                        else "cross_cultural.production.propose"
                    )
                ),
                "title": (
                    f"已确认正文单元：{title}"
                    if adopted
                    else (
                        f"人工修订版本已保存：{title}"
                        if is_manual_revision
                        else f"正文候选已生成：{title}"
                    )
                ),
                "content": (
                    f"工作包 {unit.work_package_key} · 版本 {unit.version}"
                    + (f"\n作者反馈：{unit.feedback}" if unit.feedback else "")
                ),
                "role": "writer",
                "version": unit.version,
                "work_package_key": unit.work_package_key,
                "production_unit_id": unit.id,
                "workflow_kind": "cross_cultural_recreation",
                "schema_version": 1,
            },
        )

    @classmethod
    async def _append_pipeline_event(
        cls,
        session,
        *,
        recreation: CrossCulturalRecreationModel,
        unit: RecreationProductionUnitModel,
        action: str,
        title: str,
    ) -> None:
        await cls._append_project_event(
            session,
            recreation=recreation,
            event_key=f"cross-cultural:production:{unit.id}:{action}",
            event_type=RunEventType.SYSTEM,
            actor_id="reviewer" if action == "review" else "writer",
            aggregate_type="cross_cultural_production_unit",
            aggregate_id=unit.id,
            payload={
                "action": f"cross_cultural.production.{action}",
                "title": title,
                "content": f"章节 {unit.work_package_key} · 版本 {unit.version}",
                "role": "reviewer" if action == "review" else "writer",
                "version": unit.version,
                "work_package_key": unit.work_package_key,
                "production_unit_id": unit.id,
                "pipeline_status": str(unit.pipeline_status),
                "workflow_kind": "cross_cultural_recreation",
                "schema_version": 1,
            },
        )

    @staticmethod
    def _artifact_summary(kind: RecreationArtifactKind, payload: dict[str, object]) -> str:
        if kind == RecreationArtifactKind.SOURCE_STORY_MODEL:
            return str(payload.get("story_summary") or "已完成源作品叙事功能分析")
        if kind == RecreationArtifactKind.TARGET_STORY_CONTRACT:
            return "已明确目标读者、市场、文化距离与不可放弃的故事要素"
        if kind == RecreationArtifactKind.RECREATION_STRATEGY:
            return str(
                payload.get("title") or payload.get("target_premise") or "已形成归化策略候选"
            )
        if kind == RecreationArtifactKind.PILOT:
            return str(payload.get("unit_title") or payload.get("rationale") or "已形成代表性试写")
        return "已形成可逐单元推进、确认与追溯的整书扩展方案"

    @staticmethod
    async def _append_project_event(
        session,
        *,
        recreation: CrossCulturalRecreationModel,
        event_key: str,
        event_type: RunEventType,
        actor_id: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, object],
    ) -> None:
        stream_key = f"project:{recreation.project_id}"
        existing = (
            await session.scalars(
                select(ProjectEventModel).where(
                    ProjectEventModel.stream_key == stream_key,
                    ProjectEventModel.event_key == event_key,
                )
            )
        ).one_or_none()
        if existing is not None:
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
        session.add(
            ProjectEventModel(
                tenant_id=recreation.tenant_id,
                project_id=recreation.project_id,
                run_id=None,
                stream_key=stream_key,
                sequence=sequence,
                event_key=event_key,
                event_type=event_type,
                schema_version=1,
                actor={"type": "agent", "id": actor_id},
                aggregate={"type": aggregate_type, "id": aggregate_id},
                causation_id=aggregate_id,
                correlation_id=recreation.id,
                idempotency_key=event_key,
                payload=payload,
            )
        )

    @staticmethod
    def _next_status(kind: RecreationArtifactKind, *, adopt: bool) -> RecreationStatus:
        if kind == RecreationArtifactKind.SOURCE_STORY_MODEL:
            return RecreationStatus.SOURCE_ANALYZED
        if kind == RecreationArtifactKind.TARGET_STORY_CONTRACT:
            return RecreationStatus.TARGET_CONFIRMED
        if kind == RecreationArtifactKind.RECREATION_STRATEGY:
            return RecreationStatus.STRATEGY_ADOPTED if adopt else RecreationStatus.STRATEGY_READY
        if kind == RecreationArtifactKind.PILOT:
            return RecreationStatus.PILOT_ADOPTED if adopt else RecreationStatus.PILOT_READY
        return RecreationStatus.SCALE_PLAN_ADOPTED if adopt else RecreationStatus.SCALE_PLAN_READY
