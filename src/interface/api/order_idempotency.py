"""API order idempotency — correlation_id / X-Idempotency-Key contract."""

from __future__ import annotations

import os
import uuid

IDEMPOTENCY_HEADER = "X-Idempotency-Key"


def _dev_auto_correlation_allowed() -> bool:
    """ponytail: dev-only escape hatch; prod must supply explicit idempotency keys."""
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    if os.getenv("TRADEX_DEV") == "1":
        return True
    from config.schema import AppConfig

    cfg = AppConfig.from_env()
    return cfg.app_env in ("dev", "development") and not cfg.is_production_or_staging()


def resolve_api_correlation_id(
    body_correlation_id: str | None,
    idempotency_key: str | None,
) -> str:
    """Resolve process-wide OMS correlation id from body or idempotency header."""
    if body_correlation_id and str(body_correlation_id).strip():
        return str(body_correlation_id).strip()
    if idempotency_key and str(idempotency_key).strip():
        return str(idempotency_key).strip()
    if _dev_auto_correlation_allowed():
        return f"api:{uuid.uuid4().hex[:12]}"
    raise ValueError(
        "correlation_id (body) or X-Idempotency-Key header is required for order placement"
    )
