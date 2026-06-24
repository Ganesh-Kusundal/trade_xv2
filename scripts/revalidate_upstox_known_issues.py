#!/usr/bin/env python3
"""Read-only Upstox revalidation harness.

Runs live HTTP/WS probes against `.env.upstox` credentials and writes
evidence to markdown. No order placement or write operations.

Usage::

    venv/bin/python scripts/revalidate_upstox_known_issues.py \\
        --output docs/audits/UPSTOX_REVALIDATION_EVIDENCE.md
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
ENV_PATH = PROJECT_ROOT / ".env.upstox"
DEFAULT_OUTPUT = PROJECT_ROOT / "docs" / "audits" / "UPSTOX_REVALIDATION_EVIDENCE.md"


def _load_env() -> bool:
    if not ENV_PATH.exists() or ENV_PATH.stat().st_size == 0:
        return False
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH, override=True)
    return bool(os.environ.get("UPSTOX_API_KEY") and os.environ.get("UPSTOX_ACCESS_TOKEN"))


def _token_valid() -> tuple[bool, str]:
    token = os.environ.get("UPSTOX_ACCESS_TOKEN", "")
    try:
        from brokers.common.auth.jwt_expiry import JwtExpiry

        exp_ms = JwtExpiry.parse_expiry_epoch_ms(token)
        if exp_ms > 0 and exp_ms < time.time() * 1000:
            return False, "access token expired"
        return True, "token valid"
    except Exception as exc:
        return False, f"token parse failed: {exc}"


def _market_open() -> bool:
    try:
        from tests.market_hours import is_market_open

        return bool(is_market_open())
    except Exception:
        return True


def _gateway():
    from brokers.upstox.factory import UpstoxBrokerFactory

    return UpstoxBrokerFactory().create(
        env_path=ENV_PATH, load_instruments=True, analytics_only=True
    )


def _data_list(body: Any) -> list[Any]:
    if not isinstance(body, dict):
        return []
    data = body.get("data")
    return data if isinstance(data, list) else []


def probe_depth(gw: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for symbol in ("RELIANCE", "NIFTY"):
        try:
            depth = gw.depth(symbol, "NSE")
            bids = getattr(depth, "bids", []) or []
            asks = getattr(depth, "asks", []) or []
            rows.append({
                "probe": f"D-{symbol}",
                "pass": len(bids) >= 1 and len(asks) >= 1 and len(bids) <= 5 and len(asks) <= 5,
                "detail": (
                    f"bids={len(bids)} asks={len(asks)} "
                    "endpoint=GET /v2/market-quote/quotes?quote=BEST_FIVE"
                ),
            })
        except Exception as exc:
            rows.append({"probe": f"D-{symbol}", "pass": False, "detail": str(exc)})
    return rows


def probe_options(gw: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        expiries = gw._broker.options.get_expiries("NIFTY", "NFO")
        rows.append({
            "probe": "O1-expiries",
            "pass": len(expiries) >= 1 and all(e >= date.today().isoformat() for e in expiries[:5]),
            "detail": f"count={len(expiries)} sample={expiries[:3]}",
        })
        chain = gw.option_chain("NIFTY", exchange="NFO", expiry=expiries[0] if expiries else None)
        data = chain.to_dict() if hasattr(chain, "to_dict") else {}
        strikes = data.get("strikes", [])
        rows.append({
            "probe": "O2-chain",
            "pass": len(strikes) >= 1,
            "detail": f"expiry={data.get('expiry')} strikes={len(strikes)}",
        })
    except Exception as exc:
        rows.append({"probe": "O-options", "pass": False, "detail": str(exc)})
    return rows


def probe_futures(gw: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    broker = gw._broker
    resolver = broker.instrument_resolver
    client = broker.futures_client
    try:
        bare = client._http.get_json(
            client._urls.expired_future_contracts_url(),
            params={"instrument_key": "NIFTY"},
        )
        resolved_key = client._resolve_underlying_key("NIFTY", "NFO")
        resolved = client._http.get_json(
            client._urls.expired_future_contracts_url(),
            params={"instrument_key": resolved_key},
        )
        rows.append({
            "probe": "F1-expired-api",
            "pass": True,
            "detail": (
                f"bare_count={len(_data_list(bare))} "
                f"resolved_key={resolved_key!r} resolved_count={len(_data_list(resolved))}"
            ),
        })
        im_count = len(resolver.list_future_contracts("NIFTY")) if resolver.is_loaded() else 0
        live = gw.future_chain("NIFTY", "NFO")
        live_data = live.to_dict() if hasattr(live, "to_dict") else {}
        rows.append({
            "probe": "F4-gateway-future_chain",
            "pass": im_count > 0 or len(live_data.get("contracts", [])) > 0,
            "detail": (
                f"instrument_master={im_count} "
                f"gateway_contracts={len(live_data.get('contracts', []))}"
            ),
        })
    except Exception as exc:
        rows.append({"probe": "F-futures", "pass": False, "detail": str(exc)})
    return rows


def probe_history(gw: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        end = date.today()
        start = end - timedelta(days=30)
        df = gw.history("RELIANCE", "1d", start, end)
        tz = None
        if df is not None and not df.empty and "timestamp" in df.columns:
            ts = df["timestamp"].iloc[0]
            tz = str(getattr(ts, "tzinfo", None))
        rows.append({
            "probe": "H1-gateway-history",
            "pass": df is not None and not df.empty,
            "detail": f"rows={len(df)} first_tz={tz}",
        })
    except Exception as exc:
        rows.append({"probe": "H-history", "pass": False, "detail": str(exc)})
    return rows


async def probe_websocket(gw: Any, *, soak_seconds: float = 30.0) -> list[dict[str, Any]]:
    if not _market_open():
        return [{"probe": "W1-ws", "pass": True, "detail": "skipped — market closed"}]

    mux = gw._broker.market_data_websocket
    ticks = 0

    def on_tick(_event: str, _payload: dict) -> None:
        nonlocal ticks
        ticks += 1

    mux.add_listener(on_tick)
    try:
        await mux.connect()
        key = gw._resolve_instrument_key("RELIANCE", "NSE")
        mux.subscribe([key], mode="ltpc")
        await asyncio.sleep(soak_seconds)
        return [{
            "probe": "W1-connect-ticks",
            "pass": mux.is_connected and ticks > 0,
            "detail": f"connected={mux.is_connected} ticks={ticks} soak_s={soak_seconds}",
        }]
    except Exception as exc:
        return [{"probe": "W1-ws", "pass": False, "detail": str(exc)}]
    finally:
        with contextlib.suppress(Exception):
            await mux.disconnect()


def render_markdown(sections: dict[str, list[dict[str, Any]]], meta: dict[str, str]) -> str:
    lines = [
        "# Upstox Revalidation Evidence",
        "",
        f"- Generated: {meta['generated']}",
        f"- Python: {meta['python']}",
        f"- Token: {meta['token']}",
        f"- Market open: {meta['market_open']}",
        "",
    ]
    for title, rows in sections.items():
        lines.append(f"## {title}")
        lines.append("")
        lines.append("| Probe | Pass | Detail |")
        lines.append("|-------|------|--------|")
        for row in rows:
            lines.append(f"| {row['probe']} | {row['pass']} | {row['detail']} |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Upstox read-only revalidation harness")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--ws-soak-seconds", type=float, default=30.0)
    args = parser.parse_args()

    if os.environ.get("UPSTOX_INTEGRATION") != "1" and not ENV_PATH.exists():
        print("SKIP: .env.upstox missing and UPSTOX_INTEGRATION not set", file=sys.stderr)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            "# Upstox Revalidation Evidence\n\nSkipped — no credentials.\n",
            encoding="utf-8",
        )
        return 0

    if not _load_env():
        print("FAIL: could not load .env.upstox", file=sys.stderr)
        return 1

    ok, token_msg = _token_valid()
    if not ok:
        print(f"FAIL: {token_msg}", file=sys.stderr)
        return 1

    gw = _gateway()
    sections = {
        "Depth": probe_depth(gw),
        "Option Chain": probe_options(gw),
        "Future Chain": probe_futures(gw),
        "Historical": probe_history(gw),
        "WebSocket": asyncio.run(probe_websocket(gw, soak_seconds=args.ws_soak_seconds)),
    }
    meta = {
        "generated": datetime.now().isoformat(),
        "python": sys.version.split()[0],
        "token": token_msg,
        "market_open": str(_market_open()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_markdown(sections, meta), encoding="utf-8")
    print(f"Wrote evidence to {args.output}")
    gw.close()
    failed = sum(1 for rows in sections.values() for r in rows if not r["pass"])
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
