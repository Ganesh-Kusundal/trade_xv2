"""Shim — use :mod:`infrastructure.observability.alerting`."""

from infrastructure.observability.alerting import (  # noqa: F401
    Alert,
    AlertingEngine,
    AlertLevel,
    AlertRule,
    create_default_alert_rules,
)
