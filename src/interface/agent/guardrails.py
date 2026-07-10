"""Guardrails specific to an untrusted-caller client (an AI agent).

Human CLI/API callers are implicitly trusted — a person is at the keyboard,
choosing to run a command. An agent executing autonomously is not the same
trust level, and the mandate is explicit: "agents are untrusted clients of
the OS." Nothing else in this codebase needs these three controls, each
justified by a concrete failure mode the existing per-order RiskManager
does not catch:

1. Per-agent-session rate limiting, independent of the broker's own rate
   limits — a runaway agent loop calling place_order in a tight loop would
   pass every individual per-order risk check (each order might be small
   and compliant) while still being a real operational hazard the
   per-order risk engine was never designed to catch.
2. An opt-in symbol/action allowlist — defense in depth: even if every
   other control fails, an agent scoped to a specific symbol set cannot
   touch anything outside it, checkable without touching RiskManager's
   logic at all.
3. Dry-run mode, implemented in tools.py using these guardrails' output.

See docs/architecture/trading-os/TRADING_OS_BLUEPRINT_V2_PART5.md §7.2.
"""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.resilience.rate_limiter import MultiBucketRateLimiter, RateLimitConfig


class AgentRateLimitExceeded(Exception):
    """Raised when an agent session exceeds its own call-rate budget —
    independent of, and in addition to, the broker's own rate limits."""


class AgentSymbolNotAllowed(Exception):
    """Raised when an agent attempts to act on a symbol outside its
    configured allowlist."""


@dataclass(frozen=True)
class AgentGuardrailConfig:
    """Per-agent-session limits. Defaults are deliberately conservative —
    an agent is untrusted until proven otherwise, not the reverse."""

    #: Max tool calls per second, per category ("read" vs "order").
    read_rate_per_second: float = 5.0
    read_burst_capacity: int = 10
    order_rate_per_second: float = 0.5
    order_burst_capacity: int = 3
    #: None means "no allowlist configured" — all symbols permitted. This
    #: is opt-in exactly because it must be a deliberate choice, not a
    #: silent default that gives a false sense of safety.
    symbol_allowlist: frozenset[str] | None = None


class AgentGuardrails:
    """Owns the rate limiter and symbol allowlist for one agent session.

    One instance per agent session — do not share across agents, since
    the whole point is per-session budget isolation.
    """

    def __init__(self, config: AgentGuardrailConfig | None = None) -> None:
        self._config = config or AgentGuardrailConfig()
        self._rate_limiter = MultiBucketRateLimiter(
            {
                "read": RateLimitConfig(
                    rate_per_second=self._config.read_rate_per_second,
                    capacity=self._config.read_burst_capacity,
                ),
                "order": RateLimitConfig(
                    rate_per_second=self._config.order_rate_per_second,
                    capacity=self._config.order_burst_capacity,
                ),
            }
        )

    def check_rate_limit(self, category: str) -> None:
        """Raise AgentRateLimitExceeded if this session's budget for
        *category* ("read" or "order") is exhausted. Non-blocking —
        an agent that's over budget is rejected immediately, not queued."""
        if not self._rate_limiter.acquire(category, tokens=1, timeout=0):
            raise AgentRateLimitExceeded(
                f"Agent session exceeded its own {category} rate limit — "
                "independent of the broker's rate limits"
            )

    def check_symbol_allowed(self, symbol: str) -> None:
        """Raise AgentSymbolNotAllowed if an allowlist is configured and
        *symbol* is not in it. No-op if no allowlist was configured."""
        allowlist = self._config.symbol_allowlist
        if allowlist is not None and symbol.upper() not in allowlist:
            raise AgentSymbolNotAllowed(
                f"Symbol {symbol!r} is not in this agent session's allowlist"
            )


__all__ = [
    "AgentGuardrailConfig",
    "AgentGuardrails",
    "AgentRateLimitExceeded",
    "AgentSymbolNotAllowed",
]
