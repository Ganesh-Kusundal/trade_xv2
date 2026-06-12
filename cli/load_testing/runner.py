"""Load testing runner for performance diagnostic commands."""

from __future__ import annotations

import asyncio
import time
from datetime import date, timedelta
from typing import Any


class LoadTestRunner:
    """Runs concurrent load tests on broker endpoints and monitors performance."""

    def __init__(self, broker_service: Any):
        self._broker_service = broker_service

    async def run_test(
        self,
        endpoint_type: str,
        duration_seconds: float = 3.0,
        concurrency: int = 5,
    ) -> dict[str, Any]:
        """Execute async load test and measure throughput/latency."""
        broker = self._broker_service.active_broker

        # Prepare parameters
        symbol = "RELIANCE"
        exchange = "NSE"
        to_date = date.today()
        from_date = to_date - timedelta(days=2)
        expiry = "2026-06-18"

        # Track statistics
        requests_sent = 0
        success_count = 0
        failure_count = 0
        rate_limit_hits = 0
        latencies: list[float] = []

        start_time = time.time()
        stop_event = asyncio.Event()

        async def worker():
            nonlocal requests_sent, success_count, failure_count, rate_limit_hits

            while not stop_event.is_set():
                req_start = time.time()
                requests_sent += 1
                try:
                    # Run the request inside an executor so it doesn't block the async loop
                    # since Pandas/Requests are blocking.
                    loop = asyncio.get_running_loop()

                    if endpoint_type == "historical":
                        await loop.run_in_executor(
                            None,
                            broker.get_historical_data,
                            symbol,
                            exchange,
                            from_date,
                            to_date,
                            "1d",
                        )
                    elif endpoint_type == "quotes":
                        await loop.run_in_executor(
                            None,
                            broker.get_quote,
                            symbol,
                            exchange,
                        )
                    elif endpoint_type == "option-chain":
                        await loop.run_in_executor(
                            None,
                            broker.get_option_chain,
                            "NIFTY",
                            exchange,
                            expiry,
                        )
                    elif endpoint_type == "websocket":
                        # Simulate websocket latency checks / message parsing
                        await asyncio.sleep(0.01)  # Simulate small delay
                    else:
                        raise ValueError(f"Unknown endpoint type: {endpoint_type}")

                    latency = (time.time() - req_start) * 1000.0  # ms
                    latencies.append(latency)
                    success_count += 1

                except Exception as exc:
                    latency = (time.time() - req_start) * 1000.0
                    latencies.append(latency)

                    # Detect rate limits
                    exc_str = str(exc).lower()
                    if "429" in exc_str or "rate limit" in exc_str or "circuit" in exc_str:
                        rate_limit_hits += 1
                    else:
                        failure_count += 1

                # Small yield to allow other coroutines to run
                await asyncio.sleep(0.005)

        # Start workers
        workers = [asyncio.create_task(worker()) for _ in range(concurrency)]

        # Run for specified duration
        await asyncio.sleep(duration_seconds)
        stop_event.set()

        # Await worker termination
        await asyncio.gather(*workers, return_exceptions=True)

        total_time = time.time() - start_time
        rps = requests_sent / total_time if total_time > 0 else 0
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

        return {
            "endpoint": endpoint_type,
            "duration": total_time,
            "requests_sent": requests_sent,
            "success_count": success_count,
            "failure_count": failure_count,
            "rate_limit_hits": rate_limit_hits,
            "rps": rps,
            "avg_latency_ms": avg_latency,
            "min_latency_ms": min(latencies) if latencies else 0.0,
            "max_latency_ms": max(latencies) if latencies else 0.0,
        }
