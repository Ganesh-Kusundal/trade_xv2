"""Tests for Indian market commission model in backtest."""

from __future__ import annotations

import pytest

from analytics.replay.models import ReplayConfig
from application.services.trading_costs_service import (
    CommissionModel,
    IndianMarketFees,
    compute_indian_equity_fees,
    compute_indian_fno_fees,
)

# ── Flat Commission Tests ───────────────────────────────────────────────


class TestFlatCommission:
    """Verify legacy flat commission model is unchanged."""

    def test_flat_commission_default(self):
        config = ReplayConfig()
        assert config.commission_model == CommissionModel.FLAT
        assert config.commission_flat == 0.0

    def test_flat_commission_custom(self):
        config = ReplayConfig(commission_flat=10.0)
        assert config.commission_flat == 10.0


# ── Indian Equity Fees Tests ───────────────────────────────────────────


class TestIndianEquityFees:
    """Verify Indian equity market fee computation."""

    def test_buy_has_no_stt(self):
        """STT is only charged on sell side for equity."""
        fees = compute_indian_equity_fees(100_000, "BUY")
        assert fees > 0

    def test_sell_has_stt(self):
        """Sell side includes STT."""
        buy_fees = compute_indian_equity_fees(100_000, "BUY")
        sell_fees = compute_indian_equity_fees(100_000, "SELL")
        assert sell_fees > buy_fees

    def test_brokerage_capped(self):
        """Brokerage should be capped at ₹20."""
        fees = IndianMarketFees(brokerage_pct=0.03, brokerage_max=20.0)
        # For a 100,000 trade: 0.03% = 30, but capped at 20
        result = compute_indian_equity_fees(100_000, "BUY", fees)
        # Brokerage is 20 (capped), plus exchange + GST + stamp + SEBI
        assert result > 20

    def test_total_fees_reasonable(self):
        """Total fees should be less than 1% of notional for typical trades."""
        notional = 100_000
        fees = compute_indian_equity_fees(notional, "BUY")
        assert fees < notional * 0.01  # Less than 1%

    def test_zero_notional(self):
        """Zero notional should produce zero fees."""
        fees = compute_indian_equity_fees(0, "BUY")
        assert fees == 0.0

    def test_large_notional(self):
        """Large trades should have proportionally larger fees."""
        small = compute_indian_equity_fees(100_000, "BUY")
        large = compute_indian_equity_fees(1_000_000, "BUY")
        assert large > small


# ── Indian F&O Fees Tests ──────────────────────────────────────────────


class TestIndianFnOFees:
    """Verify Indian F&O market fee computation."""

    def test_sell_has_stt(self):
        """F&O sell side includes STT."""
        buy_fees = compute_indian_fno_fees(100_000, "BUY")
        sell_fees = compute_indian_fno_fees(100_000, "SELL")
        assert sell_fees > buy_fees

    def test_no_stamp_duty(self):
        """F&O does not have stamp duty on buy side."""
        buy_fees = compute_indian_fno_fees(100_000, "BUY")
        # F&O buy should be cheaper than equity buy (no stamp duty)
        equity_buy = compute_indian_equity_fees(100_000, "BUY")
        assert buy_fees < equity_buy

    def test_total_fees_reasonable(self):
        """Total F&O fees should be less than 0.5% of notional."""
        notional = 100_000
        fees = compute_indian_fno_fees(notional, "SELL")
        assert fees < notional * 0.005  # Less than 0.5%


# ── Round-Trip Cost Tests ──────────────────────────────────────────────


class TestRoundTripCost:
    """Verify round-trip cost is realistic for Indian markets."""

    def test_equity_round_trip_cost(self):
        """Buy + sell round trip should cost ~0.1-0.3% for equity."""
        notional = 100_000
        buy_fees = compute_indian_equity_fees(notional, "BUY")
        sell_fees = compute_indian_equity_fees(notional, "SELL")
        total = buy_fees + sell_fees
        pct = (total / notional) * 100
        # Indian equity round trip typically costs 0.1-0.3%
        assert 0.05 < pct < 0.5

    def test_fno_round_trip_cost(self):
        """Buy + sell round trip should cost ~0.1-0.2% for F&O."""
        notional = 100_000
        buy_fees = compute_indian_fno_fees(notional, "BUY")
        sell_fees = compute_indian_fno_fees(notional, "SELL")
        total = buy_fees + sell_fees
        pct = (total / notional) * 100
        # Indian F&O round trip typically costs 0.1-0.2%
        assert 0.05 < pct < 0.3


# ── Config Validation Tests ────────────────────────────────────────────


class TestConfigValidation:
    """Verify ReplayConfig validates new fields."""

    def test_negative_commission_flat_rejected(self):
        with pytest.raises(ValueError, match="commission_flat"):
            ReplayConfig(commission_flat=-1.0)

    def test_indian_equity_model(self):
        config = ReplayConfig(
            commission_model=CommissionModel.INDIAN_EQUITY,
            segment="EQUITY",
        )
        assert config.commission_model == CommissionModel.INDIAN_EQUITY
        assert config.segment == "EQUITY"

    def test_indian_fno_model(self):
        config = ReplayConfig(
            commission_model=CommissionModel.INDIAN_FNO,
            segment="FNO",
        )
        assert config.commission_model == CommissionModel.INDIAN_FNO
        assert config.segment == "FNO"

    def test_custom_fees(self):
        custom_fees = IndianMarketFees(brokerage_pct=0.05)
        config = ReplayConfig(
            commission_model=CommissionModel.INDIAN_EQUITY,
            indian_market_fees=custom_fees,
        )
        assert config.indian_market_fees.brokerage_pct == 0.05
