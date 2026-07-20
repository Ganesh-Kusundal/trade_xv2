"""ENG-018/ENG-004: architecture fitness — API defaults secure."""

from __future__ import annotations

from interface.api.config import APIConfig


def test_api_config_default_auth_is_none_for_local():
    """Local/single-operator default — prod/staging gate via TRADEX_ENV + profile."""
    assert APIConfig().auth_mode == "none"


def test_metrics_not_in_public_paths():
    from interface.api.auth import PUBLIC_PATHS

    assert "/metrics" not in PUBLIC_PATHS
    assert "/healthz" in PUBLIC_PATHS
