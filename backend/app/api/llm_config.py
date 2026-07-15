"""LLM Config API — list providers, switch models"""
from fastapi import APIRouter

from app.core.llm_client import PROVIDERS, list_available_models

router = APIRouter()


@router.get("/providers")
async def get_providers():
    """List all LLM providers and their models with availability status."""
    models = list_available_models()
    return {
        "providers": models,
        "default_model": "dashscope:deepseek-v4-pro",
    }


@router.get("/providers/{provider_id}")
async def get_provider(provider_id: str):
    p = PROVIDERS.get(provider_id)
    if not p:
        return {"error": "Provider not found"}
    return {
        "id": p.id, "name": p.name, "icon": p.icon,
        "base_url": p.base_url, "api_key_env": p.api_key_env,
        "models": [{"id": m.id, "name": m.name, "type": m.type} for m in p.models],
    }
