"""Dhan-internal instrument resolution surface."""

from brokers.dhan.instruments.resolution import ResolvedInstrument

__all__ = ["ResolvedInstrument"]


def __getattr__(name: str):
    if name == "DhanInstrumentMixin":
        from brokers.dhan.instruments.mixin import DhanInstrumentMixin

        return DhanInstrumentMixin
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
