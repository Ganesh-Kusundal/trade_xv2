from application.oms._internal.trading_state import TradingState, TradingStateEnum


def test_default_state_is_active():
    state = TradingState()
    assert state.state == TradingStateEnum.ACTIVE


def test_active_allows_all_orders():
    state = TradingState()
    assert state.allows_new_order()
    assert state.allows_new_order(side="BUY", current_qty=0, new_qty=10)


def test_halted_denies_all_orders():
    state = TradingState()
    state.set_state(TradingStateEnum.HALTED)
    assert not state.allows_new_order()


def test_reducing_allows_only_reduce_orders():
    state = TradingState()
    state.set_state(TradingStateEnum.REDUCING)
    # Selling to reduce long position: allowed
    assert state.allows_new_order(side="SELL", current_qty=10, new_qty=5)
    # Buying to increase position: denied
    assert not state.allows_new_order(side="BUY", current_qty=0, new_qty=5)
    # No position to reduce: denied
    assert not state.allows_new_order(side="SELL", current_qty=0, new_qty=5)


def test_reducing_allows_cover_short():
    state = TradingState()
    state.set_state(TradingStateEnum.REDUCING)
    # Buying to cover short: allowed
    assert state.allows_new_order(side="BUY", current_qty=-10, new_qty=10)


def test_state_transitions():
    state = TradingState()
    assert state.state == TradingStateEnum.ACTIVE
    state.set_state(TradingStateEnum.HALTED)
    assert state.state == TradingStateEnum.HALTED
    state.set_state(TradingStateEnum.ACTIVE)
    assert state.state == TradingStateEnum.ACTIVE
