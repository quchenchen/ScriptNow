from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar
from uuid import UUID

from scriptnow.platform.identity import TenantContext


class TenantOwned(Protocol):
    id: UUID
    tenant_id: UUID


OwnedT = TypeVar("OwnedT", bound=TenantOwned)


class TenantObjectNotFound(LookupError):
    """The object is absent from the caller's tenant scope."""


@dataclass(slots=True)
class TenantScopedStore(Generic[OwnedT]):
    """P0 executable contract; P1 repositories must preserve this API shape."""

    _items: dict[tuple[UUID, UUID], OwnedT]

    def __init__(self) -> None:
        self._items = {}

    def add(self, context: TenantContext, item: OwnedT) -> None:
        if item.tenant_id != context.tenant_id:
            raise ValueError("cannot write an object outside the trusted tenant context")
        self._items[(context.tenant_id, item.id)] = item

    def get(self, context: TenantContext, object_id: UUID) -> OwnedT:
        try:
            return self._items[(context.tenant_id, object_id)]
        except KeyError as error:
            raise TenantObjectNotFound(str(object_id)) from error

    def list(self, context: TenantContext) -> list[OwnedT]:
        return [
            item for (tenant_id, _), item in self._items.items() if tenant_id == context.tenant_id
        ]
