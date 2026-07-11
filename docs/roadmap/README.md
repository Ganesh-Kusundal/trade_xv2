# Roadmap — Trade_XV2 → Trading OS

| Doc | Purpose |
|---|---|
| **[TRADING-OS-EXECUTION-ROADMAP.md](./TRADING-OS-EXECUTION-ROADMAP.md)** | **Canonical** multi-phase execution plan (code-verified 2026-07-12). Direct commits; security deferred. |
| [ENGINEERING-BACKLOG-TOS.md](./ENGINEERING-BACKLOG-TOS.md) | TOS-* task backlog + done tracker |
| [EXECUTION-ROADMAP-2026-07-11.md](./EXECUTION-ROADMAP-2026-07-11.md) | Prior DR-*/TRANS phase plan (historical + §9 status) |
| [DEEP-REVIEW-2026-07-11.md](./DEEP-REVIEW-2026-07-11.md) | Evidence-backed DR-* findings register |

## Live status (2026-07-12 Series A)

| Check | Result |
|---|---|
| import-linter | **15 kept, 0 broken** |
| Extended-order component test | **Pass** (`OrderCapabilityPort`) |
| `@pytest.mark.architecture` | **Registered** |
| Security track (DR-I3) | **Deferred** |

### Done (not to redo)

DR-B1/B2/B3 · DR-F2–F5 · DR-E3 · DR-I2 · DR-T2/T4 · TOS-P3-001/002/003

### Next critical path

1. **P5 composition** (TOS-P5-001–003)  
2. **P5 concurrency** (TOS-P5-010a–e)  
3. **P5 ledger spine** (TOS-P5-020–022)  
4. Then VO/MarketSurface, P4 golden, P6, P7 ops  

Full audit table and task IDs: [TRADING-OS-EXECUTION-ROADMAP.md](./TRADING-OS-EXECUTION-ROADMAP.md).

## Workflow

- **Direct commits** on `refactor/structural-cleanup` (no PRs)  
- Per commit: `lint-imports` + relevant pytest  
- **Do not touch** `src/infrastructure/security/**`
