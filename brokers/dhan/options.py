"""Options adapter — option chain, greeks, strike selection."""

from __future__ import annotations

import logging
from decimal import Decimal

from brokers.dhan.http_client import DhanHttpClient
from brokers.dhan.resolver import SymbolResolver
from brokers.dhan.segments import EXCHANGE_TO_SEGMENT

logger = logging.getLogger(__name__)

_DEFAULT_STRIKE_STEPS = {
    "NIFTY": Decimal("50"),
    "BANKNIFTY": Decimal("100"),
    "FINNIFTY": Decimal("50"),
    "MIDCPNIFTY": Decimal("25"),
    "SENSEX": Decimal("100"),
}


class OptionsAdapter:
    def __init__(self, client: DhanHttpClient, resolver: SymbolResolver):
        self._client = client
        self._resolver = resolver

    def get_option_chain(
        self,
        underlying: str,
        exchange: str,
        expiry: str,
        *,
        security_id: int | None = None,
    ) -> dict:
        """Fetch full option chain. Pass security_id for MCX commodities."""
        if security_id is not None:
            scrip_id = security_id
            segment = "MCX_COMM"
        else:
            inst, segment = self._resolve_and_segment(underlying, exchange)
            scrip_id = int(inst.security_id)

        response = self._client.post("/optionchain", json={
            "UnderlyingScrip": scrip_id,
            "UnderlyingSeg": segment,
            "Expiry": expiry,
        })

        data = response.get("data", response)
        if isinstance(data, dict):
            spot = Decimal(str(data.get("last_price", 0)))
            oc = data.get("oc", {})
        else:
            spot = Decimal("0")
            oc = {}

        strikes = []
        for strike_str, legs in sorted(oc.items(), key=lambda kv: float(kv[0])):
            strike = Decimal(str(strike_str))
            ce = legs.get("ce", {}) or {}
            pe = legs.get("pe", {}) or {}
            ce_greeks = ce.get("greeks", {}) or {}
            pe_greeks = pe.get("greeks", {}) or {}

            ce_sec_id = ce.get("security_id")
            pe_sec_id = pe.get("security_id")

            ce_symbol = ""
            if ce_sec_id:
                try:
                    ce_inst = self._resolver.get_by_security_id(str(ce_sec_id))
                    if ce_inst:
                        ce_symbol = ce_inst.symbol
                except Exception:
                    pass

            pe_symbol = ""
            if pe_sec_id:
                try:
                    pe_inst = self._resolver.get_by_security_id(str(pe_sec_id))
                    if pe_inst:
                        pe_symbol = pe_inst.symbol
                except Exception:
                    pass

            strikes.append({
                "strike": strike,
                "call": {
                    "ltp": _dec(ce.get("last_price")),
                    "oi": int(ce.get("oi", 0) or 0),
                    "volume": int(ce.get("volume", 0) or 0),
                    "iv": _dec(ce.get("implied_volatility")),
                    "delta": _dec(ce_greeks.get("delta")),
                    "theta": _dec(ce_greeks.get("theta")),
                    "gamma": _dec(ce_greeks.get("gamma")),
                    "vega": _dec(ce_greeks.get("vega")),
                    "security_id": ce_sec_id,
                    "symbol": ce_symbol,
                },
                "put": {
                    "ltp": _dec(pe.get("last_price")),
                    "oi": int(pe.get("oi", 0) or 0),
                    "volume": int(pe.get("volume", 0) or 0),
                    "iv": _dec(pe.get("implied_volatility")),
                    "delta": _dec(pe_greeks.get("delta")),
                    "theta": _dec(pe_greeks.get("theta")),
                    "gamma": _dec(pe_greeks.get("gamma")),
                    "vega": _dec(pe_greeks.get("vega")),
                    "security_id": pe_sec_id,
                    "symbol": pe_symbol,
                },
            })

        logger.info("option_chain_fetched", extra={"underlying": underlying, "expiry": expiry, "strikes": len(strikes), "spot": str(spot)})
        return {"underlying": underlying, "expiry": expiry, "spot": spot, "strikes": strikes}

    def get_expiries(self, underlying: str, exchange: str) -> list[str]:
        inst, segment = self._resolve_and_segment(underlying, exchange)
        response = self._client.post("/optionchain/expirylist", json={
            "UnderlyingScrip": int(inst.security_id),
            "UnderlyingSeg": segment,
        })
        data = response.get("data", {})
        if isinstance(data, dict):
            values = data.get("expiryList") or data.get("expiries") or []
        else:
            values = data if isinstance(data, list) else []
        result = [str(v) for v in values]
        logger.info("expiries_fetched", extra={"underlying": underlying, "count": len(result)})
        return result

    def _resolve_and_segment(self, symbol: str, exchange: str):
        inst = self._resolver.resolve(symbol, exchange)
        segment = EXCHANGE_TO_SEGMENT.get(inst.exchange.value, "IDX_I")
        return inst, segment


def _dec(value) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value))
