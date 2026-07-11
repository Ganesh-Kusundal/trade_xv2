# Engineering Backlog — Trading OS (TOS-*)

**Security deferred:** DR-I3 / `src/infrastructure/security/**` (ADR-023).  
**Workflow:** direct commits (no PRs).  
**Canonical plan:** [TRADING-OS-EXECUTION-ROADMAP.md](./TRADING-OS-EXECUTION-ROADMAP.md)

## Done (including final remaining wave)

| Area | Deliverables |
|---|---|
| Trust / gates | import-linter 15/15, arch tests, mypy clean set + broker ratchet |
| Composition / concurrency | factory.build, broker_accessors, event_loop boundary |
| OMS spine | OrderCapabilityPort, ledger outbox, PortfolioContext mirror |
| Money/Quantity | Order/Position/Trade fields are Money/Quantity with coercion |
| FLOWS | Code recon matrix 2026-07-12 in FLOWS.md |
| Options | `application.options.OptionsCapability` |
| Strategy | `application.strategy_engine.LiveStrategyEngine` dry-run + kill-switch |
| Load / cert | baselines + T0–T4 artifacts under `docs/certification/` |
| MCP | doctor/diagnose/certify/benchmark parity |
| Migrate | `migrate_legacy_to_curated` wrapper |

## Artifacts

| Path | Purpose |
|---|---|
| `docs/certification/baselines/load_baseline_paper.json` | Load SLO baseline |
| `docs/certification/baselines/mypy_brokers_baseline.json` | Broker mypy error ratchet (626 seed) |
| `docs/certification/artifacts/T{0-4}_paper_latest.json` | Cert tiers |

## Regenerators

```bash
PYTHONPATH=src python scripts/verify/record_load_baseline.py
PYTHONPATH=src python scripts/verify/mypy_broker_ratchet.py
PYTHONPATH=src python scripts/verify/emit_cert_artifacts.py --broker paper
```

## Deferred

Security fail-closed encryption (ADR-023). T3/T4 live evidence remains manual.
