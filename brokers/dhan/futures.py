"""Futures adapter — contract discovery from instrument cache."""

from __future__ import annotations

from brokers.dhan.http_client import DhanHttpClient
from brokers.dhan.resolver import SymbolResolver

COMMON_COMMODITIES = {
    "GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER",
    "ZINC", "LEAD", "NICKEL", "ALUMINIUM", "CRUDEOILM", "GOLDM", "SILVERM",
}

# Index underlyings live on INDEX exchange spot, but their derivatives
# trade on NFO (NSE F&O) or BFO (BSE F&O).
_INDEX_FNO_MAP = {
    "NIFTY": "NFO",
    "BANKNIFTY": "NFO",
    "FINNIFTY": "NFO",
    "MIDCPNIFTY": "NFO",
    "NIFTY_NEXT50": "NFO",
    "SENSEX": "BFO",
    "BANKEX": "BFO",
}


def _resolve_derivatives_exchange(underlying: str, exchange: str) -> str:
    """Map user-facing exchange to the actual derivatives exchange.

    Index instruments live on INDEX exchange, but their derivatives (futures,
    options) trade on NFO (NSE F&O) or BFO (BSE F&O).
    """
    up = exchange.strip().upper()
    if up in ("INDEX", "IDX_I"):
        return _INDEX_FNO_MAP.get(underlying.strip().upper(), up)
    return up


class FuturesAdapter:
    def __init__(self, client: DhanHttpClient, resolver: SymbolResolver):
        self._client = client
        self._resolver = resolver

    def get_contracts(self, underlying: str, exchange: str) -> list[dict]:
        exchange = _resolve_derivatives_exchange(underlying, exchange)
        instruments = self._resolver.get_futures(underlying, exchange)
        return [
            {
                "symbol": inst.canonical_symbol or inst.symbol,
                "underlying": inst.underlying,
                "exchange": inst.exchange.value,
                "expiry": inst.expiry,
                "lot_size": inst.lot_size,
                "security_id": inst.security_id,
            }
            for inst in instruments
        ]

    def get_nearest(self, underlying: str, exchange: str) -> dict | None:
        contracts = self.get_contracts(underlying, exchange)
        return contracts[0] if contracts else None

    def get_expiries(self, underlying: str, exchange: str) -> list[str]:
        exchange = _resolve_derivatives_exchange(underlying, exchange)
        return self._resolver.get_futures_expiries(underlying, exchange)

    def is_commodity(self, symbol: str) -> bool:
        return symbol.upper().strip() in COMMON_COMMODITIES
