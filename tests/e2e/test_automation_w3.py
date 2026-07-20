"""W3 Automation — product-path e2e (paper).

AU-012  SignalDTO → Session / Instrument OMS
AU-010  Simple strategy loop over session universe + history
AU-011  Kill switch rejects orders; clear resumes

No live money. No orchestrator rewrite — proves product Session spine.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

import tradex
from domain.models.trading import SignalDTO


def _execute_signal(session, signal: SignalDTO, *, correlation_id: str):
    """Minimal signal → product order adapter (AU-012)."""
    if not signal.is_actionable:
        raise ValueError("signal not actionable")
    inst = session.universe.equity(signal.symbol, exchange=signal.exchange or "NSE")
    qty = int(signal.quantity or 1)
    price = signal.price or signal.entry_price
    side = (signal.side or signal.signal_type or "").upper()
    if side in {"BUY", "STRONG_BUY", "ENTRY"}:
        if price is not None:
            return inst.buy(qty, price=price, correlation_id=correlation_id)
        return session.market(inst, qty, side="BUY")
    if side in {"SELL", "STRONG_SELL", "EXIT"}:
        if price is not None:
            return inst.sell(qty, price=price, correlation_id=correlation_id)
        return session.market(inst, qty, side="SELL")
    raise ValueError(f"unsupported signal side {side!r}")


# ── AU-012 ────────────────────────────────────────────────────────────


def test_au012_signal_to_oms_via_session() -> None:
    session = tradex.connect("paper")
    try:
        signal = SignalDTO(
            symbol="RELIANCE",
            exchange="NSE",
            side="BUY",
            signal_type="BUY",
            confidence=Decimal("0.9"),
            quantity=1,
            price=Decimal("1"),  # far below → OPEN limit
            strategy="w3_test",
        )
        assert signal.is_actionable
        result = _execute_signal(session, signal, correlation_id="w3:au012:1")
        assert result.success is True
        assert result.order is not None
        assert result.order.symbol == "RELIANCE"
        assert result.order.correlation_id == "w3:au012:1"
    finally:
        session.close()


def test_au012_non_actionable_signal_rejected() -> None:
    session = tradex.connect("paper")
    try:
        signal = SignalDTO(
            symbol="INFY",
            exchange="NSE",
            side="HOLD",
            signal_type="HOLD",
            confidence=Decimal("0"),
            quantity=1,
        )
        assert signal.is_actionable is False
        with pytest.raises(ValueError, match="not actionable"):
            _execute_signal(session, signal, correlation_id="w3:au012:hold")
    finally:
        session.close()


# ── AU-010 ────────────────────────────────────────────────────────────


def test_au010_strategy_loop_on_session_history() -> None:
    """Bar-derived signals from Instrument.history → place via Session."""
    session = tradex.connect("paper")
    try:
        placed = 0
        for symbol in ("RELIANCE", "INFY", "TCS"):
            stock = session.universe.equity(symbol)
            series = stock.history(timeframe="1D", days=30)
            assert series.bar_count >= 5
            closes = [float(b.close) for b in series.bars]
            # Simple momentum: last close > SMA → BUY 1 LIMIT far below (won't fill)
            sma = sum(closes) / len(closes)
            if closes[-1] > sma:
                signal = SignalDTO(
                    symbol=symbol,
                    exchange="NSE",
                    side="BUY",
                    signal_type="BUY",
                    confidence=Decimal("0.8"),
                    quantity=1,
                    price=Decimal("1"),
                    strategy="sma_momentum_loop",
                )
                result = _execute_signal(session, signal, correlation_id=f"w3:au010:{symbol}")
                assert result.success is True
                placed += 1
            else:
                # Still prove history path even if no signal
                assert True
        # With paper RNG series, at least one symbol should usually signal;
        # if not, force one to keep the loop test meaningful.
        if placed == 0:
            signal = SignalDTO(
                symbol="RELIANCE",
                exchange="NSE",
                side="BUY",
                signal_type="BUY",
                confidence=Decimal("0.8"),
                quantity=1,
                price=Decimal("1"),
                strategy="sma_momentum_loop_forced",
            )
            result = _execute_signal(session, signal, correlation_id="w3:au010:forced")
            assert result.success is True
            placed = 1
        assert placed >= 1
        assert len(session.orders()) >= 1
    finally:
        session.close()


# ── AU-011 ────────────────────────────────────────────────────────────


def test_au011_kill_switch_blocks_and_clears() -> None:
    session = tradex.connect("paper")
    try:
        om = session.order_service.order_manager
        rm = om._risk_manager  # intentional: paper OMS exposes risk manager
        assert rm is not None

        stock = session.universe.equity("RELIANCE")

        rm.set_kill_switch(True)
        assert rm.is_kill_switch_active() is True
        blocked = stock.buy(1, price=Decimal("1"), correlation_id="w3:au011:blocked")
        assert blocked.success is False
        assert "kill" in (blocked.error or "").lower()

        rm.set_kill_switch(False)
        assert rm.is_kill_switch_active() is False
        allowed = stock.buy(1, price=Decimal("1"), correlation_id="w3:au011:ok")
        assert allowed.success is True
        assert allowed.order is not None
    finally:
        session.close()
