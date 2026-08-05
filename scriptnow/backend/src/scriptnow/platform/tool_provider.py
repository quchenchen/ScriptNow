"""Domain tool provider protocol.

Each domain (novel, script) can register a tool provider that the AgentRuntime
discovers dynamically, keeping platform free of domain import coupling.
"""

from __future__ import annotations

from typing import Protocol

from scriptnow.platform.database import Database


class DomainToolProvider(Protocol):
    """Protocol for domain-specific AgentScope tool factories.

    The AgentRuntime calls create_writer_tools() at agent assembly time,
    receiving a list of ToolBase-compatible objects ready for Toolkit(tools=...).
    Platform never needs to know which domain is being loaded.
    """

    def create_writer_tools(self, database: Database, *, project_id: str) -> list[object]:
        """Return AgentScope-compatible tool objects for the Writer agent.

        Args:
            database: The platform database handle.
            project_id: The project to provide tools for.
        """
        ...


# Registry of domain → tool provider
_providers: dict[str, DomainToolProvider] = {}


def register_tool_provider(domain: str, provider: DomainToolProvider) -> None:
    """Register a tool provider for a domain. Called at module import time."""
    if domain in _providers:
        raise ValueError(f"tool provider already registered for domain '{domain}'")
    _providers[domain] = provider


def get_tool_provider(domain: str) -> DomainToolProvider | None:
    """Look up a registered tool provider by domain name."""
    return _providers.get(domain)
