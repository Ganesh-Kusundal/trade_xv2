# Engineering Backlog — Trading OS (TOS-*)

**Security deferred:** DR-I3 and `src/infrastructure/security/**` are out of scope.  
**Workflow:** direct commits on working branch (no PRs).  
**Canonical plan:** [TRADING-OS-EXECUTION-ROADMAP.md](./TRADING-OS-EXECUTION-ROADMAP.md)

## Done

| ID | Notes |
|---|---|
| TOS-P3-002 | Extended-order registry test expects `OrderCapabilityPort` |
| TOS-P3-001 | Pure `application.oms.ledger_authority`; import-linter **15/15** |
| TOS-P3-003 | Registered `@pytest.mark.architecture` in pyproject.toml |
| TOS-P5-003 | Dhan retry policies module; single infra RetryExecutor |
| TOS-P5-001 | `runtime.factory.build` + compose arch test |
| TOS-P5-002 | Concrete broker accessors in `runtime.broker_accessors`; UI clean |
| TOS-P5-010 | All `new_event_loop` only in `runtime.event_loop` (0 baseline) |

## Next up (priority order)

| Pri | ID | Description |
|---|---|---|
| P0 | TOS-P5-011 | Stream→OMS lock discipline tests |
| P1 | TOS-P1-001 | ADR-021 port freeze |
| P1 | TOS-P1-002 | Glossary dual OrderIntent / Instrument |
| P1 | TOS-P1-003/004 | Money/Clock unify + adopt |
| P1 | TOS-P1-005 | BrokerPluginInterface design |
| P1 | TOS-P2-001–003 | Flows reconcile, wire boundary, fail-closed capital |
| P1 | TOS-P4-002/003 | MCP/CLI parity + script list |
| P1 | TOS-P5-030 | MarketSurface at composition edges |
| P2 | TOS-P6-001–010 | Feature capabilities |
| P2 | TOS-P7-001–007 | Ops hardening (no security) |
| P2 | TOS-P3-004/005 | Expand mypy; document continue-on-error |

## Do not reopen without regression

DR-B1/B2/B3 · DR-F2–F5 · DR-E3 · DR-I2 · DR-T2/T4 · TOS-P5-001/002/003/010/020/021/022 · TOS-P4-001

## Explicitly deferred

DR-I3 · token encryption · safety/CVE gates · `src/infrastructure/security/**`
