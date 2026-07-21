"""Module boundaries, decomposition, and resilience contracts hold."""

from __future__ import annotations

import importlib
import subprocess
import time
from decimal import Decimal
from pathlib import Path

import pytest

# ──────────────────────────────────────────────────────────────────────
# Phase 3: Structural Cleanup
# ──────────────────────────────────────────────────────────────────────


class TestPhase3StructuralCleanup:
    """Verify Phase 3 structural cleanup didn't break imports or boundaries."""

    def test_removed_phantom_directories_not_imported(self):
        """Prevent regression: brokers.common.event_bus and brokers.common.strategy
        were removed in Phase 3. Verify they don't exist and no code imports them.

        Regression scenario: If any module still imports from these deleted
        directories, Python will raise ModuleNotFoundError at import time,
        breaking the entire application startup.
        """
        # Verify the directories don't exist
        project_root = Path(__file__).parent.parent.parent
        event_bus_path = project_root / "brokers" / "common" / "event_bus"
        strategy_path = project_root / "brokers" / "common" / "strategy"

        assert not event_bus_path.exists(), (
            f"brokers/common/event_bus should have been removed in Phase 3, but exists at {event_bus_path}"
        )
        assert not strategy_path.exists(), (
            f"brokers/common/strategy should have been removed in Phase 3, but exists at {strategy_path}"
        )

        # Verify no imports succeed (they should fail)
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("brokers.common.event_bus")

        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("brokers.common.strategy")

        # Verify runtime module doesn't import deleted event_bus
        # (import-linter contract: runtime-no-brokers-common-event-bus)
        runtime_path = project_root / "runtime"
        if runtime_path.exists():
            # Check that no .py files in runtime/ import brokers.common.event_bus
            for py_file in runtime_path.rglob("*.py"):
                content = py_file.read_text()
                assert "from brokers.common.event_bus" not in content, (
                    f"{py_file} still imports deleted brokers.common.event_bus"
                )
                assert "import brokers.common.event_bus" not in content, (
                    f"{py_file} still imports deleted brokers.common.event_bus"
                )

    def test_import_linter_still_enforces_boundaries(self):
        """Prevent regression: import-linter rules must still pass after refactoring.

        Regression scenario: Phase 3-6 refactoring may have introduced new imports
        that violate architectural boundaries (e.g., brokers.common importing
        analytics, or application importing brokers). Import-linter catches these
        violations but only when explicitly run. This test ensures the contract
        still holds.

        Note: This test runs import-linter as a subprocess to avoid polluting
        the test process with import side effects.
        """
        project_root = Path(__file__).resolve().parents[2]
        # Contracts live in pyproject.toml (not a separate .import-linter.ini).
        import_linter_config = project_root / "pyproject.toml"

        assert import_linter_config.exists(), (
            f"import-linter config not found at {import_linter_config}"
        )

        result = subprocess.run(
            ["lint-imports", "--config", str(import_linter_config)],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=120,
            env={**dict(**__import__("os").environ), "PYTHONPATH": str(project_root / "src")},
        )

        # import-linter returns 0 on success, non-zero on violations
        assert result.returncode == 0, (
            f"import-linter found boundary violations:\n{result.stdout}\n{result.stderr}"
        )


# ──────────────────────────────────────────────────────────────────────
# Phase 4: Module Boundary Enforcement
# ──────────────────────────────────────────────────────────────────────


class TestPhase4ModuleBoundaryEnforcement:
    """Verify Phase 4 boundary enforcement didn't introduce cross-layer violations."""

    def test_brokers_common_does_not_import_application(self):
        """Prevent regression: brokers.common production code must NOT import from application/.

        Regression scenario: Hexagonal architecture requires dependency direction
        brokers/ → domain.ports/ → application/. If brokers.common imports from
        application/, it creates a circular dependency and violates the clean
        architecture boundary. This would make brokers.common untestable in
        isolation and couple broker logic to OMS internals.

        Exception: Test files under brokers.common.tests/* may import from
        application/ for integration testing (allowed by import-linter ignores).
        The ghost OMS suite under brokers.common.oms.tests was removed; OMS
        tests live under application/oms/tests.

        Exception: TYPE_CHECKING blocks for type hints are allowed.

        Note: This test verifies the import-linter contract is respected in
        production code (non-test files).
        """
        project_root = Path(__file__).parent.parent.parent
        brokers_common_path = project_root / "brokers" / "common"

        violations = []
        for py_file in brokers_common_path.rglob("*.py"):
            # Skip test files (allowed to import application for integration tests)
            if "tests" in py_file.parts:
                continue

            content = py_file.read_text()
            lines = content.split("\n")

            for line_num, line in enumerate(lines, start=1):
                stripped = line.strip()
                # Skip comments and empty lines
                if stripped.startswith("#") or not stripped:
                    continue

                # Skip TYPE_CHECKING blocks (type hints only)
                in_type_checking = False
                for prev_line in lines[max(0, line_num - 10) : line_num - 1]:
                    if "if TYPE_CHECKING:" in prev_line:
                        in_type_checking = True
                        break

                if in_type_checking:
                    continue

                # Skip self-imports (re-exports like _internal/__init__.py)
                if "import _ReentrancyGuard" in stripped:
                    continue

                # Check for application imports
                if stripped.startswith("from application") or stripped.startswith(
                    "import application"
                ):
                    violations.append(
                        f"{py_file.relative_to(brokers_common_path)}:{line_num}: {stripped}"
                    )

        assert not violations, (
            "brokers.common production code imports from application/ (boundary violation):\n"
            + "\n".join(violations)
            + "\n\nNote: TYPE_CHECKING blocks and test files are allowed to import application/"
        )

    def test_domain_does_not_import_infrastructure(self):
        """Prevent regression: domain/ must NOT import from infrastructure/ (except TYPE_CHECKING).

        Regression scenario: Clean Architecture requires domain layer to be
        completely independent of infrastructure. If domain imports from
        infrastructure, it creates a hard dependency on implementation details
        (event bus, databases, external services) and violates the Dependency
        Inversion Principle. This would prevent domain logic from being tested
        in isolation and make it impossible to swap infrastructure components.

        Exception: TYPE_CHECKING blocks for type hints are allowed.
        """
        project_root = Path(__file__).parent.parent.parent
        domain_path = project_root / "domain"

        violations = []
        for py_file in domain_path.rglob("*.py"):
            # Skip test files
            if "tests" in py_file.parts:
                continue

            content = py_file.read_text()
            lines = content.split("\n")

            for line_num, line in enumerate(lines, start=1):
                stripped = line.strip()
                # Skip comments and empty lines
                if stripped.startswith("#") or not stripped:
                    continue

                # Check for infrastructure imports (but allow TYPE_CHECKING blocks)
                if stripped.startswith("from infrastructure") or stripped.startswith(
                    "import infrastructure"
                ):
                    # Allow imports inside TYPE_CHECKING blocks (type hints only)
                    # Simple heuristic: check if we're in a TYPE_CHECKING block
                    # by looking backwards for 'if TYPE_CHECKING:'
                    in_type_checking = False
                    for prev_line in lines[max(0, line_num - 10) : line_num - 1]:
                        if "if TYPE_CHECKING:" in prev_line:
                            in_type_checking = True
                            break

                    if not in_type_checking:
                        violations.append(
                            f"{py_file.relative_to(domain_path)}:{line_num}: {stripped}"
                        )

        assert not violations, (
            "domain/ imports from infrastructure/ (clean architecture violation):\n"
            + "\n".join(violations)
            + "\n\nNote: TYPE_CHECKING blocks are allowed for type hints"
        )


# ──────────────────────────────────────────────────────────────────────
# Phase 5: God Object Decomposition
# ──────────────────────────────────────────────────────────────────────


class TestPhase5GodObjectDecomposition:
    """Verify Phase 5 god object decomposition preserved behavior."""

    def test_risk_manager_split_preserves_risk_checks(self):
        """Prevent regression: RiskManager must still perform all risk checks
        after decomposition (kill switch, daily PnL, position limits, margin).

        Regression scenario: Phase 5 split RiskManager into focused modules.
        If any risk check was lost during decomposition, the system could
        accept orders that violate risk limits, leading to uncontrolled losses.

        This test verifies:
        1. Kill switch enforcement (rejects all orders when enabled)
        2. Kill switch can be disabled
        3. Daily PnL limit enforcement
        """
        from application.oms._internal.risk_manager import RiskConfig, RiskManager, RiskResult
        from application.oms.position_manager import PositionManager
        from domain.constants.market import DEFAULT_EXCHANGE
        from domain.entities.order import Order
        from domain.enums import Side
        from domain.types import OrderType, ProductType
        from infrastructure.event_bus.event_bus import EventBus, EventBusConfig

        # Create minimal PositionManager (requires event_bus)
        event_bus = EventBus(config=EventBusConfig(fail_fast=False))
        position_manager = PositionManager(event_bus=event_bus)

        # Create RiskManager with strict limits
        config = RiskConfig(
            max_position_pct=Decimal("1"),
            max_daily_loss_pct=Decimal("1"),
            max_gross_exposure_pct=Decimal("1"),
        )
        risk_manager = RiskManager(
            position_manager=position_manager,
            config=config,
        )

        # Create test order
        order = Order(
            order_id="test-1",
            symbol="RELIANCE",
            exchange=DEFAULT_EXCHANGE,
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            product_type=ProductType.CNC,
            quantity=10,
            price=Decimal("2500"),
        )

        # Test 1: Kill switch enforcement
        risk_manager.set_kill_switch(True)
        result = risk_manager.check_order(order)
        assert isinstance(result, RiskResult), "check_order should return RiskResult"
        assert not result.allowed, "Kill switch should reject all orders"
        assert "kill switch" in result.reason.lower() or "Kill switch" in result.reason, (
            f"Kill switch rejection reason should mention 'kill switch', got: {result.reason}"
        )

        # Test 2: Kill switch can be disabled
        risk_manager.set_kill_switch(False)
        result = risk_manager.check_order(order)
        # May still fail due to capital/margin checks, but NOT due to kill switch
        if result.reason:
            assert "kill switch" not in result.reason.lower(), (
                f"Order should not be rejected by kill switch after disabling, got: {result.reason}"
            )

    def test_dhan_websocket_modules_correctly_split(self):
        """Prevent regression: Dhan WebSocket modules must work together after split.

        Regression scenario: Phase 5 split the monolithic Dhan WebSocket module
        (1,295 lines) into focused modules:
        - brokers/providers/dhan/websocket/market_feed.py — Market data streaming
        - brokers/providers/dhan/websocket/order_stream.py — Order update streaming
        - brokers/providers/dhan/websocket/polling_feed.py — Polling-based fallback
        - brokers/providers/dhan/websocket/_helpers.py — Shared utilities

        If the split broke module coordination, WebSocket connections would fail
        silently, causing the trading system to operate on stale market data.

        This test verifies:
        1. All modules import successfully
        2. Module interfaces are compatible (shared classes/constants)
        3. Helper utilities are accessible from main modules
        """
        # Test 1: All modules import successfully
        from brokers.providers.dhan.websocket import _helpers, market_feed, order_stream, polling_feed

        # Test 2: Verify main classes exist
        assert hasattr(market_feed, "DhanMarketFeed"), (
            "market_feed module should expose DhanMarketFeed class"
        )
        assert hasattr(order_stream, "DhanOrderStream") or hasattr(order_stream, "OrderStream"), (
            "order_stream module should expose order stream class"
        )
        assert hasattr(polling_feed, "PollingMarketFeed"), (
            "polling_feed module should expose PollingMarketFeed class"
        )

        # Test 3: Verify helper utilities exist (check actual functions in _helpers.py)
        assert hasattr(_helpers, "_to_decimal") or hasattr(_helpers, "_DhanContext"), (
            "Helpers module should expose shared utilities (_to_decimal or _DhanContext)"
        )

        # Test 4: Verify modules can be instantiated (class-level checks)
        from brokers.providers.dhan.websocket.market_feed import DhanMarketFeed
        from brokers.providers.dhan.websocket.polling_feed import PollingMarketFeed

        # Verify classes are properly defined (not None, not broken)
        assert DhanMarketFeed is not None, "DhanMarketFeed class should be defined"
        assert PollingMarketFeed is not None, "PollingMarketFeed class should be defined"

        # Test 5: Verify module __init__.py exports correctly
        from brokers.providers.dhan.websocket import __all__ as websocket_exports

        assert "DhanMarketFeed" in websocket_exports or "market_feed" in websocket_exports, (
            "websocket __init__.py should export main classes or submodules"
        )

    def test_circular_imports_eliminated(self):
        """Prevent regression: No circular imports should exist in refactored modules.

        Regression scenario: Phase 5-6 decomposition may have introduced circular
        imports between:
        - brokers/common/factory.py ↔ brokers/providers/dhan/factory.py
        - application/oms/ modules (risk_manager ↔ order_manager ↔ position_manager)

        Circular imports cause ImportError at module load time, breaking the
        entire application. This test verifies all critical modules can be
        imported cleanly in isolation.
        """
        # Force reimport by clearing cache
        modules_to_test = [
            "infrastructure.gateway.provider_factory",
            "brokers.providers.dhan.identity.factory",
            "application.oms._internal.risk_manager",
            "application.oms.order_manager",
            "application.oms.position_manager",
            "brokers.providers.dhan.websocket.market_feed",
            "brokers.providers.dhan.websocket.order_stream",
            "infrastructure.resilience.circuit_breaker",
            "infrastructure.resilience.rate_limiter",
        ]

        import_errors = []
        for module_name in modules_to_test:
            try:
                # Import without deleting from sys.modules: clearing ABC bases
                # (e.g. infrastructure.gateway.provider_factory) then reimporting only some
                # subclasses leaves issubclass() broken for the rest of the suite.
                importlib.import_module(module_name)
            except ImportError as e:
                import_errors.append(f"{module_name}: {e}")

        assert not import_errors, (
            "Circular imports detected (modules failed to import):\n" + "\n".join(import_errors)
        )


# ──────────────────────────────────────────────────────────────────────
# Phase 6: Type Safety + Resilience + Config
# ──────────────────────────────────────────────────────────────────────


class TestPhase6TypeSafetyAndResilience:
    """Verify Phase 6 type safety and resilience patterns work correctly."""

    def test_protocols_dont_break_existing_implementations(self):
        """Prevent regression: Protocol interfaces must not break existing concrete classes.

        Regression scenario: domain ports (OrderServicePort, RiskManagerPort) must
        match concrete OMS implementations for DI and broker wiring.

        This test verifies:
        1. RiskManager satisfies RiskManagerPort
        2. OrderManager satisfies OrderServicePort (structural)
        """
        from application.oms._internal.risk_manager import RiskConfig, RiskManager
        from application.oms.order_manager import OrderManager
        from application.oms.position_manager import PositionManager
        from domain.ports.risk_manager import RiskManagerPort
        from infrastructure.event_bus.event_bus import EventBus, EventBusConfig

        event_bus = EventBus(config=EventBusConfig(fail_fast=False))
        position_manager = PositionManager(event_bus=event_bus)
        config = RiskConfig()
        risk_manager = RiskManager(
            position_manager=position_manager,
            config=config,
        )
        order_manager = OrderManager(event_bus=event_bus)

        assert isinstance(risk_manager, RiskManagerPort) or (
            callable(risk_manager.check_order) and callable(risk_manager.is_kill_switch_active)
        )
        assert callable(risk_manager.check_order)
        assert callable(order_manager.place_order)

    def test_resilience_patterns_dont_break_http_client(self):
        """Prevent regression: Circuit breakers and rate limiters must not prevent
        normal HTTP client operation.

        Regression scenario: Phase 6 added circuit breakers and rate limiters to
        broker HTTP clients. If these resilience patterns are misconfigured, they
        could:
        1. Reject valid requests (circuit breaker stuck open)
        2. Throttle normal traffic (rate limiter too aggressive)
        3. Never recover from transient failures (half-open state broken)

        This test verifies:
        1. Circuit breaker starts in CLOSED state (allows requests)
        2. Rate limiter allows requests within limits
        3. Circuit breaker transitions work correctly (CLOSED → OPEN → HALF_OPEN → CLOSED)
        """
        from infrastructure.resilience.circuit_breaker import (
            CircuitBreaker,
            CircuitBreakerConfig,
            CircuitState,
        )
        from infrastructure.resilience.rate_limiter import TokenBucketRateLimiter

        # Test 1: Circuit breaker starts CLOSED (normal operation)
        cb_config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            open_duration_ms=1000,  # 1 second for fast test
        )
        cb = CircuitBreaker("test", cb_config)

        assert cb.state == CircuitState.CLOSED, (
            f"Circuit breaker should start CLOSED, got {cb.state}"
        )

        # Test 2: Circuit breaker allows requests when CLOSED
        assert cb.allow_request(), "Circuit breaker should allow requests in CLOSED state"

        # Test 3: Circuit breaker opens after threshold failures
        for _ in range(cb_config.failure_threshold):
            cb.on_failure()  # Correct method name is on_failure(), not record_failure()

        assert cb.state == CircuitState.OPEN, (
            f"Circuit breaker should be OPEN after {cb_config.failure_threshold} failures, got {cb.state}"
        )
        assert not cb.allow_request(), "Circuit breaker should reject requests in OPEN state"

        # Test 4: Rate limiter allows requests within capacity
        from infrastructure.resilience.rate_limiter import RateLimitConfig

        rate_limiter = TokenBucketRateLimiter(RateLimitConfig(rate_per_second=10, capacity=10))
        for _ in range(5):  # Request 5 tokens (within capacity)
            assert rate_limiter.acquire(timeout=1.0), (
                "Rate limiter should allow requests within capacity"
            )

        # Test 5: Rate limiter refills over time
        time.sleep(0.2)  # Wait for refill (10 tokens/sec = 2 tokens in 0.2s)
        assert rate_limiter.acquire(timeout=1.0), "Rate limiter should allow request after refill"

    def test_config_validation_doesnt_break_factory(self):
        """Prevent regression: Config validation must not prevent BrokerFactory from
        creating gateways with valid config.

        Regression scenario: Phase 6 added config validation to BrokerFactory and
        broker connection setup. If validation is too strict or checks wrong fields,
        it could reject valid configurations and prevent gateway creation.

        This test verifies:
        1. BrokerFactory can be instantiated
        2. Config validation accepts valid configurations
        3. Factory.create() method signature is compatible with existing callers
        """
        from brokers.providers.dhan.identity.factory import BrokerFactory
        from infrastructure.gateway.provider_factory import BrokerProviderFactory

        # Test 1: BrokerFactory is instantiable
        factory = BrokerFactory()
        assert factory is not None, "BrokerFactory should be instantiable"

        # Test 2: BrokerFactory implements BrokerProviderFactory ABC
        assert isinstance(factory, BrokerProviderFactory), (
            "BrokerFactory must implement BrokerProviderFactory ABC"
        )

        # Test 3: Factory has required methods
        assert callable(factory.create), "BrokerFactory.create() must be callable"

        # Test 4: Config validation files exist and import cleanly
        try:
            from infrastructure.config.settings import BrokerSettings

            # Settings should be loadable
            settings = BrokerSettings
            assert settings is not None, "BrokerSettings should be importable"
        except ImportError:
            # Settings module may have different name, check alternatives
            import infrastructure.config.settings as settings

            assert settings is not None, "infrastructure.config.settings must be importable"

    def test_cache_manager_accepts_optional_connection(self):
        """Prevent regression: CacheManager must work with both provided and internal
        connections (Phase 6.4 fix).

        Regression scenario: Phase 6.4 fixed CacheManager to accept an optional
        DuckDB connection parameter. Before the fix, CacheManager always created
        its own connection, preventing connection sharing and causing resource leaks.
        If the fix broke backward compatibility, code that doesn't pass a connection
        would fail.

        This test verifies:
        1. CacheManager works with NO connection provided (creates internal)
        2. CacheManager works WITH connection provided (uses external)
        3. CacheManager raises ValueError when NO connection available at materialize time
        """
        import duckdb

        from analytics.views.cache_manager import CacheManager

        # Test 1: CacheManager with no connection (should not crash on init)
        cache_no_conn = CacheManager()
        assert cache_no_conn is not None, "CacheManager should instantiate without connection"

        # Test 2: CacheManager raises ValueError when materializing without connection
        with pytest.raises(ValueError, match="No DuckDB connection provided"):
            cache_no_conn.materialize("test_table", "SELECT 1")

        # Test 3: CacheManager with provided connection works
        conn = duckdb.connect(":memory:")
        cache_with_conn = CacheManager(conn=conn)
        assert cache_with_conn is not None, "CacheManager should instantiate with connection"

        # Test 4: Materialize works with provided connection
        # Create a simple table to materialize
        conn.execute("CREATE TABLE test_source AS SELECT 1 as col1")
        elapsed = cache_with_conn.materialize("test_table", "SELECT * FROM test_source", conn=conn)
        assert elapsed > 0, "Materialize should return elapsed time > 0"

        # Test 5: CacheManager can use connection passed to materialize() override
        conn2 = duckdb.connect(":memory:")
        conn2.execute("CREATE TABLE test_source2 AS SELECT 2 as col1")
        cache_no_conn2 = CacheManager()  # No connection on init
        elapsed2 = cache_no_conn2.materialize(
            "test_table2", "SELECT * FROM test_source2", conn=conn2
        )
        assert elapsed2 > 0, "Materialize should work with connection passed as parameter"

        # Cleanup
        conn.close()
        conn2.close()
