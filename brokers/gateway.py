"""Gateway — the single entry point for TradeXV2.

Ultra-simple API that hides all broker internals. A quant should be able to::

    from broker import Gateway

    g = Gateway()
    g.ltp("TCS")
    g.history("TCS")
    g.option_chain("NIFTY")
    g.positions()
    g.buy("TCS", qty=1)

without reading any broker documentation.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Union

import pandas as pd

from brokers.common.core.broker import Broker
from brokers.common.core.domain import (
    FundLimits,
    Holding,
    Order,
    OrderResponse,
    Position,
    ProductType,
    Side,
    Trade,
)
from brokers.common.core.enums import ExchangeSegment, FeedMode, TransactionType
from brokers.common.core.instruments import Instrument, InstrumentRegistry

logger = logging.getLogger(__name__)

SymbolOrSymbols = Union[str, list[str]]

_INDEX_SYMBOLS = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "NIFTYNXT50"}

# Strike step sizes by underlying for ATM/strangle calculations
_STRIKE_STEPS: dict[str, int] = {
    "NIFTY": 50,
    "BANKNIFTY": 100,
    "FINNIFTY": 50,
    "MIDCPNIFTY": 25,
    "SENSEX": 100,
    "NIFTYNXT50": 50,
}
_DEFAULT_STRIKE_STEP = 50

_UNIVERSES: dict[str, list[str]] = {
    "NIFTY50": [
        "RELIANCE",
        "TCS",
        "HDFCBANK",
        "INFY",
        "ICICIBANK",
        "HDFC",
        "SBIN",
        "ITC",
        "LT",
        "KOTAKBANK",
        "BHARTIARTL",
        "HINDUNILVR",
        "BAJFINANCE",
        "MARUTI",
        "AXISBANK",
        "ASIANPAINT",
        "SUNPHARMA",
        "TITAN",
        "ULTRACEMCO",
        "NESTLEIND",
        "NTPC",
        "ONGC",
        "POWERGRID",
        "TATASTEEL",
        "M&M",
        "BAJAJFINSV",
        "DRREDDY",
        "CIPLA",
        "JSWSTEEL",
        "TATAMOTORS",
        "COALINDIA",
        "TECHM",
        "HCLTECH",
        "WIPRO",
        "GRASIM",
        "DIVISLAB",
        "APOLLOHOSP",
        "TATACONSUM",
        "EICHERMOT",
        "BRITANNIA",
        "SBILIFE",
        "HDFCLIFE",
        "ADANIENT",
        "ADANIPORTS",
        "BPCL",
        "INDUSINDBK",
        "HEROMOTOCO",
        "UPL",
        "LTIM",
        "BAJAJ-AUTO",
    ],
    "NIFTY100": [
        "RELIANCE",
        "TCS",
        "HDFCBANK",
        "INFY",
        "ICICIBANK",
        "HDFC",
        "SBIN",
        "ITC",
        "LT",
        "KOTAKBANK",
        "BHARTIARTL",
        "HINDUNILVR",
        "BAJFINANCE",
        "MARUTI",
        "AXISBANK",
        "ASIANPAINT",
        "SUNPHARMA",
        "TITAN",
        "ULTRACEMCO",
        "NESTLEIND",
        "NTPC",
        "ONGC",
        "POWERGRID",
        "TATASTEEL",
        "M&M",
        "BAJAJFINSV",
        "DRREDDY",
        "CIPLA",
        "JSWSTEEL",
        "TATAMOTORS",
        "COALINDIA",
        "TECHM",
        "HCLTECH",
        "WIPRO",
        "GRASIM",
        "DIVISLAB",
        "APOLLOHOSP",
        "TATACONSUM",
        "EICHERMOT",
        "BRITANNIA",
        "SBILIFE",
        "HDFCLIFE",
        "ADANIENT",
        "ADANIPORTS",
        "BPCL",
        "INDUSINDBK",
        "HEROMOTOCO",
        "UPL",
        "LTIM",
        "BAJAJ-AUTO",
        "AMBUJACEM",
        "SIEMENS",
        "HAVELLS",
        "PIDILITIND",
        "DLF",
        "DABUR",
        "GODREJCP",
        "BOSCHLTD",
        "TORNTPHARM",
        "VEDL",
        "BANKBARODA",
        "GAIL",
        "SHREECEM",
        "COLPAL",
        "MARICO",
        "MUTHOOTFIN",
        "BERGEPAINT",
        "INDIGO",
        "NAUKA",
        "SRF",
        "CUMMINSIND",
        "CHOLAFIN",
        "PIIND",
        "PAGEIND",
        "ASTRAL",
        "LODHA",
        "MAXHEALTH",
        "TRENT",
        "JINDALSTEL",
        "POLYCAB",
        "ABB",
        "ADANIGREEN",
        "MOTHERSON",
        "TATAPOWER",
        "SOLARINDS",
        "PETRONET",
        "NAVINFLUOR",
        "IRCTC",
        "MPHASIS",
        "OBEROIRLTY",
        "PERSISTENT",
        "ZYDUSLIFE",
        "BALKRISIND",
        "CGPOWER",
        "ABCAPITAL",
        "LINDEINDIA",
        "SCHAEFFLER",
        "360ONE",
        "PAYTM",
        "NYKAA",
    ],
    "NIFTY200": [
        "RELIANCE",
        "TCS",
        "HDFCBANK",
        "INFY",
        "ICICIBANK",
        "HDFC",
        "SBIN",
        "ITC",
        "LT",
        "KOTAKBANK",
        "BHARTIARTL",
        "HINDUNILVR",
        "BAJFINANCE",
        "MARUTI",
        "AXISBANK",
        "ASIANPAINT",
        "SUNPHARMA",
        "TITAN",
        "ULTRACEMCO",
        "NESTLEIND",
        "NTPC",
        "ONGC",
        "POWERGRID",
        "TATASTEEL",
        "M&M",
        "BAJAJFINSV",
        "DRREDDY",
        "CIPLA",
        "JSWSTEEL",
        "TATAMOTORS",
        "COALINDIA",
        "TECHM",
        "HCLTECH",
        "WIPRO",
        "GRASIM",
        "DIVISLAB",
        "APOLLOHOSP",
        "TATACONSUM",
        "EICHERMOT",
        "BRITANNIA",
        "SBILIFE",
        "HDFCLIFE",
        "ADANIENT",
        "ADANIPORTS",
        "BPCL",
        "INDUSINDBK",
        "HEROMOTOCO",
        "UPL",
        "LTIM",
        "BAJAJ-AUTO",
        "AMBUJACEM",
        "SIEMENS",
        "HAVELLS",
        "PIDILITIND",
        "DLF",
        "DABUR",
        "GODREJCP",
        "BOSCHLTD",
        "TORNTPHARM",
        "VEDL",
        "BANKBARODA",
        "GAIL",
        "SHREECEM",
        "COLPAL",
        "MARICO",
        "MUTHOOTFIN",
        "BERGEPAINT",
        "INDIGO",
        "NAUKA",
        "SRF",
        "CUMMINSIND",
        "CHOLAFIN",
        "PIIND",
        "PAGEIND",
        "ASTRAL",
        "LODHA",
        "MAXHEALTH",
        "TRENT",
        "JINDALSTEL",
        "POLYCAB",
        "ABB",
        "ADANIGREEN",
        "MOTHERSON",
        "TATAPOWER",
        "SOLARINDS",
        "PETRONET",
        "NAVINFLUOR",
        "IRCTC",
        "MPHASIS",
        "OBEROIRLTY",
        "PERSISTENT",
        "ZYDUSLIFE",
        "BALKRISIND",
        "CGPOWER",
        "ABCAPITAL",
        "LINDEINDIA",
        "SCHAEFFLER",
        "360ONE",
        "PAYTM",
        "NYKAA",
        "PNB",
        "FEDERALBNK",
        "IDFCFIRSTB",
        "AUBANK",
        "BANDHANBNK",
        "RBLBANK",
        "LUPIN",
        "BIOCON",
        "GLAND",
        "FORTIS",
        "MRF",
        "ACC",
        "ATUL",
        "LALPATHLAB",
        "METROPOLIS",
        "MFSL",
        "CANBK",
        "UNIONBANK",
        "INDIAMART",
        "ZOMATO",
        "DELHIVERY",
        "ICICIGI",
        "STARHEALTH",
        "MEDANTA",
        "KIMS",
        "APLLTD",
        "CONCOR",
        "NAM-INDIA",
        "ANGELONE",
        "CDSL",
        "BSE",
        "IRFC",
        "RECLTD",
        "PFC",
        "NHPC",
        "SJVN",
        "ADANIPOWER",
        "TATAELXSI",
        "KPITTECH",
        "LTTS",
        "HAPPSTMNDS",
        "COFORGE",
        "IDEA",
        "VODAIDEA",
        "TIINDIA",
        "KEI",
        "FINPIPE",
        "APARINDS",
        "KALYANKJIL",
        "SAFARI",
        "KAYNES",
        "UNOMINDA",
        "ENDURANCE",
        "SONACOMS",
        "DIXON",
        "BLUESTARLT",
        "WHIRLPOOL",
        "VOLTAS",
        "OIL",
        "GLENMARK",
        "IPCALAB",
        "NATCOPHAR",
        "LAURUSLABS",
        "SYNGENE",
        "AUROPHARMA",
        "ALKEM",
        "ESCORTS",
        "MAHINDCIE",
        "ASHOKLEY",
        "BHARATFORG",
        "BEL",
        "HAL",
        "BHEL",
        "RVNL",
        "IRCON",
        "NBCC",
        "NCC",
        "KNRCON",
        "PNCINFRA",
        "WABAG",
        "GUJGASLTD",
        "IGL",
        "MGL",
        "SPARC",
        "RAYMOND",
        "FLUOROCHEM",
        "DEEPAKNTR",
        "CLEAN",
        "CARBORUNIV",
        "RESPONIND",
        "MANAPPURAM",
        "AARTIIND",
        "SUNTV",
        "PHOENIXLTD",
        "EMAMILTD",
        "GSFC",
        "NFL",
        "FACT",
        "GMMPFAUDLR",
        "MASTEK",
    ],
    "NIFTY_MIDCAP50": [
        "AMBUJACEM",
        "SIEMENS",
        "HAVELLS",
        "PIDILITIND",
        "DLF",
        "DABUR",
        "GODREJCP",
        "BOSCHLTD",
        "TORNTPHARM",
        "VEDL",
        "BANKBARODA",
        "GAIL",
        "SHREECEM",
        "COLPAL",
        "MARICO",
        "MUTHOOTFIN",
        "BERGEPAINT",
        "INDIGO",
        "NAUKA",
        "SRF",
        "CUMMINSIND",
        "CHOLAFIN",
        "PIIND",
        "PAGEIND",
        "ASTRAL",
        "LODHA",
        "MAXHEALTH",
        "TRENT",
        "JINDALSTEL",
        "POLYCAB",
        "ABB",
        "ADANIGREEN",
        "MOTHERSON",
        "TATAPOWER",
        "SOLARINDS",
        "PETRONET",
        "NAVINFLUOR",
        "IRCTC",
        "MPHASIS",
        "OBEROIRLTY",
        "PERSISTENT",
        "ZYDUSLIFE",
        "BALKRISIND",
        "CGPOWER",
        "ABCAPITAL",
        "LINDEINDIA",
        "SCHAEFFLER",
        "360ONE",
        "PAYTM",
        "NYKAA",
    ],
    "BANKNIFTY": [
        "HDFCBANK",
        "ICICIBANK",
        "SBIN",
        "KOTAKBANK",
        "AXISBANK",
        "INDUSINDBK",
        "BANKBARODA",
        "PNB",
        "FEDERALBNK",
        "IDFCFIRSTB",
        "AUBANK",
        "BANDHANBNK",
        "RBLBANK",
    ],
}


def _is_index(symbol: str) -> bool:
    return symbol.upper() in _INDEX_SYMBOLS


def _strike_step(underlying: str) -> int:
    return _STRIKE_STEPS.get(underlying.upper(), _DEFAULT_STRIKE_STEP)


class Gateway:
    """Single entry point for all trading operations.

    Wraps a broker adapter and provides sensible defaults, automatic
    symbol resolution, and a fluent API.
    """

    def __init__(
        self,
        broker: str | Broker | None = None,
        *,
        auto_connect: bool = True,
    ) -> None:
        self._registry = InstrumentRegistry()
        self._broker: Broker
        self._connected = False
        # Streaming state: maps symbol -> {"security_id", "segment", "mode", "type"}
        self._streaming_subscriptions: dict[str, dict[str, Any]] = {}
        self._streaming_listeners: list[Any] = []
        self._stream_lock = threading.Lock()

        if broker is None:
            self._broker = self._auto_detect_broker()
        elif isinstance(broker, str):
            self._broker = self._create_broker_by_name(broker)
        else:
            self._broker = broker

        if auto_connect:
            self.connect()

    # ── Factory helpers ──────────────────────────────────────────────

    def _auto_detect_broker(self) -> Broker:
        if any(k.startswith("UPSTOX_") for k in os.environ):
            try:
                from brokers.upstox import UpstoxBroker

                logger.info("Auto-detected Upstox broker (UPSTOX_* env set)")
                return UpstoxBroker()
            except Exception as exc:
                logger.info("UPSTOX_* env set but broker construction failed: %s", exc)
        try:
            from brokers.dhan.broker import DhanBroker

            b = DhanBroker.from_env()
            logger.info("Auto-detected Dhan broker")
            return b
        except Exception:
            logger.info("Falling back to PaperBroker")
            from brokers.paper import PaperBroker

            return PaperBroker()

    def _create_broker_by_name(self, name: str) -> Broker:
        name_lower = name.lower()
        if name_lower == "paper":
            from brokers.paper import PaperBroker

            return PaperBroker()
        if name_lower == "dhan":
            from brokers.dhan.broker import DhanBroker

            return DhanBroker.from_env()
        if name_lower == "upstox":
            from brokers.upstox import UpstoxBroker

            try:
                return UpstoxBroker()
            except Exception as exc:
                logger.warning(
                    "Failed to construct UpstoxBroker: %s; falling back to PaperBroker", exc
                )
                from brokers.paper import PaperBroker

                return PaperBroker()
        raise ValueError(f"Unknown broker: {name}")

    # ── Broker Lifecycle ─────────────────────────────────────────────

    def _ensure_connected(self) -> None:
        if not self._is_connected():
            logger.warning("Gateway is not connected — call connect() first")

    def _validate_qty(self, qty: int) -> None:
        if not isinstance(qty, int) or qty <= 0:
            raise ValueError(f"qty must be a positive integer, got {qty!r}")

    def connect(self) -> bool:
        self._connected = self._broker.connect()
        return self._connected

    def disconnect(self) -> bool:
        if self._streaming_subscriptions:
            logger.info(
                "Cleaning up %d active streaming subscription(s) before disconnect",
                len(self._streaming_subscriptions),
            )
            self.unsubscribe_all()
        self._connected = False
        return self._broker.disconnect()

    def reconnect(self) -> bool:
        self.disconnect()
        return self.connect()

    def health(self) -> dict[str, Any]:
        connected = self._is_connected()
        return {
            "broker": self._broker.name,
            "broker_id": self._broker.broker_id,
            "connected": connected,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def capabilities(self) -> set:
        if hasattr(self._broker, "capabilities"):
            return self._broker.capabilities()
        return set()

    def _is_connected(self) -> bool:
        if hasattr(self._broker, "is_connected"):
            return self._broker.is_connected()
        return self._connected

    # ── Authentication ───────────────────────────────────────────────

    def login(self) -> bool:
        return self.connect()

    def logout(self) -> bool:
        return self.disconnect()

    def refresh_session(self) -> bool:
        return self.reconnect()

    # ── Account APIs ─────────────────────────────────────────────────

    def funds(self) -> FundLimits:
        return self._broker.get_fund_limits()

    def holdings(self) -> list[Holding]:
        return self._broker.get_holdings()

    def positions(self) -> list[Position]:
        return self._broker.get_positions()

    def orders(self) -> list[Order]:
        return self._broker.get_orders()

    def trades(self) -> list[Trade]:
        return self._broker.get_trades()

    def order_book(self) -> list[Order]:
        return self._broker.get_orders()

    def trade_book(self) -> list[Trade]:
        return self._broker.get_trades()

    # ── Symbol Resolution ────────────────────────────────────────────

    def _resolve(self, symbol: str, exchange: str = "NSE") -> tuple:
        """Resolve symbol to (security_id, exchange_segment, canonical_exchange)."""
        sym = symbol.upper()
        if hasattr(self._broker, "instrument_service"):
            try:
                resolved = self._broker.instrument_service.resolve_to_wire(sym, exchange)
                return (
                    resolved.security_id,
                    resolved.wire_segment,
                    resolved.canonical_exchange,
                )
            except Exception:
                pass

        instr = self._registry.resolve(sym, exchange)
        if instr and instr.broker_identifier:
            seg = self._registry.exchange_segment(exchange)
            return instr.broker_identifier, seg, exchange

        return sym, self._registry.exchange_segment(exchange), exchange

    def _default_exchange(self, symbol: str) -> str:
        sym = symbol.upper()
        if _is_index(sym):
            return "IDX"
        if " " in sym:
            parts = sym.split()
            if parts[-1] in ("CE", "PE"):
                return "NFO"
        return "NSE"

    def _seg_arg(self, seg: Any, exch: str) -> Any:
        """Return the correct second argument for broker market-data calls.

        Brokers accept either an ExchangeSegment enum or a plain exchange string.
        """
        return exch if not isinstance(seg, ExchangeSegment) else seg

    # ── Market Data: LTP ─────────────────────────────────────────────

    def ltp(self, symbols: SymbolOrSymbols, exchange: str = "NSE") -> float | dict[str, float]:
        if isinstance(symbols, list):
            if not symbols:
                return {}
            result = {}
            for sym in symbols:
                result[sym.upper()] = self._single_ltp(sym, exchange)
            return result
        return self._single_ltp(symbols, exchange)

    def _single_ltp(self, symbol: str, exchange: str) -> float:
        exchange = self._default_exchange(symbol) if exchange == "NSE" else exchange
        sec_id, seg, exch = self._resolve(symbol, exchange)
        df = self._broker.get_quote(sec_id, self._seg_arg(seg, exch))
        if isinstance(df, pd.DataFrame) and not df.empty:
            return float(df.iloc[0]["ltp"])
        return 0.0

    # ── Market Data: Quote ───────────────────────────────────────────

    def quote(self, symbols: SymbolOrSymbols, exchange: str = "NSE") -> pd.DataFrame:
        if isinstance(symbols, list):
            if not symbols:
                return pd.DataFrame()
            frames = []
            for sym in symbols:
                frames.append(self._single_quote(sym, exchange))
            return pd.concat(frames, ignore_index=True)
        return self._single_quote(symbols, exchange)

    def _single_quote(self, symbol: str, exchange: str) -> pd.DataFrame:
        exchange = self._default_exchange(symbol) if exchange == "NSE" else exchange
        sec_id, seg, exch = self._resolve(symbol, exchange)
        df = self._broker.get_quote(sec_id, self._seg_arg(seg, exch))
        if isinstance(df, pd.DataFrame) and not df.empty:
            df = df.copy()
            if "symbol" in df.columns:
                df["symbol"] = symbol.upper()
            if "exchange" in df.columns:
                df["exchange"] = exch
        if isinstance(df, pd.DataFrame):
            return df
        return pd.DataFrame()

    # ── Market Data: History ─────────────────────────────────────────

    def history(
        self,
        symbols: SymbolOrSymbols,
        *,
        timeframe: str = "1m",
        lookback_days: int = 90,
        exchange: str = "NSE",
        lazy: bool = False,
    ) -> pd.DataFrame | Any:
        to_date = date.today()
        from_date = to_date - timedelta(days=lookback_days)

        if isinstance(symbols, list):
            if not symbols:
                result = pd.DataFrame()
            else:
                frames = []
                for sym in symbols:
                    df = self._single_history(sym, exchange, from_date, to_date, timeframe)
                    frames.append(df)
                result = pd.concat(frames, ignore_index=True)
        else:
            result = self._single_history(symbols, exchange, from_date, to_date, timeframe)

        if lazy:
            try:
                import polars as pl

                return pl.from_pandas(result).lazy()
            except (ImportError, Exception) as exc:
                logger.warning("polars conversion failed (%s), returning pandas DataFrame", exc)
        return result

    def _single_history(
        self, symbol: str, exchange: str, from_date: date, to_date: date, timeframe: str
    ) -> pd.DataFrame:
        exchange = self._default_exchange(symbol) if exchange == "NSE" else exchange
        sec_id, seg, exch = self._resolve(symbol, exchange)
        df = self._broker.get_historical_data(
            sec_id,
            self._seg_arg(seg, exch),
            from_date,
            to_date,
            timeframe,
        )
        if isinstance(df, pd.DataFrame) and not df.empty:
            df = df.copy()
            if "symbol" in df.columns:
                df["symbol"] = symbol.upper()
            if "exchange" in df.columns:
                df["exchange"] = exch
        return df

    def intraday(
        self, symbol: str, *, exchange: str = "NSE", lookback_days: int = 30
    ) -> pd.DataFrame:
        return self.history(symbol, timeframe="1m", lookback_days=lookback_days, exchange=exchange)

    def daily(
        self, symbol: str, *, exchange: str = "NSE", lookback_days: int = 365
    ) -> pd.DataFrame:
        return self.history(symbol, timeframe="1d", lookback_days=lookback_days, exchange=exchange)

    def weekly(
        self, symbol: str, *, exchange: str = "NSE", lookback_days: int = 730
    ) -> pd.DataFrame:
        return self.history(symbol, timeframe="1w", lookback_days=lookback_days, exchange=exchange)

    def monthly(
        self, symbol: str, *, exchange: str = "NSE", lookback_days: int = 1825
    ) -> pd.DataFrame:
        return self.history(symbol, timeframe="1M", lookback_days=lookback_days, exchange=exchange)

    # ── Market Depth ─────────────────────────────────────────────────

    def depth(self, symbol: str, *, levels: int = 5, exchange: str = "NSE") -> pd.DataFrame:
        sec_id, seg, exch = self._resolve(symbol, exchange)
        df = self._broker.get_market_depth(sec_id, self._seg_arg(seg, exch))
        if isinstance(df, pd.DataFrame) and not df.empty:
            df = df.copy()
            if "symbol" in df.columns:
                df["symbol"] = symbol.upper()
        if levels < 20 and isinstance(df, pd.DataFrame) and not df.empty:
            cols = ["symbol", "timestamp"]
            for i in range(1, levels + 1):
                cols.extend([f"bid_price_{i}", f"bid_qty_{i}", f"ask_price_{i}", f"ask_qty_{i}"])
            available = [c for c in cols if c in df.columns]
            return df[available]
        return df

    def full_depth(self, symbol: str, *, exchange: str = "NSE") -> pd.DataFrame:
        return self.depth(symbol, levels=20, exchange=exchange)

    # ── Live Streaming ───────────────────────────────────────────────

    # Map user-facing mode strings to FeedMode enums
    _FEED_MODE_MAP: dict[str, FeedMode] = {
        "ltp": FeedMode.LTP,
        "full": FeedMode.FULL,
        "depth": FeedMode.DEPTH,
        "tick": FeedMode.LTP,
    }

    def _get_ws_multiplexer(self) -> Any | None:
        """Return the broker's WebSocket multiplexer if available, else None."""
        # Direct attribute on broker (e.g. broker.market_data_websocket)
        for attr in ("market_data_websocket", "websocket_multiplexer", "market_feed_ws"):
            mux = getattr(self._broker, attr, None)
            if mux is not None:
                return mux
        return None

    def stream(
        self,
        symbols: SymbolOrSymbols,
        *,
        mode: str = "ltp",
        listener: Any | None = None,
    ) -> bool:
        """Subscribe to live market data for one or more symbols.

        Resolves each symbol to its security_id, then subscribes via the
        broker's WebSocket multiplexer (preferred) or order-stream fallback.

        Returns True if at least one subscription succeeded.
        """
        if isinstance(symbols, str):
            symbols = [symbols]

        feed_mode = self._FEED_MODE_MAP.get(mode.lower(), FeedMode.LTP)
        ws = self._get_ws_multiplexer()
        any_success = False

        for sym in symbols:
            sym_upper = sym.upper()
            exchange = self._default_exchange(sym)
            sec_id, seg, exch = self._resolve(sym, exchange)

            # Normalise segment to ExchangeSegment enum
            if isinstance(seg, str):
                try:
                    seg = ExchangeSegment(seg)
                except ValueError:
                    seg = ExchangeSegment.NSE

            subscribed = False

            # Path 1: WebSocket multiplexer (real-time market data)
            if ws is not None and hasattr(ws, "subscribe_websocket"):
                try:
                    result = ws.subscribe_websocket(str(sec_id), seg, feed_mode)
                    if result:
                        subscribed = True
                        logger.info(
                            "WS subscribed %s (sec=%s, seg=%s, mode=%s)",
                            sym_upper,
                            sec_id,
                            seg.value,
                            feed_mode.value,
                        )
                    else:
                        logger.warning(
                            "WS subscribe returned False for %s",
                            sym_upper,
                        )
                except Exception as exc:
                    logger.warning("WS subscribe failed for %s: %s", sym_upper, exc)

            # Path 2: Order stream (broker-level push for order updates)
            if not subscribed and hasattr(self._broker, "subscribe_order_stream"):
                try:
                    self._broker.subscribe_order_stream([str(sec_id)])
                    subscribed = True
                    logger.info(
                        "Order-stream subscribed %s (sec=%s, mode=%s)",
                        sym_upper,
                        sec_id,
                        feed_mode.value,
                    )
                except Exception as exc:
                    logger.warning(
                        "Order-stream subscribe failed for %s: %s",
                        sym_upper,
                        exc,
                    )

            if not subscribed and ws is None:
                logger.warning(
                    "Broker %s does not support streaming for %s",
                    self._broker.name,
                    sym_upper,
                )

            if subscribed:
                with self._stream_lock:
                    self._streaming_subscriptions[sym_upper] = {
                        "security_id": str(sec_id),
                        "segment": seg,
                        "mode": feed_mode,
                        "exchange": exch,
                        "type": "ws"
                        if (ws is not None and hasattr(ws, "subscribe_websocket"))
                        else "order_stream",
                    }
                any_success = True

        # Register listener if provided
        if listener is not None and any_success:
            self.add_stream_listener(listener)

        return any_success

    def candles(self, symbol: str, *, timeframe: str = "1m", listener: Any | None = None) -> bool:
        """Subscribe to tick data suitable for candle aggregation.

        Subscribes in FULL feed mode to get OHLCV ticks.  Candle
        aggregation from ticks is a **client-side** concern -- use the
        listener callback to accumulate OHLC bars at the desired
        timeframe.

        Returns True if the subscription succeeded.
        """
        logger.info(
            "Candle stream for %s (%s) — candle aggregation is client-side; "
            "subscribing to FULL tick feed",
            symbol,
            timeframe,
        )
        return self.stream(symbol, mode="full", listener=listener)

    def ticks(self, symbol: str, *, listener: Any | None = None) -> bool:
        """Subscribe to LTP tick stream for a symbol.

        Returns True if the subscription succeeded.
        """
        return self.stream(symbol, mode="ltp", listener=listener)

    def unsubscribe(self, symbols: SymbolOrSymbols) -> bool:
        """Unsubscribe from live market data for one or more symbols.

        Returns True if at least one unsubscription was processed.
        """
        if isinstance(symbols, str):
            symbols = [symbols]

        ws = self._get_ws_multiplexer()
        any_success = False

        for sym in symbols:
            sym_upper = sym.upper()
            with self._stream_lock:
                sub = self._streaming_subscriptions.pop(sym_upper, None)
            if sub is None:
                logger.debug("No active subscription for %s — skipping", sym_upper)
                continue

            sec_id = sub["security_id"]
            seg = sub["segment"]
            sub_type = sub["type"]

            if sub_type == "ws" and ws is not None and hasattr(ws, "unsubscribe_websocket"):
                try:
                    ws.unsubscribe_websocket(sec_id, seg)
                    any_success = True
                    logger.info("WS unsubscribed %s (sec=%s)", sym_upper, sec_id)
                except Exception as exc:
                    logger.warning("WS unsubscribe failed for %s: %s", sym_upper, exc)
            elif sub_type == "order_stream" and hasattr(self._broker, "unsubscribe_order_stream"):
                try:
                    self._broker.unsubscribe_order_stream([sec_id])
                    any_success = True
                    logger.info("Order-stream unsubscribed %s (sec=%s)", sym_upper, sec_id)
                except Exception as exc:
                    logger.warning(
                        "Order-stream unsubscribe failed for %s: %s",
                        sym_upper,
                        exc,
                    )

        return any_success

    def unsubscribe_all(self) -> bool:
        """Unsubscribe from all active streaming subscriptions."""
        with self._stream_lock:
            if not self._streaming_subscriptions:
                return True
            symbols = list(self._streaming_subscriptions.keys())
        return self.unsubscribe(symbols)

    def active_subscriptions(self) -> dict[str, dict[str, Any]]:
        """Return a copy of all active streaming subscriptions."""
        with self._stream_lock:
            return dict(self._streaming_subscriptions)

    def add_stream_listener(self, listener: Any) -> None:
        """Register a callback to receive streaming market data or order updates.

        The listener is registered with both the WebSocket multiplexer
        (if available) and the broker's order stream.
        """
        if listener in self._streaming_listeners:
            return
        with self._stream_lock:
            self._streaming_listeners.append(listener)

        ws = self._get_ws_multiplexer()
        if ws is not None and hasattr(ws, "add_market_data_listener"):
            try:
                ws.add_market_data_listener(listener)
            except Exception as exc:
                logger.warning("Failed to add WS market data listener: %s", exc)

        if hasattr(self._broker, "add_order_listener"):
            try:
                self._broker.add_order_listener(listener)
            except Exception as exc:
                logger.warning("Failed to add order listener: %s", exc)

    def remove_stream_listener(self, listener: Any) -> None:
        """Unregister a previously registered streaming listener."""
        with contextlib.suppress(ValueError):
            self._streaming_listeners.remove(listener)

        ws = self._get_ws_multiplexer()
        if ws is not None and hasattr(ws, "remove_market_data_listener"):
            with contextlib.suppress(Exception):
                ws.remove_market_data_listener(listener)

        if hasattr(self._broker, "remove_order_listener"):
            with contextlib.suppress(Exception):
                self._broker.remove_order_listener(listener)

    # ── Instrument APIs ──────────────────────────────────────────────

    def search(self, query: str) -> list[Instrument]:
        query_upper = query.upper()
        results = []
        for instr in self._registry.all():
            if query_upper in instr.symbol:
                results.append(instr)
        return results

    def instrument(self, symbol: str, exchange: str = "NSE") -> Instrument | None:
        return self._registry.resolve(symbol.upper(), exchange)

    def resolve(self, symbol: str, exchange: str = "NSE") -> dict[str, Any]:
        sec_id, seg, exch = self._resolve(symbol, exchange)
        instr = self._registry.resolve(symbol.upper(), exchange)
        return {
            "symbol": symbol.upper(),
            "exchange": exch,
            "security_id": sec_id,
            "segment": seg.value if isinstance(seg, ExchangeSegment) else str(seg),
            "instrument_type": instr.asset_class.value if instr else "EQUITY",
        }

    def universe(self, name: str) -> list[str]:
        return list(_UNIVERSES.get(name.upper(), []))

    # ── Options APIs ─────────────────────────────────────────────────

    def _resolve_expiry(self, underlying: str, expiry: str | int | None) -> str:
        """Resolve an expiry value to a date string.

        * ``None`` → nearest expiry (index 0)
        * ``int``  → expiry at that index (0 = nearest, 1 = next, …)
        * ``str``  → returned as-is
        """
        if isinstance(expiry, str):
            return expiry
        exps = self.expiries(underlying)
        idx = 0 if expiry is None else expiry
        if exps and 0 <= idx < len(exps):
            return exps[idx]
        return ""

    def option_chain(
        self, underlying: str, *, expiry: str | int | None = None, exchange: str = "NFO"
    ) -> pd.DataFrame:
        underlying = underlying.upper()
        expiry_str = self._resolve_expiry(underlying, expiry)

        idx_exchange = "IDX" if _is_index(underlying) else "NSE"
        sec_id, seg, _ = self._resolve(underlying, idx_exchange)
        fno_seg = ExchangeSegment.NSE_FNO

        return self._broker.get_option_chain(underlying, fno_seg, expiry_str)

    def expiries(self, underlying: str) -> list[str]:
        underlying = underlying.upper()
        idx_exchange = "IDX" if _is_index(underlying) else "NSE"
        sec_id, seg, _ = self._resolve(underlying, idx_exchange)
        fno_seg = ExchangeSegment.NSE_FNO

        if hasattr(self._broker, "get_option_expiries_rest"):
            try:
                return self._broker.get_option_expiries_rest(underlying, fno_seg)
            except Exception:
                pass
        if hasattr(self._broker, "options"):
            try:
                return self._broker.options.get_expiries(sec_id, seg)
            except Exception:
                pass
        return []

    def _get_chain(self, underlying: str, expiry: str | int | None) -> pd.DataFrame:
        return self.option_chain(underlying, expiry=expiry)

    def atm(self, underlying: str, *, expiry: str | int | None = None) -> pd.DataFrame:
        chain = self._get_chain(underlying, expiry)
        if chain.empty:
            return chain
        spot = self.ltp(underlying, exchange="IDX")
        step = _strike_step(underlying)
        atm_strike = round(spot / step) * step
        return chain[chain["strike"] == float(atm_strike)]

    def ce(self, underlying: str, *, expiry: str | int | None = None) -> pd.DataFrame:
        chain = self._get_chain(underlying, expiry)
        return chain[chain["option_type"] == "CE"]

    def pe(self, underlying: str, *, expiry: str | int | None = None) -> pd.DataFrame:
        chain = self._get_chain(underlying, expiry)
        return chain[chain["option_type"] == "PE"]

    def otm(self, underlying: str, *, expiry: str | int | None = None) -> pd.DataFrame:
        chain = self._get_chain(underlying, expiry)
        if chain.empty:
            return chain
        spot = self.ltp(underlying, exchange="IDX")
        ce_otm = chain[(chain["option_type"] == "CE") & (chain["strike"] > spot)]
        pe_otm = chain[(chain["option_type"] == "PE") & (chain["strike"] < spot)]
        return pd.concat([ce_otm, pe_otm], ignore_index=True)

    def itm(self, underlying: str, *, expiry: str | int | None = None) -> pd.DataFrame:
        chain = self._get_chain(underlying, expiry)
        if chain.empty:
            return chain
        spot = self.ltp(underlying, exchange="IDX")
        ce_itm = chain[(chain["option_type"] == "CE") & (chain["strike"] < spot)]
        pe_itm = chain[(chain["option_type"] == "PE") & (chain["strike"] > spot)]
        return pd.concat([ce_itm, pe_itm], ignore_index=True)

    def straddle(self, underlying: str, *, expiry: str | int | None = None) -> pd.DataFrame:
        return self.atm(underlying, expiry=expiry)

    def strangle(
        self, underlying: str, *, strikes: int = 2, expiry: str | int | None = None
    ) -> pd.DataFrame:
        chain = self._get_chain(underlying, expiry)
        if chain.empty:
            return chain
        spot = self.ltp(underlying, exchange="IDX")
        step = _strike_step(underlying)
        atm_strike = round(spot / step) * step
        call_strike = atm_strike + (strikes * step)
        put_strike = atm_strike - (strikes * step)
        ce_leg = chain[(chain["option_type"] == "CE") & (chain["strike"] == float(call_strike))]
        pe_leg = chain[(chain["option_type"] == "PE") & (chain["strike"] == float(put_strike))]
        return pd.concat([ce_leg, pe_leg], ignore_index=True)

    def greeks(self, underlying: str, *, expiry: str | int | None = None) -> pd.DataFrame:
        chain = self._get_chain(underlying, expiry)
        greek_cols = ["strike", "option_type", "iv", "delta", "gamma", "theta", "vega", "rho"]
        available = [c for c in greek_cols if c in chain.columns]
        return chain[available] if not chain.empty else chain

    def iv(self, underlying: str, *, expiry: str | int | None = None) -> pd.DataFrame:
        chain = self._get_chain(underlying, expiry)
        if chain.empty:
            return chain
        return chain[["strike", "option_type", "iv"]]

    def pcr(self, underlying: str, *, expiry: str | int | None = None) -> float:
        chain = self._get_chain(underlying, expiry)
        if chain.empty:
            return 0.0
        ce_oi = chain[chain["option_type"] == "CE"]["oi"].sum()
        pe_oi = chain[chain["option_type"] == "PE"]["oi"].sum()
        if ce_oi == 0:
            return 0.0
        return float(pe_oi / ce_oi)

    def max_pain(self, underlying: str, *, expiry: str | int | None = None) -> float:
        chain = self._get_chain(underlying, expiry)
        if chain.empty:
            return 0.0
        ce = chain[chain["option_type"] == "CE"][["strike", "oi"]].values
        pe = chain[chain["option_type"] == "PE"][["strike", "oi"]].values
        strikes = sorted(chain["strike"].unique())
        if not strikes:
            return 0.0
        ce_strikes, ce_oi = (ce[:, 0], ce[:, 1]) if len(ce) else ([], [])
        pe_strikes, pe_oi = (pe[:, 0], pe[:, 1]) if len(pe) else ([], [])
        min_pain = float("inf")
        max_pain_strike = 0.0
        for s in strikes:
            pain = 0.0
            for cs, coi in zip(ce_strikes, ce_oi, strict=False):
                if cs <= s:
                    pain += float(coi) * (s - float(cs))
            for ps, poi in zip(pe_strikes, pe_oi, strict=False):
                if ps >= s:
                    pain += float(poi) * (float(ps) - s)
            if pain < min_pain:
                min_pain = pain
                max_pain_strike = float(s)
        return max_pain_strike

    # ── Futures APIs ─────────────────────────────────────────────────

    def future(self, underlying: str) -> Any:
        if hasattr(self._broker, "get_futures_rest"):
            try:
                contracts = self._broker.get_futures_rest(
                    underlying.upper(), ExchangeSegment.NSE_FNO
                )
                return contracts[0] if contracts else None
            except Exception:
                pass
        if hasattr(self._broker, "futures"):
            try:
                return self._broker.futures.get_nearest_contract(
                    underlying.upper(), ExchangeSegment.NSE_FNO
                )
            except Exception:
                pass
        return None

    def next_future(self, underlying: str) -> Any:
        if hasattr(self._broker, "get_futures_rest"):
            try:
                contracts = self._broker.get_futures_rest(
                    underlying.upper(), ExchangeSegment.NSE_FNO
                )
                return contracts[1] if len(contracts) > 1 else None
            except Exception:
                pass
        return None

    def future_chain(self, underlying: str) -> list[Any]:
        if hasattr(self._broker, "get_futures_rest"):
            try:
                return self._broker.get_futures_rest(underlying.upper(), ExchangeSegment.NSE_FNO)
            except Exception:
                pass
        if hasattr(self._broker, "futures"):
            try:
                return self._broker.futures.get_contracts(
                    underlying.upper(), ExchangeSegment.NSE_FNO
                )
            except Exception:
                pass
        return []

    # ── Order APIs ───────────────────────────────────────────────────

    def buy(
        self,
        symbol: str,
        qty: int,
        *,
        price: float | Decimal = 0,
        exchange: str = "NSE",
        product: str = "INTRADAY",
        order_type: str = "MARKET",
        trigger_price: float | Decimal = 0,
    ) -> OrderResponse:
        return self._place(
            symbol,
            Side.BUY,
            qty,
            price=price,
            exchange=exchange,
            product=product,
            order_type=order_type,
            trigger_price=trigger_price,
        )

    def sell(
        self,
        symbol: str,
        qty: int,
        *,
        price: float | Decimal = 0,
        exchange: str = "NSE",
        product: str = "INTRADAY",
        order_type: str = "MARKET",
        trigger_price: float | Decimal = 0,
    ) -> OrderResponse:
        return self._place(
            symbol,
            Side.SELL,
            qty,
            price=price,
            exchange=exchange,
            product=product,
            order_type=order_type,
            trigger_price=trigger_price,
        )

    def market_buy(self, symbol: str, qty: int, **kwargs: Any) -> OrderResponse:
        return self.buy(symbol, qty, order_type="MARKET", **kwargs)

    def market_sell(self, symbol: str, qty: int, **kwargs: Any) -> OrderResponse:
        return self.sell(symbol, qty, order_type="MARKET", **kwargs)

    def limit_buy(
        self, symbol: str, qty: int, price: float | Decimal, **kwargs: Any
    ) -> OrderResponse:
        return self.buy(symbol, qty, price=price, order_type="LIMIT", **kwargs)

    def limit_sell(
        self, symbol: str, qty: int, price: float | Decimal, **kwargs: Any
    ) -> OrderResponse:
        return self.sell(symbol, qty, price=price, order_type="LIMIT", **kwargs)

    def sl_buy(
        self, symbol: str, qty: int, trigger_price: float | Decimal, **kwargs: Any
    ) -> OrderResponse:
        return self.buy(
            symbol, qty, trigger_price=trigger_price, order_type="STOP_LOSS_MARKET", **kwargs
        )

    def sl_sell(
        self, symbol: str, qty: int, trigger_price: float | Decimal, **kwargs: Any
    ) -> OrderResponse:
        return self.sell(
            symbol, qty, trigger_price=trigger_price, order_type="STOP_LOSS_MARKET", **kwargs
        )

    def bo(
        self,
        symbol: str,
        qty: int,
        side: str,
        price: float | Decimal,
        target: float | Decimal,
        stop_loss: float | Decimal,
        trailing_jump: float | Decimal = 0,
        **kwargs: Any,
    ) -> OrderResponse:
        self._ensure_connected()
        self._validate_qty(qty)
        if hasattr(self._broker, "place_super_order_rest"):
            from brokers.common.core.models import OrderRequest

            exchange = kwargs.get("exchange", "NSE")
            sec_id, seg, _ = self._resolve(symbol, exchange)
            req = OrderRequest(
                security_id=sec_id,
                symbol=symbol,
                exchange=exchange,
                exchange_segment=seg,
                transaction_type=TransactionType.BUY
                if side.upper() == "BUY"
                else TransactionType.SELL,
                quantity=qty,
                price=Decimal(str(price)),
            )
            result = self._broker.place_super_order_rest(
                req,
                Decimal(str(target)),
                Decimal(str(stop_loss)),
                Decimal(str(trailing_jump)),
            )
            return OrderResponse(
                success=True,
                order_id=str(getattr(result, "order_id", "")),
                message="Bracket order placed",
            )
        return OrderResponse(success=False, message="Broker does not support bracket orders")

    def co(
        self, symbol: str, qty: int, side: str, stop_loss: float | Decimal, **kwargs: Any
    ) -> OrderResponse:
        self._ensure_connected()
        self._validate_qty(qty)
        if hasattr(self._broker, "cover_order"):
            try:
                from brokers.common.core.models import OrderRequest

                exchange = kwargs.get("exchange", "NSE")
                sec_id, seg, _ = self._resolve(symbol, exchange)
                req = OrderRequest(
                    security_id=sec_id,
                    symbol=symbol,
                    exchange=exchange,
                    exchange_segment=seg,
                    transaction_type=TransactionType.BUY
                    if side.upper() == "BUY"
                    else TransactionType.SELL,
                    quantity=qty,
                )
                result = self._broker.cover_order.place_cover_order(req, Decimal(str(stop_loss)))
                return OrderResponse(
                    success=True,
                    order_id=str(getattr(result, "order_id", "")),
                    message="Cover order placed",
                )
            except Exception as e:
                return OrderResponse(success=False, message=str(e))
        return OrderResponse(success=False, message="Broker does not support cover orders")

    def basket(self, orders: list[dict[str, Any]]) -> list[OrderResponse]:
        results = []
        for o in orders:
            symbol = o["symbol"]
            qty = o["qty"]
            side = o.get("side", "BUY")
            if side.upper() == "BUY":
                results.append(
                    self.buy(
                        symbol,
                        qty,
                        **{k: v for k, v in o.items() if k not in ("symbol", "qty", "side")},
                    )
                )
            else:
                results.append(
                    self.sell(
                        symbol,
                        qty,
                        **{k: v for k, v in o.items() if k not in ("symbol", "qty", "side")},
                    )
                )
        return results

    def slice(self, symbol: str, qty: int, side: str = "BUY", **kwargs: Any) -> list[OrderResponse]:
        self._ensure_connected()
        self._validate_qty(qty)
        if hasattr(self._broker, "place_slice_order_rest"):
            from brokers.common.core.models import SliceOrderRequest

            exchange = kwargs.get("exchange", "NSE")
            sec_id, seg, _ = self._resolve(symbol, exchange)
            req = SliceOrderRequest(
                symbol=symbol,
                exchange=exchange,
                exchange_segment=seg,
                transaction_type=TransactionType.BUY
                if side.upper() == "BUY"
                else TransactionType.SELL,
                quantity=qty,
            )
            try:
                results = self._broker.place_slice_order_rest(req)
                return [
                    OrderResponse(
                        success=True,
                        order_id=str(getattr(r, "order_id", "")),
                        message="Slice child order",
                    )
                    for r in results
                ]
            except Exception as e:
                return [OrderResponse(success=False, message=str(e))]
        slice_qty = kwargs.get("slice_qty", qty // 10 or 1)
        results = []
        remaining = qty
        while remaining > 0:
            q = min(slice_qty, remaining)
            if side.upper() == "BUY":
                results.append(
                    self.buy(symbol, q, **{k: v for k, v in kwargs.items() if k != "slice_qty"})
                )
            else:
                results.append(
                    self.sell(symbol, q, **{k: v for k, v in kwargs.items() if k != "slice_qty"})
                )
            remaining -= q
        return results

    def modify(self, order_id: str, **kwargs: Any) -> OrderResponse:
        if hasattr(self._broker, "modify_order_rest"):
            try:
                self._broker.modify_order_rest(order_id, **kwargs)
                return OrderResponse(success=True, order_id=order_id, message="Modified")
            except Exception as e:
                return OrderResponse(success=False, order_id=order_id, message=str(e))
        return OrderResponse(success=False, message="Broker does not support modify")

    def cancel(self, order_id: str) -> OrderResponse:
        success = self._broker.cancel_order(order_id)
        return OrderResponse(
            success=success,
            order_id=order_id,
            message="Cancelled" if success else "Cancel failed",
        )

    def cancel_all(self) -> list[OrderResponse]:
        results = []
        for order in self._broker.get_orders():
            if not order.status.is_terminal:
                results.append(self.cancel(order.order_id))
        return results

    # ── Position Management ──────────────────────────────────────────

    def close(self, symbol: str, *, exchange: str = "NSE") -> OrderResponse:
        symbol = symbol.upper()
        for pos in self._broker.get_positions():
            if pos.symbol.upper() == symbol and pos.quantity != 0:
                side = Side.SELL if pos.quantity > 0 else Side.BUY
                return self._place(
                    symbol,
                    side,
                    abs(pos.quantity),
                    exchange=exchange,
                    product=pos.product_type.value
                    if isinstance(pos.product_type, ProductType)
                    else str(pos.product_type),
                )
        return OrderResponse(success=False, message=f"No open position for {symbol}")

    def close_all(self) -> list[OrderResponse]:
        results = []
        for pos in self._broker.get_positions():
            if pos.quantity != 0:
                side = Side.SELL if pos.quantity > 0 else Side.BUY
                results.append(
                    self._place(
                        pos.symbol,
                        side,
                        abs(pos.quantity),
                        product=pos.product_type.value
                        if isinstance(pos.product_type, ProductType)
                        else str(pos.product_type),
                    )
                )
        return results

    def exit_intraday(self) -> list[OrderResponse]:
        results = []
        for pos in self._broker.get_positions():
            pt = (
                pos.product_type.value
                if isinstance(pos.product_type, ProductType)
                else str(pos.product_type)
            )
            if pt == "INTRADAY" and pos.quantity != 0:
                side = Side.SELL if pos.quantity > 0 else Side.BUY
                results.append(self._place(pos.symbol, side, abs(pos.quantity), product="INTRADAY"))
        return results

    # ── Diagnostics ──────────────────────────────────────────────────

    def rate_limits(self) -> dict[str, Any]:
        if hasattr(self._broker, "rate_limiter"):
            rl = self._broker.rate_limiter
            info = {}
            if hasattr(rl, "_buckets"):
                for name, bucket in rl._buckets.items():
                    info[name] = {
                        "tokens": float(bucket.tokens) if hasattr(bucket, "tokens") else None,
                        "capacity": bucket.capacity if hasattr(bucket, "capacity") else None,
                    }
            return info
        return {}

    def status(self) -> dict[str, Any]:
        h = self.health()
        if hasattr(self._broker, "status"):
            h["connection_status"] = self._broker.status.value
        return h

    def connection_info(self) -> dict[str, Any]:
        info = {
            "broker": self._broker.name,
            "broker_id": self._broker.broker_id,
            "connected": self._is_connected(),
        }
        if hasattr(self._broker, "settings"):
            s = self._broker.settings
            info["auth_mode"] = getattr(s, "auth_mode", "")
            info["client_id"] = getattr(s, "client_id", "")
        return info

    # ── Internal Order Placement ─────────────────────────────────────

    def _place(
        self,
        symbol: str,
        side: Side,
        qty: int,
        *,
        price: float | Decimal = 0,
        exchange: str = "NSE",
        product: str = "INTRADAY",
        order_type: str = "MARKET",
        trigger_price: float | Decimal = 0,
    ) -> OrderResponse:
        self._ensure_connected()
        self._validate_qty(qty)
        if order_type == "LIMIT" and Decimal(str(price)) <= 0:
            raise ValueError(f"LIMIT order for {symbol!r} requires price > 0, got {price}")
        if order_type in ("STOP_LOSS", "STOP_LOSS_MARKET") and Decimal(str(trigger_price)) <= 0:
            raise ValueError(
                f"STOP_LOSS order for {symbol!r} requires trigger_price > 0, got {trigger_price}"
            )
        return self._broker.place_order(
            symbol,
            exchange,
            side,
            qty,
            Decimal(str(price)),
            order_type,
            product,
            "DAY",
            Decimal(str(trigger_price)),
        )

    # ── Repr ─────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        status = "connected" if self._is_connected() else "disconnected"
        return f"Gateway(broker={self._broker.name!r}, status={status})"

    def __enter__(self) -> Gateway:
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.disconnect()
