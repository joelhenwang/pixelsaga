"""Typed application settings (owned by S0-CONFIG-001).

Environment layout (prefix ``WORLDSIM_``, nested delimiter ``__``)::

    WORLDSIM_APP__ENVIRONMENT=test
    WORLDSIM_APP__HOST=127.0.0.1
    WORLDSIM_DATABASE__URL=postgresql+asyncpg://...
    WORLDSIM_PROVIDER__ACTIVE_PROFILE=fake
    WORLDSIM_SECURITY__PUBLIC_BIND_ALLOW=false
"""

from __future__ import annotations

import importlib.metadata
import sys
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

import worldsim

Environment = Literal["local", "test"]
ProviderProfile = Literal["fake", "openrouter"]

_PUBLIC_BIND_HOSTS = frozenset({"0.0.0.0", "::", ""})


class ApplicationSettings(BaseModel):
    """Process identity and HTTP bind contract."""

    environment: Environment = "local"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    debug: bool = False


class DatabaseSettings(BaseModel):
    """PostgreSQL connection contract (S0-DB-001 owns engine/session)."""

    url: str = "postgresql+asyncpg://worldsim:changeme-local-only@localhost:5432/worldsim"
    pool_size: int = Field(default=5, ge=1, le=50)
    statement_timeout_ms: int = Field(default=5000, ge=100, le=60000)

    @field_validator("url")
    @classmethod
    def _require_postgres_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if not parsed.scheme.startswith("postgresql"):
            raise ValueError(
                "invalid database URL scheme; set WORLDSIM_DATABASE__URL to a "
                "postgresql:// or postgresql+asyncpg:// URL"
            )
        if not parsed.hostname or not parsed.path.strip("/"):
            raise ValueError(
                "invalid database URL; WORLDSIM_DATABASE__URL must include host and database name"
            )
        return value


class ProviderSettings(BaseModel):
    """Model gateway profile selection (adapters owned by S0-MODEL-001)."""

    active_profile: ProviderProfile = "fake"
    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    embedding_model: str = "test-embed"
    embedding_dim: int = Field(default=768, ge=1, le=4096)

    @field_validator("openrouter_base_url")
    @classmethod
    def _require_http_base_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError(
                "invalid provider base URL; set WORLDSIM_PROVIDER__OPENROUTER_BASE_URL "
                "to an http(s) URL"
            )
        return value


class TracingSettings(BaseModel):
    """LangSmith development tracing (durable audit owned by S0-TRACE-001)."""

    langsmith_enabled: bool = False
    langsmith_api_key: SecretStr | None = None
    project: str = "worldsim-local"
    endpoint: str = "https://api.smith.langchain.com"


class SecuritySettings(BaseModel):
    """Explicit override for non-loopback listeners."""

    public_bind_allow: bool = False
    api_key: SecretStr | None = None


class Settings(BaseSettings):
    """Root settings; validated once at startup."""

    model_config = SettingsConfigDict(
        env_prefix="WORLDSIM_", env_nested_delimiter="__", extra="forbid"
    )

    app: ApplicationSettings = ApplicationSettings()
    database: DatabaseSettings = DatabaseSettings()
    provider: ProviderSettings = ProviderSettings()
    tracing: TracingSettings = TracingSettings()
    security: SecuritySettings = SecuritySettings()

    @model_validator(mode="after")
    def _reject_unsafe_combinations(self) -> Settings:
        if self.app.host in _PUBLIC_BIND_HOSTS and not (
            self.security.public_bind_allow
            and self.security.api_key is not None
            and self.security.api_key.get_secret_value()
        ):
            raise ValueError(
                "public bind refused: serving on "
                f"{self.app.host!r} requires WORLDSIM_SECURITY__PUBLIC_BIND_ALLOW=true "
                "and a non-empty WORLDSIM_SECURITY__API_KEY"
            )
        if self.provider.active_profile == "openrouter" and (
            self.provider.openrouter_api_key is None
            or not self.provider.openrouter_api_key.get_secret_value()
        ):
            raise ValueError(
                "openrouter profile selected without credentials: set "
                "WORLDSIM_PROVIDER__OPENROUTER_API_KEY or use the fake profile"
            )
        return self


def get_settings() -> Settings:
    """Build and validate settings from the environment."""
    return Settings()


def _package_version(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def dependency_report(active: Settings | None = None) -> dict[str, str]:
    """Version/profile report for diagnostics (never includes secrets)."""
    current = active if active is not None else Settings()
    return {
        "python_version": ".".join(str(part) for part in sys.version_info[:3]),
        "worldsim_version": worldsim.__version__,
        "pydantic_version": _package_version("pydantic"),
        "pydantic_settings_version": _package_version("pydantic-settings"),
        "environment": current.app.environment,
        "active_profile": current.provider.active_profile,
    }
