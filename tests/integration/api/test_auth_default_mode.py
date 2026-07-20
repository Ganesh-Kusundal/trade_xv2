"""Tests for api.auth — AUTH_MODE default security (Fix #6)."""

from __future__ import annotations

import importlib
import os
from unittest import mock


class TestAuthDefaultMode:
    """Fix #6: AUTH_MODE must default to 'api_key' when env var is unset."""

    def test_default_is_api_key_when_env_unset(self):
        """When AUTH_MODE is not set, is_auth_enabled() returns True."""
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUTH_MODE", None)
            import interface.api.auth as auth_mod

            importlib.reload(auth_mod)
            assert auth_mod.is_auth_enabled() is True

    def test_explicit_none_disables_auth(self):
        """When AUTH_MODE=none is explicitly set, auth is disabled."""
        with mock.patch.dict(os.environ, {"AUTH_MODE": "none"}, clear=False):
            import interface.api.auth as auth_mod

            importlib.reload(auth_mod)
            assert auth_mod.is_auth_enabled() is False

    def test_explicit_api_key_enables_auth(self):
        """When AUTH_MODE=api_key, auth is enabled."""
        with mock.patch.dict(os.environ, {"AUTH_MODE": "api_key"}, clear=False):
            import interface.api.auth as auth_mod

            importlib.reload(auth_mod)
            assert auth_mod.is_auth_enabled() is True
