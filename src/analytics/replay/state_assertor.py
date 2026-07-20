"""ReplayStateAssertor — derive expected state and assert replay parity.

Extracts the state-assertion responsibility from ``UnifiedReplayOrchestrator``.
Given the replay result and the event log's ``ReplayItem`` stream, it derives
the expected final state (equity, trades, position) and compares it against the
actual replayed state.
"""

from __future__ import annotations

from typing import Any

from analytics.replay.models import ReplayItem, ReplayResult


class ReplayStateAssertor:
    """Derives expected state from events and asserts replay parity."""

    def assert_state(
        self,
        result: ReplayResult | None,
        event_items: list[ReplayItem],
    ) -> tuple[bool, dict[str, Any]]:
        """Assert replayed state matches recorded state from events.

        Compares trade count, final equity (within tolerance), trade details,
        and position state between the replayed result and the event-derived
        expected state.

        Returns
        -------
        tuple[bool, dict[str, Any]]:
            (state_matches, state_diff)
        """
        expected: dict[str, Any] = {"event_count": len(event_items)}
        actual: dict[str, Any] = {"event_count": len(event_items) if result is not None else 0}
        diff: dict[str, Any] = {}

        if result is None:
            if not event_items:
                return True, {}
            return False, {"error": "replay_result is None"}

        # Trade count comparison
        trade_events = [
            i
            for i in event_items
            if i.event is not None and i.event.event_type in ("TRADE", "TRADE_APPLIED")
        ]
        expected["trade_count"] = len(trade_events)
        actual["trade_count"] = result.session.total_trades

        # Final equity comparison
        expected_equity = self.derive_expected_equity(event_items)
        actual_equity = (
            float(result.session.equity_curve[-1][1]) if result.session.equity_curve else 0.0
        )
        expected["equity_final"] = expected_equity
        actual["equity_final"] = actual_equity

        # Trade details comparison
        expected["trades"] = self.derive_expected_trades(event_items)
        actual["trades"] = [
            (t.symbol, str(t.side), t.quantity, str(t.entry_price)) for t in result.session.trades
        ]

        # Position state comparison
        expected["has_open_position"] = self.derive_expected_position_state(event_items)
        actual["has_open_position"] = result.session.position is not None

        # Validate each field
        matches = True

        # Trade count must match exactly
        if expected["trade_count"] != actual["trade_count"]:
            matches = False
            diff["trade_count"] = {
                "expected": expected["trade_count"],
                "actual": actual["trade_count"],
            }

        # Equity must match within tolerance (floating-point comparison)
        equity_tolerance = 0.01  # 1 cent tolerance
        if expected["equity_final"] is not None:
            equity_diff = abs(expected["equity_final"] - actual["equity_final"])
            if equity_diff > equity_tolerance:
                matches = False
                diff["equity_final"] = {
                    "expected": expected["equity_final"],
                    "actual": actual["equity_final"],
                    "difference": equity_diff,
                }

        # Trade details must match (if we have expected trades)
        if expected["trades"] and expected["trades"] != actual["trades"]:
            matches = False
            diff["trades"] = {
                "expected": expected["trades"],
                "actual": actual["trades"],
            }

        # Position state must match
        if expected["has_open_position"] != actual["has_open_position"]:
            matches = False
            diff["has_open_position"] = {
                "expected": expected["has_open_position"],
                "actual": actual["has_open_position"],
            }

        return matches, diff

    def derive_expected_equity(
        self,
        event_items: list[ReplayItem],
        initial_capital: float = 100_000.0,
        *,
        commission_per_trade: float = 20.0,
        slippage_bps: float = 5.0,
    ) -> float | None:
        """Derive expected final equity including commissions/slippage (TOS-P6-006).

        BUY debit / SELL credit from TRADE events, plus:
        - commission_per_trade on each fill
        - slippage_bps applied adversely to each fill price
        Open positions marked at entry price (best available estimate).
        """
        trade_events = [
            i
            for i in event_items
            if i.event is not None and i.event.event_type in ("TRADE", "TRADE_APPLIED")
        ]
        if not trade_events:
            return None

        capital = initial_capital
        position: tuple[float, int] | None = None  # (entry_price, quantity)
        valid_trades = 0
        slip = max(0.0, float(slippage_bps)) / 10_000.0

        for item in trade_events:
            payload = item.event.payload if hasattr(item.event, "payload") else {}
            side = str(payload.get("side", "")).upper()
            price = float(payload.get("price", payload.get("entry_price", 0)))
            qty = int(payload.get("quantity", 0))

            if price <= 0 or qty <= 0:
                continue

            valid_trades += 1
            if side == "BUY":
                px = price * (1.0 + slip)
                if position is None:
                    position = (px, qty)
                else:
                    # average up
                    ep, q0 = position
                    nq = q0 + qty
                    position = (((ep * q0) + (px * qty)) / nq, nq)
                capital -= px * qty
                capital -= commission_per_trade
            elif side == "SELL":
                px = price * (1.0 - slip)
                capital += px * qty
                capital -= commission_per_trade
                if position is not None:
                    ep, q0 = position
                    remain = q0 - qty
                    position = None if remain <= 0 else (ep, remain)

        if valid_trades == 0:
            return None

        if position is not None:
            capital += position[0] * position[1]

        return capital

    def derive_expected_trades(self, event_items: list[ReplayItem]) -> list[tuple]:
        """Derive expected trade list from TRADE/TRADE_APPLIED events."""
        trades = []
        for item in event_items:
            if item.event is not None and item.event.event_type in ("TRADE", "TRADE_APPLIED"):
                payload = item.event.payload if hasattr(item.event, "payload") else {}
                symbol = item.event.symbol or payload.get("symbol", "UNKNOWN")
                side = payload.get("side", "UNKNOWN")
                quantity = payload.get("quantity", 0)
                price = payload.get("price", payload.get("entry_price", 0))
                trades.append((symbol, str(side), quantity, str(price)))
        return trades

    def derive_expected_position_state(self, event_items: list[ReplayItem]) -> bool:
        """Derive expected position state (has open position?) from events.

        Tracks TRADE (open) and position-closing events to determine if
        there should be an open position at the end of replay.
        """
        has_open = False
        for item in event_items:
            if item.event is None:
                continue
            event_type = item.event.event_type
            if event_type in ("TRADE", "TRADE_APPLIED"):
                payload = item.event.payload if hasattr(item.event, "payload") else {}
                side = str(payload.get("side", "")).upper()
                # BUY opens, SELL closes
                if side == "BUY":
                    has_open = True
                elif side == "SELL":
                    has_open = False
            elif event_type == "POSITION_CLOSED":
                has_open = False
        return has_open
