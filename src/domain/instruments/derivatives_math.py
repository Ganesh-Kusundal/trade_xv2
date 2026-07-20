"""Pure-domain derivatives formulas — no analytics package imports.

Normative for Future/Option methods (OBJECT_MODEL PR-4).
European Black–Scholes, Brent IV, basis / cost-of-carry helpers.
"""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal

from domain.constants.market import DEFAULT_TICK_SIZE

# Actual/365.25 year fraction
_DAYS_PER_YEAR = Decimal("365.25")
_TWO_PI = 2.0 * math.pi
_SQRT_2PI = math.sqrt(_TWO_PI)


def year_fraction(expiry: date | None, *, today: date | None = None) -> Decimal | None:
    """T in years (Actual/365.25). None if expiry missing; 0 if expired."""
    if expiry is None:
        return None
    t0 = today or date.today()
    days = (expiry - t0).days
    if days < 0:
        return Decimal("0")
    return Decimal(days) / _DAYS_PER_YEAR


def _norm_cdf(x: float) -> float:
    """Standard normal CDF via math.erf."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / _SQRT_2PI


def black_scholes_price(
    spot: Decimal,
    strike: Decimal,
    t: Decimal,
    rate: Decimal,
    vol: Decimal,
    *,
    is_call: bool,
    dividend_yield: Decimal = Decimal("0"),
) -> Decimal | None:
    """European Black–Scholes price. Returns None if inputs invalid."""
    try:
        s = float(spot)
        k = float(strike)
        tau = float(t)
        r = float(rate)
        sigma = float(vol)
        q = float(dividend_yield)
    except (TypeError, ValueError):
        return None
    if s <= 0 or k <= 0 or sigma <= 0:
        return None
    if tau <= 0:
        # intrinsic
        if is_call:
            return max(Decimal("0"), spot - strike)
        return max(Decimal("0"), strike - spot)

    sqrt_t = math.sqrt(tau)
    d1 = (math.log(s / k) + (r - q + 0.5 * sigma * sigma) * tau) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    if is_call:
        price = s * math.exp(-q * tau) * _norm_cdf(d1) - k * math.exp(-r * tau) * _norm_cdf(d2)
    else:
        price = k * math.exp(-r * tau) * _norm_cdf(-d2) - s * math.exp(-q * tau) * _norm_cdf(-d1)
    if not math.isfinite(price):
        return None
    return Decimal(str(round(price, 8)))


def implied_volatility(
    market_price: Decimal,
    spot: Decimal,
    strike: Decimal,
    t: Decimal,
    rate: Decimal,
    *,
    is_call: bool,
    dividend_yield: Decimal = Decimal("0"),
    lo: float = 1e-6,
    hi: float = 5.0,
    max_iter: int = 100,
    tol: float = 1e-6,
) -> Decimal | None:
    """Brent-style bisection on BS residual for IV. None on non-converge."""
    try:
        target = float(market_price)
        if target <= 0:
            return None
    except (TypeError, ValueError):
        return None

    def residual(vol: float) -> float:
        px = black_scholes_price(
            spot,
            strike,
            t,
            rate,
            Decimal(str(vol)),
            is_call=is_call,
            dividend_yield=dividend_yield,
        )
        if px is None:
            return 1e9
        return float(px) - target

    f_lo = residual(lo)
    f_hi = residual(hi)
    if f_lo * f_hi > 0:
        # expand hi once
        hi2 = hi
        for _ in range(5):
            hi2 *= 1.5
            f_hi = residual(hi2)
            if f_lo * f_hi <= 0:
                hi = hi2
                break
        else:
            return None

    a, b = lo, hi
    fa, _fb = residual(a), residual(b)
    for _ in range(max_iter):
        mid = 0.5 * (a + b)
        fm = residual(mid)
        if abs(fm) < tol or abs(b - a) < tol:
            return Decimal(str(round(mid, 8)))
        if fa * fm <= 0:
            b, _fb = mid, fm
        else:
            a, fa = mid, fm
    return None


def option_payoff(spot: Decimal, strike: Decimal, *, is_call: bool) -> Decimal:
    """Vanilla European exercise value."""
    if is_call:
        return max(Decimal("0"), spot - strike)
    return max(Decimal("0"), strike - spot)


def moneyness_label(
    spot: Decimal,
    strike: Decimal,
    *,
    is_call: bool,
    tick_size: Decimal = DEFAULT_TICK_SIZE,
) -> str:
    """ITM / ATM / OTM with ATM band = max(tick, 0.05% of spot)."""
    band = max(tick_size, abs(spot) * Decimal("0.0005"))
    if abs(spot - strike) <= band:
        return "ATM"
    if is_call:
        return "ITM" if spot > strike else "OTM"
    return "ITM" if spot < strike else "OTM"


def future_basis(futures_ltp: Decimal | None, spot: Decimal | None) -> Decimal | None:
    """F - S; None if either missing."""
    if futures_ltp is None or spot is None:
        return None
    return futures_ltp - spot


def cost_of_carry_basis(
    futures_ltp: Decimal | None,
    spot: Decimal | None,
    t: Decimal | None,
    rate: Decimal | None,
) -> Decimal | None:
    """If rate is None: implied continuous rate ln(F/S)/T.
    If rate given: F - S*exp(r*T) (basis vs theoretical forward).
    """
    if futures_ltp is None or spot is None or t is None:
        return None
    if spot <= 0 or t <= 0:
        return None
    f = float(futures_ltp)
    s = float(spot)
    tau = float(t)
    if rate is None:
        if f <= 0:
            return None
        r_imp = math.log(f / s) / tau
        return Decimal(str(round(r_imp, 8)))
    r = float(rate)
    theo = s * math.exp(r * tau)
    return futures_ltp - Decimal(str(round(theo, 8)))


def map_underlying_cash_exchange(derivative_exchange: str) -> str:
    """NFO/MCX futures → cash exchange for spot quote (v1: NSE for NFO)."""
    ex = (derivative_exchange or "NSE").upper()
    if ex == "NFO":
        return "NSE"
    if ex == "BFO":
        return "BSE"
    return "NSE"
