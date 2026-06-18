"""Live market feed (full mode) and market depth verification for NSE and NFO.

Tests:
1. WebSocket streaming in FULL/QUOTE mode — verifies live ticks arrive
2. depth_20 (20-level WebSocket depth) — verifies depth data arrives
3. depth_200 (200-level WebSocket depth) — verifies depth data arrives
4. REST depth (5-level) — baseline comparison
"""
import sys
import os
import time
import threading
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = "PASS"
FAIL = "FAIL"
results: list[tuple[str, str, str, str]] = []

def record(test: str, segment: str, status: str, detail: str = ""):
    results.append((test, segment, status, detail))
    icon = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭️"}[status]
    print(f"  {icon} {test:30s} [{segment:8s}] {detail[:90]}")


def test_live_feed_and_depth():
    from brokers.dhan.factory import BrokerFactory

    print("=== Creating Dhan Gateway ===")
    factory = BrokerFactory()
    gw = factory.create(load_instruments=True)
    conn = gw._conn
    print(f"Instruments: {conn.instruments.stats().get('total', '?')}")

    # ── Instruments to test ──────────────────────────────────────────────
    instruments = []

    # NSE Equity
    for sym in ["RELIANCE", "TCS", "HDFCBANK"]:
        inst = conn.instruments.resolve(sym, "NSE")
        instruments.append(("NSE", sym, inst))

    # NSE Index
    inst = conn.instruments.resolve("NIFTY", "IDX_I")
    instruments.append(("IDX_I", "NIFTY", inst))

    # NFO Futures — nearest NIFTY future
    nfo_futs = conn.instruments.get_futures("NIFTY", "NFO")
    from datetime import date
    today = str(date.today())
    active_futs = [f for f in nfo_futs if f.expiry and f.expiry >= today]
    if active_futs:
        fut = active_futs[0]
        instruments.append(("NFO", f"NIFTY FUT ({fut.expiry})", fut))

    # NFO Options — nearest NIFTY CE option (near ATM)
    try:
        # Get nearest expiry option
        from brokers.dhan.extended import DhanExtendedCapabilities
        ext = DhanExtendedCapabilities(conn)
        expiries = ext.get_option_expiries("NIFTY", "NFO")
        if expiries:
            nearest_exp = expiries[0]
            chain = ext.get_option_chain("NIFTY", "NFO", nearest_exp)
            if chain:
                # Find a near-ATM CE option
                ces = [c for c in chain if c.get("option_type", "").upper() in ("CE", "CALL")]
                if ces:
                    opt_sid = str(ces[0].get("security_id", ""))
                    opt_inst = conn.instruments.get_by_security_id(opt_sid)
                    if opt_inst:
                        instruments.append(("NFO", f"NIFTY CE ({nearest_exp})", opt_inst))
    except Exception as e:
        print(f"  ⚠️ Could not resolve NFO option: {e}")

    print(f"\n=== Testing {len(instruments)} instruments ===\n")

    # ── 1. REST Depth (5-level baseline) ─────────────────────────────────
    print("=== REST Depth (5-level) ===")
    for segment, label, inst in instruments:
        try:
            d = gw.depth(inst.symbol if segment != "IDX_I" else "NIFTY", segment)
            bids = len(d.bids) if d and hasattr(d, 'bids') else 0
            asks = len(d.asks) if d and hasattr(d, 'asks') else 0
            if bids > 0 and asks > 0:
                record("REST depth (5-level)", segment, PASS,
                       f"{label}: {bids} bids, {asks} asks, top_bid={d.bids[0].price if d.bids else 'N/A'}")
            else:
                record("REST depth (5-level)", segment, FAIL, f"{label}: bids={bids}, asks={asks}")
        except Exception as e:
            record("REST depth (5-level)", segment, FAIL, f"{label}: {type(e).__name__}: {e}")
        time.sleep(0.25)

    # ── 2. Live Stream FULL mode ─────────────────────────────────────────
    print("\n=== Live Stream (FULL mode) — 10 second capture ===")
    ticks_received: dict[str, list] = {}
    tick_lock = threading.Lock()

    def on_tick_factory(seg_label):
        def on_tick(data):
            with tick_lock:
                ticks_received.setdefault(seg_label, []).append(data)
        return on_tick

    feeds = []
    for segment, label, inst in instruments:
        try:
            sym = inst.symbol if segment != "IDX_I" else "NIFTY"
            feed = gw.stream(sym, segment, mode="FULL", on_tick=on_tick_factory(label))
            feeds.append((label, feed))
            record("Stream FULL subscribe", segment, PASS, f"{label}: subscribed")
        except Exception as e:
            record("Stream FULL subscribe", segment, FAIL, f"{label}: {type(e).__name__}: {e}")
        time.sleep(0.15)

    # Wait for ticks to arrive
    print("  ⏳ Waiting 10 seconds for live ticks...")
    time.sleep(10)

    # Check results
    for segment, label, inst in instruments:
        with tick_lock:
            ticks = ticks_received.get(label, [])
        if ticks:
            sample = ticks[0]
            ltp = sample.get("ltp", "?") if isinstance(sample, dict) else getattr(sample, "ltp", "?")
            record("Stream FULL ticks", segment, PASS,
                   f"{label}: {len(ticks)} ticks, LTP={ltp}")
        else:
            record("Stream FULL ticks", segment, FAIL, f"{label}: 0 ticks in 10s")

    # ── 3. Depth 20 (WebSocket) ──────────────────────────────────────────
    print("\n=== Depth 20 (WebSocket) — 8 second capture ===")
    depth_20_results: dict[str, list] = {}
    depth_20_lock = threading.Lock()

    def on_depth_20_factory(seg_label):
        def on_depth(d):
            with depth_20_lock:
                depth_20_results.setdefault(seg_label, []).append(d)
        return on_depth

    depth_20_instruments = [
        (seg, label, inst) for seg, label, inst in instruments
        if seg in ("NSE", "IDX_I", "NFO")
    ]

    for segment, label, inst in depth_20_instruments:
        try:
            sym = inst.symbol if segment != "IDX_I" else "NIFTY"
            d = gw.depth_20(sym, segment, on_depth=on_depth_20_factory(label))
            bids = len(d.bids) if d and hasattr(d, 'bids') else 0
            asks = len(d.asks) if d and hasattr(d, 'asks') else 0
            record("Depth 20 initial", segment, PASS if bids > 0 else FAIL,
                   f"{label}: {bids} bids, {asks} asks (REST fallback)")
        except Exception as e:
            record("Depth 20 initial", segment, FAIL, f"{label}: {type(e).__name__}: {e}")
        time.sleep(0.15)

    print("  ⏳ Waiting 8 seconds for depth updates...")
    time.sleep(8)

    for segment, label, inst in depth_20_instruments:
        with depth_20_lock:
            updates = depth_20_results.get(label, [])
        if updates:
            last = updates[-1]
            bids = len(last.bids) if hasattr(last, 'bids') else 0
            asks = len(last.asks) if hasattr(last, 'asks') else 0
            record("Depth 20 live updates", segment, PASS if bids > 0 else FAIL,
                   f"{label}: {len(updates)} updates, last: {bids} bids, {asks} asks")
        else:
            record("Depth 20 live updates", segment, FAIL, f"{label}: 0 WS updates in 8s")

    # ── 4. Depth 200 (WebSocket) — NSE only ──────────────────────────────
    print("\n=== Depth 200 (WebSocket) — 8 second capture ===")
    depth_200_results: dict[str, list] = {}
    depth_200_lock = threading.Lock()

    def on_depth_200_factory(seg_label):
        def on_depth(d):
            with depth_200_lock:
                depth_200_results.setdefault(seg_label, []).append(d)
        return on_depth

    # Depth 200 allows only ONE instrument per connection
    nse_inst = next((i for s, l, i in instruments if s == "NSE"), None)
    if nse_inst:
        try:
            d = gw.depth_200(nse_inst.symbol, "NSE", on_depth=on_depth_200_factory(nse_inst.symbol))
            bids = len(d.bids) if d and hasattr(d, 'bids') else 0
            asks = len(d.asks) if d and hasattr(d, 'asks') else 0
            record("Depth 200 initial", "NSE", PASS if bids > 0 else FAIL,
                   f"{nse_inst.symbol}: {bids} bids, {asks} asks (REST fallback)")
        except Exception as e:
            record("Depth 200 initial", "NSE", FAIL, f"{nse_inst.symbol}: {type(e).__name__}: {e}")

        print("  ⏳ Waiting 8 seconds for depth-200 updates...")
        time.sleep(8)

        with depth_200_lock:
            updates = depth_200_results.get(nse_inst.symbol, [])
        if updates:
            last = updates[-1]
            bids = len(last.bids) if hasattr(last, 'bids') else 0
            asks = len(last.asks) if hasattr(last, 'asks') else 0
            record("Depth 200 live updates", "NSE", PASS if bids > 0 else FAIL,
                   f"{nse_inst.symbol}: {len(updates)} updates, last: {bids} bids, {asks} asks")
        else:
            record("Depth 200 live updates", "NSE", FAIL, f"{nse_inst.symbol}: 0 WS updates in 8s")

    return gw


if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  LIVE MARKET FEED & DEPTH VERIFICATION — NSE + NFO         ║")
    print("║  Full mode streaming + Depth 5/20/200 across segments      ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    gw = None
    try:
        gw = test_live_feed_and_depth()
    except Exception as e:
        print(f"\n💥 FATAL: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if gw:
            try:
                gw._conn.close()
            except Exception:
                pass

    # ── Summary ──────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    passed = sum(1 for r in results if r[2] == PASS)
    failed = sum(1 for r in results if r[2] == FAIL)
    total = len(results)
    print(f"  Total: {total}  |  PASS: {passed}  |  FAIL: {failed}")
    print()

    if failed:
        print("FAILURES:")
        for test, segment, status, detail in results:
            if status == FAIL:
                print(f"  ❌ {test:30s} [{segment}] {detail[:100]}")

    print(f"\nResult: {'ALL PASS' if failed == 0 else f'{failed} FAILURES'}")
