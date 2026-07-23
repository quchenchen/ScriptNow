from scriptflow_v7.platform.run_events import (
    InMemoryRunEventLog,
    RunEventType,
    encode_sse,
)


def test_run_event_cursor_reconnect_and_dedupe() -> None:
    log = InMemoryRunEventLog()
    first = log.append(
        run_id="run-1",
        event_key="framework-1",
        type=RunEventType.AGENT,
        payload={"delta": "你"},
    )
    duplicate = log.append(
        run_id="run-1",
        event_key="framework-1",
        type=RunEventType.AGENT,
        payload={"delta": "ignored"},
    )
    second = log.append(
        run_id="run-1",
        event_key="framework-2",
        type=RunEventType.TERMINAL,
        payload={"status": "succeeded"},
    )

    assert duplicate is first
    assert log.after("run-1", first.cursor) == [second]
    assert log.after("run-1", second.cursor) == []


def test_sse_frame_has_cursor_type_and_compact_json() -> None:
    event = InMemoryRunEventLog().append(
        run_id="run-1",
        event_key="heartbeat-1",
        type=RunEventType.HEARTBEAT,
        payload={"run_id": "run-1"},
    )

    assert encode_sse(event) == ('id: 1\nevent: heartbeat\ndata: {"run_id":"run-1"}\n\n')
