class RiskManager:
    """Mock Risk Management module for isolation testing."""

    def __init__(self, max_risk_per_trade: float, daily_loss_limit: float, max_exposure_units: int):
        self.max_risk_per_trade = max_risk_per_trade
        self.daily_loss_limit = daily_loss_limit
        self.max_exposure_units = max_exposure_units
        self.realized_pnl = 0.0
        self.active_positions_count = 0

    def calculate_position_size(
        self, account_equity: float, risk_percent: float, entry_price: float, stop_loss: float
    ) -> int:
        if entry_price <= stop_loss:
            return 0
        risk_amount = account_equity * risk_percent
        sl_distance = entry_price - stop_loss
        position_size = int(risk_amount / sl_distance)
        return position_size

    def check_trade(self, size: int, entry_price: float, stop_loss: float) -> bool:
        # Check daily loss limit
        if self.realized_pnl <= -self.daily_loss_limit:
            return False

        # Check max risk per trade
        risk = size * (entry_price - stop_loss)
        if risk > self.max_risk_per_trade:
            return False

        # Check active exposure limits
        return not self.active_positions_count >= self.max_exposure_units


# ── Tests ──────────────────────────────────────────────────────────────────


def test_position_sizing_calculation():
    risk_mgr = RiskManager(max_risk_per_trade=5000, daily_loss_limit=10000, max_exposure_units=5)

    # Capital: 100,000; Risk: 2% = 2,000; Entry: 100, SL: 95 (Diff: 5)
    # Target size = 2000 / 5 = 400 shares
    size = risk_mgr.calculate_position_size(
        account_equity=100000.0, risk_percent=0.02, entry_price=100.0, stop_loss=95.0
    )
    assert size == 400


def test_max_risk_limit():
    risk_mgr = RiskManager(max_risk_per_trade=1000, daily_loss_limit=5000, max_exposure_units=3)

    # 1. Trade size: 100, Risk distance: 5. Total risk = 500 <= 1000 -> Allowed
    assert risk_mgr.check_trade(size=100, entry_price=100.0, stop_loss=95.0) is True

    # 2. Trade size: 300, Risk distance: 5. Total risk = 1500 > 1000 -> Blocked
    assert risk_mgr.check_trade(size=300, entry_price=100.0, stop_loss=95.0) is False


def test_daily_loss_limit_checks():
    risk_mgr = RiskManager(max_risk_per_trade=1000, daily_loss_limit=2000, max_exposure_units=3)

    # PnL is flat -> Trade allowed
    assert risk_mgr.check_trade(size=100, entry_price=100.0, stop_loss=95.0) is True

    # PnL is at daily loss limit -> Trade blocked
    risk_mgr.realized_pnl = -2500.0
    assert risk_mgr.check_trade(size=100, entry_price=100.0, stop_loss=95.0) is False


def test_exposure_limit_checks():
    risk_mgr = RiskManager(max_risk_per_trade=1000, daily_loss_limit=5000, max_exposure_units=2)

    # Active positions count: 1 -> Allowed
    risk_mgr.active_positions_count = 1
    assert risk_mgr.check_trade(size=100, entry_price=100.0, stop_loss=95.0) is True

    # Active positions count: 2 (at limit) -> Blocked
    risk_mgr.active_positions_count = 2
    assert risk_mgr.check_trade(size=100, entry_price=100.0, stop_loss=95.0) is False
