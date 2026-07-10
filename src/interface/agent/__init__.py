"""AI Agent tool surface — thin wrappers over the real SDK, plus
guardrails specific to an untrusted-caller client.

See docs/architecture/trading-os/TRADING_OS_BLUEPRINT_V2_PART5.md §7.
"""

from interface.agent.guardrails import (
    AgentGuardrailConfig,
    AgentGuardrails,
    AgentRateLimitExceeded,
    AgentSymbolNotAllowed,
)
from interface.agent.tools import AgentTools, DryRunResult

__all__ = [
    "AgentGuardrailConfig",
    "AgentGuardrails",
    "AgentRateLimitExceeded",
    "AgentSymbolNotAllowed",
    "AgentTools",
    "DryRunResult",
]
