# Engineering Backlog — Trading OS (TOS-*)

**Security deferred:** DR-I3 and `src/infrastructure/security/**` are out of scope (ADR-023).  
**Workflow:** direct commits on working branch (no PRs).  
**Canonical plan:** [TRADING-OS-EXECUTION-ROADMAP.md](./TRADING-OS-EXECUTION-ROADMAP.md)

## Done

| ID | Notes |
|---|---|
| TOS-P3-001/002/003 | import-linter 15/15, OrderCapabilityPort test, architecture marker |
| TOS-P5-001/002/003 | factory.build, UI accessors, Dhan retry policies |
| TOS-P5-010/011 | single event-loop boundary; stream/OMS RLock arch tests |
| TOS-P5-020/021/022 | bus goldens, order spine, PortfolioContext mirror |
| TOS-P4-001/003 | GOLDEN_DIR + CANONICAL_SCRIPTS.md |
| TOS-P1-001 | ADR-021 BrokerAdapter vs Transport |
| TOS-P1-002 | TradingIntent / PersistedOrderIntent aliases + glossary |
| TOS-P1-003/004 | Money SSOT; no datetime.now in VOs; transitional Order Decimal |
| TOS-P1-005 | BrokerPluginInterface + checklist |
| TOS-P2-002 | wire boundary arch test |
| TOS-P5-030 | runtime.market_defaults from MarketSurface |
| TOS-P6-001 | StrategyPipeline registry.discover defaults |
| TOS-P6-002 | lake option_chain / future_chain readers |
| TOS-P6-006 | equity derivation with commission/slippage |
| TOS-P6-008 | DUAL_API_SURFACE.md deprecation note |
| TOS-P7-005/023 | ADR-022 state store; ADR-023 security deferred |

## Remaining / continuous (non-blocking polish)

| Pri | ID | Description |
|---|---|---|
| P2 | TOS-P4-002 | Full MCP/CLI doctor parity holes (if any remaining) |
| P2 | TOS-P2-001/003 | Full FLOWS.md recon vs code; fail-closed audit on every money path |
| P2 | TOS-P1-004 full | Migrate Order/Position fields to Money/Quantity (transitional now) |
| P2 | TOS-P6-003–005/007/009/010 | Full capability packages, indicators, parquet migrate |
| P2 | TOS-P7-001–004/006/007 | Expand chaos/load/lifecycle/mypy/cert artifacts |
| P2 | TOS-P3-004/005 | Expand mypy clean set; document advisory continue-on-error |

## Do not reopen without regression

All Done rows above · DR-B1/B2/B3 · DR-F2–F5 · DR-E3 · DR-I2 · DR-T2/T4

## Explicitly deferred

DR-I3 · token encryption · safety/CVE gates · `src/infrastructure/security/**`
