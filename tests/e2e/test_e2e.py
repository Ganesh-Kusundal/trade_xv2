from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from brokers.common.core.models import OrderRequest
from brokers.dhan import DhanBroker
from event_bus.tests.test_event_bus import Event, EventBus
from oms.tests.test_oms import OrderManager, OrderStatus
from portfolio.tests.test_portfolio import PortfolioTracker
from replay.tests.test_replay import ReplayEngine
from risk.tests.test_risk import RiskManager

# Import our modular classes from their isolation test packages
from strategy.tests.test_strategy import MovingAverageCrossoverStrategy, StrategyState


def test_full_trading_pipeline_e2e():
    """End-to-End test representing:
    Historical Replay -> Strategy Signal -> Risk Check -> OMS -> Dhan Broker -> Fill -> Position Update -> Exit -> PnL
    """

    # 1. Initialize all modular components
    ReplayEngine()
    strategy = MovingAverageCrossoverStrategy(period=3)
    risk = RiskManager(max_risk_per_trade=1000, daily_loss_limit=5000, max_exposure_units=3)
    oms = OrderManager()
    portfolio = PortfolioTracker()
    event_bus = EventBus()

    # Mock DhanBroker with connection mocked
    broker = DhanBroker(client_id="e2e_user", access_token="e2e_token")
    mock_dhan = MagicMock()
    mock_dhan.place_order.return_value = {
        "status": "success",
        "data": {"orderId": "DHAN12345"},
    }
    broker._dhan = mock_dhan
    broker._status = "CONNECTED"

    # Set up events list for the event bus subscriber
    execution_events = []
    event_bus.subscribe(lambda e: execution_events.append(e.payload))

    # 2. Setup historical market price series
    t0 = datetime(2026, 6, 11, 10, 0, 0)
    # Historic candles/prices: [100.0, 101.0, 102.0] -> SMA is 101.0
    history = [100.0, 101.0, 102.0]

    # 3. Step 1: Entry Trigger (Price crosses above SMA)
    t0 + timedelta(minutes=5)
    tick1_price = 105.0  # Above SMA of 101.0

    # Evaluate Strategy
    signal = strategy.evaluate(history, current_price=tick1_price)
    assert signal == "BUY"
    assert strategy.state == StrategyState.SIGNAL_GENERATED

    # 4. Step 2: Risk Management Verification
    # Target size based on 2% risk on 50,000 equity, SL=95.0 -> Risk amount = 1000. SL distance = 10 -> Size = 100
    size = risk.calculate_position_size(
        account_equity=50000.0, risk_percent=0.02, entry_price=tick1_price, stop_loss=95.0
    )
    assert size == 100

    # Check if risk constraints allow the trade
    is_allowed = risk.check_trade(size=size, entry_price=tick1_price, stop_loss=95.0)
    assert is_allowed is True

    # 5. Step 3: Order Routing & Broker Execution
    if is_allowed:
        # Create OMS order
        order = oms.create_order("ORD_E2E_001", size, tick1_price)
        assert order.status == OrderStatus.PENDING

        # Place order via Broker
        order_req = OrderRequest(
            symbol="RELIANCE",
            exchange="NSE",
            quantity=size,
            price=Decimal(str(tick1_price)),
            order_type="LIMIT",
        )
        broker_resp = broker.place_order(order_req)
        assert broker_resp.success is True
        assert broker_resp.order_id == "DHAN12345"

        # OMS transition order status
        oms.open_order("ORD_E2E_001")
        assert order.status == OrderStatus.OPEN

        # Publish event
        event_bus.publish(Event("EVT_001", f"Order placed: {order.order_id}"))

    # 6. Step 4: Fill Event Processing & Portfolio aggregation
    # Simulate trade execution fill
    oms.process_fill("ORD_E2E_001", size)
    assert order.status == OrderStatus.FILLED

    # Update portfolio position
    portfolio.record_fill("RELIANCE", size, tick1_price, is_buy=True)
    pos = portfolio.get_position("RELIANCE")
    assert pos.quantity == 100
    assert pos.avg_price == 105.0
    assert pos.realized_pnl == 0.0

    event_bus.publish(Event("EVT_002", f"Order filled: {order.order_id}"))

    # Update active positions count in risk manager
    risk.active_positions_count = 1

    # 7. Step 5: Exit Trigger (Price crosses below SMA)
    # New prices: [101.0, 102.0, 105.0] -> SMA is 102.66
    history2 = [101.0, 102.0, 105.0]
    tick2_price = 100.0  # Below SMA of 102.66

    # Evaluate strategy state change
    strategy.evaluate(history2, current_price=105.0)  # transition to IN_POSITION
    assert strategy.state == StrategyState.IN_POSITION

    exit_signal = strategy.evaluate(history2, current_price=tick2_price)
    assert exit_signal == "SELL"
    assert strategy.state == StrategyState.IDLE

    # 8. Step 6: Process Exit and Realize PnL
    oms.create_order("ORD_E2E_002", size, tick2_price)
    oms.open_order("ORD_E2E_002")
    oms.process_fill("ORD_E2E_002", size)

    portfolio.record_fill("RELIANCE", size, tick2_price, is_buy=False)

    # PnL: (Exit 100 - Entry 105) * 100 = -500.0
    assert pos.quantity == 0
    assert pos.realized_pnl == -500.0

    event_bus.publish(Event("EVT_003", "Position fully exited"))

    # Process all events in the queue
    while event_bus.process_next():
        pass

    # Verify event delivery log
    assert len(execution_events) == 3
    assert execution_events[0] == "Order placed: ORD_E2E_001"
    assert execution_events[1] == "Order filled: ORD_E2E_001"
    assert execution_events[2] == "Position fully exited"
