"""Shared instrument-master lifecycle — protocol + daily background refresh.

Mirrors :mod:`plugins.brokers.common.token_lifecycle`. Each broker's
``*Connection`` already has a blocking ``load_instruments()`` (downloads the
tokenless scrip master / complete.json, caches it daily, registers wire refs
in the resolver). This module adds the two things the connections lack:

* a single-flight ``ensure_fresh()`` shape (lazy trigger on first gateway
  call — ``load_instruments`` is only invoked once even under concurrency),
* a proactive ``InstrumentRefreshScheduler`` daemon thread (daily interval)
  so the on-disk cache stays fresh without waiting for the next gateway call.

Like ``token_lifecycle``, ``plugins/`` only depends on ``domain`` + ``shared``
— no infrastructure import — so the scheduler owns its own minimal lifecycle.
"""

from __future__ import annotations

import logging
import threading
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class InstrumentMasterPort(Protocol):
    """Common shape implemented by DhanConnection / UpstoxConnection."""

    def ensure_fresh(self, *, force_refresh: bool = False) -> None: ...

    def load_instruments(self) -> None: ...


class InstrumentRefreshScheduler:
    """Background thread that calls ``ensure_fresh()`` on a daily interval.

    Non-blocking on first tick: the very first gateway call triggers a load
    synchronously (see the connection's ``ensure_fresh``); this thread only
    refreshes the on-disk cache on a schedule so subsequent cold starts are
    instant. Refreshes are best-effort — a failure is logged, never raised,
    so a transient CDN hiccup can't take down the trading process.
    """

    def __init__(
        self,
        broker_id: str,
        master: InstrumentMasterPort,
        *,
        interval_seconds: float = 86_400.0,
    ) -> None:
        self.broker_id = broker_id
        self._master = master
        self._interval = interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._refresh_count = 0
        self._error_count = 0

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self, timeout_seconds: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout_seconds)
            self._thread = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval):
            self.refresh_now()

    def refresh_now(self) -> bool:
        try:
            # force_refresh=True so the daily tick re-downloads + re-caches.
            self._master.ensure_fresh(force_refresh=True)
            self._refresh_count += 1
            return True
        except Exception as exc:  # noqa: BLE001 — best-effort background refresh
            self._error_count += 1
            logger.warning(
                "instrument_refresh_failed",
                extra={"broker_id": self.broker_id, "error": str(exc)},
            )
            return False

    @property
    def refresh_count(self) -> int:
        return self._refresh_count

    @property
    def error_count(self) -> int:
        return self._error_count
