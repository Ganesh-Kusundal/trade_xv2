from src.domain.enums import (
    OrderSide, OrderType, OrderStatus, TimeInForce,
    Environment, BrokerId, AssetClass,
    SignalDirection,
    RiskLevel, DriftSeverity
)


class TestOrderSide:
    def test_buy(self):
        assert OrderSide.BUY == "BUY"

    def test_sell(self):
        assert OrderSide.SELL == "SELL"


class TestOrderType:
    def test_market(self):
        assert OrderType.MARKET == "MARKET"

    def test_limit(self):
        assert OrderType.LIMIT == "LIMIT"

    def test_stop(self):
        assert OrderType.STOP == "STOP"

    def test_stop_limit(self):
        assert OrderType.STOP_LIMIT == "STOP_LIMIT"


class TestOrderStatus:
    def test_pending(self):
        assert OrderStatus.PENDING == "PENDING"

    def test_submitted(self):
        assert OrderStatus.SUBMITTED == "SUBMITTED"

    def test_partially_filled(self):
        assert OrderStatus.PARTIALLY_FILLED == "PARTIALLY_FILLED"

    def test_filled(self):
        assert OrderStatus.FILLED == "FILLED"

    def test_cancelled(self):
        assert OrderStatus.CANCELLED == "CANCELLED"

    def test_rejected(self):
        assert OrderStatus.REJECTED == "REJECTED"

    def test_unknown(self):
        assert OrderStatus.UNKNOWN == "UNKNOWN"


class TestTimeInForce:
    def test_day(self):
        assert TimeInForce.DAY == "DAY"

    def test_ioc(self):
        assert TimeInForce.IOC == "IOC"

    def test_gtc(self):
        assert TimeInForce.GTC == "GTC"


class TestEnvironment:
    def test_replay(self):
        assert Environment.REPLAY == "REPLAY"

    def test_backtest(self):
        assert Environment.BACKTEST == "BACKTEST"

    def test_paper(self):
        assert Environment.PAPER == "PAPER"

    def test_live(self):
        assert Environment.LIVE == "LIVE"


class TestBrokerId:
    def test_dhan(self):
        assert BrokerId.DHAN == "dhan"

    def test_upstox(self):
        assert BrokerId.UPSTOX == "upstox"

    def test_paper(self):
        assert BrokerId.PAPER == "paper"



class TestAssetClass:
    def test_equity(self):
        assert AssetClass.EQUITY == "EQUITY"

    def test_derivative(self):
        assert AssetClass.DERIVATIVE == "DERIVATIVE"

    def test_commodity(self):
        assert AssetClass.COMMODITY == "COMMODITY"



class TestSignalDirection:
    def test_buy(self):
        assert SignalDirection.BUY == "BUY"

    def test_sell(self):
        assert SignalDirection.SELL == "SELL"

    def test_neutral(self):
        assert SignalDirection.NEUTRAL == "NEUTRAL"


class TestRiskLevel:
    def test_info(self):
        assert RiskLevel.INFO == "INFO"

    def test_warning(self):
        assert RiskLevel.WARNING == "WARNING"

    def test_critical(self):
        assert RiskLevel.CRITICAL == "CRITICAL"


class TestDriftSeverity:
    def test_low(self):
        assert DriftSeverity.LOW == "LOW"

    def test_medium(self):
        assert DriftSeverity.MEDIUM == "MEDIUM"

    def test_high(self):
        assert DriftSeverity.HIGH == "HIGH"
