"""Tests for the shared error hierarchy."""

import pytest

from shared.errors import (
    BrokerError,
    ConfigError,
    LifecycleError,
    OrderError,
    RiskRejectedError,
    TradeXError,
)


class TestErrorHierarchy:
    def test_base_error_is_exception(self):
        assert issubclass(TradeXError, Exception)

    def test_all_errors_inherit_from_tradex_error(self):
        for cls in (ConfigError, LifecycleError, RiskRejectedError, BrokerError, OrderError):
            assert issubclass(cls, TradeXError)

    def test_errors_are_catchable_as_base(self):
        with pytest.raises(TradeXError):
            raise ConfigError("bad config")

    def test_errors_carry_message(self):
        err = BrokerError("connection refused")
        assert str(err) == "connection refused"

    def test_specific_catch(self):
        with pytest.raises(RiskRejectedError):
            raise RiskRejectedError("limit exceeded")
