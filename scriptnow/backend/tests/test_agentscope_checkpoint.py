from agentscope.agent import Agent
from agentscope.event import RequireUserConfirmEvent
from agentscope.message import ToolCallBlock

from scriptnow.platform.agentscope_checkpoint import (
    AGENTSCOPE_CHECKPOINT_FORMAT,
    capture_parked_state,
    confirmation_event,
    restore_agent_state,
)
from tests.agentscope_fakes import ScriptedChatModel


def test_parked_agentscope_state_round_trips_public_state_and_tool_calls() -> None:
    agent = Agent(
        name="writer",
        system_prompt="test",
        model=ScriptedChatModel([]),
    )
    tool_call = ToolCallBlock(
        id="tool-1",
        name="save_candidate",
        input='{"value":"draft"}',
    )
    event = RequireUserConfirmEvent(
        reply_id="reply-1",
        tool_calls=[tool_call],
    )

    parked = capture_parked_state(
        agent=agent,
        event=event,
        execution_metadata={
            "role": "writer",
            "config_fingerprint": "fingerprint",
        },
    )
    restored = restore_agent_state(
        state_format=parked.state_format,
        state_payload=parked.state_payload,
    )
    approved = confirmation_event(
        resume_metadata=parked.resume_metadata,
        approved=True,
    )
    rejected = confirmation_event(
        resume_metadata=parked.resume_metadata,
        approved=False,
    )

    assert parked.state_format == AGENTSCOPE_CHECKPOINT_FORMAT
    assert restored.model_dump() == agent.state.model_dump()
    assert approved.reply_id == event.reply_id
    assert approved.confirm_results[0].confirmed is True
    assert approved.confirm_results[0].tool_call == tool_call
    assert rejected.confirm_results[0].confirmed is False
    assert rejected.confirm_results[0].rules == []
