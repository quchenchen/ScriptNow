import hashlib
import secrets
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

import httpx
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select

from scriptnow.platform.database import Database
from scriptnow.platform.models import (
    LanguageModelModel,
    ProviderModel,
    ProviderStatus,
    TierModel,
)


class CredentialError(RuntimeError):
    pass


class ProviderDiscoveryError(RuntimeError):
    pass


class KeyResolver(Protocol):
    def __call__(self, version: int) -> str: ...


class CredentialCipher:
    def __init__(self, key_resolver: KeyResolver) -> None:
        self._key_resolver = key_resolver

    @staticmethod
    def _key(material: str) -> bytes:
        return hashlib.sha256(material.encode("utf-8")).digest()

    def encrypt(self, plaintext: str, *, version: int, context: str) -> tuple[bytes, bytes]:
        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(self._key(self._key_resolver(version))).encrypt(
            nonce, plaintext.encode("utf-8"), context.encode("utf-8")
        )
        return ciphertext, nonce

    def decrypt(self, ciphertext: bytes, nonce: bytes, *, version: int, context: str) -> str:
        try:
            value = AESGCM(self._key(self._key_resolver(version))).decrypt(
                nonce, ciphertext, context.encode("utf-8")
            )
        except (InvalidTag, KeyError) as error:
            raise CredentialError("credential cannot be authenticated") from error
        return value.decode("utf-8")


@dataclass(frozen=True, slots=True)
class ProviderView:
    id: str
    key: str
    name: str
    base_url: str | None
    status: str
    credential_configured: bool


@dataclass(frozen=True, slots=True)
class ModelVisibility:
    model_id: str
    visible: bool
    reason: str


@dataclass(frozen=True, slots=True)
class DiscoveredModel:
    key: str
    display_name: str


class OpenAICompatibleDiscovery:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def discover(self, *, base_url: str, credential: str) -> list[DiscoveredModel]:
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ProviderDiscoveryError("model discovery requires a valid HTTPS Base URL")
        endpoint = f"{base_url.rstrip('/')}/models"
        try:
            async with httpx.AsyncClient(
                timeout=15, follow_redirects=False, transport=self._transport
            ) as client:
                response = await client.get(
                    endpoint,
                    headers={"Authorization": f"Bearer {credential}", "Accept": "application/json"},
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise ProviderDiscoveryError(
                f"provider returned HTTP {error.response.status_code}"
            ) from error
        except httpx.HTTPError as error:
            raise ProviderDiscoveryError("provider connection failed") from error
        try:
            payload = response.json()
            rows = payload["data"]
            keys = sorted({str(item["id"]).strip() for item in rows if item.get("id")})
        except (TypeError, KeyError, ValueError) as error:
            raise ProviderDiscoveryError("provider returned an invalid model catalog") from error
        return [DiscoveredModel(key=key, display_name=key) for key in keys[:1000]]


class ModelSupplyService:
    def __init__(self, database: Database, cipher: CredentialCipher, *, key_version: int) -> None:
        self.database = database
        self.cipher = cipher
        self.key_version = key_version

    async def discover_models(self, provider_id: str) -> list[DiscoveredModel]:
        async with self.database.session() as session:
            provider = await session.get(ProviderModel, provider_id)
            if provider is None:
                raise ProviderDiscoveryError("provider does not exist")
            if not provider.base_url:
                raise ProviderDiscoveryError("provider Base URL is not configured")
            credential = self._decrypt(provider)
            base_url = provider.base_url
        try:
            models = await OpenAICompatibleDiscovery().discover(
                base_url=base_url, credential=credential
            )
        except ProviderDiscoveryError:
            # Language-model catalog discovery is an optional capability. An image-only
            # provider may not expose `/models`; failure here must not disable its image runtime.
            raise
        await self._set_provider_status(provider_id, ProviderStatus.CONNECTED)
        return models

    async def _set_provider_status(self, provider_id: str, status: ProviderStatus) -> None:
        async with self.database.session() as session:
            provider = await session.get(ProviderModel, provider_id)
            if provider is not None:
                provider.status = status

    async def configure_provider(
        self, *, key: str, name: str, base_url: str | None, credential: str
    ) -> ProviderView:
        async with self.database.session() as session:
            provider = (
                await session.scalars(select(ProviderModel).where(ProviderModel.key == key))
            ).one_or_none()
            if provider is None:
                provider = ProviderModel(key=key, name=name)
                session.add(provider)
                await session.flush()
            ciphertext, nonce = self.cipher.encrypt(
                credential, version=self.key_version, context=provider.id
            )
            provider.name = name
            provider.base_url = base_url
            provider.credential_ciphertext = ciphertext
            provider.credential_nonce = nonce
            provider.credential_key_version = self.key_version
            provider.status = ProviderStatus.CONNECTED
            return self._view(provider)

    async def get_provider(self, provider_id: str) -> ProviderView | None:
        async with self.database.session() as session:
            provider = await session.get(ProviderModel, provider_id)
            return self._view(provider) if provider else None

    async def get_credential_for_runtime(self, provider_id: str) -> str:
        async with self.database.session() as session:
            provider = await session.get(ProviderModel, provider_id)
            if (
                provider is None
                or provider.credential_ciphertext is None
                or provider.credential_nonce is None
                or provider.credential_key_version is None
            ):
                raise CredentialError("provider credential is not configured")
            return self.cipher.decrypt(
                provider.credential_ciphertext,
                provider.credential_nonce,
                version=provider.credential_key_version,
                context=provider.id,
            )

    async def rotate_provider_credential(self, provider_id: str) -> None:
        async with self.database.session() as session:
            provider = await session.get(ProviderModel, provider_id)
            if provider is None:
                raise CredentialError("provider does not exist")
            plaintext = self._decrypt(provider)
            ciphertext, nonce = self.cipher.encrypt(
                plaintext, version=self.key_version, context=provider.id
            )
            provider.credential_ciphertext = ciphertext
            provider.credential_nonce = nonce
            provider.credential_key_version = self.key_version

    async def visibility(self, tenant_tier_code: str) -> list[ModelVisibility]:
        async with self.database.session() as session:
            tenant_tier = (
                await session.scalars(select(TierModel).where(TierModel.code == tenant_tier_code))
            ).one_or_none()
            if tenant_tier is None or not tenant_tier.enabled:
                return []
            rows = (
                await session.execute(
                    select(LanguageModelModel, ProviderModel, TierModel)
                    .join(ProviderModel, ProviderModel.id == LanguageModelModel.provider_id)
                    .join(TierModel, TierModel.id == LanguageModelModel.min_tier_id)
                    .order_by(LanguageModelModel.display_name)
                )
            ).all()
            result = []
            for model, provider, minimum in rows:
                reason = "available"
                if not model.enabled:
                    reason = "model_disabled"
                elif provider.status != ProviderStatus.CONNECTED:
                    reason = "provider_not_connected"
                elif tenant_tier.rank < minimum.rank:
                    reason = "tier_upgrade_required"
                result.append(ModelVisibility(model.id, reason == "available", reason))
            return result

    def _decrypt(self, provider: ProviderModel) -> str:
        if (
            provider.credential_ciphertext is None
            or provider.credential_nonce is None
            or provider.credential_key_version is None
        ):
            raise CredentialError("provider credential is not configured")
        return self.cipher.decrypt(
            provider.credential_ciphertext,
            provider.credential_nonce,
            version=provider.credential_key_version,
            context=provider.id,
        )

    @staticmethod
    def _view(provider: ProviderModel) -> ProviderView:
        return ProviderView(
            id=provider.id,
            key=provider.key,
            name=provider.name,
            base_url=provider.base_url,
            status=str(provider.status),
            credential_configured=provider.credential_ciphertext is not None,
        )
