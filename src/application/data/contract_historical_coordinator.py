"""Contract-centric historical fetch — broker adapters + coordinator."""

from __future__ import annotations

import logging
import uuid
from datetime import date, timedelta
from typing import Any, Callable

import pandas as pd

from config.indices import get_index_entry
from application.composer.registry import BrokerRegistry
from application.composer.router import BrokerRouter
from application.data.dhan_rolling_options_fetcher import DhanRollingOptionsFetcher
from application.data.provenance import ChunkRecord, ProvenanceLedger
from domain.candles.contract_historical import (
    CONTRACT_CANONICAL_COLUMNS,
    ContractHistoricalQuery,
    ContractHistoricalSeries,
)
from domain.historical.contract_state import ContractState
from domain.historical.route_lane import HistoricalRouteLane
from domain.instruments.asset_kind import AssetKind
from domain.instruments.instrument_id import InstrumentId
from domain.models.routing import OperationKind, RoutingRequest

logger = logging.getLogger(__name__)


def _resolve_gateway(gateway: Any) -> Any:
    """Unwrap MarketDataGatewayAdapter to underlying broker wire."""
    legacy = getattr(gateway, "legacy_gateway", None)
    return legacy if legacy is not None else gateway


_INTERVAL_MAP = {
    "1m": "1minute",
    "3m": "3minute",
    "5m": "5minute",
    "15m": "15minute",
    "30m": "30minute",
    "1d": "day",
    "1D": "day",
}


def _resolve_contract_state(query: ContractHistoricalQuery, today: date | None = None) -> ContractState:
    if query.contract_state != ContractState.AUTO:
        return query.contract_state
    ref = today or date.today()
    if query.instrument.expiry and query.instrument.expiry < ref:
        return ContractState.EXPIRED
    return ContractState.ACTIVE


def _asset_kind(instrument: InstrumentId) -> AssetKind:
    if instrument.right == "FUT":
        # Route lane uses FUTURES; COMMODITY is a display/market-surface kind only.
        return AssetKind.FUTURES
    parsed = AssetKind.parse(instrument.kind) if instrument.kind else None
    if parsed is not None:
        return parsed
    if instrument.right in ("CE", "PE"):
        return AssetKind.OPTIONS
    if instrument.expiry is None:
        return AssetKind.EQUITY
    return AssetKind.FUTURES


def _lookback_days(query: ContractHistoricalQuery) -> int:
    return max(1, (query.to_date - query.from_date).days + 1)


def _is_rolling_index_lane(query: ContractHistoricalQuery, state: ContractState) -> bool:
    """Dhan /charts/rollingoption — NFO index options only, no exact contract key."""
    if state != ContractState.EXPIRED or query.expired_instrument_key:
        return False
    if query.instrument.exchange != "NFO":
        return False
    if _asset_kind(query.instrument) != AssetKind.OPTIONS:
        return False
    return get_index_entry(query.instrument.underlying) is not None


def _fetch_symbol(query: ContractHistoricalQuery) -> str:
    if query.broker_symbol:
        return query.broker_symbol
    return query.instrument.underlying


def _active_history_df(gateway: Any, query: ContractHistoricalQuery) -> pd.DataFrame:
    symbol = _fetch_symbol(query)
    exchange = query.instrument.exchange
    lookback = _lookback_days(query)
    df = gateway.history(
        symbol,
        exchange,
        timeframe=query.timeframe,
        lookback_days=lookback,
        from_date=query.from_date.isoformat(),
        to_date=query.to_date.isoformat(),
    )
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def _normalize_active_df(df: pd.DataFrame, query: ContractHistoricalQuery, state: ContractState) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=list(CONTRACT_CANONICAL_COLUMNS))
    out = df.copy()
    iid = str(query.instrument)
    out["instrument_id"] = iid
    out["underlying"] = query.instrument.underlying
    out["exchange"] = query.instrument.exchange
    out["contract_state"] = state.value
    if query.instrument.expiry:
        out["expiry_date"] = query.instrument.expiry.isoformat()
    if query.instrument.strike is not None:
        out["strike"] = float(query.instrument.strike)
    if query.instrument.right in ("CE", "PE"):
        out["option_type"] = query.instrument.right
    cols = [c for c in CONTRACT_CANONICAL_COLUMNS if c in out.columns]
    return out[cols] if cols else out


def _fetch_dhan_rolling_expired(
    gateway: Any,
    query: ContractHistoricalQuery,
    *,
    quota_fn: Callable[[str, str, str], Any],
) -> pd.DataFrame:
    kind = query.rolling_expiry_kind or "WEEK"
    code = query.rolling_expiry_code if query.rolling_expiry_code is not None else 1
    offset = query.rolling_strike_offset if query.rolling_strike_offset is not None else 0
    right = (query.instrument.right or "CE").upper()
    option_type = "CALL" if right in ("CE", "CALL", "C") else "PUT"
    interval_map = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30, "1d": 1440, "1D": 1440}
    interval_min = interval_map.get(query.timeframe, 5)
    fetcher = DhanRollingOptionsFetcher(
        gateway,
        quota_acquire=lambda bid, ep, pri: quota_fn(bid, ep, pri),
        quota_release=lambda tok: tok.release() if hasattr(tok, "release") else None,
    )
    df = fetcher.fetch_series(
        underlying=query.instrument.underlying,
        expiry_kind=kind,  # type: ignore[arg-type]
        expiry_code=code,
        strike_offset=offset,
        option_type=option_type,  # type: ignore[arg-type]
        from_date=query.from_date.isoformat(),
        to_date=query.to_date.isoformat(),
        interval_min=interval_min,
    )
    return _normalize_active_df(df, query, ContractState.EXPIRED)


def _fetch_upstox_expired(gateway: Any, query: ContractHistoricalQuery) -> pd.DataFrame:
    key = query.expired_instrument_key
    if not key:
        raise ValueError("expired_instrument_key required for expired Upstox contract fetch")
    interval = _INTERVAL_MAP.get(query.timeframe, query.timeframe)
    body = gateway.get_expired_historical_candles(
        key, interval, query.from_date, query.to_date
    )
    candles = []
    if isinstance(body, dict):
        data = body.get("data") or body
        raw = data.get("candles") if isinstance(data, dict) else None
        if isinstance(raw, list):
            candles = raw
    rows = []
    for c in candles:
        if not isinstance(c, (list, tuple)) or len(c) < 5:
            continue
        rows.append(
            {
                "timestamp": c[0],
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": int(c[5]) if len(c) > 5 and c[5] is not None else 0,
                "oi": int(c[6]) if len(c) > 6 and c[6] is not None else 0,
            }
        )
    df = pd.DataFrame(rows)
    return _normalize_active_df(df, query, ContractState.EXPIRED)


class ContractHistoricalCoordinator:
    """Route and fetch exact-contract historical bars."""

    def __init__(
        self,
        registry: BrokerRegistry,
        router: BrokerRouter,
        quota_fn: Callable[[str, str, str], Any],
        *,
        entitlements: frozenset[str] | None = None,
    ) -> None:
        self._registry = registry
        self._router = router
        self._quota_fn = quota_fn
        self._entitlements = entitlements or frozenset()

    def fetch(self, query: ContractHistoricalQuery) -> tuple[pd.DataFrame, ProvenanceLedger]:
        request_id = query.request_id or str(uuid.uuid4())
        state = _resolve_contract_state(query)
        asset = _asset_kind(query.instrument)
        rolling = _is_rolling_index_lane(query, state)
        lane = HistoricalRouteLane(
            asset_kind=asset,
            exchange=query.instrument.exchange,
            contract_state=state,
            timeframe=query.timeframe,
            lookback_days=_lookback_days(query),
            underlying=query.instrument.underlying,
            rolling_index_options=rolling,
        )
        op = (
            OperationKind.GET_CONTRACT_HISTORICAL
            if not lane.rolling_index_options
            else OperationKind.GET_OPTIONS_HISTORICAL
        )
        decision = self._router.route(
            RoutingRequest(
                operation=op,
                trace_id=request_id,
                instrument=str(query.instrument),
                route_lane=lane,
                entitlements=self._entitlements,
            )
        )
        brokers = [decision.primary_broker, *decision.fallback_brokers]
        ledger = ProvenanceLedger(
            request_id=request_id,
            instrument=str(query.instrument),
            timeframe=query.timeframe,
        )
        last_error: Exception | None = None
        for broker_id in brokers:
            endpoint = lane.endpoint_class()
            dhan_rolling = (
                state == ContractState.EXPIRED and broker_id == "dhan" and rolling
            )
            token = None
            if not dhan_rolling:
                token = self._quota_fn(broker_id, endpoint, "HISTORICAL_BACKFILL")
            try:
                gw = _resolve_gateway(self._registry.get_gateway(broker_id))
                if state == ContractState.EXPIRED and broker_id == "upstox":
                    df = _fetch_upstox_expired(gw, query)
                elif dhan_rolling:
                    df = _fetch_dhan_rolling_expired(
                        gw, query, quota_fn=self._quota_fn
                    )
                else:
                    df = _active_history_df(gw, query)
                    df = _normalize_active_df(df, query, state)
                ledger.add_chunk(
                    ChunkRecord(
                        chunk_id=f"{request_id}:{broker_id}",
                        broker_id=broker_id,
                        from_date=query.from_date,
                        to_date=query.to_date,
                        timeframe=query.timeframe,
                        bars_fetched=len(df),
                    )
                )
                if token is not None and hasattr(token, "release"):
                    token.release()
                return df, ledger
            except Exception as exc:
                last_error = exc
                ledger.add_chunk(
                    ChunkRecord(
                        chunk_id=f"{request_id}:{broker_id}",
                        broker_id=broker_id,
                        from_date=query.from_date,
                        to_date=query.to_date,
                        timeframe=query.timeframe,
                        bars_fetched=0,
                        error=str(exc),
                    )
                )
                logger.warning("contract_fetch_failed broker=%s err=%s", broker_id, exc)
                if token is not None and hasattr(token, "release"):
                    token.release()
        ledger.mark_degraded(str(last_error) if last_error else "all_brokers_failed")
        if not query.allow_partial:
            raise RuntimeError(
                f"contract historical fetch failed for {query.instrument}: {ledger.degraded_reason}"
            )
        return pd.DataFrame(columns=list(CONTRACT_CANONICAL_COLUMNS)), ledger


def require_complete_contract_fetch(query: ContractHistoricalQuery, ledger: ProvenanceLedger) -> None:
    if ledger.degraded:
        raise RuntimeError(
            f"[{query.instrument}] contract fetch degraded: {ledger.degraded_reason}"
        )
