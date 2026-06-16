"""Market data adapter — LTP, Quote, Depth, OHLC."""

from __future__ import annotations

import logging
from decimal import Decimal

from brokers.dhan.domain import DepthLevel, MarketDepth, Quote, InstrumentType
from brokers.dhan.http_client import DhanHttpClient
from brokers.dhan.resolver import SymbolResolver
from brokers.dhan.segments import EXCHANGE_TO_SEGMENT

logger = logging.getLogger(__name__)


class MarketDataAdapter:
    def __init__(self, client: DhanHttpClient, resolver: SymbolResolver):
        self._client = client
        self._resolver = resolver
        self._symbol_interceptor = None  # Set by factory if available

    def _resolve_and_segment(self, symbol: str, exchange: str):
        """Resolve symbol and get exchange segment.
        
        Uses the symbol interceptor (SQLite cache) if available, falling back
        to the legacy in-memory resolver.
        """
        # Try symbol interceptor first (fast SQLite path with lazy refresh)
        if self._symbol_interceptor:
            resolved = self._symbol_interceptor.resolve("dhan", symbol, exchange)
            if resolved:
                # Get segment from resolved metadata
                inst = self._resolver.resolve(symbol, exchange)  # Fallback for segment
                segment = EXCHANGE_TO_SEGMENT.get(inst.exchange.value, "NSE_EQ")
                return inst, segment
        
        # Fallback to legacy resolver
        inst = self._resolver.resolve(symbol, exchange)
        segment = EXCHANGE_TO_SEGMENT.get(inst.exchange.value, "NSE_EQ")
        return inst, segment

    def get_ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        inst, segment = self._resolve_and_segment(symbol, exchange)
        sid = int(inst.security_id)
        data = self._client.post("/marketfeed/ltp", json={segment: [sid]})
        ltp = Decimal(str(data["data"][segment][str(sid)]["last_price"]))
        logger.debug("ltp_fetched", extra={"symbol": symbol, "ltp": str(ltp)})
        return ltp

    def get_quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        inst, segment = self._resolve_and_segment(symbol, exchange)
        sid = int(inst.security_id)
        data = self._client.post("/marketfeed/quote", json={segment: [sid]})
        raw = data["data"][segment][str(sid)]
        ohlc = raw.get("ohlc", {}) or {}
        quote = Quote(
            symbol=inst.symbol if inst.instrument_type == InstrumentType.EQUITY else (inst.canonical_symbol or inst.symbol),
            ltp=Decimal(str(raw.get("last_price", 0))),
            open=Decimal(str(ohlc.get("open", 0))),
            high=Decimal(str(ohlc.get("high", 0))),
            low=Decimal(str(ohlc.get("low", 0))),
            close=Decimal(str(ohlc.get("close", 0))),
            volume=int(raw.get("volume", 0)),
            change=Decimal(str(raw.get("net_change", 0))),
        )
        logger.debug("quote_fetched", extra={"symbol": symbol, "ltp": str(quote.ltp), "volume": quote.volume})
        return quote

    def get_depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        inst, segment = self._resolve_and_segment(symbol, exchange)
        sid = int(inst.security_id)
        data = self._client.post("/marketfeed/quote", json={segment: [sid]})
        raw = data["data"][segment][str(sid)]
        bids = [
            DepthLevel(price=Decimal(str(l["price"])), quantity=int(l["quantity"]), orders=int(l.get("orders", 0)))
            for l in raw.get("depth", {}).get("buy", [])[:5]
        ]
        asks = [
            DepthLevel(price=Decimal(str(l["price"])), quantity=int(l["quantity"]), orders=int(l.get("orders", 0)))
            for l in raw.get("depth", {}).get("sell", [])[:5]
        ]
        depth = MarketDepth(symbol=inst.symbol if inst.instrument_type == InstrumentType.EQUITY else (inst.canonical_symbol or inst.symbol), bids=bids, asks=asks)
        logger.debug("depth_fetched", extra={"symbol": symbol, "bid_levels": len(bids), "ask_levels": len(asks)})
        return depth

    def get_ohlc(self, symbol: str, exchange: str = "NSE") -> dict:
        inst, segment = self._resolve_and_segment(symbol, exchange)
        sid = int(inst.security_id)
        data = self._client.post("/marketfeed/ohlc", json={segment: [sid]})
        result = data["data"][segment][str(sid)]["ohlc"]
        logger.debug("ohlc_fetched", extra={"symbol": symbol})
        return result

    def get_batch_ltp(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
        """Fetch LTP for multiple symbols in one API call (up to 1000)."""
        segment_map: dict[str, list[int]] = {}
        symbol_map: dict[int, str] = {}
        
        for sym in symbols:
            try:
                inst, segment = self._resolve_and_segment(sym, exchange)
                sid = int(inst.security_id)
                segment_map.setdefault(segment, []).append(sid)
                symbol_map[sid] = sym
            except Exception:
                continue
        
        if not segment_map:
            return {}
        
        data = self._client.post("/marketfeed/ltp", json=segment_map)
        result = {}
        for seg, sids in data.get("data", {}).items():
            for sid_str, info in sids.items():
                sid = int(sid_str)
                if sid in symbol_map:
                    result[symbol_map[sid]] = Decimal(str(info.get("last_price", 0)))
        return result

    def get_batch_quote(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Quote]:
        """Fetch quotes for multiple symbols in one API call (up to 1000)."""
        from brokers.dhan.domain import Quote as DhanQuote
        segment_map: dict[str, list[int]] = {}
        symbol_map: dict[int, str] = {}
        inst_map: dict[int, Any] = {}
        
        for sym in symbols:
            try:
                inst, segment = self._resolve_and_segment(sym, exchange)
                sid = int(inst.security_id)
                segment_map.setdefault(segment, []).append(sid)
                symbol_map[sid] = sym
                inst_map[sid] = inst
            except Exception:
                continue
        
        if not segment_map:
            return {}
        
        data = self._client.post("/marketfeed/quote", json=segment_map)
        result = {}
        for seg, sids in data.get("data", {}).items():
            for sid_str, info in sids.items():
                sid = int(sid_str)
                if sid in symbol_map:
                    sym = symbol_map[sid]
                    inst = inst_map[sid]
                    ohlc = info.get("ohlc", {}) or {}
                    result[sym] = DhanQuote(
                        symbol=inst.symbol if inst.instrument_type == InstrumentType.EQUITY else (inst.canonical_symbol or inst.symbol),
                        ltp=Decimal(str(info.get("last_price", 0))),
                        open=Decimal(str(ohlc.get("open", 0))),
                        high=Decimal(str(ohlc.get("high", 0))),
                        low=Decimal(str(ohlc.get("low", 0))),
                        close=Decimal(str(ohlc.get("close", 0))),
                        volume=int(info.get("volume", 0)),
                        change=Decimal(str(info.get("net_change", 0))),
                    )
        return result
