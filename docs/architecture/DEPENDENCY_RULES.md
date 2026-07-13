# DEPENDENCY_RULES.md

> Canonical statement of the layer dependency rule. This is a thin pointer, not a duplicate —
> the enforced rule lives in two places that must stay in sync: `context/architecture.md` §3
> (human-readable contract) and `pyproject.toml`'s `[tool.importlinter]` section (machine-
> enforced contracts, CI-blocking for rules 1–4). See `DEPENDENCY_GRAPH.md` for the visual
> graph and the full list of import-linter contracts currently enforced.

## The rule (from `context/architecture.md` §3)

```
interfaces/      ──▶  runtime/ (composition root ONLY touches concretes)
runtime/         ──▶  infrastructure/ (adapters)  +  application/ (use-cases)
infrastructure/  ──▶  application/  (implements domain ports)
application/     ──▶  domain/  (entities, ports, events)
domain/          ──▶  (NOTHING inward — depends only on stdlib + itself)
```

1. `domain` may not import application/infrastructure/runtime/brokers/interface.
2. `application` may not import infrastructure/runtime/brokers/interface (a small,
   explicitly tracked set of debt edges is allowlisted — see `DEPENDENCY_GRAPH.md`).
3. `infrastructure` may not import runtime/interface.
4. `runtime` is the only layer permitted concrete broker/plugin imports.
5. `interface` may import application + runtime; never `brokers` directly (warning-level).

Changing this rule requires an ADR in `docs/architecture/adr/` (see ADR-0002, "Layer
dependency rule") — do not edit `context/architecture.md` §3 or the import-linter contracts
in `pyproject.toml` without one.
