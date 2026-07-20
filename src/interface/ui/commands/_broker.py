"""ponytail: broker id + history→DataFrame helpers for CLI commands."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from interface.ui.services.broker_service import BrokerService


def broker_id_from(service: BrokerService | None, *, default: str = "paper") -> str:
    if service is None:
        return default.lower()
    return (service.active_broker_name or default).lower()


def history_as_df(series: Any) -> pd.DataFrame:
    if hasattr(series, "to_dataframe"):
        return series.to_dataframe()
    if hasattr(series, "bars"):
        bars = getattr(series, "bars", []) or []
        return pd.DataFrame(
            [
                {
                    "timestamp": getattr(b, "timestamp", None),
                    "open": float(getattr(b, "open", 0)),
                    "high": float(getattr(b, "high", 0)),
                    "low": float(getattr(b, "low", 0)),
                    "close": float(getattr(b, "close", 0)),
                    "volume": int(getattr(b, "volume", 0)),
                }
                for b in bars
            ]
        )
    return series
