"""MCX exchange plugin — self-registers on import via ``tradex.exchanges`` entry-point.

Exposes module-level ``ADAPTER`` and ``CALENDAR`` for exchange discovery.
"""

from .adapter import McxExchangeAdapter
from .calendar import McxTradingCalendar

ADAPTER = McxExchangeAdapter()
CALENDAR = McxTradingCalendar()
