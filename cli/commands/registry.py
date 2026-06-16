"""Lightweight command registry — used by tests and the future router.

The :class:`OrderManager`-style refactor of ``cli/main.py`` is out of
scope for this iteration. We add this module so that every subcommand
that ``main.py`` already routes to is *also* discoverable by name, with
zero risk to the existing ``elif`` chain.

Conventions
-----------
* Each command is registered exactly once at import time of
  ``cli/main.py`` via a ``register(name, module)`` call. Module name is
  the dotted import path (e.g. ``"cli.commands.broker"``) so a future
  router can ``importlib.import_module(module).run(...)``.
* Tests do **not** import ``cli/main.py`` — they exercise the registry
  directly. The main module is reserved for the live CLI.
"""

from __future__ import annotations

COMMANDS: dict[str, str] = {}


def register(name: str, module: str) -> None:
    """Register a CLI subcommand.

    Parameters
    ----------
    name:
        Subcommand name as it would appear on the CLI (e.g. ``"broker"``).
    module:
        Dotted Python module path that exposes the ``run`` (or domain
        equivalent) entry point.
    """
    if not name:
        raise ValueError("register: command name must be non-empty")
    if not module:
        raise ValueError("register: module path must be non-empty")
    COMMANDS[name] = module


def lookup(name: str) -> str:
    """Return the module path registered for ``name``.

    Raises
    ------
    KeyError
        If ``name`` is not registered. Callers should treat the
        ``KeyError`` as "unknown command".
    """
    if name not in COMMANDS:
        raise KeyError(f"unknown command: {name!r}")
    return COMMANDS[name]


def reset() -> None:
    """Clear the registry. Intended for tests only."""
    COMMANDS.clear()


__all__ = ["COMMANDS", "lookup", "register", "reset"]
