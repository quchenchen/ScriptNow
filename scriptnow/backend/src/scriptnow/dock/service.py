import hashlib
import json
from dataclasses import asdict

from agentscope.event import (
    AgentEvent,
    CustomEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
    ToolResultEndEvent,
)
from sqlalchemy import and_, func, or_, select

from scriptnow.novel.domain import NovelDocumentRevisionModel
from scriptnow.novel.project import NovelPlanModel, NovelStoryMapModel
from scriptnow.platform.active_runs import ActiveRunRegistry
from scriptnow.platform.agent_runtime import (
    AgentRuntime,
    AgentRuntimeError,
    AgentRuntimeResult,
    AgentRuntimeTimeoutError,
)
from scriptnow.platform.billing import BillingService
from scriptnow.platform.config import Settings
from scriptnow.platform.creative_operations import (
    CreativeOperationStore,
    OperationView,
)
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    AgentStateModel,
    CreativeOperationModel,
    CreativeStageStatus,
    DecisionRequestStatus,
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
from scriptnow.platform.run_coordinator import RunCoordinator, RunView
from scriptnow.platform.run_events import PersistentRunEventLog, RunEventType
from scriptnow.review.domain import FindingStatus, ReviewFindingModel
from scriptnow.script.domain import ScriptDocumentRevisionModel
from scriptnow.script.project import ScriptPlanModel, ScriptStoryMapModel


class DockError(RuntimeError):
    pass


class DockService:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        active_runs: ActiveRunRegistry,
    ) -> None:
        self.database = database
        self.settings = settings
        self.active_runs = active_runs
        self.runs = RunCoordinator(database)
        self.events = PersistentRunEventLog(database)
        self.billing = BillingService(
            database, enforce_limits=settings.enforce_agent_budget
        )
        self.runtime = AgentRuntime(database, settings)
        self.operations = CreativeOperationStore(database)

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
        stage_override: str | None = None,
        explicit_skill_keys: tuple[str, ...] = (),
    ) -> dict[str, object]:
        run = await self.runs.enqueue(
            tenant_id=tenant_id, project_id=project_id, idempotency_key=idempotency_key
        )
        if run.status != RunStatus.QUEUED:
            return await self._run_with_operation(tenant_id=tenant_id, run=run)
        async with self.database.session() as session:
            tenant = await session.get(TenantModel, tenant_id)
            assert tenant is not None
            project = await self._project(session, tenant_id, project_id)
        reservation = await self.billing.reserve(
            tenant_id=tenant_id,
            run_id=run.id,
            idempotency_key=f"dock:{idempotency_key}",
            tier=tenant.tier,
            max_tokens=self.settings.dock_reserved_tokens,
        )
        creative_session_id = await self.operations.get_or_open_session(
            tenant_id=tenant_id,
            project_id=project_id,
            active_domain=project.medium,
        )
        turn_id = await self.operations.append_turn(
            tenant_id=tenant_id,
            session_id=creative_session_id,
            actor={"type": "user", "id": actor_id, "role": role},
            input={"content": content, "quote": quote, "focus": focus},
        )
        operation = await self.operations.enqueue_operation(
            tenant_id=tenant_id,
            session_id=creative_session_id,
            turn_id=turn_id,
            run_id=run.id,
            command="creative_partner.message",
            domain=project.medium,
            stage=stage_override or role,
            idempotency_key=idempotency_key,
            policy_snapshot={
                "requires_confirmation": requires_confirmation,
                "role": role,
                "stage": stage_override or role,
                "explicit_skill_keys": list(explicit_skill_keys),
            },
        )
        input_digest = hashlib.sha256(
            json.dumps(
                {
                    "content": content,
                    "quote": quote,
                    "focus": focus,
                    "stage": stage_override or role,
                    "explicit_skill_keys": list(explicit_skill_keys),
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode()
        ).hexdigest()
        stage_run_id = await self.operations.start_stage(
            tenant_id=tenant_id,
            operation_id=operation.id,
            stage_key=role,
            attempt=1,
            input_digest=input_digest,
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
        focus_unit_id = (
            str(focus.get("unit_id")) if focus and focus.get("unit_id") else None
        )
        context_snapshot = (
            await self.review_context(
                tenant_id=tenant_id,
                project_id=project_id,
                focus_unit_id=focus_unit_id,
            )
            if role == "reviewer"
            else await self._context_snapshot(
                tenant_id=tenant_id,
                project_id=project_id,
                role=role,
                focus_unit_id=focus_unit_id,
            )
        )
        runtime_result: AgentRuntimeResult | None = None
        runtime_status = await self.runtime.status(tenant_id=tenant_id, project_id=project_id)
        roles = dict(runtime_status["roles"])
        if role not in roles:
            raise DockError(f"unsupported agent role: {role}")
        role_status = dict(roles[role])
        if role_status["connected"]:
            try:
                runtime_sequence = 0
                tool_names: dict[str, str] = {}

                async def persist_runtime_event(event: AgentEvent) -> None:
                    nonlocal runtime_sequence
                    runtime_sequence += 1
                    payload: dict[str, object]
                    event_type: RunEventType
                    if isinstance(event, ToolCallStartEvent):
                        tool_names[event.tool_call_id] = event.tool_call_name
                        payload = {
                            "block": "tool",
                            "phase": "start",
                            "title": f"正在调用 {event.tool_call_name}",
                            "tool_call_id": event.tool_call_id,
                            "tool_name": event.tool_call_name,
                            "runtime": "agentscope",
                        }
                        event_type = RunEventType.NODE
                    elif isinstance(event, ToolCallEndEvent | ToolResultEndEvent):
                        tool_name = tool_names.get(event.tool_call_id, "Agent 工具")
                        payload = {
                            "block": "tool",
                            "phase": "end",
                            "title": f"{tool_name} 调用完成",
                            "tool_call_id": event.tool_call_id,
                            "tool_name": tool_name,
                            "state": (
                                str(event.state)
                                if isinstance(event, ToolResultEndEvent)
                                else None
                            ),
                            "runtime": "agentscope",
                        }
                        event_type = RunEventType.NODE
                    elif isinstance(event, CustomEvent) and event.name in {
                        "scriptnow.phase",
                        "scriptflow.phase",
                    }:
                        phase_value = event.value if isinstance(event.value, dict) else {}
                        phase_content = str(phase_value.get("content") or "").strip()
                        payload = {
                            "block": "thinking" if phase_content else "system",
                            "phase": (
                                "end"
                                if phase_content
                                else str(phase_value.get("phase") or "planning")
                            ),
                            "state": str(phase_value.get("state") or ""),
                            "title": str(phase_value.get("title") or "Agent 阶段更新"),
                            "content": phase_content or None,
                            "runtime": "agentscope",
                        }
                        event_type = RunEventType.SYSTEM
                    else:
                        return
                    await self.events.append(
                        tenant_id=tenant_id,
                        run_id=run.id,
                        event_key=f"dock:runtime:{runtime_sequence}",
                        type=event_type,
                        payload=payload,
                        correlation_id=run.id,
                    )

                runtime_result = await self.runtime.generate(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    role=role,
                    content=content,
                    context_snapshot=context_snapshot,
                    event_sink=persist_runtime_event,
                    stage_override=stage_override,
                    explicit_skill_keys=explicit_skill_keys,
                )
            except Exception as error:
                await self.billing.release(reservation.id)
                error_code = (
                    "agent_runtime_timeout"
                    if isinstance(error, AgentRuntimeTimeoutError)
                    else "agent_runtime_failed"
                )
                await self.runs.transition(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    target=RunStatus.FAILED,
                    error_code=error_code,
                )
                await self.events.append(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    event_key="dock:terminal",
                    type=RunEventType.TERMINAL,
                    payload={"status": "failed", "error_code": error_code},
                    correlation_id=run.id,
                )
                await self.operations.finish_stage(
                    tenant_id=tenant_id,
                    operation_id=operation.id,
                    stage_run_id=stage_run_id,
                    status=CreativeStageStatus.FAILED,
                    error={"code": error_code, "message": str(error)},
                )
                await self._project_event(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    event_key=f"dock:terminal:{run.id}",
                    type=RunEventType.SYSTEM,
                    payload={
                        "title": "运行未完成",
                        "status": "failed",
                        "error_code": error_code,
                        "run_id": run.id,
                        "schema_version": 1,
                    },
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
        visible_events = [
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
        ]
        for key, event_type, payload in visible_events:
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
                "title": "项目上下文已构建",
                "group_key": "context-read",
                "count": len(context_snapshot),
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
            decision = await self.operations.request_decision(
                tenant_id=tenant_id,
                operation_id=operation.id,
                stage_run_id=stage_run_id,
                artifact_ref_id=None,
                checkpoint_id=None,
                kind="tool_confirmation",
                prompt="允许创作搭档写入当前项目工作区吗？",
                options=[
                    {"id": "approve", "label": "允许"},
                    {"id": "reject", "label": "拒绝"},
                ],
                impact={"tool": "workspace.write", "scope": "project"},
                idempotency_key=f"{idempotency_key}:tool-confirmation",
            )
            waiting_operation = await self.operations.operation_for_run(
                tenant_id=tenant_id,
                run_id=run.id,
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
            payload = self._with_operation(asdict(waiting), waiting_operation)
            payload["decision_request_id"] = decision.id
            return payload
        await self._complete(
            tenant_id,
            run.id,
            role,
            reservation.id,
            response_text=response_text,
            runtime_result=runtime_result,
        )
        finished = await self.operations.finish_stage(
            tenant_id=tenant_id,
            operation_id=operation.id,
            stage_run_id=stage_run_id,
            status=CreativeStageStatus.READY,
        )
        return self._with_operation(
            asdict(await self._run(tenant_id, run.id)),
            finished,
        )

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
        pending_decision = await self.operations.pending_decision_for_run(
            tenant_id=tenant_id, run_id=run_id
        )
        if pending_decision is None:
            raise DockError("confirmation request is missing")
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
            await self.operations.resolve_decision(
                tenant_id=tenant_id,
                decision_id=pending_decision.id,
                status=DecisionRequestStatus.REJECTED,
                decision={"approved": False, "idempotency_key": idempotency_key},
                decided_by={"type": "user"},
            )
            await self.billing.release(reservation.id)
            cancelled = await self.runs.transition(
                tenant_id=tenant_id, run_id=run_id, target=RunStatus.CANCELLED
            )
            operation = await self.operations.finish_operation_for_run(
                tenant_id=tenant_id,
                run_id=run_id,
                status=CreativeStageStatus.CANCELLED,
            )
            return self._with_operation(asdict(cancelled), operation)
        await self.operations.resolve_decision(
            tenant_id=tenant_id,
            decision_id=pending_decision.id,
            status=DecisionRequestStatus.APPROVED,
            decision={"approved": True, "idempotency_key": idempotency_key},
            decided_by={"type": "user"},
        )
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
        operation = await self.operations.finish_operation_for_run(
            tenant_id=tenant_id,
            run_id=run_id,
            status=CreativeStageStatus.READY,
        )
        return self._with_operation(
            asdict(await self._run(tenant_id, run_id)),
            operation,
        )

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
        self.active_runs.cancel(run_id)
        cancelled = await self.runs.transition(
            tenant_id=tenant_id, run_id=run_id, target=RunStatus.CANCELLED
        )
        operation = await self.operations.finish_operation_for_run(
            tenant_id=tenant_id,
            run_id=run_id,
            status=CreativeStageStatus.CANCELLED,
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
        return self._with_operation(asdict(cancelled), operation)

    async def _run_with_operation(
        self, *, tenant_id: str, run: RunView
    ) -> dict[str, object]:
        operation = await self.operations.operation_for_run(
            tenant_id=tenant_id, run_id=run.id
        )
        return self._with_operation(asdict(run), operation)

    @staticmethod
    def _with_operation(
        payload: dict[str, object], operation: OperationView | None
    ) -> dict[str, object]:
        if operation is None:
            return payload
        payload["operation_id"] = operation.id
        payload["creative_session_id"] = operation.session_id
        payload["operation_status"] = operation.status
        return payload

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
            run_ids = [item.id for item in records]
            operation_records = (
                list(
                    await session.scalars(
                        select(CreativeOperationModel).where(
                            CreativeOperationModel.tenant_id == tenant_id,
                            CreativeOperationModel.run_id.in_(run_ids),
                        )
                    )
                )
                if run_ids
                else []
            )
            operations_by_run = {item.run_id: item for item in operation_records}
        return [
            {
                "id": item.id,
                "status": str(item.status),
                "waiting_reason": item.waiting_reason,
                "state_version": item.state_version,
                "created_at": item.created_at,
                "operation_id": (
                    operations_by_run[item.id].id if item.id in operations_by_run else None
                ),
                "creative_session_id": (
                    operations_by_run[item.id].session_id
                    if item.id in operations_by_run
                    else None
                ),
                "operation_status": (
                    str(operations_by_run[item.id].status)
                    if item.id in operations_by_run
                    else None
                ),
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

    async def reviewer_capabilities(
        self, *, tenant_id: str, project_id: str
    ) -> dict[str, object]:
        async with self.database.session() as session:
            project = await self._project(session, tenant_id, project_id)
        medium = str(project.medium)
        status = await self.runtime_status(tenant_id=tenant_id, project_id=project_id)
        reviewer_status = dict(dict(status.get("roles") or {}).get("reviewer") or {})
        coverage = {
            "novel": ["故事承诺", "人物与关系", "结构与因果", "叙述与语言", "连续性"],
            "script": ["戏剧目标", "场景行动", "人物与台词", "视听表达", "连续性"],
        }
        return {
            "medium": medium,
            "role": "reviewer",
            "stage": "review",
            "connected": bool(reviewer_status.get("connected")),
            "reviewer_ready": bool(reviewer_status.get("model_key")),
            "coverage": coverage.get(medium, ["结构", "表达", "连续性"]),
            "permission": {
                "default": "read_only",
                "writes": "finding_proposal_only",
                "adoption": "human_decision_required",
            },
        }

    async def review_context(
        self,
        *,
        tenant_id: str,
        project_id: str,
        focus_unit_id: str | None = None,
    ) -> dict[str, object]:
        """Return the persisted evidence available to a project-bound reviewer."""
        return await self._context_snapshot(
            tenant_id=tenant_id,
            project_id=project_id,
            role="reviewer",
            focus_unit_id=focus_unit_id,
        )

    async def _context_snapshot(
        self, *, tenant_id: str, project_id: str, role: str, focus_unit_id: str | None = None
    ) -> dict[str, object]:
        """Build the Dock context from persisted project facts, never fixtures."""
        review_documents: list[object] = []
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
                if role == "reviewer":
                    document_query = select(NovelDocumentRevisionModel).where(
                        NovelDocumentRevisionModel.project_id == project_id,
                        NovelDocumentRevisionModel.status == "adopted",
                    )
                    if focus_unit_id:
                        document_query = document_query.where(
                            NovelDocumentRevisionModel.chapter_id == focus_unit_id
                        )
                    review_documents = list(
                        (await session.scalars(document_query)).all()
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
                if role == "reviewer":
                    document_query = select(ScriptDocumentRevisionModel).where(
                        ScriptDocumentRevisionModel.project_id == project_id,
                        ScriptDocumentRevisionModel.status == "adopted",
                    )
                    if focus_unit_id:
                        document_query = document_query.where(
                            ScriptDocumentRevisionModel.scene_id == focus_unit_id
                        )
                    review_documents = list(
                        (await session.scalars(document_query)).all()
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
        snapshot: dict[str, object] = {
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
        if role == "reviewer":
            unit_by_id = {str(unit.get("id")): unit for unit in units}
            unit_order = {
                str(unit.get("id")): ordinal for ordinal, unit in enumerate(units)
            }
            unit_id_attribute = (
                "chapter_id" if str(project.medium) == "novel" else "scene_id"
            )
            review_documents.sort(
                key=lambda item: unit_order.get(
                    str(getattr(item, unit_id_attribute)), len(unit_order)
                )
            )
            included_documents = [
                {
                    "unit_id": str(getattr(document, unit_id_attribute)),
                    "title": str(
                        unit_by_id.get(
                            str(getattr(document, unit_id_attribute)), {}
                        ).get("title")
                        or getattr(document, unit_id_attribute)
                    ),
                    "revision_number": int(document.revision_number),
                    "blocks": list(document.blocks),
                }
                for document in review_documents
            ]
            included_ids = {
                str(document["unit_id"]) for document in included_documents
            }
            expected_ids = [
                str(unit.get("id")) for unit in units if unit.get("id")
            ]
            omitted_ids = [
                unit_id for unit_id in expected_ids if unit_id not in included_ids
            ]
            snapshot["evidence_manifest"] = {
                "scope": "focused_unit" if focus_unit_id else "whole_project",
                "coverage": (
                    "empty"
                    if not included_documents
                    else "partial"
                    if omitted_ids
                    else "complete"
                ),
                "project_direction": dict(plan.direction),
                "story_structure": {
                    "version": int(story_map.version),
                    "units": units,
                },
                "documents": included_documents,
                "included_unit_ids": sorted(included_ids),
                "omitted_unit_ids": omitted_ids,
            }
        return snapshot

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
                        context_limit=None,
                    )
                )
            else:
                state.serialized_state = context_snapshot
                state.context_tokens = estimated_tokens
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
                "block": "text",
                "phase": "end",
                "title": "Agent 评审结果" if role == "reviewer" else "Agent 回复",
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
