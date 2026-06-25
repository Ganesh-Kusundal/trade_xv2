"""Deprecated shim — import from :mod:`application.oms._internal.reentrancy_guard`.

This module is kept for backward compatibility. Remove after v0.2.
"""

from __future__ import annotations

from application.oms._internal.reentrancy_guard import _ReentrancyGuard  # noqa: F401

__all__ = ["_ReentrancyGuard"]
"""Shared re-entrancy guard for event handler depth tracking.

Used by :class:`OrderManager` and :class:`PositionManager` to prevent
re-entrant calls into the same handler.
"""

from __future__ import annotations


class _ReentrancyGuard:
    """Context manager that atomically checks and increments a handler-depth counter.

    Eliminates the duplicated try/finally pattern from event handlers
    in :class:`OrderManager` and :class:`PositionManager`.  On ``__enter__``
    the ``reentered`` flag records whether a handler was already active
    (``_handler_depth > 0`` before incrementing).  The caller checks
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
        with self._lock:
            self.reentered = self._owner._handler_depth > 0
            self._owner._handler_depth += 1
        return self

    def __exit__(self, *args) -> None:
        with self._lock:
            self._owner._handler_depth -= 1
