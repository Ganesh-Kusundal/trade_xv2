"""Comprehensive live verification of all Dhan gateway endpoints + domain standardization."""

import os
import sys
import time
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(".env.local")

PASS = 0
FAIL = 0


def check(label: str, ok: bool, detail: str = ""):
    global PASS, FAIL
    tag = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    suffix = f" — {detail}" if detail else ""
    print(f"  [{tag}] {label}{suffix}")


# ── 1. BOOTSTRAP ──────────────────────────────────────────────────
print("=" * 60)
print("1. GATEWAY BOOTSTRAP")
print("=" * 60)
from interface.ui.services.broker_registry import bootstrap_gateway

result = bootstrap_gateway("dhan")
gw = result.gateway
check("Bootstrap status", result.ok, f"status={result.status.value}, broker={result.broker}")
desc = gw.describe()
for k, v in desc.items():
    print(f"  {k}: {v}")
check("Bootstrap complete", desc.get("broker") == "Dhan")

# ── 2. BALANCE / FUNDS ───────────────────────────────────────────
print()
print("=" * 60)
print("2. BALANCE & FUNDS (domain: Balance)")
print("=" * 60)
from domain import Balance

bal = gw.get_balance()
check(
    "get_balance() returns Balance", isinstance(bal, Balance), f"available={bal.available_balance}"
)
funds = gw.funds()
check("funds() returns Balance", isinstance(funds, Balance))
check("funds() == get_balance()", funds == bal)

# ── 3. MARKET DATA (domain: Quote, MarketDepth, Decimal) ─────────
print()
print("=" * 60)
print("3. MARKET DATA (LTP, Quote, Depth)")
print("=" * 60)
from domain import MarketDepth, Quote

ltp = gw.ltp("RELIANCE", "NSE")
check("ltp() returns Decimal", isinstance(ltp, Decimal), f"RELIANCE={ltp}")

q = gw.quote("RELIANCE", "NSE")
check("quote() returns Quote", isinstance(q, Quote), f"symbol={q.symbol}, ltp={q.ltp}")

d = gw.depth("RELIANCE", "NSE")
check(
    "depth() returns MarketDepth",
    isinstance(d, MarketDepth),
    f"bids={len(d.bids)}, asks={len(d.asks)}",
)

# ── 4. HISTORICAL DATA (all timeframes) ──────────────────────────
print()
print("=" * 60)
print("4. HISTORICAL DATA (all timeframes → pd.DataFrame)")
print("=" * 60)
import pandas as pd

timeframes = ["1m", "5m", "15m", "25m", "60m", "1D"]
for tf in timeframes:
    try:
        df = gw.history("RELIANCE", "NSE", timeframe=tf, lookback_days=5)
        check(f"history({tf})", isinstance(df, pd.DataFrame) and len(df) > 0, f"{len(df)} candles")
    except Exception as e:
        check(f"history({tf})", False, str(e)[:60])

# Aliases
aliases = ["1M", "5M", "15M", "60M", "D", "DAY", "1h"]
for tf in aliases:
    try:
        df = gw.history("RELIANCE", "NSE", timeframe=tf, lookback_days=5)
        check(
            f"history alias '{tf}'",
            isinstance(df, pd.DataFrame) and len(df) > 0,
            f"{len(df)} candles",
        )
    except Exception as e:
        check(f"history alias '{tf}'", False, str(e)[:60])

# Index
try:
    df = gw.history("NIFTY", "INDEX", timeframe="1D", lookback_days=5)
    check("history INDEX NIFTY", isinstance(df, pd.DataFrame) and len(df) > 0, f"{len(df)} candles")
except Exception as e:
    check("history INDEX NIFTY", False, str(e)[:60])

# ── 5. OPTIONS (domain: OptionChain, OptionStrike, OptionLeg) ────
print()
print("=" * 60)
print("5. OPTIONS ENDPOINTS (domain objects + greeks)")
print("=" * 60)
from domain import OptionChain, OptionLeg, OptionStrike

# 5a. Expiries
try:
    exps = gw.options.get_expiries("NIFTY", "INDEX")
    check("get_expiries(NIFTY)", isinstance(exps, list) and len(exps) > 0, f"{len(exps)} expiries")
    time.sleep(1.1)
except Exception as e:
    check("get_expiries(NIFTY)", False, str(e)[:60])

# 5b. Option chain with greeks
try:
    chain = gw.option_chain("NIFTY", "INDEX")
    check("option_chain() returns OptionChain", isinstance(chain, OptionChain))
    check("chain has strikes", len(chain.strikes) > 0, f"{len(chain.strikes)} strikes")

    # Verify greeks are populated (the bug we fixed)
    atm_strike = None
    spot = chain.spot
    if spot:
        for s in chain.strikes:
            if abs(float(s.strike) - float(spot)) < 100:
                atm_strike = s
                break
    if atm_strike is None and chain.strikes:
        atm_strike = chain.strikes[len(chain.strikes) // 2]

    if atm_strike:
        call = atm_strike.call
        put = atm_strike.put
        has_call_greeks = call.greeks is not None and "delta" in (call.greeks or {})
        has_put_greeks = put.greeks is not None and "delta" in (put.greeks or {})
        check(
            "CALL greeks populated",
            has_call_greeks,
            f"delta={call.greeks.get('delta') if call.greeks else 'None'}",
        )
        check(
            "PUT greeks populated",
            has_put_greeks,
            f"delta={put.greeks.get('delta') if put.greeks else 'None'}",
        )
    time.sleep(1.1)
except Exception as e:
    check("option_chain() with greeks", False, str(e)[:60])

# 5c. BANKNIFTY chain
try:
    chain2 = gw.option_chain("BANKNIFTY", "INDEX")
    check(
        "option_chain(BANKNIFTY)",
        isinstance(chain2, OptionChain) and len(chain2.strikes) > 0,
        f"{len(chain2.strikes)} strikes",
    )
    time.sleep(1.1)
except Exception as e:
    check("option_chain(BANKNIFTY)", False, str(e)[:60])

# 5d. Future chain (domain: FutureChain)
try:
    from domain import FutureChain, FutureContract

    fc = gw.future_chain("NIFTY", "NFO")
    check("future_chain() returns FutureChain", isinstance(fc, FutureChain))
    check(
        "future_chain has contracts",
        len(fc.contracts) > 0,
        f"{len(fc.contracts)} contracts, expiries={len(fc.expiries)}",
    )
except Exception as e:
    check("future_chain()", False, str(e)[:60])

# ── 6. BATCH METHODS ─────────────────────────────────────────────
print()
print("=" * 60)
print("6. BATCH METHODS (domain-typed returns)")
print("=" * 60)

# ltp_batch
ltp_b = gw.ltp_batch(["RELIANCE", "TCS"], "NSE")
check(
    "ltp_batch() → dict[str, Decimal]",
    isinstance(ltp_b, dict) and all(isinstance(v, Decimal) for v in ltp_b.values()),
    f"keys={list(ltp_b.keys())}",
)

# quote_batch
q_b = gw.quote_batch(["RELIANCE", "TCS"], "NSE")
check(
    "quote_batch() → dict[str, Quote]",
    isinstance(q_b, dict) and all(isinstance(v, Quote) for v in q_b.values()),
    f"keys={list(q_b.keys())}",
)

# history_batch
try:
    h_b = gw.history_batch(["RELIANCE", "TCS"], "NSE", timeframe="1D", lookback_days=5)
    check(
        "history_batch() → DataFrame",
        isinstance(h_b, pd.DataFrame) and len(h_b) > 0,
        f"{len(h_b)} rows",
    )
except Exception as e:
    check("history_batch()", False, str(e)[:60])

# ── 7. PORTFOLIO (domain objects) ────────────────────────────────
print()
print("=" * 60)
print("7. PORTFOLIO (domain-typed returns)")
print("=" * 60)
from domain import Holding, Position, Trade

positions = gw.positions()
check(
    "positions() → list[Position]",
    isinstance(positions, list) and all(isinstance(p, Position) for p in positions),
    f"{len(positions)} positions",
)

holdings = gw.holdings()
check(
    "holdings() → list[Holding]",
    isinstance(holdings, list) and all(isinstance(h, Holding) for h in holdings),
    f"{len(holdings)} holdings",
)

trades = gw.trades()
check(
    "trades() → list[Trade]",
    isinstance(trades, list) and all(isinstance(t, Trade) for t in trades),
    f"{len(trades)} trades",
)

# Verify Trade.timestamp is datetime, not string
if trades:
    from datetime import datetime

    t0 = trades[0]
    check(
        "Trade.timestamp is datetime|None",
        t0.timestamp is None or isinstance(t0.timestamp, datetime),
        f"type={type(t0.timestamp).__name__}",
    )

# ── 8. ORDERBOOK (domain objects) ────────────────────────────────
print()
print("=" * 60)
print("8. ORDER BOOK (domain-typed returns)")
print("=" * 60)
from domain import Order

ob = gw.get_orderbook()
check(
    "get_orderbook() → list[Order]",
    isinstance(ob, list) and all(isinstance(o, Order) for o in ob),
    f"{len(ob)} orders",
)

tb = gw.get_trade_book()
check(
    "get_trade_book() → list[Trade]",
    isinstance(tb, list) and all(isinstance(t, Trade) for t in tb),
    f"{len(tb)} trades",
)

# ── 9. CAPABILITIES + SEARCH ─────────────────────────────────────
print()
print("=" * 60)
print("9. LIFECYCLE (capabilities, describe, search)")
print("=" * 60)
from domain.capabilities.broker_capabilities import BrokerCapabilities

caps = gw.capabilities()
check("capabilities() → BrokerCapabilities", isinstance(caps, BrokerCapabilities))

search_results = gw.search("RELIANCE")
check(
    "search() → list[dict]",
    isinstance(search_results, list) and len(search_results) > 0,
    f"{len(search_results)} results",
)

# ── SUMMARY ──────────────────────────────────────────────────────
print()
print("=" * 60)
total = PASS + FAIL
print(f"SUMMARY: {PASS}/{total} passed, {FAIL} failed")
print("=" * 60)
if FAIL > 0:
    sys.exit(1)
