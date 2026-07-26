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


def test_runtime_token_reservation_policies_are_configurable_and_ordered() -> None:
    settings = Settings(
        novel_writer_min_reserved_tokens=1_200,
        novel_writer_max_reserved_tokens=9_000,
        novel_writer_token_reserve_ratio=2.25,
    )

    assert settings.novel_writer_min_reserved_tokens == 1_200
    assert settings.novel_writer_max_reserved_tokens == 9_000
    assert settings.novel_writer_token_reserve_ratio == 2.25

    with pytest.raises(ValidationError, match="novel writer token reservation range"):
        Settings(
            novel_writer_min_reserved_tokens=9_001,
            novel_writer_max_reserved_tokens=9_000,
        )
