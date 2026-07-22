# TradeXV2 V2 — NautilusTrader-Inspired Redesign

> **Status:** Design Specification  
> **Date:** 2026-07-22  
> **Scope:** Full platform redesign inspired by NautilusTrader architecture  

---

## 1. Vision

TradeXV2 is an **event-driven quantitative trading kernel** for Indian exchanges (NSE, BSE, MCX). The V2 redesign transforms it from a well-architected application into a **NautilusTrader-level framework** — where the framework owns the execution lifecycle and users plug in strategies, adapters, and risk models.

**Core identity:** Analytics-first, broker-agnostic, zero-parity trading OS.

---

## 2. Current State Assessment (Graphify-Validated)

### Codebase Metrics

| Metric | Value |
|---|---|
| Total source files | 1,160 |
| Broker module files | 307 |
| Graph nodes | 35,763 |
| Graph edges | 64,078 |
| Communities | 1,478 |
| Tests | 7,000+ |
| Coverage | 80%+ overall |

### God Classes (Confirmed by Graphify)

| Class | Degree | Location | Problem |
|---|---|---|---|
| **DhanBroker** | 376 | `src/brokers/dhan/wire.py:32` | Owns 20+ sub-adapters, 350+ test deps |
| **UpstoxWireAdapter** | 195 | `src/brokers/upstox/wire.py:43` | 175+ connections, mixed concerns |
| **PaperGateway** | 158 | `src/brokers/paper/paper_gateway.py:33` | 138+ connections |
| **DhanConnection** | 121 | `src/brokers/dhan/streaming/connection.py:73` | 20+ sub-adapters directly owned |

### What Works (Keep)

- Clean Architecture layering (domain → application → infrastructure → runtime → interface)
- Zero-parity invariant (backtest/replay/paper share identical OMS + Risk)
- Import-linter CI gates (5 rules enforced)
- Plugin model (`tradex.brokers`, `tradex.exchanges` entry points)
- BrokerAdapter protocol (25 connections — clean abstraction)
- TradingContext (67 connections — central container, well-used)
- ExecutionEngine (41 connections — correct seam)
- BrokerInfrastructure (13 connections — clean DI container)
- All 8 architectural violations (G1-G8) resolved

### What Doesn't Work (Fix)

- **307 files** in brokers module (Dhan: 102, Upstox: 128, Paper: 12, common: 37)
- **God classes** with 100-376 connections each
- **No MessageBus** — only exists in docs, not code (graphify confirms: degree 1, document-only)
- **No standard component lifecycle** — components ad-hoc
- **Scattered configuration** — multiple config patterns
- **No health check system** — observability bolted on, not structural

---

## 3. Design Principles

### 1. Message-Driven Everything
All inter-component communication flows through a typed `MessageBus`. No direct method calls between subsystems. Enables testing, parallelism, replay, and monitoring.

### 2. Component Model
Strategy, Risk, Execution, Portfolio, Data are pluggable components with standard lifecycle: `initialize() → start() → [process] → stop() → reset()`.

### 3. Deterministic Replay
Backtest is a first-class citizen. Every event is timestamped (nanosecond precision) and reproducible. Same engine runs backtest and live — only the adapter changes.

### 4. Zero-Allocation Hot Paths
Critical path (order placement, fill processing) minimizes object creation. Frozen dataclasses, pre-allocated buffers.

### 5. Type Safety First
Extensive use of `Protocol`, `TypedDict`, `dataclass(frozen=True)`, and runtime validation via Pydantic.

### 6. Observability Built-In
Metrics, tracing, and audit are structural, not added later. Every message traced, every operation metered.

### 7. Plugin over Configuration
Brokers/exchanges are plugins discovered via entry points. No central switch statements.

---

## 4. NautilusTrader Comparison

### What We Adopt

| NautilusTrader Pattern | TradeXV2 V2 Adoption |
|---|---|
| Message Bus (typed, async) | `MessageBus` with sync/async publish, dead letter queue |
| Component Lifecycle | `Component` ABC: initialize → start → stop → reset |
| Adapter Pattern | `BrokerAdapter` → `BrokerGateway` → `BrokerConnection` → Sub-Adapters |
| Zero-Parity Engine | Same `ExecutionEngine` for all modes, `FillSource` varies |
| FillSource Abstraction | `SimulatedFillSource`, `PaperFillSource`, `BrokerFillSource` |
| Strategy Protocol | `Strategy` with `on_bar`, `on_fill`, `on_quote` callbacks |
| Instrument Master | Central `InstrumentMaster` with per-broker `InstrumentRef` |
| Risk Engine | Pre-trade + post-trade risk as pluggable `RiskModel` |
| Backtest = Live | Same engine, different data source + fill source |

### What We Adapt

| NautilusTrader | TradeXV2 V2 | Reason |
|---|---|---|
| Rust/Cython core | Pure Python | Team size, iteration speed |
| Multi-asset global | Indian exchanges only (NSE/BSE/MCX) | Focus |
| Custom storage engine | DuckDB + Parquet | Already working, good fit |
| Library-only (no CLI) | Click CLI + FastAPI + TUI + MCP | Analytics-first product |
| FIX protocol | REST + WebSocket (broker SDKs) | Indian broker APIs |
| Generic risk | Indian market-specific (STT, margins, circuit limits) | Domain accuracy |

---

## 5. Measurable Goals

| Goal | Current | Target |
|---|---|---|
| Broker module files | 307 | ~50 (-84%) |
| God classes (degree > 100) | 4 | 0 |
| MessageBus | docs-only | central nervous system |
| Component lifecycle | ad-hoc | standard for all components |
| Zero-parity | working | enhanced with message tracing |
| Test coverage | 80% | 85%+ |
| Architecture tests | 261 | 300+ |
| Health checks | none | readiness + liveness probes |
| Config | scattered | single declarative YAML |

---

## 6. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              CLIENTS                                    │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐     │
│  │  REST   │  │  gRPC   │  │WebSocket│  │  CLI    │  │  TUI    │     │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘  └─────────┘     │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────┐
│                        FACADE / ENTRY POINT                             │
│  tradex.TradingNode — Single entry point for all capabilities          │
│  configure(components, risk, execution, data) → start() → stop()      │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────┐
│                        MESSAGE BUS (Event Engine)                       │
│  EventBus — Typed, async, ordered, persistent (optional)               │
│  subscribe(handler, msg_type) │ publish(msg) │ replay(from, to)        │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
    ┌──────────────────────────┼──────────────────────────┐
    │                          │                          │
    ▼                          ▼                          ▼
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│   STRATEGY   │      │    RISK      │      │  EXECUTION   │
│  Component   │      │  Component   │      │  Component   │
│              │      │              │      │              │
│ - on_bar()   │      │ - check()    │      │ - submit()   │
│ - on_fill()  │      │ - approve()  │      │ - cancel()   │
│ - on_order() │      │ - reject()   │      │ - modify()   │
└──────────────┘      └──────────────┘      └──────────────┘
    │                          │                          │
    ▼                          ▼                          ▼
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│  PORTFOLIO   │      │   DATA       │      │  BROKER      │
│  Component   │      │  Component   │      │  ADAPTERS    │
│              │      │              │      │              │
│ - position() │      │ - stream()   │      │ - dhan       │
│ - pnl()      │      │ - history()  │      │ - upstox     │
│ - equity()   │      │ - lookup()   │      │ - paper      │
└──────────────┘      └──────────────┘      └──────────────┘
```

---

## 7. Document Index

| # | Document | Description |
|---|---|---|
| 00 | [Overview](00-overview.md) | This document — vision, goals, NautilusTrader comparison |
| 01 | [Architecture HLD](01-architecture-hld.md) | High-level architecture, layers, dependency rules, invariants |
| 02 | [Component Design LLD](02-component-design-lld.md) | Class diagrams, component interfaces, domain messages |
| 03 | [Message Bus](03-message-bus.md) | MessageBus design, message types, routing, DLQ |
| 04 | [Execution Engine](04-execution-engine.md) | ExecutionEngine, FillSource, zero-parity, TradingContext |
| 05 | [Brokers Redesign](05-brokers-module-redesign.md) | Broker adapter framework, Gateway→Connection→Sub-Adapters |
| 06 | [Data Engine & DataLake](06-data-engine-datalake.md) | DataEngine, DataLakeGateway, federation, storage |
| 07 | [Strategy & Backtest](07-strategy-and-backtest.md) | Strategy system, backtest engine, replay, paper trading |
| 08 | [Risk Management](08-risk-management.md) | Multi-layer risk model, kill switch, pre/post-trade |
| 09 | [Observability](09-observability.md) | Logging, metrics, tracing, health checks |
| 10 | [Configuration & Plugins](10-configuration-and-plugins.md) | Declarative YAML, plugin discovery, component factory |
| 11 | [Flows & DFDs](11-flows-and-dfds.md) | All data flow diagrams, sequence diagrams |
| 12 | [Deployment & CI/CD](12-deployment-and-cicd.md) | Docker, Kubernetes, GitHub Actions, Makefile |
| 13 | [Migration Plan](13-migration-plan.md) | Phased migration from current codebase |
| 14 | [Testing Strategy](14-testing-strategy.md) | Test pyramid, adapter harness, parity tests |

---

## 8. Key Architecture Decisions

| ADR | Decision | Rationale |
|---|---|---|
| V2-ADR-001 | MessageBus as central communication | Enables replay, testing, observability |
| V2-ADR-002 | Gateway → Connection → Sub-Adapters | Eliminates god classes (376 → ~8 files) |
| V2-ADR-003 | FillSource as zero-parity seam | Single execution path, mode-agnostic |
| V2-ADR-004 | Component lifecycle standard | Predictable startup/shutdown, health checks |
| V2-ADR-005 | Declarative YAML config | Single source of truth for all settings |
| V2-ADR-006 | Incremental migration (not rewrite) | 7k+ tests, working system — preserve value |
| V2-ADR-007 | DuckDB + Parquet (not custom storage) | Proven, good fit for analytics workload |
| V2-ADR-008 | Python-only (not Rust/Cython) | Team size, iteration speed > raw perf |

---

## 9. Summary

TradeXV2 V2 takes a **working, well-tested system** and evolves it into a **framework-grade platform** by:

1. **Eliminating god classes** — 307 broker files → ~50 via Gateway→Connection→Sub-Adapters
2. **Adding MessageBus** — typed, async, with dead letter queue and replay
3. **Standardizing lifecycle** — every component: initialize → start → stop → reset
4. **Declarative config** — single YAML drives all component assembly
5. **Built-in observability** — every message traced, every operation metered
6. **Preserving what works** — zero-parity, clean architecture, import-linter, 7k+ tests

The migration is **incremental**, not a rewrite. Every phase maintains backward compatibility and all existing tests pass.
