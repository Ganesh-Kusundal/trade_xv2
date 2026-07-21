"""Backward-compat shim — canonical implementation is in application.services.trading_costs_service."""

from application.services.trading_costs_service import (  # noqa: F401
    CommissionModel,
    IndianMarketFees,
    SlippageModel,
    apply_slippage,
    compute_commission,
    compute_indian_equity_fees,
    compute_indian_fno_fees,
    compute_slippage_pct,
)

__all__ = [
    "CommissionModel",
    "IndianMarketFees",
    "SlippageModel",
    "apply_slippage",
    "compute_commission",
    "compute_indian_equity_fees",
    "compute_indian_fno_fees",
    "compute_slippage_pct",
]
