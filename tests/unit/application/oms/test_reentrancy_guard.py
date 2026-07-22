"""R1: per-thread reentrancy depth — concurrent handlers must not bail as reentered."""

from __future__ import annotations

import threading

from application.oms._internal.reentrancy_guard import _ReentrancyGuard


class _Owner:
    def __init__(self) -> None:
        import threading as th

        self._lock = th.Lock()


def test_concurrent_handlers_are_not_treated_as_reentered() -> None:
    owner = _Owner()
    entered: list[bool] = []
    barrier = threading.Barrier(2)

    def worker() -> None:
        barrier.wait()
        with _ReentrancyGuard(owner._lock, owner) as guard:
            entered.append(guard.reentered)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert entered == [False, False]


def test_same_thread_reentry_is_detected() -> None:
    owner = _Owner()
    with _ReentrancyGuard(owner._lock, owner) as outer:
        assert outer.reentered is False
        with _ReentrancyGuard(owner._lock, owner) as inner:
            assert inner.reentered is True
