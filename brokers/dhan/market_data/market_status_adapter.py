"""Market status adapter for Dhan."""

from __future__ import annotations

from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from brokers.common.api.ports import MarketStatusProvider


class DhanMarketStatusProvider(MarketStatusProvider):
    """Dhan market/session status provider.

    Dhan does not expose a dedicated market-status REST endpoint in the current
    adapter surface, so this provider derives a conservative session state from
    the India/Kolkata trading calendar. It is intentionally small and can be
    replaced by a live endpoint if Dhan adds one.
    """

    def get_market_status(self) -> dict[str, Any]:
        tz = ZoneInfo("Asia/Kolkata")
        now = datetime.now(tz)
        weekday = now.weekday()
        market_open = weekday < 5 and time(9, 15) <= now.time() < time(15, 30)

        return {
            "market_open": market_open,
            "timezone": "Asia/Kolkata",
            "local_time": now.isoformat(),
            "source": "local_clock",
        }
