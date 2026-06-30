"""Lightweight command registry — used by tests and the main CLI router.

Conventions
-----------
* Each command is registered exactly once at import time of
  ``cli/main.py`` via ``register_handler(name, fn)``.
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


def module_path_for(name: str) -> str:
    """Derive the module path from the handler's ``__module__`` attribute.

    Raises
    ------
    KeyError
        If ``name`` is not registered.
    """
    handler = lookup_handler(name)
    return getattr(handler, "__module__", "<unknown>")


def reset() -> None:
    """Clear the registry. Intended for tests only."""
    DISPATCH_TABLE.clear()


__all__ = [
    "DISPATCH_TABLE",
    "CommandResult",
    "lookup_handler",
    "module_path_for",
    "register_handler",
    "reset",
]
