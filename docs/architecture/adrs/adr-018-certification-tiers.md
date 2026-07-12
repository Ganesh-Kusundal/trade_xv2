# ADR-018: Certification Truth Tiers

- **Status:** Accepted
- **Date:** 2026-07-11
- **Deciders:** Operations lane, Broker Platform

## Context

`broker certify` and production gates mixed paper-only evidence with live
broker checks. Operators could misread paper certification as live capital
readiness.

## Decision

### Tiers

| Tier | Scope | Capital | CI default |
|------|-------|---------|------------|
| **L0 — Static** | import-linter, arch tests, ruff | none | blocking |
| **L1 — Paper** | full matrix on `paper` broker | simulated | blocking |
| **L2 — Sandbox** | broker test env / dry-run | none | nightly |
| **L3 — Live** | real session, micro orders | material | manual only |

### Rules

1. Production enablement requires **L1 pass + L3 evidence** for the target broker.
2. Paper pass MUST NOT imply live pass — CLI JSON includes `"tier": "L1"`.
3. Results use ADR-019 vocabulary: `passed` | `failed` | `blocked`.
4. `blocked` (missing secrets, market closed) ≠ `failed`.

### Workflow mapping

- PR CI: L0 + L1
- `production_gate.yml`: L0 + L1 + optional L2
- Release: L3 checklist outside CI

## Consequences

- Certification matrix documents tier per check.
- Dashboards show tier badge on certify results.
- Audit report finding "paper ≠ live" is explicitly addressed.

## Compliance

- `DEVELOPER-PLATFORM.md`, `broker certify --json`
- TRANS-P4 certification expansion