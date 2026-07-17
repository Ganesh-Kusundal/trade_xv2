# ADR-0010: Events/Types Split

- **Status:** Accepted
- **Date:** 2026-07-17
- **Deciders:** Architecture review

## Context
Domain events and type definitions were co-located, causing coupling between event producers and consumers.

## Decision
Split domain events into `domain/events/` with clear topic hierarchy. Type definitions remain in `domain/types/`.

## Consequences
- Events can be published without importing all type definitions
- Consumers subscribe to specific event topics
