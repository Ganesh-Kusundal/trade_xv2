# 09 — Observability

## 1. Overview

TradeXV2 implements a three-pillar observability model:

| Pillar | Tool | Purpose |
|---|---|---|
| **Logs** | structlog → JSON | Structured, queryable event records |
| **Metrics** | Prometheus format | Time-series counters, gauges, histograms |
| **Traces** | OpenTelemetry | Distributed request tracing via correlation IDs |

## 2. Structured Logging

### 2.1 Configuration

```python
# shared/logging/config.py

from __future__ import annotations

import logging
import sys

import structlog


def setup_logging(level: str = "INFO", json_output: bool = True) -> None:
    """Configure structured logging for the entire application."""

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_output:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout, formatter=formatter)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
```

### 2.2 Log Context

```python
# shared/logging/context.py

from __future__ import annotations

import structlog
from uuid import UUID


def bind_context(
    correlation_id: UUID | None = None,
    strategy_id: str | None = None,
    broker_id: str | None = None,
    symbol: str | None = None,
) -> None:
    """Bind context variables to all subsequent log entries."""
    if correlation_id:
        structlog.contextvars.bind_contextvars(correlation_id=str(correlation_id))
    if strategy_id:
        structlog.contextvars.bind_contextvars(strategy_id=strategy_id)
    if broker_id:
        structlog.contextvars.bind_contextvars(broker_id=broker_id)
    if symbol:
        structlog.contextvars.bind_contextvars(symbol=symbol)


def unbind_context(*keys: str) -> None:
    """Remove context variables."""
    structlog.contextvars.unbind_contextvars(*keys)
```

### 2.3 Usage Pattern

```python
# Every component uses structured logging:

import structlog
logger = structlog.get_logger(__name__)

# With context
logger.info(
    "order_placed",
    order_id=str(order.order_id),
    symbol=order.symbol,
    side=order.side.value,
    quantity=str(order.quantity.value),
)

# Output (JSON):
# {"event": "order_placed", "order_id": "abc-123", "symbol": "RELIANCE",
#  "side": "BUY", "quantity": "10", "level": "info",
#  "timestamp": "2024-01-15T10:30:00Z", "logger": "application.execution.engine"}
```

## 3. Metrics

### 3.1 Metrics Registry

```python
# shared/metrics/registry.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable
import time


@dataclass
class Counter:
    name: str
    description: str
    value: int = 0
    labels: dict[str, str] = field(default_factory=dict)

    def inc(self, amount: int = 1) -> None:
        self.value += amount

    def to_prometheus(self) -> str:
        label_str = ",".join(f'{k}="{v}"' for k, v in self.labels.items())
        if label_str:
            return f'{self.name}{{{label_str}}} {self.value}'
        return f'{self.name} {self.value}'


@dataclass
class Gauge:
    name: str
    description: str
    value: float = 0.0
    labels: dict[str, str] = field(default_factory=dict)

    def set(self, value: float) -> None:
        self.value = value

    def inc(self, amount: float = 1.0) -> None:
        self.value += amount

    def dec(self, amount: float = 1.0) -> None:
        self.value -= amount

    def to_prometheus(self) -> str:
        label_str = ",".join(f'{k}="{v}"' for k, v in self.labels.items())
        if label_str:
            return f'{self.name}{{{label_str}}} {self.value}'
        return f'{self.name} {self.value}'


@dataclass
class Histogram:
    name: str
    description: str
    buckets: list[float]
    observations: list[float] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)

    def observe(self, value: float) -> None:
        self.observations.append(value)

    @property
    def count(self) -> int:
        return len(self.observations)

    @property
    def sum(self) -> float:
        return sum(self.observations)

    def to_prometheus(self) -> str:
        lines = []
        label_str = ",".join(f'{k}="{v}"' for k, v in self.labels.items())
        prefix = f'{self.name}{{{label_str}}}' if label_str else self.name

        for bucket in self.buckets:
            count = sum(1 for o in self.observations if o <= bucket)
            lines.append(f'{prefix}_bucket{{le="{bucket}"}} {count}')
        lines.append(f'{prefix}_count {self.count}')
        lines.append(f'{prefix}_sum {self.sum}')
        return "\n".join(lines)


class MetricsRegistry:
    """Global metrics registry."""

    _instance: MetricsRegistry | None = None

    def __init__(self) -> None:
        self._counters: dict[str, Counter] = {}
        self._gauges: dict[str, Gauge] = {}
        self._histograms: dict[str, Histogram] = {}

    @classmethod
    def get(cls) -> MetricsRegistry:
        if cls._instance is None:
            cls._instance = MetricsRegistry()
        return cls._instance

    def counter(self, name: str, description: str = "", **labels) -> Counter:
        key = f"{name}:{sorted(labels.items())}"
        if key not in self._counters:
            self._counters[key] = Counter(name, description, labels=labels)
        return self._counters[key]

    def gauge(self, name: str, description: str = "", **labels) -> Gauge:
        key = f"{name}:{sorted(labels.items())}"
        if key not in self._gauges:
            self._gauges[key] = Gauge(name, description, labels=labels)
        return self._gauges[key]

    def histogram(self, name: str, description: str = "", buckets=None, **labels) -> Histogram:
        key = f"{name}:{sorted(labels.items())}"
        if key not in self._histograms:
            self._histograms[key] = Histogram(
                name, description,
                buckets=buckets or [0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
                labels=labels,
            )
        return self._histograms[key]

    def to_prometheus(self) -> str:
        lines = []
        for c in self._counters.values():
            lines.append(f"# HELP {c.name} {c.description}")
            lines.append(f"# TYPE {c.name} counter")
            lines.append(c.to_prometheus())
        for g in self._gauges.values():
            lines.append(f"# HELP {g.name} {g.description}")
            lines.append(f"# TYPE {g.name} gauge")
            lines.append(g.to_prometheus())
        for h in self._histograms.values():
            lines.append(f"# HELP {h.name} {h.description}")
            lines.append(f"# TYPE {h.name} histogram")
            lines.append(h.to_prometheus())
        return "\n".join(lines)
```

### 3.2 Key Metrics

| Metric | Type | Labels | Description |
|---|---|---|---|
| `tradex_orders_total` | Counter | `side`, `status` | Total orders placed |
| `tradex_fills_total` | Counter | `symbol`, `side` | Total fills received |
| `tradex_order_latency_seconds` | Histogram | `broker` | Order placement latency |
| `tradex_position_quantity` | Gauge | `symbol`, `exchange` | Current position quantity |
| `tradex_daily_pnl` | Gauge | `strategy` | Daily P&L |
| `tradex_messages_published` | Counter | `event_type` | MessageBus publishes |
| `tradex_messages_delivered` | Counter | `event_type` | MessageBus deliveries |
| `tradex_messages_failed` | Counter | `event_type` | MessageBus failures |
| `tradex_broker_connected` | Gauge | `broker` | Broker connection status |
| `tradex_tick_count` | Counter | `symbol`, `exchange` | Ticks received |
| `tradex_risk_checks_total` | Counter | `rule`, `result` | Risk check outcomes |

### 3.3 Metrics Endpoint

```python
# interface/api/metrics.py

from fastapi import APIRouter, Response
from shared.metrics.registry import MetricsRegistry

router = APIRouter()

@router.get("/metrics")
def prometheus_metrics():
    """Prometheus-compatible metrics endpoint."""
    registry = MetricsRegistry.get()
    return Response(
        content=registry.to_prometheus(),
        media_type="text/plain",
    )
```

## 4. Distributed Tracing

### 4.1 Correlation ID Flow

Every request gets a `correlation_id` that flows through all components:

```
CLI/API → PlaceOrderCommand(correlation_id=uuid)
    → ExecutionEngine → OrderPlaced(correlation_id=same)
        → OrderManager → OrderAccepted(correlation_id=same)
            → PositionManager → PositionChanged(correlation_id=same)
```

### 4.2 Trace Context

```python
# shared/tracing/context.py

from __future__ import annotations

import threading
from uuid import UUID, uuid4


class TraceContext:
    """Thread-local trace context for distributed tracing."""

    _local = threading.local()

    @classmethod
    def start_span(cls, name: str, parent_id: UUID | None = None) -> Span:
        span = Span(
            trace_id=getattr(cls._local, "trace_id", uuid4()),
            span_id=uuid4(),
            parent_id=parent_id,
            name=name,
        )
        cls._local.current_span = span
        cls._local.trace_id = span.trace_id
        return span

    @classmethod
    def end_span(cls) -> None:
        span = getattr(cls._local, "current_span", None)
        if span:
            span.end()

    @classmethod
    def get_correlation_id(cls) -> UUID | None:
        return getattr(cls._local, "trace_id", None)


class Span:
    def __init__(self, trace_id: UUID, span_id: UUID, parent_id: UUID | None, name: str):
        self.trace_id = trace_id
        self.span_id = span_id
        self.parent_id = parent_id
        self.name = name
        self.start_time = time.time()
        self.end_time: float | None = None
        self.attributes: dict = {}

    def set_attribute(self, key: str, value: str) -> None:
        self.attributes[key] = value

    def end(self) -> None:
        self.end_time = time.time()
        # Export to trace backend
```

## 5. Health Checks

```python
# shared/health/checks.py

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheck:
    name: str
    status: HealthStatus
    detail: str = ""
    latency_ms: float = 0.0


@dataclass
class HealthReport:
    status: HealthStatus
    checks: list[HealthCheck]
    timestamp: str

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "checks": [
                {"name": c.name, "status": c.status.value, "detail": c.detail}
                for c in self.checks
            ],
            "timestamp": self.timestamp,
        }


class HealthChecker:
    """Runs registered health checks and aggregates results."""

    def __init__(self) -> None:
        self._checks: list[Callable] = []

    def register(self, check_fn: Callable) -> None:
        self._checks.append(check_fn)

    def run_all(self) -> HealthReport:
        results = []
        overall = HealthStatus.HEALTHY

        for check_fn in self._checks:
            try:
                result = check_fn()
                results.append(result)
                if result.status == HealthStatus.UNHEALTHY:
                    overall = HealthStatus.UNHEALTHY
                elif result.status == HealthStatus.DEGRADED and overall != HealthStatus.UNHEALTHY:
                    overall = HealthStatus.DEGRADED
            except Exception as exc:
                results.append(HealthCheck(
                    name=check_fn.__name__,
                    status=HealthStatus.UNHEALTHY,
                    detail=str(exc),
                ))
                overall = HealthStatus.UNHEALTHY

        return HealthReport(
            status=overall,
            checks=results,
            timestamp=datetime.utcnow().isoformat(),
        )


# Built-in health checks

def check_broker_connection(broker_id: str, gateway) -> HealthCheck:
    """Check if broker is connected."""
    if gateway.is_connected:
        return HealthCheck(name=f"broker:{broker_id}", status=HealthStatus.HEALTHY)
    return HealthCheck(
        name=f"broker:{broker_id}",
        status=HealthStatus.UNHEALTHY,
        detail="Not connected",
    )


def check_datalake(catalog) -> HealthCheck:
    """Check if DataLake is accessible."""
    try:
        catalog.query("SELECT 1")
        return HealthCheck(name="datalake", status=HealthStatus.HEALTHY)
    except Exception as exc:
        return HealthCheck(name="datalake", status=HealthStatus.UNHEALTHY, detail=str(exc))


def check_message_bus(bus) -> HealthCheck:
    """Check MessageBus health."""
    metrics = bus.metrics
    if metrics.messages_failed > 100:
        return HealthCheck(
            name="message_bus",
            status=HealthStatus.DEGRADED,
            detail=f"{metrics.messages_failed} failed messages",
        )
    return HealthCheck(name="message_bus", status=HealthStatus.HEALTHY)
```

## 6. Dashboard

```python
# interface/api/dashboard.py

from fastapi import APIRouter
from shared.health.checks import HealthChecker
from shared.metrics.registry import MetricsRegistry
from application.risk.risk_metrics import RiskMetrics

router = APIRouter()

@router.get("/health")
def health():
    checker = HealthChecker()
    # Register checks...
    return checker.run_all().to_dict()

@router.get("/status")
def status():
    """Comprehensive status endpoint."""
    return {
        "health": health(),
        "risk": get_risk_metrics(),
        "positions": get_positions(),
        "orders_today": get_orders_today(),
    }
```

## 7. Comparison with Current State

| Aspect | Current | Target |
|---|---|---|
| Logging | `print` + `logging` | structlog with JSON output |
| Metrics | None | Prometheus-compatible metrics |
| Tracing | None | Correlation ID flow |
| Health checks | None | Pluggable health check system |
| Dashboard | None | FastAPI `/health` + `/status` endpoints |
| Alerting | None | Kill switch events → alerting |
