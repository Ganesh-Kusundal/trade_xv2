# Brokers purity — delete CLI / certification / diagnostics

**Date:** 2026-07-21  
**Status:** Approved (user: go)  
**Mode:** Delete (option 1)

## Intent

Keep `src/brokers` as adapter plugins only. Remove presentation and tooling packages that block purity.

## Delete

- `src/brokers/cli/`
- `src/brokers/certification/`
- `src/brokers/diagnostics/`
- `src/brokers/platform_ops.py`
- `src/brokers/services/platform_ops.py`
- `src/brokers/services/operations.py`
- `pyproject.toml` script `broker = "brokers.cli.broker:broker"`
- Tests/scripts that only exist for the deleted surface

## Carve-out

Move `is_nse_market_open` to `plugins/exchanges/nse/` so `paper_orders` fill gating keeps working.

## Downstream

- `tradex.cli`: drop `tradex broker`; keep `config` via relocated preferences; replace `_render.present` with click.echo/json
- `runtime/platform_bridge`: remove doctor/verify/benchmark/certify bridges
- UI certify/doctor/benchmark commands that only called deleted ops: remove registration

## Keep

`dhan/`, `upstox/`, `paper/`, `common/`, `session/`, `services/` (market/orders/portfolio), `runtime/` managers, `exceptions/`, `extensions/`
