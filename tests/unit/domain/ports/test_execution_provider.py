"""Tests for ExecutionProvider port — verifying interface contract."""

from __future__ import annotations

import pytest

from domain.ports.execution_provider import ExecutionProvider


class TestExecutionProviderInterface:
    """ExecutionProvider must be abstract with required methods."""

    def test_cannot_instantiate_directly(self):
        """ExecutionProvider is abstract — cannot be instantiated."""
        with pytest.raises(TypeError):
            ExecutionProvider()

    def test_has_name_property(self):
        """ExecutionProvider must have a name property."""
        assert hasattr(ExecutionProvider, "name")

    def test_has_place_order_method(self):
        """ExecutionProvider must have place_order method."""
        assert hasattr(ExecutionProvider, "place_order")

    def test_has_cancel_order_method(self):
        """ExecutionProvider must have cancel_order method."""
        assert hasattr(ExecutionProvider, "cancel_order")

    def test_has_modify_order_method(self):
        """ExecutionProvider must have modify_order method."""
        assert hasattr(ExecutionProvider, "modify_order")

    def test_has_get_order_book_method(self):
        """ExecutionProvider must have get_order_book method."""
        assert hasattr(ExecutionProvider, "get_order_book")

    def test_has_get_positions_method(self):
        """ExecutionProvider must have get_positions method."""
        assert hasattr(ExecutionProvider, "get_positions")

    def test_has_get_holdings_method(self):
        """ExecutionProvider must have get_holdings method."""
        assert hasattr(ExecutionProvider, "get_holdings")

    def test_has_get_funds_method(self):
        """ExecutionProvider must have get_funds method."""
        assert hasattr(ExecutionProvider, "get_funds")

    def test_concrete_implementation_works(self):
        """A minimal concrete implementation should satisfy the interface."""
        from unittest.mock import MagicMock

        class MockExecutor(ExecutionProvider):
            @property
            def name(self) -> str:
                return "mock"

            def place_order(self, request):
                return MagicMock()

            def cancel_order(self, order_id):
                return MagicMock()

            def modify_order(self, request):
                return MagicMock()

            def get_order_book(self):
                return []

            def get_positions(self):
                return []

            def get_holdings(self):
                return []

            def get_funds(self):
                return MagicMock()

        executor = MockExecutor()
        assert executor.name == "mock"
        assert executor.get_order_book() == []
