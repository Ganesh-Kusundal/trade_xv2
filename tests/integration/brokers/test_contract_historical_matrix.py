"""Live contract historical certification matrix (ADR-0023).

Requires real broker credentials; skipped when env tokens absent.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import pytest

from application.composer.factory import create_composers
from application.data.contract_historical_coordinator import ContractHistoricalCoordinator
from domain.candles.contract_historical import ContractHistoricalQuery
from domain.historical.contract_state import ContractState
from domain.instruments.instrument_id import InstrumentId
from infrastructure.adapters.market_data_gateway_adapter import wrap_market_gateway
from infrastructure.gateway.factory import require_gateway
from runtime.composition import wire_domain_port_sinks
from runtime.event_loop import ensure_runtime_loop_running

ENV_DHAN = Path(__file__).resolve().parents[3] / ".env.local"
ENV_UPSTOX = Path(__file__).resolve().parents[3] / ".env.upstox"

_dhan_ok = ENV_DHAN.exists() and ENV_DHAN.stat().st_size > 0
_upstox_ok = ENV_UPSTOX.exists() and ENV_UPSTOX.stat().st_size > 0

if _dhan_ok:
    from dotenv import load_dotenv

    load_dotenv(ENV_DHAN, override=True)
    _dhan_ok = bool(os.environ.get("DHAN_CLIENT_ID"))

if _upstox_ok:
    from dotenv import load_dotenv

    load_dotenv(ENV_UPSTOX, override=True)
    _upstox_ok = bool(os.environ.get("UPSTOX_ACCESS_TOKEN"))


def _plus_entitlements() -> frozenset[str]:
    if os.environ.get("UPSTOX_PLUS", "").strip().lower() in {"1", "true", "yes"}:
        return frozenset({"upstox_plus"})
    return frozenset()


def _build_coordinator() -> ContractHistoricalCoordinator:
    wire_domain_port_sinks()
    ensure_runtime_loop_running()
    gateways = []
    for bid in ("dhan", "upstox"):
        try:
            gw = require_gateway(bid, load_instruments=True)
            gateways.append(wrap_market_gateway(gw, bid))
        except Exception:
            continue
    if not gateways:
        pytest.skip("No broker gateways available")
    _md, execution = create_composers(gateways)
    quota = execution._quota_scheduler
    return ContractHistoricalCoordinator(
        execution._registry,
        execution._router,
        lambda bid, ep, pri: quota.acquire(bid, ep, pri),
        entitlements=_plus_entitlements(),
    )


@pytest.mark.skipif(not _dhan_ok, reason="Dhan credentials required")
@pytest.mark.dhan
@pytest.mark.off_market_safe
def test_nse_active_equity_history() -> None:
    coord = _build_coordinator()
    query = ContractHistoricalQuery(
        instrument=InstrumentId.equity("NSE", "RELIANCE"),
        from_date=date.today() - timedelta(days=5),
        to_date=date.today() - timedelta(days=1),
        timeframe="1d",
        contract_state=ContractState.ACTIVE,
    )
    df, ledger = coord.fetch(query)
    assert not ledger.degraded
    assert len(df) > 0
    assert {"open", "high", "low", "close", "volume"}.issubset(df.columns)


@pytest.mark.skipif(not _dhan_ok, reason="Dhan credentials required")
@pytest.mark.dhan
@pytest.mark.off_market_safe
def test_nfo_rolling_expired_index_options() -> None:
    coord = _build_coordinator()
    query = ContractHistoricalQuery(
        instrument=InstrumentId.parse("NFO:NIFTY:20250102:24000:CE"),
        from_date=date(2024, 12, 2),
        to_date=date(2024, 12, 6),
        timeframe="5m",
        contract_state=ContractState.EXPIRED,
        rolling_expiry_kind="WEEK",
        rolling_expiry_code=1,
        rolling_strike_offset=0,
    )
    df, ledger = coord.fetch(query)
    assert not ledger.degraded
    assert len(df) > 0


@pytest.mark.skipif(not _dhan_ok, reason="Dhan credentials required")
@pytest.mark.dhan
@pytest.mark.off_market_safe
def test_mcx_active_future_routes() -> None:
    coord = _build_coordinator()
    query = ContractHistoricalQuery(
        instrument=InstrumentId.future("MCX", "GOLD", date(2026, 6, 5)),
        from_date=date.today() - timedelta(days=5),
        to_date=date.today() - timedelta(days=1),
        timeframe="1d",
        contract_state=ContractState.ACTIVE,
    )
    df, ledger = coord.fetch(query)
    assert not ledger.degraded
    assert len(df) > 0


@pytest.mark.skipif(not _upstox_ok, reason="Upstox credentials required")
@pytest.mark.upstox
@pytest.mark.off_market_safe
def test_upstox_active_nse_equity() -> None:
    coord = _build_coordinator()
    query = ContractHistoricalQuery(
        instrument=InstrumentId.equity("NSE", "RELIANCE"),
        from_date=date.today() - timedelta(days=5),
        to_date=date.today() - timedelta(days=1),
        timeframe="1d",
        contract_state=ContractState.ACTIVE,
    )
    df, ledger = coord.fetch(query)
    assert not ledger.degraded
    assert len(df) > 0
