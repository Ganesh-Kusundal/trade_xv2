"""Contract-centric historical bar models (exact InstrumentId identity)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from domain.historical.contract_state import ContractState
from domain.instruments.instrument_id import InstrumentId
from domain.parsing import require_tz_aware

CONTRACT_CANONICAL_COLUMNS: tuple[str, ...] = (
    "timestamp",
    "instrument_id",
    "symbol",
    "underlying",
    "exchange",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "oi",
    "expiry_date",
    "strike",
    "option_type",
    "interval_min",
    "contract_state",
)


@dataclass(frozen=True, slots=True)
class ContractHistoricalQuery:
    """Fetch OHLCV for one exact contract over a date range."""

    instrument: InstrumentId
    from_date: date
    to_date: date
    timeframe: str = "5m"
    contract_state: ContractState = ContractState.AUTO
    allow_partial: bool = False
    broker_symbol: str | None = None
    expired_instrument_key: str | None = None
    request_id: str | None = None
    # Dhan rolling expired index options only (NFO); not canonical contract identity.
    rolling_expiry_kind: str | None = None  # WEEK | MONTH
    rolling_expiry_code: int | None = None
    rolling_strike_offset: int | None = None


@dataclass(frozen=True, slots=True)
class ContractBar:
    """One normalized contract OHLCV bar."""

    timestamp: datetime
    instrument_id: str
    symbol: str
    underlying: str
    exchange: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    oi: int = 0
    expiry_date: str = ""
    strike: float | None = None
    option_type: str | None = None
    interval_min: int = 5
    contract_state: str = "active"

    def __post_init__(self) -> None:
        require_tz_aware(
            self.timestamp,
            f"ContractBar.timestamp must be timezone-aware, got naive {self.timestamp!r}",
        )


@dataclass
class ContractHistoricalSeries:
    """Merged bars for one contract query."""

    query: ContractHistoricalQuery
    bars: list[ContractBar] = field(default_factory=list)
    degraded: bool = False
    degraded_reason: str = ""
