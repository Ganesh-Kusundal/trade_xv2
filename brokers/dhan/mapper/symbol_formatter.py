"""Dhan / Tradehull canonical symbol formatter — Trade_J aligned.

Reference: Trade_J ``ContractSymbolNormalizer`` (``trade-core``).
ContractSymbolNormalizerTest + ContractSymbolNormalizerStrictTest are the
single source of truth for format and edge-case behaviour.

Canonical formats (human-readable, for UI / strategy / OMS / DB):

    Option  :  {UNDERLYING} {dd} {MMM} {STRIKE} CALL|PUT
               NIFTY 26 MAY 30750 CALL
               BANKNIFTY 30 JUN 30000 PUT

    Future  :  {UNDERLYING} {dd} {MMM} FUT
               NIFTY 30 JUN FUT

    Equity  :  Uppercase symbol  (SBIN, INFY, HDFCBANK)

Alias normalisations (applied during parse, reflected in canonical output):

    CE  → CALL         PE  → PUT
    C   → CALL         P   → PUT
    All-casing normalised to upper

Accepted input forms (all round-trippable):

    Spaced   :  NIFTY 30 JUN FUT            BANKNIFTY 30 JUN 30000 CALL
    Spaced w/ alias : NIFTY 26 MAY 30750 CE   BANKNIFTY 26 MAY 30000 PE
    Compact  :  NIFTY30JUNFUT               BANKNIFTY30JUN30000CE
    Broker   :  BANKNIFTY-Jun2026-30000-CE   (hyphens/underscores stripped)

Compact ↔ canonical round-trips are validated against every Java fixture.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "brokers.dhan.mapper.symbol_formatter is deprecated. Use InstrumentService or contract_symbol_normalizer instead.",
    DeprecationWarning,
    stacklevel=2,
)

__deprecated__ = True

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

# ── Compiled regex patterns ───────────────────────────────────────────────────
# Copied verbatim from Trade_J ContractSymbolNormalizer patterns.
# (?i) flag = case-insensitive; we also normalise input to upper before matching.

_SPACED_OPTION = re.compile(
    r"^(?P<underlying>[A-Z&\-\s]+)\s+"
    r"(?P<day>\d{1,2})\s+"
    r"(?P<month>[A-Z]{3})\s+"
    r"(?P<strike>\d+(?:\.\d+)?)\s+"
    r"(?P<type>CE|PE|CALL|PUT|C|P)$",
    re.IGNORECASE,
)

_COMPACT_OPTION = re.compile(
    r"^(?P<underlying>[A-Z&]+)"
    r"(?P<day>\d{2})"
    r"(?P<month>[A-Z]{3})"
    r"(?P<strike>\d+(?:\.\d+)?)"
    r"(?P<type>CE|PE|CALL|PUT|C|P)$",
    re.IGNORECASE,
)

_SPACED_FUTURE = re.compile(
    r"^(?P<underlying>[A-Z&\-\s]+)\s+"
    r"(?P<day>\d{1,2})\s+"
    r"(?P<month>[A-Z]{3})\s+"
    r"FUT(?:URES)?$",
    re.IGNORECASE,
)

_COMPACT_FUTURE = re.compile(
    r"^(?P<underlying>[A-Z&]+)"
    r"(?P<day>\d{2})"
    r"(?P<month>[A-Z]{3})"
    r"FUT(?:URES)?$",
    re.IGNORECASE,
)

# ── Month table ───────────────────────────────────────────────────────────────
# 3-char abbreviation → (2-digit seq, canonical 3-char upper display)
_MONTH_TO_NUM: dict[str, tuple[str, str]] = {
    "JAN": ("01", "JAN"),
    "FEB": ("02", "FEB"),
    "MAR": ("03", "MAR"),
    "APR": ("04", "APR"),
    "MAY": ("05", "MAY"),
    "JUN": ("06", "JUN"),
    "JUL": ("07", "JUL"),
    "AUG": ("08", "AUG"),
    "SEP": ("09", "SEP"),
    "OCT": ("10", "OCT"),
    "NOV": ("11", "NOV"),
    "DEC": ("12", "DEC"),
}


# ── Parsed result ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ParsedContract:
    """Components extracted from a parsed contract symbol.

    Mirrors Trade_J ``ParsedContract`` record fields (excluding enums).
    """

    underlying: str
    month: str = ""
    day: int = 0
    year: int = 2026
    strike: str | None = None  # raw string from regex group
    option_type: str = ""  # "CE" | "PE" (always canonical)
    is_option: bool = False


# ── Formatter ─────────────────────────────────────────────────────────────────


class SymbolFormatter:
    """Dhan / Tradehull canonical symbol formatter — Trade_J parity.

    All round-trip behaviour is anchored to the regex patterns from
    ``ContractSymbolNormalizer``, updated for Dhan/Tradehull display symbols.

    Examples::

        fmt = SymbolFormatter()

        # Options
        fmt.format_option("NIFTY", 26, "MAY", "30750", "CE")
        # → "NIFTY 30750 CE MAY 2026"
        fmt.normalize("NIFTY 26 MAY 30750 CE")
        # → "NIFTY 30750 CE MAY 2026"
    """

    # ── Canonical builders ──────────────────────────────────────────────────

    @staticmethod
    def canonical_option(
        underlying: str,
        expiry: date,
        strike: Decimal | int | float | str,
        option_type: str,  # "CALL" | "PUT" | "CE" | "PE"
    ) -> str:
        """Build a canonical option symbol from components.

        :param underlying:  e.g. ``"NIFTY"``, ``"BANKNIFTY"``
        :param expiry:      expiry ``date``
        :param strike:      numeric strike
        :param option_type: ``"CE"`` / ``"PE"`` / ``"CALL"`` / ``"PUT"``
        :returns:           e.g. ``"NIFTY 25000 CE JUL 2026"``
        """
        strike_str = _strike_str(strike)
        opt = "CE" if _option_type_code(option_type) == "CALL" else "PE"
        mmm = _canonical_month(expiry.strftime("%b"))
        yyyy = expiry.strftime("%Y")

        # Check if weekly (not the last Thursday of the month)
        is_monthly = expiry.weekday() == 3 and (expiry + date_delta(days=7)).month != expiry.month
        # Also handle Wednesday/Friday monthly/weekly logic
        if expiry.weekday() in (2, 4):
            is_monthly = (expiry + date_delta(days=7)).month != expiry.month

        if is_monthly:
            return f"{underlying.upper()} {strike_str} {opt} {mmm} {yyyy}"
        else:
            return f"{underlying.upper()} {expiry.day:02d} {mmm} {yyyy} {strike_str} {opt}"

    @staticmethod
    def canonical_future(
        underlying: str,
        expiry: date,
    ) -> str:
        """Build a canonical future symbol from components.

        :param underlying: e.g. ``"NIFTY"``
        :param expiry:     expiry ``date``
        :returns:          e.g. ``"NIFTY JUL 2026 FUT"``
        """
        mmm = _canonical_month(expiry.strftime("%b"))
        yyyy = expiry.strftime("%Y")

        is_monthly = (expiry + date_delta(days=7)).month != expiry.month
        if is_monthly:
            return f"{underlying.upper()} {mmm} {yyyy} FUT"
        else:
            return f"{underlying.upper()} {expiry.day:02d} {mmm} {yyyy} FUT"

    # ── Normalisation (parse + re-emit canonical) ───────────────────────────

    @staticmethod
    def normalize(raw: str) -> str:
        """Parse *any* supported alias and return the canonical form.

        For unrecognised symbols (e.g. ``"SBIN"``) returns ``raw.upper()``

        :param raw: spaced, compact, CE/PE, CALL/PUT, broker-trading-symbol
        :returns:  canonical form, uppercased
        """
        if not raw or not raw.strip():
            return ""
        cleaned = _clean(raw)
        parsed = SymbolFormatter.parse(cleaned)
        if parsed is None:
            return raw.strip().upper()
        if parsed.is_option:
            return SymbolFormatter._format_option(
                parsed.underlying,
                parsed.day,
                parsed.month,
                parsed.strike,
                parsed.option_type,
                parsed.year,
            )
        return SymbolFormatter._format_future(
            parsed.underlying,
            parsed.day,
            parsed.month,
            parsed.year,
        )

    @staticmethod
    def normalize_strict(raw: str) -> str:
        """Same as ``normalize`` but raises on unrecognised F&O symbols."""
        if not raw or not raw.strip():
            raise ValueError("Contract symbol must not be null or blank")
        cleaned = _clean(raw)
        if not SymbolFormatter._is_known_pattern(cleaned):
            raise ValueError(f"Unrecognised contract symbol: {raw!r}")
        return SymbolFormatter.normalize(raw)

    # ── Parse ───────────────────────────────────────────────────────────────

    @staticmethod
    def parse(raw: str) -> ParsedContract | None:
        """Parse a contract symbol into its components.

        :returns: ParsedContract or None if the symbol cannot be matched.
        """
        if not raw or not raw.strip():
            return None
        c = _clean(raw)

        # 1. Try spaced patterns first
        # New Spaced Option Monthly: e.g. "NIFTY 25000 CE JUL 2026"
        m = _NEW_SPACED_OPTION_MONTHLY.match(c)
        if m:
            g = m.groupdict()
            return ParsedContract(
                underlying=g["underlying"].strip(),
                month=_canonical_month(g["month"]),
                day=0,
                year=int(g["year"]),
                strike=g["strike"],
                option_type="CE" if _option_type_code(g["type"]) == "CALL" else "PE",
                is_option=True,
            )

        # New Spaced Option Weekly: e.g. "NIFTY 18 JUN 2026 23500 CE"
        m = _NEW_SPACED_OPTION_WEEKLY.match(c)
        if m:
            g = m.groupdict()
            year_val = int(g["year"])
            if year_val < 100:
                year_val += 2000
            return ParsedContract(
                underlying=g["underlying"].strip(),
                month=_canonical_month(g["month"]),
                day=int(g["day"]),
                year=year_val,
                strike=g["strike"],
                option_type="CE" if _option_type_code(g["type"]) == "CALL" else "PE",
                is_option=True,
            )

        # Legacy Spaced Option: e.g. "NIFTY 26 MAY 30750 CALL"
        m = _LEGACY_SPACED_OPTION.match(c)
        if m:
            g = m.groupdict()
            return ParsedContract(
                underlying=g["underlying"].strip(),
                month=_canonical_month(g["month"]),
                day=int(g["day"]),
                year=datetime.now().year,
                strike=g["strike"],
                option_type="CE" if _option_type_code(g["type"]) == "CALL" else "PE",
                is_option=True,
            )

        # New Spaced Future Monthly: e.g. "NIFTY JUL 2026 FUT"
        m = _NEW_SPACED_FUTURE_MONTHLY.match(c)
        if m:
            g = m.groupdict()
            return ParsedContract(
                underlying=g["underlying"].strip(),
                month=_canonical_month(g["month"]),
                day=0,
                year=int(g["year"]),
                is_option=False,
            )

        # Legacy Spaced Future: e.g. "NIFTY 30 JUN FUT"
        m = _LEGACY_SPACED_FUTURE.match(c)
        if m:
            g = m.groupdict()
            return ParsedContract(
                underlying=g["underlying"].strip(),
                month=_canonical_month(g["month"]),
                day=int(g["day"]),
                year=datetime.now().year,
                is_option=False,
            )

        # 2. Try compact patterns (with spaces, hyphens, underscores stripped)
        s = SymbolFormatter._stripped(c)

        # Format A: NIFTY25000CEJUL2026
        m_compact_opt_new = re.compile(
            r"^(?P<underlying>[A-Z&]+)(?P<strike>\d+(?:\.\d+)?)(?P<type>CE|PE|CALL|PUT|C|P)(?P<month>[A-Z]{3})(?P<year>\d{4})$",
            re.IGNORECASE,
        ).match(s)
        if m_compact_opt_new:
            g = m_compact_opt_new.groupdict()
            return ParsedContract(
                underlying=g["underlying"],
                month=_canonical_month(g["month"]),
                day=0,
                year=int(g["year"]),
                strike=g["strike"],
                option_type="CE" if _option_type_code(g["type"]) == "CALL" else "PE",
                is_option=True,
            )

        # Format B: NIFTY18JUN202623500CE
        m_compact_opt_weekly = re.compile(
            r"^(?P<underlying>[A-Z&]+)(?P<day>\d{2})(?P<month>[A-Z]{3})(?P<year>\d{4})(?P<strike>\d+(?:\.\d+)?)(?P<type>CE|PE|CALL|PUT|C|P)$",
            re.IGNORECASE,
        ).match(s)
        if m_compact_opt_weekly:
            g = m_compact_opt_weekly.groupdict()
            return ParsedContract(
                underlying=g["underlying"],
                month=_canonical_month(g["month"]),
                day=int(g["day"]),
                year=int(g["year"]),
                strike=g["strike"],
                option_type="CE" if _option_type_code(g["type"]) == "CALL" else "PE",
                is_option=True,
            )

        # Format C: NIFTY26MAY30750CE (legacy compact option)
        m_compact_opt_legacy = re.compile(
            r"^(?P<underlying>[A-Z&]+)(?P<day>\d{2})(?P<month>[A-Z]{3})(?P<strike>\d+(?:\.\d+)?)(?P<type>CE|PE|CALL|PUT|C|P)$",
            re.IGNORECASE,
        ).match(s)
        if m_compact_opt_legacy:
            g = m_compact_opt_legacy.groupdict()
            return ParsedContract(
                underlying=g["underlying"],
                month=_canonical_month(g["month"]),
                day=int(g["day"]),
                year=datetime.now().year,
                strike=g["strike"],
                option_type="CE" if _option_type_code(g["type"]) == "CALL" else "PE",
                is_option=True,
            )

        # Format D: NIFTYJUL2026FUT
        m_compact_fut_new = re.compile(
            r"^(?P<underlying>[A-Z&]+)(?P<month>[A-Z]{3})(?P<year>\d{4})FUT(?:URES)?$",
            re.IGNORECASE,
        ).match(s)
        if m_compact_fut_new:
            g = m_compact_fut_new.groupdict()
            return ParsedContract(
                underlying=g["underlying"],
                month=_canonical_month(g["month"]),
                day=0,
                year=int(g["year"]),
                is_option=False,
            )

        # Format E: NIFTY30JUNFUT (legacy compact future)
        m_compact_fut_legacy = re.compile(
            r"^(?P<underlying>[A-Z&]+)(?P<day>\d{2})(?P<month>[A-Z]{3})FUT(?:URES)?$",
            re.IGNORECASE,
        ).match(s)
        if m_compact_fut_legacy:
            g = m_compact_fut_legacy.groupdict()
            return ParsedContract(
                underlying=g["underlying"],
                month=_canonical_month(g["month"]),
                day=int(g["day"]),
                year=datetime.now().year,
                is_option=False,
            )

        return None

    # ── Compact ↔ canonical round-trip ──────────────────────────────────────

    @staticmethod
    def to_compact(canonical: str) -> str:
        """Canonical display → compact Dhan master form.

        :param canonical: ``"NIFTY 25000 CE JUL 2026"``
        :returns:        ``"NIFTY26JUL25000CE"`` (with resolved expiry day)
        """
        raw = canonical.strip().upper()
        if not raw:
            return raw

        parsed = SymbolFormatter.parse(raw)
        if parsed is None:
            return raw.replace(" ", "").replace("-", "").replace("_", "")

        day_val = parsed.day
        if day_val == 0:
            # Determine last Thursday for compact roundtrip
            month_num = int(_MONTH_TO_NUM[parsed.month][0])
            day_val = last_thursday_of_month(parsed.year, month_num)

        parts = [parsed.underlying.upper(), f"{day_val:02d}", parsed.month]
        if parsed.is_option:
            parts.append(parsed.strike)
            parts.append(parsed.option_type)
        else:
            parts.append("FUT")
        return "".join(parts)

    @staticmethod
    def from_compact(compact: str) -> str | None:
        """Compact Dhan master form → canonical display symbol.

        :returns: canonical string, or None if unparseable
        """
        s = compact.strip().upper()
        if not s:
            return None

        # Check options & futures patterns (compact)
        stripped = SymbolFormatter._stripped(s)

        # Try new compact option
        m = re.compile(
            r"^(?P<underlying>[A-Z&]+)(?P<day>\d{2})(?P<month>[A-Z]{3})(?P<year>\d{4})(?P<strike>\d+(?:\.\d+)?)(?P<type>CE|PE)$",
            re.IGNORECASE,
        ).match(stripped)
        if m:
            g = m.groupdict()
            return SymbolFormatter._format_option(
                g["underlying"],
                int(g["day"]),
                g["month"],
                g["strike"],
                g["type"],
                int(g["year"]),
            )

        # Try legacy compact option
        m = re.compile(
            r"^(?P<underlying>[A-Z&]+)(?P<day>\d{2})(?P<month>[A-Z]{3})(?P<strike>\d+(?:\.\d+)?)(?P<type>CE|PE|CALL|PUT|C|P)$",
            re.IGNORECASE,
        ).match(stripped)
        if m:
            g = m.groupdict()
            return SymbolFormatter._format_option(
                g["underlying"],
                int(g["day"]),
                g["month"],
                g["strike"],
                g["type"],
                datetime.now().year,
            )

        # Try new compact future
        m = re.compile(
            r"^(?P<underlying>[A-Z&]+)(?P<month>[A-Z]{3})(?P<year>\d{4})FUT$",
            re.IGNORECASE,
        ).match(stripped)
        if m:
            g = m.groupdict()
            return SymbolFormatter._format_future(
                g["underlying"],
                0,
                g["month"],
                int(g["year"]),
            )

        # Try legacy compact future
        m = re.compile(
            r"^(?P<underlying>[A-Z&]+)(?P<day>\d{2})(?P<month>[A-Z]{3})FUT$",
            re.IGNORECASE,
        ).match(stripped)
        if m:
            g = m.groupdict()
            return SymbolFormatter._format_future(
                g["underlying"],
                int(g["day"]),
                g["month"],
                datetime.now().year,
            )

        return None

    # ── Underlying extraction ───────────────────────────────────────────────

    @staticmethod
    def extract_future_underlying(trading_symbol: str) -> str:
        """Strip expiry/day tokens from a Dhan tradingSymbol to get underlying."""
        parsed = SymbolFormatter.parse(trading_symbol)
        if parsed is not None and not parsed.is_option:
            return parsed.underlying
        s = SymbolFormatter._stripped(trading_symbol)
        return re.sub(r"\d{2}[A-Z]{3}\d{4}FUT$", "", s)

    # ── Private helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _format_option(underlying, day, month, strike, option_type, year=2026) -> str:
        und = underlying.upper()
        m = _canonical_month(month)
        opt = "CE" if option_type in ("CALL", "CE", "C") else "PE"
        if day and int(day) > 0:
            return f"{und} {int(day):02d} {m} {year} {strike} {opt}"
        return f"{und} {strike} {opt} {m} {year}"

    @staticmethod
    def _format_future(underlying, day, month, year=2026) -> str:
        und = underlying.upper()
        m = _canonical_month(month)
        if day and int(day) > 0:
            return f"{und} {int(day):02d} {m} {year} FUT"
        return f"{und} {m} {year} FUT"

    @staticmethod
    def _is_known_pattern(raw: str) -> bool:
        SymbolFormatter._stripped(raw)
        return (
            _NEW_SPACED_OPTION_MONTHLY.match(raw) is not None
            or _NEW_SPACED_OPTION_WEEKLY.match(raw) is not None
            or _LEGACY_SPACED_OPTION.match(raw) is not None
            or _NEW_SPACED_FUTURE_MONTHLY.match(raw) is not None
            or _LEGACY_SPACED_FUTURE.match(raw) is not None
        )

    @staticmethod
    def _stripped(value: str) -> str:
        return value.replace(" ", "").replace("-", "").replace("_", "").upper()


# ── Module-level convenience wrappers ────────────────────────────────────────

formatter = SymbolFormatter()


def canonical_option(
    underlying: str,
    expiry: date,
    strike: Decimal | int | float | str,
    option_type: str,
) -> str:
    """Build a canonical option symbol from components."""
    return SymbolFormatter.canonical_option(underlying, expiry, strike, option_type)


def canonical_future(underlying: str, expiry: date) -> str:
    """Build a canonical future symbol from components."""
    return SymbolFormatter.canonical_future(underlying, expiry)


def normalize(raw: str) -> str:
    """Normalise any supported contract symbol alias to canonical form."""
    return SymbolFormatter.normalize(raw)


def normalize_strict(raw: str) -> str:
    """Normalise, raising ``ValueError`` for unrecognised F&O symbols."""
    return SymbolFormatter.normalize_strict(raw)


def to_compact(symbol: str) -> str:
    """Canonical display → compact Dhan master string."""
    return SymbolFormatter.to_compact(symbol)


def from_compact(compact: str) -> str | None:
    """Compact Dhan master string → canonical display."""
    return SymbolFormatter.from_compact(compact)


def parse(symbol: str) -> ParsedContract | None:
    """Parse a contract symbol into a ``ParsedContract``."""
    return SymbolFormatter.parse(symbol)


def extract_future_underlying(trading_symbol: str) -> str:
    """Strip expiry tokens from a Dhan tradingSymbol → underlying."""
    return SymbolFormatter.extract_future_underlying(trading_symbol)


# ── Private helpers ───────────────────────────────────────────────────────────

_OPTION_TYPE_MAP: dict[str, str] = {
    "CE": "CALL",
    "PE": "PUT",
    "C": "CALL",
    "P": "PUT",
    "CALL": "CALL",
    "PUT": "PUT",
}

_NEW_SPACED_OPTION_MONTHLY = re.compile(
    r"^(?P<underlying>[A-Z&\-\s]+)\s+"
    r"(?P<strike>\d+(?:\.\d+)?)\s+"
    r"(?P<type>CE|PE|CALL|PUT|C|P)\s+"
    r"(?P<month>[A-Z]{3})\s+"
    r"(?P<year>\d{4})$",
    re.IGNORECASE,
)

_NEW_SPACED_OPTION_WEEKLY = re.compile(
    r"^(?P<underlying>[A-Z&\-\s]+)\s+"
    r"(?P<day>\d{1,2})\s+"
    r"(?P<month>[A-Z]{3})\s+"
    r"(?P<year>\d{2,4})\s+"
    r"(?P<strike>\d+(?:\.\d+)?)\s+"
    r"(?P<type>CE|PE|CALL|PUT|C|P)$",
    re.IGNORECASE,
)

_LEGACY_SPACED_OPTION = re.compile(
    r"^(?P<underlying>[A-Z&\-\s]+)\s+"
    r"(?P<day>\d{1,2})\s+"
    r"(?P<month>[A-Z]{3})\s+"
    r"(?P<strike>\d+(?:\.\d+)?)\s+"
    r"(?P<type>CE|PE|CALL|PUT|C|P)$",
    re.IGNORECASE,
)

_NEW_SPACED_FUTURE_MONTHLY = re.compile(
    r"^(?P<underlying>[A-Z&\-\s]+)\s+"
    r"(?P<month>[A-Z]{3})\s+"
    r"(?P<year>\d{4})\s+"
    r"FUT(?:URES)?$",
    re.IGNORECASE,
)

_LEGACY_SPACED_FUTURE = re.compile(
    r"^(?P<underlying>[A-Z&\-\s]+)\s+"
    r"(?P<day>\d{1,2})\s+"
    r"(?P<month>[A-Z]{3})\s+"
    r"FUT(?:URES)?$",
    re.IGNORECASE,
)


def _clean(raw: str) -> str:
    """Normalise raw to upper, replace hyphens and underscores with spaces."""
    return raw.strip().upper().replace("-", " ").replace("_", " ")


def _stripped(raw: str) -> str:
    return raw.replace(" ", "").replace("-", "").replace("_", "").upper()


def _option_type_code(raw: str) -> str:
    key = raw.strip().upper()
    return _OPTION_TYPE_MAP.get(key, key)


def _canonical_option_type(raw: str) -> str:
    return _option_type_code(raw)


def _compact_option_type(canonical_type: str) -> str:
    return "CE" if canonical_type == "CALL" else "PE"


def _canonical_month(month: str) -> str:
    m = month.strip().upper()
    return _MONTH_TO_NUM.get(m, (m, m))[1]


def _day_month(d: date) -> tuple[int, str]:
    mon = _MONTH_TO_NUM[d.strftime("%b").upper()][1]
    return d.day, mon


def date_delta(days: int) -> timedelta:
    return timedelta(days=days)


def last_thursday_of_month(year: int, month: int) -> int:
    import calendar

    cal = calendar.monthcalendar(year, month)
    for week in reversed(cal):
        if week[calendar.THURSDAY] != 0:
            return week[calendar.THURSDAY]
    return 28


def _strike_str(strike: Decimal | int | float | str) -> str:
    if isinstance(strike, int | float | Decimal):
        # If the strike is very large (e.g. standard strikePricePaisa convention: rupees * 100)
        # divide by 100. Otherwise if it's already a small number (e.g. strike in rupees) keep it.
        val = float(strike)
        if val > 100000:  # clearly paisa
            rupees = val / 100
        else:
            rupees = val
        if rupees == int(rupees):
            return str(int(rupees))
        return f"{rupees:.2f}"
    return strike.strip()


def _parsed_option(m, *, from_spaced: bool) -> ParsedContract:
    groups = m.groupdict()
    day = int(groups.get("day", 0))
    month = _canonical_month(groups["month"])
    underlying = groups["underlying"].strip().replace("  ", " ")
    strike = groups.get("strike")
    opt_type = _option_type_code(groups.get("type", ""))
    year = int(groups.get("year", datetime.now().year))
    return ParsedContract(
        underlying=underlying,
        month=month,
        day=day,
        year=year,
        strike=strike,
        option_type="CE" if opt_type == "CALL" else "PE",
        is_option=True,
    )


def _parsed_future(m, *, from_spaced: bool) -> ParsedContract:
    groups = m.groupdict()
    day = int(groups.get("day", 0))
    month = _canonical_month(groups["month"])
    underlying = groups["underlying"].strip().replace("  ", " ")
    year = int(groups.get("year", datetime.now().year))
    return ParsedContract(
        underlying=underlying,
        month=month,
        day=day,
        year=year,
        is_option=False,
    )
