from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from scriptflow_v7.platform.identity import TenantContext
from scriptflow_v7.platform.tenancy import TenantObjectNotFound, TenantScopedStore


@dataclass(frozen=True, slots=True)
class ProjectRecord:
    id: UUID
    tenant_id: UUID
    name: str


def context(tenant_id: UUID) -> TenantContext:
    return TenantContext(tenant_id=tenant_id, user_id=uuid4())


def test_cross_tenant_read_is_indistinguishable_from_not_found() -> None:
    tenant_a = context(uuid4())
    tenant_b = context(uuid4())
    project = ProjectRecord(id=uuid4(), tenant_id=tenant_a.tenant_id, name="A")
    store: TenantScopedStore[ProjectRecord] = TenantScopedStore()
    store.add(tenant_a, project)

    with pytest.raises(TenantObjectNotFound):
        store.get(tenant_b, project.id)

    assert store.list(tenant_b) == []


def test_cross_tenant_write_is_rejected() -> None:
    tenant_a = context(uuid4())
    tenant_b = context(uuid4())
    project = ProjectRecord(id=uuid4(), tenant_id=tenant_a.tenant_id, name="A")
    store: TenantScopedStore[ProjectRecord] = TenantScopedStore()

    with pytest.raises(ValueError, match="trusted tenant context"):
        store.add(tenant_b, project)


def test_same_object_id_can_exist_in_separate_tenants() -> None:
    shared_id = uuid4()
    tenant_a = context(uuid4())
    tenant_b = context(uuid4())
    store: TenantScopedStore[ProjectRecord] = TenantScopedStore()
    store.add(tenant_a, ProjectRecord(shared_id, tenant_a.tenant_id, "A"))
    store.add(tenant_b, ProjectRecord(shared_id, tenant_b.tenant_id, "B"))

    assert store.get(tenant_a, shared_id).name == "A"
    assert store.get(tenant_b, shared_id).name == "B"
