from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.auth import dependencies
from app.auth import dev as dev_module
from app.auth.dev import DevStubProvider
from app.core.config import Settings
from app.core.exceptions import AuthenticationError


def make_settings(**overrides: Any) -> Settings:
    """Build Settings without reading the developer's real .env file."""
    return Settings(_env_file=None, **overrides)


def test_dev_provider_allowed_in_development() -> None:
    s = make_settings(app_env="development", auth_provider="dev")
    assert s.auth_provider == "dev"
    assert not s.is_production


def test_provider_value_is_normalised() -> None:
    s = make_settings(auth_provider=" Azure ", azure_tenant_id="t", azure_client_id="c")
    assert s.auth_provider == "azure"


def test_unknown_provider_rejected() -> None:
    with pytest.raises(ValidationError):
        make_settings(auth_provider="azzure")


def test_production_with_dev_provider_refuses_to_boot() -> None:
    with pytest.raises(ValidationError):
        make_settings(app_env="production", auth_provider="dev")


def test_production_with_default_provider_refuses_to_boot() -> None:
    # A prod deploy that simply forgets AUTH_PROVIDER must not boot.
    with pytest.raises(ValidationError):
        make_settings(app_env="PROD")


def test_production_with_azure_boots() -> None:
    s = make_settings(
        app_env="production",
        auth_provider="azure",
        azure_tenant_id="tenant",
        azure_client_id="client",
    )
    assert s.is_production
    assert s.auth_provider == "azure"


def test_azure_requires_tenant_and_client() -> None:
    with pytest.raises(ValidationError):
        make_settings(auth_provider="azure", azure_tenant_id="", azure_client_id="")


def test_get_auth_provider_fails_closed_on_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    dependencies.get_auth_provider.cache_clear()
    try:
        monkeypatch.setattr(dependencies.settings, "auth_provider", "bogus")
        with pytest.raises(RuntimeError):
            dependencies.get_auth_provider()
    finally:
        dependencies.get_auth_provider.cache_clear()


async def test_dev_stub_refuses_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dev_module.settings, "app_env", "production")
    provider = DevStubProvider()
    with pytest.raises(AuthenticationError):
        await provider.resolve_user(None, None)  # type: ignore[arg-type]
