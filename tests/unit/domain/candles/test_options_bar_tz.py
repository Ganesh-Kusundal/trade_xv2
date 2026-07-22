"""OptionsBar timezone enforcement."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from domain.candles.options_historical import OptionsBar


def _bar(**kwargs):
    defaults = dict(
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        symbol="NIFTY24JAN24000CE",
        underlying="NIFTY",
        exchange="NFO",
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=100,
        oi=1000,
        iv=0.2,
        spot=24000.0,
        strike=24000.0,
        strike_offset=0,
        option_type="CALL",
        expiry_kind="WEEK",
        expiry_code=1,
        interval_min=5,
        expiry_date="2024-01-25",
    )
    defaults.update(kwargs)
    return OptionsBar(**defaults)


def test_options_bar_accepts_aware_timestamp() -> None:
    bar = _bar()
    assert bar.timestamp.tzinfo is not None


def test_options_bar_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="OptionsBar.timestamp"):
        _bar(timestamp=datetime(2024, 1, 1))
