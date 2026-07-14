"""Single parameterized string normalizer for the codebase.

Replaces ad-hoc ``value.strip().upper()`` / ``value.upper().replace(...)``
variants scattered across brokers, domain, and datalake. One function, one
behavior per call site. See audit SMELL-10 / REF-10.
"""

from __future__ import annotations


def normalize_text(
    value: str,
    *,
    case: str | None = "upper",
    strip: bool = True,
    drop: str | None = None,
) -> str:
    """Normalize a free-form string.

    Parameters
    ----------
    value:
        Raw string.
    case:
        ``"upper"``, ``"lower"``, or ``None`` for no case change.
    strip:
        Trim leading/trailing whitespace when ``True``.
    drop:
        Optional characters to delete everywhere (e.g. ``" "`` to turn
        ``"MARKET OPEN"`` into ``"MARKET_OPEN"``).

    Returns
    -------
    str
        Normalized string.
    """
    if value is None:  # ponytail: callers sometimes pass None through
        return ""
    result = value if value is not None else ""
    if strip:
        result = result.strip()
    if case == "upper":
        result = result.upper()
    elif case == "lower":
        result = result.lower()
    if drop:
        result = result.replace(drop, "")
    return result


def normalize_universe_name(name: str) -> str:
    """Normalize a universe name (NIFTY50 vs nifty_50 vs nifty-50 → NIFTY50).

    Delegated from ``datalake.core.symbols.normalize_universe_name`` so the
    transformation lives in one place.
    """
    return normalize_text(name, case="upper", strip=True, drop="_").replace("-", "").replace(" ", "")
