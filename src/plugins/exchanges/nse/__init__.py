"""NSE exchange plugin — self-registers on import via ``tradex.exchanges`` entry-point.

Exposes module-level ``ADAPTER`` and ``CALENDAR`` for exchange discovery.
"""

from .adapter import NseExchangeAdapter
from .calendar import NseTradingCalendar

ADAPTER = NseExchangeAdapter()
CALENDAR = NseTradingCalendar()
