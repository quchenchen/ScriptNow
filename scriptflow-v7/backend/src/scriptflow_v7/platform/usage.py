from dataclasses import dataclass

from agentscope.event import ModelCallEndEvent


@dataclass(frozen=True, slots=True)
class UsageRecord:
    run_id: str
    framework_event_id: str
    reply_id: str
    input_tokens: int
    output_tokens: int


class UsageRecorder:
    """Dedupe model usage by stable framework event identity within a run."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], UsageRecord] = {}

    def record(self, run_id: str, event: ModelCallEndEvent) -> UsageRecord:
        key = (run_id, event.id)
        record = UsageRecord(
            run_id=run_id,
            framework_event_id=event.id,
            reply_id=event.reply_id,
            input_tokens=event.input_tokens,
            output_tokens=event.output_tokens,
        )
        return self._records.setdefault(key, record)

    def for_run(self, run_id: str) -> list[UsageRecord]:
        return [record for record in self._records.values() if record.run_id == run_id]
