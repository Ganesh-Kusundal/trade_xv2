"""Quotes domain — re-exports Quote + adds QuoteStream."""

from __future__ import annotations

from domain.entities.market import Quote, QuoteSnapshot
from domain.quotes.quote_stream import QuoteStream

__all__ = ["Quote", "QuoteSnapshot", "QuoteStream"]
