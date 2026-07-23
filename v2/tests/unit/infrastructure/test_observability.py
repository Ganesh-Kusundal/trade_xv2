"""Observability: Metrics, Audit, Health — combined test suite."""

from domain.enums import ComponentState
from infrastructure.observability.audit import AuditSink
from infrastructure.observability.health import ComponentHealth, HealthRegistry
from infrastructure.observability.metrics import Metrics


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def test_increment_counter() -> None:
    m = Metrics()
    m.increment("orders_submitted_total")
    m.increment("orders_submitted_total")
    assert m.get("orders_submitted_total") == 2


def test_increment_counter_with_value() -> None:
    m = Metrics()
    m.increment("orders_filled_total", value=3)
    assert m.get("orders_filled_total") == 3


def test_observe_histogram() -> None:
    m = Metrics()
    m.observe("order_latency_seconds", 0.05)
    m.observe("order_latency_seconds", 0.12)
    # get returns count for histograms
    assert m.get("order_latency_seconds") == 2


def test_gauge_set_get() -> None:
    m = Metrics()
    m.gauge("position_count", 5)
    assert m.get("position_count") == 5
    m.gauge("position_count", 8)
    assert m.get("position_count") == 8


def test_labels_create_separate_keys() -> None:
    m = Metrics()
    m.increment("orders_submitted_total", labels={"broker": "DHAN", "side": "BUY"})
    m.increment("orders_submitted_total", labels={"broker": "DHAN", "side": "SELL"})
    m.increment("orders_submitted_total", labels={"broker": "UPSTOX", "side": "BUY"})
    assert m.get("orders_submitted_total", labels={"broker": "DHAN", "side": "BUY"}) == 1
    assert m.get("orders_submitted_total", labels={"broker": "DHAN", "side": "SELL"}) == 1
    assert m.get("orders_submitted_total", labels={"broker": "UPSTOX", "side": "BUY"}) == 1


def test_gauge_with_labels() -> None:
    m = Metrics()
    m.gauge("unrealized_pnl", 1500.0, labels={"account": "ACC1"})
    m.gauge("unrealized_pnl", -200.0, labels={"account": "ACC2"})
    assert m.get("unrealized_pnl", labels={"account": "ACC1"}) == 1500.0
    assert m.get("unrealized_pnl", labels={"account": "ACC2"}) == -200.0


def test_get_returns_zero_for_missing() -> None:
    m = Metrics()
    assert m.get("nonexistent") == 0.0
    assert m.get("nonexistent", labels={"x": "y"}) == 0.0


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def test_audit_appends_entries() -> None:
    sink = AuditSink()
    sink.record({"event_type": "ORDER_SUBMITTED", "actor": "oms"})
    sink.record({"event_type": "FILL", "actor": "execution"})
    assert len(sink.records) == 2
    assert sink.records[0]["event_type"] == "ORDER_SUBMITTED"
    assert sink.records[1]["event_type"] == "FILL"


def test_audit_read_returns_copy() -> None:
    sink = AuditSink()
    sink.record("a")
    view = sink.records
    view.append("mutated")
    assert sink.records == ["a"]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health_registry_update_and_get() -> None:
    reg = HealthRegistry()
    h = ComponentHealth(
        component_id="message_bus",
        state=ComponentState.RUNNING,
        metrics={"queue_depth": 0},
    )
    reg.update(h)
    assert reg.get("message_bus") == h


def test_health_registry_all() -> None:
    reg = HealthRegistry()
    reg.update(ComponentHealth(component_id="a", state=ComponentState.RUNNING))
    reg.update(ComponentHealth(component_id="b", state=ComponentState.ERROR))
    assert len(reg.all()) == 2
    states = {h.state for h in reg.all()}
    assert states == {"RUNNING", "ERROR"}
