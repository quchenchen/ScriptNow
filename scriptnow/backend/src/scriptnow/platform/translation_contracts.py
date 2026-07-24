from dataclasses import dataclass
from typing import Protocol


class TranslationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TranslationUnit:
    titles: dict[str, str]
    blocks: tuple[dict[str, object], ...]


class TranslationService(Protocol):
    async def translate(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source_language: str,
        target_language: str,
        units: tuple[TranslationUnit, ...],
        idempotency_key: str,
    ) -> tuple[TranslationUnit, ...]: ...
