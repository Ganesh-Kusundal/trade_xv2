"""TOS-P6-005 live strategy engine dry-run + kill-switch."""

from __future__ import annotations

from application.strategy_engine import LiveStrategyEngine, StrategyEngineConfig


class _Pipe:
    def evaluate(self, candidates, features):
        class R:
            actionable = ["sig1", "sig2"]

        return [R()]


def test_dry_run_blocks_placement():
    eng = LiveStrategyEngine(
        pipeline=_Pipe(),
        config=StrategyEngineConfig(dry_run=True),
    )
    out = eng.run_once([], {})
    assert out["placed"] == 0
    assert out["blocked_reason"] == "dry_run"
    assert out["signals"] == 2


def test_kill_switch_blocks():
    eng = LiveStrategyEngine(
        pipeline=_Pipe(),
        config=StrategyEngineConfig(dry_run=False, kill_switch_active=True),
    )
    out = eng.run_once([], {})
    assert out["placed"] == 0
    assert out["blocked_reason"] == "kill_switch_active"
