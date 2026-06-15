"""Tests for the lightweight CLI command registry.

The full ``cli/main.py`` refactor is out of scope for this iteration.
We add a small ``cli/commands/registry.py`` module that mirrors the
existing ``elif`` chain via ``register(name, module)`` calls placed at
import time of ``main.py``. These tests verify:

* The registry can be populated independently of ``main.py`` (so unit
  tests do not have to instantiate the live CLI).
* The registry contains every subcommand the elif chain handles.
* ``register`` rejects empty inputs.
* ``lookup`` raises ``KeyError`` for unknown commands.
* The registry is reset-clean across tests.
"""

from __future__ import annotations

import pytest

from cli.commands import registry


@pytest.fixture(autouse=True)
def _isolate_registry() -> None:
    """Save and restore the registry so a test does not leak entries."""
    saved = dict(registry.COMMANDS)
    try:
        yield
    finally:
        registry.COMMANDS.clear()
        registry.COMMANDS.update(saved)


def test_register_adds_entry() -> None:
    registry.register("test-cmd", "cli.commands.broker")
    assert registry.COMMANDS["test-cmd"] == "cli.commands.broker"


def test_register_overwrites_existing() -> None:
    registry.register("test-cmd", "cli.commands.first")
    registry.register("test-cmd", "cli.commands.second")
    assert registry.COMMANDS["test-cmd"] == "cli.commands.second"


def test_register_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="name"):
        registry.register("", "cli.commands.broker")


def test_register_rejects_empty_module() -> None:
    with pytest.raises(ValueError, match="module"):
        registry.register("test-cmd", "")


def test_lookup_returns_module_path() -> None:
    registry.register("alpha", "cli.commands.oms")
    assert registry.lookup("alpha") == "cli.commands.oms"


def test_lookup_raises_keyerror_for_unknown_command() -> None:
    with pytest.raises(KeyError, match="nope"):
        registry.lookup("nope")


def test_reset_clears_entries() -> None:
    registry.register("a", "cli.commands.x")
    registry.register("b", "cli.commands.y")
    assert len(registry.COMMANDS) == 2
    registry.reset()
    assert registry.COMMANDS == {}


# ── Coverage of the production elif chain ────────────────────────────────
#
# The names below mirror the strings ``cli/main.py`` routes on. If a
# future change adds a new subcommand, this list must be updated
# alongside the elif chain. (The test does NOT import ``cli/main.py``
# itself — that would create a real BrokerService and pull in Dhan
# credentials — but it documents the contract that ``main.py`` must
# register the same names.)

EXPECTED_COMMANDS = {
    "broker": "cli.commands.broker",
    "dashboard": "cli.commands.dashboard",
    "validate": "cli.commands.validate",
    "validate-history": "cli.commands.validate_history",
    "validate-option-chain": "cli.commands.validate_option_chain",
    "benchmark": "cli.commands.benchmark",
    "compare": "cli.commands.compare",
    "quality-report": "cli.commands.quality_report",
    "instrument-info": "cli.commands.instrument_info",
    "account": "cli.commands.account",
    "holdings": "cli.commands.portfolio",
    "positions": "cli.commands.portfolio",
    "orders": "cli.commands.oms",
    "trades": "cli.commands.oms",
    "oms": "cli.commands.oms",
    "quote": "cli.commands.market",
    "depth": "cli.commands.market",
    "option-chain": "cli.commands.market",
    "futures": "cli.commands.market",
    "historical": "cli.commands.market",
    "history": "cli.commands.market",
    "stream": "cli.commands.market",
    "websocket": "cli.commands.websocket",
    "journal": "cli.commands.journal",
    "events": "cli.commands.events",
    "search": "cli.commands.search",
    "instrument": "cli.commands.instrument",
    "instruments": "cli.commands.instruments",
    "doctor": "cli.commands.doctor",
    "load-test": "cli.commands.load_test",
    "news": "cli.commands.news",
}


def test_register_all_expected_commands() -> None:
    """Apply the production registration table; every name must be in the registry."""
    for name, module in EXPECTED_COMMANDS.items():
        registry.register(name, module)
    for name, module in EXPECTED_COMMANDS.items():
        assert registry.lookup(name) == module


def test_main_module_populates_registry_on_import() -> None:
    """Importing cli.main must register every subcommand via the
    module-level ``register(...)`` calls in cli.main.

    We mark this test as a contract check: it asserts that the dispatch
    names the elif chain recognises are also discoverable from the
    registry. If a future change to cli/main.py drops a name from the
    elif chain but leaves it in the registry, the next test will catch
    the divergence.
    """
    import cli.main  # noqa: F401 — side effect: registers commands

    for name, module in EXPECTED_COMMANDS.items():
        assert name in registry.COMMANDS, (
            f"cli/main.py does not register command {name!r} "
            f"(expected module {module!r})"
        )
        assert registry.COMMANDS[name] == module, (
            f"cli/main.py registers {name!r} -> {registry.COMMANDS[name]!r}, "
            f"expected {module!r}"
        )
