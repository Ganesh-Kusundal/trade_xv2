"""MarketDataGateway — LTP, quote, depth, history, and instrument queries.

Responsibility: Fetch market data via HTTP (LTP, quote, depth, history),
resolve instrument keys, and manage instrument loading.
Thread-safe: All methods delegate to stateless adapters.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd

from brokers.upstox.adapters.historical_adapter import HistoricalAdapter
from brokers.upstox.market_data.market_data_adapter import (
    UpstoxMarketDataAdapter as MarketDataAdapter,
)
from domain import (
    FutureChain,
    MarketDepth,
    OptionChain,
    Quote,
)

logger = logging.getLogger(__name__)


class MarketDataGateway:
    """Market data operations — LTP, quote, depth, history, chains, search.

    Encapsulates:
    - Real-time HTTP market data (LTP, quote, depth, batch variants)
    - Historical candle fetching
    - Option/future chain retrieval
    - Instrument search and loading
    - Instrument key resolution

    Thread Safety:
        All methods are thread-safe. Delegates to broker adapters which
        maintain their own concurrency guarantees.

    Example::

        gw = MarketDataGateway(broker, market_data_adapter, historical_adapter)
        ltp = gw.ltp("RELIANCE", "NSE")
        df = gw.history("RELIANCE", "NSE", "1D", lookback_days=90)
    """

    def __init__(
        self,
        broker: Any,
        market_data_adapter: MarketDataAdapter,
        historical_adapter: HistoricalAdapter,
    ) -> None:
        """Initialize with broker facade and specialized adapters.

        Args:
            broker: UpstoxBroker instance providing access to instrument resolver
            market_data_adapter: MarketDataAdapter for HTTP market data
            historical_adapter: HistoricalAdapter for candle fetching
        """
        self._broker = broker
        self._market_data = market_data_adapter
        self._historical = historical_adapter

    # ── LTP / Quote / Depth ─────────────────────────────────────────────

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        """Fetch last traded price for a symbol (V3 LTP with v2 fallback)."""
        key = self._resolve_instrument_key(symbol, exchange)
        return self._market_data.ltp(key, exchange)

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        """Fetch full quote with OHLCV for a symbol."""
        key = self._resolve_instrument_key(symbol, exchange)
        return self._market_data.quote(key, exchange)

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        """Fetch order book depth for a symbol."""
        key = self._resolve_instrument_key(symbol, exchange)
        return self._market_data.depth(key, exchange)

    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
        """Native multi-key LTP (≤500 keys / HTTP). Overrides BatchFetchMixin N×1 path."""
        if not symbols:
            return {}
        key_to_sym, keys = self._resolve_keys(symbols, exchange)
        raw = self._market_data.ltps_batch(keys)
        return self._map_batch_to_symbols(symbols, key_to_sym, raw, default=Decimal("0"))

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Quote]:
        """Native multi-key full quotes (≤500 keys / HTTP). Overrides BatchFetchMixin."""
        if not symbols:
            return {}
        key_to_sym, keys = self._resolve_keys(symbols, exchange)
        raw = self._market_data.quotes_batch(keys)
        return self._map_batch_to_symbols(symbols, key_to_sym, raw, default=None)

    # ── Batch helpers ───────────────────────────────────────────────────

    def _resolve_keys(
        self, symbols: list[str], exchange: str
    ) -> tuple[dict[str, str], list[str]]:
        """Return (instrument_key → symbol, ordered keys)."""
        key_to_sym: dict[str, str] = {}
        keys: list[str] = []
        for sym in symbols:
            try:
                key = self._resolve_instrument_key(sym, exchange)
            except Exception:
                continue
            keys.append(key)
            key_to_sym[key] = sym
            # response keys sometimes use colon
            key_to_sym[key.replace("|", ":")] = sym
        return key_to_sym, keys

    def _map_batch_to_symbols(
        self,
        symbols: list[str],
        key_to_sym: dict[str, str],
        raw: dict[str, Any],
        *,
        default: Any,
    ) -> dict[str, Any]:
        """Map multi-key response aliases back to original symbols."""
        symbol_set = set(symbols)
        out: dict[str, Any] = {}

        for key, value in raw.items():
            sym = key_to_sym.get(key)
            if sym is None and key in symbol_set:
                sym = key
            if sym is None:
                cand = getattr(value, "symbol", None)
                if cand and str(cand) in symbol_set:
                    sym = str(cand)
            if sym is None:
                tail = (
                    str(key).split(":")[-1]
                    if ":" in str(key)
                    else str(key).split("|")[-1]
                )
                if tail in symbol_set:
                    sym = tail
            if sym is not None:
                out[sym] = value

        if default is not None:
            for sym in symbols:
                out.setdefault(sym, default)
        return out

    # ── History ─────────────────────────────────────────────────────────

    def history(
        self,
        symbol: str,
        exchange: str = "NSE",
        timeframe: str = "1D",
        lookback_days: int = 90,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        """Fetch historical candles (EOD or Intraday) for a symbol."""
        to_d = date.today()
        from_d = to_d - timedelta(days=lookback_days)
        to_str = to_date or str(to_d)
        from_str = from_date or str(from_d)
        timeframe_str = timeframe.upper() if timeframe else "1D"

        # Resolve timeframe to V3 interval
        unit, interval = HistoricalAdapter.resolve_timeframe(timeframe_str)

        try:
            return self._fetch_history(symbol, exchange, from_str, to_str, unit, interval)
        except Exception as e:
            logger.warning(
                "history_fetch_failed",
                extra={
                    "symbol": symbol,
                    "exchange": exchange,
                    "interval": timeframe_str,
                    "from": from_str,
                    "to": to_str,
                    "error": str(e),
                },
            )
            raise

    def _fetch_history(
        self,
        symbol: str,
        exchange: str,
        from_date: str,
        to_date: str,
        unit: str,
        interval: str,
    ) -> pd.DataFrame:
        """Fetch historical candles for a single symbol.

        Args:
            symbol: Canonical trading symbol
            exchange: Exchange segment
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            unit: Time unit (minutes, hours, days)
            interval: Interval value

        Returns:
            DataFrame with OHLCV data
        """
        from brokers.upstox.auth.exceptions import UpstoxApiError

        try:
            key = self._resolve_instrument_key(symbol, exchange)
            return self._historical.fetch_candles(
                symbol, exchange, key, from_date, to_date, unit, interval
            )
        except UpstoxApiError as e:
            logger.warning("Upstox history API error for symbol %s: %s", symbol, e)
            raise
        except Exception as e:
            logger.warning("Failed to fetch history for symbol %s: %s", symbol, e)
            raise

    # ── Option / Future chains ──────────────────────────────────────────

    def option_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> OptionChain:
        """Get the option chain for an underlying."""
        if expiry is None:
            expiries = self._broker.options.get_expiries(underlying, exchange)
            if not expiries:
                return OptionChain(underlying=underlying, exchange=exchange, expiry="")
            expiry = expiries[0]
        from domain.options.chain_normalizer import upstox_chain_to_canonical

        if hasattr(self._broker.options, "get_option_chain_with_meta"):
            result = self._broker.options.get_option_chain_with_meta(underlying, exchange, expiry)
            if isinstance(result, tuple) and len(result) == 3:
                contracts, raw_rows, _body = result
                return upstox_chain_to_canonical(contracts, raw_rows, underlying, exchange, expiry)
        contracts = self._broker.options.get_option_chain(underlying, exchange, expiry)
        if not isinstance(contracts, list):
            return OptionChain(underlying=underlying, exchange=exchange, expiry=expiry)
        return upstox_chain_to_canonical(contracts, None, underlying, exchange, expiry)

    def future_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
    ) -> FutureChain:
        """Get the future chain for an underlying."""
        from config.indices import INDEX_TO_FNO_EXCHANGE

        segment = INDEX_TO_FNO_EXCHANGE.get(underlying.upper(), exchange)
        futures = getattr(self._broker, "futures", None)
        if futures is None:
            return FutureChain.from_dict({"underlying": underlying, "exchange": segment})
        contracts = futures.get_contracts(underlying, segment)
        expiries = futures.get_expiries(underlying, segment)
        chain = []
        for c in contracts:
            if not isinstance(c, dict):
                continue
            chain.append(
                {
                    "expiry": c.get("expiry", ""),
                    "symbol": c.get("symbol", c.get("trading_symbol", "")),
                    "lot_size": c.get("lot_size", 1),
                    "underlying": c.get("underlying", underlying),
                }
            )
        return FutureChain.from_dict(
            {
                "underlying": underlying,
                "exchange": segment,
                "expiries": expiries,
                "contracts": chain,
            }
        )

    # ── Lifecycle ───────────────────────────────────────────────────────

    def load_instruments(self, source: str | None = None) -> None:
        """Load instrument definitions via the broker-internal instrument service."""
        self._broker.instruments.load(source=source)

    def close(self) -> None:
        """Disconnect from broker and cleanup resources."""
        self._broker.disconnect()

    def describe(self) -> dict:
        """Get broker description metadata.

        Returns:
            Dict with broker capabilities and status
        """
        return {
            "broker": "Upstox",
            "instruments_loaded": self._broker.instruments.is_loaded(),
            "instrument_count": self._broker.instruments.stats().get("total", 0),
            "market_data": "available",
            "historical": "available",
            "options": "available",
            "futures": "available",
            "streaming": "available",
        }

    # ── Search ─────────────────────────────────────────────────────────

    def search(self, query: str) -> list[dict]:
        """Search for instruments by query string."""
        return self._broker.instruments.search(query)

    # ── Instrument key resolution ──────────────────────────────────────

    def _resolve_instrument_key(self, symbol: str, exchange: str) -> str:
        """Resolve canonical symbol to Upstox instrument_key (broker-internal)."""
        segment = self._resolve_exchange_segment(symbol, exchange)
        inst = self._broker.instruments.resolve(symbol=symbol, exchange_segment=segment)
        if inst and inst.instrument_key:
            return inst.instrument_key
        return f"{segment}|{symbol}"

    def _resolve_exchange_segment(self, symbol: str, exchange: str) -> str:
        # Fallback heuristic for exchange segments
        if exchange.upper() == "NSE":
            if symbol.upper() in {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"}:
                return "IDX_I"
            return "NSE_EQ"
        return "NSE_EQ"