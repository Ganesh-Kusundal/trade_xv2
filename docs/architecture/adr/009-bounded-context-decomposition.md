# ADR-009: Formal Bounded Context Decomposition

## Status

Proposed

## Context

The codebase has grown organically with implicit boundaries between subdomains. While architecture tests enforce layer isolation (domain ↔ application ↔ infrastructure), the **intra-layer** boundaries are unclear:

- `domain/` contains instruments, orders, events, indicators, value objects, ports, capabilities, candles, and reconciliation — some of these are independent subdomains.
- `application/` mixes OMS, streaming, scheduling, data management, and services.
- `infrastructure/` mixes persistence, event bus, resilience, observability, and adapters.

Without explicit bounded contexts, changes in one subdomain can ripple unexpectedly across the codebase. The `test_module_boundaries_and_decomposition.py` test begins to address this but needs formalization.

## Decision

Define **formal bounded contexts** with explicit ownership, interfaces, and integration patterns:

### Proposed Bounded Contexts

| Context | Primary Responsibility | Key Packages |
|---------|----------------------|--------------|
| **Trading** | Strategy execution, signal generation, order intent creation | `application.trading`, `domain.indicators`, `domain.strategy` |
| **Order Management** | Order lifecycle, execution tracking, position book | `application.oms`, `domain.orders`, `domain.entities.order` |
| **Market Data** | Live feeds, historical data, candle aggregation | `domain.candles`, `domain.ports.market_data`, `application.streaming` |
| **Instruments** | Symbol resolution, instrument metadata, option chains | `domain.instruments`, `domain.symbols` |
| **Broker Integration** | Broker-specific adapters, wire protocols, auth | `brokers.*` |
| **Analytics** | Backtest, replay, performance metrics, data lake | `analytics.*`, `datalake.*` |
| **Platform** | Composition, lifecycle, configuration, observability | `runtime.*`, `infrastructure.*`, `config.*` |
| **Interface** | API, CLI, MCP, UI presentation | `interface.*` |

### Integration Rules

- Contexts communicate through **domain events** (EventBus) or **port interfaces** (Protocol).
- Direct cross-context imports are forbidden (existing layer tests enforce this).
- New bounded context tests should verify intra-layer isolation.

## Consequences

**Positive:**
- Clear ownership reduces merge conflicts and cognitive load.
- Changes are scoped to a context, reducing blast radius.
- Enables independent testing and potential future service extraction.

**Negative:**
- Initial decomposition requires careful design and may require moving code.
- Over-decomposition can create excessive indirection.

## Enforcement

- `tests/architecture/test_module_boundaries_and_decomposition.py` — module boundary validation
- `tests/architecture/test_domain_isolation.py` — domain layer isolation
- `tests/architecture/test_import_direction_and_layering.py` — import direction rules
- **NEW:** `tests/architecture/test_bounded_context_isolation.py` (proposed)
