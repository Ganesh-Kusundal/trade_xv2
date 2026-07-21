"""Dhan position capabilities — positions, holdings, balance, exit, P&L exit.

Extracted from ``broker_extensions.py`` to keep the broker-specific surface focused.
This module must NOT import from ``broker_extensions`` to avoid circular deps.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from domain.constants import DEFAULT_EXCHANGE

if TYPE_CHECKING:
    from brokers.dhan.streaming.connection import DhanConnection


class DhanPositionCapabilities:
    """Positions, holdings, balance, exit-all, and P&L-based exit."""

    def __init__(self, conn: DhanConnection) -> None:
        self._conn = conn

    # ── Portfolio shortcuts (contract-suite compat) ─────────────────

    def get_positions(self) -> list[Any]:
        """Get current positions."""
        return self._conn.portfolio.get_positions()

    def get_holdings(self) -> list[Any]:
        """Get current holdings."""
        return self._conn.portfolio.get_holdings()

    def get_balance(self) -> Any:
        """Get account balance."""
        return self._conn.portfolio.get_balance()

    # ── Exit All ──────────────────────────────────────────────────────

    def exit_all(self) -> Any:
        """Close all open positions."""
        return self._conn.exit_all.exit_all()

    # ── Portfolio convert ─────────────────────────────────────────────

    def convert_position(
        self,
        symbol: str,
        *,
        exchange: str = DEFAULT_EXCHANGE,
        quantity: int,
        from_product_type: str,
        to_product_type: str,
        position_type: str = "LONG",
        security_id: str | None = None,
    ) -> dict[str, Any]:
        """Convert open position product type (INTRADAY ↔ CNC, etc.)."""
        return self._conn.portfolio.convert_position(
            symbol,
            exchange=exchange,
            quantity=quantity,
            from_product_type=from_product_type,
            to_product_type=to_product_type,
            position_type=position_type,
            security_id=security_id,
        )

    # ── P&L Based Exit (Trader's Control) ─────────────────────────────

    def configure_pnl_exit(
        self,
        *,
        profit_value: Any = None,
        loss_value: Any = None,
        product_types: list[str] | None = None,
        enable_kill_switch: bool = False,
    ) -> Any:
        """Configure day-session P&L auto-exit thresholds."""
        return self._conn.pnl_exit.configure(
            profit_value=profit_value,
            loss_value=loss_value,
            product_types=product_types,
            enable_kill_switch=enable_kill_switch,
        )

    def stop_pnl_exit(self) -> Any:
        """Disable active P&L based exit."""
        return self._conn.pnl_exit.stop()

    def get_pnl_exit(self) -> Any:
        """Fetch current P&L based exit configuration."""
        return self._conn.pnl_exit.get()
