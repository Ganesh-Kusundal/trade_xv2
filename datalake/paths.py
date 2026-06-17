"""Canonical paths and partition scheme for the datalake (REF-10).

Single source of truth for the hive-partition layout. Every writer
and reader in :mod:`datalake` MUST import from here instead of
hard-coding the partition string.

Why this matters
----------------
The previous design inlined the path string
``"{root}/equities/candles/timeframe=1m/symbol={symbol}/data.parquet"``
in 4+ places (:mod:`datalake.normalize`, :mod:`datalake.updater`,
tests, sync scripts). A change to the partition scheme required
editing every call site — the textbook shotgun-surgery pattern.

Partition scheme (current)
--------------------------
::

    {root}/equities/candles/timeframe={timeframe}/symbol={symbol}/data.parquet
    {root}/options/chains/expiry={expiry}/underlying={underlying}/data.parquet

The scheme is intentionally narrow: hive-partitioned on the
fields most often filtered in queries (symbol, timeframe, expiry,
underlying). Adding new fields is a breaking change for readers
that already have data on disk — version the partition root
when you do.

Migration tools
---------------
:meth:`partition_path_to_dict` parses a path back into its
partition parts so tests and validation tools can check the
scheme without re-deriving the constants.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


# Default root directory for the datalake on disk.
DEFAULT_DATA_ROOT: str = "market_data"

# Supported timeframes. Adding a new one requires also adding it to
# the historical loader's ``_TIMEFRAME_MAP`` in
# :mod:`brokers.dhan.historical` and the corresponding CLI
# ``options sync`` and ``backtest`` commands.
SUPPORTED_TIMEFRAMES: frozenset[str] = frozenset({"1m", "5m", "15m", "1h", "1d"})

# Default timeframe for ``DataLake.history`` and CLI smoke tests.
DEFAULT_TIMEFRAME: str = "1m"

# Partition scheme constants. These are the keys used in the path.
PARTITION_TIMEFRAME: str = "timeframe"
PARTITION_SYMBOL: str = "symbol"
PARTITION_EXPIRY: str = "expiry"
PARTITION_UNDERLYING: str = "underlying"


def symbol_partition_path(
    root: str,
    symbol: str,
    timeframe: str = DEFAULT_TIMEFRAME,
) -> Path:
    """Return the path to a single symbol's candle Parquet file.

    Parameters
    ----------
    root:
        Datalake root directory. Defaults to :data:`DEFAULT_DATA_ROOT`.
    symbol:
        Canonical symbol name (e.g. ``"RELIANCE"``). MUST already be
        normalized by :func:`datalake.symbols.normalize_symbol`.
    timeframe:
        One of :data:`SUPPORTED_TIMEFRAMES`. Defaults to
        :data:`DEFAULT_TIMEFRAME`.
    """
    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise ValueError(
            f"unsupported timeframe {timeframe!r}; "
            f"supported: {sorted(SUPPORTED_TIMEFRAMES)}"
        )
    return Path(root) / "equities" / "candles" / f"timeframe={timeframe}" / f"symbol={symbol}" / "data.parquet"


def symbol_partition_glob(
    root: str,
    timeframe: str = DEFAULT_TIMEFRAME,
) -> str:
    """Return a SQL/glob pattern matching every symbol's data for a timeframe."""
    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise ValueError(
            f"unsupported timeframe {timeframe!r}; "
            f"supported: {sorted(SUPPORTED_TIMEFRAMES)}"
        )
    return f"{root}/equities/candles/timeframe={timeframe}/symbol=*/data.parquet"


def option_partition_path(
    root: str,
    expiry: str,
    underlying: str,
) -> Path:
    """Return the path to an option-chain Parquet file."""
    return Path(root) / "options" / "chains" / f"expiry={expiry}" / f"underlying={underlying}" / "data.parquet"


def partition_path_to_dict(path: str | Path) -> dict[str, str]:
    """Parse a partition path back into its key/value parts.

    Returns:
        ``{"timeframe": "1m", "symbol": "RELIANCE", ...}`` for any
        component whose name appears in the known partition keys. Non-
        partition segments (``equities``, ``candles``, ``data.parquet``)
        are ignored.

    Examples
    --------
    >>> partition_path_to_dict("market_data/equities/candles/timeframe=1m/symbol=RELIANCE/data.parquet")
    {'timeframe': '1m', 'symbol': 'RELIANCE'}
    >>> partition_path_to_dict("market_data/options/chains/expiry=2026-06-26/underlying=NIFTY/data.parquet")
    {'expiry': '2026-06-26', 'underlying': 'NIFTY'}
    """
    result: dict[str, str] = {}
    known_keys = {
        PARTITION_TIMEFRAME,
        PARTITION_SYMBOL,
        PARTITION_EXPIRY,
        PARTITION_UNDERLYING,
    }
    for part in Path(path).parts:
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        if key in known_keys:
            result[key] = value
    return result


__all__ = [
    "DEFAULT_DATA_ROOT",
    "DEFAULT_TIMEFRAME",
    "PARTITION_EXPIRY",
    "PARTITION_SYMBOL",
    "PARTITION_TIMEFRAME",
    "PARTITION_UNDERLYING",
    "SUPPORTED_TIMEFRAMES",
    "option_partition_path",
    "partition_path_to_dict",
    "symbol_partition_glob",
    "symbol_partition_path",
]
