"""Ambient Session ContextVar — notebook / multi-session provider resolution.

Used by :class:`~domain.instruments.instrument.Instrument` when no explicit
``DataProvider`` was stamped. See OBJECT_MODEL_COMPLETION_DESIGN KD-1.

Threading: ContextVars do **not** auto-propagate to ``ThreadPoolExecutor``
workers unless ``contextvars.copy_context().run(...)`` is used. Prefer
Universe-stamped instruments in worker threads.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from domain.universe import Session

_ambient: ContextVar["Session | None"] = ContextVar("ambient_session", default=None)


def get_ambient_session() -> "Session | None":
    """Return the ambient Session for this context, or None."""
    return _ambient.get()


def set_ambient_session(session: "Session | None") -> Token:
    """Set ambient Session; return token for :func:`reset_ambient_session`."""
    return _ambient.set(session)


def reset_ambient_session(token: Token) -> None:
    """Restore ambient Session to the value before the matching set."""
    _ambient.reset(token)


def clear_ambient_session_if_current(session: "Session") -> None:
    """Clear ambient only if *session* is still the active ambient."""
    if _ambient.get() is session:
        _ambient.set(None)


@contextmanager
def activate_session(session: "Session") -> Iterator["Session"]:
    """Nested-safe activation for notebooks / multi-session REPL.

    Pushes ambient Session and (temporarily) the process default provider
    so bare ``Equity("X")`` resolves during the block.
    """
    from domain.ports.provider_registry import get_default_provider, set_default_provider

    token = set_ambient_session(session)
    prev_default = get_default_provider()
    set_default_provider(session.provider)
    try:
        yield session
    finally:
        reset_ambient_session(token)
        if get_default_provider() is session.provider:
            set_default_provider(prev_default)
