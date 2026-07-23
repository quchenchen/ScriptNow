from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SpanProcessor


def configure_tracing(
    *,
    service_name: str,
    processor: SpanProcessor,
) -> TracerProvider:
    """Configure the OTel provider consumed by AgentScope TracingMiddleware."""

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    return provider


def shutdown_tracing(provider: TracerProvider) -> None:
    provider.force_flush()
    provider.shutdown()
