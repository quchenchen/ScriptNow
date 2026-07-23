from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Trusted tenant identity resolved by the server authentication boundary."""

    tenant_id: UUID
    user_id: UUID
    is_admin: bool = False
