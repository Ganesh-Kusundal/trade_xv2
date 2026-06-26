"""Symbol normalization — consistent symbol handling across the pipeline.

Symbols are stored uppercased and stripped of whitespace. This prevents
case-sensitivity bugs (RELIANCE vs Reliance vs reliance) and trailing
whitespace from broker APIs.

Path traversal protection:
    ``sanitize_path_param`` strips ``../``, ``..\\``, ``/``, and null
    bytes from any string used in filesystem paths (timeframe, expiry,
    etc.). ``normalize_symbol`` rejects symbols containing path
    separators.
"""

from __future__ import annotations

import re
from pathlib import Path

# Symbols that end with exchange suffixes (e.g., "RELIANCE-EQ", "TCS-BE")
SUFFIX_PATTERN = re.compile(r"[-_](EQ|BE|BL|BZ|MC|NC|NZ|SM|SO|TT)\s*$", re.IGNORECASE)

# Path traversal patterns to reject
_PATH_TRAVERSAL = re.compile(r"\.\.[\\/]|[\\/]\.\.|\x00")
_PATH_CHARS = re.compile(r"[^A-Za-z0-9_\-]")


def normalize_symbol(symbol: str) -> str:
    """Normalize a symbol name.

    - Strip whitespace
    - Uppercase
    - Remove common exchange suffixes (EQ, BE, etc.)
    - Remove NSE-specific suffixes like "-EQ"
    - Reject symbols with path traversal characters
    """
    if not symbol:
        return ""

    s = symbol.strip().upper()
    s = SUFFIX_PATTERN.sub("", s)
    # Reject path separators in symbol names
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
    return f"symbol={normalize_symbol(symbol)}"


def path_to_symbol(path: str | Path) -> str:
    """Extract symbol from a hive partition path.

    Walks up the path to find the ``symbol=`` component.
    """
    p = Path(path)
    for part in p.parts:
        if part.startswith("symbol="):
            return normalize_symbol(part.replace("symbol=", ""))
    return normalize_symbol(p.name)


def normalize_universe_name(name: str) -> str:
    """Normalize universe name, handling NIFTY50 vs nifty_50 variations."""
    return name.upper().replace("_", "").replace("-", "").replace(" ", "")


def are_same_symbol(a: str, b: str) -> bool:
    """Check if two symbol strings refer to the same instrument."""
    return normalize_symbol(a) == normalize_symbol(b)


def instrument_id_from_symbol(symbol: str, exchange: str = "NSE") -> str:
    """Convert (symbol, exchange) to canonical InstrumentId string.

    Example: instrument_id_from_symbol("RELIANCE", "NSE") → "NSE:RELIANCE"
    """
    return f"{exchange.upper()}:{normalize_symbol(symbol)}"


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
    from datetime import datetime
    exp = expiry_date.replace("-", "")
    if len(exp) == 10:  # YYYY-MM-DD
        exp = exp.replace("-", "")

    return f"{exchange.upper()}:{normalize_symbol(underlying)}:{exp}:{int(strike)}:{ot}"


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
    return f"{exchange.upper()}:{normalize_symbol(underlying)}:{exp}:FUT"
