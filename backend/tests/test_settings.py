import pytest
from pydantic import ValidationError

from worldsim.infrastructure.settings import Settings, dependency_report


def test_local_defaults_bind_loopback():
    settings = Settings()
    assert settings.app.environment == "local"
    assert settings.app.host == "127.0.0.1"


def test_test_profile_permits_missing_secrets(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WORLDSIM_APP__ENVIRONMENT", "test")
    settings = Settings()
    assert settings.app.environment == "test"
    assert settings.provider.openrouter_api_key is None


def test_invalid_database_url_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WORLDSIM_DATABASE__URL", "sqlite:///local.db")
    with pytest.raises(ValidationError, match="database URL"):
        Settings()


def test_invalid_embedding_dim_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WORLDSIM_PROVIDER__EMBEDDING_DIM", "0")
    with pytest.raises(ValidationError, match="embedding_dim"):
        Settings()


def test_public_bind_without_override_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WORLDSIM_APP__HOST", "0.0.0.0")
    with pytest.raises(ValidationError, match="public bind refused"):
        Settings()


def test_public_bind_with_override_and_key_allowed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WORLDSIM_APP__HOST", "0.0.0.0")
    monkeypatch.setenv("WORLDSIM_SECURITY__PUBLIC_BIND_ALLOW", "true")
    monkeypatch.setenv("WORLDSIM_SECURITY__API_KEY", "test-sentinel-key")
    settings = Settings()
    assert settings.app.host == "0.0.0.0"


def test_openrouter_without_key_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WORLDSIM_PROVIDER__ACTIVE_PROFILE", "openrouter")
    with pytest.raises(ValidationError, match="OPENROUTER_API_KEY"):
        Settings()


def test_dependency_report_contains_versions():
    report = dependency_report(Settings())
    assert report["worldsim_version"] == "0.1.0"
    assert report["python_version"].startswith("3.12.")
    assert report["active_profile"] == "fake"
    assert "OPENROUTER" not in str(report.values()).upper()


def test_invalid_provider_base_url_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORLDSIM_PROVIDER__OPENROUTER_BASE_URL", "not-a-url")
    with pytest.raises(ValidationError, match="base URL"):
        Settings()
