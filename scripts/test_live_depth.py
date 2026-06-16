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
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from brokers.common.event_bus import EventBus
from brokers.common.lifecycle import LifecycleManager
from brokers.dhan.factory import BrokerFactory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
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
    gateway = BrokerFactory.create(
        lifecycle=lifecycle,
        event_bus=event_bus,
    )

    logger.info(f"Gateway created: {gateway}")
    logger.info(f"Capabilities: depth_20={gateway.capabilities().depth_20}")

    # Start lifecycle (auto-starts WebSocket services)
    lifecycle.start_all()
    time.sleep(3)  # Allow WebSocket to connect

    # Check health
    health = lifecycle.health_snapshot()
    logger.info(f"Lifecycle health: {health}")

    # Try to get depth
    try:
        logger.info("Fetching 20-level depth for RELIANCE...")
        depth = gateway.depth_20("RELIANCE", "NSE")
        logger.info(f"Depth received: {depth.symbol if depth else 'None'}")
        if depth:
            logger.info(f"  Bids: {len(depth.bids) if depth.bids else 0}")
            logger.info(f"  Asks: {len(depth.asks) if depth.asks else 0}")
            logger.info(f"  Depth type: {depth.depth_type}")
    except Exception as exc:
        logger.error(f"Error fetching depth: {exc}", exc_info=True)

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
    gateway = BrokerFactory.create(
        lifecycle=lifecycle,
        event_bus=event_bus,
    )

    logger.info(f"Gateway created: {gateway}")
    logger.info(f"Capabilities: depth_200={gateway.capabilities().depth_200}")

    # Start lifecycle
    lifecycle.start_all()
    time.sleep(3)

    # Check health
    health = lifecycle.health_snapshot()
    logger.info(f"Lifecycle health: {health}")

    # Try to get depth
    try:
        logger.info("Fetching 200-level depth for RELIANCE...")
        depth = gateway.depth_200("RELIANCE", "NSE")
        logger.info(f"Depth received: {depth.symbol if depth else 'None'}")
        if depth:
            logger.info(f"  Bids: {len(depth.bids) if depth.bids else 0}")
            logger.info(f"  Asks: {len(depth.asks) if depth.asks else 0}")
            logger.info(f"  Depth type: {depth.depth_type}")
    except Exception as exc:
        logger.error(f"Error fetching depth: {exc}", exc_info=True)

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

    gateway = BrokerFactory.create()

    try:
        # Test LTP
        logger.info("Fetching LTP for RELIANCE...")
        ltp = gateway.ltp("RELIANCE", "NSE")
        logger.info(f"RELIANCE LTP: ₹{ltp}")

        # Test quote
        logger.info("Fetching quote for RELIANCE...")
        quote = gateway.quote("RELIANCE", "NSE")
        logger.info(f"Quote: LTP={quote.ltp}, Volume={quote.volume}")

        # Test depth (5-level)
        logger.info("Fetching 5-level depth for RELIANCE...")
        depth = gateway.depth("RELIANCE", "NSE")
        logger.info(f"Depth: {len(depth.bids)} bids, {len(depth.asks)} asks")

        # Test balance
        logger.info("Fetching account balance...")
        balance = gateway.portfolio.get_balance()
        logger.info(f"Available balance: ₹{balance.available_balance}")

        logger.info("✅ Basic connection test PASSED")

    except Exception as exc:
        logger.error(f"❌ Basic connection test FAILED: {exc}", exc_info=True)
    finally:
        gateway.close()


if __name__ == "__main__":
    # Load environment
    env_file = project_root / ".env.local"
    if env_file.exists():
        load_dotenv(env_file)
        logger.info(f"Loaded .env.local")

    # Check credentials
    client_id = os.getenv("DHAN_CLIENT_ID")
    access_token = os.getenv("DHAN_ACCESS_TOKEN")

    if not client_id or not access_token:
        logger.error("DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN must be set")
        logger.error("Add them to .env.local or export as environment variables")
        sys.exit(1)

    logger.info(f"Client ID: {client_id}")
    logger.info(f"Access token: {access_token[:20]}...")

    # Run tests
    try:
        test_basic_connection()
        # Test depth WebSockets:
        test_depth_20_live()
        # test_depth_200_live()
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    except Exception as exc:
        logger.error(f"Test failed: {exc}", exc_info=True)
        sys.exit(1)
