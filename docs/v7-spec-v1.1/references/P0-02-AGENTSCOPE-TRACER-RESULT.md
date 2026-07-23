# P0-02 AgentScope 2.0.4 Tracer Result

- Date: 2026-07-18
- Runtime: local deterministic ScriptedChatModel
- Framework: agentscope 2.0.4

## Verified by executable tests

- Text streaming emits Reply/Model/Text Start→Delta→End in stable order.
- `ModelCallEndEvent` exposes usage; `(run_id, framework_event_id)` prevents replay double counting.
- Non-read-only FunctionTool parks on `RequireUserConfirmEvent`.
- AgentState survives JSON serialization while parked; `UserConfirmResultEvent` resumes and executes once.
- `UserInterruptEvent` terminates a parked reply as interrupted.
- `ModelConfig.fallback_model` takes over after primary failure; only the successful call emits usage in this failure mode.
- Run events support per-run monotonic cursor, event-key dedupe, heartbeat frames and reconnect-after-cursor.
- AgentScope `TracingMiddleware` emits Agent and model OpenTelemetry spans when a standard SDK provider is configured.

## Findings that change the V1.0 assumption

1. AgentScope 2.0.4 has no public `agentscope.init(studio_url=...)` API. The current public Studio tutorial describes a different framework line. V7 will configure the standard OTel SDK directly and treat Studio as an OTLP visualization target.
2. `ModelCallEndEvent` has no application `call_id`; its framework event ID must be persisted as the provider-independent call identity unless a later framework event adds one.
3. Cancelling an actively generating reply means cancelling the asyncio task. `UserInterruptEvent` only targets a parked confirmation/external-execution reply.
4. A primary call that raises before returning a ChatResponse produces no usage event. Provider-side billable failures therefore need provider response metadata or separate middleware evidence; V7 must not invent token usage.

## Environment-dependent checks

- AgentScope Studio is not installed. Official installation is `npm install -g @agentscope/studio`; V7 does not require global Studio for unit/integration tests.
- `agentscope-runtime` is not installed.
- Docker CLI exists, but the local daemon is not running, so DockerWorkspace isolation cannot be executed in this environment yet.

These checks become an environment gate before enabling sandboxed production tools. Domain and platform development may continue with default-deny tool policy and LocalWorkspace tests; no production claim of Docker isolation is allowed until the gate passes.
