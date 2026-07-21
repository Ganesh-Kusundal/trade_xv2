"""DhanHttpClientConfig — configuration for DhanHttpClient constructor.

Groups the 15 constructor parameters into a structured dataclass,
reducing cognitive load and making the configuration surface explicit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import requests

    from brokers.providers.dhan.config import DhanResilienceConfig
    from infrastructure.resilience.circuit_breaker import CircuitBreaker
    from infrastructure.resilience.rate_limiter import MultiBucketRateLimiter


@dataclass
class DhanHttpClientConfig:
    """Configuration for :class:`DhanHttpClient`.

    Reduces the 15-parameter constructor to a single config object.
    Most fields have sensible defaults; callers only override what they need.
    """

    # ── Identity ──
    client_id: str = ""
    access_token: str = ""
    base_url: str = "https://api.dhan.co"
    timeout: float = 15.0

    # ── Token refresh ──
    token_refresh_fn: object = None  # Callable[[], str] | None

    # ── Retry ──
    enable_retry: bool = True

    # ── Circuit breakers ──
    # Single fallback CB used when category-specific CB is not provided.
    circuit_breaker: CircuitBreaker | None = None
    # Category-specific CBs (read/write/admin). Falls back to circuit_breaker.
    read_circuit_breaker: CircuitBreaker | None = None
    write_circuit_breaker: CircuitBreaker | None = None
    admin_circuit_breaker: CircuitBreaker | None = None

    # ── Session ──
    session: requests.Session | None = None

    # ── Resilience ──
    rate_limiter: MultiBucketRateLimiter | None = None
    circuit_breakers: dict[str, CircuitBreaker] = field(default_factory=dict)

    # ── Config ──
    config: DhanResilienceConfig | None = None
