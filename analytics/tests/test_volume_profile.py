"""Tests for volume profile."""

from __future__ import annotations

import pytest

from analytics.volume_profile.volume_profile import VolumeProfileBuilder

from .helpers import prices


class TestVolumeProfile:
    def test_basic(self) -> None:
        df = prices(30)
        result = VolumeProfileBuilder().build(df)
        assert result is not None
