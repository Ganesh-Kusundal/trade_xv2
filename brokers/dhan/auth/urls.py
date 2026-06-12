"""Dhan v2 REST URL resolver.

Generates fully-qualified endpoint URLs for every Dhan API surface,
respecting ``LIVE`` vs ``SANDBOX`` environment and any custom ``restBaseUrl``
set in :class:`~broker.dhan.DhanConnectionSettings`.

Design reference: Trade_J ``DhanApiUrlResolver``.
"""

from __future__ import annotations

from datetime import date
from typing import Any

LIVE_BASE_URL = "https://api.dhan.co/v2"
SANDBOX_BASE_URL = "https://sandbox.dhan.co/v2"
INSTRUMENT_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"


class DhanApiUrlResolver:
    """URL resolver matching Trade_J's DhanApiUrlResolver."""

    def __init__(self, settings: Any) -> None:
        base_url: str = getattr(settings, "rest_base_url", "") or (
            SANDBOX_BASE_URL if getattr(settings, "is_sandbox", False) else LIVE_BASE_URL
        )
        self._base_url = base_url.rstrip("/")

    # ── Option chain ────────────────────────────────────────────────

    def option_chain_url(self) -> str:
        return f"{self._base_url}/optionchain"

    def option_chain_expiry_list_url(self) -> str:
        return f"{self._base_url}/optionchain/expirylist"

    # ── Historical data ─────────────────────────────────────────────

    def historical_daily_url(self) -> str:
        return f"{self._base_url}/charts/historical"

    def historical_intraday_url(self) -> str:
        return f"{self._base_url}/charts/intraday"

    # ── Orders ──────────────────────────────────────────────────────

    def margin_calculator_url(self) -> str:
        return f"{self._base_url}/margincalculator"

    def pnl_exit_url(self) -> str:
        return f"{self._base_url}/pnlExit"

    def alert_orders_url(self) -> str:
        return f"{self._base_url}/alerts/orders"

    def alert_order_url(self, alert_id: str) -> str:
        return f"{self.alert_orders_url()}/{alert_id}"

    def orders_url(self) -> str:
        return f"{self._base_url}/orders"

    def order_url(self, order_id: str) -> str:
        return f"{self.orders_url()}/{order_id}"

    def order_by_correlation_id_url(self, correlation_id: str) -> str:
        return f"{self.orders_url()}/external/{correlation_id}"

    # ── Trades ──────────────────────────────────────────────────────

    def trades_url(self) -> str:
        return f"{self._base_url}/trades"

    def trades_url_for_order(self, order_id: str) -> str:
        return f"{self.trades_url()}/{order_id}"

    def super_order_url(self) -> str:
        return f"{self._base_url}/super-order"

    def super_orders_url(self) -> str:
        suffix = "super-orders" if "sandbox" in self._base_url else "super/orders"
        return f"{self._base_url}/{suffix}"

    def super_order_by_id_url(self, order_id: str) -> str:
        return f"{self.super_orders_url()}/{order_id}"

    def super_order_leg_url(self, order_id: str, leg_name: str) -> str:
        return f"{self.super_order_by_id_url(order_id)}/{leg_name}"

    def forever_orders_url(self) -> str:
        suffix = "forever-orders" if "sandbox" in self._base_url else "forever/orders"
        return f"{self._base_url}/{suffix}"

    def forever_orders_all_url(self) -> str:
        suffix = "forever-orders" if "sandbox" in self._base_url else "forever/all"
        return f"{self._base_url}/{suffix}"

    def forever_order_url(self, order_id: str) -> str:
        return f"{self.forever_orders_url()}/{order_id}"

    def slice_order_url(self) -> str:
        return f"{self._base_url}/orders/slicing"

    # ── Account ─────────────────────────────────────────────────────

    def kill_switch_url(self) -> str:
        return f"{self._base_url}/killswitch"

    def ledger_url(self, from_date: date, to_date: date) -> str:
        return (
            f"{self._base_url}/ledger"
            f"?from-date={from_date.isoformat()}"
            f"&to-date={to_date.isoformat()}"
        )

    def profile_url(self) -> str:
        return f"{self._base_url}/profile"

    def fund_limit_url(self) -> str:
        return f"{self._base_url}/fundlimit"

    # ── Portfolio ───────────────────────────────────────────────────

    def positions_url(self) -> str:
        return f"{self._base_url}/positions"

    def holdings_url(self) -> str:
        return f"{self._base_url}/holdings"

    # ── Market feed ─────────────────────────────────────────────────

    def market_feed_ltp_url(self) -> str:
        return f"{self._base_url}/marketfeed/ltp"

    def market_feed_quote_url(self) -> str:
        return f"{self._base_url}/marketfeed/quote"

    def market_feed_ohlc_url(self) -> str:
        return f"{self._base_url}/marketfeed/ohlc"
