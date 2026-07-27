import json
from dataclasses import asdict

from sqlalchemy import and_, func, or_, select

from scriptnow.novel.domain import NovelDocumentRevisionModel
from scriptnow.novel.project import NovelPlanModel, NovelStoryMapModel
from scriptnow.platform.agent_runtime import AgentRuntime, AgentRuntimeError, AgentRuntimeResult
from scriptnow.platform.billing import BillingService
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    AgentStateModel,
    MemoryAuditModel,
    MemoryEntryModel,
    ProjectEventModel,
    ProjectModel,
    ProjectRunModel,
    RunStatus,
    RunStreamEventModel,
    TenantModel,
    UsageReservationModel,
    new_id,
)
from scriptnow.platform.run_coordinator import RunCoordinator
from scriptnow.platform.run_events import PersistentRunEventLog, RunEventType
from scriptnow.review.domain import FindingStatus, ReviewFindingModel
from scriptnow.script.domain import ScriptDocumentRevisionModel
from scriptnow.script.project import ScriptPlanModel, ScriptStoryMapModel


class DockError(RuntimeError):
    pass


class DockService:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings
        self.runs = RunCoordinator(database)
        self.events = PersistentRunEventLog(database)
        self.billing = BillingService(
            database, enforce_limits=settings.enforce_agent_budget
        )
        self.runtime = AgentRuntime(database, settings)

    async def project_events(
        self, *, tenant_id: str, project_id: str, after_id: str | None, types: set[str]
    ) -> list[dict[str, object]]:
        async with self.database.session() as session:
            await self._project(session, tenant_id, project_id)
            query = select(ProjectEventModel).where(ProjectEventModel.project_id == project_id)
            if after_id:
                cursor = await session.get(ProjectEventModel, after_id)
                if cursor is None or cursor.project_id != project_id:
                    raise DockError("invalid project event cursor")
                query = query.where(
                    or_(
                        ProjectEventModel.occurred_at > cursor.occurred_at,
                        and_(
                            ProjectEventModel.occurred_at == cursor.occurred_at,
                            ProjectEventModel.id > cursor.id,
                        ),
                    )
                )
            records = list(
                await session.scalars(
                    query.order_by(ProjectEventModel.occurred_at, ProjectEventModel.id)
                )
            )
        views = [self._view(item) for item in records]
        if types:
            views = [item for item in views if str(item["type"]) in types]
        return self._aggregate_nodes(views)

    async def send_message(
        self,
        *,
        tenant_id: str,
        project_id: str,
        actor_id: str,
        role: str,
        content: str,
        quote: dict[str, object] | None,
        focus: dict[str, str] | None,
        idempotency_key: str,
        requires_confirmation: bool,
    ) -> dict[str, object]:
        run = await self.runs.enqueue(
            tenant_id=tenant_id, project_id=project_id, idempotency_key=idempotency_key
        )
        if run.status != RunStatus.QUEUED:
            return asdict(run)
        async with self.database.session() as session:
            tenant = await session.get(TenantModel, tenant_id)
            assert tenant is not None
        reservation = await self.billing.reserve(
            tenant_id=tenant_id,
            run_id=run.id,
            idempotency_key=f"dock:{idempotency_key}",
            tier=tenant.tier,
            max_tokens=self.settings.dock_reserved_tokens,
        )
        await self.runs.transition(tenant_id=tenant_id, run_id=run.id, target=RunStatus.RUNNING)
        await self._project_event(
            tenant_id=tenant_id,
            project_id=project_id,
            event_key=f"dock:user:{idempotency_key}",
            type=RunEventType.CONVERSATION,
            payload={
                "actor": "user",
                "actor_id": actor_id,
                "role": role,
                "title": content[:80],
                "content": content,
                "quote": quote,
                "schema_version": 1,
                "idempotency_key": idempotency_key,
            },
        )
        await self._compress_if_needed(
            tenant_id=tenant_id,
            project_id=project_id,
            role=role,
            actor_id=actor_id,
        )
        context_snapshot = await self._context_snapshot(
            tenant_id=tenant_id,
            project_id=project_id,
            role=role,
            focus_unit_id=str(focus.get("unit_id")) if focus and focus.get("unit_id") else None,
        )
        runtime_result: AgentRuntimeResult | None = None
        runtime_status = await self.runtime.status(tenant_id=tenant_id, project_id=project_id)
        role_status = dict(dict(runtime_status["roles"])[role])
        if role_status["connected"]:
            try:
                runtime_result = await self.runtime.generate(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    role=role,
                    content=content,
                    context_snapshot=context_snapshot,
                )
            except Exception:
                await self.billing.release(reservation.id)
                await self.runs.transition(
                    tenant_id=tenant_id, run_id=run.id, target=RunStatus.FAILED
                )
                raise
        response_text = (
            runtime_result.text if runtime_result else self._context_response(context_snapshot)
        )
        runtime_label = runtime_result.runtime if runtime_result else "deterministic"
        await self._persist_context_state(
            tenant_id=tenant_id,
            project_id=project_id,
            role=role,
            context_snapshot=context_snapshot,
        )
        fixtures = (
            (
                "thinking:start",
                RunEventType.SYSTEM,
                {
                    "block": "thinking",
                    "phase": "start",
                    "title": "理解用户任务",
                    "runtime": runtime_label,
                },
            ),
            (
                "thinking:delta",
                RunEventType.SYSTEM,
                {
                    "block": "thinking",
                    "phase": "delta",
                    "delta": f"识别任务：{content[:120]}",
                    "runtime": runtime_label,
                },
            ),
            ("thinking:end", RunEventType.SYSTEM, {"block": "thinking", "phase": "end"}),
            (
                "tool:start",
                RunEventType.NODE,
                {
                    "block": "tool",
                    "phase": "start",
                    "title": "读取真实项目状态",
                    "group_key": "context-read",
                    "runtime": runtime_label,
                },
            ),
            (
                "tool:end",
                RunEventType.NODE,
                {
                    "block": "tool",
                    "phase": "end",
                    "title": "读取真实项目状态",
                    "group_key": "context-read",
                    "duration_ms": 0,
                    "runtime": runtime_label,
                },
            ),
            (
                "data:end",
                RunEventType.NODE,
                {
                    "block": "data",
                    "phase": "end",
                    "title": "上下文包已生成",
                    "group_key": "context-pack",
                    "data": context_snapshot,
                    "runtime": runtime_label,
                },
            ),
            ("text:start", RunEventType.CONVERSATION, {"block": "text", "phase": "start"}),
            (
                "text:delta",
                RunEventType.CONVERSATION,
                {
                    "block": "text",
                    "phase": "delta",
                    "delta": response_text,
                    "runtime": runtime_label,
                },
            ),
            ("text:end", RunEventType.CONVERSATION, {"block": "text", "phase": "end"}),
        )
        for key, event_type, payload in fixtures:
            await self.events.append(
                tenant_id=tenant_id,
                run_id=run.id,
                event_key=f"dock:{key}",
                type=event_type,
                payload=payload,
                correlation_id=run.id,
            )
        await self._project_event(
            tenant_id=tenant_id,
            project_id=project_id,
            event_key=f"dock:node:{idempotency_key}",
            type=RunEventType.NODE,
            payload={
                "title": "读取项目上下文",
                "group_key": "context-read",
                "count": 2,
                "run_id": run.id,
                "schema_version": 1,
            },
        )
        if requires_confirmation:
            waiting = await self.runs.transition(
                tenant_id=tenant_id,
                run_id=run.id,
                target=RunStatus.WAITING,
                waiting_reason="tool_confirmation",
            )
            await self.events.append(
                tenant_id=tenant_id,
                run_id=run.id,
                event_key="dock:confirm-required",
                type=RunEventType.SYSTEM,
                payload={
                    "title": "需要确认工具调用",
                    "confirmation": {"tool": "workspace.write", "risk": "writes_project_workspace"},
                },
                correlation_id=run.id,
            )
            await self._project_event(
                tenant_id=tenant_id,
                project_id=project_id,
                event_key=f"dock:waiting:{idempotency_key}",
                type=RunEventType.SYSTEM,
                payload={
                    "title": "需要确认工具调用",
                    "run_id": run.id,
                    "confirmation": {"tool": "workspace.write", "risk": "writes_project_workspace"},
                    "schema_version": 1,
                },
            )
            return asdict(waiting)
        await self._complete(
            tenant_id,
            run.id,
            role,
            reservation.id,
            response_text=response_text,
            runtime_result=runtime_result,
        )
        return asdict(await self._run(tenant_id, run.id))

    async def confirm(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        approved: bool,
        idempotency_key: str,
        role: str,
    ) -> dict[str, object]:
        run = await self._run(tenant_id, run_id)
        if run.project_id != project_id:
            raise DockError("run is outside project scope")
        async with self.database.session() as session:
            existing = (
                await session.scalars(
                    select(RunStreamEventModel).where(
                        RunStreamEventModel.run_id == run_id,
                        RunStreamEventModel.event_key == f"dock:confirm:{idempotency_key}",
                    )
                )
            ).one_or_none()
            reservation = (
                await session.scalars(
                    select(UsageReservationModel).where(UsageReservationModel.run_id == run_id)
                )
            ).one()
        if existing:
            return asdict(await self._run(tenant_id, run_id))
        if run.status != RunStatus.WAITING:
            raise DockError("run is not waiting for confirmation")
        await self.events.append(
            tenant_id=tenant_id,
            run_id=run_id,
            event_key=f"dock:confirm:{idempotency_key}",
            type=RunEventType.DECISION,
            payload={
                "title": "用户确认工具调用",
                "approved": approved,
                "idempotency_key": idempotency_key,
            },
            correlation_id=run_id,
        )
        await self._project_event(
            tenant_id=tenant_id,
            project_id=project_id,
            event_key=f"dock:confirm:{idempotency_key}",
            type=RunEventType.DECISION,
            payload={
                "title": "用户确认工具调用",
                "approved": approved,
                "run_id": run_id,
                "schema_version": 1,
                "idempotency_key": idempotency_key,
            },
        )
        if not approved:
            await self.billing.release(reservation.id)
            cancelled = await self.runs.transition(
                tenant_id=tenant_id, run_id=run_id, target=RunStatus.CANCELLED
            )
            return asdict(cancelled)
        await self.runs.transition(tenant_id=tenant_id, run_id=run_id, target=RunStatus.RUNNING)
        context_snapshot = await self._context_snapshot(
            tenant_id=tenant_id, project_id=project_id, role=role
        )
        await self._complete(
            tenant_id,
            run_id,
            role,
            reservation.id,
            response_text=self._context_response(context_snapshot),
        )
        return asdict(await self._run(tenant_id, run_id))

    async def cancel(self, *, tenant_id: str, project_id: str, run_id: str) -> dict[str, object]:
        run = await self._run(tenant_id, run_id)
        if run.project_id != project_id or run.status not in {
            RunStatus.QUEUED,
            RunStatus.RUNNING,
            RunStatus.WAITING,
        }:
            raise DockError("run cannot be cancelled")
        async with self.database.session() as session:
            reservation = (
                await session.scalars(
                    select(UsageReservationModel).where(UsageReservationModel.run_id == run_id)
                )
            ).one_or_none()
        if reservation:
            await self.billing.release(reservation.id)
        cancelled = await self.runs.transition(
            tenant_id=tenant_id, run_id=run_id, target=RunStatus.CANCELLED
        )
        await self._project_event(
            tenant_id=tenant_id,
            project_id=project_id,
            event_key=f"dock:cancelled:{run_id}",
            type=RunEventType.SYSTEM,
            payload={
                "title": "运行已由用户取消",
                "status": "cancelled",
                "run_id": run_id,
                "schema_version": 1,
            },
        )
        return asdict(cancelled)

    async def project_runs(self, *, tenant_id: str, project_id: str) -> list[dict[str, object]]:
        async with self.database.session() as session:
            await self._project(session, tenant_id, project_id)
            records = list(
                await session.scalars(
                    select(ProjectRunModel)
                    .where(ProjectRunModel.project_id == project_id)
                    .order_by(ProjectRunModel.created_at.desc())
                    .limit(20)
                )
            )
        return [
            {
                "id": item.id,
                "status": str(item.status),
                "waiting_reason": item.waiting_reason,
                "state_version": item.state_version,
                "created_at": item.created_at,
            }
            for item in records
        ]

    async def transparency(
        self, *, tenant_id: str, project_id: str, role: str
    ) -> dict[str, object]:
        async with self.database.session() as session:
            await self._project(session, tenant_id, project_id)
            state = (
                await session.scalars(
                    select(AgentStateModel).where(
                        AgentStateModel.tenant_id == tenant_id,
                        AgentStateModel.project_id == project_id,
                        AgentStateModel.role_key == role,
                    )
                )
            ).one_or_none()
            memories = int(
                await session.scalar(
                    select(func.count(MemoryEntryModel.id)).where(
                        MemoryEntryModel.tenant_id == tenant_id,
                        MemoryEntryModel.project_id == project_id,
                        MemoryEntryModel.role_key == role,
                    )
                )
                or 0
            )
        used = state.context_tokens if state and state.context_tokens is not None else 0
        limit = state.context_limit if state and state.context_limit else 0
        return {
            "context_tokens": used,
            "context_limit": limit,
            "context_percent": round(used / limit * 100, 1) if state and limit else None,
            "memory_entries": memories,
            "role": role,
            "connected": state is not None,
        }

    async def runtime_status(self, *, tenant_id: str, project_id: str) -> dict[str, object]:
        try:
            return await self.runtime.status(tenant_id=tenant_id, project_id=project_id)
        except AgentRuntimeError as error:
            raise DockError(str(error)) from error

    async def _context_snapshot(
        self, *, tenant_id: str, project_id: str, role: str, focus_unit_id: str | None = None
    ) -> dict[str, object]:
        """Build the Dock context from persisted project facts, never fixtures."""
        async with self.database.session() as session:
            project = await self._project(session, tenant_id, project_id)
            if str(project.medium) == "novel":
                plan = (
                    await session.scalars(
                        select(NovelPlanModel).where(NovelPlanModel.project_id == project_id)
                    )
                ).one()
                story_map = (
                    await session.scalars(
                        select(NovelStoryMapModel).where(
                            NovelStoryMapModel.project_id == project_id
                        )
                    )
                ).one()
                units = [
                    chapter
                    for volume in story_map.volumes
                    for chapter in volume.get("chapters", [])
                ]
                adopted_units = int(
                    await session.scalar(
                        select(func.count(NovelDocumentRevisionModel.id)).where(
                            NovelDocumentRevisionModel.project_id == project_id,
                            NovelDocumentRevisionModel.status == "adopted",
                        )
                    )
                    or 0
                )
                focused_document = (
                    (
                        await session.scalars(
                            select(NovelDocumentRevisionModel).where(
                                NovelDocumentRevisionModel.project_id == project_id,
                                NovelDocumentRevisionModel.chapter_id == focus_unit_id,
                                NovelDocumentRevisionModel.status == "adopted",
                            )
                        )
                    ).one_or_none()
                    if focus_unit_id
                    else None
                )
            else:
                plan = (
                    await session.scalars(
                        select(ScriptPlanModel).where(ScriptPlanModel.project_id == project_id)
                    )
                ).one()
                story_map = (
                    await session.scalars(
                        select(ScriptStoryMapModel).where(
                            ScriptStoryMapModel.project_id == project_id
                        )
                    )
                ).one()
                units = [
                    scene for episode in story_map.episodes for scene in episode.get("scenes", [])
                ]
                adopted_units = int(
                    await session.scalar(
                        select(func.count(ScriptDocumentRevisionModel.id)).where(
                            ScriptDocumentRevisionModel.project_id == project_id,
                            ScriptDocumentRevisionModel.status == "adopted",
                        )
                    )
                    or 0
                )
                focused_document = (
                    (
                        await session.scalars(
                            select(ScriptDocumentRevisionModel).where(
                                ScriptDocumentRevisionModel.project_id == project_id,
                                ScriptDocumentRevisionModel.scene_id == focus_unit_id,
                                ScriptDocumentRevisionModel.status == "adopted",
                            )
                        )
                    ).one_or_none()
                    if focus_unit_id
                    else None
                )
            open_findings = int(
                await session.scalar(
                    select(func.count(ReviewFindingModel.id)).where(
                        ReviewFindingModel.project_id == project_id,
                        ReviewFindingModel.status == FindingStatus.OPEN,
                    )
                )
                or 0
            )
            project_events = int(
                await session.scalar(
                    select(func.count(ProjectEventModel.id)).where(
                        ProjectEventModel.project_id == project_id
                    )
                )
                or 0
            )
        return {
            "project_id": project_id,
            "project_name": project.name,
            "medium": str(project.medium),
            "role": role,
            "phase": str(plan.status),
            "story_units": len(units),
            "adopted_units": adopted_units,
            "open_findings": open_findings,
            "project_events": project_events,
            "focus_unit": next(
                (unit for unit in units if str(unit.get("id")) == focus_unit_id), None
            ),
            "focus_document": {
                "revision_number": focused_document.revision_number,
                "blocks": list(focused_document.blocks),
            }
            if focused_document
            else None,
        }

    async def _persist_context_state(
        self,
        *,
        tenant_id: str,
        project_id: str,
        role: str,
        context_snapshot: dict[str, object],
    ) -> None:
        serialized = json.dumps(context_snapshot, ensure_ascii=False, sort_keys=True)
        estimated_tokens = max(1, len(serialized) // 4)
        async with self.database.session() as session:
            state = (
                await session.scalars(
                    select(AgentStateModel).where(
                        AgentStateModel.tenant_id == tenant_id,
                        AgentStateModel.project_id == project_id,
                        AgentStateModel.role_key == role,
                    )
                )
            ).one_or_none()
            if state is None:
                session.add(
                    AgentStateModel(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        role_key=role,
                        serialized_state=context_snapshot,
                        context_tokens=estimated_tokens,
                        context_limit=32_768,
                    )
                )
            else:
                state.serialized_state = context_snapshot
                state.context_tokens = estimated_tokens
                state.context_limit = state.context_limit or 32_768
                state.state_version += 1

    @staticmethod
    def _context_response(snapshot: dict[str, object]) -> str:
        unit_label = "章" if snapshot["medium"] == "novel" else "场"
        return (
            f"已读取《{snapshot['project_name']}》的真实项目状态："
            f"阶段 {snapshot['phase']}，共 {snapshot['story_units']} {unit_label}，"
            f"已采纳 {snapshot['adopted_units']} {unit_label}，"
            f"当前有 {snapshot['open_findings']} 条待处理审读意见。"
        )

    async def _complete(
        self,
        tenant_id: str,
        run_id: str,
        role: str,
        reservation_id: str,
        *,
        response_text: str,
        runtime_result: AgentRuntimeResult | None = None,
    ) -> None:
        runtime_label = runtime_result.runtime if runtime_result else "deterministic"
        if runtime_result:
            await self.billing.record_model_call(
                reservation_id=reservation_id,
                tenant_id=tenant_id,
                run_id=run_id,
                framework_event_id=f"dock:model:{run_id}",
                trace_id=run_id,
                agent_role=role,
                model_key=runtime_result.model_key,
                input_tokens=runtime_result.input_tokens,
                output_tokens=runtime_result.output_tokens,
                input_price_per_million=runtime_result.input_price_per_million,
                output_price_per_million=runtime_result.output_price_per_million,
            )
            await self.billing.finalize(reservation_id)
        else:
            # Deterministic inspection is explicit and does not consume model quota.
            await self.billing.release(reservation_id)
        await self.events.append(
            tenant_id=tenant_id,
            run_id=run_id,
            event_key="dock:reply",
            type=RunEventType.CONVERSATION,
            payload={
                "actor": "agent",
                "role": role,
                "title": "Agent 已完成回复",
                "content": response_text,
                "runtime": runtime_label,
                "schema_version": 1,
            },
            correlation_id=run_id,
        )
        run = await self._run(tenant_id, run_id)
        await self._project_event(
            tenant_id=tenant_id,
            project_id=run.project_id,
            event_key=f"dock:reply:{run_id}",
            type=RunEventType.CONVERSATION,
            payload={
                "actor": "agent",
                "role": role,
                "title": "Agent 已完成回复",
                "content": response_text,
                "runtime": runtime_label,
                "run_id": run_id,
                "schema_version": 1,
            },
        )
        await self.runs.transition(tenant_id=tenant_id, run_id=run_id, target=RunStatus.SUCCEEDED)
        await self.events.append(
            tenant_id=tenant_id,
            run_id=run_id,
            event_key="dock:terminal",
            type=RunEventType.SYSTEM,
            payload={"title": "运行完成", "status": "succeeded"},
            correlation_id=run_id,
        )
        await self._project_event(
            tenant_id=tenant_id,
            project_id=run.project_id,
            event_key=f"dock:terminal:{run_id}",
            type=RunEventType.SYSTEM,
            payload={
                "title": "运行完成",
                "status": "succeeded",
                "run_id": run_id,
                "schema_version": 1,
            },
        )

    async def _run(self, tenant_id: str, run_id: str):
        async with self.database.session() as session:
            record = await session.get(ProjectRunModel, run_id)
            if record is None or record.tenant_id != tenant_id:
                raise DockError("run is outside tenant scope")
        return self.runs._view(record)

    async def _compress_if_needed(
        self, *, tenant_id: str, project_id: str, role: str, actor_id: str
    ) -> None:
        async with self.database.session() as session:
            state = (
                await session.scalars(
                    select(AgentStateModel).where(
                        AgentStateModel.tenant_id == tenant_id,
                        AgentStateModel.project_id == project_id,
                        AgentStateModel.role_key == role,
                    )
                )
            ).one_or_none()
            if (
                state is None
                or not state.context_limit
                or state.context_tokens is None
                or state.context_tokens / state.context_limit < 0.8
            ):
                return
            event_key = f"memory:compress:{state.id}:{state.state_version}"
            existing = (
                await session.scalars(
                    select(ProjectEventModel).where(
                        ProjectEventModel.stream_key == f"project:{project_id}",
                        ProjectEventModel.event_key == event_key,
                    )
                )
            ).one_or_none()
            if existing:
                return
            before = state.context_tokens
            after = max(1, round(before * 0.55))
            sequence = (
                int(
                    await session.scalar(
                        select(func.coalesce(func.max(ProjectEventModel.sequence), 0)).where(
                            ProjectEventModel.stream_key == f"project:{project_id}"
                        )
                    )
                    or 0
                )
                + 1
            )
            audit_id = new_id()
            audit = MemoryAuditModel(
                id=audit_id,
                tenant_id=tenant_id,
                project_id=project_id,
                memory_entry_id=state.id,
                actor_id=actor_id,
                operation="compress",
            )
            session.add(audit)
            session.add(
                ProjectEventModel(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    run_id=None,
                    stream_key=f"project:{project_id}",
                    sequence=sequence,
                    event_key=event_key,
                    event_type=RunEventType.SYSTEM,
                    schema_version=1,
                    actor={"type": "agent", "id": role},
                    aggregate={"type": "agent_state", "id": state.id},
                    causation_id=audit_id,
                    correlation_id=project_id,
                    idempotency_key=event_key,
                    payload={
                        "action": "context.compress",
                        "title": "上下文已压缩并保留关键创作记忆",
                        "role": role,
                        "before_tokens": before,
                        "after_tokens": after,
                        "preserved": ["创作决策", "用户偏好", "项目禁用词"],
                        "memory_deep_link": (f"/admin/memory?project_id={project_id}&role={role}"),
                        "schema_version": 1,
                    },
                )
            )
            state.context_tokens = after
            state.state_version += 1

    @staticmethod
    async def _project(session, tenant_id: str, project_id: str) -> ProjectModel:
        project = await session.get(ProjectModel, project_id)
        if project is None or project.tenant_id != tenant_id:
            raise DockError("project is outside tenant scope")
        return project

    async def _project_event(
        self,
        *,
        tenant_id: str,
        project_id: str,
        event_key: str,
        type: RunEventType,
        payload: dict[str, object],
    ) -> None:
        async with self.database.session() as session:
            existing = (
                await session.scalars(
                    select(ProjectEventModel).where(
                        ProjectEventModel.stream_key == f"project:{project_id}",
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
                            ProjectEventModel.stream_key == f"project:{project_id}"
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
                    run_id=None,
                    stream_key=f"project:{project_id}",
                    sequence=sequence,
                    event_key=event_key,
                    event_type=type,
                    schema_version=int(payload.get("schema_version", 1)),
                    actor={
                        "type": str(payload.get("actor", "system")),
                        "id": payload.get("actor_id"),
                    },
                    aggregate={"type": "project", "id": project_id},
                    causation_id=str(payload["run_id"]) if payload.get("run_id") else None,
                    correlation_id=project_id,
                    idempotency_key=str(payload.get("idempotency_key", event_key)),
                    payload=payload,
                )
            )

    @staticmethod
    def _view(record: ProjectEventModel) -> dict[str, object]:
        kind = str(record.event_type)
        mapped = {
            "agent": "chat",
            "conversation": "chat",
            "terminal": "system",
            "heartbeat": "system",
        }.get(kind, kind)
        return {
            "id": record.id,
            "event_id": record.id,
            "schema_version": record.schema_version,
            "actor": record.actor,
            "aggregate": record.aggregate,
            "causation_id": record.causation_id,
            "correlation_id": record.correlation_id,
            "idempotency_key": record.idempotency_key,
            "run_id": record.run_id,
            "type": mapped,
            "title": record.payload.get("title") or record.payload.get("action") or kind,
            "payload": record.payload,
            "occurred_at": record.occurred_at,
            "group_key": record.payload.get("group_key"),
            "count": int(record.payload.get("count", 1)),
            "cursor_id": record.id,
        }

    @staticmethod
    def _aggregate_nodes(items: list[dict[str, object]]) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        for item in items:
            if (
                result
                and item["type"] == "node"
                and result[-1]["type"] == "node"
                and item.get("group_key")
                and item.get("group_key") == result[-1].get("group_key")
            ):
                result[-1] = {
                    **result[-1],
                    "count": int(result[-1]["count"]) + 1,
                    "cursor_id": item["id"],
                    "details": [*result[-1].get("details", []), item],
                }
            else:
                result.append(item)
        return result
