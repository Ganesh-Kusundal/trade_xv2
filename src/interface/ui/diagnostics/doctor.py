"""Diagnostics runner for doctor check commands — domain session API."""

from __future__ import annotations

from interface.ui.services.active_session import get_active_session
from interface.ui.services.broker_service import BrokerService
from interface.ui.services.market_access import fetch_funds, refresh_quote


class DoctorDiagnostics:
    """Runs connectivity, authentication, and API sanity checks on any broker."""

    def __init__(self, broker_service: BrokerService, gateway=None):
        self._broker_service = broker_service
        self._gw = gateway

    def run_all_checks(self) -> list[tuple[str, str, str]]:
        checks: list[tuple[str, str, str]] = []

        if self._gw is None and self._broker_service.active_broker is None:
            checks.append(("Broker Backend", "FAIL", "No broker gateway available — configure credentials."))
            return checks

        session = get_active_session(self._broker_service)
        try:
            # 1. Authentication Check
            try:
                balance = fetch_funds(session)
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
                    ("Authentication Check", "WARNING", "Funds check not implemented for this broker")
                )
            except Exception as e:
                checks.append(
                    ("Authentication Check", "FAIL", f"Authentication check failed: {type(e).__name__}: {e}")
                )

            # 2. Quote Check
            try:
                symbol = "RELIANCE"
                quote = refresh_quote(session, symbol)
                ltp = getattr(quote, "ltp", None) or (quote.get("ltp") if isinstance(quote, dict) else 0)
                if ltp and float(ltp) > 0:
                    checks.append(
                        (
                            "Quote Check",
                            "PASS",
                            f"Retrieved live quote for {symbol}: LTP={float(ltp):.2f}",
                        )
                    )
                else:
                    checks.append(("Quote Check", "FAIL", f"No valid LTP for {symbol}"))
            except Exception as e:
                checks.append(("Quote Check", "FAIL", f"Quote check failed: {type(e).__name__}: {e}"))
        finally:
            session.close()

        return checks
