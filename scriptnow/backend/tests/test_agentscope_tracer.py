from collections.abc import AsyncGenerator

import pytest
from agentscope.agent import Agent, ModelConfig
from agentscope.event import (
    ConfirmResult,
    ModelCallEndEvent,
    RequireUserConfirmEvent,
    UserConfirmResultEvent,
    UserInterruptEvent,
)
from agentscope.message import Msg, TextBlock, ToolCallBlock
from agentscope.model import ChatResponse, ChatUsage
from agentscope.tool import FunctionTool, Toolkit

from scriptnow.platform.usage import UsageRecorder
from tests.agentscope_fakes import ScriptedChatModel


def user_message(text: str) -> Msg:
    return Msg(name="user", role="user", content=[TextBlock(text=text)])


def usage(input_tokens: int = 2, output_tokens: int = 2) -> ChatUsage:
    return ChatUsage(input_tokens=input_tokens, output_tokens=output_tokens, time=0.01)


async def collect(events: AsyncGenerator[object, None]) -> list[object]:
    return [event async for event in events]


@pytest.mark.asyncio
async def test_stream_event_sequence_and_usage_dedupe() -> None:
    model = ScriptedChatModel(
        [
            [
                ChatResponse(content=[TextBlock(id="b1", text="你")], is_last=False),
                ChatResponse(content=[TextBlock(id="b1", text="好")], is_last=False),
                ChatResponse(content=[], is_last=True, usage=usage(3, 2)),
            ],
        ],
    )
    agent = Agent(name="writer", system_prompt="test", model=model)

    events = await collect(agent.reply_stream(user_message("hello")))
    event_names = [type(event).__name__ for event in events]

    assert event_names == [
        "ReplyStartEvent",
        "HintBlockEvent",
        "ModelCallStartEvent",
        "TextBlockStartEvent",
        "TextBlockDeltaEvent",
        "TextBlockDeltaEvent",
        "TextBlockEndEvent",
        "ModelCallEndEvent",
        "ReplyEndEvent",
    ]
    assert [event.delta for event in events if type(event).__name__ == "TextBlockDeltaEvent"] == [
        "你",
        "好",
    ]

    meter = UsageRecorder()
    model_end = next(event for event in events if isinstance(event, ModelCallEndEvent))
    meter.record("run-1", model_end)
    meter.record("run-1", model_end)
    assert [(item.input_tokens, item.output_tokens) for item in meter.for_run("run-1")] == [(3, 2)]


@pytest.mark.asyncio
async def test_tool_confirmation_can_resume_after_state_serialization() -> None:
    writes: list[str] = []

    async def save_candidate(value: str) -> str:
        writes.append(value)
        return value

    model = ScriptedChatModel(
        [
            ChatResponse(
                content=[
                    ToolCallBlock(
                        id="tool-1",
                        name="save_candidate",
                        input='{"value":"draft"}',
                    ),
                ],
                is_last=True,
                usage=usage(),
            ),
            ChatResponse(content=[TextBlock(text="saved")], is_last=True, usage=usage()),
        ],
    )
    toolkit = Toolkit(tools=[FunctionTool(save_candidate)])
    agent = Agent(name="writer", system_prompt="test", model=model, toolkit=toolkit)

    parked_events = await collect(agent.reply_stream(user_message("save")))
    confirmation = next(
        event for event in parked_events if isinstance(event, RequireUserConfirmEvent)
    )
    serialized_state = agent.state.model_dump_json()

    restored_agent = Agent(
        name="writer",
        system_prompt="test",
        model=model,
        toolkit=toolkit,
        state=agent.state.model_validate_json(serialized_state),
    )
    resumed_events = await collect(
        restored_agent.reply_stream(
            UserConfirmResultEvent(
                reply_id=confirmation.reply_id,
                confirm_results=[
                    ConfirmResult(
                        confirmed=True,
                        tool_call=confirmation.tool_calls[0],
                        rules=confirmation.tool_calls[0].suggested_rules,
                    ),
                ],
            ),
        ),
    )

    assert writes == ["draft"]
    assert type(resumed_events[-1]).__name__ == "ReplyEndEvent"
    assert restored_agent.state.model_dump_json()


@pytest.mark.asyncio
async def test_parked_tool_call_can_be_interrupted() -> None:
    model = ScriptedChatModel(
        [
            ChatResponse(
                content=[ToolCallBlock(id="tool-1", name="write", input='{"value":"x"}')],
                is_last=True,
                usage=usage(),
            ),
        ],
    )

    async def write(value: str) -> str:
        return value

    agent = Agent(
        name="writer",
        system_prompt="test",
        model=model,
        toolkit=Toolkit(tools=[FunctionTool(write)]),
    )
    parked = await collect(agent.reply_stream(user_message("write")))
    confirmation = next(event for event in parked if isinstance(event, RequireUserConfirmEvent))

    interrupted = await collect(
        agent.reply_stream(UserInterruptEvent(reply_id=confirmation.reply_id)),
    )

    assert type(interrupted[-1]).__name__ == "ReplyEndEvent"
    assert interrupted[-1].finished_reason == "interrupted"


@pytest.mark.asyncio
async def test_fallback_model_emits_usage_only_for_successful_call() -> None:
    primary = ScriptedChatModel([RuntimeError("primary failed")], name="primary")
    fallback = ScriptedChatModel(
        [ChatResponse(content=[TextBlock(text="fallback")], is_last=True, usage=usage(5, 1))],
        name="fallback",
    )
    agent = Agent(
        name="writer",
        system_prompt="test",
        model=primary,
        model_config=ModelConfig(max_retries=0, fallback_model=fallback),
    )

    events = await collect(agent.reply_stream(user_message("hello")))
    usage_events = [event for event in events if isinstance(event, ModelCallEndEvent)]

    assert primary.call_count == 1
    assert fallback.call_count == 1
    assert [(event.input_tokens, event.output_tokens) for event in usage_events] == [(5, 1)]
