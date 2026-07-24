import httpx
import pytest

from scriptnow.platform.model_supply import (
    OpenAICompatibleDiscovery,
    ProviderDiscoveryError,
)


@pytest.mark.asyncio
async def test_openai_compatible_model_discovery_sorts_and_deduplicates() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://dashscope.example/compatible-mode/v1/models"
        assert request.headers["Authorization"] == "Bearer sk-test"
        return httpx.Response(
            200,
            json={"object": "list", "data": [{"id": "qwen-plus"}, {"id": "qwen-max"}, {"id": "qwen-plus"}]},
        )

    client = OpenAICompatibleDiscovery(httpx.MockTransport(handler))
    models = await client.discover(
        base_url="https://dashscope.example/compatible-mode/v1", credential="sk-test"
    )

    assert [model.key for model in models] == ["qwen-max", "qwen-plus"]


@pytest.mark.asyncio
async def test_model_discovery_rejects_non_https_base_url() -> None:
    with pytest.raises(ProviderDiscoveryError, match="HTTPS"):
        await OpenAICompatibleDiscovery().discover(
            base_url="http://127.0.0.1:9000/v1", credential="secret"
        )
