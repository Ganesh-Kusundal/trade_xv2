# time — wall clock for streaming/composer (re-exports canonical TimeService)
from infrastructure.time.clock import Clock, TimeService, time_service

__all__ = ["Clock", "TimeService", "time_service"]
