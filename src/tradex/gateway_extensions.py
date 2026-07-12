"""Collect broker Extension instances for BrokerFacade (instrument.broker.*).

Extracted from ``tradex.session`` so the composition root stays focused on
wiring. ``collect`` gathers extension objects from the broker adapter factory,
the gateway's extension registry, and well-known ``get_extension`` names,
de-duplicating by name/type.
"""

from __future__ import annotations

from typing import Any


def add(ext: Any, exts: list[Any], seen: set[str]) -> None:
    """Append ``ext`` to ``exts`` unless it is a duplicate (by name/type)."""
    if ext is None:
        return
    key = getattr(ext, "name", None) or type(ext).__name__
    if key in seen:
        return
    seen.add(str(key))
    exts.append(ext)


def collect(gateway: Any, *, broker_id: str = "") -> list[Any]:
    """Build broker Extension instances for BrokerFacade (instrument.broker.*)."""
    exts: list[Any] = []
    seen: set[str] = set()

    if broker_id:
        try:
            from infrastructure.adapter_factory import get_broker_extension_classes

            for cls in get_broker_extension_classes(broker_id):
                try:
                    add(cls(gateway), exts, seen)
                except Exception:
                    continue
        except Exception:
            pass

    registry = getattr(gateway, "extension_registry", None)
    if registry is not None and hasattr(registry, "all"):
        try:
            for ext in registry.all():
                add(ext, exts, seen)
        except Exception:
            pass
    get_ext = getattr(gateway, "get_extension", None)
    if callable(get_ext):
        for name in (
            "depth_20",
            "depth_200",
            "depth_30",
            "depth20",
            "depth200",
            "depth30",
            "news",
            "super_order",
            "forever_order",
        ):
            try:
                add(get_ext(name), exts, seen)
            except Exception:
                continue
    return exts
