from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from scriptnow.platform.database import Database
from scriptnow.platform.model_supply import CredentialCipher, CredentialError
from scriptnow.platform.models import ImageModelModel, ProviderModel


class ImageGenerationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ImageGenerationResult:
    request_id: str
    status: str
    urls: tuple[str, ...]


class ImageGenerationGateway:
    def __init__(
        self,
        database: Database,
        cipher: CredentialCipher,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.database = database
        self.cipher = cipher
        self.transport = transport

    async def generate(
        self,
        *,
        image_model_id: str,
        prompt: str,
        aspect_ratio: str | None = None,
        reference_images: tuple[str, ...] = (),
    ) -> ImageGenerationResult:
        if not prompt.strip() or len(prompt) > 20_000:
            raise ImageGenerationError("cover prompt must contain 1-20000 characters")
        async with self.database.session() as session:
            model = await session.get(ImageModelModel, image_model_id)
            if model is None or not model.enabled:
                raise ImageGenerationError("image model is unavailable")
            provider = await session.get(ProviderModel, model.provider_id)
            if provider is None:
                raise ImageGenerationError("image provider does not exist")
            if not provider.base_url:
                raise ImageGenerationError("image provider Base URL is missing")
            credential = self._credential(provider)
            model_key = model.key
            protocol = model.protocol
            endpoint_path = model.endpoint_path
            defaults = dict(model.default_parameters)
        if protocol != "grsai_image2":
            raise ImageGenerationError(f"unsupported image proxy protocol: {protocol}")
        base = urlparse(provider.base_url)
        if base.scheme != "https" or not base.netloc:
            raise ImageGenerationError("image proxy requires a valid HTTPS Base URL")
        payload = {
            "model": model_key,
            "prompt": prompt.strip(),
            "images": list(reference_images),
            "aspectRatio": aspect_ratio or str(defaults.get("aspectRatio") or "1024x1024"),
            "replyType": str(defaults.get("replyType") or "json"),
        }
        endpoint = f"{provider.base_url.rstrip('/')}{endpoint_path}"
        try:
            async with httpx.AsyncClient(
                timeout=180,
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {credential}",
                        "Accept": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPStatusError as error:
            raise ImageGenerationError(
                f"image proxy returned HTTP {error.response.status_code}"
            ) from error
        except (httpx.HTTPError, ValueError) as error:
            raise ImageGenerationError("image proxy request failed") from error
        request_id = str(body.get("id") or "")
        status = str(body.get("status") or "")
        if not request_id or status not in {"running", "violation", "succeeded", "failed"}:
            raise ImageGenerationError("image proxy returned an invalid response")
        if status != "succeeded":
            detail = str(body.get("error") or status)
            raise ImageGenerationError(f"image generation did not succeed: {detail}")
        urls = tuple(
            str(item["url"])
            for item in body.get("results", [])
            if isinstance(item, dict) and item.get("url")
        )
        if not urls:
            raise ImageGenerationError("image proxy returned no image URL")
        return ImageGenerationResult(request_id=request_id, status=status, urls=urls)

    def _credential(self, provider: ProviderModel) -> str:
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
