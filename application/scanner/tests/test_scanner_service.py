"""Tests for scanner service."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.scanner.scanner_service import ScannerService


def _make_gateway(data_available: bool = True):
    gw = MagicMock()
    if data_available:
        import numpy as np
        import pandas as pd
        gw.history.return_value = pd.DataFrame({
            "open": np.random.randn(100) + 100,
            "high": np.random.randn(100) + 102,
            "low": np.random.randn(100) + 98,
            "close": np.random.randn(100) + 100,
            "volume": np.random.randint(1000, 10000, 100),
        })
    else:
        gw.history.return_value = None
    return gw


def _make_catalog():
    return MagicMock()


class TestScannerService:
    def test_unknown_scanner_raises(self):
        gw = _make_gateway()
        cat = _make_catalog()
        svc = ScannerService(gw, cat)

        with pytest.raises(ValueError, match="Unknown scanner"):
            svc.run_scan("nonexistent", universe="NIFTY50")

    def test_valid_scanners_accepted(self):
        """Verify all three scanner names are recognized."""
        gw = _make_gateway()
        cat = _make_catalog()
        svc = ScannerService(gw, cat)

        for name in ["momentum", "volume", "breakout"]:
            # Will fail on execution but shouldn't raise ValueError for name
            try:
                svc.run_scan(name, universe="NIFTY50")
            except ValueError as e:
                if "Unknown scanner" in str(e):
                    pytest.fail(f"Scanner '{name}' should be recognized")
            except Exception:
                pass  # Other errors are OK in unit test
