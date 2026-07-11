# Roadmap — Trade_XV2 → Trading OS

| Doc | Purpose |
|---|---|
| **[TRADING-OS-EXECUTION-ROADMAP.md](./TRADING-OS-EXECUTION-ROADMAP.md)** | Multi-phase execution plan |
| [ENGINEERING-BACKLOG-TOS.md](./ENGINEERING-BACKLOG-TOS.md) | TOS-* done + remaining polish |
| [EXECUTION-ROADMAP-2026-07-11.md](./EXECUTION-ROADMAP-2026-07-11.md) | Historical DR-* plan |
| [DEEP-REVIEW-2026-07-11.md](./DEEP-REVIEW-2026-07-11.md) | Findings register |

## Live status (2026-07-12 — program wave complete for core TOS-*)

| Check | Result |
|---|---|
| import-linter | **15/15** |
| Event-loop boundary | **0** ad-hoc outside `runtime.event_loop` |
| UI concrete brokers | **0** (via `runtime.broker_accessors`) |
| OMS broker-agnostic | **Yes** (`OrderCapabilityPort`) |
| Bus goldens | Dhan + Upstox |
| Order spine | Arch-enforced OMS + ledger outbox |
| Money SSOT | primitives = value_objects alias |
| VO wall-clock | via `ClockPort` |
| GOLDEN_DIR | `tests/fixtures/golden` |
| Security (DR-I3) | **Deferred** (ADR-023) |

### Remaining polish

Full Money/Quantity field migration on aggregates, deeper chaos/load, MCP parity gaps, full P6 capability packages — see backlog "Remaining / continuous".

### Workflow

- Direct commits (no PRs)
- Gates: `lint-imports` + `pytest tests/architecture`
- Do not touch `src/infrastructure/security/**`
