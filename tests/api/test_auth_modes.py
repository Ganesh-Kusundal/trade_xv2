"""Tests for api.auth — authentication modes and configuration."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

import api.auth


@pytest.fixture(autouse=True)
def _restore_auth_state():
    """Save and restore auth module globals after each test."""
    saved_mode = api.auth.AUTH_MODE
    saved_key = api.auth.API_KEY
    yield
    api.auth.AUTH_MODE = saved_mode
    api.auth.API_KEY = saved_key


class TestConfigure:
    def test_configure_sets_auth_mode_none(self):
        api.auth.configure(auth_mode="none")
        assert api.auth.AUTH_MODE == "none"
        assert api.auth.is_auth_enabled() is False

    def test_configure_sets_auth_mode_api_key(self):
        api.auth.configure(auth_mode="api_key", api_key="test-key-123")
        assert api.auth.AUTH_MODE == "api_key"
        assert api.auth.API_KEY == "test-key-123"
        assert api.auth.is_auth_enabled() is True

    def test_configure_generates_key_when_missing(self):
        api.auth.API_KEY = ""
        api.auth.configure(auth_mode="api_key")
        assert len(api.auth.API_KEY) > 0

    def test_configure_normalizes_case(self):
        api.auth.configure(auth_mode="NONE")
        assert api.auth.AUTH_MODE == "none"


class TestRequireAuth:
    @pytest.mark.asyncio
    async def test_no_auth_mode_passes(self):
        api.auth.configure(auth_mode="none")
        await api.auth.require_auth(x_api_key=None)

    @pytest.mark.asyncio
    async def test_api_key_mode_missing_key_raises(self):
        api.auth.configure(auth_mode="api_key", api_key="secret")
        with pytest.raises(HTTPException) as exc_info:
            await api.auth.require_auth(x_api_key=None)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_api_key_mode_invalid_key_raises(self):
        api.auth.configure(auth_mode="api_key", api_key="secret")
        with pytest.raises(HTTPException) as exc_info:
            await api.auth.require_auth(x_api_key="wrong")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_api_key_mode_valid_key_passes(self):
        api.auth.configure(auth_mode="api_key", api_key="secret")
        await api.auth.require_auth(x_api_key="secret")


class TestPublicPaths:
    def test_healthz_is_public(self):
        assert api.auth.is_public_path("/healthz") is True

    def test_docs_is_public(self):
        assert api.auth.is_public_path("/docs") is True

    def test_api_endpoint_not_public(self):
        assert api.auth.is_public_path("/api/v1/orders") is False


class TestGetApiKey:
    def test_returns_current_key(self):
        api.auth.configure(auth_mode="api_key", api_key="my-key")
        assert api.auth.get_api_key() == "my-key"
