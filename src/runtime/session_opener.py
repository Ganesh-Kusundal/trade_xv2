"""Composition-root registry for the session opener.

Mirrors ``runtime/replay_factory.py`` — domain stays pure, registry lives
at the composition root.
"""

from __future__ import annotations

from domain.ports.session_opener import SessionOpener

_session_opener: SessionOpener | None = None


def set_session_opener(opener: SessionOpener) -> None:
    """Register the canonical session opener (call at composition root)."""
    global _session_opener
    _session_opener = opener


def get_session_opener() -> SessionOpener:
    """Return the registered session opener."""
    if _session_opener is None:
        raise RuntimeError("session opener not wired at composition root")
    return _session_opener
