"""P1-T2 (drift D3): Upstox exit-all honours the live-order authority.

The Upstox exit-all adapter deactivates every trading segment via the kill
switch — a destructive live action that bypassed the OMS gate. It now accepts an
``authorize`` callable and MUST call it before the kill-switch wire call.
"""

from __future__ import annotations

import pytest

from brokers.upstox.orders.exit_all_adapter import UpstoxExitAllAdapter


class _RecordingKillSwitch:
    """Real recording fake (not a mock) for UpstoxKillSwitchClient.set_status."""

    def __init__(self) -> None:
        self.calls: list[object] = []

    def set_status(self, updates: object) -> dict[str, object]:
        self.calls.append(updates)
        return {"status": "ok"}


class _Blocked(RuntimeError):
    pass


def test_exit_all_blocked_before_wire() -> None:
    ks = _RecordingKillSwitch()
    adapter = UpstoxExitAllAdapter(ks)
    with pytest.raises(_Blocked):
        adapter.exit_all(authorize=lambda: (_ for _ in ()).throw(_Blocked()))
    assert ks.calls == []


def test_exit_all_reaches_wire_when_authorized() -> None:
    ks = _RecordingKillSwitch()
    adapter = UpstoxExitAllAdapter(ks)
    result = adapter.exit_all(authorize=lambda: None)
    assert result["success"] is True
    assert len(ks.calls) == 1
