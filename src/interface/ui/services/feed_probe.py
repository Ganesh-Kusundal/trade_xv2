"""FeedProbe — broker-agnostic live-feed smoke logic.

Pure (no rich / CLI deps) so it is unit-testable with a fake
``DataProvider`` and reusable by the CLI and a future API endpoint.

Usage::

    result = FeedProbe().run(instrument, duration_s=10, depth=False)
    if result.is_healthy():
        ...
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from domain.instruments.instrument import Instrument

logger = logging.getLogger(__name__)


@dataclass
class FeedProbeResult:
    """Outcome of a single live-feed probe."""

    instrument_id: str
    depth_mode: bool
    duration_s: float
    tick_count: int = 0
    depth_count: int = 0
    first_frame_latency_s: float | None = None
    errors: list[str] = field(default_factory=list)
    started_at: str = ""
    ended_at: str = ""

    @property
    def total_frames(self) -> int:
        return self.tick_count + self.depth_count

    def is_healthy(self) -> bool:
        """Healthy == at least one frame arrived and no errors captured."""
        return self.total_frames > 0 and not self.errors


class FeedProbe:
    """Subscribe to an instrument and assert frames arrive within a window."""

    def run(
        self,
        instrument: Instrument,
        *,
        duration_s: float = 10.0,
        depth: bool = False,
    ) -> FeedProbeResult:
        started = datetime.now(timezone.utc)
        result = FeedProbeResult(
            instrument_id=str(instrument.id),
            depth_mode=depth,
            duration_s=duration_s,
            started_at=started.isoformat(),
        )

        def _on_frame(iid: Any, payload: Any) -> None:
            now = datetime.now(timezone.utc)
            if result.first_frame_latency_s is None:
                result.first_frame_latency_s = (now - started).total_seconds()
            from domain.entities.market import MarketDepth, QuoteSnapshot

            if isinstance(payload, MarketDepth):
                result.depth_count += 1
            elif isinstance(payload, QuoteSnapshot):
                result.tick_count += 1
            else:
                # Raw dict / unknown fallback (e.g. REST polling path).
                result.tick_count += 1

        try:
            provider = instrument._resolve_provider()
            handle = provider.subscribe(instrument.id, _on_frame, depth=depth)
            instrument._subscription = handle
        except Exception as exc:
            result.errors.append(f"subscribe_failed: {exc}")
            result.ended_at = datetime.now(timezone.utc).isoformat()
            return result

        try:
            time.sleep(max(0.0, duration_s))
        finally:
            # Always tear down — never leak a subscription.
            try:
                instrument.unsubscribe()
            except Exception as exc:
                result.errors.append(f"unsubscribe_failed: {exc}")
            result.ended_at = datetime.now(timezone.utc).isoformat()
        return result
