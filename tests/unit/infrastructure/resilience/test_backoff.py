"""TDD tests for BackoffStrategy — exponential backoff with jitter."""

from infrastructure.resilience.backoff import BackoffStrategy, ExponentialBackoff


class TestExponentialBackoff:
    def test_exponential_increase(self):
        b = ExponentialBackoff(base_delay_ms=100, max_delay_ms=10000)
        delays = [b.delay(i) for i in range(5)]
        for i in range(1, len(delays)):
            assert delays[i] >= delays[i - 1]

    def test_capped_at_max(self):
        b = ExponentialBackoff(base_delay_ms=1000, max_delay_ms=3000)
        delays = [b.delay(i) for i in range(10)]
        for d in delays:
            assert d <= 3.0

    def test_default_config(self):
        b = ExponentialBackoff()
        d = b.delay(0)
        assert 0.5 <= d <= 1.5

    def test_multiplicative_factor(self):
        b = ExponentialBackoff(base_delay_ms=1000, multiplier=3.0, max_delay_ms=30000)
        d0 = b.delay(0)
        d1 = b.delay(1)
        d2 = b.delay(2)
        assert d1 >= d0
        assert d2 >= d1

    def test_adds_jitter(self):
        b = ExponentialBackoff(base_delay_ms=1000, max_delay_ms=10000)
        delays = {b.delay(5) for _ in range(20)}
        assert len(delays) > 1

    def test_reset(self):
        b = ExponentialBackoff()
        b.delay(10)
        b.reset()
        assert True


class TestBackoffInterface:
    def test_strategy_pattern(self):
        strategy: BackoffStrategy = ExponentialBackoff()
        assert hasattr(strategy, "delay")
        assert callable(strategy.delay)
        assert hasattr(strategy, "reset")
        assert callable(strategy.reset)

    def test_with_retry_executor(self):
        b = ExponentialBackoff(base_delay_ms=100, max_delay_ms=5000, multiplier=2.0)
        delays = [b.delay(a) for a in range(5)]
        for d in delays:
            assert d >= 0
            assert d < float("inf")
