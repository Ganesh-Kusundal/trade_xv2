"""Historical data adapter — daily and intraday candles."""

from __future__ import annotations

import logging

import pandas as pd

from brokers.dhan.exceptions import MarketDataError
from brokers.dhan.http_client import DhanHttpClient
from brokers.dhan.resolver import SymbolResolver
from brokers.dhan.segments import DEFAULT_SEGMENT, EXCHANGE_TO_SEGMENT

logger = logging.getLogger(__name__)

_SESSION_OPEN = {"MCX": "09:00:00", "MCX_COMM": "09:00:00"}
_SESSION_CLOSE = {"MCX": "23:30:00", "MCX_COMM": "23:30:00"}
_DEFAULT_OPEN = "09:15:00"
_DEFAULT_CLOSE = "15:30:00"

_TIMEFRAME_MAP = {
    "1": 1, "1M": 1, "1m": 1,
    "5": 5, "5M": 5, "5m": 5,
    "15": 15, "15M": 15, "15m": 15,
    "25": 25,
    "60": 60, "60M": 60, "60m": 60,
    "1D": "1D", "D": "1D", "DAY": "1D",
}


class HistoricalAdapter:
    def __init__(self, client: DhanHttpClient, resolver: SymbolResolver):
        self._client = client
        self._resolver = resolver

    def get_historical(
        self,
        symbol: str,
        exchange: str,
        from_date: str,
        to_date: str,
        timeframe: str = "1D",
    ) -> pd.DataFrame:
        inst = self._resolver.resolve(symbol, exchange)
        segment = EXCHANGE_TO_SEGMENT.get(inst.exchange.value, DEFAULT_SEGMENT)
        interval = _TIMEFRAME_MAP.get(timeframe, timeframe)
        instrument_type = self._get_instrument_type(inst)

        if interval == "1D":
            endpoint = "/charts/historical"
            payload = {
                "securityId": inst.security_id,
                "exchangeSegment": segment,
                "instrument": instrument_type,
                "expiryCode": 0,
                "oi": True,
                "fromDate": str(from_date),
                "toDate": str(to_date),
            }
        else:
            endpoint = "/charts/intraday"
            exch_upper = exchange.upper()
            sess_open = _SESSION_OPEN.get(exch_upper, _DEFAULT_OPEN)
            sess_close = _SESSION_CLOSE.get(exch_upper, _DEFAULT_CLOSE)
            payload = {
                "securityId": inst.security_id,
                "exchangeSegment": segment,
                "instrument": instrument_type,
                "interval": str(interval),
                "oi": True,
                "fromDate": f"{from_date} {sess_open}",
                "toDate": f"{to_date} {sess_close}",
            }

        data = self._client.post(endpoint, json=payload)
        df = self._parse(data, symbol=symbol, exchange=exchange, timeframe=timeframe)
        logger.info("historical_fetched", extra={
            "symbol": symbol, "timeframe": timeframe, "candles": len(df),
            "from": str(from_date), "to": str(to_date),
        })
        return df

    @staticmethod
    def _parse(
        data: dict,
        symbol: str = "",
        exchange: str = "",
        timeframe: str = "1D",
    ) -> pd.DataFrame:
        if isinstance(data, dict) and data.get("status") == "failure":
            raise MarketDataError(f"API returned failure: {data}")
        raw = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(raw, dict) and "data" in raw and isinstance(raw["data"], dict):
            raw = raw["data"]
        df = pd.DataFrame(raw)
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
        elif "date" in df.columns:
            df["timestamp"] = pd.to_datetime(df["date"])
            df = df.drop(columns=["date"])
        for col in ("open", "high", "low", "close", "volume"):
            if col not in df.columns:
                df[col] = 0
        if "oi" not in df.columns:
            df["oi"] = 0
        df["symbol"] = symbol
        df["exchange"] = exchange
        df["timeframe"] = timeframe
        return df[["timestamp", "open", "high", "low", "close", "volume", "oi", "symbol", "exchange", "timeframe"]]

    @staticmethod
    def _get_instrument_type(inst) -> str:
        if inst.name:
            return "EQUITY" if inst.name == "INDEX" else inst.name
        if inst.exchange.value == "INDEX":
            return "EQUITY"
        if inst.exchange.value in ("NFO", "BFO"):
            return "OPTIDX"
        if inst.exchange.value == "MCX":
            return "FUTCOM"
        return "EQUITY"
