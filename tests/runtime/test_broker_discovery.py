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


def test_open_session_invokes_entry_point_discovery():
    """Composition root (tradex.open_session) must run discover after
    ensure_core_plugins so out-of-tree tradex.brokers plugins load."""
    from tradex.session import open_session

    order: list[str] = []

    def _track_ensure():
        order.append("ensure")

    def _track_discover():
        order.append("discover")
        return ["paper"]

    with (
        patch("tradex.session.ensure_core_plugins", side_effect=_track_ensure),
        patch(
            "tradex.session.discover_broker_plugins",
            side_effect=_track_discover,
        ) as mock_discover,
        patch("tradex.session.get_broker_plugin", return_value=None),
        patch("tradex.session._normalize_mode", return_value="sim"),
        patch("tradex.session._ensure_broker_registered"),
        patch("tradex.session._is_live", return_value=False),
        patch(
            "infrastructure.gateway.factory.bootstrap_gateway",
            side_effect=RuntimeError("stop before full connect"),
        ),
    ):
        try:
            open_session("paper")
        except Exception:
            pass  # discovery runs before gateway bootstrap

    mock_discover.assert_called()
    assert "discover" in order
    assert order.index("ensure") < order.index("discover")
