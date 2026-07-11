# Engineering Backlog — Trading OS (TOS-*)

**Security deferred:** DR-I3 and `src/infrastructure/security/**` are out of scope (ADR-023).  
**Workflow:** direct commits on working branch (no PRs).  
**Canonical plan:** [TRADING-OS-EXECUTION-ROADMAP.md](./TRADING-OS-EXECUTION-ROADMAP.md)

## Done (core + polish)

| ID | Notes |
|---|---|
| TOS-P3-001/002/003 | import-linter 15/15, OrderCapabilityPort test, architecture marker |
| TOS-P3-004/005 | Expanded mypy clean set; documented advisory `continue-on-error` |
| TOS-P5-001/002/003 | factory.build, UI accessors, Dhan retry policies |
| TOS-P5-010/011 | event-loop boundary; stream/OMS RLock arch tests |
| TOS-P5-020/021/022 | bus goldens, order spine, PortfolioContext mirror |
| TOS-P4-001/002/003 | GOLDEN_DIR, MCP diagnose/benchmark, CANONICAL_SCRIPTS |
| TOS-P1-001–005 | ADRs, aliases, Money SSOT, Money helpers, plugin interface |
| TOS-P2-002/003 | wire boundary + fail-closed capital arch tests |
| TOS-P5-030 | runtime.market_defaults |
| TOS-P6-001/002/006/008/010 | strategy discover, lake chains, equity costs, dual API note, migrate wrapper |
| TOS-P7-001 polish | concurrent fills chaos test |
| TOS-P7-003 | EventBusAlertingService for LifecycleManager |
| TOS-P7-005/023 | ADR-022 / ADR-023 |

## Remaining continuous (optional product depth)

| Pri | ID | Description |
|---|---|---|
| P3 | TOS-P1-004 full | Replace Order/Position *fields* with Money/Quantity (helpers exist) |
| P3 | TOS-P2-001 | Full FLOWS.md line-by-line vs every runtime path |
| P3 | TOS-P6-003–005/007/009 | Full options product UI, live strategy engine, analytics port migration |
| P3 | TOS-P7-002/004/006/007 | Load baselines, config SSOT merge, full mypy brokers, live cert T0–T4 |

## Explicitly deferred

DR-I3 · token encryption · safety/CVE gates · `src/infrastructure/security/**`
