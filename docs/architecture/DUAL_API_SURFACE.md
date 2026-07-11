# Dual API surface (`/live/` vs clean routers) — TOS-P6-008

## Status

**Deprecated-for-new-work:** prefer clean `interface.api.routers` modules.

The parallel package `interface.api.routers.live` remains for backward-compatible
live broker endpoints (webhook, extended orders, etc.). New features must land
on the clean router tree; migrate live endpoints opportunistically.

## Rule

| Do | Don't |
|---|---|
| Add routes under `interface.api.routers` | Add new modules under `routers/live` unless migrating |
| Share services via application layer | Duplicate OMS logic in live routers |

## Exit

When `/live/` route count is zero or fully re-exported as thin aliases, delete this note.
