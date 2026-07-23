import json
import time
from dataclasses import dataclass
from typing import Protocol

from agentscope.mcp import HttpMCPConfig, MCPClient, StdioMCPConfig
from sqlalchemy import select

from scriptflow_v7.platform.database import Database
from scriptflow_v7.platform.model_supply import CredentialCipher
from scriptflow_v7.platform.models import McpServerModel, McpToolModel, TierModel


class McpGovernanceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DiscoveredTool:
    key: str
    name: str
    description: str


class McpProbe(Protocol):
    async def discover(
        self, *, name: str, transport: str, config: dict[str, object]
    ) -> tuple[list[DiscoveredTool], int]: ...


class AgentScopeMcpProbe:
    async def discover(
        self, *, name: str, transport: str, config: dict[str, object]
    ) -> tuple[list[DiscoveredTool], int]:
        if transport == "http":
            mcp_config = HttpMCPConfig(
                url=str(config["url"]),
                headers=config.get("headers"),
                timeout=float(config.get("timeout", 30)),
            )
        elif transport == "stdio":
            mcp_config = StdioMCPConfig(
                command=str(config["command"]),
                args=list(config.get("args", [])),
                env=config.get("env"),
                cwd=config.get("cwd"),
            )
        else:
            raise McpGovernanceError("unsupported MCP transport")
        client = MCPClient(name=name, is_stateful=True, mcp_config=mcp_config)
        started = time.monotonic()
        try:
            await client.connect()
            tools = await client.list_tools()
            latency = round((time.monotonic() - started) * 1000)
            return [
                DiscoveredTool(
                    key=str(item.name),
                    name=str(item.name),
                    description=str(getattr(item, "description", "") or ""),
                )
                for item in tools
            ], latency
        finally:
            await client.close()


class McpGovernanceService:
    def __init__(
        self,
        database: Database,
        cipher: CredentialCipher,
        *,
        key_version: int,
        probe: McpProbe | None = None,
    ) -> None:
        self.database = database
        self.cipher = cipher
        self.key_version = key_version
        self.probe = probe or AgentScopeMcpProbe()

    async def configure(
        self,
        *,
        key: str,
        name: str,
        transport: str,
        config: dict[str, object],
        min_tier_code: str,
        enabled: bool,
        confirmation_required: bool,
    ) -> str:
        if transport == "http" and not str(config.get("url", "")).startswith(
            ("http://", "https://")
        ):
            raise McpGovernanceError("HTTP MCP requires a valid URL")
        if transport == "stdio" and not str(config.get("command", "")).strip():
            raise McpGovernanceError("stdio MCP requires a command")
        async with self.database.session() as session:
            tier = (
                await session.scalars(select(TierModel).where(TierModel.code == min_tier_code))
            ).one_or_none()
            if tier is None:
                raise McpGovernanceError("tier unavailable")
            item = (
                await session.scalars(select(McpServerModel).where(McpServerModel.key == key))
            ).one_or_none()
            if item is None:
                item = McpServerModel(
                    key=key,
                    name=name,
                    transport=transport,
                    public_config={},
                    secret_ciphertext=b"",
                    secret_nonce=b"",
                    secret_key_version=self.key_version,
                    min_tier_id=tier.id,
                )
                session.add(item)
                await session.flush()
            ciphertext, nonce = self.cipher.encrypt(
                json.dumps(config), version=self.key_version, context=item.id
            )
            item.name = name
            item.transport = transport
            item.public_config = self._public(transport, config)
            item.secret_ciphertext = ciphertext
            item.secret_nonce = nonce
            item.secret_key_version = self.key_version
            item.min_tier_id = tier.id
            item.enabled = enabled
            item.confirmation_required = confirmation_required
            item.status = "unconfigured"
            item.last_error = None
            return item.id

    async def discover(self, server_id: str) -> list[DiscoveredTool]:
        async with self.database.session() as session:
            item = await session.get(McpServerModel, server_id)
            if item is None:
                raise McpGovernanceError("MCP server not found")
            config = json.loads(
                self.cipher.decrypt(
                    item.secret_ciphertext,
                    item.secret_nonce,
                    version=item.secret_key_version,
                    context=item.id,
                )
            )
            name, transport = item.name, item.transport
        try:
            tools, latency = await self.probe.discover(
                name=name, transport=transport, config=config
            )
        except Exception as error:
            async with self.database.session() as session:
                item = await session.get(McpServerModel, server_id)
                assert item is not None
                item.status = "error"
                item.latency_ms = None
                item.last_error = str(error)[:500]
            raise McpGovernanceError("MCP connection failed") from error
        async with self.database.session() as session:
            item = await session.get(McpServerModel, server_id)
            assert item is not None
            item.status = "connected"
            item.latency_ms = latency
            item.last_error = None
            existing = {
                tool.key: tool
                for tool in (
                    await session.scalars(
                        select(McpToolModel).where(McpToolModel.server_id == server_id)
                    )
                ).all()
            }
            for discovered in tools:
                tool = existing.get(discovered.key)
                if tool is None:
                    session.add(
                        McpToolModel(
                            server_id=server_id,
                            key=discovered.key,
                            name=discovered.name,
                            description=discovered.description,
                        )
                    )
                else:
                    tool.name = discovered.name
                    tool.description = discovered.description
        return tools

    @staticmethod
    def _public(transport: str, config: dict[str, object]) -> dict[str, object]:
        if transport == "http":
            return {
                "url": config.get("url"),
                "timeout": config.get("timeout", 30),
                "headers_configured": bool(config.get("headers")),
            }
        return {
            "command": config.get("command"),
            "args": config.get("args", []),
            "cwd": config.get("cwd"),
            "env_configured": bool(config.get("env")),
        }
