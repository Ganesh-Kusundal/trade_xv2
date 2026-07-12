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
from interface.agent.llm_client import AnthropicLLMClient, LLMClient, LLMResponse
from interface.agent.loop import (
    AgentLoop,
    AgentRunResult,
    AgentStep,
    GuardrailBlock,
    ToolCallRecord,
)
from interface.agent.tools import AgentTools, DryRunResult
from interface.agent.tools_schema import (
    AGENT_TOOL_SPECS,
    build_tool_schemas,
    dispatch_tool,
)

__all__ = [
    "AGENT_TOOL_SPECS",
    "AgentGuardrailConfig",
    "AgentGuardrails",
    "AgentLoop",
    "AgentRateLimitExceeded",
    "AgentRunResult",
    "AgentStep",
    "AgentSymbolNotAllowed",
    "AgentTools",
    "AnthropicLLMClient",
    "DryRunResult",
    "GuardrailBlock",
    "LLMClient",
    "LLMResponse",
    "ToolCallRecord",
    "build_tool_schemas",
    "dispatch_tool",
]
