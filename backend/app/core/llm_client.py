"""LLM provider registry.

This file used to hold a hand-rolled ``LLMClient`` wrapping ``AsyncOpenAI`` in
parallel with an unrelated ``LLMGateway`` (also removed). Both were unwired
dead code. The one thing that *is* wired is this provider/model registry —
consumed by ``/api/llm/list_available_models`` so the frontend model picker
knows what to show and which are ready-to-use (API key configured).

All real LLM calls now go through AgentScope 2.0 (see :mod:`app.agents.team`).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class ModelInfo:
    id: str
    name: str
    provider: str
    type: str  # "text" | "vision" | "reasoning"
    context_window: int = 128000
    max_output: int = 8192


@dataclass
class ProviderInfo:
    id: str
    name: str
    icon: str
    models: list[ModelInfo] = field(default_factory=list)
    requires_api_key: bool = True
    base_url: str = ""
    api_key_env: str = ""  # e.g. "DEEPSEEK_API_KEY"


PROVIDERS: dict[str, ProviderInfo] = {
    "deepseek": ProviderInfo(
        id="deepseek", name="DeepSeek", icon="deepseek",
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
        models=[
            ModelInfo("deepseek-v4-pro", "DeepSeek V4 Pro", "deepseek", "reasoning", 128000, 8192),
            ModelInfo("deepseek-chat", "DeepSeek Chat", "deepseek", "text", 64000, 4096),
        ],
    ),
    "dashscope": ProviderInfo(
        id="dashscope", name="阿里云百炼", icon="dashscope",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="DASHSCOPE_API_KEY",
        models=[
            ModelInfo("deepseek-v4-pro", "DeepSeek V4 Pro (百炼)", "dashscope", "reasoning", 128000, 8192),
            ModelInfo("qwen3.7-max", "Qwen 3.7 Max", "dashscope", "text", 128000, 8192),
            ModelInfo("qwen3.7-plus", "Qwen 3.7 Plus", "dashscope", "text", 128000, 4096),
        ],
    ),
    "openai": ProviderInfo(
        id="openai", name="OpenAI", icon="openai",
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        models=[
            ModelInfo("gpt-4o", "GPT-4o", "openai", "text", 128000, 4096),
            ModelInfo("gpt-4o-mini", "GPT-4o Mini", "openai", "text", 128000, 16384),
        ],
    ),
    "anthropic": ProviderInfo(
        id="anthropic", name="Anthropic", icon="anthropic",
        base_url="https://api.anthropic.com/v1",
        api_key_env="ANTHROPIC_API_KEY",
        models=[
            ModelInfo("claude-sonnet-4-20250514", "Claude Sonnet 4", "anthropic", "text", 200000, 8192),
            ModelInfo("claude-opus-4-20250514", "Claude Opus 4", "anthropic", "text", 200000, 8192),
        ],
    ),
}


def get_provider(provider_id: str) -> ProviderInfo | None:
    return PROVIDERS.get(provider_id)


def list_available_models() -> list[dict]:
    """Return all models grouped by provider, marking which are configured."""
    result: list[dict] = []
    for pid, p in PROVIDERS.items():
        has_key = bool(os.getenv(p.api_key_env, ""))
        models = [
            {
                "id": f"{pid}:{m.id}",
                "name": m.name,
                "type": m.type,
                "context": m.context_window,
                "available": has_key,
            }
            for m in p.models
        ]
        result.append(
            {
                "provider_id": pid,
                "provider_name": p.name,
                "icon": p.icon,
                "configured": has_key,
                "models": models,
            }
        )
    return result
