"""
LLM Gateway — Multi-provider routing with intelligent model selection.
"""
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass

from openai import AsyncOpenAI

from .config import LLM_CONFIG


@dataclass
class LLMRequest:
    messages: list[dict]
    temperature: float = 0.7
    max_tokens: int = 4096
    stream: bool = False
    agent_type: str = "creative"  # creative | analytical | translation


class LLMGateway:
    """Multi-provider LLM gateway with intelligent routing."""

    def __init__(self):
        self._clients: dict[str, AsyncOpenAI] = {}
        self._init_clients()

    def _init_clients(self):
        for name, cfg in LLM_CONFIG["providers"].items():
            if cfg["api_key"]:
                self._clients[name] = AsyncOpenAI(
                    api_key=cfg["api_key"],
                    base_url=cfg["api_base"],
                )

    def _get_route(self, agent_type: str) -> dict:
        """Get provider + model for a given agent type."""
        route = LLM_CONFIG["routing"].get(agent_type, {})
        return {
            "provider": route.get("provider", LLM_CONFIG["default_provider"]),
            "model": route.get("model", LLM_CONFIG["default_model"]),
        }

    async def chat(self, req: LLMRequest) -> str:
        """Non-streaming chat completion."""
        route = self._get_route(req.agent_type)
        client = self._clients.get(route["provider"])
        if not client:
            raise ValueError(f"No client for provider: {route['provider']}")

        resp = await client.chat.completions.create(
            model=route["model"],
            messages=req.messages,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            stream=False,
        )
        return resp.choices[0].message.content or ""

    async def stream_chat(self, req: LLMRequest) -> AsyncGenerator[str, None]:
        """Streaming chat completion."""
        route = self._get_route(req.agent_type)
        client = self._clients.get(route["provider"])
        if not client:
            raise ValueError(f"No client for provider: {route['provider']}")

        stream = await client.chat.completions.create(
            model=route["model"],
            messages=req.messages,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def json_chat(self, req: LLMRequest) -> dict:
        """Chat with forced JSON output."""
        route = self._get_route(req.agent_type)
        client = self._clients.get(route["provider"])
        if not client:
            raise ValueError(f"No client for provider: {route['provider']}")

        resp = await client.chat.completions.create(
            model=route["model"],
            messages=req.messages,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            response_format={"type": "json_object"},
            stream=False,
        )
        raw = resp.choices[0].message.content or "{}"
        return json.loads(raw)


# Singleton
_llm_gateway: LLMGateway | None = None


def get_llm() -> LLMGateway:
    global _llm_gateway
    if _llm_gateway is None:
        _llm_gateway = LLMGateway()
    return _llm_gateway
