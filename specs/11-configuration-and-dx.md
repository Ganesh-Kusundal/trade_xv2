# 11 — Configuration and Developer Experience

## 1. Purpose

The framework is configured declaratively via YAML and driven through CLI/TUI/API surfaces. Developer experience prioritizes fast iteration: backtest locally, paper trade with live data, deploy to live with safety gates.

## 2. Declarative Configuration

### AppConfig Schema

```yaml
# config/trading.yaml
environment: PAPER          # REPLAY | BACKTEST | PAPER | LIVE
broker: dhan                  # dhan | upstox | paper

components:
  message_bus:
    max_queue_size: 10000
    persistent_log: false
  execution:
    default_order_type: MARKET
  risk:
    max_order_size: 1000
    max_position_size: 5000
    max_daily_loss: 50000
    max_orders_per_day: 100
  data:
    datalake_path: ./data/lake
    default_timeframe: 1m

strategies:
  - id: momentum_v1
    class: strategies.momentum.MomentumStrategy
    params:
      lookback: 20
      threshold: 0.02

logging:
  level: INFO
  format: json

observability:
  metrics_enabled: true
  tracing_enabled: true
  otlp_endpoint: http://localhost:4317
```

### Environment Profiles

| Profile | Environment | Broker | Risk Limits |
|---------|-------------|--------|-------------|
| replay.yaml | REPLAY | paper | Relaxed |
| backtest.yaml | BACKTEST | paper | Relaxed |
| paper.yaml | PAPER | dhan/upstox | Moderate |
| live.yaml | LIVE | dhan/upstox | Strict |

Profiles overlay base config. LIVE profile requires explicit enablement flag.

### Configuration Hierarchy

Resolved in order (later overrides earlier):

1. Built-in defaults
2. Base YAML (`config/tradex.yaml`)
3. Profile overlay (`config/profiles/{profile}.yaml`)
4. Environment variables (`TRADEX_*` prefix)
5. CLI overrides (`--config key=value`)

## 3. Component Wiring

### RuntimeFactory

```python
class RuntimeFactory:
    @staticmethod
    def build(config: AppConfig) -> Runtime:
        bus = MessageBus(config.components.message_bus)
        clock = resolve_clock(config.environment)
        fill_source = resolve_fill_source(config.environment, config.broker)
        cache = TradingCache()
        risk = RiskManager(config.components.risk)
        execution = ExecutionEngine(bus, fill_source, cache, risk, clock)
        # ... wire remaining components
        return Runtime(bus, execution, cache, ...)
```

Configuration drives component assembly. No hard-coded wiring.

### ComponentFactory

```python
class ComponentFactory:
    def create_message_bus(self, config: MessageBusConfig) -> MessageBus: ...
    def create_execution_engine(self, config: ExecutionConfig, ...) -> ExecutionEngine: ...
    def create_risk_manager(self, config: RiskConfig, ...) -> RiskManager: ...
    def create_data_engine(self, config: DataConfig, ...) -> DataEngine: ...
```

ComponentFactory + ComponentRegistry + ConfigManager assemble the runtime from declarative YAML.

### ComponentRegistry

```python
class ComponentRegistry:
    def register(self, component: Component) -> None: ...
    def get(self, component_id: ComponentId) -> Component: ...
    def all(self) -> list[Component]: ...
```

## 4. CLI Surfaces

### Analytics-First Command Tree

Research questions first — not order/position/portfolio:

```
tradex
├── scanner          momentum, breakout, volume, rs
├── indicator        halftrend, halftrend_scan
├── strategy         list, run
├── backtest         run, replay, optimize, walkforward, paper
├── market           breadth, sector, sector_rotation, sector_strength, sector_volume
├── support          levels, nearest
├── fundamentals     financial analysis
├── report           performance reports
├── config           get, set, list, reset, validate
├── paper            paper trading session
├── live             live trading (--confirm required)
├── quote            live quotes
├── history          historical bars
└── version          framework version
```

Thin argv-translators delegate to analytics engines; no duplicate wiring in CLI layer.

### Interface Matrix

| Surface | Purpose | Mode Support |
|---------|---------|--------------|
| Click CLI | Analytics-first research + trading | All four modes |
| Textual TUI | Terminal trading dashboard | Paper, Live |
| FastAPI REST | Programmatic access | All modes |
| MCP Server | Datalake queries for external tools | Read-only |
| Interactive shell | REPL exploration | All modes |

### Key Commands

```bash
# Run a backtest
tradex backtest --strategy momentum_v1 --from 2026-01-01 --to 2026-06-30

# Run paper trading
tradex paper --broker dhan --strategy momentum_v1

# Run live (with safety checks)
tradex live --broker dhan --strategy momentum_v1 --confirm

# List available adapters
tradex config --list-brokers

# Validate configuration
tradex config --validate trading.yaml
```

## 5. TradingNode (Public Entry Point)

```python
class TradingNode:
    """Single entry point for all framework capabilities."""

    @classmethod
    def from_config(cls, path: str) -> TradingNode: ...

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def submit_order(self, intent: OrderIntent) -> OrderResult: ...
    def cancel_order(self, order_id: OrderId) -> CancelResult: ...
    def query_positions(self) -> list[Position]: ...
    def query_pnl(self) -> PnLReport: ...
```

## 6. Interactive Shell

```python
# Optional REPL for exploration
tradex shell --config sandbox.yaml

>>> node.query_positions()
>>> node.submit_order(OrderIntent(...))
>>> node.query_pnl()
```

## 7. Developer Workflow

```
1. Define strategy (implement Strategy protocol)
2. Configure backtest profile
3. Run: tradex backtest --strategy my_strategy
4. Review report
5. Configure sandbox profile
6. Run: tradex paper --strategy my_strategy
7. Monitor via TUI/API
8. Configure live profile with strict risk limits
9. Run: tradex live --strategy my_strategy --confirm
```

## 8. Plugin Development

### Creating a Broker Plugin

1. Implement BrokerGateway, BrokerConnection, sub-adapters
2. Implement WireMapper for native ↔ domain translation
3. Register via entry point in pyproject.toml
4. Register BrokerPlugin metadata in __init__.py
5. Test with AdapterTestHarness

### Creating a Strategy

1. Implement Strategy protocol
2. Register in config strategies section
3. Backtest with historical data
4. Paper trade with live data
5. Deploy to live

### Plugin Manifest

```python
@dataclass(frozen=True)
class PluginManifest:
    plugin_id: str
    version: str
    author: str
    capabilities: list[str]
    config_schema: type[BaseModel]
```

## 9. Configuration Validation

Config validated at startup via Pydantic:

- All required fields present
- Enum values valid (Environment, BrokerId)
- Risk limits positive
- Strategy class importable
- Broker plugin discoverable
- Environment/broker combination supported

Validation failure → abort startup with clear error message.

## 10. Common Development Commands

Standard Makefile targets for developer workflow:

| Command | Purpose |
|---------|---------|
| `make install` | Install dependencies (editable) |
| `make test` | Run unit + component tests |
| `make test-integration` | Run integration tests (requires sandbox creds) |
| `make lint` | Run ruff + mypy + import-linter |
| `make backtest` | Run sample backtest |
| `make paper` | Start paper trading session |
| `make docs` | Generate API reference docs |

## 11. Developer Experience Invariants

1. Same strategy code runs in backtest, paper, and live
2. Configuration drives all wiring; no code changes between environments
3. CLI provides discoverable commands with --help
4. Config validation fails fast at startup
5. LIVE requires explicit --confirm flag
6. Plugin development follows standard entry-point pattern
