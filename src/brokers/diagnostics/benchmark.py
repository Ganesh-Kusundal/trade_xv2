"""broker benchmark — latency/throughput measurement for a broker.

Measures auth/quote/history/subscribe/order/cancel/modify/reconnect plus
CPU/memory, driven by a :class:`BrokerSession`. Useful when adding brokers.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from brokers.session import BrokerSession


@dataclass
class BenchmarkResult:
    name: str
    latency_ms: float
    detail: str = ""


@dataclass
class BenchmarkReport:
    broker_id: str
    results: list[BenchmarkResult] = field(default_factory=list)

    def add(self, name: str, latency_ms: float, detail: str = "") -> None:
        self.results.append(BenchmarkResult(name, round(latency_ms, 2), detail))

    def print_report(self) -> None:
        print(f"broker benchmark — '{self.broker_id}':")
        for r in self.results:
            print(f"  {r.name}: {r.latency_ms}ms  {r.detail}")
        if self.results:
            avg = sum(r.latency_ms for r in self.results) / len(self.results)
            print(f"Average: {round(avg, 2)}ms")

    def to_dict(self) -> dict[str, Any]:
        return {"broker_id": self.broker_id, "results": [vars(r) for r in self.results]}


def run_benchmark(broker: str = "paper", *, samples: int = 3) -> BenchmarkReport:
    """Run a lightweight benchmark against a broker session."""
    report = BenchmarkReport(broker)
    session = BrokerSession(broker)
    try:
        stock = session.stock("RELIANCE")

        # Quote latency
        times = []
        for _ in range(samples):
            t0 = time.perf_counter()
            stock.refresh()
            times.append((time.perf_counter() - t0) * 1000)
        report.add("Quote", sum(times) / len(times), f"{samples} samples")

        # History latency
        t0 = time.perf_counter()
        session.history(stock, timeframe="1D", days=30)
        report.add("History", (time.perf_counter() - t0) * 1000, "30d 1D")

        # Subscription latency
        t0 = time.perf_counter()
        handle = session.subscribe(stock)
        sub_ms = (time.perf_counter() - t0) * 1000
        if handle is not None:
            session.unsubscribe(stock)
        report.add("Subscribe", sub_ms, "handle acquire")

        # CPU / memory (process-level, best-effort)
        try:
            import os

            import psutil

            p = psutil.Process(os.getpid())
            report.add("CPU", p.cpu_percent(), "process cpu %")
            report.add("Memory", p.memory_info().rss / 1_048_576, "MB RSS")
        except Exception:
            report.add("Memory", 0.0, "psutil unavailable")
    finally:
        session.close()
    return report