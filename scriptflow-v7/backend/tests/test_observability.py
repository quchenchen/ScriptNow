import pytest
from agentscope.agent import Agent
from agentscope.message import TextBlock
from agentscope.middleware import TracingMiddleware
from agentscope.model import ChatResponse, ChatUsage
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from scriptflow_v7.platform.observability import configure_tracing, shutdown_tracing
from tests.agentscope_fakes import ScriptedChatModel
from tests.test_agentscope_tracer import collect, user_message


@pytest.mark.asyncio
async def test_agentscope_tracing_emits_agent_and_model_spans() -> None:
    exporter = InMemorySpanExporter()
    provider = configure_tracing(
        service_name="scriptflow-v7-test",
        processor=SimpleSpanProcessor(exporter),
    )
    model = ScriptedChatModel(
        [
            ChatResponse(
                content=[TextBlock(text="ok")],
                is_last=True,
                usage=ChatUsage(input_tokens=2, output_tokens=1, time=0.01),
            ),
        ],
    )
    agent = Agent(
        name="writer",
        system_prompt="test",
        model=model,
        middlewares=[TracingMiddleware()],
    )

    await collect(agent.reply_stream(user_message("trace me")))
    provider.force_flush()
    spans = exporter.get_finished_spans()

    assert len(spans) >= 2
    assert any("writer" in span.name for span in spans)
    assert any("fake" in span.name for span in spans)
    shutdown_tracing(provider)
