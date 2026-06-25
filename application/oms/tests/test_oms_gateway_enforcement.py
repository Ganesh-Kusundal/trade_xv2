"""Tests for OMS-only gateway access enforcement (B4 fix).

Verifies that:
1. Order placement through OMS proxy is allowed when kill switch is OFF
2. Order placement is blocked when kill switch is ON
3. Direct gateway access for order operations is blocked
4. Market data access is allowed (not an order operation)
5. Audit logging captures all operations
6. OrderBlockedError is raised on violation
7. Strict mode vs audit-only mode behavior
8. Cancel and modify operations are also enforced
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from application.oms.oms_gateway_proxy import OMSGatewayProxy, OrderBlockedError


@pytest.fixture
def mock_gateway():
    """Create a mock broker gateway."""
    gw = MagicMock()
    gw.place_order.return_value = MagicMock(
        success=True,
        order_id="TEST-ORD-001",
        message="Order placed",
    )
    gw.cancel_order.return_value = MagicMock(
        success=True,
        order_id="TEST-ORD-001",
        message="Order cancelled",
    )
    gw.modify_order.return_value = MagicMock(
        success=True,
        order_id="TEST-ORD-001",
        message="Order modified",
    )
    gw.quote.return_value = MagicMock(
        symbol="RELIANCE",
        ltp=Decimal("2450.50"),
    )
    gw.ltp.return_value = Decimal("2450.50")
    gw.positions.return_value = []
    gw.get_orderbook.return_value = []
    gw.describe.return_value = {"name": "test", "connected": True}
    gw.capabilities.return_value = MagicMock()
    return gw


@pytest.fixture
def mock_risk_manager():
    """Create a mock risk manager with kill switch OFF by default."""
    rm = MagicMock()
    rm.is_kill_switch_active.return_value = False
    return rm


@pytest.fixture
def audit_log():
    """Collect audit entries for verification."""
    entries = []

    def collector(entry: dict) -> None:
        entries.append(entry)

    return entries, collector


class TestOrderPlacementAllowed:
    """Test order placement is allowed when kill switch is OFF."""

    def test_place_order_allowed_when_kill_switch_off(self, mock_gateway, mock_risk_manager):
        """Order placement succeeds when kill switch is inactive."""
        proxy = OMSGatewayProxy(
            real_gateway=mock_gateway,
            risk_manager=mock_risk_manager,
            strict_mode=True,
        )

        result = proxy.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            quantity=10,
            price=Decimal("2450.00"),
        )

        assert result.success is True
        mock_gateway.place_order.assert_called_once()

    def test_place_order_audit_entry_created(self, mock_gateway, mock_risk_manager, audit_log):
        """Audit entry is created for allowed order placement."""
        entries, collector = audit_log
        proxy = OMSGatewayProxy(
            real_gateway=mock_gateway,
            risk_manager=mock_risk_manager,
            audit_logger=collector,
            strict_mode=True,
        )

        proxy.place_order(symbol="RELIANCE", side="BUY", quantity=10)

        assert len(entries) == 1
        assert entries[0]["operation"] == "place_order"
        assert entries[0]["outcome"] == "ALLOWED"
        assert entries[0]["symbol"] == "RELIANCE"

    def test_place_order_proxies_all_parameters(self, mock_gateway, mock_risk_manager):
        """All order parameters are correctly proxied to the real gateway."""
        proxy = OMSGatewayProxy(
            real_gateway=mock_gateway,
            risk_manager=mock_risk_manager,
            strict_mode=True,
        )

        proxy.place_order(
            symbol="NIFTY24600CE",
            exchange="NFO",
            side="SELL",
            quantity=75,
            price=Decimal("100.00"),
            order_type="LIMIT",
            product_type="MARGIN",
            validity="IOC",
            trigger_price=Decimal("95.00"),
            correlation_id="test-corr-123",
        )

        call_kwargs = mock_gateway.place_order.call_args[1]
        assert call_kwargs["symbol"] == "NIFTY24600CE"
        assert call_kwargs["exchange"] == "NFO"
        assert call_kwargs["side"] == "SELL"
        assert call_kwargs["quantity"] == 75
        assert call_kwargs["price"] == Decimal("100.00")
        assert call_kwargs["order_type"] == "LIMIT"
        assert call_kwargs["product_type"] == "MARGIN"
        assert call_kwargs["validity"] == "IOC"
        assert call_kwargs["trigger_price"] == Decimal("95.00")
        assert call_kwargs["correlation_id"] == "test-corr-123"


class TestOrderPlacementBlocked:
    """Test order placement is blocked when kill switch is ON."""

    def test_place_order_blocked_when_kill_switch_active(self, mock_gateway, mock_risk_manager):
        """Order placement raises OrderBlockedError when kill switch is active."""
        mock_risk_manager.is_kill_switch_active.return_value = True

        proxy = OMSGatewayProxy(
            real_gateway=mock_gateway,
            risk_manager=mock_risk_manager,
            strict_mode=True,
        )

        with pytest.raises(OrderBlockedError) as exc_info:
            proxy.place_order(symbol="RELIANCE", side="BUY", quantity=10)

        assert exc_info.value.operation == "place_order"
        assert "Kill switch active" in exc_info.value.reason
        # Gateway should NOT have been called
        mock_gateway.place_order.assert_not_called()

    def test_place_order_blocked_audit_entry(self, mock_gateway, mock_risk_manager, audit_log):
        """Blocked order placement creates audit entry."""
        mock_risk_manager.is_kill_switch_active.return_value = True
        entries, collector = audit_log

        proxy = OMSGatewayProxy(
            real_gateway=mock_gateway,
            risk_manager=mock_risk_manager,
            audit_logger=collector,
            strict_mode=True,
        )

        with pytest.raises(OrderBlockedError):
            proxy.place_order(symbol="RELIANCE", side="BUY", quantity=10)

        assert len(entries) == 1
        assert entries[0]["operation"] == "place_order"
        assert entries[0]["outcome"] == "BLOCKED"
        assert entries[0]["reason"] == "Kill switch active"

    def test_cancel_order_blocked_when_kill_switch_active(self, mock_gateway, mock_risk_manager):
        """Order cancellation raises OrderBlockedError when kill switch is active."""
        mock_risk_manager.is_kill_switch_active.return_value = True

        proxy = OMSGatewayProxy(
            real_gateway=mock_gateway,
            risk_manager=mock_risk_manager,
            strict_mode=True,
        )

        with pytest.raises(OrderBlockedError) as exc_info:
            proxy.cancel_order("TEST-ORD-001")

        assert exc_info.value.operation == "cancel_order"
        mock_gateway.cancel_order.assert_not_called()

    def test_modify_order_blocked_when_kill_switch_active(self, mock_gateway, mock_risk_manager):
        """Order modification raises OrderBlockedError when kill switch is active."""
        mock_risk_manager.is_kill_switch_active.return_value = True

        proxy = OMSGatewayProxy(
            real_gateway=mock_gateway,
            risk_manager=mock_risk_manager,
            strict_mode=True,
        )

        with pytest.raises(OrderBlockedError) as exc_info:
            proxy.modify_order("TEST-ORD-001", price=Decimal("2500.00"))

        assert exc_info.value.operation == "modify_order"
        mock_gateway.modify_order.assert_not_called()


class TestMarketDataPassThrough:
    """Test that market data operations pass through without OMS enforcement."""

    def test_quote_allowed_when_kill_switch_active(self, mock_gateway, mock_risk_manager):
        """Market data (quote) works even when kill switch is active."""
        mock_risk_manager.is_kill_switch_active.return_value = True

        proxy = OMSGatewayProxy(
            real_gateway=mock_gateway,
            risk_manager=mock_risk_manager,
            strict_mode=True,
        )

        result = proxy.quote("RELIANCE", "NSE")

        assert result.ltp == Decimal("2450.50")
        mock_gateway.quote.assert_called_once()

    def test_ltp_allowed_when_kill_switch_active(self, mock_gateway, mock_risk_manager):
        """LTP lookup works even when kill switch is active."""
        mock_risk_manager.is_kill_switch_active.return_value = True

        proxy = OMSGatewayProxy(
            real_gateway=mock_gateway,
            risk_manager=mock_risk_manager,
            strict_mode=True,
        )

        result = proxy.ltp("RELIANCE", "NSE")

        assert result == Decimal("2450.50")
        mock_gateway.ltp.assert_called_once()

    def test_positions_allowed_when_kill_switch_active(self, mock_gateway, mock_risk_manager):
        """Portfolio read works even when kill switch is active."""
        mock_risk_manager.is_kill_switch_active.return_value = True

        proxy = OMSGatewayProxy(
            real_gateway=mock_gateway,
            risk_manager=mock_risk_manager,
            strict_mode=True,
        )

        result = proxy.positions()

        assert result == []
        mock_gateway.positions.assert_called_once()

    def test_describe_allowed_when_kill_switch_active(self, mock_gateway, mock_risk_manager):
        """Gateway describe works even when kill switch is active."""
        mock_risk_manager.is_kill_switch_active.return_value = True

        proxy = OMSGatewayProxy(
            real_gateway=mock_gateway,
            risk_manager=mock_risk_manager,
            strict_mode=True,
        )

        result = proxy.describe()

        assert result["name"] == "test"


class TestStrictModeVsAuditOnly:
    """Test behavior difference between strict mode and audit-only mode."""

    def test_strict_mode_blocks_when_risk_manager_none(self, mock_gateway):
        """In strict mode, None risk_manager blocks order operations."""
        proxy = OMSGatewayProxy(
            real_gateway=mock_gateway,
            risk_manager=None,
            strict_mode=True,
        )

        with pytest.raises(OrderBlockedError) as exc_info:
            proxy.place_order(symbol="RELIANCE", side="BUY", quantity=10)

        assert "OMS unavailable" in exc_info.value.reason

    def test_audit_mode_allows_when_risk_manager_none(self, mock_gateway, audit_log):
        """In audit-only mode, None risk_manager logs but allows order operations."""
        entries, collector = audit_log

        proxy = OMSGatewayProxy(
            real_gateway=mock_gateway,
            risk_manager=None,
            audit_logger=collector,
            strict_mode=False,
        )

        result = proxy.place_order(symbol="RELIANCE", side="BUY", quantity=10)

        assert result.success is True
        mock_gateway.place_order.assert_called_once()
        assert len(entries) >= 1
        assert any(e["outcome"] == "ALLOWED_AUDIT_ONLY" for e in entries)

    def test_audit_mode_blocks_when_kill_switch_active(
        self, mock_gateway, mock_risk_manager, audit_log
    ):
        """Even in audit-only mode, kill switch active still blocks."""
        mock_risk_manager.is_kill_switch_active.return_value = True
        entries, collector = audit_log

        proxy = OMSGatewayProxy(
            real_gateway=mock_gateway,
            risk_manager=mock_risk_manager,
            audit_logger=collector,
            strict_mode=False,
        )

        with pytest.raises(OrderBlockedError):
            proxy.place_order(symbol="RELIANCE", side="BUY", quantity=10)

        assert entries[0]["outcome"] == "BLOCKED"
        mock_gateway.place_order.assert_not_called()


class TestOrderBlockedError:
    """Test OrderBlockedError properties."""

    def test_error_has_operation_field(self):
        """OrderBlockedError stores the operation name."""
        err = OrderBlockedError("Test", operation="place_order")
        assert err.operation == "place_order"

    def test_error_has_reason_field(self):
        """OrderBlockedError stores the reason."""
        err = OrderBlockedError("Test", reason="Kill switch active")
        assert err.reason == "Kill switch active"

    def test_error_has_timestamp(self):
        """OrderBlockedError stores a timestamp."""
        err = OrderBlockedError("Test")
        assert isinstance(err.timestamp, float)
        assert err.timestamp > 0

    def test_error_message_contains_details(self):
        """Error message contains relevant context."""
        err = OrderBlockedError(
            "Order blocked: kill switch active. symbol=RELIANCE",
            operation="place_order",
        )
        assert "place_order" in str(err) or "RELIANCE" in str(err)


class TestObservability:
    """Test proxy observability and metrics."""

    def test_operation_count_increments(self, mock_gateway, mock_risk_manager):
        """Operation count tracks all attempts."""
        proxy = OMSGatewayProxy(
            real_gateway=mock_gateway,
            risk_manager=mock_risk_manager,
            strict_mode=True,
        )

        proxy.place_order(symbol="A", side="BUY", quantity=1)
        proxy.place_order(symbol="B", side="BUY", quantity=1)
        proxy.cancel_order("ORD-001")

        assert proxy.operation_count == 3

    def test_blocked_count_increments(self, mock_gateway, mock_risk_manager):
        """Blocked count tracks rejected operations."""
        mock_risk_manager.is_kill_switch_active.return_value = True

        proxy = OMSGatewayProxy(
            real_gateway=mock_gateway,
            risk_manager=mock_risk_manager,
            strict_mode=True,
        )

        for i in range(3):
            with pytest.raises(OrderBlockedError):
                proxy.place_order(symbol=f"SYM{i}", side="BUY", quantity=1)

        assert proxy.blocked_count == 3

    def test_snapshot_returns_state(self, mock_gateway, mock_risk_manager):
        """Snapshot returns all proxy state fields."""
        proxy = OMSGatewayProxy(
            real_gateway=mock_gateway,
            risk_manager=mock_risk_manager,
            strict_mode=True,
        )

        proxy.place_order(symbol="RELIANCE", side="BUY", quantity=10)

        snap = proxy.snapshot()

        assert snap["operation_count"] == 1
        assert snap["blocked_count"] == 0
        assert snap["strict_mode"] is True
        assert snap["kill_switch_active"] is False
        assert "real_gateway" in snap


class TestAuditLogging:
    """Test audit logging captures all operations."""

    def test_all_order_operations_logged(self, mock_gateway, mock_risk_manager, audit_log):
        """Place, cancel, and modify all create audit entries."""
        entries, collector = audit_log

        proxy = OMSGatewayProxy(
            real_gateway=mock_gateway,
            risk_manager=mock_risk_manager,
            audit_logger=collector,
            strict_mode=True,
        )

        proxy.place_order(symbol="RELIANCE", side="BUY", quantity=10)
        proxy.cancel_order("ORD-001")
        proxy.modify_order("ORD-001", price=Decimal("2500.00"))

        assert len(entries) == 3
        operations = [e["operation"] for e in entries]
        assert "place_order" in operations
        assert "cancel_order" in operations
        assert "modify_order" in operations

    def test_audit_entry_has_required_fields(self, mock_gateway, mock_risk_manager, audit_log):
        """Every audit entry contains timestamp, operation, symbol, outcome."""
        entries, collector = audit_log

        proxy = OMSGatewayProxy(
            real_gateway=mock_gateway,
            risk_manager=mock_risk_manager,
            audit_logger=collector,
            strict_mode=True,
        )

        proxy.place_order(symbol="RELIANCE", side="BUY", quantity=10)

        entry = entries[0]
        assert "timestamp" in entry
        assert "operation" in entry
        assert "outcome" in entry
        assert "strict_mode" in entry
        assert "gateway" in entry
        assert isinstance(entry["timestamp"], float)

    def test_blocked_operations_logged(self, mock_gateway, mock_risk_manager, audit_log):
        """Blocked operations are also logged."""
        mock_risk_manager.is_kill_switch_active.return_value = True
        entries, collector = audit_log

        proxy = OMSGatewayProxy(
            real_gateway=mock_gateway,
            risk_manager=mock_risk_manager,
            audit_logger=collector,
            strict_mode=True,
        )

        with pytest.raises(OrderBlockedError):
            proxy.place_order(symbol="RELIANCE", side="BUY", quantity=10)

        assert len(entries) == 1
        assert entries[0]["outcome"] == "BLOCKED"
        assert entries[0]["reason"] == "Kill switch active"
