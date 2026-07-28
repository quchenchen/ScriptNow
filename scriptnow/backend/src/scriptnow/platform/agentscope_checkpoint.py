from dataclasses import dataclass

from agentscope.agent import Agent
from agentscope.event import (
    ConfirmResult,
    RequireUserConfirmEvent,
    UserConfirmResultEvent,
)
from agentscope.message import ToolCallBlock
from agentscope.state import AgentState

AGENTSCOPE_CHECKPOINT_FORMAT = "agentscope-agent-state-json-v1"


class AgentScopeCheckpointError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ParkedAgentScopeState:
    state_format: str
    state_payload: bytes
    resume_metadata: dict[str, object]


def capture_parked_state(
    *,
    agent: Agent,
    event: RequireUserConfirmEvent,
    execution_metadata: dict[str, object],
) -> ParkedAgentScopeState:
    """Capture the exact public AgentScope state required to resume a parked tool call."""
    if not event.tool_calls:
        raise AgentScopeCheckpointError("confirmation event does not contain tool calls")
    return ParkedAgentScopeState(
        state_format=AGENTSCOPE_CHECKPOINT_FORMAT,
        state_payload=agent.state.model_dump_json().encode("utf-8"),
        resume_metadata={
            "reply_id": event.reply_id,
            "tool_calls": [item.model_dump(mode="json") for item in event.tool_calls],
            "execution": execution_metadata,
        },
    )


def restore_agent_state(*, state_format: str, state_payload: bytes) -> AgentState:
    if state_format != AGENTSCOPE_CHECKPOINT_FORMAT:
        raise AgentScopeCheckpointError("unsupported AgentScope checkpoint format")
    try:
        return AgentState.model_validate_json(state_payload)
    except Exception as error:
        raise AgentScopeCheckpointError("AgentScope checkpoint payload is invalid") from error


def confirmation_event(
    *,
    resume_metadata: dict[str, object],
    approved: bool,
) -> UserConfirmResultEvent:
    reply_id = resume_metadata.get("reply_id")
    raw_tool_calls = resume_metadata.get("tool_calls")
    if not isinstance(reply_id, str) or not reply_id:
        raise AgentScopeCheckpointError("checkpoint does not identify the parked reply")
    if not isinstance(raw_tool_calls, list) or not raw_tool_calls:
        raise AgentScopeCheckpointError("checkpoint does not contain parked tool calls")
    try:
        tool_calls = [ToolCallBlock.model_validate(item) for item in raw_tool_calls]
    except Exception as error:
        raise AgentScopeCheckpointError("checkpoint tool calls are invalid") from error
    return UserConfirmResultEvent(
        reply_id=reply_id,
        confirm_results=[
            ConfirmResult(
                confirmed=approved,
                tool_call=tool_call,
                rules=tool_call.suggested_rules if approved else [],
            )
            for tool_call in tool_calls
        ],
    )
