# ADR-014: Brokers as Trading OS Mini-OS

- **Status:** Accepted
- **Date:** 2026-07-11
- **Deciders:** Chief Quant Architect, Broker Platform Division

## Context

The brokers module must behave like a mini operating system for market
connectivity: a stable public SDK (`BrokerSession → Instrument`), internal
runtime coordinators, broker plugins, and first-class developer tooling (CLI,
MCP, certification, diagnostics).

Historically the package exposed gateway-centric transport types
(`DhanBrokerGateway`, `UpstoxBrokerGateway`) as the primary integration path.
Product code should never depend on those types.

## Decision

1. **Public surface** is `BrokerSession` over rich `domain/` instruments.
   Transport boundary is **`brokers.<broker>.wire`** (`DhanWireAdapter`,
   `UpstoxWireAdapter`). Legacy `gateway.py` modules are **removed**; wire
   adapters own the full port surface.

2. **Three equivalent interfaces** share `brokers.services` as the single core:
   - Python SDK (`BrokerSession`)
   - CLI (`broker` command)
   - MCP server (`brokers.mcp`)

3. **Certification is mandatory** for production readiness:
   `broker verify <broker>` and `BrokerCertifier` run the same matrix for
   paper, dhan, and upstox.

4. **Domain types stay in `domain/`** — the mental model `brokers/domain/`
   maps to `domain/instruments`, `domain/candles`, `domain/options`; no
   physical relocation (Clean Architecture import-linter contracts).

5. **Runtime managers** (`RuntimeBundle`) coordinate subscribe/history/quote/
   execution lifecycles at the session level; market behavior remains on
   instruments and plugins.

6. **Startup self-test** is opt-in via `TRADEX_BROKER_SELFTEST=1` on
   `tradex.connect` / `open_session` (not on `BrokerSession` used by CLI verify).

7. **Connect invariant:** all live paths MUST pass `bootstrap_gateway`
   (`require_gateway`, `BrokerSession`, `tradex.open_session`, CLI
   `connect_live`). `_create_transport_gateway` and broker factory `.create()`
   are private to `infrastructure.gateway.factory`. UI commands use
   `interface.ui.services.connect` shims only.

## Consequences

- Engineers and AI agents run `broker doctor` / `broker verify` before debugging.
- CI gates PRs with `broker verify paper` and certification unit tests.
- Nightly live certify: `.github/workflows/broker_live_certify.yml` (skips without secrets).
- New brokers add `plugins/<name>/plugin.py` + wire adapter + certification pass.
- Kernel extraction (`ReconnectingTransport`, ACL, `TokenLifecycle`, use-case layer)
  lives in `brokers/common/`; broker packages implement wire adapters only.
- Plugin registration: `brokers/plugins/{dhan,upstox,paper}/`; transport code
  remains at `brokers/{dhan,upstox,paper}/` with wire as the sanctioned entry.

## Rejected

- Relocating `domain/` into `brokers/domain/` (breaks layer boundaries).
- Separate code paths for CLI vs SDK vs MCP (violates §12 single-core rule).
- Zerodha as a supported broker (see ADR-013).
