"""Concurrent get_active_adapter() must not raise ExchangeNotConfigured.

Regression guard for a real bug hit while running a parallel datalake
sync (batch_execute's ThreadPoolExecutor, 5 workers): discover() sets
_discovered=True as its first line, before _active_adapter is actually
populated (plugin import takes measurable time). A concurrent thread
reading both flags unlocked -- even behind a "double-checked" lock that
only guards the discover() call itself, not the read of _discovered
before deciding whether to acquire the lock -- can observe the exact
transitional state (_discovered=True, _active_adapter=None) and raise,
a few milliseconds before the discovering thread would have succeeded.
Reproduced directly: 4 of 5 threads failed before the fix; the fix
serializes the entire read-check-return under one lock.
"""

from __future__ import annotations

import threading

from datalake.exchange_registry import _ExchangeState, get_active_exchange_code


def test_concurrent_get_active_exchange_code_never_raises():
    _ExchangeState._active_adapter = None
    _ExchangeState._discovered = False

    results: dict[str, object] = {}

    def worker(name: str) -> None:
        try:
            results[name] = get_active_exchange_code()
        except Exception as exc:  # noqa: BLE001 - capturing for assertion below
            results[name] = exc

    # Repeat several trials with fresh state each time -- a race doesn't
    # necessarily reproduce on every run.
    for trial in range(10):
        _ExchangeState._active_adapter = None
        _ExchangeState._discovered = False
        threads = [
            threading.Thread(target=worker, args=(f"t{trial}_{i}",)) for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    failures = {k: v for k, v in results.items() if isinstance(v, Exception)}
    assert not failures, f"{len(failures)}/{len(results)} concurrent calls raised: {failures}"
    assert all(v == "NSE" for v in results.values())
