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

from datalake.core.constants import (
    CURATED_ROOT,
    DEFAULT_DATA_ROOT,
    DEFAULT_TIMEFRAME,
    SUPPORTED_TIMEFRAMES,
)

# Supported timeframes (defined in :mod:`datalake.core.constants`). Adding a new
# one requires also adding it to the historical loader's ``_TIMEFRAME_MAP`` in
# :mod:`brokers.providers.dhan.historical` and the corresponding CLI
# ``options sync`` and ``backtest`` commands.

# Default timeframe for ``DataLake.history`` and CLI smoke tests (see
# :data:`datalake.core.constants.DEFAULT_TIMEFRAME`).

# Partition scheme constants. These are the keys used in the path.
PARTITION_TIMEFRAME: str = "timeframe"
PARTITION_SYMBOL: str = "symbol"
PARTITION_EXPIRY: str = "expiry"
PARTITION_UNDERLYING: str = "underlying"
PARTITION_EXPIRY_KIND: str = "expiry_kind"
PARTITION_EXPIRY_CODE: str = "expiry_code"
PARTITION_CONTRACT_STATE: str = "contract_state"


def contract_option_partition_path(
    root: str,
    exchange: str,
    underlying: str,
    expiry: str,
    timeframe: str,
) -> Path:
    """Contract-centric option OHLCV path (ADR-0023)."""
    from datalake.core.symbols import normalize_symbol_for_storage

    u = normalize_symbol_for_storage(underlying)
    ex = normalize_symbol_for_storage(exchange)
    return (
        Path(root)
        / "contracts"
        / "options"
        / "candles"
        / f"exchange={ex}"
        / f"underlying={u}"
        / f"expiry={expiry}"
        / f"timeframe={timeframe}"
        / "data.parquet"
    )


def contract_future_partition_path(
    root: str,
    exchange: str,
    underlying: str,
    expiry: str,
    timeframe: str,
) -> Path:
    """Contract-centric future OHLCV path (ADR-0023)."""
    from datalake.core.symbols import normalize_symbol_for_storage

    u = normalize_symbol_for_storage(underlying)
    ex = normalize_symbol_for_storage(exchange)
    return (
        Path(root)
        / "contracts"
        / "futures"
        / "candles"
        / f"exchange={ex}"
        / f"underlying={u}"
        / f"expiry={expiry}"
        / f"timeframe={timeframe}"
        / "data.parquet"
    )


def option_candle_partition_path(
    root: str,
    underlying: str,
    expiry_kind: str,
    expiry_code: int,
) -> Path:
    """Canonical path for rolling options OHLCV parquet (``options/candles/``)."""
    from datalake.core.symbols import normalize_symbol_for_storage

    u = normalize_symbol_for_storage(underlying)
    return (
        Path(root)
        / "options"
        / "candles"
        / f"underlying={u}"
        / f"expiry_kind={expiry_kind}"
        / f"expiry_code={int(expiry_code)}"
        / "data.parquet"
    )


def symbol_partition_path(
    root: str,
    symbol: str,
    timeframe: str = DEFAULT_TIMEFRAME,
) -> Path:
    """LEGACY — Return the path to a single symbol's candle Parquet file.

    .. deprecated::
        Use :func:`curated_equity_path` instead. The legacy symbol-per-
        file layout produces many tiny files, harming DuckDB performance.

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
            f"unsupported timeframe {timeframe!r}; supported: {sorted(SUPPORTED_TIMEFRAMES)}"
        )
    from config.indices import is_index

    asset = "indices" if is_index(symbol) else "equities"
    return (
        Path(root)
        / asset
        / "candles"
        / f"timeframe={timeframe}"
        / f"symbol={symbol}"
        / "data.parquet"
    )


def symbol_partition_glob(
    root: str,
    timeframe: str = DEFAULT_TIMEFRAME,
) -> str:
    """LEGACY — Return a SQL/glob pattern matching every symbol's data for a timeframe.

    .. deprecated::
        Use :func:`curated_equity_glob` instead.
    """
    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise ValueError(
            f"unsupported timeframe {timeframe!r}; supported: {sorted(SUPPORTED_TIMEFRAMES)}"
        )
    return f"{root}/equities/candles/timeframe={timeframe}/symbol=*/data.parquet"


def timeframe_partition_dir(
    root: str,
    timeframe: str = DEFAULT_TIMEFRAME,
) -> Path:
    """Return the directory path for a timeframe's candle data.

    Layout: ``{root}/equities/candles/timeframe={timeframe}/``
    """
    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise ValueError(
            f"unsupported timeframe {timeframe!r}; supported: {sorted(SUPPORTED_TIMEFRAMES)}"
        )
    return Path(root) / "equities" / "candles" / f"timeframe={timeframe}"


# ---------------------------------------------------------------------------
# Curated (date-partitioned) layout — preferred for new readers/writers
# ---------------------------------------------------------------------------

CURATED_EQUITY_CANDLES: str = "equities/candles"


def curated_equity_path(
    root: str = CURATED_ROOT,
    year: int | None = None,
    month: int | None = None,
) -> Path:
    """Return path for curated equity candle data.

    Layout: ``{root}/equities/candles/year={year}/month={month}/``

    If *year* or *month* is ``None``, the corresponding directory
    component is omitted so the returned path can be used as a parent
    for glob patterns.
    """
    parts = [Path(root), "equities", "candles"]
    if year is not None:
        parts.append(f"year={year:04d}")
    if month is not None:
        parts.append(f"month={month:02d}")
    return Path(*parts)


def curated_equity_glob(
    root: str = CURATED_ROOT,
    from_year: int | None = None,
    to_year: int | None = None,
) -> str:
    """Return a glob pattern for curated equity candles in a date range."""
    if from_year is not None and to_year is not None and from_year == to_year:
        return f"{root}/equities/candles/year={from_year:04d}/month=*/data_*.parquet"
    return f"{root}/equities/candles/year=*/month=*/data_*.parquet"


def legacy_symbol_partition_path(
    root: str,
    symbol: str,
    timeframe: str = DEFAULT_TIMEFRAME,
) -> Path:
    """Return the OLD path to a single symbol's candle file (deprecated).

    Thin wrapper around :func:`symbol_partition_path` to make migration
    call sites explicit about which layout they target.
    """
    return symbol_partition_path(root, symbol, timeframe)


def migrate_legacy_to_curated(
    root: str | None = None,
    curated_root: str = CURATED_ROOT,
    timeframe: str = "1m",
    target_mb: int = 150,
    *,
    dry_run: bool = True,
) -> dict:
    """Merge all legacy symbol= files into date-partitioned curated files.

    Thin wrapper over the migration script implementation (TOS-P6-010).
    Defaults to ``dry_run=True`` so accidental imports are safe.
    """
    if root is None:
        from domain.ports.data_catalog import DEFAULT_DATA_PATHS

        root = DEFAULT_DATA_PATHS.lake_root
    try:
        from scripts.migration.migrate_to_curated_layout import migrate
    except ImportError:
        # When installed without scripts package on path, try module path.
        import importlib

        mod = importlib.import_module("scripts.migration.migrate_to_curated_layout")
        migrate = mod.migrate
    return migrate(
        root=root,
        curated_root=curated_root,
        timeframe=timeframe,
        target_mb=target_mb,
        dry_run=dry_run,
    )


def get_candle_path(
    symbol: str,
    timeframe: str,
    root: str = DEFAULT_DATA_ROOT,
) -> Path:
    """Return the legacy hive-partition path for a symbol's candle file.

    This is the canonical single-location helper used by
    :mod:`datalake.cache_utils` and :mod:`datalake.gateway` to locate
    a symbol's parquet file without constructing the path inline.

    Layout: ``{root}/equities/candles/timeframe={timeframe}/symbol={symbol}/data.parquet``

    Parameters
    ----------
    symbol:
        Instrument symbol (will be normalized).
    timeframe:
        Candle timeframe (e.g. ``"1m"``, ``"5m"``).
    root:
        Datalake root directory.  Defaults to :data:`DEFAULT_DATA_ROOT`.
    """
    from datalake.core.symbols import normalize_symbol_for_storage

    symbol = normalize_symbol_for_storage(symbol)
    return (
        Path(root)
        / "equities"
        / "candles"
        / f"timeframe={timeframe}"
        / f"symbol={symbol}"
        / "data.parquet"
    )


def option_partition_path(
    root: str,
    expiry: str,
    underlying: str,
) -> Path:
    """Return the path to an option-chain Parquet file."""
    return (
        Path(root)
        / "options"
        / "chains"
        / f"expiry={expiry}"
        / f"underlying={underlying}"
        / "data.parquet"
    )


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
    "CURATED_EQUITY_CANDLES",
    "CURATED_ROOT",
    "DEFAULT_DATA_ROOT",
    "DEFAULT_TIMEFRAME",
    "PARTITION_EXPIRY",
    "PARTITION_SYMBOL",
    "PARTITION_TIMEFRAME",
    "PARTITION_UNDERLYING",
    "SUPPORTED_TIMEFRAMES",
    "curated_equity_glob",
    "curated_equity_path",
    "get_candle_path",
    "legacy_symbol_partition_path",
    "migrate_legacy_to_curated",
    "option_partition_path",
    "partition_path_to_dict",
    "symbol_partition_glob",
    "symbol_partition_path",
    "timeframe_partition_dir",
]
