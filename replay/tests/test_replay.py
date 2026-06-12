from datetime import datetime, time, timedelta


class MarketEvent:
    def __init__(self, timestamp: datetime, symbol: str, price: float):
        self.timestamp = timestamp
        self.symbol = symbol
        self.price = price


class ReplayEngine:
    """Mock Replay Engine for historical market data simulation."""

    def __init__(self):
        self.simulated_now: datetime = datetime.min
        self.processed_events: list[MarketEvent] = []

    def is_market_open(self, timestamp: datetime) -> bool:
        # Standard NSE market hours: 09:15 to 15:30
        current_time = timestamp.time()
        market_start = time(9, 15)
        market_end = time(15, 30)

        # Check weekdays (0 = Monday, 4 = Friday)
        if timestamp.weekday() > 4:
            return False

        return market_start <= current_time <= market_end

    def replay_events(self, events: list[MarketEvent]) -> int:
        count = 0
        for event in events:
            # Time simulation: simulated clock advances to current event time
            self.simulated_now = event.timestamp

            # Check market session hours
            if self.is_market_open(event.timestamp):
                self.processed_events.append(event)
                count += 1

        return count


# ── Tests ──────────────────────────────────────────────────────────────────


def test_time_simulation_stepping():
    engine = ReplayEngine()
    start_time = datetime(2026, 6, 11, 9, 30, 0)

    events = [
        MarketEvent(start_time, "RELIANCE", 2500.0),
        MarketEvent(start_time + timedelta(minutes=5), "RELIANCE", 2505.0),
        MarketEvent(start_time + timedelta(minutes=10), "RELIANCE", 2502.0),
    ]

    engine.replay_events(events)
    # The clock should match the timestamp of the last event
    assert engine.simulated_now == start_time + timedelta(minutes=10)
    assert len(engine.processed_events) == 3


def test_market_session_hours_check():
    engine = ReplayEngine()

    # 1. Weekday during trading hours (Thursday 10:00 AM) -> Open
    open_time = datetime(2026, 6, 11, 10, 0, 0)
    assert engine.is_market_open(open_time) is True

    # 2. Weekday before market opens (Thursday 8:30 AM) -> Closed
    early_time = datetime(2026, 6, 11, 8, 30, 0)
    assert engine.is_market_open(early_time) is False

    # 3. Weekday after market closes (Thursday 4:00 PM) -> Closed
    late_time = datetime(2026, 6, 11, 16, 0, 0)
    assert engine.is_market_open(late_time) is False

    # 4. Weekend (Saturday 11:00 AM) -> Closed
    weekend_time = datetime(2026, 6, 13, 11, 0, 0)
    assert engine.is_market_open(weekend_time) is False


def test_historical_replay_filters_off_market_hours():
    engine = ReplayEngine()
    t = datetime(2026, 6, 11, 9, 0, 0)  # Thursday 9:00 AM (Closed)

    events = [
        MarketEvent(t, "SBIN", 500.0),  # 9:00 AM (Skip)
        MarketEvent(t + timedelta(minutes=20), "SBIN", 502.0),  # 9:20 AM (Replay)
        MarketEvent(t + timedelta(hours=8), "SBIN", 501.0),  # 5:00 PM (Skip)
    ]

    played_count = engine.replay_events(events)
    assert played_count == 1
    assert len(engine.processed_events) == 1
    assert engine.processed_events[0].price == 502.0
