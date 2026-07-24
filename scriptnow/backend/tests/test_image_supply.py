import json

import httpx
import pytest

from scriptnow.platform.database import Database
from scriptnow.platform.image_supply import ImageGenerationGateway
from scriptnow.platform.model_supply import CredentialCipher, ModelSupplyService
from scriptnow.platform.models import ImageModelModel, TierModel


@pytest.mark.asyncio
async def test_grsai_image2_proxy_uses_documented_contract() -> None:
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    cipher = CredentialCipher(lambda version: "master-key-with-at-least-32-bytes")
    supply = ModelSupplyService(database, cipher, key_version=1)
    provider = await supply.configure_provider(
        key="grsai",
        name="Grsai",
        base_url="https://grsaiapi.com",
        credential="sk-image-secret",
    )
    async with database.session() as session:
        tier = TierModel(code="plus", name="Plus", rank=10)
        session.add(tier)
        await session.flush()
        model = ImageModelModel(
            key="gpt-image-2",
            display_name="GPT Image 2",
            provider_id=provider.id,
            protocol="grsai_image2",
            endpoint_path="/v1/api/generate",
            min_tier_id=tier.id,
            default_parameters={"aspectRatio": "2:3", "replyType": "json"},
        )
        session.add(model)
        await session.flush()
        model_id = model.id

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://grsaiapi.com/v1/api/generate"
        assert request.headers["Authorization"] == "Bearer sk-image-secret"
        body = json.loads(request.content)
        assert body == {
            "model": "gpt-image-2",
            "prompt": "A restrained literary science-fiction cover",
            "images": [],
            "aspectRatio": "2:3",
            "replyType": "json",
        }
        return httpx.Response(
            200,
            json={
                "id": "image-task-1",
                "status": "succeeded",
                "results": [{"url": "https://cdn.example.test/cover.png"}],
            },
        )

    gateway = ImageGenerationGateway(database, cipher, transport=httpx.MockTransport(handler))
    result = await gateway.generate(
        image_model_id=model_id,
        prompt="A restrained literary science-fiction cover",
    )

    assert result.urls == ("https://cdn.example.test/cover.png",)
    await database.dispose()
