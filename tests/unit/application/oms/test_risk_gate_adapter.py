"""Tests for the RiskGateAdapter — bridges domain RiskGate to OMS risk-check interface."""

from __future__ import annotations

from decimal import Decimal

import pytest

from application.oms.risk_gate_adapter import RiskGateAdapter
from application.oms._internal.risk_types import RiskResult
from domain.risk.policy import RiskGate, OrderNotionalLimit, GrossExposureLimit, RiskResult as DomainRiskResult


class _FakeOrder:
    """Minimal order-like object for testing."""

    def __init__(self, price: Decimal = Decimal("100"), quantity: int = 10):
        self.price = price
        self.quantity = quantity


class TestRiskGateAdapter:
    """Unit tests for the adapter."""

    def test_approves_when_gate_approves(self):
        gate = RiskGate(notional=OrderNotionalLimit(max_notional=Decimal("100000")))
        adapter = RiskGateAdapter(gate=gate)
        result = adapter.check_order(_FakeOrder(price=Decimal("50"), quantity=10))
        assert result.allowed is True
        assert result.reason is None

    def test_rejects_when_gate_rejects(self):
        gate = RiskGate(notional=OrderNotionalLimit(max_notional=Decimal("100")))
        adapter = RiskGateAdapter(gate=gate)
        result = adapter.check_order(_FakeOrder(price=Decimal("50"), quantity=10))
        assert result.allowed is False
        assert result.reason is not None

    def test_extracts_notional_from_order(self):
        gate = RiskGate(notional=OrderNotionalLimit(max_notional=Decimal("500")))
        adapter = RiskGateAdapter(gate=gate)
        # notional = 100 * 10 = 1000 > 500 → rejected
        result = adapter.check_order(_FakeOrder(price=Decimal("100"), quantity=10))
        assert result.allowed is False

    def test_uses_capital_fn(self):
        gate = RiskGate(gross_exposure=GrossExposureLimit(max_pct=Decimal("1.0")))
        adapter = RiskGateAdapter(
            gate=gate,
            capital_fn=lambda: Decimal("10000"),
            total_exposure_fn=lambda: Decimal("5000"),
        )
        result = adapter.check_order(_FakeOrder(price=Decimal("100"), quantity=10))
        assert result.allowed is True

    def test_none_fn_returns_default(self):
        gate = RiskGate(notional=OrderNotionalLimit(max_notional=Decimal("100000")))
        adapter = RiskGateAdapter(gate=gate, capital_fn=None)
        result = adapter.check_order(_FakeOrder())
        assert result.allowed is True

    def test_fn_exception_returns_default(self):
        def broken_fn():
            raise RuntimeError("boom")

        gate = RiskGate(notional=OrderNotionalLimit(max_notional=Decimal("100000")))
        adapter = RiskGateAdapter(gate=gate, capital_fn=broken_fn)
        result = adapter.check_order(_FakeOrder())
        assert result.allowed is True

    def test_result_has_reason_string(self):
        gate = RiskGate(notional=OrderNotionalLimit(max_notional=Decimal("100")))
        adapter = RiskGateAdapter(gate=gate)
        result = adapter.check_order(_FakeOrder(price=Decimal("1000"), quantity=1))
        assert isinstance(result, RiskResult)
        assert result.allowed is False
        assert isinstance(result.reason, str)
