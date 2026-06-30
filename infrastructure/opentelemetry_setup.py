# Backward compat — moved to infrastructure.observability.opentelemetry_setup
from infrastructure.observability.opentelemetry_setup import (
    get_tracer,
    otel_available,
    setup_telemetry,
)

__all__ = [
    "get_tracer",
    "otel_available",
    "setup_telemetry",
]
