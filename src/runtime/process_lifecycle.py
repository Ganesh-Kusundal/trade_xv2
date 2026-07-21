"""Process-scoped LifecycleManager — single owner for TOTP/WS background services."""

from __future__ import annotations

import threading

from infrastructure.lifecycle.lifecycle import LifecycleManager

_lock = threading.Lock()
_process_lifecycle: LifecycleManager | None = None


def get_process_lifecycle() -> LifecycleManager:
    """Return the shared process LifecycleManager (create on first use)."""
    global _process_lifecycle
    with _lock:
        if _process_lifecycle is None:
            _process_lifecycle = LifecycleManager()
        return _process_lifecycle


def set_process_lifecycle(lifecycle: LifecycleManager | None) -> None:
    """Replace or clear the process lifecycle (tests only)."""
    global _process_lifecycle
    with _lock:
        _process_lifecycle = lifecycle


def resolve_lifecycle(injected: LifecycleManager | None = None) -> LifecycleManager | None:
    """Use explicit lifecycle when provided; else reuse process singleton if set."""
    if injected is not None:
        return injected
    return _process_lifecycle
