"""Sandbox order placement via product API (tradex.connect).

**Product gate (deliberate, not money risk):**
- ``DHAN_ENVIRONMENT=SANDBOX``
- ``DHAN_ALLOW_LIVE_ORDERS=1``
- Sandbox credentials (``DHAN_SANDBOX_*``)
- Process OMS registered (ENG-001)
- Far-from-market LIMIT then cancel

Not run in default CI — requires ``@pytest.mark.sandbox`` and credentials.

::

    PYTHONPATH=src:. pytest tests/e2e/test_sandbox_product_orders.py -m sandbox -q
"""

from __future__ import annotations

from brokers import BrokerSession
from tests.support.gateway_orders import (
    cancel_via_gateway,
    modify_via_gateway,
    place_via_gateway,
    subscribe_via_gateway,
)

import contextlib
import os
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SANDBOX_ENV = ROOT / ".env.dhan.sandbox"
LOCAL_ENV = ROOT / ".env.local"

pytestmark = pytest.mark.sandbox


def _materialize_sandbox_env() -> Path | None:
    """Build/refresh ``.env.dhan.sandbox`` from sandbox keys in ``.env.local``."""
    from dotenv import dotenv_values

    if not LOCAL_ENV.is_file():
        return None
    vals = dotenv_values(LOCAL_ENV)
    cid = (vals.get("DHAN_SANDBOX_CLIENT_ID") or "").strip()
    tok = (vals.get("DHAN_SANDBOX_ACCESS_TOKEN") or "").strip()
    if not cid or not tok:
        return None
    base = (vals.get("DHAN_SANDBOX_REST_BASE_URL") or "https://sandbox.dhan.co/v2").strip()
    SANDBOX_ENV.write_text(
        "\n".join(
            [
                "DHAN_ENVIRONMENT=SANDBOX",
                "DHAN_ALLOW_LIVE_ORDERS=1",
                f"DHAN_SANDBOX_CLIENT_ID={cid}",
                f"DHAN_SANDBOX_ACCESS_TOKEN={tok}",
                "DHAN_SANDBOX_ENVIRONMENT=SANDBOX",
                f"DHAN_SANDBOX_REST_BASE_URL={base}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return SANDBOX_ENV


def _sandbox_ready() -> bool:
    return _materialize_sandbox_env() is not None


def _clear_dhan_env() -> None:
    for k in list(os.environ):
        if k.startswith("DHAN_"):
            del os.environ[k]


@pytest.fixture
def sandbox_session():
    """Process OMS + tradex.connect(dhan, mode=trade) against sandbox env file."""
    if not _sandbox_ready():
        pytest.skip("Dhan sandbox credentials not configured in .env.local")

    _clear_dhan_env()
    import tradex
    from application.oms.process_context import register_oms_context, reset_oms_context
    from application.oms.session_bridge import build_oms_service
    from brokers.providers.dhan.identity.account_registry import AccountConnectionRegistry
    from brokers.providers.paper.execution_provider import PaperExecutionProvider
    from brokers.providers.paper.paper_gateway import PaperGateway

    reset_oms_context()
    AccountConnectionRegistry.release_all()

    # Process-wide OMS book (ENG-001); execution uses Dhan transport from connect.
    paper_ep = PaperExecutionProvider(PaperGateway(initial_capital=Decimal("1000000")))
    oms = build_oms_service(paper_ep, broker_id="paper")

    class _Ctx:
        order_manager = oms.order_manager

    register_oms_context(_Ctx())  # type: ignore[arg-type]

    session = None
    try:
        session = tradex.connect(
            "dhan",
            mode="trade",
            env_path=str(SANDBOX_ENV),
            load_instruments=True,
        )
        assert session.status is not None
        assert session.status.mode == "trade"
        assert session.status.orders_enabled is True
        yield session
    finally:
        if session is not None:
            with contextlib.suppress(Exception):
                session.close()
        reset_oms_context()
        AccountConnectionRegistry.release_all()
        _clear_dhan_env()


def test_sandbox_product_path_limit_place_and_cancel(sandbox_session) -> None:
    """TR-022 sandbox: Instrument LIMIT far below market → cancel via Session."""
    session = sandbox_session
    stock = session.universe.equity("RELIANCE")

    # Sandbox market-data endpoints may 404; use conservative fixed LIMIT.
    # Align to ₹10 tick if local validators require it.
    price = Decimal("1000")
    corr = uuid.uuid4().hex[:16]

    result = place_via_gateway(session, stock, 
        1,
        price=price,
        correlation_id=corr,
    )
    if not result.success:
        msg = (result.error or "").lower()
        # Soft-skip credential / sandbox outage — gate still documents the path
        if any(
            x in msg
            for x in (
                "token",
                "dh-906",
                "unauthorized",
                "401",
                "403",
                "not found",
                "instrument resolution",
            )
        ):
            pytest.skip(f"sandbox unavailable or token rejected: {result.error}")
        pytest.fail(f"sandbox place failed: {result.error}")

    assert result.order is not None
    oid = result.order.order_id
    assert oid

    can = cancel_via_gateway(session, oid)
    if not can.success:
        # Order may already be rejected/cancelled by broker — still exercised path
        pytest.skip(f"sandbox cancel soft-fail (order may be terminal): {can.error}")
    assert can.success is True


def test_sandbox_allow_live_orders_gate_blocks_when_disabled() -> None:
    """Without ALLOW_LIVE_ORDERS, sandbox/live transport must refuse placement."""
    if not LOCAL_ENV.is_file():
        pytest.skip("no .env.local")

    # Unit-level: OrdersAdapter fail-closed
    from unittest.mock import MagicMock

    from brokers.providers.dhan.execution.orders import OrdersAdapter
    from domain.enums import OrderType, ProductType, Side, Validity
    from domain.models.dtos import BrokerOrderPayload

    adapter = OrdersAdapter(
        MagicMock(),
        MagicMock(),
        allow_live_orders=False,
        allow_duck_identity=True,
    )
    resp = adapter.place_order(
        BrokerOrderPayload(
            symbol="RELIANCE",
            exchange="NSE",
            transaction_type=Side.BUY,
            quantity=1,
            price=Decimal("1000"),
            order_type=OrderType.LIMIT,
            product_type=ProductType.INTRADAY,
            validity=Validity.DAY,
        )
    )
    assert resp.success is False
    assert "ALLOW_LIVE_ORDERS" in (resp.message or "")
