import pytest
from pydantic import ValidationError

from scriptnow.platform.config import Settings


def test_production_rejects_development_secrets_and_insecure_cookies() -> None:
    with pytest.raises(ValidationError, match="access token secret"):
        Settings(environment="production")
    with pytest.raises(ValidationError, match="credential master key"):
        Settings(
            environment="production",
            access_token_secret="production-access-secret-at-least-24-bytes",
        )
    with pytest.raises(ValidationError, match="cookies must be secure"):
        Settings(
            environment="production",
            access_token_secret="production-access-secret-at-least-24-bytes",
            credential_master_key="production-credential-key-at-least-32-bytes",
        )

    settings = Settings(
        environment="production",
        access_token_secret="production-access-secret-at-least-24-bytes",
        credential_master_key="production-credential-key-at-least-32-bytes",
        cookie_secure=True,
    )
    assert settings.environment == "production"
