# Brokers package

Adapters for Dhan, Upstox, and paper trading. **Not** the public product API.

| Layer | Use |
|-------|-----|
| **Product** | `tradex.connect(broker, mode=…)` → `Session` / `Instrument` / ports — see [`docs/OBJECT_MODEL.md`](../docs/OBJECT_MODEL.md) |
| **Transport** | `DhanBrokerGateway`, `UpstoxBrokerGateway`, `PaperGateway` |
| **Ports** | `DataProvider`, `ExecutionProvider`, `BrokerAdapter` in `domain.ports` |
| **Kernel** | `tradex.runtime.*` (factory, auth, resilience, services) |
| **Common residual** | `brokers.common.broker_capabilities`, `api`, `oms.margin_provider`, contracts/tests |

### Connect modes (product API)

| Mode | Default for | Orders |
|------|-------------|--------|
| `sim` | `paper` | In-memory OMS |
| `market` | `dhan` / `upstox` | Disabled (`ORDERS_DISABLED`) — quotes/chains work |
| `trade` | explicit | Process OMS required (`OMS_REQUIRED` otherwise) |

```python
import tradex
s = tradex.connect("dhan", mode="market")  # .env.local auth; same DX as paper for reads
s.universe.equity("RELIANCE").refresh()
```

Plans:

- Object model: [`reports/OBJECT_MODEL_COMPLETION_DESIGN.md`](../reports/OBJECT_MODEL_COMPLETION_DESIGN.md)
- TradeHull DX: [`reports/TRADEHULL_DX_REFERENCE_DESIGN.md`](../reports/TRADEHULL_DX_REFERENCE_DESIGN.md)
- Broker UX: [`reports/BROKER_UX_STANDARDIZATION_DESIGN.md`](../reports/BROKER_UX_STANDARDIZATION_DESIGN.md)
- Safe-to-trade: [`reports/SAFE_TO_TRADE_GATE.md`](../reports/SAFE_TO_TRADE_GATE.md)
- Quickstart: [`examples/object_model_quickstart.py`](../examples/object_model_quickstart.py)
