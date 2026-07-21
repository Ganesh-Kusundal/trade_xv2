"""Tests for the unified exception hierarchy in domain.exceptions."""

from __future__ import annotations

import pytest

from domain.exceptions import (
    AuthenticationError,
    BrokerDegradedError,
    BrokerError,
    BrokerNotReadyError,
    BrokerUnavailableError,
    CapabilityError,
    CircuitBreakerOpenError,
    ConfigError,
    DataError,
    ExitAllError,
    InstrumentError,
    InstrumentNotFoundError,
    LiveBrokerBlockedError,
    MappingError,
    MergeConflictError,
    NetworkError,
    NonRetryableError,
    NotConfiguredError,
    NotSupportedError,
    OrderError,
    QuotaExhaustedError,
    RateLimitError,
    RejectedOrderError,
    RetryableError,
    RoutingError,
    ServiceNotFoundError,
    TradeXV2Error,
    TradeXV2RecoverableError,
    UnsupportedExtensionError,
    UnsupportedGatewayOperationError,
    ValidationError,
)


class TestInheritanceChain:
    """Verify that all exception classes follow the expected inheritance hierarchy."""

    def test_trade_xv2_error_is_root(self):
        assert issubclass(TradeXV2Error, Exception)
        assert not issubclass(Exception, TradeXV2Error)

    def test_platform_errors_inherit_trade_xv2_error(self):
        for exc_cls in [
            ConfigError,
            DataError,
            LiveBrokerBlockedError,
            NotConfiguredError,
            ServiceNotFoundError,
            ValidationError,
        ]:
            assert issubclass(exc_cls, TradeXV2Error), f"{exc_cls.__name__} should inherit TradeXV2Error"

    def test_data_error_subclasses(self):
        assert issubclass(DataError, TradeXV2Error)

    def test_broker_error_inherits_trade_xv2_error(self):
        assert issubclass(BrokerError, TradeXV2Error)

    def test_broker_error_direct_subclasses(self):
        broker_subclasses = [
            BrokerDegradedError,
            CapabilityError,
            CircuitBreakerOpenError,
            AuthenticationError,
            ExitAllError,
            InstrumentError,
            InstrumentNotFoundError,
            MappingError,
            NetworkError,
            NonRetryableError,
            NotSupportedError,
            OrderError,
            RateLimitError,
            RejectedOrderError,
            RetryableError,
        ]
        for exc_cls in broker_subclasses:
            assert issubclass(exc_cls, BrokerError), f"{exc_cls.__name__} should inherit BrokerError"

    def test_broker_unavailable_error_inherits_trade_xv2_error_and_runtime_error(self):
        assert issubclass(BrokerUnavailableError, TradeXV2Error)
        assert issubclass(BrokerUnavailableError, RuntimeError)
        assert not issubclass(BrokerUnavailableError, BrokerError)

    def test_quota_exhausted_inherits_trade_xv2_error_and_runtime_error(self):
        assert issubclass(QuotaExhaustedError, TradeXV2Error)
        assert issubclass(QuotaExhaustedError, RuntimeError)
        assert not issubclass(QuotaExhaustedError, BrokerError)

    def test_retryable_error_hierarchy(self):
        assert issubclass(RetryableError, BrokerError)
        assert issubclass(TradeXV2RecoverableError, RetryableError)
        assert TradeXV2RecoverableError is RetryableError

    def test_network_error_inherits_retryable_error(self):
        assert issubclass(NetworkError, RetryableError)
        assert issubclass(NetworkError, BrokerError)
        assert issubclass(NetworkError, TradeXV2Error)

    def test_order_error_hierarchy(self):
        assert issubclass(OrderError, BrokerError)
        assert issubclass(RejectedOrderError, OrderError)
        assert issubclass(RejectedOrderError, BrokerError)

    def test_instrument_error_hierarchy(self):
        assert issubclass(InstrumentError, BrokerError)
        assert issubclass(InstrumentNotFoundError, InstrumentError)
        assert issubclass(InstrumentNotFoundError, BrokerError)

    def test_not_supported_error_hierarchy(self):
        assert issubclass(NotSupportedError, BrokerError)
        assert issubclass(CapabilityError, NotSupportedError)
        assert issubclass(ExitAllError, NotSupportedError)

    def test_routing_quota_errors_inherit_trade_xv2_error(self):
        assert issubclass(RoutingError, TradeXV2Error)
        assert issubclass(QuotaExhaustedError, TradeXV2Error)
        assert issubclass(MergeConflictError, TradeXV2Error)
        assert issubclass(BrokerUnavailableError, TradeXV2Error)
        assert issubclass(UnsupportedExtensionError, TradeXV2Error)
        assert issubclass(UnsupportedGatewayOperationError, TradeXV2Error)

    def test_live_broker_blocked_inherits_runtime_error(self):
        assert issubclass(LiveBrokerBlockedError, RuntimeError)

    def test_broker_unavailable_inherits_runtime_error(self):
        assert issubclass(BrokerUnavailableError, RuntimeError)

    def test_routing_error_inherits_runtime_error(self):
        assert issubclass(RoutingError, RuntimeError)

    def test_quota_exhausted_inherits_runtime_error(self):
        assert issubclass(QuotaExhaustedError, RuntimeError)

    def test_unsupported_gateway_operation_inherits_not_implemented_error(self):
        assert issubclass(UnsupportedGatewayOperationError, NotImplementedError)

    def test_unsupported_extension_inherits_not_implemented_error(self):
        assert issubclass(UnsupportedExtensionError, NotImplementedError)

    def test_merge_conflict_inherits_value_error(self):
        assert issubclass(MergeConflictError, ValueError)


class TestAliasConsistency:
    """Verify re-exports and aliases are correct."""

    def test_trade_xv2_recoverable_error_alias(self):
        assert TradeXV2RecoverableError is RetryableError

    def test_domain_errors_shim_has_key_types(self):
        """Verify that domain.errors re-exports key types from domain.exceptions."""
        import domain.errors as errors_shim

        assert issubclass(errors_shim.TradeXV2Error, Exception)
        assert issubclass(errors_shim.BrokerError, errors_shim.TradeXV2Error)
        assert issubclass(errors_shim.TradeXV2RecoverableError, errors_shim.BrokerError)

    def test_infrastructure_resilience_errors_shim_re_exports(self):
        """Verify that infrastructure.resilience.errors re-exports from domain.exceptions."""
        import infrastructure.resilience.errors as resilience_errors

        assert hasattr(resilience_errors, "TradeXV2Error")
        assert hasattr(resilience_errors, "BrokerError")
        assert hasattr(resilience_errors, "NetworkError")
        assert hasattr(resilience_errors, "convert_network_errors")

    def test_convert_network_errors_preserved(self):
        """Ensure the convert_network_errors decorator is still accessible."""
        from infrastructure.resilience.errors import convert_network_errors

        assert callable(convert_network_errors)
