"""Volume delta helper for cumulative broker payloads."""

from __future__ import annotations

from brokers.common.quote_normalize import CumulativeVolumeTracker, tick_volume_from_frame


def test_cumulative_vtt_emits_delta() -> None:
    tracker = CumulativeVolumeTracker()
    key = "RELIANCE:NSE"
    assert tracker.tick_volume(key, 1000, cumulative=True) == 1000
    assert tracker.tick_volume(key, 1250, cumulative=True) == 250
    assert tracker.tick_volume(key, 900, cumulative=True) == 900


def test_tick_volume_from_frame_prefers_vtt() -> None:
    first = tick_volume_from_frame({"volume": 999, "vtt": 5000}, "INFY", "NSE")
    second = tick_volume_from_frame({"volume": 999, "vtt": 5100}, "INFY", "NSE")
    assert first == 5000
    assert second == 100
