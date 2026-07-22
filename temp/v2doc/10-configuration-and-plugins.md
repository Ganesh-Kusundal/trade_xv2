# 10 — Configuration & Plugins

## 1. Overview

TradeXV2 uses a declarative configuration system where YAML files define
component assembly, and plugins are discovered via Python entry points.

```
┌─────────────────────────────────────────────────────────────┐
│                    ConfigManager                            │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  YAML        │  │  Environment │  │  Plugin          │  │
│  │  Files       │  │  Variables   │  │  Discovery       │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         │                 │                    │            │
│         └─────────────────┼────────────────────┘            │
│                           │                                 │
│                    ┌──────▼───────┐                         │
│                    │  Component   │                         │
│                    │  Factory     │                         │
│                    └──────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

## 2. Configuration Hierarchy

Configuration is resolved in this order (later overrides earlier):

1. **Defaults** — Built-in defaults in code
2. **YAML files** — `config/tradex.yaml`
3. **Profile overrides** — `config/profiles/{profile}.yaml`
4. **Environment variables** — `TRADEX_*` prefix
5. **CLI arguments** — `--config key=value`

```python
# runtime/config/config_manager.py

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml


class ConfigManager:
    """
    Hierarchical configuration manager.

    Merges defaults, YAML files, environment variables, and CLI overrides.
    """

    def __init__(self, config_dir: Path = Path("config")) -> None:
        self._config_dir = config_dir
        self._config: dict = {}

    def load(
        self,
        profile: str = "default",
        overrides: Optional[dict] = None,
    ) -> dict:
        """Load configuration with hierarchy."""
        # 1. Load base config
        base_path = self._config_dir / "tradex.yaml"
        if base_path.exists():
            with open(base_path) as f:
                self._config = yaml.safe_load(f) or {}

        # 2. Load profile override
        profile_path = self._config_dir / "profiles" / f"{profile}.yaml"
        if profile_path.exists():
            with open(profile_path) as f:
                profile_config = yaml.safe_load(f) or {}
                self._config = self._deep_merge(self._config, profile_config)

        # 3. Apply environment variables
        self._apply_env_overrides()

        # 4. Apply CLI overrides
        if overrides:
            self._config = self._deep_merge(self._config, overrides)

        return self._config

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value by dot-notation key."""
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        return value

    def _apply_env_overrides(self) -> None:
        """Apply TRADEX_* environment variables."""
        prefix = "TRADEX_"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                config_key = key[len(prefix):].lower().replace("__", ".")
                self._set_nested(config_key, value)

    def _set_nested(self, key: str, value: Any) -> None:
        """Set a nested config value."""
        keys = key.split(".")
        d = self._config
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = value

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """Deep merge two dicts."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
```

## 3. Example Configuration

```yaml
# config/tradex.yaml

# ── Application ──────────────────────────────────────────────
app:
  name: "TradeXV2"
  mode: "paper"  # backtest | paper | live
  log_level: "INFO"
  log_format: "json"  # json | console

# ── Broker ───────────────────────────────────────────────────
broker:
  id: "dhan"
  config:
    api_url: "https://api.dhan.co/v2"
    access_token: "${DHAN_ACCESS_TOKEN}"
    client_id: "${DHAN_CLIENT_ID}"

# ── Risk ─────────────────────────────────────────────────────
risk:
  initial_capital: 1000000
  max_position_qty: 1000
  max_order_qty: 500
  max_daily_loss: 50000
  max_drawdown_pct: 5
  max_orders_per_minute: 60

# ── Data ─────────────────────────────────────────────────────
data:
  datalake_path: "./datalake"
  prefer_local: true
  sync_enabled: true
  sync_schedule: "0 6 * * *"  # Daily at 6 AM

# ── Strategy ─────────────────────────────────────────────────
strategy:
  id: "momentum_01"
  class: "strategies.momentum_strategy:MomentumStrategy"
  params:
    lookback: 20
    exit_lookback: 10
    quantity: 10

# ── Symbols ──────────────────────────────────────────────────
symbols:
  - symbol: "RELIANCE"
    exchange: "NSE"
  - symbol: "TCS"
    exchange: "NSE"
  - symbol: "NIFTY"
    exchange: "NSE"

# ── Observability ────────────────────────────────────────────
observability:
  metrics_enabled: true
  metrics_port: 9090
  health_check_interval: 30
```

## 4. Profile Overrides

```yaml
# config/profiles/backtest.yaml

app:
  mode: "backtest"

data:
  prefer_local: true
  sync_enabled: false

backtest:
  start: "2024-01-01"
  end: "2024-12-31"
  initial_capital: 1000000
  slippage_bps: 5
```

```yaml
# config/profiles/live.yaml

app:
  mode: "live"
  log_level: "WARNING"

broker:
  id: "dhan"
  config:
    api_url: "https://api.dhan.co/v2"

risk:
  max_daily_loss: 25000  # Tighter for live
```

## 5. Plugin Discovery

### 5.1 Entry Points

```toml
# pyproject.toml

[project.entry-points."tradex.brokers"]
dhan = "brokers.dhan:create_plugin"
upstox = "brokers.upstox:create_plugin"
paper = "brokers.paper:create_plugin"

[project.entry-points."tradex.exchanges"]
nse = "exchanges.nse:create_plugin"
bse = "exchanges.bse:create_plugin"
mcx = "exchanges.mcx:create_plugin"
```

### 5.2 Plugin Registry

```python
# runtime/composition/plugin_registry.py

from __future__ import annotations

import importlib.metadata
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class BrokerPlugin:
    broker_id: str
    env_file: str
    default_mode: str
    supported_modes: frozenset
    is_live: bool
    gateway_class: type
    capabilities_loader: Callable


class PluginRegistry:
    """Discover and register broker plugins via entry points."""

    def __init__(self) -> None:
        self._brokers: dict[str, BrokerPlugin] = {}

    def discover(self) -> None:
        """Discover all registered broker plugins."""
        eps = importlib.metadata.entry_points()
        broker_eps = eps.get("tradex.brokers", [])

        for ep in broker_eps:
            try:
                create_plugin = ep.load()
                plugin = create_plugin()
                self._brokers[plugin.broker_id] = plugin
            except Exception as exc:
                logger.warning("Failed to load broker plugin %s: %s", ep.name, exc)

    def get(self, broker_id: str) -> BrokerPlugin:
        if broker_id not in self._brokers:
            raise ValueError(f"Unknown broker: {broker_id}")
        return self._brokers[broker_id]

    def list_brokers(self) -> list[str]:
        return list(self._brokers.keys())
```

## 6. Component Factory

```python
# runtime/composition/component_factory.py

from __future__ import annotations

import importlib
import logging
from typing import Any

from application.execution.execution_engine import ExecutionEngine
from application.execution.fill_sources.broker import BrokerFillSource
from application.execution.fill_sources.paper import PaperFillSource
from application.execution.fill_sources.simulated import SimulatedFillSource
from application.oms.order_manager import OrderManager
from application.oms.position_manager import PositionManager
from application.risk.risk_manager import RiskManager, RiskConfig
from runtime.composition.plugin_registry import PluginRegistry
from shared.messaging.message_bus import MessageBus


logger = logging.getLogger(__name__)


class ComponentFactory:
    """
    Creates and wires components based on configuration.

    This is the composition root — the only place that knows about all layers.
    """

    def __init__(self, config: dict) -> None:
        self._config = config
        self._plugins = PluginRegistry()
        self._plugins.discover()

    def create_trading_context(self):
        """Create a fully wired TradingContext."""
        mode = self._config["app"]["mode"]

        # 1. Create MessageBus
        bus = MessageBus()

        # 2. Create broker gateway
        broker_id = self._config["broker"]["id"]
        plugin = self._plugins.get(broker_id)
        gateway = plugin.gateway_class(self._config["broker"]["config"])

        # 3. Create FillSource based on mode
        if mode == "backtest":
            fill_source = SimulatedFillSource(
                slippage_bps=self._config.get("backtest", {}).get("slippage_bps", 5),
            )
        elif mode == "paper":
            fill_source = PaperFillSource(
                quote_fn=gateway.get_quote,
                slippage_bps=2.0,
            )
        elif mode == "live":
            fill_source = BrokerFillSource(gateway)
        else:
            raise ValueError(f"Unknown mode: {mode}")

        # 4. Create risk manager
        risk_config = RiskConfig(
            max_position_qty=self._config["risk"]["max_position_qty"],
            max_order_qty=self._config["risk"]["max_order_qty"],
            max_daily_loss=self._config["risk"]["max_daily_loss"],
        )
        risk_manager = RiskManager(
            bus=bus,
            initial_capital=self._config["risk"]["initial_capital"],
            config=risk_config,
        )

        # 5. Create managers
        order_manager = OrderManager(bus)
        position_manager = PositionManager(bus)

        # 6. Create execution engine
        execution_engine = ExecutionEngine(
            bus=bus,
            fill_source=fill_source,
            risk_manager=risk_manager,
            order_manager=order_manager,
            position_manager=position_manager,
        )

        # 7. Initialize
        execution_engine.initialize()
        execution_engine.start()

        return TradingContext(
            event_bus=bus,
            execution_engine=execution_engine,
            order_manager=order_manager,
            position_manager=position_manager,
            risk_manager=risk_manager,
            fill_source=fill_source,
            mode=mode,
        )

    def create_strategy(self, bus):
        """Create strategy instance from config."""
        strategy_config = self._config["strategy"]
        class_path = strategy_config["class"]
        module_path, class_name = class_path.split(":")
        module = importlib.import_module(module_path)
        strategy_class = getattr(module, class_name)
        return strategy_class(
            strategy_id=strategy_config["id"],
            bus=bus,
            **strategy_config.get("params", {}),
        )
```

## 7. Bootstrap

```python
# runtime/bootstrap.py

from __future__ import annotations

import logging
from pathlib import Path

from runtime.config.config_manager import ConfigManager
from runtime.composition.component_factory import ComponentFactory
from runtime.lifecycle.lifecycle_manager import LifecycleManager


logger = logging.getLogger(__name__)


def bootstrap(config_path: Path = Path("config/tradex.yaml")) -> dict:
    """
    Bootstrap the entire application.

    Returns a dict with all components for the interface layer to use.
    """
    # 1. Load config
    config_manager = ConfigManager(config_path.parent)
    config = config_manager.load()

    # 2. Setup logging
    from shared.logging.config import setup_logging
    setup_logging(
        level=config["app"]["log_level"],
        json_output=config["app"]["log_format"] == "json",
    )

    logger.info("Bootstrapping TradeXV2", mode=config["app"]["mode"])

    # 3. Create components
    factory = ComponentFactory(config)
    ctx = factory.create_trading_context()
    strategy = factory.create_strategy(ctx.event_bus)

    # 4. Setup lifecycle
    lifecycle = LifecycleManager()
    lifecycle.register(ctx.execution_engine)
    lifecycle.register(strategy)

    logger.info("Bootstrap complete")

    return {
        "config": config,
        "context": ctx,
        "strategy": strategy,
        "lifecycle": lifecycle,
    }
```

## 8. Comparison with Current State

| Aspect | Current | Target |
|---|---|---|
| Config | Scattered env vars | Hierarchical YAML + env overlay |
| Profiles | None | `backtest`, `paper`, `live` profiles |
| Plugin discovery | Hardcoded imports | Entry points |
| Component wiring | Ad hoc | `ComponentFactory` |
| Bootstrap | Manual | `bootstrap()` function |
| Adding new broker | Code changes | Entry point + plugin |
