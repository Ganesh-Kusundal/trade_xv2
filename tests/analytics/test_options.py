from __future__ import annotations

import pandas as pd

from analytics.options.options_analytics import OptionsAnalytics


def test_options_pcr_and_max_pain() -> None:
    chain = pd.DataFrame(
        [
            {"strike": 100, "option_type": "CE", "oi": 10, "change_in_oi": 2, "volume": 100, "iv": 20, "ltp": 5, "ltp_change": 1, "delta": 0.6},
            {"strike": 110, "option_type": "CE", "oi": 40, "change_in_oi": 5, "volume": 200, "iv": 22, "ltp": 3, "ltp_change": 1, "delta": 0.4},
            {"strike": 100, "option_type": "PE", "oi": 30, "change_in_oi": -1, "volume": 80, "iv": 19, "ltp": 4, "ltp_change": -1, "delta": -0.4},
            {"strike": 110, "option_type": "PE", "oi": 20, "change_in_oi": -2, "volume": 90, "iv": 21, "ltp": 6, "ltp_change": -1, "delta": -0.6},
        ]
    )

    result = OptionsAnalytics().analyze("NIFTY", chain, spot_price=105)

    assert result.metrics["highest_call_oi_strike"] == 110
    assert result.metrics["highest_put_oi_strike"] == 100
    assert result.metrics["pcr"] == 50 / 50
    assert result.metrics["current_max_pain"] == 110
    assert "Call Buying" in result.signals
