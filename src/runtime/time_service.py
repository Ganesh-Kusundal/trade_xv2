"""Re-export shim — canonical implementation is in infrastructure.time_service."""

from infrastructure.time_service import (
    FakeClock,
    SystemClock,
    TimeService,
    _wrap as _wrap_clock,
)

__all__ = ["FakeClock", "SystemClock", "TimeService", "_wrap_clock"]
