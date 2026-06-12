"""M4 — market/options adapters resolve symbols via shared InstrumentService."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from brokers.common.core.enums import ExchangeSegment
from brokers.dhan.instrument_service import InstrumentService
from brokers.dhan.market_data.market_data_adapter import DhanMarketDataProvider
from brokers.dhan.market_data.options_adapter import DhanOptionsAdapter

pytestmark = pytest.mark.unit


def _service(tmp_path: Path, csv_path: Path) -> InstrumentService:
    service = InstrumentService(cache_dir=tmp_path / "instr")
    service.load_snapshot(csv_path)
    return service


class TestMarketDataAdapterResolution:
    def test_historical_nifty_uses_index_instrument(
        self, tmp_path: Path, real_csv_path: Path
    ) -> None:
        service = _service(tmp_path, real_csv_path)
        captured: dict = {}

        def fake_history(security_id, segment, from_date, to_date, **kwargs):
            captured["security_id"] = security_id
            captured["segment"] = segment
            captured.update(kwargs)
            return []

        market_client = MagicMock()
        market_client.get_historical_data.side_effect = fake_history
        adapter = DhanMarketDataProvider(
            market_client,
            MagicMock(),
            service,
        )
        adapter.get_historical_intraday_for_symbol(
            "NIFTY",
            "IDX_I",
            date(2026, 1, 1),
            date(2026, 1, 5),
        )
        assert captured["instrument"] == "INDEX"
        assert captured["segment"] == ExchangeSegment.IDX_I

    def test_quote_reliance_resolves_security_id(
        self, tmp_path: Path, real_csv_path: Path
    ) -> None:
        service = _service(tmp_path, real_csv_path)
        market_client = MagicMock()
        market_client.get_quote.return_value = MagicMock(last_price=100)
        adapter = DhanMarketDataProvider(market_client, MagicMock(), service)
        adapter.get_quote_for_symbol("RELIANCE", "NSE")
        args = market_client.get_quote.call_args[0]
        assert args[0] == "2885"
        assert args[1] == ExchangeSegment.NSE


class TestOptionsAdapterUnderlyingRouting:
    def test_nifty_on_nfo_routes_to_idx_i(
        self, tmp_path: Path, real_csv_path: Path
    ) -> None:
        service = _service(tmp_path, real_csv_path)
        options_client = MagicMock()
        options_client.get_parsed_option_chain.return_value = []
        adapter = DhanOptionsAdapter(options_client, service)
        adapter.get_option_chain_for_symbol("NIFTY", "NFO", "2026-06-26")
        args = options_client.get_parsed_option_chain.call_args[0]
        assert args[1] == ExchangeSegment.IDX_I

    def test_expiries_use_underlying_resolution(
        self, tmp_path: Path, real_csv_path: Path
    ) -> None:
        service = _service(tmp_path, real_csv_path)
        options_client = MagicMock()
        options_client.get_expiries.return_value = ["2026-06-26"]
        adapter = DhanOptionsAdapter(options_client, service)
        adapter.get_expiries_for_symbol("NIFTY", "NFO")
        args = options_client.get_expiries.call_args[0]
        assert args[1] == ExchangeSegment.IDX_I
