"""Tests for BrokerId enum (G1 stable contract)."""

from __future__ import annotations

import pytest

from domain.ports.broker_id import BrokerId


class TestBrokerId:
    def test_values(self):
        assert BrokerId.DHAN == "dhan"
        assert BrokerId.UPSTOX == "upstox"
        assert BrokerId.PAPER == "paper"
        assert BrokerId.MOCK == "mock"

    def test_from_str(self):
        assert BrokerId.from_str("dhan") == BrokerId.DHAN
        assert BrokerId.from_str("UPSTOX") == BrokerId.UPSTOX
        assert BrokerId.from_str("Paper") == BrokerId.PAPER

    def test_from_str_invalid(self):
        with pytest.raises(ValueError, match="Unknown broker"):
            BrokerId.from_str("nonexistent")

    def test_is_str(self):
        assert isinstance(BrokerId.DHAN, str)
        assert BrokerId.DHAN == "dhan"

    def test_enum_members(self):
        members = list(BrokerId)
        assert len(members) == 4
        assert BrokerId.DHAN in members
        assert BrokerId.UPSTOX in members
        assert BrokerId.PAPER in members
        assert BrokerId.MOCK in members
