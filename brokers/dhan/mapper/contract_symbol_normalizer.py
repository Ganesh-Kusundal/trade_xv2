"""Contract symbol normalizer — Trade_J port of ``ContractSymbolNormalizer``.

Single source of truth for F&O and equity contract symbol formatting.

Canonical option: ``BANKNIFTY 30 JUN 30000 CALL``
Canonical future: ``NIFTY 30 JUN FUT``

Supported inputs
----------------

Equity / index
    ``SBIN``                     → ``SBIN``
    ``Nifty 50``                 → ``NIFTY 50`` (uppercased, trimmed)

Option (spaced)
    ``NIFTY 30 JUN 25000 CE``    → ``NIFTY 30 JUN 25000 CALL``
    ``BANKNIFTY 25 JUN 56000 PE``→ ``BANKNIFTY 25 JUN 56000 PUT``

Option (compact, no spaces)
    ``NIFTY30JUN25000CE``        → ``NIFTY 30 JUN 25000 CALL``
    ``BANKNIFTY25JUN56000PE``    → ``BANKNIFTY 25 JUN 56000 PUT``

Future (spaced)
    ``NIFTY 30 JUN FUT``         → ``NIFTY 30 JUN FUT``
    ``RELIANCE 25 JUN FUTURES``  → ``RELIANCE 25 JUN FUT``

Future (compact)
    ``NIFTY30JUNFUT``            → ``NIFTY 30 JUN FUT``
    ``RELIANCE25JUNFUT``         → ``RELIANCE 25 JUN FUT``

Aliases ``CALL`` ↔ ``CE`` and ``PUT`` ↔ ``PE`` are interchangeable, as are
``FUT`` and ``FUTURES``.

The normalizer never falls back silently.  Use :meth:`normalize` for lenient
matching (returns the uppercased input for unknown patterns) and
:meth:`normalize_strict` to raise :class:`ValueError` instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

# Pattern for ``NIFTY 30 JUN 25000 CE`` (spaced option).
_SPACED_OPTION_RE = re.compile(
    r"^(?P<underlying>[A-Z&\-\s]+?)\s+"
    r"(?P<day>\d{1,2})\s+"
    r"(?P<month>[A-Z]{3})\s+"
    r"(?P<strike>\d+(?:\.\d+)?)\s+"
    r"(?P<type>CE|PE|CALL|PUT|C|P)$",
    re.IGNORECASE,
)

# Pattern for ``NIFTY30JUN25000CE`` (compact option, no separators).
_COMPACT_OPTION_RE = re.compile(
    r"^(?P<underlying>[A-Z&]+)"
    r"(?P<day>\d{2})"
    r"(?P<month>[A-Z]{3})"
    r"(?P<strike>\d+(?:\.\d+)?)"
    r"(?P<type>CE|PE|CALL|PUT|C|P)$",
    re.IGNORECASE,
)

# Pattern for ``NIFTY 30 JUN FUT`` (spaced future).
_SPACED_FUTURE_RE = re.compile(
    r"^(?P<underlying>[A-Z&\-\s]+?)\s+"
    r"(?P<day>\d{1,2})\s+"
    r"(?P<month>[A-Z]{3})\s+"
    r"FUT(?:URES)?$",
    re.IGNORECASE,
)

# Pattern for ``NIFTY30JUNFUT`` (compact future).
_COMPACT_FUTURE_RE = re.compile(
    r"^(?P<underlying>[A-Z&]+)"
    r"(?P<day>\d{2})"
    r"(?P<month>[A-Z]{3})"
    r"FUT(?:URES)?$",
    re.IGNORECASE,
)

# Pattern for ``NIFTY 25000 CE`` — bare option with no date.
# Underlying has 2+ letters so we don't match equity tickers like ``M&M``.
_BARE_OPTION_RE = re.compile(
    r"^(?P<underlying>[A-Z&][A-Z&\-\s]+?)\s+"
    r"(?P<strike>\d+(?:\.\d+)?)\s+"
    r"(?P<type>CE|PE|CALL|PUT|C|P)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedContract:
    """Structured representation of a parsed F&O contract symbol."""

    underlying: str
    month: str  # 3-letter month abbreviation, uppercased
    day: int
    strike: str | None  # string form, e.g. "25000" or "25000.5"
    option_type: str  # "CE" | "PE" | "CALL" | "PUT" — canonicalised to CE/PE
    option: bool  # True for options, False for futures

    @property
    def is_future(self) -> bool:
        return not self.option

    @property
    def is_option(self) -> bool:
        return self.option


def _strip_separators(value: str) -> str:
    """Remove all spaces, hyphens, and underscores; uppercase."""
    return re.sub(r"[\s\-_]+", "", value).upper()


def _canonical_option_type(raw: str) -> str:
    """Map ``CE`` / ``CALL`` / ``C`` (any case) to ``CE`` or ``PE``."""
    upper = raw.strip().upper()
    if upper in ("CE", "CALL", "C"):
        return "CE"
    if upper in ("PE", "PUT", "P"):
        return "PE"
    return upper  # unknown — preserve for diagnostics


def _format_option(underlying: str, day: int, month: str, strike: str, otype: str) -> str:
    return f"{underlying} {day:02d} {month} {strike} {otype}"


def _format_future(underlying: str, day: int, month: str) -> str:
    return f"{underlying} {day:02d} {month} FUT"


def _is_known_pattern(symbol: str) -> bool:
    """Check whether a symbol matches any of the known contract patterns."""
    if not symbol:
        return False
    cleaned = symbol.strip().upper()
    if _SPACED_OPTION_RE.match(cleaned):
        return True
    if _COMPACT_OPTION_RE.match(_strip_separators(cleaned)):
        return True
    if _BARE_OPTION_RE.match(cleaned):
        return True
    if _SPACED_FUTURE_RE.match(cleaned):
        return True
    return bool(_COMPACT_FUTURE_RE.match(_strip_separators(cleaned)))


def parse(raw: str) -> ParsedContract | None:
    """Parse a contract symbol into a :class:`ParsedContract`.

    Returns ``None`` for plain equity / index symbols.
    """
    if not raw or not raw.strip():
        return None
    cleaned = raw.strip().upper()
    stripped = _strip_separators(cleaned)

    for regex, compact in (
        (_SPACED_OPTION_RE, False),
        (_COMPACT_OPTION_RE, True),
        (_BARE_OPTION_RE, False),
        (_SPACED_FUTURE_RE, False),
        (_COMPACT_FUTURE_RE, True),
    ):
        candidate = stripped if compact else cleaned
        m = regex.match(candidate)
        if m is None:
            continue
        groups = m.groupdict()
        underlying = groups["underlying"].strip()
        day = int(groups.get("day", 0)) if groups.get("day") else 0
        month = groups.get("month", "").upper()[:3] if groups.get("month") else ""
        if "type" in groups:  # option
            otype = _canonical_option_type(groups["type"])
            return ParsedContract(
                underlying=underlying,
                month=month,
                day=day,
                strike=groups["strike"],
                option_type=otype,
                option=True,
            )
        # future
        return ParsedContract(
            underlying=underlying,
            month=month,
            day=day,
            strike=None,
            option_type="",
            option=False,
        )
    return None


def normalize(raw: str) -> str:
    """Lenient normalisation.

    For recognised F&O contracts, returns the canonical spaced form
    (e.g. ``NIFTY 30 JUN 25000 CALL``).  For unknown input, returns the
    uppercased, trimmed string unchanged.
    """
    if not raw:
        return ""
    parsed = parse(raw)
    if parsed is None:
        return raw.strip().upper()
    if parsed.option:
        return _format_option(
            parsed.underlying,
            parsed.day,
            parsed.month,
            parsed.strike,
            parsed.option_type,
        )
    return _format_future(parsed.underlying, parsed.day, parsed.month)


def normalize_strict(raw: str) -> str:
    """Strict normalisation — raises :class:`ValueError` on unknown input.

    Mirrors Trade_J's :meth:`ContractSymbolNormalizer.normalizeStrict`.  Use
    this at the resolver boundary when a contract symbol is required.
    """
    if not raw or not raw.strip():
        raise ValueError("Contract symbol must not be null or blank")
    if not _is_known_pattern(raw):
        raise ValueError(f"Unrecognized contract symbol: {raw!r}")
    return normalize(raw)


def extract_future_underlying(trading_symbol: str) -> str:
    """Pull the underlying out of a futures contract symbol.

    Examples
    --------
    >>> extract_future_underlying("NIFTY30JUNFUT")
    'NIFTY'
    >>> extract_future_underlying("RELIANCE 25 JUN FUT")
    'RELIANCE'
    """
    if not trading_symbol:
        return ""
    parsed = parse(trading_symbol)
    if parsed is not None and not parsed.option:
        return parsed.underlying
    # Fallback: strip dates and FUT suffix from stripped form.
    stripped = _strip_separators(trading_symbol)
    return re.sub(r"\d{2}[A-Z]{3}FUT(?:URES)?$", "", stripped)


def build_canonical(
    underlying: str,
    expiry: date,
    strike_paisa: int | None,
    option_type: str | None,
    is_option: bool,
) -> str:
    """Build the canonical contract symbol for an instrument definition.

    Mirrors Trade_J's :meth:`ContractSymbolNormalizer.getCanonicalSymbol`.

    Parameters
    ----------
    underlying:
        Underlying root symbol, e.g. ``"NIFTY"``.
    expiry:
        Contract expiry date.
    strike_paisa:
        Strike price in paisa (i.e. 100 paisa = 1 rupee).  ``None`` for
        futures.
    option_type:
        ``"CE"`` / ``"CALL"`` / ``"PE"`` / ``"PUT"`` for options, ``None`` for
        futures.
    is_option:
        ``True`` for options, ``False`` for futures.
    """
    if not underlying or not expiry:
        return ""
    underlying_u = underlying.strip().upper()
    otype_canonical = ""
    if is_option:
        if strike_paisa is None or not option_type:
            return ""
        otype_canonical = _canonical_option_type(option_type)
    day = expiry.day
    month = expiry.strftime("%b").upper()
    if is_option:
        whole = strike_paisa // 100
        strike = str(whole) if strike_paisa % 100 == 0 else f"{strike_paisa / 100:.2f}"
        return _format_option(underlying_u, day, month, strike, otype_canonical)
    return _format_future(underlying_u, day, month)


def is_known_contract(symbol: str) -> bool:
    """Return ``True`` if the symbol matches a recognised F&O contract pattern."""
    return _is_known_pattern(symbol)
