"""AgentLoop — the LLM-driven tool-calling loop.

Orchestration only. It does not know about brokers, sessions, or risk
internals: it calls the LLM, and whenever the LLM requests a tool it asks
``AgentTools`` to perform it (which is where ``AgentGuardrails`` are
enforced). Guardrail rejections are caught, recorded, and fed back to the
LLM as error tool-results rather than crashing the run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from interface.agent.guardrails import (
    AgentGuardrails,
    AgentRateLimitExceeded,
    AgentSymbolNotAllowed,
)
from interface.agent.llm_client import LLMClient
from interface.agent.tools import AgentTools
from interface.agent.tools_schema import build_tool_schemas, dispatch_tool

DEFAULT_SYSTEM_PROMPT = (
    "You are a trading assistant operating inside a strict agent sandbox. "
    "You have read-only market tools and order tools. Every order path is "
    "guarded: you may be rate-limited, symbol-restricted, or in dry-run mode. "
    "Prefer checking get_risk_status before placing orders. When you have "
    "fully answered, respond with a plain text final answer (no tool call)."
)


@dataclass(frozen=True)
class ToolCallRecord:
    """One tool invocation within a run."""

    iteration: int
    tool_use_id: str
    name: str
    args: dict[str, Any]
    result: Any = None
    is_error: bool = False
    blocked_by_guardrail: bool = False
    error_type: str | None = None


@dataclass(frozen=True)
class GuardrailBlock:
    """A tool call rejected by AgentGuardrails."""

    iteration: int
    tool_use_id: str
    name: str
    error_type: str
    message: str


@dataclass(frozen=True)
class AgentStep:
    """One LLM turn: what the model emitted and what came back."""

    iteration: int
    assistant_content: list[dict[str, Any]]
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    text: str | None = None


@dataclass(frozen=True)
class AgentRunResult:
    """Structured outcome of a full agent run."""

    steps: list[AgentStep]
    tool_calls: list[ToolCallRecord]
    guardrail_blocks: list[GuardrailBlock]
    final_message: str | None
    iterations: int
    stopped_reason: str  # "final_answer" | "max_iterations"


def _serialize_result(value: Any) -> str:
    """Render a tool result as a string for an Anthropic tool_result block.

    Decimals and other non-JSON types degrade to ``str`` rather than raising,
    so an arbitrary tool return value can always be fed back to the model.
    """

    def _default(obj: Any) -> str:
        return str(obj)

    try:
        return json.dumps(value, default=_default)
    except (TypeError, ValueError):
        return str(value)


class AgentLoop:
    """Run the tool-calling loop for one agent session."""

    def __init__(
        self,
        tools: AgentTools,
        llm: LLMClient,
        *,
        max_iterations: int = 10,
        system_prompt: str | None = None,
        guardrails: AgentGuardrails | None = None,
    ) -> None:
        self._tools = tools
        self._llm = llm
        self._max_iterations = max_iterations
        self._system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        # Guardrails also live inside AgentTools; we keep a reference only so
        # callers can introspect the session budget if they want.
        self._guardrails = guardrails or tools._guardrails

    def run(self, user_message: str) -> AgentRunResult:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_message}
        ]
        tool_schemas = build_tool_schemas()

        steps: list[AgentStep] = []
        tool_calls: list[ToolCallRecord] = []
        guardrail_blocks: list[GuardrailBlock] = []
        final_message: str | None = None

        for iteration in range(self._max_iterations):
            response = self._llm.send(self._system_prompt, messages, tool_schemas)
            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            tool_uses = response.tool_use_blocks()
            if not tool_uses:
                final_message = "\n".join(response.text_blocks()).strip() or None
                steps.append(
                    AgentStep(
                        iteration=iteration,
                        assistant_content=assistant_content,
                        text=final_message,
                    )
                )
                return AgentRunResult(
                    steps=steps,
                    tool_calls=tool_calls,
                    guardrail_blocks=guardrail_blocks,
                    final_message=final_message,
                    iterations=iteration + 1,
                    stopped_reason="final_answer",
                )

            tool_results: list[dict[str, Any]] = []
            step_text = "\n".join(response.text_blocks()).strip() or None

            for tu in tool_uses:
                name = tu.get("name", "")
                args = tu.get("input", {}) or {}
                tool_use_id = tu.get("id", "")
                record = ToolCallRecord(
                    iteration=iteration,
                    tool_use_id=tool_use_id,
                    name=name,
                    args=args,
                )
                try:
                    result = dispatch_tool(self._tools, name, args)
                    record = record.__class__(
                        iteration=iteration,
                        tool_use_id=tool_use_id,
                        name=name,
                        args=args,
                        result=result,
                        is_error=False,
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": _serialize_result(result),
                        }
                    )
                except (AgentRateLimitExceeded, AgentSymbolNotAllowed) as exc:
                    record = record.__class__(
                        iteration=iteration,
                        tool_use_id=tool_use_id,
                        name=name,
                        args=args,
                        is_error=True,
                        blocked_by_guardrail=True,
                        error_type=type(exc).__name__,
                    )
                    guardrail_blocks.append(
                        GuardrailBlock(
                            iteration=iteration,
                            tool_use_id=tool_use_id,
                            name=name,
                            error_type=type(exc).__name__,
                            message=str(exc),
                        )
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": str(exc),
                            "is_error": True,
                        }
                    )
                except Exception as exc:
                    record = record.__class__(
                        iteration=iteration,
                        tool_use_id=tool_use_id,
                        name=name,
                        args=args,
                        is_error=True,
                        error_type=type(exc).__name__,
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": f"tool error: {exc}",
                            "is_error": True,
                        }
                    )
                tool_calls.append(record)

            messages.append({"role": "user", "content": tool_results})
            steps.append(
                AgentStep(
                    iteration=iteration,
                    assistant_content=assistant_content,
                    tool_results=tool_results,
                    text=step_text,
                )
            )

        # Exhausted the iteration budget without a final answer.
        return AgentRunResult(
            steps=steps,
            tool_calls=tool_calls,
            guardrail_blocks=guardrail_blocks,
            final_message=final_message,
            iterations=self._max_iterations,
            stopped_reason="max_iterations",
        )


__all__ = [
    "AgentLoop",
    "AgentRunResult",
    "AgentStep",
    "GuardrailBlock",
    "ToolCallRecord",
]
