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


class AssetClass(StrEnum):
    EQUITY = "EQUITY"
    DERIVATIVE = "DERIVATIVE"
    COMMODITY = "COMMODITY"
    CURRENCY = "CURRENCY"


class InstrumentType(StrEnum):
    EQUITY = "EQUITY"
    FUTURE = "FUTURE"
    OPTION = "OPTION"
    INDEX = "INDEX"


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
