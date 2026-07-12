"""Unit tests: Upstox native multi-key quotes (V3 LTP + full batch + mapper)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest

from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper
from brokers.upstox.market_data.client_v3 import UPSTOX_QUOTE_MAX_KEYS, UpstoxMarketDataV3Client
from brokers.upstox.market_data.market_data_adapter import UpstoxMarketDataAdapter, _chunked
from domain import Quote


# ---------------------------------------------------------------------------
# Mapper: multi-instrument + V3 LTP fields
# ---------------------------------------------------------------------------


class TestToQuotesMapper:
    def test_multi_instrument_full_quote_payload(self):
        payload = {
            "status": "success",
            "data": {
                "NSE_EQ:RELIANCE": {
                    "symbol": "RELIANCE",
                    "instrument_token": "NSE_EQ|INE002A01018",
                    "last_price": 2500.5,
                    "ohlc": {"open": 2490, "high": 2510, "low": 2480, "close": 2495},
                    "volume": 100,
                    "depth": {
                        "buy": [{"price": 2500, "quantity": 10, "orders": 1}],
                        "sell": [{"price": 2501, "quantity": 20, "orders": 2}],
                    },
                },
                "NSE_EQ:TCS": {
                    "symbol": "TCS",
                    "instrument_token": "NSE_EQ|INE467B01029",
                    "last_price": 3500.0,
                    "ohlc": {"open": 3480, "high": 3520, "low": 3470, "close": 3490},
                    "volume": 50,
                },
            },
        }
        quotes = UpstoxDomainMapper.to_quotes(payload)
        assert quotes["RELIANCE"].ltp == Decimal("2500.5")
        assert quotes["TCS"].ltp == Decimal("3500.0")
        assert quotes["NSE_EQ|INE002A01018"].symbol == "RELIANCE"
        assert quotes["NSE_EQ:RELIANCE"].bid == Decimal("2500")

    def test_v3_ltp_fields_cp_volume(self):
        payload = {
            "status": "success",
            "data": {
                "NSE_FO:NIFTY2543021600PE": {
                    "last_price": 303.9,
                    "instrument_token": "NSE_FO|51834",
                    "ltq": 75,
                    "volume": 170325,
                    "cp": 29.0,
                }
            },
        }
        q = UpstoxDomainMapper.to_quote(payload)
        assert q.ltp == Decimal("303.9")
        assert q.volume == 170325
        assert q.close == Decimal("29.0")  # V3 cp → close

        multi = UpstoxDomainMapper.to_quotes(payload)
        assert multi["NSE_FO|51834"].ltp == Decimal("303.9")

    def test_v3_live_ohlc_fallback(self):
        payload = {
            "data": {
                "NSE_EQ:X": {
                    "last_price": 100,
                    "instrument_token": "NSE_EQ|X",
                    "live_ohlc": {
                        "open": 99,
                        "high": 101,
                        "low": 98,
                        "close": 100.5,
                        "volume": 9,
                        "ts": 1,
                    },
                }
            }
        }
        q = UpstoxDomainMapper.to_quote(payload)
        assert q.open == Decimal("99")
        assert q.high == Decimal("101")
        assert q.close == Decimal("100.5")


# ---------------------------------------------------------------------------
# Chunking helper
# ---------------------------------------------------------------------------


class TestChunked:
    def test_chunks_at_500(self):
        keys = [f"K{i}" for i in range(1200)]
        chunks = _chunked(keys, UPSTOX_QUOTE_MAX_KEYS)
        assert len(chunks) == 3
        assert len(chunks[0]) == 500
        assert len(chunks[1]) == 500
        assert len(chunks[2]) == 200

    def test_empty(self):
        assert _chunked([], 500) == []


# ---------------------------------------------------------------------------
# Adapter batch (mocked HTTP clients)
# ---------------------------------------------------------------------------


def _v2_v3_pair(full_body: dict | None = None, ltp_body: dict | None = None):
    v2 = MagicMock()
    v3 = MagicMock()
    if full_body is not None:
        v2.get_quote.return_value = full_body
    if ltp_body is not None:
        v3.get_ltp_v3.return_value = ltp_body
    hist = MagicMock()
    return v2, v3, hist


class TestMarketDataAdapterBatch:
    def test_quotes_batch_single_http_for_small_list(self):
        body = {
            "data": {
                "NSE_EQ:RELIANCE": {
                    "symbol": "RELIANCE",
                    "instrument_token": "NSE_EQ|INE002A01018",
                    "last_price": 100,
                    "volume": 1,
                },
                "NSE_EQ:TCS": {
                    "symbol": "TCS",
                    "instrument_token": "NSE_EQ|INE467B01029",
                    "last_price": 200,
                    "volume": 2,
                },
            }
        }
        v2, v3, hist = _v2_v3_pair(full_body=body)
        adapter = UpstoxMarketDataAdapter(v2, v3, hist)
        result = adapter.quotes_batch(
            ["NSE_EQ|INE002A01018", "NSE_EQ|INE467B01029"]
        )
        v2.get_quote.assert_called_once()
        args = v2.get_quote.call_args[0][0]
        assert len(args) == 2
        assert result["RELIANCE"].ltp == Decimal("100")
        assert result["TCS"].ltp == Decimal("200")

    def test_quotes_batch_chunks_above_500(self):
        def _make_body(keys: list[str]) -> dict[str, Any]:
            return {
                "data": {
                    k: {
                        "symbol": k.split("|")[-1],
                        "instrument_token": k,
                        "last_price": 1.0,
                    }
                    for k in keys
                }
            }

        v2 = MagicMock()
        v2.get_quote.side_effect = lambda keys: _make_body(keys)
        v3 = MagicMock()
        hist = MagicMock()
        adapter = UpstoxMarketDataAdapter(v2, v3, hist, max_keys_per_request=500)
        keys = [f"NSE_EQ|ID{i}" for i in range(501)]
        result = adapter.quotes_batch(keys)
        assert v2.get_quote.call_count == 2
        assert len(result) >= 501  # aliases inflate; at least one entry per symbol tail

    def test_ltps_batch_prefers_v3(self):
        ltp_body = {
            "data": {
                "NSE_EQ:RELIANCE": {
                    "last_price": 111.1,
                    "instrument_token": "NSE_EQ|INE002A01018",
                    "volume": 9,
                    "cp": 100,
                }
            }
        }
        v2, v3, hist = _v2_v3_pair(ltp_body=ltp_body)
        adapter = UpstoxMarketDataAdapter(v2, v3, hist)
        out = adapter.ltps_batch(["NSE_EQ|INE002A01018"])
        v3.get_ltp_v3.assert_called_once()
        v2.get_quote.assert_not_called()
        assert out["NSE_EQ|INE002A01018"] == Decimal("111.1")

    def test_ltp_single_falls_back_to_v2_on_v3_error(self):
        v2 = MagicMock()
        v3 = MagicMock()
        v3.get_ltp_v3.side_effect = RuntimeError("v3 down")
        v2.get_quote.return_value = {
            "data": {
                "symbol": "RELIANCE",
                "last_price": 50,
                "ohlc": {"open": 1, "high": 2, "low": 0.5, "close": 49},
            }
        }
        hist = MagicMock()
        adapter = UpstoxMarketDataAdapter(v2, v3, hist)
        assert adapter.ltp("NSE_EQ|INE002A01018") == Decimal("50")


# ---------------------------------------------------------------------------
# Gateway batch mapping (resolve keys → symbols)
# ---------------------------------------------------------------------------


class TestGatewayNativeBatch:
    def test_quote_batch_maps_back_to_symbols(self):
        from brokers.upstox.wire import UpstoxBrokerGateway

        broker = MagicMock()
        gw = object.__new__(UpstoxBrokerGateway)
        gw._broker = broker
        gw._market_data = MagicMock()
        gw._resolve_instrument_key = MagicMock(
            side_effect=lambda s, e: {
                "RELIANCE": "NSE_EQ|INE002A01018",
                "TCS": "NSE_EQ|INE467B01029",
            }[s]
        )
        gw._market_data.quotes_batch.return_value = {
            "NSE_EQ|INE002A01018": Quote(symbol="RELIANCE", ltp=Decimal("10")),
            "RELIANCE": Quote(symbol="RELIANCE", ltp=Decimal("10")),
            "NSE_EQ|INE467B01029": Quote(symbol="TCS", ltp=Decimal("20")),
            "TCS": Quote(symbol="TCS", ltp=Decimal("20")),
        }
        result = UpstoxBrokerGateway.quote_batch(gw, ["RELIANCE", "TCS"], "NSE")
        assert result["RELIANCE"].ltp == Decimal("10")
        assert result["TCS"].ltp == Decimal("20")
        gw._market_data.quotes_batch.assert_called_once()
        # single multi-key call, not N singles
        called_keys = gw._market_data.quotes_batch.call_args[0][0]
        assert set(called_keys) == {"NSE_EQ|INE002A01018", "NSE_EQ|INE467B01029"}

    def test_ltp_batch_empty(self):
        from brokers.upstox.wire import UpstoxBrokerGateway

        gw = object.__new__(UpstoxBrokerGateway)
        assert UpstoxBrokerGateway.ltp_batch(gw, [], "NSE") == {}


# ---------------------------------------------------------------------------
# DataProvider batch
# ---------------------------------------------------------------------------


class TestDataProviderBatch:
    def test_get_quotes_batch_uses_gateway_quote_batch(self):
        from brokers.upstox.data_provider import UpstoxDataProvider
        from domain.instruments.instrument_id import InstrumentId

        gw = MagicMock()
        gw.quote_batch.return_value = {
            "RELIANCE": Quote(symbol="RELIANCE", ltp=Decimal("99"), volume=5),
        }
        dp = UpstoxDataProvider(gw)
        iids = [InstrumentId.equity("NSE", "RELIANCE")]
        out = dp.get_quotes_batch(iids)
        assert len(out) == 1
        assert out[0] is not None
        assert out[0].ltp == Decimal("99")
        gw.quote_batch.assert_called_once()


# ---------------------------------------------------------------------------
# History series (domain SSOT)
# ---------------------------------------------------------------------------


class TestUpstoxHistorySeries:
    def test_adapter_get_history_series_returns_domain_series(self):
        from unittest.mock import MagicMock

        from brokers.upstox.market_data.market_data_adapter import UpstoxMarketDataAdapter
        from domain.candles.historical import HistoricalSeries

        v2 = MagicMock()
        v3 = MagicMock()
        hist = MagicMock()
        hist.get_candles.return_value = {
            "data": {
                "candles": [
                    ["2026-01-15T03:45:00+00:00", 100, 101, 99, 100.5, 1000],
                ]
            }
        }
        adapter = UpstoxMarketDataAdapter(v2, v3, hist)
        series = adapter.get_history_series(
            "RELIANCE",
            "NSE",
            "1m",
            lookback_days=1,
            from_date="2026-01-15",
            to_date="2026-01-15",
        )
        assert isinstance(series, HistoricalSeries)
        assert len(series.bars) == 1
        assert float(series.bars[0].close) == pytest.approx(100.5)

    def test_adapter_history_is_dataframe_export(self):
        from unittest.mock import MagicMock

        import pandas as pd

        from brokers.upstox.market_data.market_data_adapter import UpstoxMarketDataAdapter

        v2 = MagicMock()
        v3 = MagicMock()
        hist = MagicMock()
        hist.get_candles.return_value = {
            "data": {
                "candles": [
                    ["2026-01-15T03:45:00+00:00", 100, 101, 99, 100.5, 1000],
                ]
            }
        }
        adapter = UpstoxMarketDataAdapter(v2, v3, hist)
        df = adapter.history(
            "RELIANCE",
            "NSE",
            "1m",
            from_date="2026-01-15",
            to_date="2026-01-15",
        )
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert float(df.iloc[0]["close"]) == pytest.approx(100.5)

    def test_data_provider_get_history_returns_bars(self):
        from unittest.mock import MagicMock

        import pandas as pd

        from brokers.upstox.data_provider import UpstoxDataProvider
        from domain.candles.historical import HistoricalBar
        from domain.instruments.instrument_id import InstrumentId

        gw = MagicMock()
        gw.history.return_value = pd.DataFrame(
            {
                "timestamp": [pd.Timestamp("2026-01-15T03:45:00Z")],
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.5],
                "volume": [1000],
            }
        )
        provider = UpstoxDataProvider(gw)
        iid = InstrumentId.equity("NSE", "RELIANCE")
        bars = provider.get_history(iid, timeframe="1m")
        assert isinstance(bars, list)
        assert len(bars) == 1
        assert isinstance(bars[0], HistoricalBar)
        assert float(bars[0].close) == pytest.approx(100.5)


# ---------------------------------------------------------------------------
# V3 client URL / params
# ---------------------------------------------------------------------------


class TestV3Client:
    def test_ltp_v3_joins_keys(self):
        http = MagicMock()
        http.get_json.return_value = {"status": "success", "data": {}}
        urls = MagicMock()
        urls.market_quote_ltp_v3_url.return_value = "https://api.upstox.com/v3/market-quote/ltp"
        client = UpstoxMarketDataV3Client(http, urls)
        client.get_ltp_v3(["NSE_EQ|A", "NSE_EQ|B"])
        params = http.get_json.call_args.kwargs["params"]
        assert params["instrument_key"] == "NSE_EQ|A,NSE_EQ|B"

    def test_ohlc_v3_requires_interval(self):
        http = MagicMock()
        http.get_json.return_value = {}
        urls = MagicMock()
        urls.market_quote_ohlc_v3_url.return_value = "https://api.upstox.com/v3/market-quote/ohlc"
        client = UpstoxMarketDataV3Client(http, urls)
        client.get_ohlc_v3(["NSE_EQ|A"], interval="I1")
        params = http.get_json.call_args.kwargs["params"]
        assert params["interval"] == "I1"
