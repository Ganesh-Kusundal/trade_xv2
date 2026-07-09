"""TradeHull-friendly display names ↔ canonical :class:`InstrumentId`.

Display grammar (human / CLI / TradeHull migrants)::

    Equity:   RELIANCE
    Index:    NIFTY  (when treat_as_index / known index list)
    Future:   NIFTY 27 NOV FUT   |  NIFTY NOV 2026 FUT
    Option:   NIFTY 21 NOV 24400 CALL  |  NIFTY 21 NOV 24400 CE

Canonical remains the source of truth for domain/OMS/storage::

    NSE:RELIANCE
    NFO:NIFTY:20261121:24400:CE
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from domain.instruments.instrument_id import InstrumentId
from domain.symbols import normalize_exchange, normalize_symbol

_MONTHS: dict[str, int] = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "SEPT": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}
_MONTH_ABBR = {
    1: "JAN",
    2: "FEB",
    3: "MAR",
    4: "APR",
    5: "MAY",
    6: "JUN",
    7: "JUL",
    8: "AUG",
    9: "SEP",
    10: "OCT",
    11: "NOV",
    12: "DEC",
}

# Common Indian index underlyings (display bare name → index, not equity)
_INDEX_NAMES = frozenset(
    {
        "NIFTY",
        "BANKNIFTY",
        "FINNIFTY",
        "MIDCPNIFTY",
        "SENSEX",
        "BANKEX",
    }
)

_RIGHT_MAP = {
    "CALL": "CE",
    "PUT": "PE",
    "CE": "CE",
    "PE": "PE",
    "C": "CE",
    "P": "PE",
}

# Option: UNDERLYING [DD] MON [YYYY] STRIKE RIGHT
_OPTION_RE = re.compile(
    r"^"
    r"(?P<underlying>[A-Z0-9]+)"
    r"\s+"
    r"(?:(?P<day>\d{1,2})\s+)?"
    r"(?P<mon>[A-Z]{3,4})"
    r"(?:\s+(?P<year>\d{4}))?"
    r"\s+"
    r"(?P<strike>\d+(?:\.\d+)?)"
    r"\s+"
    r"(?P<right>CALL|PUT|CE|PE|C|P)"
    r"$",
    re.IGNORECASE,
)

# Future: UNDERLYING [DD] MON [YYYY] FUT
_FUTURE_RE = re.compile(
    r"^"
    r"(?P<underlying>[A-Z0-9]+)"
    r"\s+"
    r"(?:(?P<day>\d{1,2})\s+)?"
    r"(?P<mon>[A-Z]{3,4})"
    r"(?:\s+(?P<year>\d{4}))?"
    r"\s+"
    r"FUT(?:URES?)?"
    r"$",
    re.IGNORECASE,
)

# Bare symbol (equity / index / underlying)
_BARE_RE = re.compile(r"^[A-Z][A-Z0-9]*$", re.IGNORECASE)

# Already-canonical InstrumentId string
_CANONICAL_RE = re.compile(r"^[A-Z]{2,4}:[A-Z0-9]+", re.IGNORECASE)


def _resolve_year_month_day(
    *,
    mon: str,
    day: str | None,
    year: str | None,
    default_year: int | None,
    as_of: date | None,
) -> date:
    month = _MONTHS.get(mon.upper())
    if month is None:
        raise ValueError(f"Unknown month abbreviation: {mon!r}")
    d = int(day) if day else 1
    ref = as_of or date.today()
    if year:
        y = int(year)
    elif default_year is not None:
        y = default_year
    else:
        y = ref.year
        # If the date is already past (and no day given, end-of-month-ish),
        # roll to next year for F&O continuity.
        candidate = date(y, month, min(d, 28))
        if candidate < ref.replace(day=1):
            y = ref.year + 1
    try:
        return date(y, month, d)
    except ValueError as exc:
        raise ValueError(f"Invalid expiry date components: {y}-{month}-{d}") from exc


def _default_fno_exchange(underlying: str, default_exchange: str) -> str:
    """NFO for equity indices, MCX for commodities when exchange looks equity."""
    u = underlying.upper()
    de = normalize_exchange(default_exchange)
    if de in {"NFO", "MCX", "BFO"}:
        return de
    # Commodity underlyings commonly on MCX
    if u in {"CRUDEOIL", "GOLD", "SILVER", "NATURALGAS", "COPPER", "ZINC", "NICKEL"}:
        return "MCX"
    return "NFO"


def parse_display_name(
    name: str,
    *,
    default_exchange: str = "NSE",
    default_year: int | None = None,
    as_of: date | None = None,
    treat_as_index: bool | None = None,
) -> InstrumentId:
    """Parse a TradeHull-style or bare display name into :class:`InstrumentId`.

    Parameters
    ----------
    name:
        Display string or canonical ``EXCHANGE:…`` id.
    default_exchange:
        Used for bare equities/indices and when F&O exchange is not implied.
        Options/futures default to NFO (or MCX for commodities) when this is NSE/BSE.
    default_year:
        Year for month-only display names when omitted from the string.
    as_of:
        Reference date for rolling year inference (default: today).
    treat_as_index:
        If True, bare names become indices. If None, known index names auto-detect.
    """
    raw = " ".join(str(name).strip().split())
    if not raw:
        raise ValueError("Empty display name")

    # Pass-through canonical ids
    if ":" in raw and _CANONICAL_RE.match(raw):
        return InstrumentId.parse(raw)

    upper = raw.upper()

    m = _OPTION_RE.match(upper)
    if m:
        underlying = normalize_symbol(m.group("underlying"))
        expiry = _resolve_year_month_day(
            mon=m.group("mon"),
            day=m.group("day"),
            year=m.group("year"),
            default_year=default_year,
            as_of=as_of,
        )
        strike = Decimal(m.group("strike"))
        right = _RIGHT_MAP[m.group("right").upper()]
        exch = _default_fno_exchange(underlying, default_exchange)
        return InstrumentId.option(exch, underlying, expiry, strike, right)

    m = _FUTURE_RE.match(upper)
    if m:
        underlying = normalize_symbol(m.group("underlying"))
        expiry = _resolve_year_month_day(
            mon=m.group("mon"),
            day=m.group("day"),
            year=m.group("year"),
            default_year=default_year,
            as_of=as_of,
        )
        exch = _default_fno_exchange(underlying, default_exchange)
        return InstrumentId.future(exch, underlying, expiry)

    if _BARE_RE.match(upper):
        sym = normalize_symbol(upper)
        is_index = treat_as_index if treat_as_index is not None else sym in _INDEX_NAMES
        exch = normalize_exchange(default_exchange)
        # Indices on NSE/BSE/INDEX → NSE for our InstrumentId
        if is_index:
            if exch not in InstrumentId.VALID_EXCHANGES:
                exch = "NSE"
            return InstrumentId.index(exch if exch in {"NSE", "BSE"} else "NSE", sym)
        return InstrumentId.equity(exch, sym)

    raise ValueError(
        f"Unrecognized display name: {name!r}. "
        "Expected bare symbol, 'UNDERLYING DD MON STRIKE CALL|PUT', "
        "or 'UNDERLYING DD MON FUT'."
    )


def format_display_name(instrument_id: InstrumentId | str) -> str:
    """Format canonical id as a TradeHull-style display name."""
    iid = (
        instrument_id
        if isinstance(instrument_id, InstrumentId)
        else InstrumentId.parse(str(instrument_id))
    )
    if iid.is_option and iid.expiry is not None and iid.strike is not None:
        mon = _MONTH_ABBR[iid.expiry.month]
        right = "CALL" if iid.right == "CE" else "PUT"
        strike_s = (
            str(int(iid.strike))
            if iid.strike == iid.strike.to_integral_value()
            else str(iid.strike)
        )
        return f"{iid.underlying} {iid.expiry.day} {mon} {strike_s} {right}"

    if iid.is_future and iid.expiry is not None:
        mon = _MONTH_ABBR[iid.expiry.month]
        return f"{iid.underlying} {iid.expiry.day} {mon} FUT"

    # Equity / index
    return iid.underlying
