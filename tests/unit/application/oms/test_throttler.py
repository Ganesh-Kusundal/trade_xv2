import time

from application.oms._internal.throttler import Throttler


def test_throttler_allows_within_limit():
    throttler = Throttler(max_per_second=5)
    for _ in range(5):
        assert throttler.allow()


def test_throttler_denies_burst():
    throttler = Throttler(max_per_second=5)
    for _ in range(5):
        assert throttler.allow()
    assert not throttler.allow()  # 6th request denied


def test_throttler_allows_after_window():
    throttler = Throttler(max_per_second=2, window_seconds=0.1)
    assert throttler.allow()
    assert throttler.allow()
    assert not throttler.allow()
    time.sleep(0.15)  # Wait for window to expire
    assert throttler.allow()


def test_throttler_remaining_count():
    throttler = Throttler(max_per_second=5)
    assert throttler.remaining == 5
    throttler.allow()
    assert throttler.remaining == 4


def test_throttler_reset():
    throttler = Throttler(max_per_second=2)
    throttler.allow()
    throttler.allow()
    assert not throttler.allow()
    throttler.reset()
    assert throttler.allow()
