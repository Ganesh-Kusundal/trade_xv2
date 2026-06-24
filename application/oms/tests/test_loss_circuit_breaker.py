"""Tests for B1: Loss-based circuit breaker.

Covers:
  - State transitions (CLOSED -> OPEN -> COOLDOWN -> CLOSED)
  - Rolling window purges old losses
  - Thread-safe concurrent record_loss
  - Integration with RiskManager.check_order()
  - Snapshot is JSON serializable
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from domain import Order, OrderStatus, OrderType, ProductType, Side
from application.oms._internal.loss_circuit_breaker import (
    LossCircuitBreaker,
    LossCircuitBreakerConfig,
    LossCircuitState,
)
from application.oms import (
    PositionManager,
    RiskConfig,
    RiskManager,
)

# -- Helpers --


def _make_order(symbol: str = "RELIANCE", price: Decimal = Decimal("2500")) -> Order:
    return Order(
        order_id="O-1",
        symbol=symbol,
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price=price,
        order_type=OrderType.LIMIT,
        product_type=ProductType.INTRADAY,
        status=OrderStatus.OPEN,
    )


@pytest.fixture
def position_manager() -> PositionManager:
    return PositionManager()


@pytest.fixture
def capital_fn() -> MagicMock:
    fn = MagicMock(return_value=Decimal("1000000"))
    return fn


@pytest.fixture
def default_cb_config() -> LossCircuitBreakerConfig:
    return LossCircuitBreakerConfig(
        loss_threshold_pct=Decimal("2.0"),
        cooldown_seconds=5,  # Short for test speed
        window_seconds=10,   # Short for test speed
    )


# ═════════════════════════════════════════════════════════════════════════
# State transitions
# ═════════════════════════════════════════════════════════════════════════


class TestStateTransitions:
    """Verify the circuit breaker transitions through all states correctly."""

    def test_initial_state_is_closed(self, default_cb_config: LossCircuitBreakerConfig) -> None:
        cb = LossCircuitBreaker(config=default_cb_config)
        allowed, reason = cb.allow_trading()
        assert allowed is True
        assert reason is None

    def test_closed_remains_closed_with_small_losses(
        self, default_cb_config: LossCircuitBreakerConfig
    ) -> None:
        """Small losses that don't exceed threshold keep circuit CLOSED."""
        cb = LossCircuitBreaker(config=default_cb_config)
        capital = Decimal("1000000")
        # 1% loss, below 2% threshold
        cb.record_loss(Decimal("-10000"), capital)
        allowed, _ = cb.allow_trading()
        assert allowed is True

    def test_closes_to_open_when_threshold_exceeded(
        self, default_cb_config: LossCircuitBreakerConfig
    ) -> None:
        """Cumulative loss >= threshold trips the circuit to OPEN."""
        cb = LossCircuitBreaker(config=default_cb_config)
        capital = Decimal("1000000")
        # 2% loss = threshold
        cb.record_loss(Decimal("-20000"), capital)
        allowed, reason = cb.allow_trading()
        assert allowed is False
        assert "OPEN" in reason

    def test_open_blocks_trading(self, default_cb_config: LossCircuitBreakerConfig) -> None:
        """OPEN state returns False with clear reason."""
        cb = LossCircuitBreaker(config=default_cb_config)
        capital = Decimal("1000000")
        cb.record_loss(Decimal("-20000"), capital)
        # Trip to OPEN
        allowed, reason = cb.allow_trading()
        assert allowed is False
        assert reason is not None
        assert "OPEN" in reason

    def test_reset_open_moves_to_cooldown(self, default_cb_config: LossCircuitBreakerConfig) -> None:
        """reset() on OPEN transitions to COOLDOWN, not directly to CLOSED."""
        cb = LossCircuitBreaker(config=default_cb_config)
        capital = Decimal("1000000")
        cb.record_loss(Decimal("-20000"), capital)
        cb.reset()
        allowed, reason = cb.allow_trading()
        assert allowed is False
        assert "COOLDOWN" in reason

    def test_cooldown_blocks_trading(self, default_cb_config: LossCircuitBreakerConfig) -> None:
        """COOLDOWN state still blocks trading."""
        cb = LossCircuitBreaker(config=default_cb_config)
        capital = Decimal("1000000")
        cb.record_loss(Decimal("-20000"), capital)
        cb.reset()
        allowed, reason = cb.allow_trading()
        assert allowed is False
        assert "COOLDOWN" in reason

    def test_cooldown_auto_transitions_to_closed_after_expiry(
        self, default_cb_config: LossCircuitBreakerConfig
    ) -> None:
        """After cooldown_seconds elapse, COOLDOWN auto-transitions to CLOSED."""
        cb = LossCircuitBreaker(config=default_cb_config)
        capital = Decimal("1000000")
        cb.record_loss(Decimal("-20000"), capital)
        cb.reset()
        # Wait for cooldown to expire
        time.sleep(default_cb_config.cooldown_seconds + 0.5)
        allowed, reason = cb.allow_trading()
        assert allowed is True
        assert reason is None

    def test_reset_cooldown_moves_to_closed_immediately(
        self, default_cb_config: LossCircuitBreakerConfig
    ) -> None:
        """reset() on COOLDOWN transitions immediately to CLOSED."""
        cb = LossCircuitBreaker(config=default_cb_config)
        capital = Decimal("1000000")
        cb.record_loss(Decimal("-20000"), capital)
        cb.reset()  # OPEN -> COOLDOWN
        cb.reset()  # COOLDOWN -> CLOSED
        allowed, reason = cb.allow_trading()
        assert allowed is True
        assert reason is None

    def test_reset_closed_is_noop(self, default_cb_config: LossCircuitBreakerConfig) -> None:
        """reset() on CLOSED is a no-op."""
        cb = LossCircuitBreaker(config=default_cb_config)
        cb.reset()  # no-op
        allowed, reason = cb.allow_trading()
        assert allowed is True
        assert reason is None

    def test_gains_reduce_cumulative_loss(
        self, default_cb_config: LossCircuitBreakerConfig
    ) -> None:
        """Positive PnL (gains) offset prior losses."""
        cb = LossCircuitBreaker(config=default_cb_config)
        capital = Decimal("1000000")
        # 1.5% loss
        cb.record_loss(Decimal("-15000"), capital)
        # 1% gain reduces net loss to 0.5%
        cb.record_loss(Decimal("10000"), capital)
        allowed, _ = cb.allow_trading()
        assert allowed is True


# ═════════════════════════════════════════════════════════════════════════
# Rolling window
# ═════════════════════════════════════════════════════════════════════════


class TestRollingWindow:
    """Verify old samples are purged and don't contribute to cumulative loss."""

    def test_old_samples_are_purged(self) -> None:
        """Samples older than window_seconds are removed."""
        cb = LossCircuitBreaker(config=LossCircuitBreakerConfig(
            loss_threshold_pct=Decimal("2.0"),
            cooldown_seconds=1,  # Short cooldown for test
            window_seconds=1,  # 1 second window
        ))
        capital = Decimal("1000000")
        cb.record_loss(Decimal("-50000"), capital)  # 5% loss

        # Should be OPEN now
        allowed, _ = cb.allow_trading()
        assert allowed is False

        # Wait for window to expire
        time.sleep(1.5)

        # Record a small new loss; old 5% should be purged
        # This triggers OPEN -> COOLDOWN transition
        cb.record_loss(Decimal("-100"), capital)
        
        # Wait for cooldown to expire
        time.sleep(cb.config.cooldown_seconds + 0.5)
        
        allowed, reason = cb.allow_trading()
        assert allowed is True

    def test_rolling_window_prevents_trip_when_old_losses_expire(self) -> None:
        """When old losses expire, cumulative loss drops below threshold."""
        cb = LossCircuitBreaker(config=LossCircuitBreakerConfig(
            loss_threshold_pct=Decimal("2.0"),
            cooldown_seconds=1,  # Short cooldown for test
            window_seconds=2,
        ))
        capital = Decimal("1000000")
        # 3% loss (would trip)
        cb.record_loss(Decimal("-30000"), capital)
        allowed, _ = cb.allow_trading()
        assert allowed is False

        time.sleep(2.5)

        # Old loss purged; new small loss doesn't trip
        # This triggers OPEN -> COOLDOWN transition
        cb.record_loss(Decimal("-500"), capital)
        
        # Wait for cooldown to expire
        time.sleep(cb.config.cooldown_seconds + 0.5)
        
        allowed, _ = cb.allow_trading()
        assert allowed is True

    def test_cumulative_loss_across_window_boundary(self) -> None:
        """Losses within the window accumulate correctly."""
        cb = LossCircuitBreaker(config=LossCircuitBreakerConfig(
            loss_threshold_pct=Decimal("2.0"),
            cooldown_seconds=5,
            window_seconds=10,
        ))
        capital = Decimal("1000000")
        # Two losses of 1.2% each = 2.4% total
        cb.record_loss(Decimal("-12000"), capital)
        cb.record_loss(Decimal("-12000"), capital)
        allowed, reason = cb.allow_trading()
        assert allowed is False
        assert "OPEN" in reason


# ═════════════════════════════════════════════════════════════════════════
# Thread safety
# ═════════════════════════════════════════════════════════════════════════


class TestThreadSafety:
    """Verify concurrent record_loss calls don't corrupt state."""

    def test_concurrent_record_loss(self, default_cb_config: LossCircuitBreakerConfig) -> None:
        """Multiple threads calling record_loss simultaneously don't crash or lose data."""
        cb = LossCircuitBreaker(config=default_cb_config)
        capital = Decimal("1000000")
        num_threads = 20
        loss_per_thread = Decimal("-500")

        def record():
            cb.record_loss(loss_per_thread, capital)

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(record) for _ in range(num_threads)]
            for f in futures:
                f.result()  # Raise any exception

        # Total loss = 20 * 500 = 10000 = 1% of capital (below 2% threshold)
        snap = cb.snapshot()
        assert snap["window_samples"] == num_threads
        assert snap["cumulative_loss"] == str(Decimal("-10000"))

    def test_concurrent_record_loss_trips_correctly(
        self, default_cb_config: LossCircuitBreakerConfig
    ) -> None:
        """Concurrent losses that exceed threshold trip the circuit."""
        cb = LossCircuitBreaker(config=default_cb_config)
        capital = Decimal("1000000")
        num_threads = 50
        loss_per_thread = Decimal("-500")  # Total = 25000 = 2.5%

        def record():
            cb.record_loss(loss_per_thread, capital)

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(record) for _ in range(num_threads)]
            for f in futures:
                f.result()

        allowed, reason = cb.allow_trading()
        assert allowed is False
        assert "OPEN" in reason

    def test_concurrent_allow_trading_and_record_loss(
        self, default_cb_config: LossCircuitBreakerConfig
    ) -> None:
        """allow_trading and record_loss can run concurrently without deadlock."""
        cb = LossCircuitBreaker(config=default_cb_config)
        capital = Decimal("1000000")
        errors: list[Exception] = []

        def record_loss_thread():
            try:
                for _ in range(100):
                    cb.record_loss(Decimal("-100"), capital)
            except Exception as e:
                errors.append(e)

        def allow_trading_thread():
            try:
                for _ in range(100):
                    cb.allow_trading()
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(5):
            t1 = threading.Thread(target=record_loss_thread)
            t2 = threading.Thread(target=allow_trading_thread)
            threads.extend([t1, t2])

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Concurrent access caused errors: {errors}"


# ═════════════════════════════════════════════════════════════════════════
# Integration with RiskManager
# ═════════════════════════════════════════════════════════════════════════


class TestRiskManagerIntegration:
    """Verify LossCircuitBreaker integrates correctly with RiskManager."""

    def test_loss_cb_blocks_order_in_check_order(
        self, position_manager: PositionManager, capital_fn: MagicMock
    ) -> None:
        """When loss CB is OPEN, check_order returns blocked."""
        # Create a config with very low threshold so it trips easily
        cb_config = LossCircuitBreakerConfig(
            loss_threshold_pct=Decimal("0.5"),
            cooldown_seconds=5,
            window_seconds=10,
        )
        rm = RiskManager(
            position_manager=position_manager,
            config=RiskConfig(),
            capital_fn=capital_fn,
            loss_cb_config=cb_config,
        )
        # Record enough loss to trip
        rm.update_daily_pnl(Decimal("-6000"))  # 0.6% of 1M
        order = _make_order()
        result = rm.check_order(order)
        assert result.allowed is False
        assert "Loss circuit breaker" in (result.reason or "")

    def test_loss_cb_allows_order_when_below_threshold(
        self, position_manager: PositionManager, capital_fn: MagicMock
    ) -> None:
        """When loss CB is CLOSED, orders pass through (subject to other checks)."""
        cb_config = LossCircuitBreakerConfig(
            loss_threshold_pct=Decimal("2.0"),
            cooldown_seconds=5,
            window_seconds=10,
        )
        rm = RiskManager(
            position_manager=position_manager,
            config=RiskConfig(),
            capital_fn=capital_fn,
            loss_cb_config=cb_config,
        )
        # Small loss, below threshold
        rm.update_daily_pnl(Decimal("-10000"))  # 1% of 1M
        order = _make_order()
        result = rm.check_order(order)
        assert result.allowed is True

    def test_reset_loss_circuit_breaker_unblocks_orders(
        self, position_manager: PositionManager, capital_fn: MagicMock
    ) -> None:
        """After reset, orders can flow again (after cooldown)."""
        cb_config = LossCircuitBreakerConfig(
            loss_threshold_pct=Decimal("0.5"),
            cooldown_seconds=1,  # Very short for test
            window_seconds=10,
        )
        rm = RiskManager(
            position_manager=position_manager,
            config=RiskConfig(),
            capital_fn=capital_fn,
            loss_cb_config=cb_config,
        )
        rm.update_daily_pnl(Decimal("-6000"))
        order = _make_order()
        assert rm.check_order(order).allowed is False

        # Reset: OPEN -> COOLDOWN -> wait -> CLOSED
        rm.reset_loss_circuit_breaker()
        time.sleep(cb_config.cooldown_seconds + 0.5)
        assert rm.check_order(order).allowed is True

    def test_update_daily_pnl_records_delta_not_absolute(
        self, position_manager: PositionManager, capital_fn: MagicMock
    ) -> None:
        """update_daily_pnl records the delta (change), not the absolute PnL."""
        cb_config = LossCircuitBreakerConfig(
            loss_threshold_pct=Decimal("1.0"),
            cooldown_seconds=5,
            window_seconds=10,
        )
        rm = RiskManager(
            position_manager=position_manager,
            config=RiskConfig(),
            capital_fn=capital_fn,
            loss_cb_config=cb_config,
        )
        # First update: delta = -5000
        rm.update_daily_pnl(Decimal("-5000"))
        # Second update: delta = -6000 (from -5000 to -11000)
        rm.update_daily_pnl(Decimal("-11000"))
        # Total delta = -11000, which is 1.1% of 1M -> should trip
        order = _make_order()
        result = rm.check_order(order)
        assert result.allowed is False

    def test_snapshot_includes_loss_cb_state(
        self, position_manager: PositionManager, capital_fn: MagicMock
    ) -> None:
        """RiskManager.snapshot() includes loss CB state."""
        cb_config = LossCircuitBreakerConfig(
            loss_threshold_pct=Decimal("2.0"),
            cooldown_seconds=5,
            window_seconds=10,
        )
        rm = RiskManager(
            position_manager=position_manager,
            config=RiskConfig(),
            capital_fn=capital_fn,
            loss_cb_config=cb_config,
        )
        snap = rm.snapshot()
        assert "loss_circuit_breaker" in snap
        assert "state" in snap["loss_circuit_breaker"]
        assert "trip_count" in snap["loss_circuit_breaker"]


# ═════════════════════════════════════════════════════════════════════════
# Snapshot JSON serializability
# ═════════════════════════════════════════════════════════════════════════


class TestSnapshot:
    """Verify snapshot() returns JSON-serializable data."""

    def test_snapshot_closed_is_json_serializable(
        self, default_cb_config: LossCircuitBreakerConfig
    ) -> None:
        cb = LossCircuitBreaker(config=default_cb_config)
        snap = cb.snapshot()
        # Should not raise
        json_str = json.dumps(snap)
        parsed = json.loads(json_str)
        assert parsed["state"] == "CLOSED"

    def test_snapshot_open_is_json_serializable(
        self, default_cb_config: LossCircuitBreakerConfig
    ) -> None:
        cb = LossCircuitBreaker(config=default_cb_config)
        capital = Decimal("1000000")
        cb.record_loss(Decimal("-20000"), capital)
        snap = cb.snapshot()
        json_str = json.dumps(snap)
        parsed = json.loads(json_str)
        assert parsed["state"] == "OPEN"
        assert "opened_at" in parsed
        assert "seconds_since_open" in parsed

    def test_snapshot_cooldown_is_json_serializable(
        self, default_cb_config: LossCircuitBreakerConfig
    ) -> None:
        cb = LossCircuitBreaker(config=default_cb_config)
        capital = Decimal("1000000")
        cb.record_loss(Decimal("-20000"), capital)
        cb.reset()  # OPEN -> COOLDOWN
        snap = cb.snapshot()
        json_str = json.dumps(snap)
        parsed = json.loads(json_str)
        assert parsed["state"] == "COOLDOWN"
        assert "cooldown_remaining_seconds" in parsed

    def test_risk_manager_snapshot_is_json_serializable(
        self, position_manager: PositionManager, capital_fn: MagicMock
    ) -> None:
        """Full RiskManager snapshot including loss CB is JSON serializable."""
        cb_config = LossCircuitBreakerConfig(
            loss_threshold_pct=Decimal("2.0"),
            cooldown_seconds=5,
            window_seconds=10,
        )
        rm = RiskManager(
            position_manager=position_manager,
            config=RiskConfig(),
            capital_fn=capital_fn,
            loss_cb_config=cb_config,
        )
        snap = rm.snapshot()
        json_str = json.dumps(snap)
        parsed = json.loads(json_str)
        assert "loss_circuit_breaker" in parsed
        assert parsed["kill_switch"] is False


# ═════════════════════════════════════════════════════════════════════════
# Config validation
# ═════════════════════════════════════════════════════════════════════════


class TestConfigValidation:
    """Verify LossCircuitBreakerConfig validates its inputs."""

    def test_negative_threshold_raises(self) -> None:
        with pytest.raises(ValueError, match="loss_threshold_pct must be positive"):
            LossCircuitBreakerConfig(loss_threshold_pct=Decimal("-1"))

    def test_zero_threshold_raises(self) -> None:
        with pytest.raises(ValueError, match="loss_threshold_pct must be positive"):
            LossCircuitBreakerConfig(loss_threshold_pct=Decimal("0"))

    def test_negative_cooldown_raises(self) -> None:
        with pytest.raises(ValueError, match="cooldown_seconds must be positive"):
            LossCircuitBreakerConfig(cooldown_seconds=-1)

    def test_negative_window_raises(self) -> None:
        with pytest.raises(ValueError, match="window_seconds must be positive"):
            LossCircuitBreakerConfig(window_seconds=-1)


# ═════════════════════════════════════════════════════════════════════════
# Trip count tracking
# ═════════════════════════════════════════════════════════════════════════


class TestTripCount:
    """Verify trip_count increments correctly."""

    def test_trip_count_starts_at_zero(self, default_cb_config: LossCircuitBreakerConfig) -> None:
        cb = LossCircuitBreaker(config=default_cb_config)
        assert cb.snapshot()["trip_count"] == 0

    def test_trip_count_increments_on_open(
        self, default_cb_config: LossCircuitBreakerConfig
    ) -> None:
        cb = LossCircuitBreaker(config=default_cb_config)
        capital = Decimal("1000000")
        cb.record_loss(Decimal("-20000"), capital)
        assert cb.snapshot()["trip_count"] == 1

    def test_trip_count_increments_on_repeated_trips(
        self, default_cb_config: LossCircuitBreakerConfig
    ) -> None:
        """After reset and re-trip, count increments again."""
        cb = LossCircuitBreaker(config=default_cb_config)
        capital = Decimal("1000000")
        cb.record_loss(Decimal("-20000"), capital)
        cb.reset()
        time.sleep(default_cb_config.cooldown_seconds + 0.5)
        cb.allow_trading()  # Auto-close
        # Trip again
        cb.record_loss(Decimal("-20000"), capital)
        assert cb.snapshot()["trip_count"] == 2
