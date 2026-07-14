#!/usr/bin/env python
"""Live market test for Dhan depth 20/200 WebSocket feeds.

Tests real WebSocket connections to Dhan depth APIs.
Requires valid Dhan credentials in .env.local or environment variables.

Usage:
    python scripts/test_live_depth.py
"""

import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "scripts"))
from _connect import bootstrap_or_exit
from infrastructure.event_bus import EventBus
from infrastructure.lifecycle import LifecycleManager
from infrastructure.logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


def test_depth_20_live():
    """Test 20-level depth WebSocket with real connection."""
    logger.info("=" * 60)
    logger.info("TESTING DEPTH 20 LIVE WEBSOCKET")
    logger.info("=" * 60)

    # Create lifecycle and event bus
    lifecycle = LifecycleManager()
    event_bus = EventBus()

    # Create gateway from factory
    gateway = bootstrap_or_exit(
        "dhan",
        lifecycle=lifecycle,
        event_bus=event_bus,
    )

    logger.info("Gateway created: %s", gateway)
    logger.info("Capabilities: depth_20=%s", gateway.capabilities().depth_20)

    # Start lifecycle (auto-starts WebSocket services)
    lifecycle.start_all()
    time.sleep(3)  # Allow WebSocket to connect

    # Check health
    health = lifecycle.health_snapshot()
    logger.info("Lifecycle health: %s", health)

    # Try to get depth
    try:
        logger.info("Fetching 20-level depth for RELIANCE...")
        depth = gateway.depth_20("RELIANCE", "NSE")
        logger.info("Depth received: %s", depth.symbol if depth else "None")
        if depth:
            logger.info("  Bids: %s", len(depth.bids) if depth.bids else 0)
            logger.info("  Asks: %s", len(depth.asks) if depth.asks else 0)
            logger.info("  Depth type: %s", depth.depth_type)
    except Exception as exc:
        logger.exception("Error fetching depth: %s", exc)

    # Wait for some messages
    logger.info("Waiting 10 seconds for depth updates...")
    time.sleep(10)

    # Stop
    lifecycle.stop_all()
    logger.info("Depth 20 test complete")


def test_depth_200_live():
    """Test 200-level depth WebSocket with real connection."""
    logger.info("=" * 60)
    logger.info("TESTING DEPTH 200 LIVE WEBSOCKET")
    logger.info("=" * 60)

    # Create lifecycle and event bus
    lifecycle = LifecycleManager()
    event_bus = EventBus()

    # Create gateway from factory
    gateway = bootstrap_or_exit(
        "dhan",
        lifecycle=lifecycle,
        event_bus=event_bus,
    )

    logger.info("Gateway created: %s", gateway)
    logger.info("Capabilities: depth_200=%s", gateway.capabilities().depth_200)

    # Start lifecycle
    lifecycle.start_all()
    time.sleep(3)

    # Check health
    health = lifecycle.health_snapshot()
    logger.info("Lifecycle health: %s", health)

    # Try to get depth
    try:
        logger.info("Fetching 200-level depth for RELIANCE...")
        depth = gateway.depth_200("RELIANCE", "NSE")
        logger.info("Depth received: %s", depth.symbol if depth else "None")
        if depth:
            logger.info("  Bids: %s", len(depth.bids) if depth.bids else 0)
            logger.info("  Asks: %s", len(depth.asks) if depth.asks else 0)
            logger.info("  Depth type: %s", depth.depth_type)
    except Exception as exc:
        logger.exception("Error fetching depth: %s", exc)

    # Wait for some messages
    logger.info("Waiting 10 seconds for depth updates...")
    time.sleep(10)

    # Stop
    lifecycle.stop_all()
    logger.info("Depth 200 test complete")


def test_basic_connection():
    """Test basic Dhan connection and REST API."""
    logger.info("=" * 60)
    logger.info("TESTING BASIC DHAN CONNECTION")
    logger.info("=" * 60)

    gateway = bootstrap_or_exit("dhan", load_instruments=True)

    try:
        # Test LTP
        logger.info("Fetching LTP for RELIANCE...")
        ltp = gateway.ltp("RELIANCE", "NSE")
        logger.info("RELIANCE LTP: %s", ltp)

        # Test quote
        logger.info("Fetching quote for RELIANCE...")
        quote = gateway.quote("RELIANCE", "NSE")
        logger.info("Quote: LTP=%s, Volume=%s", quote.ltp, quote.volume)

        # Test depth (5-level)
        logger.info("Fetching 5-level depth for RELIANCE...")
        depth = gateway.depth("RELIANCE", "NSE")
        logger.info("Depth: %s bids, %s asks", len(depth.bids), len(depth.asks))

        # Test balance
        logger.info("Fetching account balance...")
        balance = gateway.funds()
        logger.info("Available balance: %s", balance.available_balance)

        logger.info("Basic connection test PASSED")

    except Exception as exc:
        logger.exception("Basic connection test FAILED: %s", exc)
    finally:
        gateway.close()


if __name__ == "__main__":
    # Load environment
    env_file = project_root / ".env.local"
    if env_file.exists():
        load_dotenv(env_file)
        logger.info("Loaded .env.local")

    # Check credentials
    client_id = os.getenv("DHAN_CLIENT_ID")
    access_token = os.getenv("DHAN_ACCESS_TOKEN")

    if not client_id or not access_token:
        logger.error("DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN must be set")
        logger.error("Add them to .env.local or export as environment variables")
        sys.exit(1)

    # NEVER log credentials or token prefixes — only confirm presence.
    # CWE-532: insertion of sensitive info into log file.
    logger.info("DHAN credentials present (DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN set)")

    # Run tests
    try:
        test_basic_connection()
        # Test depth WebSockets:
        test_depth_20_live()
        # test_depth_200_live()
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    except Exception as exc:
        logger.exception("Test failed: %s", exc)
        sys.exit(1)
