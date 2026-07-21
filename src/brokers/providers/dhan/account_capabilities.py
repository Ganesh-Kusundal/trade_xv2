"""Dhan account capabilities — ledger, profile, IP management, EDIS, TPIN.

Extracted from ``broker_extensions.py`` to keep the broker-specific surface focused.
This module must NOT import from ``broker_extensions`` to avoid circular deps.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from brokers.providers.dhan.streaming.connection import DhanConnection


class DhanAccountCapabilities:
    """Ledger, user profile, IP management, and EDIS (e-DIS) capabilities."""

    def __init__(self, conn: DhanConnection) -> None:
        self._conn = conn

    # ── Ledger ────────────────────────────────────────────────────────

    def get_ledger(self, from_date: str, to_date: str) -> list[Any]:
        """Get ledger entries for a date range."""
        return self._conn.ledger.get_ledger(from_date, to_date)

    # ── User Profile ──────────────────────────────────────────────────

    def get_user_profile(self) -> Any:
        """Get user profile information."""
        return self._conn.user_profile.get_profile()

    # ── IP Management ─────────────────────────────────────────────────

    def set_ip(self, ip_address: str, ip_type: str) -> dict:
        """Set IP address for API access."""
        return self._conn.ip_management.set_ip(ip_address, ip_type)

    def modify_ip(self, ip_address: str, ip_type: str) -> dict:
        """Modify IP address."""
        return self._conn.ip_management.modify_ip(ip_address, ip_type)

    def get_ip(self) -> list[Any]:
        """Get configured IP addresses."""
        return self._conn.ip_management.get_ip()

    # ── EDIS (Electronic Delivery Instruction) ────────────────────────

    def generate_tpin(self) -> dict:
        """Generate TPIN for EDIS."""
        return self._conn.edis.generate_tpin()

    def authorize_edis(self, isin: str, quantity: int, exchange: str) -> dict:
        """Authorize EDIS transaction."""
        return self._conn.edis.authorize_edis(isin, quantity, exchange)

    def check_edis_status(self, isin: str) -> dict:
        """Check EDIS authorization status."""
        return self._conn.edis.check_status(isin)
