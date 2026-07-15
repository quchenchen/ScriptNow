"""
LLM Gateway — Multi-provider abstraction with unified interface.

Pattern: Each provider is a named entry with model list.
Users configure API keys per provider, then assign models to agents.
"""
from dataclasses import dataclass, field
from typing import Optional, AsyncGenerator
from openai import AsyncOpenAI
import json, os


@dataclass
class ModelInfo:
    id: str          # "deepseek-v4-pro"
    name: str        # "DeepSeek V4 Pro"
    provider: str    # "deepseek"
    type: str        # "text" | "vision" | "reasoning"
    context_window: int = 128000
    max_output: int = 8192


@dataclass
class ProviderInfo:
    id: str          # "deepseek"
    name: str        # "DeepSeek"
    icon: str        # provider logo key
    models: list[ModelInfo] = field(default_factory=list)
    requires_api_key: bool = True
    base_url: str = ""
    api_key_env: str = ""  # e.g. "DEEPSEEK_API_KEY"


# ── Provider Registry ──────────────────────────────────────────

PROVIDERS: dict[str, ProviderInfo] = {
    "deepseek": ProviderInfo(
        id="deepseek", name="DeepSeek", icon="deepseek",
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
        models=[
            ModelInfo("deepseek-v4-pro", "DeepSeek V4 Pro", "deepseek", "reasoning", 128000, 8192),
            ModelInfo("deepseek-chat", "DeepSeek Chat", "deepseek", "text", 64000, 4096),
        ]
    ),
    "dashscope": ProviderInfo(
        id="dashscope", name="阿里云百炼", icon="dashscope",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="DASHSCOPE_API_KEY",
        models=[
            ModelInfo("deepseek-v4-pro", "DeepSeek V4 Pro (百炼)", "dashscope", "reasoning", 128000, 8192),
            ModelInfo("qwen3.7-max", "Qwen 3.7 Max", "dashscope", "text", 128000, 8192),
            ModelInfo("qwen3.7-plus", "Qwen 3.7 Plus", "dashscope", "text", 128000, 4096),
        ]
    ),
    "openai": ProviderInfo(
        id="openai", name="OpenAI", icon="openai",
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        models=[
            ModelInfo("gpt-4o", "GPT-4o", "openai", "text", 128000, 4096),
            ModelInfo("gpt-4o-mini", "GPT-4o Mini", "openai", "text", 128000, 16384),
        ]
    ),
    "anthropic": ProviderInfo(
        id="anthropic", name="Anthropic", icon="anthropic",
        base_url="https://api.anthropic.com/v1",
        api_key_env="ANTHROPIC_API_KEY",
        models=[
            ModelInfo("claude-sonnet-4-20250514", "Claude Sonnet 4", "anthropic", "text", 200000, 8192),
            ModelInfo("claude-opus-4-20250514", "Claude Opus 4", "anthropic", "text", 200000, 8192),
        ]
    ),
    "custom": ProviderInfo(
        id="custom", name="自定义", icon="custom",
        base_url="",
        api_key_env="CUSTOM_API_KEY",
        models=[]
    ),
}


def get_provider(provider_id: str) -> Optional[ProviderInfo]:
    return PROVIDERS.get(provider_id)


def list_available_models() -> list[dict]:
    """Return all models grouped by provider, marking which have API keys configured."""
    result = []
    for pid, p in PROVIDERS.items():
        has_key = bool(os.getenv(p.api_key_env, ""))
        models = []
        for m in p.models:
            models.append({
                "id": f"{pid}:{m.id}",
                "name": m.name,
                "type": m.type,
                "context": m.context_window,
                "available": has_key,
            })
        result.append({
            "provider_id": pid,
            "provider_name": p.name,
            "icon": p.icon,
            "configured": has_key,
            "models": models,
        })
    return result


# ── Unified LLM Client ─────────────────────────────────────────

class LLMClient:
    """Unified client that routes to the correct provider based on model ID."""

    def __init__(self, model_id: str = "dashscope:deepseek-v4-pro"):
        self.model_id = model_id
        self._client: Optional[AsyncOpenAI] = None
        self._provider: Optional[ProviderInfo] = None
        self._init()

    def _init(self):
        parts = self.model_id.split(":", 1)
        pid = parts[0] if len(parts) == 2 else "dashscope"
        model = parts[1] if len(parts) == 2 else parts[0]
        self._provider = PROVIDERS.get(pid)
        if not self._provider:
            raise ValueError(f"Unknown provider: {pid}")
        api_key = os.getenv(self._provider.api_key_env, "")
        self._client = AsyncOpenAI(api_key=api_key, base_url=self._provider.base_url)
        self._model = model

    async def chat(self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 4096) -> str:
        resp = await self._client.chat.completions.create(
            model=self._model, messages=messages,
            temperature=temperature, max_tokens=max_tokens, stream=False)
        return resp.choices[0].message.content or ""

    async def stream_chat(self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 4096) -> AsyncGenerator[str, None]:
        stream = await self._client.chat.completions.create(
            model=self._model, messages=messages,
            temperature=temperature, max_tokens=max_tokens, stream=True)
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def json_chat(self, messages: list[dict], temperature: float = 0.3) -> dict:
        msgs = [{"role": "system", "content": "Always respond with valid JSON."}, *messages]
        resp = await self._client.chat.completions.create(
            model=self._model, messages=msgs,
            temperature=temperature, max_tokens=4096,
            response_format={"type": "json_object"}, stream=False)
        return json.loads(resp.choices[0].message.content or "{}")

    @property
    def provider_name(self) -> str:
        return self._provider.name if self._provider else "unknown"

    @property
    def model_name(self) -> str:
        return self._model
