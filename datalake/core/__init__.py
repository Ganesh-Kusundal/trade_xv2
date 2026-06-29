"""Datalake core infrastructure — paths, schema, symbols, connections, IO."""

from datalake.core.duckdb_utils import (
    DEFAULT_CATALOG_PATH,
    DuckDBPool,
    DuckDBReadPool,
    close_all_connections,
    connect_with_retry,
    duckdb_connection,
    get_connection,
    get_pool,
    get_read_pool,
)
from datalake.core.io import (
    atomic_json_write,
    atomic_parquet_write,
    atomic_text_write,
    file_lock,
)
from datalake.core.nse_calendar import (
    count_trading_days,
    expected_candles,
    is_early_close,
    is_trading_day,
    trading_days_between,
)
from datalake.core.option_format import (
    convert_format,
    make_option_symbol,
    map_expiry_code_to_date,
)
from datalake.core.paths import (
    CURATED_ROOT,
    DEFAULT_DATA_ROOT,
    DEFAULT_TIMEFRAME,
    SUPPORTED_TIMEFRAMES,
    curated_equity_glob,
    curated_equity_path,
    get_candle_path,
    option_partition_path,
    partition_path_to_dict,
    symbol_partition_glob,
    symbol_partition_path,
)
from datalake.core.pit_joins import (
    PitQueryConfig,
    as_of_join,
    pit_query,
    validate_no_lookahead,
)
from datalake.core.schema import (
    ARROW_SCHEMA,
    CANONICAL_COLUMNS,
    TEMPORAL_COLUMNS,
    TIMEFRAMES,
    UNIVERSE_FILES,
    load_universe,
)
from datalake.core.symbols import (
    are_same_symbol,
    normalize_symbol,
    normalize_universe_name,
    path_to_symbol,
    sanitize_path_param,
    symbol_to_path,
)
from datalake.core.universe import load_universe
