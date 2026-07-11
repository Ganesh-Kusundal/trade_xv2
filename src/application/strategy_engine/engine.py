"""Live strategy engine with dry-run + kill-switch (TOS-P6-005).

Evaluates strategies via StrategyPipeline and optionally routes intents
through OMS. Dry-run never places. Kill-switch blocks all live placement.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class StrategyEngineConfig:
    dry_run: bool = True
    kill_switch_active: bool = False
    max_signals: int = 50


@dataclass
class LiveStrategyEngine:
    """Paper/live strategy loop with mandatory dry-run default."""

    pipeline: Any
    order_service: Any | None = None  # OrderServicePort / OmsOrderService
    risk_manager: Any | None = None
    config: StrategyEngineConfig = field(default_factory=StrategyEngineConfig)

    def is_placement_allowed(self) -> tuple[bool, str]:
        if self.config.kill_switch_active:
            return False, "kill_switch_active"
        if self.risk_manager is not None and hasattr(
            self.risk_manager, "is_kill_switch_active"
        ):
            if self.risk_manager.is_kill_switch_active():
                return False, "risk_kill_switch"
        if self.config.dry_run:
            return False, "dry_run"
        return True, "ok"

    def evaluate(
        self,
        candidates: list[Any],
        features_by_symbol: dict[str, Any],
    ) -> list[Any]:
        results = self.pipeline.evaluate(candidates, features_by_symbol)
        # Flatten actionable signals
        signals: list[Any] = []
        for r in results:
            actionable = getattr(r, "actionable", None)
            if actionable is None:
                continue
            signals.extend(list(actionable)[: self.config.max_signals])
        return signals[: self.config.max_signals]

    def run_once(
        self,
        candidates: list[Any],
        features_by_symbol: dict[str, Any],
    ) -> dict[str, Any]:
        """Evaluate and optionally place (never when dry_run / kill-switch)."""
        signals = self.evaluate(candidates, features_by_symbol)
        allowed, reason = self.is_placement_allowed()
        placements: list[dict[str, Any]] = []
        if not allowed:
            return {
                "signals": len(signals),
                "placed": 0,
                "blocked_reason": reason,
                "dry_run": self.config.dry_run,
                "signal_preview": [str(s) for s in signals[:5]],
            }
        if self.order_service is None:
            return {
                "signals": len(signals),
                "placed": 0,
                "blocked_reason": "no_order_service",
                "dry_run": False,
            }
        for sig in signals:
            try:
                # Best-effort: signal may expose to_intent / place hook
                if hasattr(sig, "to_intent"):
                    intent = sig.to_intent()
                    result = self.order_service.place_order(intent)
                    placements.append({"ok": True, "result": str(result)})
                else:
                    placements.append({"ok": False, "error": "signal_has_no_to_intent"})
            except Exception as exc:
                logger.warning("strategy_place_failed: %s", exc)
                placements.append({"ok": False, "error": str(exc)})
        return {
            "signals": len(signals),
            "placed": sum(1 for p in placements if p.get("ok")),
            "blocked_reason": None,
            "dry_run": False,
            "placements": placements,
        }
