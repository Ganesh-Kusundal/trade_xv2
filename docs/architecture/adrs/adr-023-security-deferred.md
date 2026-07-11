# ADR-023: Security track deferred

**Status:** Accepted  
**Date:** 2026-07-12  
**Related:** DR-I3, TRANS-P7-I3

## Context

Token encryption (`SECRET_ENCRYPTION_KEY`), fail-closed live token stores, and CVE/`safety` merge gates are production-security concerns.

## Decision

This Trading OS transformation program **explicitly defers** security-track work:

- Do not require `SECRET_ENCRYPTION_KEY` for live brokers in this program.
- Do not rewrite `src/infrastructure/security/**` as part of TOS-* delivery.
- Do not claim unattended live capital safety from security controls.

Operational hardening (chaos, load, lifecycle, mypy) continues without security claims.

## Consequences

- Product sign-off for live capital must include a separate security workstream.
- CI may keep advisory (non-blocking) safety steps until that workstream lands.
