# Canonical scripts vs deprecated (TOS-P4-003)

Prefer SDK / CLI / MCP over ad-hoc scripts.

## Canonical

| Surface | Entry |
|---|---|
| CLI | `tradex` / `broker` (pyproject scripts) |
| MCP | `broker-mcp` |
| Doctor / certify | `broker doctor`, `broker certify` via `brokers.platform_ops` |
| Python SDK | `tradex.open_session` / `runtime.factory.build` |
| Golden save | `python -m analytics.replay.golden_dataset` (`GOLDEN_DIR` → `tests/fixtures/golden`) |
| Architecture | `lint-imports`, `pytest tests/architecture` |

## Deprecated / migration

| Path | Note |
|---|---|
| `scripts/verify/*` one-offs | Prefer `broker doctor` / platform_ops |
| `scripts/debug/*` | Local diagnostics only; not CI gates |
| Ad-hoc notebooks without golden fixtures | Use `examples/minimal_session` + fixtures |

New automation must extend `platform_ops` or CLI rather than adding a new top-level script without updating this list.
