"""Fail-closed production runtime configuration tests."""

import pytest

from backend.config import Settings


_SECURE_PRODUCTION = {
    "env": "production",
    "secret_key": "production-secret",
    "auth_secret": "production-auth-secret",
    "request_scoped_runtime": True,
    "database_url": "postgresql://user:password@database.example/finview",
}


def test_production_accepts_persistent_request_scoped_runtime():
    runtime = Settings(**_SECURE_PRODUCTION)

    assert runtime.request_scoped_runtime is True
    assert runtime.database_url.startswith("postgresql")


def test_production_rejects_background_runtime():
    with pytest.raises(RuntimeError, match="REQUEST_SCOPED_RUNTIME"):
        Settings(**{**_SECURE_PRODUCTION, "request_scoped_runtime": False})


def test_production_rejects_ephemeral_sqlite():
    with pytest.raises(RuntimeError, match="persistent PostgreSQL"):
        Settings(**{**_SECURE_PRODUCTION, "database_url": "sqlite:///finview.db"})


def test_cloud_run_rejects_missing_production_environment(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "finview-api")

    with pytest.raises(RuntimeError, match="FINVIEW_ENV=production"):
        Settings(env="local")
