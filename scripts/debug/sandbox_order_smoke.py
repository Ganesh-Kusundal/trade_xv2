#!/usr/bin/env python3
"""Dhan sandbox order smoke — product path place LIMIT + cancel.

Prerequisites (in ``.env.local``)::

    DHAN_SANDBOX_CLIENT_ID=...
    DHAN_SANDBOX_ACCESS_TOKEN=...   # must be a *sandbox* token (not LIVE)

Run::

    PYTHONPATH=src:. python scripts/sandbox_order_smoke.py

Exit codes:
  0  place+cancel OK
  2  missing credentials
  3  token/auth failure (refresh sandbox token)
  4  other place failure
"""

from __future__ import annotations

import os
import sys
import uuid
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _materialize() -> Path | None:
    from dotenv import dotenv_values

    local = ROOT / ".env.local"
    if not local.is_file():
        return None
    vals = dotenv_values(local)
    cid = (vals.get("DHAN_SANDBOX_CLIENT_ID") or "").strip()
    tok = (vals.get("DHAN_SANDBOX_ACCESS_TOKEN") or "").strip()
    if not cid or not tok:
        return None
    path = ROOT / ".env.dhan.sandbox"
    base = vals.get("DHAN_SANDBOX_REST_BASE_URL") or "https://sandbox.dhan.co/v2"
    path.write_text(
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
    # Decode JWT exp if possible for diagnostics
    try:
        import base64
        import json

        parts = tok.split(".")
        if len(parts) >= 2:
            pad = "=" * (-len(parts[1]) % 4)
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + pad))
            exp = payload.get("exp")
            if exp:
                from datetime import datetime, timezone

                print(
                    "token exp:",
                    datetime.fromtimestamp(int(exp), tz=timezone.utc).isoformat(),
                )
    except Exception:
        pass
    return path


def main() -> int:
    env_path = _materialize()
    if env_path is None:
        print("Missing DHAN_SANDBOX_CLIENT_ID / DHAN_SANDBOX_ACCESS_TOKEN in .env.local")
        return 2

    for k in list(os.environ):
        if k.startswith("DHAN_"):
            del os.environ[k]

    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT))

    import tradex
    from application.oms.process_context import register_oms_context, reset_oms_context
    from application.oms.session_bridge import build_oms_service
    from brokers.dhan.identity.account_registry import AccountConnectionRegistry
    from brokers.paper.execution_provider import PaperExecutionProvider
    from brokers.paper.paper_gateway import PaperGateway

    reset_oms_context()
    AccountConnectionRegistry.release_all()
    paper_ep = PaperExecutionProvider(PaperGateway(initial_capital=Decimal("1000000")))
    oms = build_oms_service(paper_ep, broker_id="paper")

    class _Ctx:
        order_manager = oms.order_manager

    register_oms_context(_Ctx())  # type: ignore[arg-type]

    try:
        session = tradex.connect(
            "dhan", mode="trade", env_path=str(env_path), load_instruments=True
        )
    except Exception as exc:
        print("connect failed:", exc)
        reset_oms_context()
        return 3

    try:
        stock = session.universe.equity("RELIANCE")
        price = Decimal("1000")
        corr = uuid.uuid4().hex[:16]
        result = stock.buy(1, price=price, correlation_id=corr)
        print("place success=", result.success, "error=", result.error)
        if not result.success:
            err = (result.error or "").lower()
            if "token" in err or "dh-906" in err or "unauth" in err:
                print(
                    "HINT: Generate a fresh SANDBOX access token in Dhan and "
                    "update DHAN_SANDBOX_ACCESS_TOKEN in .env.local"
                )
                return 3
            return 4
        oid = result.order.order_id
        can = session.cancel(oid)
        print("cancel success=", can.success, "error=", can.error)
        return 0 if can.success else 4
    finally:
        session.close()
        reset_oms_context()
        AccountConnectionRegistry.release_all()


if __name__ == "__main__":
    raise SystemExit(main())
