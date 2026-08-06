from decimal import Decimal

import pytest
from sqlalchemy import func, select

from scriptnow.platform.agent_runtime import (
    AGENT_MAX_ITERATIONS_MESSAGE,
    AgentRuntimeResult,
)
from scriptnow.platform.config import Settings
from scriptnow.platform.database import Database
from scriptnow.platform.models import ProjectModel, ReviewMessageModel, TenantModel
from scriptnow.review.workbench_service import ReviewWorkbenchError, ReviewWorkbenchService


@pytest.fixture
async def review_workbench() -> tuple[ReviewWorkbenchService, Database, str]:
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    async with database.session() as session:
        tenant = TenantModel(name="Independent review tenant")
        session.add(tenant)
        await session.flush()
        tenant_id = tenant.id
    service = ReviewWorkbenchService(database, Settings())
    yield service, database, tenant_id
    await database.dispose()


@pytest.mark.asyncio
async def test_uploaded_review_case_does_not_create_hidden_project(review_workbench) -> None:
    service, database, tenant_id = review_workbench

    case = await service.create_case(
        tenant_id=tenant_id,
        filename="outline.md",
        media_type="text/markdown",
        content=b"# The Crossing\nA witness must choose between truth and safety.",
        document_kind="outline",
        review_domain="script",
        title=None,
    )

    assert case["title"] == "outline"
    assert case["status"] == "ready"
    assert case["messages"] == []
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(ProjectModel)) == 0


@pytest.mark.asyncio
async def test_create_case_surface_readable_parse_error(review_workbench, monkeypatch) -> None:
    service, _, tenant_id = review_workbench

    def _fail_extract_source_text(*_args, **_kwargs) -> str:
        raise ValueError("parse failed")

    monkeypatch.setattr(
        "scriptnow.review.workbench_service.extract_source_text", _fail_extract_source_text
    )

    with pytest.raises(ReviewWorkbenchError) as error:
        await service.create_case(
            tenant_id=tenant_id,
            filename="story.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            content=b"bad content",
            document_kind="novel",
            review_domain="novel",
            title="Bad story",
        )

    assert "cannot be parsed or is not readable" in str(error.value)


@pytest.mark.asyncio
async def test_review_conversation_is_durable_and_idempotent(
    review_workbench,
    monkeypatch,
) -> None:
    service, database, tenant_id = review_workbench
    case = await service.create_case(
        tenant_id=tenant_id,
        filename="story.txt",
        media_type="text/plain",
        content=b"A character opens the forbidden door.",
        document_kind="novel",
        review_domain="novel",
        title="The Door",
    )

    async def review_source(**kwargs) -> AgentRuntimeResult:
        assert kwargs["source_text"] == "A character opens the forbidden door."
        assert kwargs["request"] == "Assess the opening and cite evidence."
        assert kwargs["conversation"] == ()
        return AgentRuntimeResult(
            text="## Finding\nThe forbidden door creates an immediate decision.",
            runtime="agentscope",
            model_key="review-model",
            input_tokens=20,
            output_tokens=12,
            input_price_per_million=Decimal("0"),
            output_price_per_million=Decimal("0"),
            config_fingerprint="review-config",
        )

    monkeypatch.setattr(service.runtime, "review_source", review_source)
    first = await service.send_message(
        tenant_id=tenant_id,
        case_id=str(case["id"]),
        content="Assess the opening and cite evidence.",
        idempotency_key="turn-1",
        language="en-US",
    )
    repeated = await service.send_message(
        tenant_id=tenant_id,
        case_id=str(case["id"]),
        content="Assess the opening and cite evidence.",
        idempotency_key="turn-1",
        language="en-US",
    )

    assert [message["actor"] for message in first["messages"]] == ["user", "assistant"]
    assert all("metadata" not in message for message in first["messages"])
    assert repeated["messages"] == first["messages"]
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ReviewMessageModel))
            == 2
        )


@pytest.mark.asyncio
async def test_follow_up_review_receives_the_durable_conversation(
    review_workbench,
    monkeypatch,
) -> None:
    service, _, tenant_id = review_workbench
    case = await service.create_case(
        tenant_id=tenant_id,
        filename="story.txt",
        media_type="text/plain",
        content=b"A character opens the forbidden door.",
        document_kind="novel",
        review_domain="novel",
        title="The Door",
    )
    conversations: list[tuple[dict[str, str], ...]] = []

    async def review_source(**kwargs) -> AgentRuntimeResult:
        conversations.append(kwargs["conversation"])
        return AgentRuntimeResult(
            text="The answer remains bound to the cited door scene.",
            runtime="agentscope",
            model_key="review-model",
            input_tokens=20,
            output_tokens=12,
            input_price_per_million=Decimal("0"),
            output_price_per_million=Decimal("0"),
            config_fingerprint="review-config",
        )

    monkeypatch.setattr(service.runtime, "review_source", review_source)
    await service.send_message(
        tenant_id=tenant_id,
        case_id=str(case["id"]),
        content="Assess the opening.",
        idempotency_key="turn-1",
        language="en-US",
    )
    await service.send_message(
        tenant_id=tenant_id,
        case_id=str(case["id"]),
        content="Now compare that finding with the ending.",
        idempotency_key="turn-2",
        language="en-US",
    )

    assert conversations[0] == ()
    assert conversations[1] == (
        {"actor": "user", "content": "Assess the opening."},
        {
            "actor": "assistant",
            "content": "The answer remains bound to the cited door scene.",
        },
    )


@pytest.mark.asyncio
async def test_incomplete_agentscope_reply_is_recoverable(
    review_workbench,
    monkeypatch,
) -> None:
    service, database, tenant_id = review_workbench
    case = await service.create_case(
        tenant_id=tenant_id,
        filename="story.txt",
        media_type="text/plain",
        content=b"A character opens the forbidden door.",
        document_kind="novel",
        review_domain="novel",
        title="The Door",
    )

    async def review_source(**_kwargs) -> AgentRuntimeResult:
        return AgentRuntimeResult(
            text=AGENT_MAX_ITERATIONS_MESSAGE,
            runtime="agentscope",
            model_key="review-model",
            input_tokens=20,
            output_tokens=12,
            input_price_per_million=Decimal("0"),
            output_price_per_million=Decimal("0"),
            config_fingerprint="review-config",
            completed=False,
            stop_reason="iteration_limit",
            agent_state={"memory": {"state": "paused"}},
        )

    monkeypatch.setattr(service.runtime, "review_source", review_source)
    await service.send_message(
        tenant_id=tenant_id,
        case_id=str(case["id"]),
        content="Assess the opening.",
        idempotency_key="turn-incomplete",
        language="en-US",
    )

    loaded = await service.get_case(tenant_id=tenant_id, case_id=str(case["id"]))
    assert loaded["status"] == "waiting"
    assert [message["actor"] for message in loaded["messages"]] == [
        "user",
        "assistant",
    ]
    assistant = loaded["messages"][1]
    assert AGENT_MAX_ITERATIONS_MESSAGE not in assistant["content"]
    assert assistant["metadata"] == {
        "kind": "interruption",
        "recoverable": True,
        "stop_reason": "iteration_limit",
    }
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ReviewMessageModel))
            == 2
        )


@pytest.mark.asyncio
async def test_follow_up_resumes_saved_agentscope_state(
    review_workbench,
    monkeypatch,
) -> None:
    service, _, tenant_id = review_workbench
    case = await service.create_case(
        tenant_id=tenant_id,
        filename="story.txt",
        media_type="text/plain",
        content=b"A character opens the forbidden door.",
        document_kind="novel",
        review_domain="novel",
        title="The Door",
    )
    received_states: list[dict[str, object] | None] = []

    async def review_source(**kwargs) -> AgentRuntimeResult:
        received_states.append(kwargs["agent_state"])
        if len(received_states) == 1:
            return AgentRuntimeResult(
                text=AGENT_MAX_ITERATIONS_MESSAGE,
                runtime="agentscope",
                model_key="review-model",
                input_tokens=20,
                output_tokens=12,
                input_price_per_million=Decimal("0"),
                output_price_per_million=Decimal("0"),
                config_fingerprint="review-config",
                completed=False,
                stop_reason="iteration_limit",
                agent_state={"memory": {"state": "paused"}},
            )
        return AgentRuntimeResult(
            text="## Completed review\nThe door is the decisive image.",
            runtime="agentscope",
            model_key="review-model",
            input_tokens=20,
            output_tokens=12,
            input_price_per_million=Decimal("0"),
            output_price_per_million=Decimal("0"),
            config_fingerprint="review-config",
        )

    monkeypatch.setattr(service.runtime, "review_source", review_source)
    await service.send_message(
        tenant_id=tenant_id,
        case_id=str(case["id"]),
        content="Assess the opening.",
        idempotency_key="turn-1",
        language="en-US",
    )
    resumed = await service.send_message(
        tenant_id=tenant_id,
        case_id=str(case["id"]),
        content="Continue the same review.",
        idempotency_key="turn-2",
        language="en-US",
    )

    assert received_states == [None, {"memory": {"state": "paused"}}]
    assert resumed["status"] == "ready"
    assert resumed["messages"][-1]["content"].startswith("## Completed review")


@pytest.mark.asyncio
async def test_review_focus_reaches_runtime_without_leaking_internal_metadata(
    review_workbench,
    monkeypatch,
) -> None:
    service, _, tenant_id = review_workbench
    case = await service.create_case(
        tenant_id=tenant_id,
        filename="screenplay.txt",
        media_type="text/plain",
        content=b"INT. STUDIO - NIGHT\nA sculptor opens the plaster shell.",
        document_kind="script",
        review_domain="script",
        title="The Shell",
    )
    received: list[dict[str, object]] = []

    async def review_source(**kwargs) -> AgentRuntimeResult:
        received.append(kwargs)
        return AgentRuntimeResult(
            text="## Character review\nThe action reveals the sculptor's fear.",
            runtime="agentscope",
            model_key="review-model",
            input_tokens=20,
            output_tokens=12,
            input_price_per_million=Decimal("0"),
            output_price_per_million=Decimal("0"),
            config_fingerprint="review-config",
        )

    monkeypatch.setattr(service.runtime, "review_source", review_source)
    loaded = await service.send_message(
        tenant_id=tenant_id,
        case_id=str(case["id"]),
        content="Assess character agency.",
        idempotency_key="turn-character",
        language="en-US",
        review_focus="character",
    )

    assert received[0]["review_focus"] == "character"
    assert "metadata" not in loaded["messages"][-1]


@pytest.mark.asyncio
async def test_changing_review_focus_starts_a_fresh_agent_state(
    review_workbench,
    monkeypatch,
) -> None:
    service, _, tenant_id = review_workbench
    case = await service.create_case(
        tenant_id=tenant_id,
        filename="story.txt",
        media_type="text/plain",
        content=b"A character opens the forbidden door.",
        document_kind="novel",
        review_domain="novel",
        title="The Door",
    )
    received_states: list[dict[str, object] | None] = []

    async def review_source(**kwargs) -> AgentRuntimeResult:
        received_states.append(kwargs["agent_state"])
        return AgentRuntimeResult(
            text=AGENT_MAX_ITERATIONS_MESSAGE,
            runtime="agentscope",
            model_key="review-model",
            input_tokens=20,
            output_tokens=12,
            input_price_per_million=Decimal("0"),
            output_price_per_million=Decimal("0"),
            config_fingerprint="review-config",
            completed=False,
            stop_reason="iteration_limit",
            agent_state={"memory": {"focus": kwargs["review_focus"]}},
        )

    monkeypatch.setattr(service.runtime, "review_source", review_source)
    await service.send_message(
        tenant_id=tenant_id,
        case_id=str(case["id"]),
        content="Assess structure.",
        idempotency_key="turn-structure",
        language="en-US",
        review_focus="structure",
    )
    await service.send_message(
        tenant_id=tenant_id,
        case_id=str(case["id"]),
        content="Now assess market positioning.",
        idempotency_key="turn-market",
        language="en-US",
        review_focus="market",
    )

    assert received_states == [None, None]
