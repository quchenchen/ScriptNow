import hashlib
from pathlib import Path

from sqlalchemy import func, select

from scriptnow.platform.agent_factory import AgentFactory, RuntimeConfigError
from scriptnow.platform.agent_runtime import (
    AgentRuntime,
    AgentRuntimeResult,
    is_incomplete_agent_text,
)
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    ReviewCaseModel,
    ReviewCaseStatus,
    ReviewMessageModel,
)
from scriptnow.platform.source_text import extract_source_text


class ReviewWorkbenchError(RuntimeError):
    pass


class ReviewWorkbenchService:
    """Independent evidence review; no hidden ProjectModel is created."""

    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings
        self.runtime = AgentRuntime(database, settings)
        self.factory = AgentFactory(database)

    async def capabilities(self, *, tenant_id: str, review_domain: str) -> dict[str, object]:
        if review_domain not in {"novel", "script"}:
            raise ReviewWorkbenchError("review domain must be novel or script")
        try:
            snapshot = await self.factory.preview_for_tenant(
                tenant_id=tenant_id,
                role_key="reviewer",
                medium=review_domain,
                direction={"language": "zh-CN"},
                stage="review",
            )
        except RuntimeConfigError as error:
            raise ReviewWorkbenchError(str(error)) from error
        values = snapshot.values
        return {
            "review_domain": review_domain,
            "connected": values.get("provider_key") != "mock",
            "reviewer_ready": bool(values.get("model_key")),
            "coverage": (
                ["人物与关系", "结构与节奏", "场景与表达", "连续性", "市场与改编价值"]
                if review_domain == "novel"
                else ["人物与冲突", "场景行动", "视听表达", "结构与节奏", "制作与市场价值"]
            ),
        }

    async def create_case(
        self,
        *,
        tenant_id: str,
        filename: str,
        media_type: str,
        content: bytes,
        document_kind: str,
        review_domain: str,
        title: str | None,
    ) -> dict[str, object]:
        if review_domain not in {"novel", "script"}:
            raise ReviewWorkbenchError("review domain must be novel or script")
        if document_kind not in {"novel", "script", "outline"}:
            raise ReviewWorkbenchError("document kind must be novel, script, or outline")
        if document_kind in {"novel", "script"} and document_kind != review_domain:
            raise ReviewWorkbenchError("document kind and review domain do not match")
        try:
            text = extract_source_text(content, media_type)
        except Exception as error:
            raise ReviewWorkbenchError(
                "the uploaded file cannot be parsed or is not readable"
            ) from error
        if not text.strip():
            raise ReviewWorkbenchError("the uploaded file does not contain readable text")
        case = ReviewCaseModel(
            tenant_id=tenant_id,
            title=(title or Path(filename).stem).strip()[:240],
            document_kind=document_kind,
            review_domain=review_domain,
            source_filename=filename,
            source_media_type=media_type,
            source_digest=hashlib.sha256(content).hexdigest(),
            source_text=text,
            status=ReviewCaseStatus.READY,
        )
        async with self.database.session() as session:
            session.add(case)
            await session.flush()
        return await self.get_case(tenant_id=tenant_id, case_id=case.id)

    async def list_cases(self, *, tenant_id: str) -> list[dict[str, object]]:
        async with self.database.session() as session:
            cases = list(
                await session.scalars(
                    select(ReviewCaseModel)
                    .where(ReviewCaseModel.tenant_id == tenant_id)
                    .order_by(ReviewCaseModel.updated_at.desc())
                )
            )
        return [self._case_payload(case, []) for case in cases]

    async def get_case(self, *, tenant_id: str, case_id: str) -> dict[str, object]:
        async with self.database.session() as session:
            case = await session.get(ReviewCaseModel, case_id)
            if case is None or case.tenant_id != tenant_id:
                raise ReviewWorkbenchError("review case does not exist")
            messages = list(
                await session.scalars(
                    select(ReviewMessageModel)
                    .where(
                        ReviewMessageModel.tenant_id == tenant_id,
                        ReviewMessageModel.case_id == case_id,
                    )
                    .order_by(ReviewMessageModel.sequence)
                )
            )
        return self._case_payload(case, messages)

    async def send_message(
        self,
        *,
        tenant_id: str,
        case_id: str,
        content: str,
        idempotency_key: str,
        language: str,
        review_focus: str = "overall",
    ) -> dict[str, object]:
        user_key = f"user:{idempotency_key}"
        assistant_key = f"assistant:{idempotency_key}"
        async with self.database.session() as session:
            case = await session.get(ReviewCaseModel, case_id)
            if case is None or case.tenant_id != tenant_id:
                raise ReviewWorkbenchError("review case does not exist")
            existing = (
                await session.scalars(
                    select(ReviewMessageModel).where(
                        ReviewMessageModel.case_id == case_id,
                        ReviewMessageModel.idempotency_key == assistant_key,
                    )
                )
            ).one_or_none()
            if existing is not None:
                return await self.get_case(tenant_id=tenant_id, case_id=case_id)
            sequence = int(
                await session.scalar(
                    select(func.coalesce(func.max(ReviewMessageModel.sequence), 0)).where(
                        ReviewMessageModel.case_id == case_id
                    )
                )
                or 0
            )
            prior_messages = list(
                await session.scalars(
                    select(ReviewMessageModel)
                    .where(
                        ReviewMessageModel.tenant_id == tenant_id,
                        ReviewMessageModel.case_id == case_id,
                    )
                    .order_by(ReviewMessageModel.sequence)
                )
            )
            resumable_state = next(
                (
                    message.metadata_json.get("agent_state")
                    for message in reversed(prior_messages)
                    if message.actor == "assistant"
                    and isinstance(message.metadata_json, dict)
                    and isinstance(message.metadata_json.get("agent_state"), dict)
                    and message.metadata_json.get("review_focus", "overall") == review_focus
                ),
                None,
            )
            session.add(
                ReviewMessageModel(
                    tenant_id=tenant_id,
                    case_id=case_id,
                    sequence=sequence + 1,
                    actor="user",
                    content=content,
                    idempotency_key=user_key,
                    metadata_json={"review_focus": review_focus},
                )
            )
            case.status = ReviewCaseStatus.REVIEWING
            source_text = case.source_text
            title = case.title
            review_domain = case.review_domain
            document_kind = case.document_kind
        try:
            result = await self.runtime.review_source(
                tenant_id=tenant_id,
                review_domain=review_domain,
                document_kind=document_kind,
                title=title,
                source_text=source_text,
                request=content,
                language=language,
                review_focus=review_focus,
                conversation=tuple(
                    {"actor": message.actor, "content": message.content}
                    for message in prior_messages
                ),
                agent_state=resumable_state,
            )
            await self._record_assistant(
                tenant_id=tenant_id,
                case_id=case_id,
                sequence=sequence + 2,
                idempotency_key=assistant_key,
                result=result,
                review_focus=review_focus,
            )
        except Exception:
            async with self.database.session() as session:
                case = await session.get(ReviewCaseModel, case_id)
                if case is not None:
                    case.status = ReviewCaseStatus.FAILED
            raise
        return await self.get_case(tenant_id=tenant_id, case_id=case_id)

    async def _record_assistant(
        self,
        *,
        tenant_id: str,
        case_id: str,
        sequence: int,
        idempotency_key: str,
        result: AgentRuntimeResult,
        review_focus: str,
    ) -> None:
        completed = result.completed and not is_incomplete_agent_text(result.text)
        assistant_text = (
            result.text.strip()
            if completed
            else "评审尚未完成，当前进度已保存。你可以继续本轮评审，无需重新上传作品。"
        )
        metadata: dict[str, object] = {
            "runtime": result.runtime,
            "model_key": result.model_key,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "config_fingerprint": result.config_fingerprint,
            "review_focus": review_focus,
        }
        if result.evidence_manifest:
            metadata["evidence_manifest"] = list(result.evidence_manifest)
        if result.agent_state:
            metadata["agent_state"] = result.agent_state
        if not completed:
            metadata.update(
                {
                    "kind": "interruption",
                    "recoverable": True,
                    "stop_reason": result.stop_reason or "iteration_limit",
                }
            )
        async with self.database.session() as session:
            case = await session.get(ReviewCaseModel, case_id)
            if case is None or case.tenant_id != tenant_id:
                raise ReviewWorkbenchError("review case does not exist")
            session.add(
                ReviewMessageModel(
                    tenant_id=tenant_id,
                    case_id=case_id,
                    sequence=sequence,
                    actor="assistant",
                    content=assistant_text,
                    idempotency_key=idempotency_key,
                    metadata_json=metadata,
                )
            )
            case.status = (
                ReviewCaseStatus.READY if completed else ReviewCaseStatus.WAITING
            )

    @staticmethod
    def _case_payload(
        case: ReviewCaseModel,
        messages: list[ReviewMessageModel],
    ) -> dict[str, object]:
        return {
            "id": case.id,
            "title": case.title,
            "document_kind": case.document_kind,
            "review_domain": case.review_domain,
            "source_filename": case.source_filename,
            "status": str(case.status),
            "created_at": case.created_at.isoformat(),
            "updated_at": case.updated_at.isoformat(),
            "messages": [
                {
                    "id": message.id,
                    "sequence": message.sequence,
                    "actor": message.actor,
                    "content": (
                        "本轮评审未完成。评审要求已保留，请直接重试。"
                        if message.actor == "assistant"
                        and is_incomplete_agent_text(message.content)
                        else message.content
                    ),
                    "created_at": message.created_at.isoformat(),
                    **ReviewWorkbenchService._public_message_metadata(message),
                }
                for message in messages
            ],
        }

    @staticmethod
    def _public_message_metadata(message: ReviewMessageModel) -> dict[str, object]:
        if not isinstance(message.metadata_json, dict):
            return {}
        public_keys = {
            "kind",
            "recoverable",
            "stop_reason",
            "evidence_manifest",
        }
        metadata = {
            key: value
            for key, value in message.metadata_json.items()
            if key in public_keys
        }
        return {"metadata": metadata} if metadata else {}
