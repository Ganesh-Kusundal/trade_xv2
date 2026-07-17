"""Shared Dhan test fixtures (single source of truth).

Consolidates all ``FakeHttpClient`` implementations and ``SAMPLE_ROWS``
data into one canonical location. Every Dhan test imports from here.

Methods consolidated from:
  - conftest.py: ``set_response()``, ``set_side_effect()``, ``calls_for()``,
    ``call_count``, ``update_token()``, ``close()``
  - test_chaos.py: ``_fail``, ``_fail_count``, ``_success_count``,
    ``_rate_limit_count``, failure simulation via ``ConnectionError``
  - test_edge_cases.py: ``SAMPLE_ROWS`` (absorbed into canonical dataset)
"""

from __future__ import annotations

from typing import Any


SAMPLE_ROWS = [
    # ── Index ──
    {
        "SEM_TRADING_SYMBOL": "NIFTY",
        "SEM_SMST_SECURITY_ID": "13",
        "SEM_EXM_EXCH_ID": "IDX_I",
        "SEM_INSTRUMENT_NAME": "INDEX",
        "SEM_LOT_UNITS": 1,
        "SEM_TICK_SIZE": 0.05,
        "SEM_CUSTOM_SYMBOL": "Nifty 50",
        "SM_SYMBOL_NAME": "NIFTY",
    },
    # ── NSE Equity ──
    {
        "SEM_TRADING_SYMBOL": "RELIANCE",
        "SEM_SMST_SECURITY_ID": "2885",
        "SEM_EXM_EXCH_ID": "NSE_EQ",
        "SEM_INSTRUMENT_NAME": "EQUITY",
        "SEM_LOT_UNITS": 1,
        "SEM_TICK_SIZE": 0.05,
        "SEM_CUSTOM_SYMBOL": "Reliance Industries",
        "SM_SYMBOL_NAME": "RELIANCE INDUSTRIES LTD",
    },
    # ── BSE Equity ──
    {
        "SEM_TRADING_SYMBOL": "RELIANCE",
        "SEM_SMST_SECURITY_ID": "532",
        "SEM_EXM_EXCH_ID": "BSE_EQ",
        "SEM_INSTRUMENT_NAME": "EQUITY",
        "SEM_LOT_UNITS": 1,
        "SEM_TICK_SIZE": 0.05,
        "SEM_CUSTOM_SYMBOL": "Reliance Industries",
        "SM_SYMBOL_NAME": "RELIANCE INDUSTRIES LTD",
    },
    # ── TCS Equity ──
    {
        "SEM_TRADING_SYMBOL": "TCS",
        "SEM_SMST_SECURITY_ID": "11536",
        "SEM_EXM_EXCH_ID": "NSE_EQ",
        "SEM_INSTRUMENT_NAME": "EQUITY",
        "SEM_LOT_UNITS": 1,
        "SEM_TICK_SIZE": 10,
        "SEM_CUSTOM_SYMBOL": "Tata Consultancy Services",
        "SM_SYMBOL_NAME": "TATA CONSULTANCY SERVICES LTD",
    },
    # ── NSE F&O Option (CE) ──
    {
        "SEM_TRADING_SYMBOL": "NIFTY-26Jun2026-25000-CE",
        "SEM_SMST_SECURITY_ID": "55000",
        "SEM_EXM_EXCH_ID": "NSE_FNO",
        "SEM_INSTRUMENT_NAME": "OPTIDX",
        "SEM_LOT_UNITS": 75,
        "SEM_TICK_SIZE": 0.05,
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_STRIKE_PRICE": 25000,
        "SEM_OPTION_TYPE": "CE",
        "SEM_CUSTOM_SYMBOL": "NIFTY 26 JUN 25000 CALL",
        "SM_SYMBOL_NAME": "NIFTY",
    },
    # ── NSE F&O Option (PE) ──
    {
        "SEM_TRADING_SYMBOL": "NIFTY-26Jun2026-25000-PE",
        "SEM_SMST_SECURITY_ID": "55001",
        "SEM_EXM_EXCH_ID": "NSE_FNO",
        "SEM_INSTRUMENT_NAME": "OPTIDX",
        "SEM_LOT_UNITS": 75,
        "SEM_TICK_SIZE": 0.05,
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_STRIKE_PRICE": 25000,
        "SEM_OPTION_TYPE": "PE",
        "SEM_CUSTOM_SYMBOL": "NIFTY 26 JUN 25000 PUT",
        "SM_SYMBOL_NAME": "NIFTY",
    },
    # ── NSE F&O Future ──
    {
        "SEM_TRADING_SYMBOL": "NIFTY-26Jun2026-FUT",
        "SEM_SMST_SECURITY_ID": "55100",
        "SEM_EXM_EXCH_ID": "NSE_FNO",
        "SEM_INSTRUMENT_NAME": "FUTIDX",
        "SEM_LOT_UNITS": 75,
        "SEM_TICK_SIZE": 0.05,
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_CUSTOM_SYMBOL": "NIFTY JUN FUT",
        "SM_SYMBOL_NAME": "NIFTY",
    },
    # ── MCX Commodity Future (near-month) ──
    {
        "SEM_TRADING_SYMBOL": "CRUDEOIL-18Jun2026-FUT",
        "SEM_SMST_SECURITY_ID": "466500",
        "SEM_EXM_EXCH_ID": "MCX_COMM",
        "SEM_INSTRUMENT_NAME": "FUTCOM",
        "SEM_LOT_UNITS": 100,
        "SEM_TICK_SIZE": 1.0,
        "SEM_EXPIRY_DATE": "2026-06-18",
        "SEM_CUSTOM_SYMBOL": "CRUDEOIL JUN FUT",
        "SM_SYMBOL_NAME": "CRUDEOIL",
    },
    # ── MCX Commodity Future (far-month) ──
    {
        "SEM_TRADING_SYMBOL": "CRUDEOIL-20Jul2026-FUT",
        "SEM_SMST_SECURITY_ID": "466501",
        "SEM_EXM_EXCH_ID": "MCX_COMM",
        "SEM_INSTRUMENT_NAME": "FUTCOM",
        "SEM_LOT_UNITS": 100,
        "SEM_TICK_SIZE": 1.0,
        "SEM_EXPIRY_DATE": "2026-07-20",
        "SEM_CUSTOM_SYMBOL": "CRUDEOIL JUL FUT",
        "SM_SYMBOL_NAME": "CRUDEOIL",
    },
    # ── MCX Commodity Option ──
    {
        "SEM_TRADING_SYMBOL": "CRUDEOIL-18Jun2026-5000-CE",
        "SEM_SMST_SECURITY_ID": "466600",
        "SEM_EXM_EXCH_ID": "MCX_COMM",
        "SEM_INSTRUMENT_NAME": "OPTFUT",
        "SEM_LOT_UNITS": 100,
        "SEM_TICK_SIZE": 1.0,
        "SEM_EXPIRY_DATE": "2026-06-18",
        "SEM_STRIKE_PRICE": 5000,
        "SEM_OPTION_TYPE": "CE",
        "SEM_CUSTOM_SYMBOL": "CRUDEOIL 18 JUN 5000 CALL",
        "SM_SYMBOL_NAME": "CRUDEOIL",
    },
    # ── GOLDM MCX Commodity Future ──
    {
        "SEM_TRADING_SYMBOL": "GOLDM-03Jul2026-FUT",
        "SEM_SMST_SECURITY_ID": "466584",
        "SEM_EXM_EXCH_ID": "MCX_COMM",
        "SEM_INSTRUMENT_NAME": "FUTCOM",
        "SEM_LOT_UNITS": 10,
        "SEM_TICK_SIZE": 1.0,
        "SEM_EXPIRY_DATE": "2026-07-03",
        "SEM_CUSTOM_SYMBOL": "GOLDM JUL FUT",
        "SM_SYMBOL_NAME": "GOLDM",
    },
    # ── GOLD MCX Commodity Future (near-month) ──
    {
        "SEM_TRADING_SYMBOL": "GOLD AUG FUT",
        "SEM_SMST_SECURITY_ID": "466583",
        "SEM_EXM_EXCH_ID": "MCX_COMM",
        "SEM_INSTRUMENT_NAME": "FUTCOM",
        "SEM_LOT_UNITS": 1,
        "SEM_TICK_SIZE": 1.0,
        "SEM_EXPIRY_DATE": "2026-08-05",
        "SEM_CUSTOM_SYMBOL": "GOLD",
        "SM_SYMBOL_NAME": "GOLD",
    },
    # ── GOLD MCX Commodity Future (far-month) ──
    {
        "SEM_TRADING_SYMBOL": "GOLD OCT FUT",
        "SEM_SMST_SECURITY_ID": "483079",
        "SEM_EXM_EXCH_ID": "MCX_COMM",
        "SEM_INSTRUMENT_NAME": "FUTCOM",
        "SEM_LOT_UNITS": 1,
        "SEM_TICK_SIZE": 1.0,
        "SEM_EXPIRY_DATE": "2026-10-05",
        "SEM_CUSTOM_SYMBOL": "GOLD",
        "SM_SYMBOL_NAME": "GOLD",
    },
    # ── BSE F&O Option (SENSEX) ──
    {
        "SEM_TRADING_SYMBOL": "SENSEX-26Jun2026-80000-CE",
        "SEM_SMST_SECURITY_ID": "70000",
        "SEM_EXM_EXCH_ID": "BSE_FNO",
        "SEM_INSTRUMENT_NAME": "OPTIDX",
        "SEM_LOT_UNITS": 10,
        "SEM_TICK_SIZE": 0.05,
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_STRIKE_PRICE": 80000,
        "SEM_OPTION_TYPE": "CE",
        "SEM_CUSTOM_SYMBOL": "SENSEX 26 JUN 80000 CALL",
        "SM_SYMBOL_NAME": "SENSEX",
    },
    # ── Currency Future (NSE) ──
    {
        "SEM_TRADING_SYMBOL": "USDINR-26Jun2026-FUT",
        "SEM_SMST_SECURITY_ID": "80000",
        "SEM_EXM_EXCH_ID": "NSE_CURRENCY",
        "SEM_INSTRUMENT_NAME": "FUTCUR",
        "SEM_LOT_UNITS": 1000,
        "SEM_TICK_SIZE": 0.0025,
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_CUSTOM_SYMBOL": "USDINR JUN FUT",
        "SM_SYMBOL_NAME": "USDINR",
    },
    # ── Currency Option (NSE) ──
    {
        "SEM_TRADING_SYMBOL": "USDINR-26Jun2026-85-CE",
        "SEM_SMST_SECURITY_ID": "80100",
        "SEM_EXM_EXCH_ID": "NSE_CURRENCY",
        "SEM_INSTRUMENT_NAME": "OPTCUR",
        "SEM_LOT_UNITS": 1000,
        "SEM_TICK_SIZE": 0.0025,
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_STRIKE_PRICE": 85,
        "SEM_OPTION_TYPE": "CE",
        "SEM_CUSTOM_SYMBOL": "USDINR 26 JUN 85 CALL",
        "SM_SYMBOL_NAME": "USDINR",
    },
    # ── Stock F&O Option (RELIANCE) ──
    {
        "SEM_TRADING_SYMBOL": "RELIANCE-26Jun2026-3000-CE",
        "SEM_SMST_SECURITY_ID": "60000",
        "SEM_EXM_EXCH_ID": "NSE_FNO",
        "SEM_INSTRUMENT_NAME": "OPTSTK",
        "SEM_LOT_UNITS": 250,
        "SEM_TICK_SIZE": 0.05,
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_STRIKE_PRICE": 3000,
        "SEM_OPTION_TYPE": "CE",
        "SEM_CUSTOM_SYMBOL": "RELIANCE 26 JUN 3000 CALL",
        "SM_SYMBOL_NAME": "RELIANCE",
    },
    # ── Stock F&O Future (RELIANCE) ──
    {
        "SEM_TRADING_SYMBOL": "RELIANCE-26Jun2026-FUT",
        "SEM_SMST_SECURITY_ID": "60100",
        "SEM_EXM_EXCH_ID": "NSE_FNO",
        "SEM_INSTRUMENT_NAME": "FUTSTK",
        "SEM_LOT_UNITS": 250,
        "SEM_TICK_SIZE": 0.05,
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_CUSTOM_SYMBOL": "RELIANCE JUN FUT",
        "SM_SYMBOL_NAME": "RELIANCE",
    },
]


def _quote_entry(sid: str) -> dict[str, Any]:
    return {
        "last_price": 2500.0,
        "net_change": 10.0,
        "volume": 100000,
        "ohlc": {"open": 2490.0, "high": 2510.0, "low": 2480.0, "close": 2495.0},
        "depth": {
            "buy": [{"price": 2499.0, "quantity": 100, "orders": 2}],
            "sell": [{"price": 2501.0, "quantity": 150, "orders": 3}],
        },
    }


class FakeHttpClient:
    """Unified offline stand-in for the Dhan HTTP client.

    Consolidates call tracking (conftest), failure simulation (chaos),
    and rich endpoint-based auto-responses (fixtures) into one class.

    Precedence for each request:
      1. ``set_side_effect()`` overrides — raise immediately
      2. Global ``_fail`` flag — raise ``ConnectionError``
      3. ``set_response()`` overrides — return verbatim
      4. Endpoint-pattern auto-responses (marketfeed, charts, fund limits)
      5. Fallback empty ``{"data": []}``
    """

    def __init__(self, client_id: str = "test", access_token: str = "test"):
        self.client_id = client_id
        self.access_token = access_token

        # ── Call tracking (from conftest.py) ──
        self._responses: dict[tuple[str, str], Any] = {}
        self._side_effects: dict[tuple[str, str], Exception] = {}
        self.calls: list[tuple[str, str, Any]] = []

        # ── Failure simulation (from test_chaos.py) ──
        self._fail = False
        self._fail_count = 0
        self._success_count = 0
        self._rate_limit_count = 0

    # ── Configuration (conftest.py) ──────────────────────────────────────

    def set_response(self, method: str, path: str, response: Any) -> None:
        """Override the default response for a specific method+path."""
        self._responses[(method, path)] = response

    def set_side_effect(self, method: str, path: str, exc: Exception) -> None:
        """Make a specific method+path raise *exc*."""
        self._side_effects[(method, path)] = exc

    def set_fail(self, enabled: bool = True) -> None:
        """Enable/disable global failure simulation (all requests raise)."""
        self._fail = enabled

    def set_fail_after(self, count: int) -> None:
        """Succeed for *count* requests, then fail all subsequent ones."""
        self._success_count = 0
        self._fail_after_count: int | None = count

    # ── Query (conftest.py) ──────────────────────────────────────────────

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def calls_for(self, method: str, path: str) -> list[Any]:
        """Return all JSON bodies for requests matching *method* + *path*."""
        return [j for m, p, j in self.calls if m == method and p == path]

    # ── Lifecycle (conftest.py) ──────────────────────────────────────────

    def update_token(self, token: str) -> None:
        self.access_token = token

    def close(self) -> None:
        pass

    # ── Internal helpers ─────────────────────────────────────────────────

    def _check_fail_after(self) -> None:
        """If ``set_fail_after(N)`` was used, trip after N successes."""
        limit = getattr(self, "_fail_after_count", None)
        if limit is not None and self._success_count >= limit:
            self._fail = True

    def _dispatch(self, method: str, endpoint: str, body: Any = None) -> Any:
        """Common request dispatch: side-effects → global fail → overrides → auto."""
        self.calls.append((method, endpoint, body))
        key = (method, endpoint)

        # 1. Explicit side-effect override
        if key in self._side_effects:
            raise self._side_effects[key]

        # 2. Global failure simulation (chaos)
        if self._fail:
            self._fail_count += 1
            raise ConnectionError("Simulated network failure")

        # 3. Explicit response override
        if key in self._responses:
            self._success_count += 1
            self._check_fail_after()
            return self._responses[key]

        # 4. Endpoint-pattern auto-responses
        result = self._auto_response(method, endpoint, body)
        self._success_count += 1
        self._check_fail_after()
        return result

    def _auto_response(self, method: str, endpoint: str, body: Any = None) -> Any:
        """Return a canned response based on endpoint heuristics."""
        if method == "GET":
            if "fundlimit" in endpoint or "fund" in endpoint:
                return {
                    "data": {
                        "availabelBalance": 100000.0,
                        "utilizedAmount": 0.0,
                        "sodLimit": 100000.0,
                    }
                }
            if "orders" in endpoint or "trades" in endpoint:
                return {"data": []}
            return {"data": []}

        if method == "POST":
            if endpoint.startswith("/marketfeed/"):
                data: dict[str, Any] = {}
                for segment, sids in (body or {}).items():
                    data[segment] = {str(sid): _quote_entry(str(sid)) for sid in sids}
                return {"data": data}
            if "charts" in endpoint or "historical" in endpoint:
                return {
                    "data": {
                        "open": [100.0],
                        "high": [110.0],
                        "low": [95.0],
                        "close": [105.0],
                        "volume": [1000],
                        "timestamp": [1718601600],
                        "open_interest": [0],
                    }
                }
            return {"data": []}

        if method == "PUT":
            return {"data": {}}

        if method == "DELETE":
            return {"data": {}}

        return {"data": []}

    # ── HTTP verbs ───────────────────────────────────────────────────────

    def get(self, endpoint: str, **kw: Any) -> Any:
        return self._dispatch("GET", endpoint)

    def post(self, endpoint: str, json: Any = None) -> Any:
        return self._dispatch("POST", endpoint, json)

    def put(self, endpoint: str, json: Any = None) -> Any:
        return self._dispatch("PUT", endpoint, json)

    def delete(self, endpoint: str) -> Any:
        return self._dispatch("DELETE", endpoint)


__all__ = ["FakeHttpClient", "SAMPLE_ROWS"]
