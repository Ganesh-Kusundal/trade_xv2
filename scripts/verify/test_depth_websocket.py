#!/usr/bin/env python
"""Test depth 20/200 WebSocket feeds with real Dhan connection."""

import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from brokers.dhan.identity.factory import BrokerFactory
from infrastructure.event_bus import EventBus
from infrastructure.lifecycle import LifecycleManager
from infrastructure.logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


def test_depth_20_websocket():
    """Test 20-level depth WebSocket with real connection."""
    logger.info("=" * 60)
    logger.info("TESTING DEPTH 20 WEBSOCKET (NSE ONLY)")
    logger.info("=" * 60)

    lifecycle = LifecycleManager()
    event_bus = EventBus()

    gateway = BrokerFactory().create(
        lifecycle=lifecycle,
        event_bus=event_bus,
    )

    logger.info("Capabilities: depth_20=%s", gateway.capabilities().depth_20)

    # Start lifecycle
    lifecycle.start_all()
    time.sleep(2)

    try:
        # Test NSE equity
        logger.info("\nFetching 20-level depth for RELIANCE (NSE_EQ)...")
        depth = gateway.depth_20("RELIANCE", "NSE_EQ")
        logger.info("Depth received: %s", depth.symbol)
        logger.info("   Bids: %s", len(depth.bids) if depth.bids else 0)
        logger.info("   Asks: %s", len(depth.asks) if depth.asks else 0)
        logger.info("   Depth type: %s", depth.depth_type)

        # Test NSE F&O
        logger.info("\nFetching 20-level depth for NIFTY (NSE_FNO)...")
        depth = gateway.depth_20("NIFTY", "NFO")
        logger.info("Depth received: %s", depth.symbol)
        logger.info("   Depth type: %s", depth.depth_type)

        # Test invalid exchange (should raise error)
        logger.info("\nTesting invalid exchange (BSE)...")
        try:
            depth = gateway.depth_20("RELIANCE", "BSE")
            logger.error("Should have raised ValueError for BSE")
        except ValueError as e:
            logger.info("Correctly rejected: %s", e)

        # Wait for WebSocket messages
        logger.info("\nWaiting 5 seconds for depth updates...")
        time.sleep(5)

        # Check health
        health = lifecycle.health_snapshot()
        logger.info("\nLifecycle health: %s", health)

    except Exception as exc:
        logger.exception("Test failed: %s", exc)
    finally:
        lifecycle.stop_all()
        gateway.close()


def test_depth_200_websocket():
    """Test 200-level depth WebSocket with real connection."""
    logger.info("=" * 60)
    logger.info("TESTING DEPTH 200 WEBSOCKET (NSE ONLY, 1 INSTRUMENT)")
    logger.info("=" * 60)

    lifecycle = LifecycleManager()
    event_bus = EventBus()

    gateway = BrokerFactory().create(
        lifecycle=lifecycle,
        event_bus=event_bus,
    )

    logger.info("Capabilities: depth_200=%s", gateway.capabilities().depth_200)

    # Start lifecycle
    lifecycle.start_all()
    time.sleep(2)

    try:
        # Test NSE equity
        logger.info("\nFetching 200-level depth for RELIANCE (NSE_EQ)...")
        depth = gateway.depth_200("RELIANCE", "NSE_EQ")
        logger.info("Depth received: %s", depth.symbol)
        logger.info("   Bids: %s", len(depth.bids) if depth.bids else 0)
        logger.info("   Asks: %s", len(depth.asks) if depth.asks else 0)
        logger.info("   Depth type: %s", depth.depth_type)

        # Test invalid exchange
        logger.info("\nTesting invalid exchange (MCX)...")
        try:
            depth = gateway.depth_200("CRUDEOIL", "MCX")
            logger.error("Should have raised ValueError for MCX")
        except ValueError as e:
            logger.info("Correctly rejected: %s", e)

        # Wait for WebSocket messages
        logger.info("\nWaiting 5 seconds for depth updates...")
        time.sleep(5)

        # Check health
        health = lifecycle.health_snapshot()
        logger.info("\nLifecycle health: %s", health)

    except Exception as exc:
        logger.exception("Test failed: %s", exc)
    finally:
        lifecycle.stop_all()
        gateway.close()


if __name__ == "__main__":
    env_file = project_root / ".env.local"
    if env_file.exists():
        load_dotenv(env_file)

    client_id = os.getenv("DHAN_CLIENT_ID")
    access_token = os.getenv("DHAN_ACCESS_TOKEN")

    if not client_id or not access_token:
        logger.error("DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN must be set")
        sys.exit(1)

    logger.info("Client ID: %s", client_id)

    try:
        # Test both depth feeds
        test_depth_20_websocket()
        test_depth_200_websocket()
    except KeyboardInterrupt:
        logger.info("Test interrupted")
    except Exception as exc:
        logger.exception("Test failed: %s", exc)
        sys.exit(1)
