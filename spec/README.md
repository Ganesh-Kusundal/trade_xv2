# Vendeta Framework Specification

**Version:** 1.0  
**Status:** Draft  
**Last Updated:** 2026-07-22  

---

## Overview

This specification document set defines the complete design of the **Vendeta** algorithmic trading framework — a professional, event-driven, component-based platform for Indian markets (NSE, BSE, MCX), inspired by [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) and implemented in Rust.

The specifications transform the architectural vision into implementation-ready blueprints covering every subsystem, from the message bus to broker adapters, risk management to backtesting.

---

## Table of Contents

| # | Document | Topic |
|---|----------|-------|
| 01 | [Introduction & Vision](./01-introduction-vision.md) | Framework philosophy, design principles, goals |
| 02 | [Architecture Overview](./02-architecture-overview.md) | High-level architecture, component model, dependency rules |
| 03 | [Project Structure](./03-project-structure.md) | Crate layout, responsibilities, dependency graph |
| 04 | [Message-Driven Architecture](./04-message-driven-architecture.md) | Message types, bus, routing, backpressure, replay |
| 05 | [Component Lifecycle](./05-component-lifecycle.md) | Component trait, lifecycle states, health checks |
| 06 | [Execution Engine](./06-execution-engine.md) | Order lifecycle, FSM, fills, algorithms |
| 07 | [Strategy System](./07-strategy-system.md) | Strategy trait, context, signal bridge, registry |
| 08 | [Adapter System](./08-adapter-system.md) | BrokerGateway, capabilities, feed bridge, reconnection |
| 09 | [Risk Management](./09-risk-management.md) | Pre-trade checks, circuit breaker, kill switch |
| 10 | [Portfolio Construction](./10-portfolio-construction.md) | Positions, P&L, capital allocation, rebalancing |
| 11 | [Data Infrastructure](./11-data-infrastructure.md) | Feed bridge, bar aggregation, storage layer |
| 12 | [Zero-Parity Engine](./12-zero-parity-engine.md) | Clock abstraction, backtest/live parity, replay |
| 13 | [Observability](./13-observability.md) | Logging, metrics, tracing, audit trail |
| 14 | [Plugin System](./14-plugin-system.md) | Registration, discovery, extension model |
| 15 | [Configuration](./15-configuration.md) | YAML schema, validation, component factory |
| 16 | [Performance](./16-performance.md) | Zero-alloc paths, fixed-point math, benchmarks |
| 17 | [Testing](./17-testing.md) | Test pyramid, property tests, parity tests |
| 18 | [CI/CD](./18-ci-cd.md) | Pipeline, gates, release automation |
| 19 | [Developer Experience](./19-developer-experience.md) | CLI, Makefile, onboarding |
| 20 | [Documentation Strategy](./20-documentation-strategy.md) | Doc generation, guides, examples |
| 21 | [Versioning](./21-versioning.md) | SemVer, release process, changelog |
| 22 | [Community](./22-community.md) | Ecosystem, templates, contributions |
| 23 | [Framework vs Application](./23-framework-vs-application.md) | IoC, contract, guarantees |
| 24 | [Migration Path](./24-migration-path.md) | Phased migration, compatibility |

---

## Reading Order

### For New Contributors
1. **01** → **02** → **03** (understand the vision and structure)
2. **04** → **05** (core infrastructure: bus + components)
3. **06** → **07** → **08** (primary subsystems)
4. Pick your area of interest from **09–24**

### For Strategy Developers
1. **01** (philosophy) → **07** (strategy system) → **12** (backtest/live parity)
2. **15** (configuration) → **19** (developer experience)

### For Adapter/Broker Developers
1. **08** (adapter system) → **04** (message bus) → **11** (data infrastructure)
2. **09** (risk) → **13** (observability)

### For Infrastructure Engineers
1. **02** → **03** → **04** → **05**
2. **16** (performance) → **17** (testing) → **18** (CI/CD)

---

## Document Conventions

### Internal Structure
Each specification document follows a consistent structure:
1. Title & Metadata
2. Overview (purpose, scope, principles)
3. Requirements (functional + non-functional)
4. Detailed Design (Rust types, traits, structs)
5. Class Diagram (Mermaid `classDiagram`)
6. Sequence Diagrams (Mermaid `sequenceDiagram`)
7. Data Flow (Mermaid `flowchart`)
8. Configuration (YAML schema)
9. Error Handling
10. Testing Requirements
11. Implementation Notes
12. Cross-References

### Diagram Syntax
- All diagrams use **Mermaid** syntax
- Class diagrams: `classDiagram`
- Sequence diagrams: `sequenceDiagram`
- State machines: `stateDiagram-v2`
- Flow charts: `flowchart TD` / `flowchart LR`

### Code Conventions
- All code examples are in **Rust** (matching the actual implementation)
- Python pseudocode is included where it aids conceptual understanding
- Fixed-point arithmetic: `Price(i64)` with `PRICE_PRECISION = 10_000`
- Timestamps: nanoseconds since epoch (`i64`)

### Status Legend
| Status | Meaning |
|--------|---------|
| `Draft` | Initial design, subject to change |
| `Review` | Ready for team review |
| `Approved` | Accepted for implementation |
| `Implemented` | Fully implemented in codebase |

---

## Glossary

| Term | Definition |
|------|-----------|
| **Component** | Infrastructure-level processing node with lifecycle (init/start/stop/reset) |
| **Strategy** | User-written alpha logic; NOT a Component; owned by DataEngine |
| **Signal** | Strategy intent (EnterLong, ExitShort, etc.); converted to orders by bridge |
| **BrokerGateway** | Trait for broker connectivity (orders, data, positions) |
| **MessageBus** | Central typed message dispatcher (broadcast + mpsc) |
| **Clock** | Time abstraction; LiveClock for production, BacktestClock for replay |
| **Zero-Parity** | Same strategy code runs identically in backtest and live |
| **FeedBridge** | WebSocket → MessageBus adapter for real-time market data |
| **Event Sourcing** | All state changes are events; reconstruct state by replaying |
| **Fixed-Point** | Prices stored as `i64` (value × 10,000) to avoid floating-point errors |

---

## Source Documents

This specification set derives from:
- `goal.md` — Framework vision and philosophy (5,878 lines)
- `docs/architecture/target-architecture.md` — Rust architecture blueprint (2,535 lines)
- Actual crate source code in `crates/`

---

## License

Internal specification — Vendeta Trading Framework
