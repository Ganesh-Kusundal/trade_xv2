# Trading OS Architecture

This folder is the landing page for the institutional Trading OS target design.
Use it when the ask is to design the production architecture the platform should
evolve toward, not to review the current implementation.

| Document | Role |
|----------|------|
| **[TRADING_OS_BLUEPRINT.md](./TRADING_OS_BLUEPRINT.md)** | **Target** institutional Trading OS — first principles |
| [../CODE_REALITY_AND_PLAN.md](../CODE_REALITY_AND_PLAN.md) | **What the repo actually is + commit plan** (source-verified) |
| [../TARGET_SYSTEM_DESIGN.md](../TARGET_SYSTEM_DESIGN.md) | Near-term build spine |
| [../MODULE_PROGRAM.md](../MODULE_PROGRAM.md) | Module EXIT_MET sheets |
| [../../reports/PRODUCTION_BOARD_REVIEW_CODE_ONLY_2026-07-10.md](../../reports/PRODUCTION_BOARD_REVIEW_CODE_ONLY_2026-07-10.md) | Older board dump |

**Read order for implementation:** CODE_REALITY first → Module Program → Blueprint (direction).

## Blueprint Coverage

`TRADING_OS_BLUEPRINT.md` is the answer to the “battle-tested institutional
Trading OS architecture” prompt. It covers:

- Runtime kernel, bootstrap, broker, market data, OMS/trading, strategy,
  analytics, replay, and infrastructure runtimes.
- Startup, instrument, history, subscription, quote, option chain, order,
  position, portfolio, market depth, reconnect, recovery, paper, backtest, and
  AI-agent flows.
- Communication patterns, dependency rules, package ownership, state ownership,
  testing architecture, operational architecture, extension model, and Mermaid
  diagram pack.

Keep implementation plans separate from this file; the blueprint is the target
architecture, not a claim about what the current tree already guarantees.
