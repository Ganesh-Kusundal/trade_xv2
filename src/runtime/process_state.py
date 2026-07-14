"""Single owner of process-wide mutable state.

The composition root is the ONLY place permitted to own process globals
(quota scheduler, etc.). Previously these lived as module-level singletons
in several ``runtime/*`` modules, which invited last-writer-wins clobbering
when multiple broker profiles initialized. See audit SMELL-9 / REF-9.

Access is via the accessors below; nothing else should hold a module-level
mutable singleton for process state.
"""

from __future__ import annotations

from typing import Any


_shared_quota: Any | None = None


def set_shared_quota_scheduler(scheduler: Any) -> None:
    """Register the process-wide QuotaScheduler (idempotent — first writer wins)."""
    global _shared_quota
    if _shared_quota is None:
        _shared_quota = scheduler


def get_shared_quota_scheduler() -> Any | None:
    """Return the process-wide QuotaScheduler, or None if not yet created."""
    return _shared_quota


def reset_process_state() -> None:
    """Reset all process state (test isolation only)."""
    global _shared_quota
    _shared_quota = None
