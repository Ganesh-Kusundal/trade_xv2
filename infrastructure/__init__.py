"""Infrastructure layer — cross-cutting concerns shared across the system.

This package contains infrastructure services that are not domain-specific
but are required by multiple layers:

- **event_bus/** — Synchronous and asynchronous event publishing/subscription
- (future) **logging/** — Structured logging configuration
- (future) **metrics/** — Observability and metrics collection
- (future) **cache/** — Caching abstractions

These services implement domain-defined ports (protocols) from
:mod:`domain.ports` so that domain-adjacent code depends on interfaces,
not on concrete implementations.
"""
