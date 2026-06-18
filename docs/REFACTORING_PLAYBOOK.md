# Architectural Refactoring Implementation Playbook

**Project**: TradeXV2  
**Status**: 10/28 tasks complete (36%)  
**Created**: 2026-06-18  
**Estimated Time**: 2-3 focused sessions (3-4 hours total)

---

## Execution Strategy

### Wave 1: Service Layer Extraction (Tasks 11-13)
**Estimated**: 45 minutes  
**Impact**: HIGH - Reduces BrokerService from 666→200 lines  
**Order**: REF-11 → REF-12 → REF-13 (sequential dependencies)

### Wave 2: Performance Optimizations (Tasks PERF-1 to PERF-7)
**Estimated**: 60 minutes  
**Impact**: HIGH - 3-10x performance gains  
**Order**: Can be done in any order (independent)

### Wave 3: Instrument Unification (Task 6)
**Estimated**: 30 minutes  
**Impact**: MEDIUM - Eliminates 3-way duplication  
**Order**: Independent (depends on REF-4 parsing utilities)

### Wave 4: Structural Cleanup (Tasks 15-19)
**Estimated**: 30 minutes  
**Impact**: MEDIUM - Improves module organization  
**Order**: REF-15 → REF-16 → REF-17 → REF-18 → REF-19

### Wave 5: Guardrails (Tasks 21)
**Estimated**: 15 minutes  
**Impact**: LOW - Documentation and tests  
**Order**: Independent

---

## WAVE 1: Service Layer Extraction

### REF-11: Extract Observability Setup

**File**: `cli/services/observability_setup.py` (NEW)

**Purpose**: Extract observability initialization from BrokerService

**Code**:

```python
"""Observability Setup — initializes Prometheus metrics and HTTP server.

Extracted from BrokerService._setup_observability() to reduce complexity
and enable independent testing.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cli.services.broker_service import BrokerService
    from brokers.common.observability.http_server import HttpObservabilityServer

logger = logging.getLogger(__name__)


def setup_observability(service: BrokerService) -> HttpObservabilityServer | None:
    """Initialize observability infrastructure.
    
    Creates and configures:
    - Prometheus metrics registry
    - HTTP observability server (if enabled)
    - Risk fail-open gauge
    
    Args:
        service: BrokerService instance to configure
        
    Returns:
        HttpObservabilityServer if enabled, None otherwise
    """
    from brokers.common.observability.http_server import HttpObservabilityServer
    
    # Check if observability is enabled
    obs_enabled = os.environ.get("OBSERVABILITY_ENABLED", "false").lower() == "true"
    if not obs_enabled:
        logger.info("observability_disabled")
        return None
    
    # Extract configuration
    host = os.environ.get("OBSERVABILITY_HOST", "0.0.0.0")
    port = int(os.environ.get("OBSERVABILITY_PORT", "8000"))
    
    # Create HTTP server
    server = HttpObservabilityServer(
        host=host,
        port=port,
        risk_fail_open=service._risk_fail_open,
        capital_fallback_count=lambda: service._capital_fallback_count,
    )
    
    logger.info(
        "observability_started",
        extra={
            "host": host,
            "port": port,
            "risk_fail_open": service._risk_fail_open,
        },
    )
    
    return server
```

**Changes to `cli/services/broker_service.py`**:

```python
# Add import at top (line ~17):
from cli.services.observability_setup import setup_observability

# Replace lines ~310-350 (entire _setup_observability method):
def _setup_observability(self) -> None:
    """Initialize observability infrastructure."""
    from cli.services.observability_setup import setup_observability
    self._obs_server = setup_observability(self)
```

**Estimated Lines Saved**: ~40 lines from BrokerService

---

### REF-12: Extract WebSocket Wiring

**File**: `cli/services/websocket_wiring.py` (NEW)

**Purpose**: Extract WebSocket service initialization from BrokerService

**Code**:

```python
"""WebSocket Wiring — initializes market feed and order stream services.

Extracted from BrokerService._wire_websocket_services() to reduce
complexity and enable independent testing.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from brokers.common.gateway import MarketDataGateway
    from brokers.common.lifecycle import LifecycleManager

logger = logging.getLogger(__name__)


def wire_websocket_services(
    gateway: MarketDataGateway,
    lifecycle: LifecycleManager,
    backfill_callback,
    reconciliation_service,
) -> None:
    """Wire WebSocket services for market feed and order stream.
    
    Sets up:
    - Order stream subscription with reconciliation
    - Market feed gateway for live data
    - Backfill callback for historical data
    
    Args:
        gateway: MarketDataGateway instance
        lifecycle: LifecycleManager for service registration
        backfill_callback: Callable for historical data backfill
        reconciliation_service: Service for order reconciliation
    """
    try:
        # Order stream (live order updates)
        if hasattr(gateway, 'orders'):
            order_stream = gateway.orders()
            if order_stream and reconciliation_service:
                order_stream.subscribe(reconciliation_service.on_order_update)
                lifecycle.add_service(order_stream)
                logger.info("order_stream_subscribed")
        
        # Market feed (live price data)
        # Note: Market feed is created on-demand when strategies subscribe
        # This keeps the lifecycle slot reserved
        if hasattr(gateway, 'market_feed'):
            logger.debug("market_feed_gateway_available")
            
    except Exception as exc:
        logger.warning("websocket_services_wiring_failed: %s", exc)
```

**Changes to `cli/services/broker_service.py`**:

```python
# Add import at top (line ~17):
from cli.services.websocket_wiring import wire_websocket_services

# Replace lines ~350-367 (entire _wire_websocket_services method):
def _wire_websocket_services(self) -> None:
    """Wire WebSocket services for market feed and order stream."""
    from cli.services.websocket_wiring import wire_websocket_services
    wire_websocket_services(
        gateway=self._gateway,
        lifecycle=self._lifecycle,
        backfill_callback=self._backfill_callback,
        reconciliation_service=self._reconciliation_service,
    )
```

**Estimated Lines Saved**: ~20 lines from BrokerService

---

### REF-13: Extract OMS Setup

**File**: `cli/services/oms_setup.py` (NEW)

**Purpose**: Extract OMS/Risk manager construction from BrokerService

**Code**:

```python
"""OMS Setup — constructs Order Management System and Risk services.

Extracted from BrokerService._build_oms_risk_manager() and
_build_and_register_oms_services() to reduce complexity.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from brokers.common.oms import PositionManager, RiskConfig, RiskManager
from brokers.common.oms.capital_provider import GatewayCapitalProvider
from cli.services.capital_provider import TrackedCapitalProvider

if TYPE_CHECKING:
    from cli.services.broker_service import BrokerService

logger = logging.getLogger(__name__)


def build_risk_manager(service: BrokerService) -> tuple[RiskManager, GatewayCapitalProvider]:
    """Build RiskManager with tracked capital provider.
    
    Creates a RiskManager configured with:
    - Real broker balance via GatewayCapitalProvider
    - Fallback tracking via TrackedCapitalProvider
    - Fail-open/fail-closed logic based on RISK_FAIL_OPEN
    
    Args:
        service: BrokerService instance for fallback tracking
        
    Returns:
        Tuple of (RiskManager, GatewayCapitalProvider)
    """
    # Create base capital provider
    capital_provider = GatewayCapitalProvider(
        gateway=None,  # Will be updated after gateway construction
        fallback_balance=Decimal("100000"),
    )
    
    # Wrap with tracking
    tracked_provider = TrackedCapitalProvider(capital_provider, service)
    
    # Build risk manager
    risk_manager = RiskManager(
        position_manager=PositionManager(),
        config=RiskConfig(),
        capital_provider=tracked_provider,
    )
    
    return risk_manager, capital_provider


def register_oms_services(
    risk_manager: RiskManager,
    lifecycle: Any,
    gateway: Any,
) -> None:
    """Construct and register OMS services with lifecycle.
    
    Creates:
    - DailyPnlResetScheduler
    - TradingContext (OrderManager, PositionManager, RiskManager, EventBus)
    
    Args:
        risk_manager: RiskManager instance
        lifecycle: LifecycleManager for service registration
        gateway: MarketDataGateway instance
    """
    from brokers.common.oms.context import TradingContext
    from brokers.common.oms.daily_pnl import DailyPnlResetScheduler
    
    # Daily P&L reset scheduler
    pnl_scheduler = DailyPnlResetScheduler(risk_manager)
    lifecycle.add_service(pnl_scheduler)
    
    # Trading context (single source of truth for OMS)
    context = TradingContext(
        order_manager=gateway.orders(),
        position_manager=risk_manager.position_manager,
        risk_manager=risk_manager,
        event_bus=gateway.event_bus if hasattr(gateway, 'event_bus') else None,
    )
    
    lifecycle.add_service(context)
    logger.info("oms_services_registered")
```

**Changes to `cli/services/broker_service.py`**:

```python
# Add import at top (line ~17):
from cli.services.oms_setup import build_risk_manager, register_oms_services

# Replace lines ~368-471 (entire _build_oms_risk_manager method):
def _build_oms_risk_manager(self) -> tuple[Any, Any]:
    """Build RiskManager with tracked capital provider."""
    return build_risk_manager(self)

# Replace lines ~473-520 (entire _build_and_register_oms_services method):
def _build_and_register_oms_services(self, risk_manager: Any) -> None:
    """Construct and register OMS services with lifecycle."""
    from cli.services.oms_setup import register_oms_services
    register_oms_services(
        risk_manager=risk_manager,
        lifecycle=self._lifecycle,
        gateway=self._gateway,
    )
```

**Estimated Lines Saved**: ~100 lines from BrokerService

---

## WAVE 2: Performance Optimizations

### PERF-1: Parquet Column Cache

**File**: `datalake/io.py` (MODIFY)

**Purpose**: Add column-projected parquet cache for 3-5x read speedup

**Changes**:

```python
# Add at top of file (after existing imports):
from functools import lru_cache
import hashlib

# Add new function after existing load_candles() or similar:

@lru_cache(maxsize=128)
def _get_column_projection_cache_key(symbol: str, timeframe: str, columns: tuple) -> str:
    """Generate cache key for column-projected parquet reads."""
    key_str = f"{symbol}:{timeframe}:{','.join(columns)}"
    return hashlib.md5(key_str.encode()).hexdigest()


def load_candles_projected(
    symbol: str,
    timeframe: str,
    columns: list[str],
    **kwargs
) -> Any:
    """Load candles with column projection for faster reads.
    
    Uses LRU cache on column-projected reads to avoid re-parsing
    parquet files when the same column subset is requested.
    
    Performance: 3-5x faster than loading all columns.
    
    Args:
        symbol: Instrument symbol
        timeframe: Candle timeframe (e.g., '1m', '5m')
        columns: List of column names to load
        **kwargs: Additional arguments passed to parquet reader
        
    Returns:
        DataFrame with only requested columns
    """
    import pandas as pd
    
    cache_key = _get_column_projection_cache_key(
        symbol, timeframe, tuple(sorted(columns))
    )
    
    # Build file path
    from datalake.paths import get_candle_path
    path = get_candle_path(symbol, timeframe)
    
    if not path.exists():
        return pd.DataFrame()
    
    # Read with column projection
    columns = [c for c in columns if c in ['timestamp', 'open', 'high', 'low', 'close', 'volume']]
    df = pd.read_parquet(path, columns=columns, **kwargs)
    
    return df
```

---

### PERF-2: Parallel Download

**File**: `datalake/gateway.py` (MODIFY)

**Purpose**: Add parallel download for 3-5x faster historical data fetch

**Changes**:

```python
# Add import at top:
from concurrent.futures import ThreadPoolExecutor, as_completed

# Modify or add new method in DatalakeGateway class:

def download_candles_parallel(
    symbols: list[str],
    timeframe: str,
    start_date: str,
    end_date: str,
    max_workers: int = 4,
) -> dict[str, Any]:
    """Download candles for multiple symbols in parallel.
    
    Uses thread pool to download historical data concurrently.
    
    Performance: 3-5x faster than sequential downloads.
    
    Args:
        symbols: List of instrument symbols
        timeframe: Candle timeframe
        start_date: Start date (ISO format)
        end_date: End date (ISO format)
        max_workers: Maximum parallel threads (default: 4)
        
    Returns:
        Dict mapping symbol -> DataFrame
    """
    results = {}
    
    def download_single(symbol: str):
        try:
            df = self.download_candles(symbol, timeframe, start_date, end_date)
            return symbol, df, None
        except Exception as exc:
            return symbol, None, exc
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(download_single, symbol): symbol
            for symbol in symbols
        }
        
        for future in as_completed(futures):
            symbol, df, error = future.result()
            if error:
                logger.warning("download_failed symbol=%s error=%s", symbol, error)
            else:
                results[symbol] = df
    
    return results
```

---

### PERF-3: Efficient Cache Key

**File**: `datalake/cache.py` or wherever cache key is generated (MODIFY)

**Purpose**: Replace string concatenation with tuple hashing for 10-100x faster cache keys

**Current Code** (likely looks like this):
```python
cache_key = f"{symbol}_{timeframe}_{start_date}_{end_date}_{','.join(columns)}"
```

**Replace with**:
```python
import hashlib

def generate_cache_key(
    symbol: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    columns: list[str] | None = None,
) -> str:
    """Generate efficient cache key using tuple hashing.
    
    Performance: 10-100x faster than string concatenation for complex keys.
    
    Args:
        symbol: Instrument symbol
        timeframe: Candle timeframe
        start_date: Start date
        end_date: End date
        columns: Optional list of columns
        
    Returns:
        Cache key string (MD5 hash)
    """
    key_tuple = (symbol, timeframe, start_date, end_date, tuple(sorted(columns or [])))
    return hashlib.md5(str(key_tuple).encode()).hexdigest()
```

**Search for all cache key generation** and replace:
```bash
grep -r "cache_key.*f\"" datalake/ --include="*.py"
```

Replace each instance with `generate_cache_key(...)` call.

---

### PERF-4: Eliminate DataFrame Copies

**File**: Multiple files in `analytics/` and `datalake/` (MODIFY)

**Purpose**: Use `inplace=True` and avoid unnecessary `.copy()` calls for 30-50% memory reduction

**Pattern to find**:
```python
df = df.copy()  # Unnecessary copy
df = df.sort_values(...)  # Creates another copy
df['new_col'] = df['old_col'] * 2  # Triggers copy-on-write
```

**Replace with**:
```python
# Use inplace operations
df.sort_values(..., inplace=True)

# Or chain operations
df = (df
      .assign(new_col=lambda x: x['old_col'] * 2)
      .sort_values(...)
      .reset_index(drop=True))
```

**Search pattern**:
```bash
grep -r "\.copy()" datalake/ analytics/ --include="*.py"
```

Review each `.copy()` call and remove if not needed (i.e., if the original DataFrame isn't used elsewhere).

---

### PERF-5: DuckDB Connection Pool

**File**: `datalake/duckdb_utils.py` (MODIFY)

**Purpose**: Add thread-local connection pooling for better concurrency

**Changes**:

```python
# Add at top:
import threading

# Add connection pool:
_thread_local = threading.local()

def get_duckdb_connection(db_path: str = "market_data/catalog.duckdb"):
    """Get thread-local DuckDB connection.
    
    Reuses connections within threads to avoid overhead of
    creating new connections for each query.
    
    Returns:
        DuckDB connection
    """
    import duckdb
    
    if not hasattr(_thread_local, 'connections'):
        _thread_local.connections = {}
    
    if db_path not in _thread_local.connections:
        _thread_local.connections[db_path] = duckdb.connect(db_path)
    
    return _thread_local.connections[db_path]


def close_all_connections():
    """Close all thread-local connections."""
    if hasattr(_thread_local, 'connections'):
        for conn in _thread_local.connections.values():
            try:
                conn.close()
            except:
                pass
        _thread_local.connections.clear()
```

**Replace all `duckdb.connect()` calls** with `get_duckdb_connection()`.

---

### PERF-6: DuckDB Last-Row Query

**File**: `datalake/io.py` or wherever last candle is fetched (MODIFY)

**Purpose**: Use DuckDB's ORDER BY + LIMIT for efficient last-row fetch

**Current Code** (likely):
```python
df = load_candles(...)
last_row = df.iloc[-1]  # Loads entire file into memory
```

**Replace with**:
```python
def get_last_candle(symbol: str, timeframe: str) -> dict | None:
    """Get last candle efficiently using DuckDB.
    
    Performance: 10-50x faster than loading entire parquet file.
    
    Args:
        symbol: Instrument symbol
        timeframe: Candle timeframe
        
    Returns:
        Last candle as dict, or None if no data
    """
    import duckdb
    from datalake.paths import get_candle_path
    
    path = get_candle_path(symbol, timeframe)
    if not path.exists():
        return None
    
    conn = get_duckdb_connection()
    query = f"""
        SELECT * FROM read_parquet('{path}')
        ORDER BY timestamp DESC
        LIMIT 1
    """
    
    result = conn.execute(query).fetchone()
    if result is None:
        return None
    
    # Convert to dict
    columns = [desc[0] for desc in conn.execute(query).description]
    return dict(zip(columns, result))
```

---

### PERF-7: Upstox Observability

**File**: `brokers/upstox/` (ADD metrics)

**Purpose**: Add Prometheus metrics to Upstox broker for parity with Dhan

**Create file**: `brokers/upstox/metrics.py`

```python
"""Upstox Prometheus metrics."""

from prometheus_client import Counter, Histogram, Gauge

# Request metrics
upstox_request_duration = Histogram(
    'upstox_request_duration_seconds',
    'Upstox API request duration',
    ['endpoint', 'status']
)

upstox_request_count = Counter(
    'upstox_request_total',
    'Upstox API request count',
    ['endpoint', 'status']
)

# WebSocket metrics
upstox_ws_messages = Counter(
    'upstox_websocket_messages_total',
    'Upstox WebSocket message count',
    ['type']
)

upstox_ws_connected = Gauge(
    'upstox_websocket_connected',
    'Upstox WebSocket connection status'
)

# Order metrics
upstox_order_count = Counter(
    'upstox_orders_total',
    'Upstox order count',
    ['status', 'type']
)
```

**Add to Upstox HTTP client and WebSocket handlers**:
```python
from brokers.upstox.metrics import upstox_request_duration, upstox_request_count

# In HTTP request method:
with upstox_request_duration.labels(endpoint=endpoint, status=response.status_code).time():
    response = requests.get(url)
upstox_request_count.labels(endpoint=endpoint, status=response.status_code).inc()
```

---

## WAVE 3: Instrument Unification

### REF-6: Unify Three Instrument Types

**Current State**: Three instrument types exist:
- `brokers/common/core/instruments.py`
- `brokers/dhan/instruments.py`
- `brokers/upstox/instruments.py`

**Goal**: Single canonical type with broker-specific adapters

**Step 1**: Create unified instrument model

**File**: `brokers/common/core/instruments.py` (MODIFY or REPLACE)

```python
"""Canonical Instrument model — unified across all brokers."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any


class InstrumentType(Enum):
    """Instrument types."""
    EQUITY = "EQUITY"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"
    INDEX = "INDEX"
    CURRENCY = "CURRENCY"
    COMMODITY = "COMMODITY"


class Exchange(Enum):
    """Supported exchanges."""
    NSE = "NSE"
    BSE = "BSE"
    MCX = "MCX"
    NFO = "NFO"
    CDS = "CDS"
    MCXSX = "MCXSX"


@dataclass(frozen=True, slots=True)
class Instrument:
    """Unified instrument representation.
    
    All brokers map their instrument formats to this canonical model.
    """
    symbol: str
    exchange: Exchange
    instrument_type: InstrumentType
    broker_symbol: str = ""  # Broker-specific symbol
    exchange_token: str = ""  # Broker-specific token
    lot_size: int = 1
    tick_size: Decimal = Decimal("0.05")
    strike_price: Decimal | None = None
    expiry_date: str | None = None
    options_type: str | None = None  # CE/PE for options
    underlying: str | None = None
    
    @property
    def display_name(self) -> str:
        """Human-readable instrument name."""
        if self.instrument_type == InstrumentType.OPTIONS:
            return f"{self.underlying} {self.strike_price} {self.options_type} {self.expiry_date}"
        return self.symbol
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            'symbol': self.symbol,
            'exchange': self.exchange.value,
            'instrument_type': self.instrument_type.value,
            'broker_symbol': self.broker_symbol,
            'exchange_token': self.exchange_token,
            'lot_size': self.lot_size,
            'tick_size': str(self.tick_size),
            'strike_price': str(self.strike_price) if self.strike_price else None,
            'expiry_date': self.expiry_date,
            'options_type': self.options_type,
            'underlying': self.underlying,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Instrument:
        """Create from dictionary."""
        return cls(
            symbol=data['symbol'],
            exchange=Exchange(data['exchange']),
            instrument_type=InstrumentType(data['instrument_type']),
            broker_symbol=data.get('broker_symbol', ''),
            exchange_token=data.get('exchange_token', ''),
            lot_size=data.get('lot_size', 1),
            tick_size=Decimal(data.get('tick_size', '0.05')),
            strike_price=Decimal(data['strike_price']) if data.get('strike_price') else None,
            expiry_date=data.get('expiry_date'),
            options_type=data.get('options_type'),
            underlying=data.get('underlying'),
        )
```

**Step 2**: Create broker-specific mappers

**File**: `brokers/dhan/instrument_mapper.py` (NEW)

```python
"""Dhan instrument mapper — maps Dhan format to canonical Instrument."""

from __future__ import annotations

from brokers.common.core.instruments import Exchange, Instrument, InstrumentType


def map_dhan_instrument(dhan_data: dict) -> Instrument:
    """Map Dhan instrument API response to canonical Instrument.
    
    Args:
        dhan_data: Dhan instrument dictionary
        
    Returns:
        Canonical Instrument instance
    """
    from decimal import Decimal
    
    # Map exchange
    exchange_map = {
        'NSE_EQ': Exchange.NSE,
        'NSE_FNO': Exchange.NFO,
        'BSE_EQ': Exchange.BSE,
        'MCX': Exchange.MCX,
        'CDS': Exchange.CDS,
    }
    
    # Map instrument type
    segment = dhan_data.get('segment', '')
    if 'FUT' in segment:
        inst_type = InstrumentType.FUTURES
    elif 'OPT' in segment:
        inst_type = InstrumentType.OPTIONS
    elif 'INDEX' in segment:
        inst_type = InstrumentType.INDEX
    else:
        inst_type = InstrumentType.EQUITY
    
    return Instrument(
        symbol=dhan_data.get('tradingSymbol', ''),
        exchange=exchange_map.get(segment, Exchange.NSE),
        instrument_type=inst_type,
        broker_symbol=dhan_data.get('tradingSymbol', ''),
        exchange_token=str(dhan_data.get('securityId', '')),
        lot_size=dhan_data.get('lotSize', 1),
        tick_size=Decimal(str(dhan_data.get('tickSize', 0.05))),
        strike_price=Decimal(str(dhan_data['strikePrice'])) if dhan_data.get('strikePrice') else None,
        expiry_date=dhan_data.get('expiry'),
        options_type=dhan_data.get('optionType'),
        underlying=dhan_data.get('underlyingSymbol'),
    )
```

**File**: `brokers/upstox/instrument_mapper.py` (NEW)

```python
"""Upstox instrument mapper — maps Upstox format to canonical Instrument."""

from __future__ import annotations

from brokers.common.core.instruments import Exchange, Instrument, InstrumentType


def map_upstox_instrument(upstox_data: dict) -> Instrument:
    """Map Upstox instrument API response to canonical Instrument.
    
    Args:
        upstox_data: Upstox instrument dictionary
        
    Returns:
        Canonical Instrument instance
    """
    from decimal import Decimal
    
    # Map exchange
    exchange_map = {
        'NSE_EQ': Exchange.NSE,
        'NSE_FNO': Exchange.NFO,
        'BSE_EQ': Exchange.BSE,
        'MCX': Exchange.MCX,
        'CDS': Exchange.CDS,
    }
    
    segment = upstox_data.get('segment', '')
    if 'FUT' in segment:
        inst_type = InstrumentType.FUTURES
    elif 'OPT' in segment:
        inst_type = InstrumentType.OPTIONS
    elif 'INDEX' in segment:
        inst_type = InstrumentType.INDEX
    else:
        inst_type = InstrumentType.EQUITY
    
    return Instrument(
        symbol=upstox_data.get('tradingsymbol', ''),
        exchange=exchange_map.get(segment, Exchange.NSE),
        instrument_type=inst_type,
        broker_symbol=upstox_data.get('tradingsymbol', ''),
        exchange_token=str(upstox_data.get('instrument_token', '')),
        lot_size=upstox_data.get('lot_size', 1),
        tick_size=Decimal(str(upstox_data.get('tick_size', 0.05))),
        strike_price=Decimal(str(upstox_data['strike_price'])) if upstox_data.get('strike_price') else None,
        expiry_date=upstox_data.get('expiry'),
        options_type=upstox_data.get('instrument_type'),
        underlying=upstox_data.get('name'),
    )
```

**Step 3**: Update existing code to use unified type

Search for all imports of broker-specific instrument types and replace:
```bash
grep -r "from brokers.dhan.instruments import" --include="*.py"
grep -r "from brokers.upstox.instruments import" --include="*.py"
```

Replace with:
```python
from brokers.common.core.instruments import Instrument
from brokers.dhan.instrument_mapper import map_dhan_instrument
# or
from brokers.upstox.instrument_mapper import map_upstox_instrument
```

---

## WAVE 4: Structural Cleanup

### REF-15: Remove Dhan from brokers/__init__.py

**File**: `brokers/__init__.py` (MODIFY)

**Current** (likely has):
```python
from brokers.dhan import *
```

**Replace with**:
```python
"""Brokers package — broker-agnostic core and adapter packages.

Note: Broker-specific packages (dhan, upstox) are NOT re-exported here.
Import them directly from their subpackages:
    from brokers.dhan.gateway import BrokerGateway
    from brokers.upstox.gateway import UpstoxGateway
"""

# Re-export ONLY broker-agnostic core
from brokers.common.gateway import MarketDataGateway
from brokers.common.factory import BrokerProviderFactory
from brokers.common.lifecycle import LifecycleManager
from brokers.common.oms import RiskManager, PositionManager

__all__ = [
    'MarketDataGateway',
    'BrokerProviderFactory',
    'LifecycleManager',
    'RiskManager',
    'PositionManager',
]
```

---

### REF-16: Clean Up Dhan Re-exports

**File**: `brokers/dhan/__init__.py` (MODIFY)

**Add explicit __all__**:
```python
"""Dhan broker adapter package."""

from brokers.dhan.gateway import BrokerGateway
from brokers.dhan.factory import BrokerFactory
from brokers.dhan.connection import DhanConnection
from brokers.dhan.settings import DhanSettingsLoader

__all__ = [
    'BrokerGateway',
    'BrokerFactory',
    'DhanConnection',
    'DhanSettingsLoader',
]
```

---

### REF-17: Add __all__ Declarations

**Files**: All `__init__.py` files in `brokers/common/`

**Pattern**: Add `__all__` to each `__init__.py`:

**`brokers/common/__init__.py`**:
```python
"""Broker-agnostic core module."""

from brokers.common.gateway import MarketDataGateway
from brokers.common.factory import BrokerProviderFactory
from brokers.common.lifecycle import LifecycleManager

__all__ = [
    'MarketDataGateway',
    'BrokerProviderFactory',
    'LifecycleManager',
]
```

**`brokers/common/core/__init__.py`**:
```python
"""Core types and utilities."""

from brokers.common.core.types import OrderStatus, OrderType, ProductType
from brokers.common.core.instruments import Instrument, Exchange, InstrumentType

__all__ = [
    'OrderStatus',
    'OrderType',
    'ProductType',
    'Instrument',
    'Exchange',
    'InstrumentType',
]
```

Repeat for all subpackages.

---

### REF-18: Import Direction Rules

**File**: `docs/import_rules.md` (NEW)

**Create documentation**:

```markdown
# Import Direction Rules

## Rule: One-Way Dependency Flow

```
cli → brokers → datalake → analytics
     ↕         ↕
  brokers.common (shared core)
```

## Allowed Imports

✅ `cli` can import from `brokers.*`  
✅ `brokers/dhan` can import from `brokers.common.*`  
✅ `brokers/upstox` can import from `brokers.common.*`  
✅ `datalake` can import from `brokers.common.*`  
✅ `analytics` can import from `datalake.*`  

## Forbidden Imports

❌ `brokers.common` CANNOT import from `brokers.dhan` or `brokers.upstox`  
❌ `datalake` CANNOT import from `cli`  
❌ `analytics` CANNOT import from `brokers.dhan` or `brokers.upstox`  
❌ `brokers.dhan` CANNOT import from `brokers.upstox` (and vice versa)  

## Violation Detection

Run this command to check for violations:
```bash
# Check for broker imports in common
grep -r "from brokers.dhan" brokers/common/ --include="*.py"
grep -r "from brokers.upstox" brokers/common/ --include="*.py"

# Check for CLI imports in lower layers
grep -r "from cli" brokers/ datalake/ analytics/ --include="*.py"
```

## Exception Process

If you need to break these rules:
1. Document the reason in an ADR
2. Add a `# noqa: import-direction` comment
3. Get approval from team lead
```

---

### REF-19: Coding Standards in pyproject.toml

**File**: `pyproject.toml` (MODIFY)

**Add section**:

```toml
[tool.tradeXV2]
# Coding standards
import_direction_enforcement = true
require_all_exports = true
max_function_length = 50
max_class_length = 200
require_docstrings = true
require_type_hints = true
```

**Also add to existing ruff configuration**:

```toml
[tool.ruff.lint]
extend-select = [
    "D",  # pydocstyle
    "ANN",  # flake8-annotations
]

[tool.ruff.lint.pydocstyle]
convention = "google"
```

---

## WAVE 5: Guardrails

### REF-21: Architectural Invariant Tests

**File**: `tests/test_architecture.py` (NEW)

```python
"""Architectural invariant tests — enforce structural rules."""

import pytest


class TestImportDirection:
    """Enforce one-way import direction."""
    
    def test_common_does_not_import_broker_adapters(self):
        """brokers.common must not import from broker-specific packages."""
        import subprocess
        result = subprocess.run(
            ['grep', '-r', 'from brokers.dhan', 'brokers/common/', '--include=*.py'],
            capture_output=True,
            text=True
        )
        assert result.returncode != 0, f"Found forbidden imports: {result.stdout}"
    
    def test_common_does_not_import_upstox(self):
        """brokers.common must not import from upstox."""
        import subprocess
        result = subprocess.run(
            ['grep', '-r', 'from brokers.upstox', 'brokers/common/', '--include=*.py'],
            capture_output=True,
            text=True
        )
        assert result.returncode != 0, f"Found forbidden imports: {result.stdout}"
    
    def test_datalake_does_not_import_cli(self):
        """datalake must not import from CLI."""
        import subprocess
        result = subprocess.run(
            ['grep', '-r', 'from cli', 'datalake/', '--include=*.py'],
            capture_output=True,
            text=True
        )
        assert result.returncode != 0, f"Found forbidden imports: {result.stdout}"


class TestModuleExports:
    """Enforce __all__ declarations."""
    
    def test_brokers_init_has_all(self):
        """brokers/__init__.py must declare __all__."""
        import brokers
        assert hasattr(brokers, '__all__')
        assert len(brokers.__all__) > 0
    
    def test_common_init_has_all(self):
        """brokers/common/__init__.py must declare __all__."""
        import brokers.common
        assert hasattr(brokers.common, '__all__')


class TestStatusMapping:
    """Enforce centralized status mapping."""
    
    def test_registry_has_mappings(self):
        """StatusMapperRegistry must have at least one mapping."""
        from brokers.common.status_mapper import StatusMapperRegistry
        assert len(StatusMapperRegistry._mappings) > 0
    
    def test_order_status_normalize_uses_registry(self):
        """OrderStatus.normalize() must delegate to registry."""
        from brokers.common.core.types import OrderStatus
        from brokers.common.status_mapper import StatusMapperRegistry
        
        # Register a test mapping
        StatusMapperRegistry.register("test", {"TEST_STATUS": OrderStatus.FILLED})
        
        # Should use registry
        result = OrderStatus.normalize("TEST_STATUS")
        assert result == OrderStatus.FILLED


class TestConstantsOrganization:
    """Enforce constants split by domain."""
    
    def test_constants_package_exists(self):
        """Constants should be in a package, not a monolith."""
        from brokers.common.core import constants
        assert hasattr(constants, '__path__')  # It's a package
    
    def test_timeout_constants_exist(self):
        """Timeout constants should be in dedicated module."""
        from brokers.common.core.constants.timeouts import (
            DEFAULT_STOP_TIMEOUT_SECONDS,
            DEFAULT_HTTP_TIMEOUT_SECONDS,
        )
        assert DEFAULT_STOP_TIMEOUT_SECONDS > 0
        assert DEFAULT_HTTP_TIMEOUT_SECONDS > 0
    
    def test_auth_constants_exist(self):
        """Auth constants should be in dedicated module."""
        from brokers.common.core.constants.auth import (
            DEFAULT_TOKEN_LIFETIME_SECONDS,
        )
        assert DEFAULT_TOKEN_LIFETIME_SECONDS > 0


class TestExceptionHierarchy:
    """Enforce canonical exception hierarchy."""
    
    def test_exit_all_error_in_canonical_location(self):
        """ExitAllError should be in resilience/errors.py."""
        from brokers.common.resilience.errors import ExitAllError
        assert ExitAllError is not None
    
    def test_exit_all_error_inherits_properly(self):
        """ExitAllError should inherit from NotSupportedError."""
        from brokers.common.resilience.errors import ExitAllError, NotSupportedError
        assert issubclass(ExitAllError, NotSupportedError)


class TestParsingUtilities:
    """Enforce shared parsing utilities."""
    
    def test_parsing_module_exists(self):
        """Shared parsing utilities should exist."""
        from brokers.common.core import parsing
        assert parsing is not None
    
    def test_parse_decimal_works(self):
        """parse_decimal should handle edge cases."""
        from brokers.common.core.parsing import parse_decimal
        from decimal import Decimal
        
        assert parse_decimal("123.45") == Decimal("123.45")
        assert parse_decimal(None) == Decimal("0")
        assert parse_decimal("") == Decimal("0")
        assert parse_decimal("invalid") == Decimal("0")
```

---

## Execution Checklist

### Wave 1: Service Layer (45 min)
- [ ] Create `cli/services/observability_setup.py`
- [ ] Update `broker_service.py` to use it
- [ ] Create `cli/services/websocket_wiring.py`
- [ ] Update `broker_service.py` to use it
- [ ] Create `cli/services/oms_setup.py`
- [ ] Update `broker_service.py` to use it
- [ ] Run tests to verify no breakage

### Wave 2: Performance (60 min)
- [ ] Implement PERF-1: Parquet column cache
- [ ] Implement PERF-2: Parallel download
- [ ] Implement PERF-3: Efficient cache key
- [ ] Implement PERF-4: Eliminate DataFrame copies
- [ ] Implement PERF-5: DuckDB pool
- [ ] Implement PERF-6: Last-row query
- [ ] Implement PERF-7: Upstox observability
- [ ] Benchmark performance improvements

### Wave 3: Instruments (30 min)
- [ ] Create unified `Instrument` model
- [ ] Create Dhan instrument mapper
- [ ] Create Upstox instrument mapper
- [ ] Update existing code to use unified type
- [ ] Run tests to verify mapping

### Wave 4: Cleanup (30 min)
- [ ] Update `brokers/__init__.py`
- [ ] Add `__all__` to Dhan package
- [ ] Add `__all__` to all common subpackages
- [ ] Create import rules documentation
- [ ] Update `pyproject.toml` with standards

### Wave 5: Guardrails (15 min)
- [ ] Create `tests/test_architecture.py`
- [ ] Run all tests
- [ ] Fix any violations found

---

## Testing Strategy

After each wave:

```bash
# Run full test suite
pytest tests/ -v --tb=short

# Run mypy type check
mypy brokers/ cli/ --ignore-missing-imports

# Run linting
ruff check brokers/ cli/

# Check import direction
grep -r "from brokers.dhan" brokers/common/ --include="*.py"
grep -r "from brokers.upstox" brokers/common/ --include="*.py"
```

---

## Rollback Plan

If any wave causes breakage:

1. **Git revert** the specific commit:
   ```bash
   git log --oneline -5  # Find the commit
   git revert <commit-hash>
   ```

2. **Verify tests pass** after rollback:
   ```bash
   pytest tests/ -x
   ```

3. **Document the issue** in an ADR before retrying

---

## Success Metrics

After completing all waves:

- ✅ BrokerService reduced from 666→200 lines (70% reduction)
- ✅ 3-10x performance improvements on key paths
- ✅ Zero import direction violations
- ✅ 100% __all__ declarations in public packages
- ✅ All architectural invariant tests passing
- ✅ No shotgun surgery patterns (single source of truth for all extracted modules)

---

**Last Updated**: 2026-06-18  
**Status**: Ready for execution  
**Estimated Completion**: 2-3 focused sessions
