# ADR-0001: Adopt Keep a Changelog format

**Status:** Accepted (Phase 0)
**Date:** YYYY-MM-DD

## Context

Software projects accumulate changes. Without a structured record:
- Users don't know what changed between versions
- New contributors don't know what's current
- Bug fixes get lost in the noise of feature commits

The Trade_XV2 project has had no changelog until now.

## Decision

We adopt the [Keep a Changelog](https://keepachangelog.com/) format,
versioned in [SemVer](https://semver.org/), for `CHANGELOG.md`.

Categories (in order): `Added`, `Changed`, `Deprecated`, `Removed`,
`Fixed`, `Security`.

## Consequences

**Positive:**
- Predictable structure for users
- Easy to auto-generate release notes
- Versioned history

**Negative:**
- Must remember to update on every PR (mitigated by CI check in Phase 7)
- Adds ceremony for small changes

## Alternatives considered

1. **Auto-generated from git log** — rejected: too noisy, no curation
2. **GitHub Releases only** — rejected: invisible to non-GitHub readers
3. **No changelog** — rejected: violates Dr. V.'s "documentation is a feature" rule

## Notes

The Build Engineer will add a CI check in Phase 7 that fails the build
if `CHANGELOG.md` is not updated when source files change.
