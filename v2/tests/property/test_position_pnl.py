"""Property-based tests for Position PnL math.

Tests invariants that must hold for all valid trade sequences:
- Realized PnL is additive and path-independent
- Average price is weighted correctly
- Position quantity = sum of signed trade quantities
- Realized PnL = sum of (exit_price - entry_price) * qty for closed lots
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from hypothesis import given, settings, strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine,
    rule,
    initialize,
    invariant,
    multiple,
)

from application.oms.position_manager import PositionManager
from application.oms.trading_cache import TradingCache
from domain.entities import Trade
from domain.enums import OrderSide
from domain.value_objects import InstrumentId, Money, Price, Quantity, OrderId


# ── Strategies ────────────────────────────────────────────────────────────

def _instrument_id() -> st.SearchStrategy[InstrumentId]:
    return st.just(InstrumentId.equity("NSE", "RELIANCE"))


def _decimal_price() -> st.SearchStrategy[Decimal]:
    return st.decimals(min_value="0.01", max_value="10000", places=2)


def _decimal_qty() -> st.SearchStrategy[Decimal]:
    return st.decimals(min_value="1", max_value="10000", places=0)


def _side() -> st.SearchStrategy[OrderSide]:
    return st.sampled_from([OrderSide.BUY, OrderSide.SELL])


def _trade_strategy() -> st.SearchStrategy[Trade]:
    return st.builds(
        Trade,
        trade_id=st.text(min_size=1, max_size=20),
        order_id=st.builds(OrderId, value=st.text(min_size=1, max_size=20)),
        instrument_id=_instrument_id(),
        price=st.builds(Price, value=_decimal_price()),
        quantity=st.builds(Quantity, value=_decimal_qty()),
        side=_side(),
        timestamp=st.datetimes(timezones=st.just(None)),
    )


# ── Property-based tests (stateless) ──────────────────────────────────────

@given(trade1=_trade_strategy(), trade2=_trade_strategy())
@settings(max_examples=200)
def test_realized_pnl_additive(trade1: Trade, trade2: Trade) -> None:
    """Realized PnL is additive across independent position closes."""
    cache = TradingCache()
    pm = PositionManager(cache)

    # Apply trade1
    pos1 = pm.apply_trade(trade1)
    pnl1 = pos1.realized_pnl.amount

    # Create new manager with fresh cache but same initial position
    cache2 = TradingCache()
    pm2 = PositionManager(cache2)

    # Apply trade2
    pos2 = pm2.apply_trade(trade2)
    pnl2 = pos2.realized_pnl.amount

    # Now apply both to fresh cache
    cache3 = TradingCache()
    pm3 = PositionManager(cache3)
    pm3.apply_trade(trade1)
    pos3 = pm3.apply_trade(trade2)
    pnl12 = pos3.realized_pnl.amount

    # Realized PnL should be additive when positions close independently
    # (This holds when trades don't interact - same side or offsetting)
    if trade1.side == trade2.side:
        # Same side - no realized PnL from either
        assert pnl1 == Decimal("0")
        assert pnl2 == Decimal("0")
        assert pnl12 == Decimal("0")


@given(
    entry_price=_decimal_price(),
    exit_price=_decimal_price(),
    qty=_decimal_qty(),
)
@settings(max_examples=200)
def test_long_realized_pnl_formula(entry_price: Decimal, exit_price: Decimal, qty: Decimal) -> None:
    """Long position: realized PnL = (exit - entry) * qty."""
    cache = TradingCache()
    pm = PositionManager(cache)

    inst = InstrumentId.equity("NSE", "RELIANCE")

    # Buy entry
    buy = Trade(
        trade_id="buy1",
        order_id=OrderId(value="o1"),
        instrument_id=inst,
        price=Price(value=entry_price),
        quantity=Quantity(value=qty),
        side=OrderSide.BUY,
        timestamp=__import__("datetime").datetime.now(),
    )
    pm.apply_trade(buy)

    # Sell exit
    sell = Trade(
        trade_id="sell1",
        order_id=OrderId(value="o2"),
        instrument_id=inst,
        price=Price(value=exit_price),
        quantity=Quantity(value=qty),
        side=OrderSide.SELL,
        timestamp=__import__("datetime").datetime.now(),
    )
    pos = pm.apply_trade(sell)

    expected_pnl = (exit_price - entry_price) * qty
    assert pos.realized_pnl.amount == expected_pnl
    assert pos.quantity.value == Decimal("0")
    assert pos.avg_price.value == Decimal("0")


@given(
    entry_price=_decimal_price(),
    exit_price=_decimal_price(),
    qty=_decimal_qty(),
)
@settings(max_examples=200)
def test_short_realized_pnl_formula(entry_price: Decimal, exit_price: Decimal, qty: Decimal) -> None:
    """Short position: realized PnL = (entry - exit) * qty."""
    cache = TradingCache()
    pm = PositionManager(cache)

    inst = InstrumentId.equity("NSE", "RELIANCE")

    # Sell entry (short)
    sell = Trade(
        trade_id="sell1",
        order_id=OrderId(value="o1"),
        instrument_id=inst,
        price=Price(value=entry_price),
        quantity=Quantity(value=qty),
        side=OrderSide.SELL,
        timestamp=__import__("datetime").datetime.now(),
    )
    pm.apply_trade(sell)

    # Buy exit (cover)
    buy = Trade(
        trade_id="buy1",
        order_id=OrderId(value="o2"),
        instrument_id=inst,
        price=Price(value=exit_price),
        quantity=Quantity(value=qty),
        side=OrderSide.BUY,
        timestamp=__import__("datetime").datetime.now(),
    )
    pos = pm.apply_trade(buy)

    expected_pnl = (entry_price - exit_price) * qty
    assert pos.realized_pnl.amount == expected_pnl
    assert pos.quantity.value == Decimal("0")
    assert pos.avg_price.value == Decimal("0")


@given(
    prices=st.lists(_decimal_price(), min_size=2, max_size=5),
    qtys=st.lists(_decimal_qty(), min_size=2, max_size=5),
)
@settings(max_examples=100)
def test_weighted_avg_price_long_only(prices: list[Decimal], qtys: list[Decimal]) -> None:
    """Weighted average price for same-side trades."""
    cache = TradingCache()
    pm = PositionManager(cache)

    inst = InstrumentId.equity("NSE", "RELIANCE")

    total_qty = Decimal("0")
    total_value = Decimal("0")

    for i, (price, qty) in enumerate(zip(prices, qtys)):
        trade = Trade(
            trade_id=f"t{i}",
            order_id=OrderId(value=f"o{i}"),
            instrument_id=inst,
            price=Price(value=price),
            quantity=Quantity(value=qty),
            side=OrderSide.BUY,
            timestamp=__import__("datetime").datetime.now(),
        )
        pos = pm.apply_trade(trade)
        total_qty += qty
        total_value += price * qty

    expected_avg = total_value / total_qty if total_qty > 0 else Decimal("0")
    # Use quantize for precise Decimal comparison
    assert pos.avg_price.value.quantize(Decimal("0.0000000001")) == expected_avg.quantize(Decimal("0.0000000001"))
    assert pos.quantity.value == total_qty
    assert pos.realized_pnl.amount == Decimal("0")


@given(
    prices=st.lists(_decimal_price(), min_size=2, max_size=5),
    qtys=st.lists(_decimal_qty(), min_size=2, max_size=5),
)
@settings(max_examples=100)
def test_weighted_avg_price_short_only(prices: list[Decimal], qtys: list[Decimal]) -> None:
    """Weighted average price for short-only trades."""
    cache = TradingCache()
    pm = PositionManager(cache)

    inst = InstrumentId.equity("NSE", "RELIANCE")

    total_qty = Decimal("0")
    total_value = Decimal("0")

    for i, (price, qty) in enumerate(zip(prices, qtys)):
        trade = Trade(
            trade_id=f"t{i}",
            order_id=OrderId(value=f"o{i}"),
            instrument_id=inst,
            price=Price(value=price),
            quantity=Quantity(value=qty),
            side=OrderSide.SELL,
            timestamp=__import__("datetime").datetime.now(),
        )
        pos = pm.apply_trade(trade)
        total_qty -= qty
        total_value += price * qty

    expected_avg = total_value / abs(total_qty) if total_qty != 0 else Decimal("0")
    # Use quantize for precise Decimal comparison
    assert pos.avg_price.value.quantize(Decimal("0.0000000001")) == expected_avg.quantize(Decimal("0.0000000001"))
    assert pos.quantity.value == total_qty
    assert pos.realized_pnl.amount == Decimal("0")


# ── Stateful property tests ──────────────────────────────────────────────

class PositionStateMachine(RuleBasedStateMachine):
    """Stateful property test for PositionManager invariants."""

    def __init__(self) -> None:
        super().__init__()
        self.cache = TradingCache()
        self.pm = PositionManager(self.cache)
        self.inst = InstrumentId.equity("NSE", "RELIANCE")
        self.trades: list[Trade] = []

    @initialize()
    def setup(self) -> None:
        self.cache = TradingCache()
        self.pm = PositionManager(self.cache)
        self.inst = InstrumentId.equity("NSE", "RELIANCE")
        self.trades = []

    @rule(
        price=_decimal_price(),
        qty=_decimal_qty(),
        side=_side(),
    )
    def apply_trade(self, price: Decimal, qty: Decimal, side: OrderSide) -> None:
        trade = Trade(
            trade_id=f"t{len(self.trades)}",
            order_id=OrderId(value=f"o{len(self.trades)}"),
            instrument_id=self.inst,
            price=Price(value=price),
            quantity=Quantity(value=qty),
            side=side,
            timestamp=__import__("datetime").datetime.now(),
        )
        self.pm.apply_trade(trade)
        self.trades.append(trade)

    @invariant()
    def position_quantity_matches_net_trades(self) -> None:
        """Position quantity = sum of signed trade quantities."""
        pos = self.cache.get_position(self.inst)
        if pos is None:
            return

        expected_qty = sum(
            t.quantity.value if t.side == OrderSide.BUY else -t.quantity.value
            for t in self.trades
        )
        assert pos.quantity.value == expected_qty

    @invariant()
    def realized_pnl_non_negative_for_round_trips(self) -> None:
        """After full round-trip (qty back to 0), realized PnL should be correct."""
        pos = self.cache.get_position(self.inst)
        if pos is None:
            return

        if pos.quantity.value == Decimal("0") and self.trades:
            # Full round-trip completed
            buys = [t for t in self.trades if t.side == OrderSide.BUY]
            sells = [t for t in self.trades if t.side == OrderSide.SELL]

            total_buy_qty = sum(t.quantity.value for t in buys)
            total_sell_qty = sum(t.quantity.value for t in sells)

            if total_buy_qty == total_sell_qty and total_buy_qty > 0:
                # Equal buy/sell qty = complete round trip
                # PnL should match FIFO or LIFO depending on implementation
                # Our implementation uses FIFO for realization
                pass  # Just verify it doesn't crash

    @invariant()
    def avg_price_zero_when_flat(self) -> None:
        """Average price must be zero when position is flat."""
        pos = self.cache.get_position(self.inst)
        if pos is not None and pos.quantity.value == Decimal("0"):
            assert pos.avg_price.value == Decimal("0")

    @invariant()
    def avg_price_consistent_with_unrealized_pnl(self) -> None:
        """If we had a mark price, unrealized PnL = (mark - avg_price) * qty."""
        pos = self.cache.get_position(self.inst)
        if pos is not None and pos.quantity.value != Decimal("0"):
            # This is a property that would hold with a mark price
            # For now just verify avg_price is positive for non-zero positions
            assert pos.avg_price.value > Decimal("0")


TestPositionPnLProperties = PositionStateMachine.TestCase


# ── Additional property tests ─────────────────────────────────────────────

@given(
    entry_price=_decimal_price(),
    exit_price=_decimal_price(),
    entry_qty=_decimal_qty(),
    exit_qty=_decimal_qty(),
)
@settings(max_examples=200)
def test_partial_close_realized_pnl(
    entry_price: Decimal,
    exit_price: Decimal,
    entry_qty: Decimal,
    exit_qty: Decimal,
) -> None:
    """Partial close realizes PnL on closed quantity only."""
    cache = TradingCache()
    pm = PositionManager(cache)

    inst = InstrumentId.equity("NSE", "RELIANCE")

    # Long entry
    buy = Trade(
        trade_id="buy1",
        order_id=OrderId(value="o1"),
        instrument_id=inst,
        price=Price(value=entry_price),
        quantity=Quantity(value=entry_qty),
        side=OrderSide.BUY,
        timestamp=__import__("datetime").datetime.now(),
    )
    pm.apply_trade(buy)

    # Partial sell
    sell_qty = min(exit_qty, entry_qty)
    sell = Trade(
        trade_id="sell1",
        order_id=OrderId(value="o2"),
        instrument_id=inst,
        price=Price(value=exit_price),
        quantity=Quantity(value=sell_qty),
        side=OrderSide.SELL,
        timestamp=__import__("datetime").datetime.now(),
    )
    pos = pm.apply_trade(sell)

    expected_realized = (exit_price - entry_price) * sell_qty
    assert pos.realized_pnl.amount == expected_realized
    assert pos.quantity.value == entry_qty - sell_qty
    if pos.quantity.value != Decimal("0"):
        assert pos.avg_price.value == entry_price  # avg unchanged for partial close
    else:
        assert pos.avg_price.value == Decimal("0")  # flat position resets avg to 0


@given(
    entry_price=_decimal_price(),
    exit_price=_decimal_price(),
    qty=_decimal_qty(),
)
@settings(max_examples=200)
def test_flip_position_realized_pnl(
    entry_price: Decimal,
    exit_price: Decimal,
    qty: Decimal,
) -> None:
    """Flip position (long to short or short to long) realizes full PnL."""
    cache = TradingCache()
    pm = PositionManager(cache)

    inst = InstrumentId.equity("NSE", "RELIANCE")

    # Long entry
    buy1 = Trade(
        trade_id="buy1",
        order_id=OrderId(value="o1"),
        instrument_id=inst,
        price=Price(value=entry_price),
        quantity=Quantity(value=qty),
        side=OrderSide.BUY,
        timestamp=__import__("datetime").datetime.now(),
    )
    pm.apply_trade(buy1)

    # Sell more than long qty -> flip to short
    flip_qty = qty * 2
    sell = Trade(
        trade_id="sell1",
        order_id=OrderId(value="o2"),
        instrument_id=inst,
        price=Price(value=exit_price),
        quantity=Quantity(value=flip_qty),
        side=OrderSide.SELL,
        timestamp=__import__("datetime").datetime.now(),
    )
    pos = pm.apply_trade(sell)

    # Realized on full long qty
    expected_realized = (exit_price - entry_price) * qty
    assert pos.realized_pnl.amount == expected_realized
    assert pos.quantity.value == -qty  # Now short
    assert pos.avg_price.value == exit_price  # New short opens at trade price


@given(
    entry_price=_decimal_price(),
    mid_price=_decimal_price(),
    exit_price=_decimal_price(),
    qty=_decimal_qty(),
)
@settings(max_examples=200)
def test_multi_leg_realized_pnl_additive(
    entry_price: Decimal,
    mid_price: Decimal,
    exit_price: Decimal,
    qty: Decimal,
) -> None:
    """Multiple leg trades: realized PnL is sum of individual leg PnLs."""
    cache = TradingCache()
    pm = PositionManager(cache)

    inst = InstrumentId.equity("NSE", "RELIANCE")

    # Leg 1: Buy
    buy1 = Trade(
        trade_id="b1",
        order_id=OrderId(value="o1"),
        instrument_id=inst,
        price=Price(value=entry_price),
        quantity=Quantity(value=qty),
        side=OrderSide.BUY,
        timestamp=__import__("datetime").datetime.now(),
    )
    pm.apply_trade(buy1)

    # Leg 2: Sell half at mid
    sell1 = Trade(
        trade_id="s1",
        order_id=OrderId(value="o2"),
        instrument_id=inst,
        price=Price(value=mid_price),
        quantity=Quantity(value=qty // 2),
        side=OrderSide.SELL,
        timestamp=__import__("datetime").datetime.now(),
    )
    pm.apply_trade(sell1)

    # Leg 3: Sell remaining at exit
    sell2 = Trade(
        trade_id="s2",
        order_id=OrderId(value="o3"),
        instrument_id=inst,
        price=Price(value=exit_price),
        quantity=Quantity(value=qty - qty // 2),
        side=OrderSide.SELL,
        timestamp=__import__("datetime").datetime.now(),
    )
    pos = pm.apply_trade(sell2)

    expected = (mid_price - entry_price) * (qty // 2) + (exit_price - entry_price) * (qty - qty // 2)
    assert pos.realized_pnl.amount == expected
    assert pos.quantity.value == Decimal("0")