"""Architecture — unified exception hierarchy (REF-1)."""

from __future__ import annotations

import pytest

from domain.exceptions import BrokerError, TradeXV2Error


@pytest.mark.architecture
def test_broker_error_is_subclass_of_tradexv2_error() -> None:
    assert issubclass(BrokerError, TradeXV2Error)



@pytest.mark.architecture
def test_infrastructure_resilience_errors_reexport_identity() -> None:
    from domain.exceptions import NetworkError
    from infrastructure.resilience.errors import NetworkError as InfraNetworkError

    assert InfraNetworkError is NetworkError
