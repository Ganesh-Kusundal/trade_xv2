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
* ``cli/main.py`` registers every name in
  :data:`cli.tests.endpoint_manifest.TOP_LEVEL_COMMANDS` and the
  module-path table (``COMMANDS``) matches the dispatch table
  (``DISPATCH_TABLE``) — preventing silent drift when new commands
  are added.
"""

from __future__ import annotations

import pytest

from cli.commands import registry
from cli.tests.endpoint_manifest import TOP_LEVEL_COMMANDS


@pytest.fixture(autouse=True)
def _isolate_registry() -> None:
    """Save and restore the registry so a test does not leak entries."""
    saved = dict(registry.COMMANDS)
    saved_dispatch = dict(registry.DISPATCH_TABLE)
    try:
        yield
    finally:
        registry.COMMANDS.clear()
        registry.COMMANDS.update(saved)
        registry.DISPATCH_TABLE.clear()
        registry.DISPATCH_TABLE.update(saved_dispatch)


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


# ── Manifest-driven contract checks (T0) ───────────────────────────────
#
# The names below are the canonical CLI surface. They must match the
# dispatch table populated by ``cli/main.py`` at import time. Adding a
# new CLI command without updating ``endpoint_manifest.py`` will fail
# this test.


def test_manifest_is_nonempty() -> None:
    assert len(TOP_LEVEL_COMMANDS) >= 40, (
        "endpoint_manifest.TOP_LEVEL_COMMANDS must list every CLI "
        "command. If this fails, you probably removed a command from "
        "the router without updating the manifest."
    )
    assert len(set(TOP_LEVEL_COMMANDS)) == len(TOP_LEVEL_COMMANDS), (
        "TOP_LEVEL_COMMANDS contains duplicates"
    )


def test_main_module_populates_registry_on_import() -> None:
    """Importing cli.main must register every manifest top-level command.

    Both the module-path table (``COMMANDS``) and the dispatch table
    (``DISPATCH_TABLE``) must contain every name. If either is
    missing an entry, the next test will catch the divergence.
    """
    import cli.main  # noqa: F401 — triggers register() calls

    missing_from_commands = [
        name for name in TOP_LEVEL_COMMANDS if name not in registry.COMMANDS
    ]
    missing_from_dispatch = [
        name for name in TOP_LEVEL_COMMANDS if name not in registry.DISPATCH_TABLE
    ]
    assert not missing_from_commands, (
        f"cli/main.py does not register these commands in COMMANDS: "
        f"{missing_from_commands}"
    )
    assert not missing_from_dispatch, (
        f"cli/main.py does not register these commands in DISPATCH_TABLE: "
        f"{missing_from_dispatch}"
    )


def test_commands_table_matches_dispatch_table() -> None:
    """The two registry tables must be in lockstep.

    The dispatch table is what the router actually uses; COMMANDS is
    a discoverability aid. A drift between them means a command is
    either un-routable or un-discoverable — both are bugs.
    """
    import cli.main  # noqa: F401

    in_commands_only = set(registry.COMMANDS) - set(registry.DISPATCH_TABLE)
    in_dispatch_only = set(registry.DISPATCH_TABLE) - set(registry.COMMANDS)
    assert not in_commands_only, (
        f"commands present in COMMANDS but missing from DISPATCH_TABLE "
        f"(un-routable): {sorted(in_commands_only)}"
    )
    assert not in_dispatch_only, (
        f"commands present in DISPATCH_TABLE but missing from COMMANDS "
        f"(un-discoverable): {sorted(in_dispatch_only)}"
    )


def test_no_unexpected_commands_in_dispatch() -> None:
    """If cli/main.py adds a new command, the manifest must be updated.

    This is the inverse of the previous test — it catches a new
    command being added to the router but forgotten in
    ``endpoint_manifest.py``.
    """
    import cli.main  # noqa: F401

    extra = set(registry.DISPATCH_TABLE) - set(TOP_LEVEL_COMMANDS)
    assert not extra, (
        f"cli/main.py routes new commands not in endpoint_manifest: "
        f"{sorted(extra)}. Add them to cli/tests/endpoint_manifest.py."
    )
