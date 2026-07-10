# TradeXV2 test suite

Tests are the **living specification** of platform guarantees. They describe
behavior that must remain true across refactors — not the history of how a
change was introduced.

## Pyramid

```text
                    E2E / Production Validation
                  ───────────────────────────────
                 tests/e2e, tests/chaos, sandbox

               Integration / Contract Tests
           ───────────────────────────────────────
         tests/integration, package */tests/integration

               Component / Service Tests
         ────────────────────────────────────────
        tests/component, application/*/tests

             Domain / Unit Tests
      ─────────────────────────────────
     tests/unit, domain/tests, value objects
```

| Layer | Directory | Question answered |
|-------|-----------|-------------------|
| Unit | `tests/unit/`, `src/domain/tests/` | Does this business rule work? |
| Component | `tests/component/`, `src/application/*/tests/` | Does this service behave correctly? |
| Integration | `tests/integration/`, broker `*/tests/integration/` | Do components collaborate? |
| E2E | `tests/e2e/`, `tests/chaos/` | Does the full system work? |
| Architecture | `tests/architecture/` | Do layering / import rules hold? |

Package-local tests under `src/**/tests` remain allowed for fast unit/component
coverage next to the code they protect. Prefer **behavioral file names**.

## Naming rules

**Good** (keep after a rewrite of the implementation):

- `test_duplicate_order_is_not_submitted_twice.py`
- `test_order_rejected_when_kill_switch_active.py`
- `test_process_oms_book_is_shared.py`

**Bad** (describes history, not guarantee):

- `test_b7_oms_wireup.py`
- `test_phase3.py`
- `test_after_refactor.py`
- `test_issue_127.py`

Heuristic: *If I rewrite the implementation tomorrow but keep the same external
behavior, would I keep this test?* If no, rewrite the test or delete it.

## Markers

See `pyproject.toml` `[tool.pytest.ini_options] markers`.

Common filters:

```bash
PYTHONPATH=src pytest -m unit
PYTHONPATH=src pytest tests/component -q
PYTHONPATH=src pytest tests/integration -q
PYTHONPATH=src pytest tests/e2e -q
PYTHONPATH=src pytest tests/architecture -q
```

## Adding a test

1. Pick the pyramid layer (not a sprint or phase folder).
2. Name the file after the guarantee.
3. Prefer real domain objects; mock only at trust boundaries (network, clock).
4. Do not import production code from `tests/` into `src/`.
