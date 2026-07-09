# Brokers Evolution Plan (Boy Scout, no rewrite)

**Status:** Waves A–D complete · **Updated:** 2026-07-09  
**Parent backlog:** [ENGINEERING_BACKLOG.md](./ENGINEERING_BACKLOG.md) (Delivery Backlog)  
**Constitution:** [`docs/OPERATING_MODEL.md`](../docs/OPERATING_MODEL.md) — no new pure-refactor waves; residual shim work is Category C Boy Scout only.

## Mission

Make brokers easier to evolve while delivering value.  
**No redesign. No Dhan/Upstox tree rewrite.** Gateways stay as *transport*.

## Target product path

```python
import tradex
session = tradex.connect("dhan")          # + process OMS for live
reliance = session.universe.equity("RELIANCE")
reliance.quote / reliance.history("5m") / reliance.subscribe()
session.buy(reliance, 10, price=2955)     # Intent → OMS → ExecutionProvider
```

Gateways (`DhanBrokerGateway`, `UpstoxBrokerGateway`, `PaperGateway`) are **ops/transport**, not the product API.

## Waves

| Wave | Goal | Status |
|------|------|--------|
| **A** | Tradex-first docs; dual-gateway narrative = transitional transport | **done** |
| **B** | Point call sites at `tradex.runtime`; shrink shim reliance | **done** (prod + tests migrated for models/registry/policy/dtos/auth/resilience/factory/…) |
| **C** | Port contracts for paper + Dhan/Upstox offline fakes | **done** (+ portfolio list queries) |
| **D** | Freeze gateway surface + more import migrations + DhanBrokerGateway primary | **done** |

## Definition of done (this program)

- [x] Docs lead with `tradex` + ports  
- [x] Port contracts green for paper + offline Dhan/Upstox transports  
- [x] External packages / adapters prefer `tradex.runtime` over `brokers.common` shims  
- [x] Lazy `brokers` / `brokers.common` exports avoid import cycles  
- [x] No new gateway public methods without capability/extension justification (review gate)

## Wave progress log

| Date | Change |
|------|--------|
| 2026-07-09 | A: `brokers/README.md`, `brokers/__init__.py`, `tradex.runtime.broker_port`, `tradex/__init__` examples |
| 2026-07-09 | B: datalake batch_executor; adapter_factory registration |
| 2026-07-09 | B: bulk migrate models/registry/policy/dtos/provenance/stream/historical imports |
| 2026-07-09 | B: migrate auth/resilience/factory/gateway/extensions/mappers/settings/observability in dhan/upstox/cli |
| 2026-07-09 | B: lazy package exports fix tradex ↔ brokers circular import |
| 2026-07-09 | C: port contracts for DhanOrderTransport + UpstoxExecutionProvider + portfolio reads |
| 2026-07-09 | D: `test_gateway_surface_freeze.py` allowlists; more tests/cli → tradex.runtime; factory returns `DhanBrokerGateway` |
| 2026-07-09 | D+: purge ~50 zero-ref shims; restore minimal re-exports; architecture tests point at tradex.runtime SSOT |

## Remaining (later Boy Scout)

- Residual real code only in `brokers.common`: `broker_capabilities`, `api/`, `oms.margin_provider`, contracts/tests  
- Prefer `DhanBrokerGateway` (legacy `BrokerGateway` alias removed)  

## Wave D addendum — shim purge

Deleted ~50 pure re-export modules under `brokers.common` (auth, resilience, models, registry, dtos, stream, batch, extensions, services, …).  
Kept: `broker_capabilities` (canonical), real residual code (`api/`, `oms/margin_provider`, contracts/tests).

## Wave E — full shim purge (2026-07-09)

Deleted remaining pure re-exports (`factory`, `gateway`, `settings`, `errors`, `auth`, `resilience`, `services`, `core`, `mappers`, `observability`, `options`, `reconciliation`, `connection`, `extensions`, `idempotency`, `adapters`, deprecated `BrokerSession`).  
Moved tests under `tradex.runtime.*` / `infrastructure.*`. Removed `BrokerGateway` alias → `DhanBrokerGateway` only.

## Out of scope

- Merging Dhan/Upstox package layouts  
- Decorator instrument stacks  
- Deleting working gateways in one cut  
