"""Tests for the AI agent loop (Tier 3-J).

No network, no real ``anthropic`` install: a scripted ``FakeLLM`` drives the
loop and a ``MagicMock`` session stands in for the broker. Guardrails are the
real ``AgentGuardrails`` — exercised directly (not mocked).
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from interface.agent.guardrails import (
    AgentGuardrailConfig,
    AgentGuardrails,
)
from interface.agent.llm_client import LLMClient, LLMResponse
from interface.agent.loop import AgentLoop
from interface.agent.tools import AgentTools, DryRunResult

# ── Helpers ────────────────────────────────────────────────────────────────


def _fake_session() -> MagicMock:
    session = MagicMock()
    inst = MagicMock()
    inst.ltp = Decimal("2500")
    inst.bid = Decimal("2499")
    inst.ask = Decimal("2501")
    inst.volume = 1000
    session.universe.equity.return_value = inst
    session.account.refresh.return_value.positions = []
    session.account.risk_profile = None
    return session


def _text_block(text: str) -> dict:
    return {"type": "text", "text": text}


def _tool_use(name: str, args: dict, tool_id: str = "call_1") -> dict:
    return {"type": "tool_use", "id": tool_id, "name": name, "input": args}


def _resp(blocks: list[dict], stop_reason: str = "tool_use") -> LLMResponse:
    return LLMResponse(content=blocks, stop_reason=stop_reason)


class FakeLLM(LLMClient):
    """Returns scripted responses in order; records every send() call."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self._queue = list(responses)
        self.sends: list[dict] = []

    def send(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        self.sends.append({"system": system, "messages": messages, "tools": tools})
        return self._queue.pop(0)

    def tool_schema_passed(self) -> list[dict]:
        # The schema handed to the very first send().
        return self.sends[0]["tools"]


# ── Loop drives the correct tool and terminates ─────────────────────────────


def test_loop_invokes_correct_tool_then_returns_final_answer():
    session = _fake_session()
    tools = AgentTools(session)
    llm = FakeLLM(
        [
            _resp([_tool_use("get_quote", {"symbol": "RELIANCE"})]),
            _resp([_text_block("RELIANCE last traded at 2500.")], stop_reason="end_turn"),
        ]
    )

    result = AgentLoop(tools, llm).run("What is RELIANCE trading at?")

    # The tool method was actually invoked on the real surface.
    session.universe.equity.assert_called_once_with("RELIANCE", "NSE")
    assert result.stopped_reason == "final_answer"
    assert result.final_message == "RELIANCE last traded at 2500."
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "get_quote"
    assert result.tool_calls[0].args == {"symbol": "RELIANCE"}
    assert not result.guardrail_blocks


def test_tool_results_flow_back_into_subsequent_llm_turn():
    session = _fake_session()
    tools = AgentTools(session)
    llm = FakeLLM(
        [
            _resp([_tool_use("get_quote", {"symbol": "RELIANCE"})]),
            _resp([_text_block("done")], stop_reason="end_turn"),
        ]
    )
    AgentLoop(tools, llm).run("quote?")

    # Second turn's user message carries the tool_result from the first.
    second_turn = llm.sends[1]
    user_msgs = [m for m in second_turn["messages"] if m["role"] == "user"]
    last_user = user_msgs[-1]["content"]
    assert isinstance(last_user, list)
    assert last_user[0]["type"] == "tool_result"
    assert "2500" in last_user[0]["content"]


def test_loop_respects_max_iterations():
    session = _fake_session()
    tools = AgentTools(session)
    # Never returns a final answer -> exhaust the budget.
    llm = FakeLLM(
        [
            _resp([_tool_use("get_quote", {"symbol": "RELIANCE"}, tool_id="c1")]),
            _resp([_tool_use("get_quote", {"symbol": "RELIANCE"}, tool_id="c2")]),
            _resp([_tool_use("get_quote", {"symbol": "RELIANCE"}, tool_id="c3")]),
        ]
    )
    result = AgentLoop(tools, llm, max_iterations=3).run("loop")

    assert result.stopped_reason == "max_iterations"
    assert result.iterations == 3
    assert len(result.tool_calls) == 3


# ── Guardrails are enforced through the tool path ───────────────────────────


def test_guardrail_blocks_disallowed_symbol():
    session = _fake_session()
    guardrails = AgentGuardrails(
        AgentGuardrailConfig(symbol_allowlist=frozenset({"RELIANCE"}))
    )
    tools = AgentTools(session, guardrails=guardrails)
    llm = FakeLLM(
        [
            _resp(
                [_tool_use("place_order", {
                    "symbol": "INFY", "exchange": "NSE", "side": "BUY", "quantity": 1,
                })]
            ),
            _resp([_text_block("aborted")], stop_reason="end_turn"),
        ]
    )

    result = AgentLoop(tools, llm).run("buy INFY")

    assert len(result.guardrail_blocks) == 1
    block = result.guardrail_blocks[0]
    assert block.name == "place_order"
    assert block.error_type == "AgentSymbolNotAllowed"
    assert result.tool_calls[0].blocked_by_guardrail is True
    # The order never reached the broker path.
    session.universe.equity.return_value.buy.assert_not_called()
    session.universe.equity.return_value.sell.assert_not_called()


def test_guardrail_blocks_when_rate_limit_exceeded():
    session = _fake_session()
    # capacity 1, zero refill -> the 2nd order call is rejected.
    guardrails = AgentGuardrails(
        AgentGuardrailConfig(order_burst_capacity=1, order_rate_per_second=0.01)
    )
    tools = AgentTools(session, guardrails=guardrails)
    llm = FakeLLM(
        [
            _resp(
                [_tool_use("place_order", {
                    "symbol": "RELIANCE", "exchange": "NSE", "side": "BUY", "quantity": 1,
                }, tool_id="c1")]
            ),
            _resp(
                [_tool_use("place_order", {
                    "symbol": "RELIANCE", "exchange": "NSE", "side": "BUY", "quantity": 1,
                }, tool_id="c2")]
            ),
            _resp([_text_block("done")], stop_reason="end_turn"),
        ]
    )

    result = AgentLoop(tools, llm).run("buy twice")

    assert len(result.guardrail_blocks) == 1
    assert result.guardrail_blocks[0].error_type == "AgentRateLimitExceeded"
    # Exactly one order was actually placed.
    assert session.universe.equity.return_value.buy.call_count == 1


def test_dry_run_prevents_real_order():
    session = _fake_session()
    tools = AgentTools(session)
    llm = FakeLLM(
        [
            _resp(
                [_tool_use("place_order", {
                    "symbol": "RELIANCE", "exchange": "NSE", "side": "BUY",
                    "quantity": 5, "dry_run": True,
                })]
            ),
            _resp([_text_block("previewed")], stop_reason="end_turn"),
        ]
    )

    result = AgentLoop(tools, llm).run("preview a buy")

    call = result.tool_calls[0]
    assert isinstance(call.result, DryRunResult)
    assert call.result.symbol == "RELIANCE"
    assert call.result.quantity == 5
    # No real order hit the broker.
    session.universe.equity.return_value.buy.assert_not_called()
    session.universe.equity.return_value.sell.assert_not_called()


def test_tool_schema_is_passed_to_llm():
    session = _fake_session()
    tools = AgentTools(session)
    llm = FakeLLM(
        [_resp([_text_block("hi")], stop_reason="end_turn")]
    )
    AgentLoop(tools, llm).run("hello")

    names = {t["name"] for t in llm.tool_schema_passed()}
    assert {
        "get_quote", "get_history", "get_option_chain", "get_positions",
        "get_portfolio", "get_risk_status", "place_order", "cancel_order",
        "modify_order",
    } <= names
