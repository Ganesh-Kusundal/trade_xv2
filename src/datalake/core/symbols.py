"""Symbol normalization — consistent symbol handling across the pipeline.

Canonical trading-key normalization lives in :mod:`domain.symbols`.
This module re-exports that for callers and adds a storage-path helper that
strips exchange suffixes (e.g. ``RELIANCE-EQ`` → ``RELIANCE``) for filesystem
partition paths only.
"""

from __future__ import annotations

import re
from pathlib import Path

from domain.symbols import make_instrument_id
from domain.symbols import normalize_exchange
from domain.symbols import normalize_symbol as _domain_normalize_symbol

# Symbols that end with exchange suffixes (e.g., "RELIANCE-EQ", "TCS-BE")
SUFFIX_PATTERN = re.compile(r"[-_](EQ|BE|BL|BZ|MC|NC|NZ|SM|SO|TT)\s*$", re.IGNORECASE)

# Path traversal patterns to reject
_PATH_TRAVERSAL = re.compile(r"\.\.[\\/]|[\\/]\.\.|\x00")
_PATH_CHARS = re.compile(r"[^A-Za-z0-9_\-]")


def normalize_symbol(symbol: str) -> str:
    """Canonical symbol normalization — delegates to :func:`domain.symbols.normalize_symbol`.

    Does **not** strip exchange suffixes. Use
    :func:`normalize_symbol_for_storage` at filesystem path boundaries.
    """
    return _domain_normalize_symbol(symbol)


def normalize_symbol_for_storage(symbol: str) -> str:
    """Normalize a symbol for datalake filesystem / hive partition paths.

    - Strip whitespace, uppercase (via domain)
    - Remove common exchange suffixes (EQ, BE, etc.)
    - Reject symbols with path traversal characters
    """
    if not symbol:
        return ""

    s = _domain_normalize_symbol(symbol)
    s = SUFFIX_PATTERN.sub("", s)
    if "/" in s or "\\" in s or ".." in s or "\x00" in s:
        raise ValueError(f"Invalid symbol (path traversal detected): {symbol!r}")
    return s


def sanitize_path_param(value: str, param_name: str = "param") -> str:
    """Sanitize a string used in filesystem path construction.

    Rejects path traversal sequences, null bytes, and path separators.
    Raises ValueError if the value contains any dangerous characters.

    Use this for timeframe, expiry_kind, expiry_code, and any other
    parameter that flows into partition paths.
    """
    if not value:
        raise ValueError(f"{param_name} cannot be empty")
    if _PATH_TRAVERSAL.search(value) or "/" in value or "\\" in value or "\x00" in value:
        raise ValueError(f"{param_name} contains path traversal characters: {value!r}")
    return value


def symbol_to_path(symbol: str) -> str:
    """Convert a symbol to a hive partition path component."""
    return f"symbol={normalize_symbol_for_storage(symbol)}"


def path_to_symbol(path: str | Path) -> str:
    """Extract symbol from a hive partition path.

    Walks up the path to find the ``symbol=`` component.
    """
    p = Path(path)
    for part in p.parts:
        if part.startswith("symbol="):
            return normalize_symbol_for_storage(part.replace("symbol=", ""))
    return normalize_symbol_for_storage(p.name)


def normalize_universe_name(name: str) -> str:
    """Normalize universe name, handling NIFTY50 vs nifty_50 variations.

    Delegates to :func:`domain.normalize.normalize_universe_name`.
    """
    from domain.normalize import normalize_universe_name as _norm_universe

    return _norm_universe(name)


def are_same_symbol(a: str, b: str) -> bool:
    """Check if two symbol strings refer to the same instrument (storage form)."""
    return normalize_symbol_for_storage(a) == normalize_symbol_for_storage(b)


def instrument_id_from_symbol(symbol: str, exchange: str = "NSE") -> str:
    """Convert (symbol, exchange) to canonical InstrumentId string.

    Delegates key construction to :func:`domain.symbols.make_instrument_id`
    (single source of truth) and applies the storage-specific suffix strip on
    top. Example: instrument_id_from_symbol("RELIANCE", "NSE") → "NSE:RELIANCE"
    """
    return make_instrument_id(normalize_symbol_for_storage(symbol), exchange)


def instrument_id_from_option(
    underlying: str,
    expiry_date: str,
    strike: float | int,
    option_type: str,
    exchange: str = "NFO",
) -> str:
    """Build canonical InstrumentId string for an option.

    Example: instrument_id_from_option("NIFTY", "2026-07-30", 25000, "CE")
             → "NFO:NIFTY:20260730:25000:CE"
    """
    # Normalize option type
    ot = option_type.upper().strip()
    if ot in ("CE", "CALL"):
        ot = "CE"
    elif ot in ("PE", "PUT"):
        ot = "PE"

    # Parse expiry to YYYYMMDD
    exp = expiry_date.replace("-", "")
    if len(exp) == 10:  # YYYY-MM-DD
        exp = exp.replace("-", "")

    return (
        f"{normalize_exchange(exchange)}:"
        f"{normalize_symbol_for_storage(underlying)}:{exp}:{int(strike)}:{ot}"
    )


def instrument_id_from_future(
    underlying: str,
    expiry_date: str,
    exchange: str = "NFO",
) -> str:
    """Build canonical InstrumentId string for a future.

    Example: instrument_id_from_future("NIFTY", "2026-07-30")
             → "NFO:NIFTY:20260730:FUT"
    """
    exp = expiry_date.replace("-", "")
    if len(exp) == 10:
        exp = exp.replace("-", "")
    return (
        f"{normalize_exchange(exchange)}:"
        f"{normalize_symbol_for_storage(underlying)}:{exp}:FUT"
    )
