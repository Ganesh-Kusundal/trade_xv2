"""Tests for the lightweight CLI command registry.

The registry is a single dispatch table (``DISPATCH_TABLE``) populated
at import time of ``cli/main.py`` via ``register_handler(name, fn)``.

These tests verify:

* The registry can be populated independently of ``main.py``.
* ``register_handler`` rejects empty inputs.
* ``lookup_handler`` raises ``KeyError`` for unknown commands.
* The registry is reset-clean across tests.
* ``cli/main.py`` registers every name in
  :data:`cli.tests.endpoint_manifest.TOP_LEVEL_COMMANDS` — preventing
  silent drift when new commands are added.
"""

from __future__ import annotations

import pytest

from interface.ui.commands import registry
from tests.component.ui.endpoint_manifest import TOP_LEVEL_COMMANDS


@pytest.fixture(autouse=True)
def _isolate_registry() -> None:
    """Save and restore the registry so a test does not leak entries."""
    saved = dict(registry.DISPATCH_TABLE)
    try:
        yield
    finally:
        registry.DISPATCH_TABLE.clear()
        registry.DISPATCH_TABLE.update(saved)


def test_register_handler_adds_entry() -> None:
    registry.register_handler("test-cmd", lambda a, b, c: None)
    assert "test-cmd" in registry.DISPATCH_TABLE


def test_register_handler_overwrites_existing() -> None:
    registry.register_handler("test-cmd", lambda a, b, c: "first")
    registry.register_handler("test-cmd", lambda a, b, c: "second")
    assert registry.DISPATCH_TABLE["test-cmd"](None, None, None) == "second"


def test_register_handler_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="name"):
        registry.register_handler("", lambda a, b, c: None)


def test_lookup_handler_returns_callable() -> None:
    fn = lambda a, b, c: None  # noqa: E731
    registry.register_handler("alpha", fn)
    assert registry.lookup_handler("alpha") is fn


def test_lookup_handler_raises_keyerror_for_unknown_command() -> None:
    with pytest.raises(KeyError, match="nope"):
        registry.lookup_handler("nope")


def test_reset_clears_entries() -> None:
    registry.register_handler("a", lambda a, b, c: None)
    registry.register_handler("b", lambda a, b, c: None)
    assert len(registry.DISPATCH_TABLE) == 2
    registry.reset()
    assert registry.DISPATCH_TABLE == {}


def test_module_path_for_returns_handler_module() -> None:
    registry.register_handler("broker", lambda a, b, c: None)
    path = registry.module_path_for("broker")
    assert isinstance(path, str)


def test_module_path_for_raises_for_unknown() -> None:
    with pytest.raises(KeyError):
        registry.module_path_for("nonexistent")


# ── Manifest-driven contract checks (T0) ───────────────────────────────


def test_manifest_is_nonempty() -> None:
    # Threshold dropped from 40 by the analytics-first CLI pivot (2026-07-14),
    # which removed the order/position/portfolio/execution command surface.
    assert len(TOP_LEVEL_COMMANDS) >= 25, (
        "endpoint_manifest.TOP_LEVEL_COMMANDS must list every CLI "
        "command. If this fails, you probably removed a command from "
        "the router without updating the manifest."
    )
    assert len(set(TOP_LEVEL_COMMANDS)) == len(TOP_LEVEL_COMMANDS), (
        "TOP_LEVEL_COMMANDS contains duplicates"
    )


def test_main_module_populates_registry_on_import() -> None:
    """Importing cli.main must register every manifest top-level command."""
    import interface.ui.main  # noqa: F401 — side effect: populates DISPATCH_TABLE

    missing = [name for name in TOP_LEVEL_COMMANDS if name not in registry.DISPATCH_TABLE]
    assert not missing, f"cli/main.py does not register these commands: {missing}"


def test_no_unexpected_commands_in_dispatch() -> None:
    """If cli/main.py adds a new command, the manifest must be updated."""
    import interface.ui.main  # noqa: F401 — side effect: populates DISPATCH_TABLE

    extra = set(registry.DISPATCH_TABLE) - set(TOP_LEVEL_COMMANDS)
    assert not extra, (
        f"cli/main.py routes new commands not in endpoint_manifest: "
        f"{sorted(extra)}. Add them to cli/tests/endpoint_manifest.py."
    )
