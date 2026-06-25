"""Lightweight command registry — used by tests and the main CLI router.

P0-10 (2026-06-17): added ``CommandResult``, ``DISPATCH_TABLE``, and
``register_handler`` / ``lookup_handler`` so ``cli/main.py`` can use a
dict-based dispatch instead of the hand-rolled ``if/elif`` chain.

Conventions
-----------
* Each command is registered exactly once at import time of
  ``cli/main.py`` via a ``register(name, module)`` call (module-path
  lookup, retained for discoverability) and a ``register_handler(name, fn)``
  call (runtime dispatch).
* Handler signatures are normalized to
  ``(args: list[str], broker_service, console: Console) -> CommandResult | None``.
* Tests do **not** import ``cli/main.py`` — they exercise the registry
  directly. The main module is reserved for the live CLI.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CommandResult:
    """Result of a CLI command execution.

    Carries structured data for ``--json`` output mode and a canonical
    exit code so the router in ``cli/main.py`` never forgets to call
    ``sys.exit()`` (I-10).
    """

    success: bool = True
    data: Any = None
    error: str | None = None
    exit_code: int = field(default=0)

    def __post_init__(self) -> None:
        if not self.success and self.exit_code == 0:
            self.exit_code = 1


# ── Module-path table (discoverability, kept for tests) ────────────────────
COMMANDS: dict[str, str] = {}


def register(name: str, module: str) -> None:
    """Register a CLI subcommand's module path.

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


# ── Dispatch table (runtime routing, P0-10) ────────────────────────────────
# Handler: (args: list[str], broker_service, console: Console) -> CommandResult | None
DISPATCH_TABLE: dict[str, Callable[..., CommandResult | None]] = {}


def register_handler(name: str, handler: Callable[..., CommandResult | None]) -> None:
    """Register a dispatch handler for ``name``.

    The handler receives ``(args, broker_service, console)`` and
    returns a :class:`CommandResult` or ``None``.  Commands whose
    native signature differs should be wrapped in a lambda or adapter
    at registration time in ``cli/main.py``.
    """
    if not name:
        raise ValueError("register_handler: command name must be non-empty")
    DISPATCH_TABLE[name] = handler


def lookup_handler(name: str) -> Callable[..., CommandResult | None]:
    """Return the dispatch handler for ``name``.

    Raises
    ------
    KeyError
        If ``name`` is not registered in the dispatch table.
    """
    if name not in DISPATCH_TABLE:
        raise KeyError(f"unknown command: {name!r}")
    return DISPATCH_TABLE[name]


def reset() -> None:
    """Clear the registry. Intended for tests only."""
    COMMANDS.clear()
    DISPATCH_TABLE.clear()


__all__ = [
    "COMMANDS",
    "DISPATCH_TABLE",
    "CommandResult",
    "lookup",
    "lookup_handler",
    "register",
    "register_handler",
    "reset",
]
