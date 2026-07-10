"""ReconnectingTransport — broker-invariant reconnect loop.

Owns lifecycle (should_retry / delay / attempt counting). Feed decoding and
socket I/O stay in the broker wire adapter; this module only drives policy.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from brokers.common.transport_policy import ResiliencePolicy

T = TypeVar("T")


class ReconnectingTransport:
    """Policy-driven reconnect helper.

    Typical use inside a broker WS loop::

        transport = ReconnectingTransport(ResiliencePolicy.for_dhan_ws())
        while not stop.is_set():
            try:
                connect_and_run()
                transport.reset()
            except Exception:
                if not transport.should_retry():
                    break
                time.sleep(transport.next_delay())
                transport.record_failure()
    """

    def __init__(self, policy: ResiliencePolicy | None = None) -> None:
        self._policy = policy or ResiliencePolicy()
        self._attempts = 0

    @property
    def policy(self) -> ResiliencePolicy:
        return self._policy

    @property
    def attempts(self) -> int:
        return self._attempts

    def should_retry(self) -> bool:
        return self._policy.should_retry(self._attempts)

    def next_delay(self, *, with_jitter: bool = True) -> float:
        return self._policy.delay_for(self._attempts, with_jitter=with_jitter)

    def record_failure(self) -> None:
        self._attempts += 1

    def reset(self) -> None:
        self._attempts = 0

    def run_until(
        self,
        connect_fn: Callable[[], T],
        *,
        should_stop: Callable[[], bool],
        sleep_fn: Callable[[float], None],
        on_failure: Callable[[BaseException], None] | None = None,
    ) -> T | None:
        """Run ``connect_fn`` until success, stop, or policy exhaustion.

        Returns the last successful result, or None if stopped/exhausted.
        """
        last: T | None = None
        while not should_stop():
            try:
                last = connect_fn()
                self.reset()
                return last
            except BaseException as exc:
                if on_failure is not None:
                    on_failure(exc)
                if not self.should_retry() or should_stop():
                    return last
                sleep_fn(self.next_delay())
                self.record_failure()
        return last


__all__ = ["ReconnectingTransport"]
