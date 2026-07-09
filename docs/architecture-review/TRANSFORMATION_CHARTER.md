# TradeX V2 → TradingOS — Transformation Charter

**Standing mandate for the architecture evolution.** This charter governs all work. It is
complemented by three working documents:
- `ARCHITECTURE_REVIEW.md` — **Current State Assessment** (audit of today).
- `TARGET_ARCHITECTURE.md` — **Target Architecture Specification** (desired platform).
- `REFACTORING_ROADMAP.md` — **gap-driven migration** (Phase A–G).
Plus: `DATA_LAKE_ARCHITECTURE.md`, `TESTING_STRATEGY.md`, `RISK_ASSESSMENT.md`,
`TECHNICAL_DEBT.md`, `ADRS.md`.

**Status:** DESIGN ONLY. No code has been changed.

---

## 1. Mission
Transform the existing **TradeX V2** codebase into a world-class **Trading Operating System
(TradingOS)** — a highly modular, event-driven, broker-agnostic, object-oriented, testable,
scalable platform for quant research, backtesting, simulation, paper trading, and live trading.
**Evolve, never rewrite.** Preserve working functionality; improve architecture continuously.

## 2. Virtual Engineering Organization
Decisions are challenged from multiple viewpoints before implementation:
- Robert C. Martin (Clean Architecture), Eric Evans (DDD), Martin Fowler (Enterprise Patterns),
  Greg Young (Event Sourcing / Event-Driven), Kent Beck (TDD), Michael Feathers (Working
  Effectively with Legacy Code), Vaughn Vernon (IDDD), Dr. Venkat Subramaniam (Modern OO),
  Martin Thompson (High-Performance / Low-Latency).
- Plus the pragmatic lens of senior architects from Jane Street, Citadel Securities, Two Sigma,
  Bloomberg, Interactive Brokers, QuantConnect, NinjaTrader, Trading Technologies.

## 3. Product Vision
A complete TradingOS: multiple brokers, exchanges, asset classes; live / paper / replay /
backtest / research; market scanning; portfolio & risk management; OMS; strategy execution; AI
agents; visual strategy builder; automation; analytics; performance attribution; multi-account
trading. Must support years of growth without redesign.

## 4. Existing Assets (reuse, do not rewrite)
Valuable IP already present: broker integrations (Dhan/Upstox/Paper), event-driven core
(`infrastructure/event_bus`), DuckDB + Parquet data lake (`datalake`), strategy framework,
OMS (`OrderManager`/`PositionManager`/`RiskManager`), scanner modules, indicators, analytics,
replay infrastructure, extensive tests (597 test files), and DDD domain models (`src/domain`).
Treat as IP; refactor incrementally; **no big-bang rewrite.**

## 5. Core Architectural Principles
DDD · Clean Architecture · Hexagonal · Event-Driven · CQRS where appropriate · SOLID · Rich
Domain Model · Composition over Inheritance · Immutable Value Objects · Dependency Injection ·
Explicit Boundaries · High Cohesion · Low Coupling. **Infrastructure never leaks into the domain.**

## 6. Top-Down Review Method (never implement before understanding)
- **Phase 1 — Product & Business Model:** vision, capabilities, user/trading/research
  lifecycles, bounded contexts.
- **Phase 2 — Architecture Review:** layering, package org, boundaries, dependency direction,
  coupling/cohesion, debt, duplication, missing/over-abstractions. Challenge every decision.
- **Phase 3 — Domain Model Review:** classify every concept (Entity/Aggregate/VO/Domain
  Event/Repository/Factory); behavior belongs to domain objects.
- **Phase 4 — Package Organization:** by business capability, not technical type.
- **Phase 5 — Runtime Architecture:** validate init order (Config→Auth→Broker→Metadata→Data
  Lake→Market Data→Strategy Warm-up→Scanner→Trading Ready→Market Open→Trading→Shutdown).
- **Phase 6 — Event Architecture:** ownership, contracts, versioning, replay, routing,
  persistence, ordering; events immutable.
- **Phase 7 — Data Flow:** single owner per transformation, Exchange→Broker→Normalization→
  Canonical Market Model→Data Lake→DuckDB→Indicators→Signals→Scanner→Strategy→Risk→OMS→
  Execution→Portfolio→Analytics.
- **Phase 8 — Broker Architecture:** brokers are plugins; public SDK broker-agnostic
  (`session.equity("RELIANCE").buy()`); broker specifics behind `.broker.<capability>()`.
- **Phase 9 — Data Lake Architecture:** DuckDB + Parquet as unified analytical platform.
- **Phase 10 — Testing Strategy:** Test Pyramid; mock only external boundaries.

## 7. Continuous Refactoring Loop
For every iteration: (1) analyze, (2) find weaknesses, (3) prioritize by impact, (4) propose
multiple solutions, (5) compare trade-offs, (6) select best design, (7) refactor incrementally,
(8) run full suite, (9) update docs, (10) write an ADR, (11) **wait for review before the next
major change.** No uncontrolled refactoring.

## 8. Definition of Success
TradeX V2 becomes a TradingOS where domain objects are central; infrastructure fully encapsulated;
brokers are interchangeable plugins; DuckDB+Parquet form a unified analytical data platform;
live/replay/backtest/research share one canonical market model; every decision is traceable;
the codebase is understandable, extensible, and maintainable for a decade without another
redesign.

---

*This charter is the mandate. Implementation begins only after Phase A of `REFACTORING_ROADMAP.md`
is approved.*
