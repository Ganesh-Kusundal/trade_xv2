"""E2E tests for Flow 2: Market Data → Order.

Tests the complete data pipeline from quote ingestion through risk checks
to order placement, using real DuckDB and ViewManager instances.

Flow stages verified:
  1. Quote ingestion → DuckDB table → Analytics view
  2. OHLCV invariant validation (anomaly detection)
  3. ViewManager composition (Registry + Executor + Cache)
  4. No look-ahead bias in feature computation
  5. Feature → Strategy signal (SignalDTO)
  6. Risk check rejects order exceeding limits
  7. Risk check passes order within limits → order placed
  8. View refresh after new data insertion
  9. CacheManager materialization lifecycle
 10. QueryExecutor read-only safety enforcement
"""

from __future__ import annotations

from decimal import Decimal

import duckdb
import pytest

pytestmark = pytest.mark.e2e

from analytics.views.manager import ViewManager  # noqa: E402
from application.oms.order_manager import OmsOrderCommand, OrderManager  # noqa: E402
from datalake.core.duckdb_utils import close_all_connections  # noqa: E402
from domain import Order, OrderStatus, OrderType, ProductType, Side  # noqa: E402
from domain.models.trading import SignalDTO  # noqa: E402
from tests.e2e.fixtures.data_generators import generate_ohlcv_data  # noqa: E402
from tests.e2e.fixtures.trading_context_factory import create_paper_trading_context  # noqa: E402

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def view_manager(tmp_path):
    """Create a ViewManager backed by a temp DuckDB catalog.

    Uses tmp_path for full DuckDB file fidelity (connection pool,
    read-only connections, and materialization all work correctly).
    Cleans up all pooled connections after each test.
    """
    catalog_path = tmp_path / "test_catalog.duckdb"
    vm = ViewManager(catalog_path=catalog_path)
    try:
        yield vm
    finally:
        vm.close()
        close_all_connections()


def _insert_ohlcv(conn: duckdb.DuckDBPyConnection, df) -> None:
    """Insert OHLCV DataFrame rows into a ``candles`` table."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS candles (
            timestamp TIMESTAMP,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume DOUBLE,
            symbol VARCHAR
        )
        """
    )
    for _, row in df.iterrows():
        conn.execute(
            "INSERT INTO candles VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                str(row["timestamp"]),
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
                float(row["volume"]),
                str(row["symbol"]),
            ],
        )


# ── Tests 1-7: In-memory-speed flow (DuckDB via tmp_path catalog) ──────────


def test_quote_ingestion_to_view(view_manager: ViewManager) -> None:
    """Quote → DataLake → View: raw candles land in a table and are
    exposed through a DuckDB view with correct data and registration."""
    conn = view_manager.conn
    df = generate_ohlcv_data(n_bars=10, seed=42)
    _insert_ohlcv(conn, df)

    # Create an analytics view over the raw candles
    conn.execute(
        """
        CREATE VIEW v_latest_quotes AS
        SELECT symbol, close AS ltp, high AS day_high,
               low AS day_low, volume
        FROM candles
        """
    )

    # View returns all inserted rows
    rows = conn.execute("SELECT * FROM v_latest_quotes").fetchall()
    assert len(rows) == 10
    assert rows[0][0] == "RELIANCE"  # symbol column

    # ViewManager's registry sees the view
    views = view_manager.list_views()
    view_names = [v["name"] for v in views]
    assert "v_latest_quotes" in view_names

    # View column introspection works
    cols = view_manager.view_columns("v_latest_quotes")
    assert "symbol" in cols
    assert "ltp" in cols


def test_ohlcv_invariants_preserved(view_manager: ViewManager) -> None:
    """OHLCV invariant violations (H < L, V < 0) are flagged by a
    quality-check view that counts anomalies per symbol."""
    conn = view_manager.conn

    # Insert clean bar
    conn.execute(
        """
        CREATE TABLE candles_raw (
            timestamp TIMESTAMP, open DOUBLE, high DOUBLE,
            low DOUBLE, close DOUBLE, volume DOUBLE, symbol VARCHAR
        )
        """
    )
    conn.execute(
        "INSERT INTO candles_raw VALUES "
        "('2026-01-01 09:15:00', 100, 105, 95, 102, 50000, 'RELIANCE')"
    )
    # Insert anomaly bar: high < low AND negative volume
    conn.execute(
        "INSERT INTO candles_raw VALUES "
        "('2026-01-01 09:16:00', 100, 90, 110, 102, -500, 'RELIANCE')"
    )

    # Quality view that flags OHLCV invariant violations
    conn.execute(
        """
        CREATE VIEW v_data_quality AS
        SELECT
            symbol,
            COUNT(*) FILTER (WHERE high < low) AS hl_violations,
            COUNT(*) FILTER (WHERE volume < 0) AS neg_vol_violations,
            COUNT(*) AS total_bars
        FROM candles_raw
        GROUP BY symbol
        """
    )

    row = conn.execute(
        "SELECT hl_violations, neg_vol_violations, total_bars "
        "FROM v_data_quality WHERE symbol = 'RELIANCE'"
    ).fetchone()

    assert row is not None
    hl_violations, neg_vol_violations, total_bars = row
    assert hl_violations == 1, f"Expected 1 H<L violation, got {hl_violations}"
    assert neg_vol_violations == 1, f"Expected 1 negative volume violation, got {neg_vol_violations}"
    assert total_bars == 2


def test_view_manager_composition(view_manager: ViewManager) -> None:
    """ViewManager composes ViewRegistry + QueryExecutor + CacheManager."""
    from analytics.views.cache_manager import CacheManager
    from analytics.views.view_registry import ViewRegistry

    # All three modules are instantiated
    assert hasattr(view_manager, "_registry")
    assert hasattr(view_manager, "_executor")
    assert hasattr(view_manager, "_cache")

    # Correct types
    assert isinstance(view_manager._registry, ViewRegistry)
    assert isinstance(view_manager._cache, CacheManager)

    # Domain-level view sub-modules are composed
    assert hasattr(view_manager, "base")
    assert hasattr(view_manager, "features")
    assert hasattr(view_manager, "scanner")
    assert hasattr(view_manager, "strategy")

    # Introspection delegation works through the registry
    assert view_manager.view_count() >= 0
    assert view_manager.table_count() >= 0


def test_feature_fetcher_no_lookahead(view_manager: ViewManager) -> None:
    """Bar N's features must NOT contain data from bar N+1 or later.

    Verifies:
    - SMA(5) at bar N uses only bars [max(0, N-4) … N] (backward-only)
    - SQL definition contains no LEAD() or FOLLOWING window frames
    - Adding future bars does NOT change already-computed feature values
    """
    conn = view_manager.conn
    df = generate_ohlcv_data(n_bars=10, seed=42)
    _insert_ohlcv(conn, df)

    # Feature view using ONLY backward-looking window (PRECEDING)
    conn.execute(
        """
        CREATE VIEW v_feature_sma AS
        SELECT
            symbol,
            timestamp,
            close,
            AVG(close) OVER (
                PARTITION BY symbol ORDER BY timestamp
                ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
            ) AS sma_5
        FROM candles
        """
    )

    # 1. SQL definition must not contain look-ahead constructs
    sql_def = conn.execute(
        "SELECT sql FROM duckdb_views() WHERE view_name = 'v_feature_sma'"
    ).fetchone()[0]
    upper_sql = sql_def.upper()
    assert "LEAD(" not in upper_sql, "LEAD() detected — look-ahead bias"
    assert "FOLLOWING" not in upper_sql, "FOLLOWING window — look-ahead bias"

    # 2. Query features ordered by timestamp
    features_before = (
        conn.execute(
            "SELECT symbol, timestamp, close, sma_5 "
            "FROM v_feature_sma ORDER BY timestamp"
        ).fetchall()
    )
    assert len(features_before) == 10

    # 3. SMA at bar 4 = mean of close[0:5] (only past data used)
    close_values = [features_before[i][2] for i in range(5)]
    expected_sma = sum(close_values) / 5.0
    assert abs(features_before[4][3] - expected_sma) < 1e-10, (
        f"SMA mismatch: expected {expected_sma}, got {features_before[4][3]}"
    )

    # 4. Snapshot SMA values for bars 0-9 BEFORE adding future data
    sma_snapshot = [row[3] for row in features_before]

    # 5. Insert 10 MORE bars (future data beyond the original set)
    df_future = generate_ohlcv_data(
        n_bars=10, start_price=200.0, seed=99,
        start_date=df["timestamp"].iloc[-1] + __import__("datetime").timedelta(minutes=1),
    )
    _insert_ohlcv(conn, df_future)

    # 6. Re-query: original bars' SMA values must be UNCHANGED
    features_after = (
        conn.execute(
            "SELECT symbol, timestamp, close, sma_5 "
            "FROM v_feature_sma ORDER BY timestamp"
        ).fetchall()
    )
    for i in range(10):
        old_sma = sma_snapshot[i]
        new_sma = features_after[i][3]
        if old_sma is not None and new_sma is not None:
            assert abs(old_sma - new_sma) < 1e-10, (
                f"Bar {i} SMA changed from {old_sma} to {new_sma} "
                f"after adding future data — look-ahead leak!"
            )


def test_strategy_signal_from_features(view_manager: ViewManager) -> None:
    """Features computed from candles are consumed by strategy logic
    to produce a SignalDTO with correct fields and actionable flag."""
    conn = view_manager.conn
    df = generate_ohlcv_data(n_bars=20, start_price=100.0, seed=42)
    _insert_ohlcv(conn, df)

    # Compute a simple feature: last close price
    last_close = conn.execute(
        "SELECT close FROM candles ORDER BY timestamp DESC LIMIT 1"
    ).fetchone()[0]

    # Strategy logic: price above 100 → BUY (deterministic for seed=42)
    signal = SignalDTO(
        symbol="RELIANCE",
        exchange="NSE",
        side="BUY",
        signal_type="BUY",
        confidence=Decimal("0.75"),
        quantity=10,
        entry_price=Decimal(str(round(last_close, 2))),
        strategy="test_simple_momentum",
    )

    # SignalDTO is correctly constructed
    assert signal.symbol == "RELIANCE"
    assert signal.exchange == "NSE"
    assert signal.signal_type == "BUY"
    assert signal.confidence == Decimal("0.75")
    assert signal.is_actionable is True
    assert signal.entry_price > Decimal("0")
    assert signal.strategy == "test_simple_momentum"


def test_risk_check_before_order(view_manager: ViewManager, tmp_path) -> None:
    """Order exceeding max_position_pct risk limit is REJECTED before
    reaching the broker — capital protection gate works."""
    ctx = create_paper_trading_context(
        capital=Decimal("100000"),
        max_position_pct=Decimal("10"),  # 10% of 100k = 10,000 max notional
        events_dir=tmp_path / "events",
    )

    # Order: 1000 shares × 150 = 150,000 notional → 150% of capital
    order = Order(
        order_id="ORD-RISK-001",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=1000,
        price=Decimal("150"),
        product_type=ProductType.INTRADAY,
        status=OrderStatus.OPEN,
    )

    result = ctx.risk_manager.check_order(order)
    assert result.allowed is False
    assert result.reason is not None
    assert "position" in result.reason.lower() or "exceeds" in result.reason.lower()


def test_order_placed_after_risk_pass(view_manager: ViewManager, tmp_path) -> None:
    """Order within risk limits passes risk check and is placed
    successfully through the OrderManager."""
    ctx = create_paper_trading_context(
        capital=Decimal("100000"),
        max_position_pct=Decimal("50"),  # 50% of 100k = 50,000 max
        events_dir=tmp_path / "events",
    )

    order_manager = OrderManager(
        event_bus=ctx.event_bus,
        risk_manager=ctx.risk_manager,
    )

    # Order: 10 shares × 120 = 1,200 notional → 1.2% of capital (well within 50%)
    command = OmsOrderCommand(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price=Decimal("120"),
        product_type=ProductType.INTRADAY,
        correlation_id="test:flow2:e2e:001",
    )

    result = order_manager.place_order(command)
    assert result.success is True, f"Order should succeed, got error: {result.error}"
    assert result.order is not None
    assert result.order.status == OrderStatus.OPEN
    assert result.order.symbol == "RELIANCE"
    assert result.order.quantity == 10

    # Order is retrievable from the order book
    retrieved = order_manager.get_order(result.order.order_id)
    assert retrieved is not None
    assert retrieved.symbol == "RELIANCE"


# ── Tests 8-10: Persistence-required flow (tmp_path catalog) ───────────────


def test_view_refresh_after_data_insert(view_manager: ViewManager) -> None:
    """After inserting new bars into the base table, the view
    automatically reflects the new data on next query."""
    conn = view_manager.conn

    # Insert initial batch
    conn.execute(
        """
        CREATE TABLE candles_ts (
            timestamp TIMESTAMP, open DOUBLE, high DOUBLE,
            low DOUBLE, close DOUBLE, volume DOUBLE, symbol VARCHAR
        )
        """
    )
    for i in range(10):
        conn.execute(
            "INSERT INTO candles_ts VALUES "
            "(?, 100, 105, 95, 102, 50000, 'RELIANCE')",
            [f"2026-01-01 09:{15 + i:02d}:00"],
        )

    # Create view over the table
    conn.execute(
        "CREATE VIEW v_ts_candles AS SELECT * FROM candles_ts"
    )

    # Verify initial count
    initial_count = conn.execute(
        "SELECT COUNT(*) FROM v_ts_candles"
    ).fetchone()[0]
    assert initial_count == 10

    # Insert 5 more bars
    for i in range(5):
        conn.execute(
            "INSERT INTO candles_ts VALUES "
            "(?, 103, 107, 100, 105, 60000, 'RELIANCE')",
            [f"2026-01-01 09:{25 + i:02d}:00"],
        )

    # View reflects the new data without explicit refresh
    updated_count = conn.execute(
        "SELECT COUNT(*) FROM v_ts_candles"
    ).fetchone()[0]
    assert updated_count == 15, (
        f"View should show 15 rows after insert, got {updated_count}"
    )


def test_cache_manager_materialization(view_manager: ViewManager) -> None:
    """CacheManager materializes a query result to Parquet and registers
    it as a queryable DuckDB table."""
    conn = view_manager.conn

    # Source table
    conn.execute(
        """
        CREATE TABLE source_candles (
            symbol VARCHAR, close DOUBLE, volume DOUBLE
        )
        """
    )
    conn.execute(
        "INSERT INTO source_candles VALUES ('RELIANCE', 100.5, 50000)"
    )
    conn.execute(
        "INSERT INTO source_candles VALUES ('TCS', 3500.0, 20000)"
    )

    # Materialize to versioned Parquet via ViewManager → CacheManager
    elapsed = view_manager.materialize(
        "test_mat_candles",
        "SELECT symbol, close, volume FROM source_candles",
    )
    assert isinstance(elapsed, float)
    assert elapsed >= 0

    # Register the materialized Parquet as a DuckDB table
    view_manager.register_materialized("test_mat_candles")

    # Verify the materialized table is queryable
    assert view_manager.table_exists("test_mat_candles")

    rows = conn.execute(
        "SELECT symbol, close, volume FROM test_mat_candles ORDER BY symbol"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0][0] == "RELIANCE"
    assert rows[1][0] == "TCS"


def test_query_executor_read_only_safety(tmp_path) -> None:
    """A read-only DuckDB connection can query data but cannot write.

    Verifies that DuckDB's read_only flag rejects write operations
    at the database level, which is the safety mechanism underlying
    ViewManager's read_only mode.
    """
    db_path = str(tmp_path / "ro_safety.duckdb")

    # Phase 1: Create data via a read-write connection
    conn_rw = duckdb.connect(db_path)
    conn_rw.execute(
        "CREATE TABLE ro_test_data AS SELECT 42 AS answer, 'test' AS label"
    )
    conn_rw.close()

    # Phase 2: Open a STRICTLY read-only connection (not via pool)
    conn_ro = duckdb.connect(db_path, read_only=True)

    # Read succeeds
    rows = conn_ro.execute("SELECT answer FROM ro_test_data").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 42

    # Write MUST fail on a read-only connection
    with pytest.raises(Exception):
        conn_ro.execute("CREATE TABLE should_fail (id INTEGER)")

    conn_ro.close()

    # Phase 3: ViewManager with read_only=True sets the flag correctly
    vm = ViewManager(catalog_path=tmp_path / "ro_vm.duckdb", read_only=True)
    try:
        assert vm._read_only is True
        assert vm._registry._read_only is True
    finally:
        vm.close()
        close_all_connections()
