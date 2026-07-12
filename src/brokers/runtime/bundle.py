"""RuntimeBundle — session-scoped coordinator for broker runtime managers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from brokers.runtime.capability_manager import CapabilityManager
from brokers.runtime.event_bus import EventBusFacade
from brokers.runtime.execution_manager import ExecutionManager
from brokers.runtime.historical_manager import HistoricalManager
from brokers.runtime.quote_manager import QuoteManager
from brokers.runtime.subscription_manager import SubscriptionManager
from brokers.runtime.symbol_registry import SymbolRegistry
from domain.universe import Session as DomainSession


@dataclass
class StartupCheckpoint:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class RuntimeBundle:
    """Thin coordinators over a composition-root session."""

    session: DomainSession
    subscriptions: SubscriptionManager = field(default_factory=SubscriptionManager)
    history: HistoricalManager = field(default_factory=HistoricalManager)
    quotes: QuoteManager = field(default_factory=QuoteManager)
    execution: ExecutionManager | None = field(default=None, repr=False)
    capabilities: CapabilityManager = field(default_factory=CapabilityManager)
    symbols: SymbolRegistry = field(default_factory=SymbolRegistry)
    events: EventBusFacade | None = field(default=None, repr=False)
    checkpoints: list[StartupCheckpoint] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.execution = ExecutionManager(self.session)
        bus = getattr(self.session, "event_bus", None)
        self.events = EventBusFacade(bus) if bus is not None else EventBusFacade(None)

    def record_startup(self) -> list[StartupCheckpoint]:
        """Observable startup checkpoints for doctor / self-test."""
        self.checkpoints.clear()
        broker_id = getattr(getattr(self.session, "status", None), "broker_id", "unknown")
        self._add("Load Plugin", True, broker_id)
        st = getattr(self.session, "status", None)
        self._add(
            "Authenticate",
            bool(getattr(st, "authenticated", False)),
            getattr(st, "mode", "?"),
        )
        self._add(
            "Load Symbol Master",
            bool(getattr(st, "instruments_loaded", False)),
        )
        try:
            inst = self.session.universe.equity("RELIANCE")
            caps = self.capabilities.capabilities(inst)
            self._add("Capability Discovery", True, f"{len(caps)} caps")
        except Exception as exc:  # noqa: BLE001
            self._add("Capability Discovery", False, str(exc))
        try:
            inst = self.session.universe.equity("RELIANCE")
            q = self.quotes.quote(inst)
            self._add("Warm Cache", q is not None, "sample quote")
        except Exception as exc:  # noqa: BLE001
            self._add("Warm Cache", False, str(exc))
        self._add("Ready", all(c.ok for c in self.checkpoints), "startup complete")
        return list(self.checkpoints)

    def _add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checkpoints.append(StartupCheckpoint(name, ok, detail))
