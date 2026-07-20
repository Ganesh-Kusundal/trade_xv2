"""Re-export of transport-error mapping now owned by infrastructure.

The implementation moved to ``infrastructure.resilience.transport_errors`` so
gateway code can use it without violating the infrastructure-independence
import contract. Broker/runtime importers keep working through this shim.
"""

from __future__ import annotations

from infrastructure.resilience.transport_errors import (
    map_transport_exception,
    order_response_from_transport_error,
    order_result_from_response,
    order_result_from_transport_error,
)

__all__ = [
    "map_transport_exception",
    "order_response_from_transport_error",
    "order_result_from_response",
    "order_result_from_transport_error",
]
