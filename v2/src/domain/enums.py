"""Domain enumerations — StrEnum for JSON serialization."""

from enum import StrEnum


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(StrEnum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


class TimeInForce(StrEnum):
    DAY = "DAY"
    IOC = "IOC"
    GTC = "GTC"


class ProductType(StrEnum):
    """Broker-agnostic order product vocabulary.

    Per-broker Wire.from_place_command translates these to each broker's
    own strings (Dhan: CNC/INTRADAY/MARGIN/MTF/CO; Upstox: D/I/MTF/CO) —
    callers use this enum, never a raw broker-native string.
    """

    INTRADAY = "INTRADAY"
    DELIVERY = "DELIVERY"
    MARGIN = "MARGIN"
    MTF = "MTF"
    COVER_ORDER = "COVER_ORDER"


class Environment(StrEnum):
    REPLAY = "REPLAY"
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    LIVE = "LIVE"


class ExecutionTargetKind(StrEnum):
    REPLAY = "REPLAY"
    SIMULATED = "SIMULATED"
    PAPER = "PAPER"
    BROKER = "BROKER"


class BrokerId(StrEnum):
    DHAN = "DHAN"
    UPSTOX = "UPSTOX"
    PAPER = "PAPER"


class ExchangeId(StrEnum):
    NSE = "NSE"
    BSE = "BSE"
    MCX = "MCX"
    NFO = "NFO"
    BFO = "BFO"
    CDS = "CDS"
    BCD = "BCD"
    IDX = "IDX"
    # Dhan dual-lists some MCX commodity contracts under an NSE-routed
    # listing with its own distinct security_id (same real contract, two
    # tradeable listings) — kept as its own exchange so the two canonical
    # InstrumentIds never collide (see dhan/adapters/instruments.py _SEGMENT_MAP).
    NSE_COMM = "NSE_COMM"


class AssetClass(StrEnum):
    EQUITY = "EQUITY"
    DERIVATIVE = "DERIVATIVE"
    COMMODITY = "COMMODITY"
    CURRENCY = "CURRENCY"
    INDEX = "INDEX"


class InstrumentType(StrEnum):
    EQUITY = "EQUITY"
    FUTURE = "FUTURE"
    OPTION = "OPTION"
    INDEX = "INDEX"


class AssetKind(StrEnum):
    """Canonical InstrumentId classification — richer than InstrumentType/AssetClass
    (adds ETF/CURRENCY/COMMODITY/SPOT/BOND), ported from legacy src's proven design.
    """

    EQUITY = "EQUITY"
    INDEX = "INDEX"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"
    ETF = "ETF"
    CURRENCY = "CURRENCY"
    COMMODITY = "COMMODITY"
    SPOT = "SPOT"
    BOND = "BOND"

    @classmethod
    def parse(cls, value: "str | AssetKind | None") -> "AssetKind | None":
        if value is None:
            return None
        if isinstance(value, AssetKind):
            return value
        key = str(value).strip().upper()
        aliases = {"FUTURE": cls.FUTURES, "OPTION": cls.OPTIONS}
        if key in aliases:
            return aliases[key]
        try:
            return cls(key)
        except ValueError:
            return None


class OptionType(StrEnum):
    CALL = "CALL"
    PUT = "PUT"


class SignalDirection(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"


class RiskLevel(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class DriftSeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Currency(StrEnum):
    INR = "INR"


class ComponentState(StrEnum):
    UNINITIALIZED = "UNINITIALIZED"
    INITIALIZED = "INITIALIZED"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"
