"""Thin client over the Anthropic SDK for the agent loop.

This module owns exactly one responsibility: turn (system, messages, tools)
into a Messages API call and hand back the model's response in a small,
mock-friendly shape (``LLMResponse``). The agent loop depends only on the
``send()`` method, so tests inject a fake client without importing
``anthropic`` or touching the network.

The API key is read from ``ANTHROPIC_API_KEY`` — never hardcoded.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMResponse:
    """Structured view of one Messages API turn.

    ``content`` mirrors the Anthropic content-block format: a list of
    ``{"type": "text", "text": ...}`` and
    ``{"type": "tool_use", "id": ..., "name": ..., "input": {...}}`` dicts.
    """

    content: list[dict[str, Any]]
    stop_reason: str | None = None
    raw: Any = None

    def tool_use_blocks(self) -> list[dict[str, Any]]:
        return [b for b in self.content if b.get("type") == "tool_use"]

    def text_blocks(self) -> list[str]:
        return [b["text"] for b in self.content if b.get("type") == "text"]


class LLMClient:
    """Duck-typed interface the loop depends on. ``AnthropicLLMClient`` is
    the real implementation; tests substitute any object with ``send()``."""

    def send(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        raise NotImplementedError


def _safe_model_dump(block: Any) -> dict[str, Any] | None:
    """Call pydantic ``model_dump()``; return None on any failure so the
    caller can fall back to manual extraction (SDK version drift)."""
    try:
        dumped = block.model_dump()
    except Exception:  # defensive: any failure means "use fallback"
        return None
    return dumped if isinstance(dumped, dict) else None


def _block_to_dict(block: Any) -> dict[str, Any]:
    """Normalise an Anthropic SDK content block to a plain dict.

    The SDK returns typed objects; ``model_dump()`` is the clean path, but we
    fall back to manual extraction so this survives SDK version drift.
    """
    if isinstance(block, dict):
        return block
    if hasattr(block, "model_dump") and callable(block.model_dump):
        dumped = _safe_model_dump(block)
        if dumped is not None:
            return dumped
    if getattr(block, "type", None) == "text":
        return {"type": "text", "text": getattr(block, "text", "")}
    if getattr(block, "type", None) == "tool_use":
        return {
            "type": "tool_use",
            "id": getattr(block, "id", ""),
            "name": getattr(block, "name", ""),
            "input": getattr(block, "input", {}) or {},
        }
    return {"type": getattr(block, "type", "unknown"), "raw": str(block)}


class AnthropicLLMClient(LLMClient):
    """Real client wrapping ``anthropic.Anthropic``.

    The ``anthropic`` package is an optional dependency (``agent`` extra), so
    it is imported lazily — importing *this module* does not require it.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
        client: Any | None = None,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client = client
        if self._client is None and self._api_key is None:
            # Defer the hard error to send() so construction stays testable.
            self._client_factory = self._default_client
        else:
            self._client_factory = lambda: (self._client or self._default_client())

    def _default_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - exercised only without the dep
            raise RuntimeError(
                "The 'anthropic' package is required for AnthropicLLMClient. "
                "Install the 'agent' extra: pip install -e '.[agent]'"
            ) from exc
        return anthropic.Anthropic(api_key=self._api_key)

    def send(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        client = self._client_factory()
        response = client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=messages,
            tools=tools,
        )
        content = [_block_to_dict(b) for b in response.content]
        return LLMResponse(
            content=content,
            stop_reason=getattr(response, "stop_reason", None),
            raw=response,
        )


__all__ = ["AnthropicLLMClient", "LLMClient", "LLMResponse"]
