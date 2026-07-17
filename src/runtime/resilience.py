"""Resilience & Correctness subsystem configuration (ADR-012 appendix).

The Trading OS has a cross-cutting resilience layer that the original diagram
under-stated: idempotency, dead-letter queue, event-log persistence, and the
runtime parity gate. This dataclass makes that subsystem a *visible kernel
dependency* so composition roots wire it explicitly instead of scattering
env-var reads across modules.

It is a plain configuration object — it owns no behavior. The concrete
collaborators (``IdempotencyService``, ``DeadLetterQueue``, ``BufferedEventLog``,
``assert_runtime_parity_or_raise``) are constructed by the composition root from
these fields. Keeping it in ``runtime`` (not ``domain``) preserves the domain
layer's independence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.constants import SECONDS_PER_DAY


@dataclass(frozen=True)
class ResilienceConfig:
    """Tunables for the resilience & correctness subsystem.

    Attributes
    ----------
    idempotency_ttl_seconds:
        How long a command/order correlation id is remembered for de-dup.
    idempotency_backend:
        ``"memory"`` (default), ``"redis"``, or ``"file"`` — selects the
        ``IdempotencyService`` cache backend.
    dead_letter_enabled:
        Whether handler failures are captured in the DLQ instead of silently
        dropped.
    event_log_enabled:
        Whether domain events are persisted to the event log on publish
        (required for crash-recovery replay).
    event_log_sync_for_capital_events:
        Force fsync for capital events (TRADE_APPLIED/FILLED, ORDER_PLACED).
    parity_gate_enabled:
        Refuse live boot unless quant determinism checks pass. Disabled under
        ``SKIP_PARITY_GATE=1`` / pytest automatically by the gate itself.
    max_async_bus_queue:
        Bounded buffer size for the ``AsyncEventBus`` (backpressure).
    drop_non_critical_when_full:
        When the async bus is full, drop non-critical events rather than grow
        unbounded; critical events overflow up to 2x.
    extra:
        Escape hatch for broker/adapter-specific resilience knobs.
    """

    idempotency_ttl_seconds: int = SECONDS_PER_DAY
    idempotency_backend: str = "memory"
    dead_letter_enabled: bool = True
    event_log_enabled: bool = True
    event_log_sync_for_capital_events: bool = True
    parity_gate_enabled: bool = True
    max_async_bus_queue: int = 10_000
    drop_non_critical_when_full: bool = True
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(cls, **overrides: Any) -> "ResilienceConfig":
        """Build from environment with sane defaults (env wins over defaults)."""
        import os

        env = (os.getenv("TRADEX_ENV") or "development").strip().lower()
        is_live_env = env in ("production", "staging")
        # In live environments the parity gate is mandatory — SKIP_PARITY_GATE
        # must not be able to disable it via this config path either.
        skip_parity = (os.getenv("SKIP_PARITY_GATE", "0") == "1") and not is_live_env

        defaults = dict(
            idempotency_ttl_seconds=int(os.getenv("TRADEX_IDEMPOTENCY_TTL", "86400")),
            idempotency_backend=os.getenv("TRADEX_IDEMPOTENCY_BACKEND", "memory"),
            dead_letter_enabled=os.getenv("TRADEX_DLQ_ENABLED", "1") != "0",
            event_log_enabled=os.getenv("TRADEX_EVENT_LOG_ENABLED", "1") != "0",
            parity_gate_enabled=not skip_parity,
            max_async_bus_queue=int(os.getenv("TRADEX_ASYNC_BUS_QUEUE", "10000")),
        )
        defaults.update(overrides)
        return cls(**defaults)
