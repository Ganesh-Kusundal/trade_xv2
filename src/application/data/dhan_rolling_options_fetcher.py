"""Dhan rolling options fetch adapter for federated options sync."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Literal

import pandas as pd

from config.indices import get_index_entry
from datalake.core.option_format import (
    convert_from_dhan_rolling,
    lake_to_dhan_expiry_code,
    strike_offset_to_dhan_strike,
)

logger = logging.getLogger(__name__)

_REQUIRED_DATA = ["open", "high", "low", "close", "volume", "oi", "spot", "iv", "strike"]

OptionSide = Literal["CALL", "PUT"]
ExpiryKind = Literal["WEEK", "MONTH"]


class DhanRollingOptionsFetcher:
    """Fetch one rolling-option series from Dhan ``/charts/rollingoption``."""

    def __init__(
        self,
        gateway: Any,
        *,
        broker_id: str = "dhan",
        quota_acquire: Callable[..., Any] | None = None,
        quota_release: Callable[[Any], None] | None = None,
    ) -> None:
        self._gateway = gateway
        self._broker_id = broker_id
        self._quota_acquire = quota_acquire
        self._quota_release = quota_release

    def _security_id(self, underlying: str) -> int:
        entry = get_index_entry(underlying)
        if entry is None or not entry.dhan_security_id:
            raise ValueError(f"No Dhan security_id for underlying {underlying!r}")
        return int(entry.dhan_security_id)

    def _acquire_quota(self) -> Any | None:
        if self._quota_acquire is None:
            return None
        return self._quota_acquire(self._broker_id, "options_historical", "HISTORICAL_BACKFILL")

    def fetch_series(
        self,
        *,
        underlying: str,
        expiry_kind: ExpiryKind,
        expiry_code: int,
        strike_offset: int,
        option_type: OptionSide,
        from_date: str,
        to_date: str,
        interval_min: int = 5,
    ) -> pd.DataFrame:
        """Fetch and normalize one (strike, side) series for a date range."""
        token = self._acquire_quota()
        started = time.perf_counter()
        try:
            data = self._gateway.extended.data.get_expired_options_data(
                security_id=self._security_id(underlying),
                expiry_flag=expiry_kind,
                expiry_code=lake_to_dhan_expiry_code(expiry_code),
                strike=strike_offset_to_dhan_strike(strike_offset),
                option_type=option_type,
                from_date=from_date,
                to_date=to_date,
                required_data=_REQUIRED_DATA,
                interval=interval_min,
            )
        finally:
            if token is not None and self._quota_release is not None:
                self._quota_release(token)

        side_key = "ce" if option_type == "CALL" else "pe"
        side = data.get(side_key) if isinstance(data, dict) else None
        df = convert_from_dhan_rolling(
            side or {},
            underlying=underlying,
            expiry_kind=expiry_kind,
            expiry_code=expiry_code,
            strike_offset=strike_offset,
            option_type=option_type,
            interval_min=interval_min,
        )
        logger.debug(
            "dhan_rolling_fetch rows=%s underlying=%s %s code=%s offset=%s %s %.0fms",
            len(df),
            underlying,
            expiry_kind,
            expiry_code,
            strike_offset,
            option_type,
            (time.perf_counter() - started) * 1000,
        )
        return df
