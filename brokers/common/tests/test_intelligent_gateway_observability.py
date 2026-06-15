"""Tests for IntelligentGateway observability — Phase A / A4.

These tests verify the contract that every silent ``except Exception: pass``
has been replaced with a log + metric emission, while the caller-visible
fallback behavior is preserved.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from unittest.mock import MagicMock

import pandas as pd
import pytest

from brokers.common.core.domain import FundLimits
from brokers.common.intelligent_gateway import IntelligentGateway
from brokers.common.observability.event_metrics import EventMetrics


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def metrics() -> EventMetrics:
    return EventMetrics()


@pytest.fixture
def gateway(metrics: EventMetrics) -> IntelligentGateway:
    return IntelligentGateway(
        dhan_gateway=MagicMock(name="dhan"),
        upstox_gateway=MagicMock(name="upstox"),
        metrics=metrics,
    )


def _fallback_count(metrics: EventMetrics, operation: str, broker: str) -> int:
    """Sum the fallback counter for an (operation, broker) pair across all
    exception types. Each unique exception class produces its own bucket
    in the metrics dict."""
    snap = metrics.snapshot().get("intelligent_gateway_fallback", {})
    total = 0
    for key, count in snap.items():
        # key shape: "<operation>:<broker>:<ExceptionType>"
        parts = key.split(":")
        if len(parts) >= 2 and parts[0] == operation and parts[1] == broker:
            total += count
    return total


# ── Observability: log + metric on every fallback ──────────────────────


def test_upstox_failure_logs_and_meters_then_falls_back_to_dhan(
    gateway: IntelligentGateway, metrics: EventMetrics, caplog
) -> None:
    """When Upstox raises, we log at WARNING, increment a metric, and
    fall through to Dhan. Caller never sees the exception."""
    gateway.upstox.ltp.side_effect = ConnectionError("upstox 503")
    gateway.dhan.ltp.return_value = Decimal("123.45")

    with caplog.at_level(logging.WARNING, logger="brokers.common.intelligent_gateway"):
        result = gateway.ltp("RELIANCE")

    assert result == Decimal("123.45"), "Caller must still receive the Dhan answer"
    assert _fallback_count(metrics, "ltp", "upstox") == 1
    fallback_logs = [r for r in caplog.records if r.message == "intelligent_gateway_fallback"]
    assert len(fallback_logs) == 1
    rec = fallback_logs[0]
    assert rec.levelname == "WARNING"
    assert getattr(rec, "operation") == "ltp"
    assert getattr(rec, "broker") == "upstox"
    assert getattr(rec, "exception_type") == "ConnectionError"
    assert "upstox 503" in getattr(rec, "exception_message")


def test_dhan_failure_logs_and_meters_then_falls_back_to_upstox(
    gateway: IntelligentGateway, metrics: EventMetrics, caplog
) -> None:
    gateway.dhan.history.side_effect = TimeoutError("dhan timed out")
    gateway.upstox.history.return_value = pd.DataFrame({"close": [100]})

    with caplog.at_level(logging.WARNING, logger="brokers.common.intelligent_gateway"):
        result = gateway.history("RELIANCE", "NSE", "1D", 30)

    assert isinstance(result, pd.DataFrame)
    assert _fallback_count(metrics, "history", "dhan") == 1
    fallback_logs = [r for r in caplog.records if r.message == "intelligent_gateway_fallback"]
    assert len(fallback_logs) == 1
    assert getattr(fallback_logs[0], "exception_type") == "TimeoutError"


def test_both_brokers_fail_secondary_exception_propagates(metrics: EventMetrics) -> None:
    """Document the contract: if the secondary broker also fails, its
    exception propagates. Only the *primary* broker's failure is
    silently logged and metered. The caller decides what to do with
    the propagated exception (e.g. retry, alert, surface to user).

    This is the behavior the previous implementation had, preserved
    by this refactor. Wrapping the secondary call would mask systemic
    failures and is deliberately out of scope for A4.
    """
    dhan = MagicMock(name="dhan")
    upstox = MagicMock(name="upstox")
    dhan.positions.side_effect = RuntimeError("dhan down")
    upstox.positions.side_effect = ConnectionError("upstox down")

    gw = IntelligentGateway(dhan_gateway=dhan, upstox_gateway=upstox, metrics=metrics)

    with pytest.raises(ConnectionError, match="upstox down"):
        gw.positions()

    # Only the primary broker's failure is metered
    assert _fallback_count(metrics, "positions", "dhan") == 1
    assert _fallback_count(metrics, "positions", "upstox") == 0


def test_no_brokers_configured_still_raises_runtime_error() -> None:
    """No broker available should still raise — observability change
    must not silently swallow the no-broker case."""
    gw = IntelligentGateway()  # both None
    with pytest.raises(RuntimeError, match="No broker available"):
        gw.ltp("RELIANCE")


def test_metrics_isolated_per_instance() -> None:
    """Two gateway instances must not share metrics — the test
    constructor argument controls isolation. Use different exception
    types so the metrics buckets are distinct (the bucket key includes
    the exception class name)."""
    a = EventMetrics()
    b = EventMetrics()
    g1 = IntelligentGateway(dhan_gateway=MagicMock(), metrics=a)
    g2 = IntelligentGateway(dhan_gateway=MagicMock(), metrics=b)

    g1.dhan.positions.side_effect = RuntimeError("x")
    g1.positions()

    g2.dhan.positions.side_effect = ConnectionError("y")
    g2.positions()

    assert a.snapshot() != b.snapshot(), "Metrics should be independent per instance"
    a_keys = list(a.snapshot()["intelligent_gateway_fallback"].keys())
    b_keys = list(b.snapshot()["intelligent_gateway_fallback"].keys())
    assert a_keys[0].endswith(":RuntimeError")
    assert b_keys[0].endswith(":ConnectionError")


# ── Method-by-method observability coverage ────────────────────────────


@pytest.mark.parametrize(
    "method_name,args,default_return,mock_setup",
    [
        # Read methods that prefer Upstox
        ("ltp", ("RELIANCE",), None, "upstox"),
        ("quote", ("RELIANCE",), None, "upstox"),
        ("ltp_batch", (["RELIANCE", "TCS"],), {}, "upstox"),
        ("quote_batch", (["RELIANCE", "TCS"],), {}, "upstox"),
        # Read methods that prefer Dhan
        ("history", ("RELIANCE",), pd.DataFrame(), "dhan"),
        ("history_batch", (["RELIANCE", "TCS"],), pd.DataFrame(), "dhan"),
        ("depth", ("RELIANCE",), None, "dhan"),
        ("option_chain", ("NIFTY",), {}, "dhan"),
        ("future_chain", ("NIFTY",), None, "dhan"),
        ("stream", ("RELIANCE",), None, "dhan"),
        ("positions", (), [], "dhan"),
        ("holdings", (), [], "dhan"),
        ("funds", (), None, "dhan"),
        ("trades", (), [], "dhan"),
        ("search", ("RELIANCE",), [], "dhan"),
    ],
)
def test_each_method_emits_fallback_metric(
    method_name: str, args, default_return, mock_setup: str
) -> None:
    """Every routing method must have observability: when the preferred
    broker raises, log + metric must fire before falling through."""
    metrics = EventMetrics()
    dhan = MagicMock(name="dhan")
    upstox = MagicMock(name="upstox")
    gw = IntelligentGateway(dhan_gateway=dhan, upstox_gateway=upstox, metrics=metrics)

    preferred = upstox if mock_setup == "upstox" else dhan
    fallback = dhan if mock_setup == "upstox" else upstox

    # Preferred broker raises
    getattr(preferred, method_name).side_effect = RuntimeError(f"{mock_setup} down")
    if fallback is not None:
        getattr(fallback, method_name).return_value = default_return

    method = getattr(gw, method_name)
    try:
        method(*args)
    except RuntimeError as e:
        # Acceptable if both brokers failed and the method has no default
        if "No broker available" not in str(e):
            raise

    assert _fallback_count(metrics, method_name, mock_setup) >= 1, (
        f"Method {method_name} did not emit a fallback metric when {mock_setup} raised"
    )


# ── Backwards-compat: existing callers still work ──────────────────────


def test_describe_still_works_without_arguments() -> None:
    """The describe() method has no fallback try/except, but the
    contract is preserved (no broker = empty list)."""
    gw = IntelligentGateway()
    info = gw.describe()
    assert info["brokers"] == []
    assert "routing" in info


def test_funds_propagates_secondary_exception_when_both_brokers_fail() -> None:
    """Document the contract: when both brokers fail, the secondary
    broker's exception propagates. The caller is expected to handle
    it. This matches the previous implementation's behavior.
    """
    dhan = MagicMock(name="dhan")
    upstox = MagicMock(name="upstox")
    dhan.funds.side_effect = RuntimeError("dhan")
    upstox.funds.side_effect = ConnectionError("upstox")
    gw = IntelligentGateway(dhan_gateway=dhan, upstox_gateway=upstox)

    with pytest.raises(ConnectionError, match="upstox"):
        gw.funds()


# ── Default metrics injection ──────────────────────────────────────────


def test_default_metrics_is_eventmetrics_instance() -> None:
    """When no metrics is passed, the gateway creates an EventMetrics."""
    gw = IntelligentGateway()
    assert isinstance(gw.metrics, EventMetrics)
