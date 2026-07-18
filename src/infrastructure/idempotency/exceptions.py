"""Idempotency-specific exceptions."""

from __future__ import annotations

from domain.exceptions import TradeXV2Error


class IdempotencyError(TradeXV2Error):
    """Base exception for idempotency-related errors."""
    
    def __init__(self, message: str, key: str | None = None, operation: str = "unknown"):
        super().__init__(message)
        self.message = message
        self.key = key
        self.operation = operation
    
    def __str__(self) -> str:
        parts = [f"IdempotencyError: {self.message}"]
        if self.key:
            parts.append(f"key={self.key}")
        if self.operation:
            parts.append(f"operation={self.operation}")
        return " | ".join(parts)


__all__ = [
    "IdempotencyError",
]