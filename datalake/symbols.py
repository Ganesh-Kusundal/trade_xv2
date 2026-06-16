"""Symbol normalization — consistent symbol handling across the pipeline.

Symbols are stored uppercased and stripped of whitespace. This prevents
case-sensitivity bugs (RELIANCE vs Reliance vs reliance) and trailing
whitespace from broker APIs.
"""

from __future__ import annotations

import re
from pathlib import Path

# Symbols that end with exchange suffixes (e.g., "RELIANCE-EQ", "TCS-BE")
SUFFIX_PATTERN = re.compile(r"[-_](EQ|BE|BL|BZ|MC|NC|NZ|SM|SO|TT)\s*$", re.IGNORECASE)


def normalize_symbol(symbol: str) -> str:
    """Normalize a symbol name.

    - Strip whitespace
    - Uppercase
    - Remove common exchange suffixes (EQ, BE, etc.)
    - Remove NSE-specific suffixes like "-EQ"
    """
    if not symbol:
        return ""

    s = symbol.strip().upper()
    s = SUFFIX_PATTERN.sub("", s)
    return s


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


def are_same_symbol(a: str, b: str) -> bool:
    """Check if two symbol strings refer to the same instrument."""
    return normalize_symbol(a) == normalize_symbol(b)
