"""Shared re-entrancy guard for event handler depth tracking.

Used by :class:`OrderManager` and :class:`PositionManager` to prevent
re-entrant calls into the same handler on the *same thread*.

Concurrent handlers on different threads must not share one depth counter —
that falsely sets ``reentered`` and drops fills (Phase 1 D-07 / R1 fix).
"""

from __future__ import annotations

import threading


def _depth_local(owner: object) -> threading.local:
    local = getattr(owner, "reentrancy_depth_local", None)
    if local is None:
        local = threading.local()
        owner.reentrancy_depth_local = local  # type: ignore[attr-defined]
    if not hasattr(local, "depth"):
        local.depth = 0
    return local


class _ReentrancyGuard:
    """Context manager that atomically checks and increments a per-thread depth counter.

    Eliminates the duplicated try/finally pattern from event handlers
    in :class:`OrderManager` and :class:`PositionManager`.  On ``__enter__``
    the ``reentered`` flag records whether a handler was already active
    on this thread (``depth > 0`` before incrementing).  The caller checks
    ``guard.reentered`` to decide whether to bail out.

    Usage::

        with self._reentrancy_guard() as guard:
            if guard.reentered:
                return       # re-entered, skip
            # ... process event ...
    """

    __slots__ = ("_lock", "_owner", "reentered")

    def __init__(self, lock, owner) -> None:
        self._lock = lock
        self._owner = owner
        self.reentered = False

    def __enter__(self):
        local = _depth_local(self._owner)
        with self._lock:
            self.reentered = local.depth > 0
            local.depth += 1
        return self

    def __exit__(self, *args) -> None:
        local = _depth_local(self._owner)
        with self._lock:
            local.depth -= 1
