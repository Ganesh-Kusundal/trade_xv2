"""ENG-018/ENG-004: architecture fitness — API defaults secure."""

from __future__ import annotations

from interface.api.config import APIConfig


def test_api_config_default_auth_is_api_key():
    assert APIConfig().auth_mode == "api_key"


def test_metrics_not_in_public_paths():
    from interface.api.auth import PUBLIC_PATHS

    assert "/metrics" not in PUBLIC_PATHS
    assert "/healthz" in PUBLIC_PATHS
