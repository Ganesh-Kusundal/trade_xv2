"""Tests for AgentTools — the AI agent tool surface, thin wrappers only."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from interface.agent.guardrails import (
    AgentGuardrailConfig,
    AgentGuardrails,
    AgentRateLimitExceeded,
    AgentSymbolNotAllowed,
)
from interface.agent.tools import AgentTools, DryRunResult


def _fake_session():
    session = MagicMock()
    inst = MagicMock()
    inst.ltp = Decimal("2500")
    inst.bid = Decimal("2499")
    inst.ask = Decimal("2501")
    inst.volume = 1000
    session.universe.equity.return_value = inst
    return session, inst


# ── Read-only tools wrap the real SDK, nothing more ─────────────────────────


def test_get_quote_wraps_instrument_refresh_and_reads_state():
    session, inst = _fake_session()
    tools = AgentTools(session)

    result = tools.get_quote("RELIANCE")

    inst.refresh.assert_called_once()
    assert result["ltp"] == Decimal("2500")
    assert result["symbol"] == "RELIANCE"


def test_get_history_delegates_to_instrument_history():
    session, inst = _fake_session()
    inst.history.return_value = "series"
    tools = AgentTools(session)

    result = tools.get_history("RELIANCE", timeframe="1D", days=10)

    inst.history.assert_called_once_with(timeframe="1D", days=10)
    assert result == "series"


def test_get_option_chain_delegates_to_session():
    session, _ = _fake_session()
    session.option_chain.return_value = "chain"
    tools = AgentTools(session)

    result = tools.get_option_chain("NIFTY", expiry=0)

    session.option_chain.assert_called_once_with("NIFTY", expiry=0)
    assert result == "chain"


def test_get_positions_refreshes_account_first():
    session, _ = _fake_session()
    session.account.refresh.return_value.positions = ["pos1"]
    tools = AgentTools(session)

    result = tools.get_positions()

    session.account.refresh.assert_called_once()
    assert result == ["pos1"]


def test_get_risk_status_returns_not_configured_when_no_risk_profile():
    session, _ = _fake_session()
    session.account.risk_profile = None
    tools = AgentTools(session)

    result = tools.get_risk_status()

    assert result == {"configured": False}


def test_get_risk_status_wraps_real_risk_profile():
    from domain.portfolio.risk_profile import RiskProfile

    session, _ = _fake_session()
    session.account.risk_profile = RiskProfile(
        max_daily_loss_pct=Decimal("2"),
        max_position_pct=Decimal("10"),
        max_gross_exposure_pct=Decimal("50"),
        kill_switch=False,
        daily_pnl=Decimal("-5000"),
        capital=Decimal("1000000"),
    )
    tools = AgentTools(session)

    result = tools.get_risk_status()

    assert result["configured"] is True
    assert result["kill_switch"] is False
    # loss budget = 20,000; used 5,000 -> headroom 0.75
    assert result["headroom_pct"] == Decimal("0.75")


# ── Order tools always go through session.buy/sell -> OrderServicePort ─────


def test_place_order_buy_delegates_to_instrument_buy():
    session, inst = _fake_session()
    inst.buy.return_value = "order_result"
    tools = AgentTools(session)

    result = tools.place_order("RELIANCE", "NSE", "BUY", 10, price=Decimal("2500"))

    inst.buy.assert_called_once_with(10, price=Decimal("2500"), order_type="MARKET")
    assert result == "order_result"


def test_place_order_sell_delegates_to_instrument_sell():
    session, inst = _fake_session()
    tools = AgentTools(session)

    tools.place_order("RELIANCE", "NSE", "sell", 5)

    inst.sell.assert_called_once()
    inst.buy.assert_not_called()


def test_place_order_dry_run_never_calls_buy_or_sell():
    session, inst = _fake_session()
    session.account.risk_profile = None
    tools = AgentTools(session)

    result = tools.place_order("RELIANCE", "NSE", "BUY", 10, price=Decimal("2500"), dry_run=True)

    inst.buy.assert_not_called()
    inst.sell.assert_not_called()
    assert isinstance(result, DryRunResult)
    assert result.symbol == "RELIANCE"
    assert result.quantity == 10


def test_cancel_order_delegates_to_session():
    session, _ = _fake_session()
    session.cancel.return_value = "cancelled"
    tools = AgentTools(session)

    result = tools.cancel_order("ORD-1")

    session.cancel.assert_called_once_with("ORD-1")
    assert result == "cancelled"


def test_modify_order_delegates_to_session():
    session, _ = _fake_session()
    tools = AgentTools(session)

    tools.modify_order("ORD-1", price=Decimal("2600"))

    session.modify.assert_called_once_with("ORD-1", price=Decimal("2600"))


# ── Guardrails: rate limiting ────────────────────────────────────────────────


def test_order_rate_limit_blocks_runaway_agent_loop():
    session, inst = _fake_session()
    config = AgentGuardrailConfig(order_rate_per_second=1.0, order_burst_capacity=1)
    tools = AgentTools(session, AgentGuardrails(config))

    tools.place_order("RELIANCE", "NSE", "BUY", 1)  # consumes the one burst token
    with pytest.raises(AgentRateLimitExceeded):
        tools.place_order("RELIANCE", "NSE", "BUY", 1)  # immediately over budget


def test_read_and_order_rate_limits_are_independent_budgets():
    session, inst = _fake_session()
    config = AgentGuardrailConfig(order_rate_per_second=1.0, order_burst_capacity=1)
    tools = AgentTools(session, AgentGuardrails(config))

    tools.place_order("RELIANCE", "NSE", "BUY", 1)  # exhausts order budget
    # Reads use a separate budget and must still work.
    tools.get_quote("RELIANCE")


# ── Guardrails: symbol allowlist ─────────────────────────────────────────────


def test_symbol_allowlist_blocks_out_of_scope_symbol():
    session, _ = _fake_session()
    config = AgentGuardrailConfig(symbol_allowlist=frozenset({"NIFTY", "RELIANCE"}))
    tools = AgentTools(session, AgentGuardrails(config))

    with pytest.raises(AgentSymbolNotAllowed):
        tools.get_quote("TCS")


def test_symbol_allowlist_permits_listed_symbol():
    session, inst = _fake_session()
    config = AgentGuardrailConfig(symbol_allowlist=frozenset({"NIFTY", "RELIANCE"}))
    tools = AgentTools(session, AgentGuardrails(config))

    tools.get_quote("RELIANCE")  # must not raise


def test_no_allowlist_configured_permits_any_symbol():
    session, inst = _fake_session()
    tools = AgentTools(session)  # default guardrails, no allowlist

    tools.get_quote("ANYTHING")  # must not raise
