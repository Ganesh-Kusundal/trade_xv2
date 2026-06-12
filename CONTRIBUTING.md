# Contributing to Trade_XV2

Thank you for your interest in contributing! This document covers the
process and conventions for contributing to Trade_XV2.

## Code of Conduct

Be respectful. Be kind. Assume good intent. Disagree on ideas, not on
people.

## Getting started

1. Read the [README](./README.md) for project overview.
2. Read [agent.md](./agent.md) (if present) for module-by-module guide.
3. Set up dev environment: `pip install -e ".[dev]"` and `pre-commit install`.
4. Run the test suite to verify: `pytest -m "not integration and not sandbox and not live_readonly" -q`.

## Workflow

1. **Branch** from `main`: `git checkout -b feat/my-feature`
2. **Code** following the conventions below.
3. **Test** with unit + contract tests.
4. **Verify**: `ruff check . && ruff format --check . && mypy brokers/`
5. **Commit** with [conventional commit](https://www.conventionalcommits.org/) format:
   - `feat:` new feature
   - `fix:` bug fix
   - `refactor:` code change without behavior change
   - `test:` test-only change
   - `docs:` documentation only
   - `chore:` tooling, CI, etc.
6. **Push** and open a Pull Request.

## Code conventions

### Style

- **Formatter**: `ruff format` (enforced in CI).
- **Linter**: `ruff check` (enforced in CI).
- **Line length**: 100 characters max.
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants.

### Type hints

- **Required** for all new code.
- Use `Optional[T]` for nullable values, not `T | None` (Python 3.10 compatibility).
- Use `Decimal` for money, never `float`.
- Use `datetime` with `tzinfo`, never naive.

### Testing

- **Required** for all new code. Target ≥80% line coverage on new modules.
- Use `unittest.mock.MagicMock(spec=ClassName)` for SDK mocks.
- Use `PaperBroker` for end-to-end tests that don't need a real network.
- Test files mirror source structure: `brokers/foo/bar.py` → `brokers/foo/tests/test_bar.py`.

### Commits

- Atomic commits. One logical change per commit.
- Reference the plan/issue in the message when applicable.
- Sign off commits: `git commit --signoff`.

## Pull Request template

```markdown
## What

<!-- Brief description of the change -->

## Why

<!-- Why is this needed? What problem does it solve? -->

## How

<!-- Implementation notes. Anything tricky? -->

## Tests

<!-- How did you test? What was the result? -->

## Risk

<!-- Any risks? Breaking changes? -->
```

## Review process

1. **CI must be green** (lint + tests).
2. **One approval** from a maintainer required.
3. **Squash and merge** to keep `main` history clean.

## Module ownership

See `CODEOWNERS` (to be added in Phase 8). For now:

- `brokers/common/` — core team
- `brokers/dhan/` — Dhan adapter team
- `brokers/upstox/` — Upstox adapter team
- `brokers/paper/` — paper trading team
- `cli/`, `oms/`, etc. — framework team

## Questions?

Open a GitHub Discussion or ask in the team Slack.
