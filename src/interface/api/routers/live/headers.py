"""Response provenance headers for live broker routes."""

from __future__ import annotations

from fastapi import Response


def apply_live_headers(response: Response, broker_name: str) -> None:
    """Set mandatory data provenance headers."""
    response.headers["X-Data-Source"] = "live_broker"
    response.headers["X-Broker-Name"] = broker_name
