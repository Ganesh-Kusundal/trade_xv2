"""Canonical enums — the vocabulary of the trading domain.

These are the single source of truth for every enum used across the
broker-agnostic core. Broker-specific status mappers live in each
broker's ``status_mapper.py`` and delegate to :meth:`OrderStatus.normalize`
for canonical values.
"""

from __future__ import annotations

from enum import Enum


class Side(str, Enum):
    """Order side — BUY or SELL."""

    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    """Canonical order status.

    Broker-specific variants (TRANSIT, TRIGGER PENDING, COMPLETE, etc.)
    must be normalized to these values at the adapter boundary.
    """

    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

    @classmethod
    def normalize(cls, broker_status: str) -> OrderStatus:
        """Map broker-specific status strings to canonical status."""
        normalized = broker_status.upper().strip().replace(" ", "_")

        _MAP: dict[str, OrderStatus] = {
            "OPEN": cls.OPEN,
            "PARTIALLY_FILLED": cls.PARTIALLY_FILLED,
            "FILLED": cls.FILLED,
            "CANCELLED": cls.CANCELLED,
            "REJECTED": cls.REJECTED,
            "EXPIRED": cls.EXPIRED,
            "EXECUTED": cls.FILLED,
            "COMPLETE": cls.FILLED,
            "TRADED": cls.FILLED,
            "TRIGGER_PENDING": cls.OPEN,
            "TRANSIT": cls.OPEN,
            "PENDING": cls.OPEN,
            "PLACED": cls.OPEN,
            "TRIGGERED": cls.OPEN,
            "OPEN_PENDING": cls.OPEN,
            "PUT_ORDER_REQ_RECEIVED": cls.OPEN,
            "PARTIAL": cls.PARTIALLY_FILLED,
            "PARTIALLY_EXECUTED": cls.PARTIALLY_FILLED,
            "PARTIALLY_CANCELLED": cls.PARTIALLY_FILLED,
            "OPEN_ORDER": cls.OPEN,
            "TRIGGER_ORDER": cls.OPEN,
            "CANCEL_PENDING": cls.CANCELLED,
            "REJECTED_BY_BROKER": cls.REJECTED,
            "REJECTED_BY_EXCHANGE": cls.REJECTED,
            "MODIFIED": cls.OPEN,
            "MODIFIED_PENDING": cls.OPEN,
            "AFTER_MARKET_ORDER_REQ_RECEIVED": cls.OPEN,
            "AMO": cls.OPEN,
            "MARGIN_TRADED": cls.PARTIALLY_FILLED,
        }

        return _MAP.get(normalized, cls.OPEN)

    @property
    def is_terminal(self) -> bool:
        return self in {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        }


class ProductType(str, Enum):
    """Canonical product types."""

    CNC = "CNC"
    INTRADAY = "INTRADAY"
    MARGIN = "MARGIN"
    MTF = "MTF"


class OrderType(str, Enum):
    """Canonical order types."""

    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_MARKET = "STOP_LOSS_MARKET"


class Validity(str, Enum):
    """Order validity."""

    DAY = "DAY"
    IOC = "IOC"


class ExchangeSegment(str, Enum):
    """Exchange segments supported by the broker system.

    The values use canonical wire-format strings (e.g. "NSE_EQ") so the
    segment string in the HTTP payload matches what the broker expects.
    """

    NSE = "NSE_EQ"
    BSE = "BSE_EQ"
    NSE_FNO = "NSE_FNO"
    BSE_FNO = "BSE_FNO"
    MCX = "MCXCOMM"
    NSE_CURRENCY = "NSE_CURRENCY"
    BSE_CURRENCY = "BSE_CURRENCY"
    IDX_I = "IDX_I"


class InstrumentType(str, Enum):
    """Canonical instrument type categories."""

    EQUITY = "EQUITY"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"
    CURRENCY = "CURRENCY"
    COMMODITY = "COMMODITY"
    INDEX = "INDEX"


class Capability(str, Enum):
    """Capabilities a broker connection can provide."""

    MARKET_DATA = "market_data"
    ORDER_COMMAND = "order_command"
    ORDER_QUERY = "order_query"
    PORTFOLIO = "portfolio"
    OPTIONS_CHAIN = "options_chain"
    INSTRUMENTS = "instruments"
    FUTURES = "futures"
    HISTORICAL_DATA = "historical_data"
    WEBSOCKET = "websocket"
    # BRACKET_ORDER removed — not supported in Upstox v3 API (as of 2024)
    COVER_ORDER = "cover_order"
    GTT_ORDER = "gtt_order"
    SLICE_ORDER = "slice_order"
    MARGIN = "margin"
    NEWS = "news"
    SESSION_RISK = "session_risk"
    ALERTS = "alerts"
    MARKET_STATUS = "market_status"
    DEPTH = "depth"
    ORDER_STREAM = "order_stream"
    IDEMPOTENCY = "idempotency"
    MULTI_ORDER = "multi_order"
    KILL_SWITCH = "kill_switch"
    STATIC_IP = "static_ip"
    SMARTLIST = "smartlist"
    FII_DII = "fii_dii"
    OI_PCR_MAXPAIN = "oi_pcr_maxpain"
    MARKET_INTELLIGENCE = "market_intelligence"
    FUNDAMENTALS = "fundamentals"
    IPO = "ipo"
    MUTUAL_FUNDS = "mutual_funds"
    PAYMENTS = "payments"
    INSTRUMENT_SEARCH = "instrument_search"
    HISTORICAL_TRADES = "historical_trades"
    TSL = "trailing_stop_loss"
    MTF = "mtf"
    WEBHOOKS = "webhooks"
    AMO_ORDER = "amo_order"
    EXIT_ALL = "exit_all"
    PORTFOLIO_STREAM = "portfolio_stream"
    ORDER_SLICING = "order_slicing"
    DEPTH_30 = "depth_30"
    LEVEL2_MARKET_DATA = "level2_market_data"
    OPTION_GREEKS = "option_greeks"
    GLOBAL_MARKETS = "global_markets"
    VOLATILITY_INDEX = "volatility_index"


class ConnectionStatus(str, Enum):
    """Lifecycle status of a broker connection."""

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"

    def is_connected(self) -> bool:
        return self == ConnectionStatus.CONNECTED
