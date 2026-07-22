"""In-memory metrics collector."""

from infrastructure.observability.metrics import Metrics


def test_increment_and_gauge() -> None:
    m = Metrics()
    m.increment("orders_submitted_total")
    m.increment("orders_submitted_total", value=2)
    m.gauge("position_count", 5)
    assert m.get("orders_submitted_total") == 3
    assert m.get("position_count") == 5
