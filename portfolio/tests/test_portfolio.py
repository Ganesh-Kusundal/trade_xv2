class Position:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.quantity = 0
        self.avg_price = 0.0
        self.realized_pnl = 0.0

    def add_fill(self, qty: int, price: float, is_buy: bool) -> None:
        direction = 1 if is_buy else -1

        # 1. Opening/increasing position
        if (
            self.quantity == 0
            or (self.quantity > 0 and is_buy)
            or (self.quantity < 0 and not is_buy)
        ):
            total_cost = (self.quantity * self.avg_price) + (qty * price * direction)
            self.quantity += qty * direction
            self.avg_price = abs(total_cost / self.quantity)

        # 2. Closing/reducing position
        else:
            abs_qty = abs(self.quantity)
            # Full or partial reduction
            reduce_qty = min(qty, abs_qty)
            pnl_direction = 1 if self.quantity > 0 else -1
            self.realized_pnl += (price - self.avg_price) * reduce_qty * pnl_direction

            self.quantity += qty * direction
            if self.quantity == 0:
                self.avg_price = 0.0

            # If position flipped from Long to Short (or vice versa), handle the remainder
            remainder = qty - reduce_qty
            if remainder > 0:
                self.avg_price = price

    def unrealized_pnl(self, current_price: float) -> float:
        if self.quantity == 0:
            return 0.0
        pnl_direction = 1 if self.quantity > 0 else -1
        return (current_price - self.avg_price) * abs(self.quantity) * pnl_direction


class PortfolioTracker:
    """Mock Portfolio Tracker for position aggregation and PnL calculation."""

    def __init__(self):
        self.positions: dict[str, Position] = {}

    def get_position(self, symbol: str) -> Position:
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol)
        return self.positions[symbol]

    def record_fill(self, symbol: str, qty: int, price: float, is_buy: bool) -> None:
        pos = self.get_position(symbol)
        pos.add_fill(qty, price, is_buy)


# ── Tests ──────────────────────────────────────────────────────────────────


def test_position_long_aggregation():
    portfolio = PortfolioTracker()

    # Buy 10 RELIANCE at 2500
    portfolio.record_fill("RELIANCE", 10, 2500.0, is_buy=True)
    pos = portfolio.get_position("RELIANCE")
    assert pos.quantity == 10
    assert pos.avg_price == 2500.0

    # Buy 10 more RELIANCE at 2600 -> Avg cost: 2550
    portfolio.record_fill("RELIANCE", 10, 2600.0, is_buy=True)
    assert pos.quantity == 20
    assert pos.avg_price == 2550.0


def test_realized_and_unrealized_pnl():
    portfolio = PortfolioTracker()

    # Buy 10 shares at 100
    portfolio.record_fill("SBIN", 10, 100.0, is_buy=True)
    pos = portfolio.get_position("SBIN")

    # Unrealized PnL if market is at 105 -> +50
    assert pos.unrealized_pnl(105.0) == 50.0
    assert pos.realized_pnl == 0.0

    # Sell 5 shares at 110 (Reduce)
    portfolio.record_fill("SBIN", 5, 110.0, is_buy=False)
    assert pos.quantity == 5
    assert pos.avg_price == 100.0
    # Realized PnL: (110 - 100) * 5 = +50
    assert pos.realized_pnl == 50.0
    # Unrealized PnL at 105: (105 - 100) * 5 = +25
    assert pos.unrealized_pnl(105.0) == 25.0
