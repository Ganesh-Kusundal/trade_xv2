"""Diagnostics runner for doctor check commands — broker-agnostic version."""

from __future__ import annotations

from brokers.common.gateway import MarketDataGateway
from cli.services.broker_service import BrokerService


class DoctorDiagnostics:
    """Runs connectivity, authentication, and API sanity checks on any broker."""

    def __init__(self, broker_service: BrokerService, gateway: MarketDataGateway | None = None):
        self._broker_service = broker_service
        self._gw = gateway

    def run_all_checks(self) -> list[tuple[str, str, str]]:
        """Run all diagnostics checks.

        Returns:
            List of tuples: (check_name, status, details)
            Status can be: "PASS", "FAIL", "WARNING"
        """
        checks = []

        if self._gw is None:
            detail = "No broker gateway available — configure broker credentials."
            checks.append(("Broker Backend", "FAIL", detail))
            return checks

        gw = self._gw

        # 1. Authentication Check
        try:
            balance = gw.funds()
            if isinstance(balance, dict):
                available = balance.get("available_balance", balance.get("available_margin", 0))
            else:
                available = getattr(
                    balance, "available_balance", getattr(balance, "available_margin", 0)
                )
            checks.append(
                (
                    "Authentication Check",
                    "PASS",
                    f"Connected and authenticated. Available balance: {float(available):,.2f}",
                )
            )
        except NotImplementedError:
            checks.append(
                (
                    "Authentication Check",
                    "WARNING",
                    "Funds check not implemented for this broker",
                )
            )
        except Exception as e:
            checks.append(
                (
                    "Authentication Check",
                    "FAIL",
                    f"Authentication check failed: {type(e).__name__}: {e}",
                )
            )

        # 2. Quote Check
        try:
            symbol = "RELIANCE"
            quote = gw.quote(symbol)
            if quote and isinstance(quote, dict):
                ltp = quote.get("ltp", 0)
                if ltp and float(ltp) > 0:
                    checks.append(
                        (
                            "Quote Check",
                            "PASS",
                            f"Retrieved live quote for {symbol}: LTP={float(ltp):.2f}",
                        )
                    )
                else:
                    checks.append(
                        (
                            "Quote Check",
                            "FAIL",
                            f"Quote endpoint returned no data for symbol {symbol}",
                        )
                    )
            else:
                checks.append(
                    (
                        "Quote Check",
                        "FAIL",
                        f"Quote endpoint returned invalid data for {symbol}",
                    )
                )
        except NotImplementedError:
            checks.append(
                (
                    "Quote Check",
                    "WARNING",
                    "Quote check not implemented for this broker",
                )
            )
        except Exception as e:
            checks.append(
                (
                    "Quote Check",
                    "FAIL",
                    f"Quote API verification failed: {type(e).__name__}: {e}",
                )
            )

        # 3. Historical Data Check
        try:
            symbol = "RELIANCE"
            df = gw.history(symbol, timeframe="1D", lookback_days=7)
            if df is not None and not df.empty:
                rows = len(df)
                latest = df["timestamp"].max() if "timestamp" in df.columns else "N/A"
                checks.append(
                    (
                        "Historical Data Check",
                        "PASS",
                        f"Retrieved {rows} candles for {symbol}, latest: {latest}",
                    )
                )
            else:
                checks.append(
                    (
                        "Historical Data Check",
                        "FAIL",
                        f"No historical data returned for {symbol}",
                    )
                )
        except NotImplementedError:
            checks.append(
                (
                    "Historical Data Check",
                    "WARNING",
                    "Historical data check not implemented for this broker",
                )
            )
        except Exception as e:
            checks.append(
                (
                    "Historical Data Check",
                    "FAIL",
                    f"Historical data check failed: {type(e).__name__}: {e}",
                )
            )

        # 4. Capabilities Check
        try:
            caps = gw.capabilities()
            supported_tfs = getattr(caps, "supported_timeframes", ())
            checks.append(
                (
                    "Capabilities Check",
                    "PASS",
                    f"Supported timeframes: {', '.join(supported_tfs) if supported_tfs else 'N/A'}",
                )
            )
        except Exception as e:
            checks.append(
                (
                    "Capabilities Check",
                    "FAIL",
                    f"Capabilities check failed: {type(e).__name__}: {e}",
                )
            )

        # 5. Instrument Search Check
        try:
            results = gw.search("RELIANCE")
            if results and len(results) > 0:
                checks.append(
                    (
                        "Instrument Search Check",
                        "PASS",
                        f"Found {len(results)} instruments for RELIANCE",
                    )
                )
            else:
                checks.append(
                    (
                        "Instrument Search Check",
                        "WARNING",
                        "No instruments found for RELIANCE",
                    )
                )
        except NotImplementedError:
            checks.append(
                (
                    "Instrument Search Check",
                    "WARNING",
                    "Instrument search not implemented for this broker",
                )
            )
        except Exception as e:
            checks.append(
                (
                    "Instrument Search Check",
                    "FAIL",
                    f"Instrument search failed: {type(e).__name__}: {e}",
                )
            )

        # 6. Describe Check
        try:
            desc = gw.describe()
            broker_name = desc.get("broker", desc.get("name", "Unknown"))
            checks.append(
                (
                    "Broker Identity Check",
                    "PASS",
                    f"Broker: {broker_name}",
                )
            )
        except Exception as e:
            checks.append(
                (
                    "Broker Identity Check",
                    "FAIL",
                    f"Describe failed: {type(e).__name__}: {e}",
                )
            )

        return checks
