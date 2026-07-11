# ADR-003: Broker Plugin Model

## Status

Proposed

## Date

2026-07-12

## Context

TradeXV2 supports 3 broker adapters (Dhan, Upstox, Paper) plus a DataLake gateway. Each has grown organically with varying interfaces:

- `brokers/dhan/` — 50+ files, deeply nested (api/, auth/, config/, data/, execution/, extensions/, identity/, instruments/, portfolio/, resilience/, streaming/, websocket/)
- `brokers/upstox/` — 80+ files, even more deeply nested (adapters/, auth/, capabilities/, extensions/, fundamentals/, instruments/, ipo/, kill_switch/, market_data/, market_intelligence/, mutual_funds/, news/, orders/, payments/, reconciliation/, static_ip/, websocket/)
- `brokers/paper/` — 10 files, clean implementation
- `brokers/common/` — Shared infrastructure (acl, auth, contracts, instruments, oms, transport, usecases)

The gateway factory (`infrastructure/gateway/factory.py`) creates brokers via `importlib.import_module()` and dispatches through a dictionary of builder functions.

Current entry points: `pyproject.toml [project.entry-points."tradex.brokers"]` registers Dhan, Upstox, and Paper as module-only entry points.

## Decision

All broker adapters will implement the `BrokerAdapter` protocol with a standardized lifecycle:

### Plugin Interface

```python
@runtime_checkable
class BrokerPlugin(Protocol):
    """Standard broker plugin interface."""
    
    @property
    def broker_id(self) -> str: ...
    
    @property
    def display_name(self) -> str: ...
    
    def create_adapter(
        self,
        env_path: Path | None,
        *,
        load_instruments: bool = True,
        event_bus: Any | None = None,
        lifecycle: Any | None = None,
        risk_manager: Any | None = None,
    ) -> BrokerAdapter: ...
    
    def capabilities(self) -> BrokerCapabilities: ...
    
    def health_check(self, adapter: BrokerAdapter) -> BrokerHealthSnapshot: ...
```

### Lifecycle Hooks

Each broker plugin provides lifecycle hooks:

```python
class BrokerLifecycle(Protocol):
    def on_before_connect(self) -> None: ...
    def on_after_connect(self, adapter: BrokerAdapter) -> None: ...
    def on_before_disconnect(self) -> None: ...
    def on_after_disconnect(self) -> None: ...
    def on_error(self, error: Exception) -> None: ...
    def on_health_check(self) -> BrokerHealthSnapshot: ...
```

### Registration

Brokers self-register via `register_broker_plugin()` at import time (existing pattern). The entry point's job is "import this module."

### Discovery

```python
from importlib.metadata import entry_points

def discover_brokers() -> dict[str, BrokerPlugin]:
    plugins = {}
    for ep in entry_points(group="tradex.brokers"):
        mod = ep.load()
        if hasattr(mod, "register_broker_plugin"):
            plugin = mod.register_broker_plugin()
            plugins[plugin.broker_id] = plugin
    return plugins
```

## Consequences

### Positive
- New brokers can be added without modifying core code
- Standardized testing (all brokers implement same interface)
- Plugin lifecycle is managed consistently
- Broker capabilities are self-describing
- Health checks work uniformly

### Negative
- Migration cost for existing broker implementations
- Some broker-specific behavior may not fit the standard interface (handled via extensions)
- Entry point import side effects need careful management

### Mitigations
- Phased migration: Dhan → Upstox → Paper
- Backward-compatible aliases during transition
- Extension mechanism for broker-specific capabilities
- Broker certification suite validates compliance

## References

- `src/domain/ports/broker_adapter.py` — Current BrokerAdapter protocol
- `src/domain/ports/protocols.py` — DataProvider, ExecutionProvider protocols
- `src/infrastructure/gateway/factory.py` — Current gateway factory
- `src/brokers/common/contracts/broker_contract.py` — Broker contract tests
- `src/brokers/certification/` — Broker certification suite
