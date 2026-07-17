# ADR-011: File Size Limit

- **Status:** Accepted
- **Date:** 2026-07-17
- **Deciders:** Architecture review

## Context
God classes (>650 LOC) are hard to review, test, and maintain.

## Decision
Enforce 650 LOC per file. Files exceeding this limit must be decomposed into focused modules. Enforcement via CI pre-commit hook.

## Consequences
- Forces single responsibility at file level
- Makes code review manageable
