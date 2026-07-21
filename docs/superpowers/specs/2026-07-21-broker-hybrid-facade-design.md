# Broker Hybrid Facade — Design

**Date:** 2026-07-21  
**Status:** Approved  
**Mode:** Facade-first hybrid (Option 3 + domain-centric API)

## Intent

Expose a simple public broker API without relocating shared infrastructure into
`brokers/` and without a greenfield rewrite of Dhan/Upstox/Paper.

## Architecture choice

**Hybrid facade:** `brokers` is the only public entry point. Generic resilience,
auth persistence, transport, and metrics stay in `infrastructure/`. Domain ports
stay in `domain/ports/` until a separate Phase 5 ADR says otherwise.

## Public API (domain-centric)

```python
from brokers import BrokerSession

session = BrokerSession.connect("dhan")

reliance = session.stock("RELIANCE")
quote = reliance.quote()
history = reliance.history(...)

session.gateway.place_order(...)
session.gateway.orders()
session.gateway.positions()
session.gateway.funds()
session.gateway.subscribe([reliance])

session.extension(SomeExtension)
session.close()
```

| Owner | Responsibility |
|---|---|
| `BrokerSession` | Lifecycle, connect, instrument factory, `.gateway`, `.extension()` |
| `Instrument` | Market data: quote, history, depth, option_chain |
| `BrokerGateway` | Broker ops: orders, portfolio, funds/margin, subscribe |

Exactly one public path per action. No long-term `gateway.quote` vs `stock.quote`.

## Internal layering

```text
Application
    → brokers.BrokerSession / BrokerGateway  (facade)
    → domain ports + Instrument
    → infrastructure (auth, resilience)
    → providers (dhan / upstox / paper)
    → broker HTTP/WS
```

## Migration phases

1. **Public API** — add `BrokerGateway`; deprecate instrument/session trading & subscribe wrappers; no file moves.
2. **Internal cleanup** — delete dead abstractions; shared rate-limit config tables; tighten error mapping.
3. **Provider layout** — move to `brokers/providers/{dhan,upstox,paper}/`.
4. **Delete** — remove `BrokerSession` trading/subscribe dual paths; instrument OMS helpers remain with `DeprecationWarning` until call-site migration completes.
5. **Domain ADR** — **Accepted ADR-0014:** keep ports in `domain/ports/` (no `domain/brokers/`).

## Constraints

- Every phase releasable (tests green).
- ADR-0012: operator live money remains paper-only; gateway orders use OMS/`RuntimeBundle.execution`.
- No restoring `brokers/cli|certification|diagnostics`.
- Prefer deletion over new abstractions.

## Related

- Plan: `docs/superpowers/plans/2026-07-21-broker-hybrid-facade.md`
- Constitution gap analysis: `docs/constitution/09-broker-subsystem-gap-analysis.md`
