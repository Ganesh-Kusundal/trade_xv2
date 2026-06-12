"""Upstox API URL resolver.

Mirrors Trade_J ``UpstoxEndpoints`` and ``UpstoxApiEnvironment``.

Upstox splits its API across two hosts:

* ``api.upstox.com`` (v2) — market data REST, option chain, profile, positions,
  holdings, funds, GTT authorize, news, etc.
* ``api-hft.upstox.com`` (v3) — order place/modify/cancel/details, GTT
  place/modify/cancel, feed authorize, token-request v3.

Sandbox uses ``sandbox-api.upstox.com`` and ``sandbox-api-hft.upstox.com``.
"""

from __future__ import annotations

from typing import Any


class UpstoxApiUrlResolver:
    """Build full URLs for every Upstox endpoint."""

    def __init__(self, settings: Any) -> None:
        self._settings = settings

    def _v2(self) -> str:
        return f"{self._settings.base_v2}/v2"

    def _v3(self) -> str:
        return f"{self._settings.base_v2}/v3"

    def _hft(self) -> str:
        return f"{self._settings.base_hft}/v3"

    # ── Auth ────────────────────────────────────────────────────────
    def auth_dialog_url(self) -> str:
        return f"{self._v2()}/login/authorization/dialog"

    def auth_token_url(self) -> str:
        return f"{self._v2()}/login/authorization/token"

    def token_request_v3_url(self, client_id: str) -> str:
        return f"{self._v3()}/login/auth/token/request/{client_id}"

    def logout_url(self) -> str:
        return f"{self._v2()}/logout"

    def profile_url(self) -> str:
        return f"{self._v2()}/user/profile"

    # ── Market data (v2) ────────────────────────────────────────────
    def market_quote_ltp_url(self) -> str:
        return f"{self._v2()}/market-quote/ltp"

    def market_quote_full_url(self) -> str:
        return f"{self._v2()}/market-quote/quotes"

    def market_quote_ohlc_url(self) -> str:
        return f"{self._v2()}/market-quote/ohlc"

    def market_quote_order_book_url(self) -> str:
        return f"{self._v2()}/market-quote/order-book"

    def historical_candle_url(
        self, instrument_key: str, interval: str, to_date: str, from_date: str
    ) -> str:
        return f"{self._v2()}/historical-candle/{instrument_key}/{interval}/{to_date}/{from_date}"

    def market_status_url(self, exchange: str = "NSE") -> str:
        return f"{self._v2()}/market/status/{exchange}"

    def market_holidays_url(self) -> str:
        return f"{self._v2()}/market/holidays"

    # ── V3 market quote (Plus plan) ─────────────────────────────────
    def market_quote_full_v3_url(self) -> str:
        return f"{self._v3()}/market-quote/full"

    def market_quote_option_greeks_v3_url(self) -> str:
        return f"{self._v3()}/market-quote/option-greeks"

    def market_quote_ltp_v3_url(self) -> str:
        return f"{self._v3()}/market-quote/ltp"

    # ── WebSocket authorize (v2/v3, HFT) ───────────────────────────
    def feed_authorize_v2_url(self) -> str:
        return f"{self._v2()}/feed/market-data-feed/authorize"

    def feed_authorize_v3_url(self) -> str:
        return f"{self._hft()}/feed/market-data-feed/authorize"

    def portfolio_stream_authorize_url(self) -> str:
        return f"{self._v2()}/feed/portfolio-stream-feed/authorize"

    # ── Orders (v3, HFT) ────────────────────────────────────────────
    def place_order_v3_url(self) -> str:
        return f"{self._hft()}/order/place"

    def modify_order_v3_url(self) -> str:
        return f"{self._hft()}/order/modify"

    def cancel_order_v3_url(self) -> str:
        return f"{self._hft()}/order/cancel"

    def multi_order_v2_url(self) -> str:
        return f"{self._v2()}/order/multi/place"

    def order_details_url(self) -> str:
        return f"{self._hft()}/order/details"

    def order_history_url(self) -> str:
        return f"{self._hft()}/order/history"

    def trades_for_day_url(self) -> str:
        return f"{self._hft()}/order/trades/get-trades-for-day"

    # ── Orders (v2 legacy) ──────────────────────────────────────────
    def place_order_v2_url(self) -> str:
        return f"{self._v2()}/order/place"

    def modify_order_v2_url(self) -> str:
        return f"{self._v2()}/order/modify"

    def cancel_order_v2_url(self) -> str:
        return f"{self._v2()}/order/cancel"

    # ── GTT (v3, HFT) ───────────────────────────────────────────────
    def gtt_place_url(self) -> str:
        return f"{self._hft()}/order/gtt/place"

    def gtt_modify_url(self) -> str:
        return f"{self._hft()}/order/gtt/modify"

    def gtt_cancel_url(self) -> str:
        return f"{self._hft()}/order/gtt/cancel"

    def gtt_orders_url(self) -> str:
        return f"{self._hft()}/order/gtt/orders"

    def gtt_order_details_url(self) -> str:
        return f"{self._hft()}/order/gtt/order-details"

    # ── Portfolio (v2) ──────────────────────────────────────────────
    def positions_url(self) -> str:
        return f"{self._v2()}/portfolio/short-term-positions"

    def holdings_url(self) -> str:
        return f"{self._v2()}/portfolio/long-term-holdings"

    def funds_url(self) -> str:
        return f"{self._v2()}/user/get-funds-and-margin"

    def convert_position_url(self) -> str:
        return f"{self._v2()}/portfolio/convert-position"

    def mtf_positions_v3_url(self) -> str:
        return f"{self._v3()}/portfolio/mtf-positions"

    # ── Options (v2) ────────────────────────────────────────────────
    def option_contracts_url(self) -> str:
        return f"{self._v2()}/option/contracts"

    def option_chain_url(self) -> str:
        return f"{self._v2()}/option/chain"

    def option_expiry_url(self) -> str:
        return f"{self._v2()}/option/expiry"

    def option_greeks_url(self) -> str:
        return f"{self._v2()}/option/greeks"

    # ── Margin (v2) ─────────────────────────────────────────────────
    def margin_requirement_url(self) -> str:
        return f"{self._v2()}/margin/requirement"

    def charges_brokerage_url(self) -> str:
        return f"{self._v2()}/charges/brokerage"

    def charges_margin_url(self) -> str:
        return f"{self._v2()}/charges/margin"

    # ── Expired instruments (Plus plan, v2) ─────────────────────────
    def expired_expiries_url(self) -> str:
        return f"{self._v2()}/expired-instruments/expiries"

    def expired_option_contract_url(self) -> str:
        return f"{self._v2()}/expired-instruments/option/contract"

    def expired_historical_candle_url(
        self, key: str, interval: str, to_date: str, from_date: str
    ) -> str:
        return (
            f"{self._v2()}/expired-instruments/historical-candle/{key}"
            f"/{interval}/{to_date}/{from_date}"
        )

    def expired_future_contracts_url(self) -> str:
        return f"{self._v2()}/expired-instruments/future/contract"

    # ── News (v2) ───────────────────────────────────────────────────
    def news_url(self) -> str:
        return f"{self._v2()}/news"

    # ── Market intelligence (v2) ────────────────────────────────────
    def pcr_url(self) -> str:
        return f"{self._v2()}/market/pcr"

    def max_pain_url(self) -> str:
        return f"{self._v2()}/market/max-pain"

    def oi_url(self) -> str:
        return f"{self._v2()}/market/oi"

    def fii_url(self) -> str:
        return f"{self._v2()}/market/fii"

    def dii_url(self) -> str:
        return f"{self._v2()}/market/dii"

    def smartlist_futures_url(self) -> str:
        return f"{self._v2()}/market/smartlist/futures"

    def smartlist_options_url(self) -> str:
        return f"{self._v2()}/market/smartlist/options"

    # ── Instruments (v2) ────────────────────────────────────────────
    def instrument_master_url(self, segment: str) -> str:
        return f"{self._v2()}/instrument/master/{segment}"

    def instrument_search_url(self) -> str:
        return f"{self._v2()}/instrument/search"

    def instrument_complete_url(self) -> str:
        return "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"

    # ── User / risk (v2/v3) ─────────────────────────────────────────
    def kill_switch_url(self) -> str:
        return f"{self._v2()}/user/kill-switch"

    def static_ip_url(self) -> str:
        return f"{self._v2()}/user/ip"

    def user_fund_margin_v3_url(self) -> str:
        return f"{self._v3()}/user/fund-margin"

    # ── Payments (v2) ───────────────────────────────────────────────
    def payouts_url(self) -> str:
        return f"{self._v2()}/payments/payouts"

    # ── IPO / MF / Fundamentals (v2) ────────────────────────────────
    def ipo_url(self) -> str:
        return f"{self._v2()}/ipo"

    def mutual_funds_holdings_url(self) -> str:
        return f"{self._v2()}/mutual-funds/holdings"

    def mutual_funds_order_url(self) -> str:
        return f"{self._v2()}/mutual-funds/order"

    def fundamentals_financials_url(self, isin: str, statement: str) -> str:
        return f"{self._v2()}/fundamentals/{isin}/{statement}"
