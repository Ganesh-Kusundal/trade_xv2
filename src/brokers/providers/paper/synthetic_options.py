"""Synthetic option chain and futures chain generation for paper trading.

Generates realistic-looking but synthetic market data with:
- Moneyness-based delta approximation
- OI distribution peaking near ATM
- IV smile/skew
- Greek approximations (delta, gamma, theta, vega, rho)

Extracted from PaperGateway to keep the gateway class focused on delegation.
"""

from __future__ import annotations

import math
from typing import Any


def generate_option_chain(
    underlying: str,
    exchange: str,
    spot: float,
    expiry: str | None = None,
) -> dict[str, Any]:
    """Generate a synthetic option chain with greeks.

    Returns a dict suitable for ``OptionChain.from_dict()``.
    """
    import numpy as np

    strikes = [round(spot + i * 50, 0) for i in range(-10, 11)]
    chain = []
    for strike in strikes:
        m = (spot - float(strike)) / max(spot, 1.0)
        call_delta = max(0.05, min(0.95, 0.5 + m * 2.5))
        put_delta = call_delta - 1.0
        dist = abs(float(strike) - spot)
        oi_scale = max(1000, int(50_000 * math.exp(-((dist / 150.0) ** 2))))
        call_oi = oi_scale + int(np.random.randint(0, 5000))
        put_oi = int(oi_scale * 0.9) + int(np.random.randint(0, 5000))
        iv = round(0.12 + abs(m) * 0.15 + np.random.uniform(0, 0.03), 4)
        chain.append(
            {
                "strike": strike,
                "call": {
                    "ltp": round(max(0.05, spot - strike + np.random.uniform(5, 50)), 2),
                    "oi": call_oi,
                    "volume": int(np.random.randint(100, 10000)),
                    "iv": iv,
                    "greeks": {
                        "delta": round(call_delta, 4),
                        "gamma": round(0.01 * math.exp(-((dist / 100.0) ** 2)), 6),
                        "theta": round(-0.05 - abs(m) * 0.02, 4),
                        "vega": round(0.1 * math.exp(-((dist / 120.0) ** 2)), 4),
                        "rho": round(0.01 * call_delta, 4),
                    },
                },
                "put": {
                    "ltp": round(max(0.05, strike - spot + np.random.uniform(5, 50)), 2),
                    "oi": put_oi,
                    "volume": int(np.random.randint(100, 10000)),
                    "iv": iv,
                    "greeks": {
                        "delta": round(put_delta, 4),
                        "gamma": round(0.01 * math.exp(-((dist / 100.0) ** 2)), 6),
                        "theta": round(-0.05 - abs(m) * 0.02, 4),
                        "vega": round(0.1 * math.exp(-((dist / 120.0) ** 2)), 4),
                        "rho": round(0.01 * put_delta, 4),
                    },
                },
            }
        )
    return {
        "underlying": underlying,
        "exchange": exchange,
        "expiry": expiry or "2026-07-30",
        "spot": spot,
        "strikes": chain,
    }


def generate_future_chain(underlying: str, spot: float) -> list[dict[str, Any]]:
    """Generate a synthetic futures chain with 3 monthly expiries."""
    import numpy as np

    from datetime import timedelta

    from domain.ports.time_service import get_current_clock

    expiries = [
        (get_current_clock().now() + timedelta(days=30 * i)).strftime("%Y-%m-%d")
        for i in range(1, 4)
    ]
    contracts = []
    for exp in expiries:
        contracts.append(
            {
                "expiry": exp,
                "ltp": round(spot * (1 + np.random.uniform(-0.02, 0.03)), 2),
                "volume": int(np.random.randint(10000, 500000)),
                "oi": int(np.random.randint(50000, 1000000)),
                "change": round(np.random.uniform(-2, 2), 2),
            }
        )
    return contracts
