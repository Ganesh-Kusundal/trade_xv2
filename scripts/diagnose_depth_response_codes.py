#!/usr/bin/env python3
"""Diagnostic: Log raw response codes from depth-20 WebSocket for TCS on NSE.

This script patches the depth feed to log every binary packet's response code
to determine if ask packets (response_code=51) are arriving at all.
"""

from __future__ import annotations

import logging
import struct
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("diag_depth")

# Patch the depth feed to log response codes
from brokers.dhan.depth_feed_base import BinaryDepthFeed

_original_process = BinaryDepthFeed._process_binary_message

response_codes_seen: dict[int, int] = {}  # response_code -> count

def _patched_process(self, data: bytes) -> None:
    if len(data) >= 3:
        rc = data[2]
        response_codes_seen[rc] = response_codes_seen.get(rc, 0) + 1
        if response_codes_seen[rc] <= 3:  # Log first 3 of each type
            log.info("DEPTH PACKET: response_code=%d, len=%d bytes", rc, len(data))
    _original_process(self, data)

BinaryDepthFeed._process_binary_message = _patched_process


def main():
    from cli.services.broker_registry import bootstrap_gateway

    result = bootstrap_gateway("dhan")
    if not result.ok:
        log.error("Bootstrap failed: %s", result.error)
        sys.exit(1)

    gw = result.gateway
    log.info("Bootstrap OK")

    # Resolve TCS
    inst = gw._conn.instruments.resolve("TCS", "NSE")
    log.info("TCS: security_id=%s", inst.security_id)

    depths: list = []

    def on_depth(depth):
        depths.append(depth)
        log.info("DEPTH UPDATE: bids=%d, asks=%d, type=%s",
                 len(depth.bids), len(depth.asks), depth.depth_type)
        if depth.bids:
            log.info("  Best bid: %s x %s", depth.bids[0].price, depth.bids[0].quantity)
        if depth.asks:
            log.info("  Best ask: %s x %s", depth.asks[0].price, depth.asks[0].quantity)

    # Call depth_20 with callback
    log.info("Calling gw.depth_20('TCS', 'NSE', on_depth=...)")
    depth = gw.depth_20("TCS", "NSE", on_depth=on_depth)
    log.info("Initial depth: type=%s, bids=%d, asks=%d",
             depth.depth_type, len(depth.bids), len(depth.asks))

    # Wait for WebSocket depth updates
    log.info("Waiting 15 seconds for depth updates...")
    for _i in range(15):
        time.sleep(1)
        if depths and len(depths) >= 5:
            break

    log.info("Response codes seen: %s", response_codes_seen)
    log.info("Total depth updates: %d", len(depths))

    # Check if we got ask packets (response_code=51)
    if 51 in response_codes_seen:
        log.info("ASK PACKETS RECEIVED: count=%d", response_codes_seen[51])
    else:
        log.warning("NO ASK PACKETS RECEIVED! Only response codes: %s", list(response_codes_seen.keys()))

    # Cleanup
    try:
        feed = gw._conn.depth_20_feed
        if feed:
            feed.stop(timeout_seconds=3)
    except Exception:
        pass
    try:
        gw.close()
    except Exception:
        pass


if __name__ == "__main__":
    main()
