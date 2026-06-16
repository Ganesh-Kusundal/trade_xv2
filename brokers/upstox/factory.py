"""UpstoxBrokerFactory — creates configured UpstoxBrokerGateway instances."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable, Optional

from brokers.common.env_loader import load_env_file
from brokers.common.event_bus import EventBus
from brokers.common.instrument_cache import InstrumentCacheManager
from brokers.common.oms.risk_manager import RiskManager
from brokers.common.symbol_resolver import SymbolResolutionInterceptor
from brokers.upstox.auth.config import UpstoxConnectionSettings
from brokers.upstox.broker import UpstoxBroker
from brokers.upstox.gateway import UpstoxBrokerGateway
from brokers.upstox.instruments.cache_adapter import UpstoxInstrumentAdapter

logger = logging.getLogger(__name__)


class UpstoxBrokerFactory:
    @staticmethod
    def create(
        env_path: Optional[Path] = None,
        load_instruments: bool = True,
        analytics_only: bool = False,
        event_bus: Optional[EventBus] = None,
        risk_manager: Optional[RiskManager] = None,
        backfill_callback: Callable[[list[str], Any, Any], list[dict]] | None = None,
        reconciliation_service: Any | None = None,
    ) -> UpstoxBrokerGateway:
        env_file = env_path or Path(".env.local")
        if env_file.exists():
            load_env_file(env_file)

        client_id = os.environ.get("UPSTOX_API_KEY", "")
        client_secret = os.environ.get("UPSTOX_API_SECRET", "")
        access_token = os.environ.get("UPSTOX_ACCESS_TOKEN", "")
        environment = os.environ.get("UPSTOX_ENVIRONMENT", "live")
        redirect_uri = os.environ.get("UPSTOX_REDIRECT_URI", "http://127.0.0.1:18080/callback")

        if not client_id:
            from brokers.upstox.auth.exceptions import UpstoxAuthError
            raise UpstoxAuthError("UPSTOX_API_KEY not configured")

        analytics_only_str = os.environ.get("UPSTOX_ANALYTICS_ONLY", "false")
        analytics_only = analytics_only_str.lower() == "true" or analytics_only

        settings = UpstoxConnectionSettings(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            access_token=access_token,
            environment=environment.upper(),
            analytics_only=analytics_only,
        )

        broker = UpstoxBroker(
            settings=settings,
            event_bus=event_bus,
            risk_manager=risk_manager,
            backfill_callback=backfill_callback,
            reconciliation_service=reconciliation_service,
        )
        broker.connect()

        # Set up SQLite instrument cache with lazy refresh
        cache_db = Path(".cache/instruments.db")
        cache_mgr = InstrumentCacheManager(db_path=cache_db)
        adapter = UpstoxInstrumentAdapter(db_path=cache_db)
        cache_mgr.register_adapter(adapter)
        
        # Register loader for transparent lazy refresh
        # The loader downloads from Upstox CDN if cache is stale, then parses
        def load_upstox_instruments():
            cache_path = Path(".cache/upstox/complete.json.gz")
            if cache_path.exists():
                path = cache_path
            else:
                path = broker.instrument_loader.download(cache_path)
            return broker.instrument_loader.load(path)
        
        cache_mgr.register_loader("upstox", load_upstox_instruments)
        
        # Create symbol resolution interceptor
        symbol_interceptor = SymbolResolutionInterceptor(cache_mgr)
        broker.symbol_interceptor = symbol_interceptor
        broker.instrument_cache = cache_mgr

        gateway = UpstoxBrokerGateway(broker)

        if load_instruments:
            try:
                # Trigger lazy refresh on first call
                # This will populate SQLite cache if expired
                gateway.load_instruments()
            except Exception as e:
                logger.warning("Failed to load Upstox instruments: %s", e)

        return gateway


