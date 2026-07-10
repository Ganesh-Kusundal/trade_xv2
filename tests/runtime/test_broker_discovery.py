"""Tests for runtime.broker_discovery — tradex.brokers entry-point discovery."""

from __future__ import annotations

from unittest.mock import patch

from runtime.broker_discovery import discover_broker_plugins


def test_discovers_the_three_built_in_brokers():
    discovered = discover_broker_plugins()
    assert set(discovered) == {"dhan", "upstox", "paper"}


def test_a_single_broken_plugin_does_not_abort_discovery_of_others():
    """One third-party plugin failing to import must not prevent the
    others (built-in or third-party) from loading."""
    import importlib

    real_import_module = importlib.import_module

    def _boom_on_dhan(name, *args, **kwargs):
        if name == "brokers.dhan":
            raise ImportError("simulated broken third-party plugin")
        return real_import_module(name, *args, **kwargs)

    with patch("runtime.broker_discovery.importlib.import_module", side_effect=_boom_on_dhan):
        discovered = discover_broker_plugins()

    assert "dhan" not in discovered
    assert "upstox" in discovered
    assert "paper" in discovered


def test_discovered_brokers_are_actually_registered():
    """Discovery should trigger real self-registration, not just import
    without side effects."""
    from infrastructure.broker_plugin import get_broker_plugin

    discover_broker_plugins()
    for broker_id in ("dhan", "upstox", "paper"):
        assert get_broker_plugin(broker_id) is not None
