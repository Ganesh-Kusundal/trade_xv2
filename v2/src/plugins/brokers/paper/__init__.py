"""Paper broker — in-memory venue, no network I/O."""

from __future__ import annotations

from domain.enums import BrokerId
from plugins.brokers.paper.gateway import PAPER_CAPABILITIES, PaperGateway
from plugins.brokers.registry import register_broker_plugin


def register() -> None:
    """Entry point: tradex.brokers → paper."""
    register_broker_plugin(
        BrokerId.PAPER,
        {"gateway": PaperGateway, "capabilities": PAPER_CAPABILITIES},
    )


__all__ = ["PAPER_CAPABILITIES", "PaperGateway", "register"]
