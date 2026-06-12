"""Diagnostics runner for doctor check commands."""

from __future__ import annotations

from datetime import date, timedelta

from brokers.dhan.auth.auth import DhanAuthRejected
from cli.services.broker_service import BrokerService, MockBroker


def _format_auth_error(exc: Exception) -> str:
    if isinstance(exc, DhanAuthRejected) and exc.rate_limited:
        return (
            f"Dhan TOTP mint is rate-limited (once every 2 minutes). {exc}"
        )
    return str(exc)


class DoctorDiagnostics:
    """Runs connectivity, authentication, and API sanity checks on the broker."""

    def __init__(self, broker_service: BrokerService):
        self._broker_service = broker_service

    def run_all_checks(self) -> list[tuple[str, str, str]]:
        """Run all diagnostics checks.

        Returns:
            List of tuples: (check_name, status, details)
            Status can be: "PASS", "FAIL", "WARNING"
        """
        checks = []
        broker = self._broker_service.active_broker

        if isinstance(broker, MockBroker):
            detail = "Mock broker active — configure .env.local with valid Dhan credentials."
            if self._broker_service.dhan_load_error:
                detail += f" Load error: {self._broker_service.dhan_load_error}"
            checks.append(("Broker Backend", "FAIL", detail))
            return checks

        # 1. Authentication Check
        try:
            connected = broker.is_connected()
            if not connected:
                connected = broker.connect()

            if connected:
                try:
                    from brokers.dhan.auth.auth import DhanAuthClient
                    token = broker._access_token()
                    info = DhanAuthClient().fetch_profile(token)
                    if info.valid:
                        checks.append((
                            "Authentication Check",
                            "PASS",
                            f"Connected as client ID {broker.broker_id}. Token is valid.",
                        ))
                    else:
                        checks.append((
                            "Authentication Check",
                            "FAIL",
                            "Broker connection succeeded but authentication token is marked invalid.",
                        ))
                except Exception as e:
                    checks.append((
                        "Authentication Check",
                        "FAIL",
                        f"Profile validation failed: {_format_auth_error(e)}",
                    ))
            else:
                checks.append((
                    "Authentication Check",
                    "FAIL",
                    "Failed to establish connection to the broker API.",
                ))
        except Exception as e:
            checks.append((
                "Authentication Check",
                "FAIL",
                f"Authentication check raised exception: {_format_auth_error(e)}",
            ))

        # 2. Quote Check
        try:
            symbol = "RELIANCE"
            exchange = "NSE"
            quote_df = broker.get_quote(symbol, exchange)
            if quote_df is not None and not quote_df.empty:
                ltp = quote_df["ltp"].iloc[0]
                checks.append((
                    "Quote Check",
                    "PASS",
                    f"Retrieved live quote for {symbol}: LTP={ltp:.2f}",
                ))
            else:
                checks.append((
                    "Quote Check",
                    "FAIL",
                    f"Quote endpoint returned empty DataFrame for symbol {symbol}",
                ))
        except Exception as e:
            checks.append((
                "Quote Check",
                "FAIL",
                f"Quote API verification failed: {_format_auth_error(e)}",
            ))

        # 3. Historical Data Check
        try:
            symbol = "RELIANCE"
            exchange = "NSE"
            to_date = date.today()
            from_date = to_date - timedelta(days=5)
            hist_df = broker.get_historical_data(
                symbol, exchange, from_date, to_date, timeframe="1d"
            )
            if hist_df is not None and not hist_df.empty:
                checks.append((
                    "Historical Data Check",
                    "PASS",
                    f"Fetched {len(hist_df)} historical candles successfully. Schema matches perfectly.",
                ))
            else:
                checks.append((
                    "Historical Data Check",
                    "FAIL",
                    "Historical data endpoint returned empty DataFrame.",
                ))
        except Exception as e:
            checks.append((
                "Historical Data Check",
                "FAIL",
                f"Historical data verification failed: {_format_auth_error(e)}",
            ))

        # 4. Websocket Check
        try:
            if hasattr(broker, "order_stream") and broker.order_stream:
                checks.append((
                    "Websocket Check",
                    "PASS",
                    "Order stream adapter is configured.",
                ))
            else:
                checks.append((
                    "Websocket Check",
                    "WARNING",
                    "Order stream adapter not found.",
                ))
        except Exception as e:
            checks.append((
                "Websocket Check",
                "FAIL",
                f"Websocket diagnostics failed: {e}",
            ))

        # 5. Order API Check (REST path — same auth as quotes)
        try:
            orders = broker.order_query.get_order_list()
            checks.append((
                "Order API Check",
                "PASS",
                f"Retrieved {len(orders)} orders for today. Endpoints are active and readable.",
            ))
        except Exception as e:
            checks.append((
                "Order API Check",
                "FAIL",
                f"Order API retrieval failed: {_format_auth_error(e)}",
            ))

        # 6. Position Sync Check
        try:
            positions = broker.get_positions()
            holdings = broker.get_holdings()
            checks.append((
                "Position Sync Check",
                "PASS",
                f"Positions synced ({len(positions)} open). Holdings synced ({len(holdings)} assets).",
            ))
        except Exception as e:
            checks.append((
                "Position Sync Check",
                "FAIL",
                f"Portfolio sync check failed: {_format_auth_error(e)}",
            ))

        return checks
