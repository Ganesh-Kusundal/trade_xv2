"""Tests for PnL precision with Decimal to prevent float accumulation drift."""

from __future__ import annotations

from decimal import Decimal

from analytics.replay.models import SimulatedTrade


class TestSimulatedTradePnlDecimal:
    """Verify SimulatedTrade.pnl uses Decimal for precision."""

    def test_pnl_is_decimal(self):
        trade = SimulatedTrade(
            symbol="TEST",
            side="BUY",
            entry_price=100.0,
            exit_price=110.0,
            quantity=10,
            pnl=Decimal("100"),
        )
        assert isinstance(trade.pnl, Decimal)

    def test_pnl_default_is_decimal_zero(self):
        trade = SimulatedTrade(
            symbol="TEST",
            side="BUY",
            entry_price=100.0,
        )
        assert isinstance(trade.pnl, Decimal)
        assert trade.pnl == Decimal("0")

    def test_pnl_sum_no_drift_with_repeated_values(self):
        """Summing repeated exact Decimal values has zero drift."""
        n = 100_000
        trades = [
            SimulatedTrade(
                symbol="TEST",
                side="BUY",
                entry_price=100.0,
                exit_price=100.01,
                quantity=1,
                pnl=Decimal("0.01"),
            )
            for _ in range(n)
        ]

        decimal_total = sum(t.pnl for t in trades)
        assert decimal_total == Decimal("1000.0"), (
            f"Unexpected drift: {decimal_total - Decimal('1000.0')}"
        )

    def test_to_domain_trade_works_with_decimal_pnl(self):
        """to_domain_trade() should handle Decimal pnl correctly."""
        trade = SimulatedTrade(
            symbol="TEST",
            side="BUY",
            entry_price=100.0,
            exit_price=110.0,
            quantity=10,
            pnl=Decimal("100.50"),
        )
        domain_trade = trade.to_domain_trade()
        assert domain_trade is not None

    def test_pnl_comparison_with_zero(self):
        """Decimal pnl should compare correctly with zero."""
        positive = SimulatedTrade(symbol="TEST", side="BUY", entry_price=100.0, pnl=Decimal("0.01"))
        negative = SimulatedTrade(
            symbol="TEST", side="BUY", entry_price=100.0, pnl=Decimal("-0.01")
        )
        zero = SimulatedTrade(symbol="TEST", side="BUY", entry_price=100.0, pnl=Decimal("0"))

        assert positive.pnl > 0
        assert negative.pnl < 0
        assert zero.pnl == 0

    def test_pnl_float_conversion(self):
        """Decimal pnl should convert to float cleanly."""
        trade = SimulatedTrade(
            symbol="TEST",
            side="BUY",
            entry_price=100.0,
            exit_price=110.0,
            quantity=10,
            pnl=Decimal("100.50"),
        )
        assert float(trade.pnl) == 100.5
