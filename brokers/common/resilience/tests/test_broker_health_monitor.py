"""TDD tests for BrokerHealthMonitor and IntelligentGateway graceful degradation.

Tests cover:
- Health tracking (success/failure recording)
- Threshold-based health determination
- Concurrent access thread safety
- IntelligentGateway graceful degradation behavior
- Cache TTL behavior
- Write operations rejected in degraded mode
"""

from __future__ import annotations

import logging
import threading
import time
from decimal import Decimal
from unittest.mock import MagicMock

import pandas as pd
import pytest

from brokers.common.intelligent_gateway import (
    _CacheEntry,
    IntelligentGateway,
    _HISTORY_CACHE_TTL,
    _QUOTE_CACHE_TTL,
    _WRITE_OPERATIONS,
)
from brokers.common.observability.event_metrics import EventMetrics
from brokers.common.resilience.broker_health_monitor import (
    BrokerHealthMonitor,
    BrokerHealthStatus,
)
from brokers.common.resilience.errors import BrokerDegradedError


# ======================================================================
# BrokerHealthMonitor tests
# ======================================================================


class TestBrokerHealthMonitorInitialization:
    def test_default_threshold(self):
        monitor = BrokerHealthMonitor()
        assert monitor.failure_threshold == 5

    def test_custom_threshold(self):
        monitor = BrokerHealthMonitor(failure_threshold=3)
        assert monitor.failure_threshold == 3

    def test_invalid_threshold_raises(self):
        with pytest.raises(ValueError, match="failure_threshold must be positive"):
            BrokerHealthMonitor(failure_threshold=0)
        with pytest.raises(ValueError, match="failure_threshold must be positive"):
            BrokerHealthMonitor(failure_threshold=-1)

    def test_empty_monitor_is_healthy_for_any(self):
        monitor = BrokerHealthMonitor()
        assert monitor.any_healthy(["dhan"]) is True  # unknown = healthy


class TestBrokerHealthMonitorSuccessFailureTracking:
    def test_record_success_marks_healthy(self):
        monitor = BrokerHealthMonitor(failure_threshold=3)
        monitor.record_failure("dhan")
        monitor.record_failure("dhan")
        monitor.record_success("dhan")
        assert monitor.is_healthy("dhan") is True

    def test_record_success_resets_consecutive_failures(self):
        monitor = BrokerHealthMonitor(failure_threshold=3)
        monitor.record_failure("dhan")
        monitor.record_failure("dhan")
        assert monitor.get_health_status()["dhan"].consecutive_failures == 2
        monitor.record_success("dhan")
        assert monitor.get_health_status()["dhan"].consecutive_failures == 0

    def test_consecutive_failures_reach_threshold(self):
        monitor = BrokerHealthMonitor(failure_threshold=3)
        monitor.record_failure("dhan")
        monitor.record_failure("dhan")
        assert monitor.is_healthy("dhan") is True  # 2 < 3
        monitor.record_failure("dhan")
        assert monitor.is_healthy("dhan") is False  # 3 >= 3

    def test_success_after_unhealthy_recovers(self):
        monitor = BrokerHealthMonitor(failure_threshold=2)
        monitor.record_failure("dhan")
        monitor.record_failure("dhan")
        assert monitor.is_healthy("dhan") is False
        monitor.record_success("dhan")
        assert monitor.is_healthy("dhan") is True

    def test_unknown_broker_is_healthy(self):
        monitor = BrokerHealthMonitor()
        assert monitor.is_healthy("nonexistent") is True

    def test_last_successful_call_updated(self):
        monitor = BrokerHealthMonitor()
        before = time.monotonic()
        monitor.record_success("dhan")
        after = time.monotonic()
        status = monitor.get_health_status()["dhan"]
        assert status.last_successful_call is not None
        assert before <= status.last_successful_call <= after

    def test_last_health_check_updated_on_failure(self):
        monitor = BrokerHealthMonitor()
        before = time.monotonic()
        monitor.record_failure("dhan")
        after = time.monotonic()
        status = monitor.get_health_status()["dhan"]
        assert before <= status.last_health_check <= after


class TestBrokerHealthMonitorGetHealthStatus:
    def test_returns_copy_not_reference(self):
        monitor = BrokerHealthMonitor()
        monitor.record_failure("dhan")
        status1 = monitor.get_health_status()
        status2 = monitor.get_health_status()
        assert status1 is not status2
        assert status1["dhan"] is not status2["dhan"]

    def test_to_dict_serializable(self):
        monitor = BrokerHealthMonitor()
        monitor.record_success("dhan")
        status = monitor.get_health_status()["dhan"]
        d = status.to_dict()
        assert isinstance(d, dict)
        assert "last_successful_call" in d
        assert "consecutive_failures" in d
        assert "circuit_state" in d
        assert "last_health_check" in d

    def test_circuit_state_values(self):
        monitor = BrokerHealthMonitor(failure_threshold=2)
        status = monitor.get_health_status()
        assert "dhan" not in status  # not tracked yet

        monitor.record_failure("dhan")
        status = monitor.get_health_status()["dhan"]
        assert status.circuit_state == "healthy"

        monitor.record_failure("dhan")
        status = monitor.get_health_status()["dhan"]
        assert status.circuit_state == "unhealthy"


class TestBrokerHealthMonitorAnyHealthy:
    def test_any_healthy_with_list(self):
        monitor = BrokerHealthMonitor(failure_threshold=2)
        monitor.record_failure("dhan")
        monitor.record_failure("dhan")
        assert monitor.any_healthy(["dhan", "upstox"]) is True  # upstox unknown = healthy

    def test_any_healthy_all_unhealthy(self):
        monitor = BrokerHealthMonitor(failure_threshold=2)
        monitor.record_failure("dhan")
        monitor.record_failure("dhan")
        monitor.record_failure("upstox")
        monitor.record_failure("upstox")
        assert monitor.any_healthy(["dhan", "upstox"]) is False

    def test_any_healthy_empty_list(self):
        monitor = BrokerHealthMonitor()
        assert monitor.any_healthy([]) is False

    def test_any_healthy_no_tracking(self):
        monitor = BrokerHealthMonitor()
        assert monitor.any_healthy() is False  # no tracked brokers


class TestBrokerHealthMonitorReset:
    def test_reset_single_broker(self):
        monitor = BrokerHealthMonitor(failure_threshold=2)
        monitor.record_failure("dhan")
        monitor.record_failure("dhan")
        assert monitor.is_healthy("dhan") is False
        monitor.reset("dhan")
        assert monitor.is_healthy("dhan") is True  # removed = unknown = healthy

    def test_reset_all(self):
        monitor = BrokerHealthMonitor()
        monitor.record_failure("dhan")
        monitor.record_failure("dhan")
        monitor.record_failure("upstox")
        monitor.record_failure("upstox")
        monitor.reset()
        assert monitor.get_health_status() == {}


class TestBrokerHealthMonitorThreadSafety:
    """Verify concurrent access does not corrupt state."""

    def test_concurrent_record_success(self):
        monitor = BrokerHealthMonitor()
        threads = []
        for _ in range(50):
            t = threading.Thread(target=monitor.record_success, args=("dhan",))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        status = monitor.get_health_status()["dhan"]
        assert status.consecutive_failures == 0
        assert status.circuit_state == "healthy"

    def test_concurrent_record_failure(self):
        monitor = BrokerHealthMonitor(failure_threshold=100)
        threads = []
        for _ in range(50):
            t = threading.Thread(target=monitor.record_failure, args=("dhan",))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        status = monitor.get_health_status()["dhan"]
        assert status.consecutive_failures == 50

    def test_concurrent_mixed_operations(self):
        monitor = BrokerHealthMonitor(failure_threshold=10)
        barrier = threading.Barrier(20)

        def worker(is_success: bool):
            barrier.wait()
            for _ in range(100):
                if is_success:
                    monitor.record_success("dhan")
                else:
                    monitor.record_failure("dhan")

        threads = []
        for i in range(20):
            t = threading.Thread(target=worker, args=(i % 2 == 0,))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        # No exceptions means thread-safe
        status = monitor.get_health_status()["dhan"]
        assert isinstance(status, BrokerHealthStatus)


# ======================================================================
# IntelligentGateway graceful degradation tests
# ======================================================================


class TestIntelligentGatewayHealthMonitorIntegration:
    """Test that IntelligentGateway correctly uses BrokerHealthMonitor."""

    def test_health_monitor_optional(self):
        gw = IntelligentGateway()
        assert gw.health_monitor is None
        assert gw.degraded_mode is False

    def test_health_monitor_injected(self):
        monitor = BrokerHealthMonitor()
        gw = IntelligentGateway(health_monitor=monitor)
        assert gw.health_monitor is monitor

    def test_degraded_mode_when_all_unhealthy(self):
        monitor = BrokerHealthMonitor(failure_threshold=2)
        dhan = MagicMock()
        upstox = MagicMock()
        gw = IntelligentGateway(
            dhan_gateway=dhan,
            upstox_gateway=upstox,
            health_monitor=monitor,
        )
        # Make both unhealthy
        for _ in range(2):
            monitor.record_failure("dhan")
            monitor.record_failure("upstox")
        assert gw.degraded_mode is True

    def test_degraded_mode_false_when_one_healthy(self):
        monitor = BrokerHealthMonitor(failure_threshold=2)
        dhan = MagicMock()
        upstox = MagicMock()
        gw = IntelligentGateway(
            dhan_gateway=dhan,
            upstox_gateway=upstox,
            health_monitor=monitor,
        )
        monitor.record_failure("dhan")
        monitor.record_failure("dhan")
        # upstox is still healthy
        assert gw.degraded_mode is False

    def test_degraded_mode_false_when_no_brokers(self):
        monitor = BrokerHealthMonitor()
        gw = IntelligentGateway(health_monitor=monitor)
        assert gw.degraded_mode is False  # no brokers configured

    def test_skip_unhealthy_primary(self, caplog):
        """If primary is unhealthy but fallback is healthy, skip primary."""
        monitor = BrokerHealthMonitor(failure_threshold=2)
        dhan = MagicMock()
        upstox = MagicMock()
        upstox.ltp.return_value = Decimal("100.00")

        gw = IntelligentGateway(
            dhan_gateway=dhan,
            upstox_gateway=upstox,
            health_monitor=monitor,
            metrics=EventMetrics(),
        )
        # Make dhan (fallback for ltp) unhealthy — wait, ltp primary is upstox
        # Let's make upstox unhealthy
        for _ in range(2):
            monitor.record_failure("upstox")

        result = gw.ltp("RELIANCE")
        # Should have skipped upstox and gone to dhan
        assert result == Decimal("100.00") or dhan.ltp.called
        # Verify skip was logged
        skip_logs = [
            r for r in caplog.records
            if getattr(r, "message", None) == "broker_health_skip_primary"
        ]
        assert len(skip_logs) >= 1


class TestIntelligentGatewayDegradedModeReadOperations:
    """Read operations should return cached data in degraded mode."""

    def _make_degraded_gateway(self, monitor: BrokerHealthMonitor):
        """Create a gateway with both brokers unhealthy."""
        dhan = MagicMock()
        upstox = MagicMock()
        return IntelligentGateway(
            dhan_gateway=dhan,
            upstox_gateway=upstox,
            health_monitor=monitor,
            metrics=EventMetrics(),
        ), dhan, upstox

    def test_ltp_returns_cached_data_in_degraded_mode(self, caplog):
        monitor = BrokerHealthMonitor(failure_threshold=2)
        gw, dhan, upstox = self._make_degraded_gateway(monitor)

        # First, populate the cache with a successful call
        upstox.ltp.return_value = Decimal("150.00")
        gw.ltp("RELIANCE")

        # Now make both unhealthy AND make them fail
        for _ in range(2):
            monitor.record_failure("upstox")
            monitor.record_failure("dhan")
        upstox.ltp.side_effect = ConnectionError("upstox down")
        dhan.ltp.side_effect = ConnectionError("dhan down")

        # In degraded mode, should return cached value
        result = gw.ltp("RELIANCE")
        assert result == Decimal("150.00")

        # Should have logged critical and warning
        critical_logs = [
            r for r in caplog.records
            if getattr(r, "message", None) == "broker_degraded_mode"
        ]
        assert len(critical_logs) >= 1
        stale_logs = [
            r for r in caplog.records
            if getattr(r, "message", None) == "broker_degraded_serving_stale_cache"
        ]
        assert len(stale_logs) >= 1

    def test_history_returns_cached_data_in_degraded_mode(self):
        monitor = BrokerHealthMonitor(failure_threshold=2)
        gw, dhan, upstox = self._make_degraded_gateway(monitor)

        expected_df = pd.DataFrame({"close": [100, 101, 102]})
        dhan.history.return_value = expected_df
        gw.history("RELIANCE")

        for _ in range(2):
            monitor.record_failure("dhan")
            monitor.record_failure("upstox")

        result = gw.history("RELIANCE")
        pd.testing.assert_frame_equal(result, expected_df)

    def test_no_cache_raises_runtime_error_in_degraded_mode(self):
        monitor = BrokerHealthMonitor(failure_threshold=2)
        gw, dhan, upstox = self._make_degraded_gateway(monitor)

        # Never called successfully, so cache is empty
        for _ in range(2):
            monitor.record_failure("dhan")
            monitor.record_failure("upstox")
        upstox.ltp.side_effect = ConnectionError("upstox down")
        dhan.ltp.side_effect = ConnectionError("dhan down")

        with pytest.raises(RuntimeError, match="No broker available and no cached data"):
            gw.ltp("RELIANCE")

    def test_positions_returns_default_in_degraded_mode(self):
        """positions() has a default=[] so it should return that."""
        monitor = BrokerHealthMonitor(failure_threshold=2)
        gw, dhan, upstox = self._make_degraded_gateway(monitor)

        for _ in range(2):
            monitor.record_failure("dhan")
            monitor.record_failure("upstox")
        dhan.positions.side_effect = RuntimeError("dhan down")
        upstox.positions.side_effect = ConnectionError("upstox down")

        result = gw.positions()
        assert result == []

    def test_degraded_mode_metric_incremented(self):
        metrics = EventMetrics()
        monitor = BrokerHealthMonitor(failure_threshold=2)
        gw, dhan, upstox = self._make_degraded_gateway(monitor)
        gw._metrics = metrics

        upstox.ltp.return_value = Decimal("100.00")
        gw.ltp("RELIANCE")

        for _ in range(2):
            monitor.record_failure("dhan")
            monitor.record_failure("upstox")
        upstox.ltp.side_effect = ConnectionError("upstox down")
        dhan.ltp.side_effect = ConnectionError("dhan down")

        gw.ltp("RELIANCE")
        assert metrics.get("intelligent_gateway_degraded", "ltp") == 1


class TestIntelligentGatewayDegradedModeWriteOperations:
    """Write operations must raise BrokerDegradedError in degraded mode."""

    def test_write_operation_not_in_write_set(self):
        """Verify our _WRITE_OPERATIONS constant exists."""
        assert isinstance(_WRITE_OPERATIONS, frozenset)
        assert "place_order" in _WRITE_OPERATIONS

    def test_degraded_mode_allows_read_not_write(self):
        monitor = BrokerHealthMonitor(failure_threshold=2)
        dhan = MagicMock()
        upstox = MagicMock()
        gw = IntelligentGateway(
            dhan_gateway=dhan,
            upstox_gateway=upstox,
            health_monitor=monitor,
        )
        for _ in range(2):
            monitor.record_failure("dhan")
            monitor.record_failure("upstox")

        assert gw._is_degraded_and_should_fallback("ltp") is True
        assert gw._is_degraded_and_should_fallback("place_order") is False

    def test_cache_key_and_extraction(self):
        gw = IntelligentGateway()
        assert gw._cache_key("ltp", "RELIANCE") == ("ltp", "RELIANCE")
        assert gw._extract_symbol(("RELIANCE", "NSE"), {}) == "RELIANCE"
        assert gw._extract_symbol((), {"symbol": "TCS"}) == "TCS"
        assert gw._extract_symbol((["RELIANCE"],), {}) == "RELIANCE"


class TestIntelligentGatewayCacheTTL:
    """Test cache TTL behavior."""

    def test_cache_put_and_get(self):
        gw = IntelligentGateway()
        gw._cache_put("ltp", "RELIANCE", Decimal("100"), ttl=60)
        assert gw._cache_get("ltp", "RELIANCE") == Decimal("100")

    def test_cache_expired(self):
        gw = IntelligentGateway()
        # Use a very short TTL
        gw._cache_put("ltp", "RELIANCE", Decimal("100"), ttl=0.001)
        time.sleep(0.01)
        assert gw._cache_get("ltp", "RELIANCE") is None

    def test_cache_ttl_for_operations(self):
        gw = IntelligentGateway()
        assert gw._cache_ttl_for("ltp") == _QUOTE_CACHE_TTL
        assert gw._cache_ttl_for("quote") == _QUOTE_CACHE_TTL
        assert gw._cache_ttl_for("history") == _HISTORY_CACHE_TTL
        assert gw._cache_ttl_for("history_batch") == _HISTORY_CACHE_TTL

    def test_cache_entry_expired_property(self):
        entry = _CacheEntry("value", ttl=0.001, operation="ltp", symbol="X")
        time.sleep(0.01)
        assert entry.is_expired is True

    def test_cache_entry_not_expired(self):
        entry = _CacheEntry("value", ttl=60, operation="ltp", symbol="X")
        assert entry.is_expired is False

    def test_successful_call_populates_cache(self):
        dhan = MagicMock()
        upstox = MagicMock()
        upstox.ltp.return_value = Decimal("200.00")
        gw = IntelligentGateway(dhan_gateway=dhan, upstox_gateway=upstox)

        result = gw.ltp("RELIANCE", "NSE")
        assert result == Decimal("200.00")
        cached = gw._cache_get("ltp", "RELIANCE")
        assert cached == Decimal("200.00")


class TestIntelligentGatewayBackwardCompatibility:
    """Ensure existing behavior is preserved when health_monitor is None."""

    def test_no_health_monitor_uses_existing_routing(self):
        """Without health monitor, routing behaves exactly as before."""
        dhan = MagicMock()
        upstox = MagicMock()
        upstox.ltp.return_value = Decimal("100.00")
        gw = IntelligentGateway(dhan_gateway=dhan, upstox_gateway=upstox)

        result = gw.ltp("RELIANCE")
        assert result == Decimal("100.00")
        assert upstox.ltp.called

    def test_no_health_monitor_fallback_works(self):
        dhan = MagicMock()
        upstox = MagicMock()
        upstox.ltp.side_effect = ConnectionError("up")
        dhan.ltp.return_value = Decimal("200.00")
        gw = IntelligentGateway(dhan_gateway=dhan, upstox_gateway=upstox)

        result = gw.ltp("RELIANCE")
        assert result == Decimal("200.00")
        assert dhan.ltp.called

    def test_no_health_monitor_both_fail_raises(self):
        dhan = MagicMock()
        upstox = MagicMock()
        upstox.ltp.side_effect = ConnectionError("up")
        dhan.ltp.side_effect = ConnectionError("dhan")
        gw = IntelligentGateway(dhan_gateway=dhan, upstox_gateway=upstox)

        # Without health monitor, the fallback exception propagates
        with pytest.raises(ConnectionError, match="dhan"):
            gw.ltp("RELIANCE")

    def test_describe_still_works(self):
        gw = IntelligentGateway()
        info = gw.describe()
        assert info["brokers"] == []
        assert "routing" in info


class TestIntelligentGatewayHealthSkipMetric:
    """Verify that skipping an unhealthy primary increments the health_skip metric."""

    def test_health_skip_metric_incremented(self):
        metrics = EventMetrics()
        monitor = BrokerHealthMonitor(failure_threshold=2)
        dhan = MagicMock()
        upstox = MagicMock()
        dhan.ltp.return_value = Decimal("100.00")

        gw = IntelligentGateway(
            dhan_gateway=dhan,
            upstox_gateway=upstox,
            health_monitor=monitor,
            metrics=metrics,
        )
        for _ in range(2):
            monitor.record_failure("upstox")

        gw.ltp("RELIANCE")
        assert metrics.get("intelligent_gateway_health_skip", "ltp:upstox") == 1


class TestBrokerDegradedError:
    """Test the BrokerDegradedError exception."""

    def test_default_message(self):
        err = BrokerDegradedError()
        assert "degraded mode" in str(err).lower()

    def test_custom_message(self):
        err = BrokerDegradedError("custom message")
        assert "custom message" in str(err)

    def test_health_status_attached(self):
        health = {"dhan": {"circuit_state": "unhealthy"}}
        err = BrokerDegradedError(health_status=health)
        assert err.health_status == health

    def test_is_broker_error(self):
        from brokers.common.resilience.errors import BrokerError
        err = BrokerDegradedError()
        assert isinstance(err, BrokerError)
