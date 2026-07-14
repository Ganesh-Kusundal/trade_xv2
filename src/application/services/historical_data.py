"""Historical data service — implementation lives in infrastructure.

Application no longer re-exports infrastructure (layering). Prefer::

    from infrastructure.historical_data import HistoricalDataService, ...

Or the runtime facade::

    from runtime.historical_data import HistoricalDataService, ...
"""

from __future__ import annotations

__all__: list[str] = []
