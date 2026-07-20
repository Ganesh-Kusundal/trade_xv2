"""Options schemas (Chain, Greeks, PCR, Max Pain, IV Surface)."""

from __future__ import annotations

from pydantic import BaseModel

from domain.value_objects.money import MoneyField


class PCRResponse(BaseModel):
    """Put-Call Ratio data."""

    timestamp: int
    underlying: str
    expiry_kind: str  # WEEK, MONTH
    expiry_date: str
    spot: float
    pcr_volume: float | None = None
    pcr_oi: float | None = None
    total_ce_volume: float
    total_pe_volume: float
    total_ce_oi: float
    total_pe_oi: float


class MaxPainResponse(BaseModel):
    """Max Pain data."""

    timestamp: int
    underlying: str
    expiry_kind: str
    expiry_date: str
    spot: float
    max_pain_strike: float
    total_pain_at_max_pain: float
    distance_from_spot: float
    position_vs_spot: str  # below_spot, above_spot, at_spot


class IVSurfaceResponse(BaseModel):
    """IV surface data."""

    timestamp: int
    underlying: str
    expiry_kind: str
    expiry_date: str
    spot: float
    atm_strike: float
    atm_iv: float
    otm_put_iv: float
    otm_call_iv: float
    iv_skew: float
    put_call_iv_ratio: float | None = None
    days_to_expiry: int


class OptionContract(BaseModel):
    """Single option contract with Greeks."""

    symbol: str
    expiry: str
    strike: MoneyField
    option_type: str  # CE or PE
    ltp: MoneyField
    bid: MoneyField | None = None
    ask: MoneyField | None = None
    volume: float
    oi: float
    iv: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None


class OptionChainResponse(BaseModel):
    """Option chain response."""

    underlying: str
    expiry: str
    contracts: list[OptionContract]
    count: int
