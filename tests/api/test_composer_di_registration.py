"""Task 1 verification: DI registration of ExecutionComposer.

Tests that create_app(execution_composer=...) makes the composer
resolvable via get_execution_composer() — the exact bug fixed in
api/main.py where composers were silently dropped.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from api.config import APIConfig
from api.deps import (
    get_execution_composer,
    get_market_data_composer,
    reset_container,
    set_container,
)
from api.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clean_di():
    """Reset DI container before and after each test."""
    reset_container()
    yield
    reset_container()


class TestComposerDIRegistration:
    """Verify composers are properly registered in DI when passed to create_app()."""

    def test_execution_composer_resolvable_when_provided(self):
        """create_app(execution_composer=mock) must make it resolvable."""
        mock_composer = MagicMock()
        app = create_app(
            config=APIConfig(auth_mode="none"),
            execution_composer=mock_composer,
        )
        # The composer should be resolvable — not raise 503
        resolved = get_execution_composer()
        assert resolved is mock_composer

    def test_execution_composer_raises_503_when_not_provided(self):
        """Without execution_composer, get_execution_composer() must raise 503."""
        app = create_app(config=APIConfig(auth_mode="none"))
        with pytest.raises(HTTPException) as exc_info:
            get_execution_composer()
        assert exc_info.value.status_code == 503

    def test_market_data_composer_resolvable_when_provided(self):
        """create_app(market_data_composer=mock) must make it resolvable."""
        mock_composer = MagicMock()
        app = create_app(
            config=APIConfig(auth_mode="none"),
            market_data_composer=mock_composer,
        )
        resolved = get_market_data_composer()
        assert resolved is mock_composer

    def test_market_data_composer_raises_503_when_not_provided(self):
        """Without market_data_composer, get_market_data_composer() must raise 503."""
        app = create_app(config=APIConfig(auth_mode="none"))
        with pytest.raises(HTTPException) as exc_info:
            get_market_data_composer()
        assert exc_info.value.status_code == 503

    def test_both_composers_resolvable_simultaneously(self):
        """Both composers can coexist in DI."""
        mock_md = MagicMock()
        mock_exec = MagicMock()
        app = create_app(
            config=APIConfig(auth_mode="none"),
            market_data_composer=mock_md,
            execution_composer=mock_exec,
        )
        assert get_market_data_composer() is mock_md
        assert get_execution_composer() is mock_exec

    def test_composer_none_when_explicitly_passed_as_none(self):
        """Passing execution_composer=None must register None (503 on resolve)."""
        app = create_app(
            config=APIConfig(auth_mode="none"),
            execution_composer=None,
        )
        with pytest.raises(HTTPException) as exc_info:
            get_execution_composer()
        assert exc_info.value.status_code == 503
