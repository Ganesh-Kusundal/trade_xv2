"""Market data check strategy.

Tests quote, depth, and historical data endpoints via domain session.
"""

from __future__ import annotations

from interface.ui.commands.doctor.checks import CheckResult, CheckStrategy
from interface.ui.services.broker_service import BrokerService


class MarketDataCheck(CheckStrategy):
    """Test market data endpoints: quote, depth, and historical.

    Parameters
    ----------
    quick_mode : bool
        If True, skip slower checks (depth, historical data).
    """

    def __init__(self, quick_mode: bool = False) -> None:
        self.quick_mode = quick_mode

    def execute(self, broker_service: BrokerService | None) -> list[CheckResult]:
        """Test quote, depth, and historical data endpoints."""
        results: list[CheckResult] = []

        if broker_service is None:
            results.append(CheckResult("Market Data", "FAIL", "No broker service available"))
            return results

        from interface.ui.services.active_session import get_active_session
        from interface.ui.services.market_access import fetch_depth, fetch_history, refresh_quote

        session = get_active_session(broker_service)
        try:
            symbol = "RELIANCE"
            try:
                q = refresh_quote(session, symbol)
                if q is not None and q.ltp > 0:
                    results.append(
                        CheckResult(
                            "Quote",
                            "PASS",
                            f"{symbol}: LTP={q.ltp:.2f} | O={q.open:.2f} H={q.high:.2f} "
                            f"L={q.low:.2f} C={q.close:.2f} Vol={q.volume:,}",
                        )
                    )
                else:
                    results.append(
                        CheckResult(
                            "Quote",
                            "WARN",
                            f"{symbol} returned quote with LTP=0 (paper/mock?)",
                        )
                    )
            except Exception as exc:
                results.append(CheckResult("Quote", "FAIL", f"Quote failed: {exc}"))

            if self.quick_mode:
                results.append(CheckResult("Market Depth", "INFO", "Skipped (--quick mode)"))
            else:
                try:
                    depth = fetch_depth(session, symbol)
                    if depth is not None:
                        n_bids = len(depth.bids or [])
                        n_asks = len(depth.asks or [])
                        if n_bids > 0 or n_asks > 0:
                            results.append(
                                CheckResult(
                                    "Market Depth",
                                    "PASS",
                                    f"{symbol}: {n_bids} bid(s), {n_asks} ask(s)",
                                )
                            )
                        else:
                            results.append(
                                CheckResult(
                                    "Market Depth",
                                    "WARN",
                                    f"{symbol}: depth returned empty levels",
                                )
                            )
                    else:
                        results.append(
                            CheckResult("Market Depth", "WARN", f"{symbol}: depth returned None")
                        )
                except Exception as exc:
                    results.append(CheckResult("Market Depth", "FAIL", f"Depth failed: {exc}"))

            if self.quick_mode:
                results.append(CheckResult("Historical Data", "INFO", "Skipped (--quick mode)"))
            else:
                try:
                    hist = fetch_history(session, symbol, days=5)
                    n = getattr(hist, "bar_count", None)
                    if n is None and hasattr(hist, "__len__"):
                        n = len(hist)
                    if n:
                        results.append(
                            CheckResult(
                                "Historical Data",
                                "PASS",
                                f"{symbol}: {n} candles",
                            )
                        )
                    else:
                        results.append(
                            CheckResult(
                                "Historical Data",
                                "WARN",
                                f"{symbol}: empty history returned",
                            )
                        )
                except Exception as exc:
                    results.append(CheckResult("Historical Data", "FAIL", f"History failed: {exc}"))
        finally:
            session.close()

        return results
