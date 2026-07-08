# ADR-001: `src/` Layout & Package Organization

## Status
Accepted (Phase 0)

## Context
The repository historically kept top-level packages (`domain/`, `markets/`,
`brokers/`, `analytics/`, `application/`, ...) at the repo root. As we re-platform
into a DDD-aligned, broker-agnostic framework, we need a stable, conventional
layout that cleanly separates the pure domain, infrastructure, plugins, and
delivery layers.

## Decision
Adopt a **src-layout**: all first-party importable packages live under `src/`.

```
src/
  domain/         # pure finance model — zero infra imports
  application/    # workflows/commands/queries (no business rules)
  infrastructure/ # implements domain ports only
  plugins/        # concrete broker/provider packages (dhan, upstox, paper, replay)
  api/            # FastAPI delivery
  ui/             # terminal / dashboard
```

`pyproject.toml` uses `[tool.setuptools.packages.find] where = ["src", "."]` so
packages under `src/` (e.g. `domain`, `application`) remain importable by their
package name (`import domain`, not `import src.domain`). Tests stay at repo-root
`tests/` plus co-located `src/**/tests/` and are collected via `testpaths`.

## Consequences
- Package names are stable across the move (`from domain.x import ...` unchanged).
- Future phases move `brokers/`, `analytics/`, `application/`, `api/`, `cli/` into
  `src/`; the `where = ["src", "."]` already supports a hybrid during migration.
- Build/tooling (ruff, mypy, import-linter, coverage) must reference package names,
  not filesystem paths under `src/`.
