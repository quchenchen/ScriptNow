import pytest

from scriptnow.platform.database import Database
from scriptnow.platform.integrity import IntegrityAuditor


@pytest.mark.asyncio
async def test_empty_schema_has_zero_integrity_differences() -> None:
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    report = await IntegrityAuditor(database).audit()
    assert report.ok is True
    assert report.orphan_runtime_snapshots == 0
    assert report.cross_tenant_runs == 0
    assert report.cross_tenant_usage == 0
    assert report.duplicate_usage_events == 0
    assert report.duplicate_ledger_operations == 0
    await database.dispose()
