"""Tick authority — StreamOrchestrator is canonical; EventBus TICK is fan-out (MD-001).

Consumers must not treat callback and bus paths as independent sources of truth.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_stream_to_bus_wired: bool = False
_live_bar_sink_wired: bool = False
_last_tick_publish_monotonic: float | None = None


@dataclass(frozen=True)
class TickAuthorityStatus:
    """Runtime snapshot for health probes and architecture tests."""

    stream_to_bus: bool = False
    live_bar_sink: bool = False
    last_tick_publish_age_s: float | None = None


def should_publish_tick_directly() -> bool:
    """True when broker may publish TICK to EventBus (no orchestrator authority)."""
    return not _stream_to_bus_wired


def mark_stream_to_bus_wired() -> None:
    global _stream_to_bus_wired
    _stream_to_bus_wired = True
    logger.info("tick_authority: stream_orchestrator → EventBus TICK")


def mark_live_bar_sink_wired() -> None:
    global _live_bar_sink_wired
    _live_bar_sink_wired = True
    logger.info("tick_authority: EventBus TICK → live_bar_sink")


def record_tick_publish() -> None:
    global _last_tick_publish_monotonic
    _last_tick_publish_monotonic = time.monotonic()


def tick_authority_status() -> TickAuthorityStatus:
    age: float | None = None
    if _last_tick_publish_monotonic is not None:
        age = time.monotonic() - _last_tick_publish_monotonic
    return TickAuthorityStatus(
        stream_to_bus=_stream_to_bus_wired,
        live_bar_sink=_live_bar_sink_wired,
        last_tick_publish_age_s=age,
    )


def reset_tick_authority_for_tests() -> None:
    """Test-only reset."""
    global _stream_to_bus_wired, _live_bar_sink_wired, _last_tick_publish_monotonic
    _stream_to_bus_wired = False
    _live_bar_sink_wired = False
    _last_tick_publish_monotonic = None


@dataclass
class LiveBarSinkSLO:
    """ponytail: documented SLO for live→lake path; enforcement is metric + ops."""

    max_merge_write_ms: float = 500.0
    max_catalog_refresh_ms: float = 2000.0
    notes: str = field(
        default="1m bars only; sync merge-write; burst backlog possible under tick flood"
    )
