import asyncio

from sqlalchemy import select

from scriptnow.platform.auth import AuthService
from scriptnow.platform.config import get_settings
from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    AgentTemplateVersionModel,
    LanguageModelModel,
    ProviderModel,
    ProviderStatus,
    TenantModel,
    TierModel,
    TokenAccountModel,
    UserModel,
)


async def seed() -> None:
    settings = get_settings()
    if settings.environment == "production":
        raise RuntimeError("development seed is disabled in production")
    database = Database.create(settings.database_url)
    await database.create_schema()
    auth = AuthService(database, settings)
    async with database.session() as session:
        user = (
            await session.scalars(select(UserModel).where(UserModel.email == "creator@scriptnow.local"))
        ).one_or_none()
    if user is None:
        tenant, _ = await auth.create_tenant_owner(
            tenant_name="Local Studio",
            email="creator@scriptnow.local",
            password="scriptnow-local-password",
        )
    async with database.session() as session:
        user = (
            await session.scalars(
                select(UserModel).where(UserModel.email == "creator@scriptnow.local")
            )
        ).one()
        user.is_admin = True
        tenant = await session.get(TenantModel, user.tenant_id)
        assert tenant is not None
    async with database.session() as session:
        tier = (
            await session.scalars(select(TierModel).where(TierModel.code == "plus"))
        ).one_or_none()
        if tier is None:
            tier = TierModel(code="plus", name="Plus", rank=10, monthly_token_quota=100_000)
            session.add(tier)
            await session.flush()
        provider = (
            await session.scalars(select(ProviderModel).where(ProviderModel.key == "mock"))
        ).one_or_none()
        if provider is None:
            provider = ProviderModel(key="mock", name="MockRuntime", status=ProviderStatus.CONNECTED)
            session.add(provider)
            await session.flush()
        model = (
            await session.scalars(select(LanguageModelModel).where(LanguageModelModel.key == "mock-v1"))
        ).one_or_none()
        if model is None:
            model = LanguageModelModel(
                key="mock-v1",
                display_name="Mock Runtime",
                provider_id=provider.id,
                agentscope_class="OpenAIChatModel",
                min_tier_id=tier.id,
            )
            session.add(model)
            await session.flush()
        role_souls = {
            "director": "Clarify intent and protect the creative direction.",
            "architect": "Build coherent structures from adopted creative anchors.",
            "writer": (
                "Write vivid, character-bound prose from adopted truth. Protect agency, voice, "
                "causality and human ambiguity; prefer costly choices and concrete perception "
                "over explanation, generic sentiment or deterministic completion."
            ),
            "reviewer": (
                "Protect the work's distinct voice and emotional truth. Diagnose continuity, "
                "agency, relationship movement and AI-like prose with evidence; preserve strong "
                "writing and propose the smallest viable repair."
            ),
        }
        for role_key, soul in role_souls.items():
            template = (
                await session.scalars(
                    select(AgentTemplateVersionModel).where(
                        AgentTemplateVersionModel.role_key == role_key,
                        AgentTemplateVersionModel.published.is_(True),
                    )
                )
            ).first()
            if template is None:
                session.add(
                    AgentTemplateVersionModel(
                        role_key=role_key,
                        version=1,
                        soul=soul,
                        default_model_id=model.id,
                        published=True,
                    )
                )
        account = (
            await session.scalars(
                select(TokenAccountModel).where(
                    TokenAccountModel.tenant_id == tenant.id,
                    TokenAccountModel.tier == "plus",
                )
            )
        ).one_or_none()
        if account is None:
            session.add(
                TokenAccountModel(
                    tenant_id=tenant.id,
                    tier="plus",
                    period_key="development",
                    monthly_available=100_000,
                    credits_available=0,
                )
            )
    await database.dispose()
    print("Seeded creator@scriptnow.local / scriptnow-local-password")


if __name__ == "__main__":
    asyncio.run(seed())
