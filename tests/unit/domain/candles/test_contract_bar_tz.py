"""ContractBar timezone enforcement."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from domain.candles.contract_historical import ContractBar


def _bar(**kwargs):
    defaults = dict(
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        instrument_id="NFO:NIFTY24JAN24000CE",
        symbol="NIFTY24JAN24000CE",
        underlying="NIFTY",
        exchange="NFO",
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=100,
    )
    defaults.update(kwargs)
    return ContractBar(**defaults)


def test_contract_bar_accepts_aware_timestamp() -> None:
    bar = _bar()
    assert bar.timestamp.tzinfo is not None


def test_contract_bar_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="ContractBar.timestamp"):
        _bar(timestamp=datetime(2024, 1, 1))
