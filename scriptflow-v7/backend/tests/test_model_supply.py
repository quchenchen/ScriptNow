import pytest
from sqlalchemy import select

from scriptflow_v7.platform.database import Database
from scriptflow_v7.platform.model_supply import (
    CredentialCipher,
    CredentialError,
    ModelSupplyService,
)
from scriptflow_v7.platform.models import (
    LanguageModelModel,
    ProviderModel,
    ProviderStatus,
    TierModel,
)


@pytest.fixture
async def supply() -> tuple[ModelSupplyService, Database, dict[int, str]]:
    database = Database.create("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    keys = {
        1: "first-master-key-with-at-least-32-bytes",
        2: "second-master-key-with-at-least-32-bytes",
    }
    service = ModelSupplyService(database, CredentialCipher(keys.__getitem__), key_version=1)
    yield service, database, keys
    await database.dispose()


@pytest.mark.asyncio
async def test_provider_secret_is_encrypted_and_never_returned(
    supply: tuple[ModelSupplyService, Database, dict[int, str]],
) -> None:
    service, database, _ = supply
    view = await service.configure_provider(
        key="dashscope", name="DashScope", base_url=None, credential="sk-plain-secret"
    )

    assert view.credential_configured is True
    assert not hasattr(view, "credential")
    async with database.session() as session:
        stored = await session.get(ProviderModel, view.id)
        assert stored is not None
        assert b"sk-plain-secret" not in stored.credential_ciphertext
    assert await service.get_credential_for_runtime(view.id) == "sk-plain-secret"


@pytest.mark.asyncio
async def test_authenticated_encryption_detects_tampering(
    supply: tuple[ModelSupplyService, Database, dict[int, str]],
) -> None:
    service, database, _ = supply
    view = await service.configure_provider(
        key="openai", name="OpenAI", base_url=None, credential="sk-secret"
    )
    async with database.session() as session:
        stored = await session.get(ProviderModel, view.id)
        assert stored is not None and stored.credential_ciphertext is not None
        stored.credential_ciphertext = (
            bytes([stored.credential_ciphertext[0] ^ 1]) + stored.credential_ciphertext[1:]
        )

    with pytest.raises(CredentialError, match="authenticated"):
        await service.get_credential_for_runtime(view.id)


@pytest.mark.asyncio
async def test_key_rotation_reencrypts_with_new_version(
    supply: tuple[ModelSupplyService, Database, dict[int, str]],
) -> None:
    service, database, keys = supply
    view = await service.configure_provider(
        key="anthropic", name="Anthropic", base_url=None, credential="secret-value"
    )
    rotated = ModelSupplyService(database, CredentialCipher(keys.__getitem__), key_version=2)
    await rotated.rotate_provider_credential(view.id)

    assert await rotated.get_credential_for_runtime(view.id) == "secret-value"
    async with database.session() as session:
        stored = await session.get(ProviderModel, view.id)
        assert stored is not None and stored.credential_key_version == 2


@pytest.mark.asyncio
async def test_model_visibility_explains_each_failed_condition(
    supply: tuple[ModelSupplyService, Database, dict[int, str]],
) -> None:
    service, database, _ = supply
    async with database.session() as session:
        plus = TierModel(code="plus", name="Plus", rank=10)
        pro = TierModel(code="pro", name="Pro", rank=20)
        connected = ProviderModel(key="one", name="One", status=ProviderStatus.CONNECTED)
        offline = ProviderModel(key="two", name="Two", status=ProviderStatus.ERROR)
        session.add_all([plus, pro, connected, offline])
        await session.flush()
        session.add_all(
            [
                LanguageModelModel(
                    key="available",
                    display_name="A",
                    provider_id=connected.id,
                    agentscope_class="OpenAIChatModel",
                    min_tier_id=plus.id,
                ),
                LanguageModelModel(
                    key="disabled",
                    display_name="B",
                    provider_id=connected.id,
                    agentscope_class="OpenAIChatModel",
                    min_tier_id=plus.id,
                    enabled=False,
                ),
                LanguageModelModel(
                    key="offline",
                    display_name="C",
                    provider_id=offline.id,
                    agentscope_class="OpenAIChatModel",
                    min_tier_id=plus.id,
                ),
                LanguageModelModel(
                    key="locked",
                    display_name="D",
                    provider_id=connected.id,
                    agentscope_class="OpenAIChatModel",
                    min_tier_id=pro.id,
                ),
            ]
        )

    visibility = await service.visibility("plus")
    reasons = [item.reason for item in visibility]
    assert reasons == [
        "available",
        "model_disabled",
        "provider_not_connected",
        "tier_upgrade_required",
    ]
    assert [item.visible for item in visibility] == [True, False, False, False]

    async with database.session() as session:
        assert len((await session.scalars(select(LanguageModelModel))).all()) == 4
