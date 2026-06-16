# ADR-001: Domain Types Live in brokers/common/core/

## Context
Previously, domain types like `Quote`, `Balance`, `DepthLevel`, and `MarketDepth` were defined in multiple places: `brokers/common/core/domain.py` and `brokers/dhan/domain.py`. This caused shotgun surgery — adding a field required editing 4+ files.

## Decision
All canonical domain types are defined exactly once in the `brokers/common/core/` package, split across focused modules:
- `types.py` — enums (Side, OrderStatus, ProductType, OrderType, Validity, ExchangeSegment, InstrumentType, Capability, ConnectionStatus)
- `models.py` — domain dataclasses (Order, Position, Holding, Trade, Quote, Balance, DepthLevel, MarketDepth, Instrument, etc.)
- `requests.py` — input shapes (OrderRequest, ModifyOrderRequest, SliceOrderRequest, OrderPreview, HistoricalCandle)
- `reconciliation.py` — drift/reconciliation types (DriftItem, ReconciliationReport)
- `domain.py` — thin re-export facade for backward compatibility

Broker-specific extensions (e.g., Dhan's `Instrument` with typed `Exchange` enum) are allowed but must NOT redefine canonical types.

## Consequences
- Adding a field to `Quote` now requires editing 1 file instead of 4
- Architecture tests enforce this rule in CI
- Existing `from brokers.common.core.domain import X` continues to work via the re-export facade
