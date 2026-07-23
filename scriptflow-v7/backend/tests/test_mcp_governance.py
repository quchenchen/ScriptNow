import pytest
from sqlalchemy import select

from scriptflow_v7.platform.agent_runtime import AgentRuntime
from scriptflow_v7.platform.config import Settings
from scriptflow_v7.platform.database import Database
from scriptflow_v7.platform.mcp_governance import (
    DiscoveredTool,
    McpGovernanceError,
    McpGovernanceService,
)
from scriptflow_v7.platform.model_supply import CredentialCipher
from scriptflow_v7.platform.models import McpServerModel, McpToolModel, TierModel


class FakeProbe:
    def __init__(self, *, fails: bool = False) -> None:
        self.fails = fails

    async def discover(self, **_: object) -> tuple[list[DiscoveredTool], int]:
        if self.fails:
            raise RuntimeError("offline secret=must-not-leak")
        return [DiscoveredTool("search", "Search", "Search approved sources")], 17


@pytest.mark.asyncio
async def test_discovery_defaults_to_denied_whitelist_and_preserves_it_on_disconnect() -> None:
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    async with database.session() as session:
        session.add(TierModel(code="plus", name="Plus", rank=10))
    cipher = CredentialCipher(lambda _: "test-master-key")
    service = McpGovernanceService(database, cipher, key_version=1, probe=FakeProbe())
    server_id = await service.configure(
        key="research",
        name="Research",
        transport="http",
        config={"url": "https://mcp.example", "headers": {"Authorization": "secret-token"}},
        min_tier_code="plus",
        enabled=True,
        confirmation_required=True,
    )
    tools = await service.discover(server_id)
    assert [item.key for item in tools] == ["search"]
    async with database.session() as session:
        server = await session.get(McpServerModel, server_id)
        tool = (await session.scalars(select(McpToolModel))).one()
        assert server is not None and server.status == "connected" and server.latency_ms == 17
        assert server.public_config == {
            "url": "https://mcp.example",
            "timeout": 30,
            "headers_configured": True,
        }
        assert "secret-token" not in str(server.public_config)
        assert tool.whitelisted is False
        tool.whitelisted = True
    failing = McpGovernanceService(database, cipher, key_version=1, probe=FakeProbe(fails=True))
    with pytest.raises(McpGovernanceError, match="connection failed"):
        await failing.discover(server_id)
    async with database.session() as session:
        server = await session.get(McpServerModel, server_id)
        tool = (await session.scalars(select(McpToolModel))).one()
        assert server is not None and server.status == "error"
        assert tool.whitelisted is True
    await database.dispose()


@pytest.mark.asyncio
async def test_runtime_mounts_only_connected_whitelisted_tools_without_confirmation() -> None:
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    async with database.session() as session:
        session.add(TierModel(code="plus", name="Plus", rank=10))
    cipher = CredentialCipher(lambda _: "test-master-key-that-is-long-enough")
    service = McpGovernanceService(database, cipher, key_version=1, probe=FakeProbe())
    server_id = await service.configure(
        key="research",
        name="Research",
        transport="http",
        config={"url": "https://mcp.example", "headers": {"Authorization": "secret-token"}},
        min_tier_code="plus",
        enabled=True,
        confirmation_required=False,
    )
    await service.discover(server_id)
    async with database.session() as session:
        tool = (await session.scalars(select(McpToolModel))).one()
        tool.whitelisted = True
    runtime = AgentRuntime(
        database,
        Settings(credential_master_key="test-master-key-that-is-long-enough"),
    )
    clients = await runtime._mcp_clients(
        ["mcp.research.search", "mcp.research.not-discovered", "builtin.unrelated"]
    )
    assert len(clients) == 1
    assert clients[0].name == "research"
    assert clients[0].is_stateful is False
    assert clients[0].enable_tools == ["search"]
    assert clients[0].mcp_config.url == "https://mcp.example"
    assert clients[0].mcp_config.headers == {"Authorization": "secret-token"}

    async with database.session() as session:
        server = await session.get(McpServerModel, server_id)
        assert server is not None
        server.confirmation_required = True
    assert await runtime._mcp_clients(["mcp.research.search"]) == []
    await database.dispose()
