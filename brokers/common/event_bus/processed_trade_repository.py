"""Idempotency ledger for trade events.

A ``trade`` from a broker is the most dangerous event in the system:
double-processing it doubles a position, which loses money.

The :class:`ProcessedTradeRepository` records every trade id we have
already accepted and rejects duplicates with a loud, observable outcome.

Storage
-------
Two layers, both thread-safe:

1. **In-memory** (always): ``set[TradeIdKey]`` for fast lookups.
2. **Persistent** (optional): a JSONL file append-only, fsynced on
   write. Replayed at startup so restarts don't reintroduce duplicates.

Key construction
----------------
A trade is identified by **two** ids when the broker provides them
(``trade_id`` + ``broker_trade_id``), falling back to just the broker
``trade_id`` otherwise. Constructing the key defensively means a
malformed payload cannot sneak past the dedup check.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TradeIdKey:
    """Canonical identifier for a trade.

    Two trades are considered the same if and only if their
    :class:`TradeIdKey` compares equal.
    """

    trade_id: str
    broker_trade_id: str | None = None
    order_id: str | None = None

    def __post_init__(self) -> None:
        if not self.trade_id:
            raise ValueError("TradeIdKey requires a non-empty trade_id")
        # Defensive normalisation.
        object.__setattr__(self, "trade_id", str(self.trade_id).strip())
        if self.broker_trade_id is not None:
            object.__setattr__(
                self, "broker_trade_id", str(self.broker_trade_id).strip()
            )
        if self.order_id is not None:
            object.__setattr__(self, "order_id", str(self.order_id).strip())

    @classmethod
    def from_trade(cls, trade: Any) -> "TradeIdKey":
        """Build a key from a domain ``Trade`` (or any duck-typed object)."""
        trade_id = getattr(trade, "trade_id", "") or ""
        broker_trade_id = (
            getattr(trade, "broker_trade_id", None)
            or getattr(trade, "exchange_trade_id", None)
            or None
        )
        order_id = getattr(trade, "order_id", None) or None
        return cls(
            trade_id=trade_id,
            broker_trade_id=broker_trade_id,
            order_id=order_id,
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "TradeIdKey":
        """Build a key from a raw event payload ``{"trade": Trade(...)}``."""
        trade = payload.get("trade")
        if trade is not None:
            return cls.from_trade(trade)
        return cls(
            trade_id=str(payload.get("trade_id", "")),
            broker_trade_id=payload.get("broker_trade_id"),
            order_id=payload.get("order_id"),
        )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "trade_id": self.trade_id,
            "broker_trade_id": self.broker_trade_id,
            "order_id": self.order_id,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TradeIdKey":
        return cls(
            trade_id=str(raw.get("trade_id", "")),
            broker_trade_id=raw.get("broker_trade_id"),
            order_id=raw.get("order_id"),
        )


class ProcessedTradeRepository:
    """Idempotency ledger for trade events.

    Parameters
    ----------
    persistence_path:
        Optional path to a JSONL file used to durably record every
        processed trade. When omitted, the ledger is in-memory only.
    on_duplicate:
        Optional callback invoked when a duplicate is detected. Useful
        for emitting a metric without coupling this class to a metrics
        implementation.
    max_age_seconds:
        Maximum age in seconds for in-memory entries. Entries older than
        this are evicted during cleanup. Default: 86400 (24 hours).
        Set to 0 to disable eviction.
    """

    def __init__(
        self,
        persistence_path: str | Path | None = None,
        on_duplicate=None,
        max_age_seconds: int = 86400,
    ) -> None:
        self._lock = threading.RLock()
        self._seen: set[TradeIdKey] = set()
        self._key_timestamps: dict[TradeIdKey, float] = {}
        self._max_age_seconds = max_age_seconds
        self._path = Path(persistence_path) if persistence_path else None
        self._on_duplicate = on_duplicate
        self._duplicates_observed = 0
        self._total_processed = 0
        self._evicted = 0
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()

    # ── Public API ────────────────────────────────────────────────────────

    def is_processed(self, key: TradeIdKey) -> bool:
        with self._lock:
            return key in self._seen

    def mark_processed(self, key: TradeIdKey) -> bool:
        """Record ``key`` as processed.

        Returns True if the key was *new* (caller should apply the trade).
        Returns False if the key was already present (caller MUST skip).
        """
        if not key.trade_id:
            raise ValueError(
                "ProcessedTradeRepository.mark_processed requires a "
                "non-empty trade_id"
            )
        import time

        with self._lock:
            if key in self._seen:
                self._duplicates_observed += 1
                if self._on_duplicate is not None:
                    try:
                        self._on_duplicate(key)
                    except Exception:
                        logger.exception(
                            "ProcessedTradeRepository: on_duplicate raised"
                        )
                logger.info(
                    "ProcessedTradeRepository: duplicate trade %s ignored",
                    key.trade_id,
                )
                return False
            self._seen.add(key)
            self._key_timestamps[key] = time.time()
            self._total_processed += 1
            if self._path is not None:
                self._append_to_disk(key)
            return True

    def process(self, key: TradeIdKey) -> bool:
        """Alias for :meth:`mark_processed`. Returns True on first sight."""
        return self.mark_processed(key)

    def contains(self, key: TradeIdKey) -> bool:
        return self.is_processed(key)

    def size(self) -> int:
        with self._lock:
            return len(self._seen)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "size": len(self._seen),
                "duplicates_observed": self._duplicates_observed,
                "total_processed": self._total_processed,
                "evicted": self._evicted,
            }

    def clear(self) -> None:
        """Wipe in-memory state. Persistence file is left untouched."""
        with self._lock:
            self._seen.clear()
            self._key_timestamps.clear()
            self._duplicates_observed = 0
            self._total_processed = 0

    def cleanup(self) -> int:
        """Evict entries older than max_age_seconds.

        Returns the number of entries evicted.
        """
        if self._max_age_seconds <= 0:
            return 0
        import time

        now = time.time()
        cutoff = now - self._max_age_seconds
        evicted = 0
        with self._lock:
            expired = [k for k, ts in self._key_timestamps.items() if ts < cutoff]
            for key in expired:
                self._seen.discard(key)
                del self._key_timestamps[key]
                evicted += 1
            self._evicted += evicted
        if evicted > 0:
            logger.info(
                "ProcessedTradeRepository: evicted %d expired entries (age>%ds)",
                evicted,
                self._max_age_seconds,
            )
        return evicted

    # ── Persistence ───────────────────────────────────────────────────────

    def _append_to_disk(self, key: TradeIdKey) -> None:
        assert self._path is not None
        record = {
            **key.to_dict(),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        line = json.dumps(record, separators=(",", ":"), sort_keys=True)
        # Append-only; crash-safe.
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except (OSError, ValueError):
                # Filesystem may not support fsync (e.g. some CI sandboxes).
                pass

    def _load_from_disk(self) -> None:
        assert self._path is not None
        if not self._path.exists():
            return
        loaded = 0
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    logger.warning(
                        "ProcessedTradeRepository: corrupt line in %s: %s",
                        self._path,
                        exc,
                    )
                    continue
                try:
                    key = TradeIdKey.from_dict(record)
                except ValueError:
                    continue
                self._seen.add(key)
                loaded += 1
        self._total_processed = loaded
        logger.info(
            "ProcessedTradeRepository: loaded %d processed trades from %s",
            loaded,
            self._path,
        )
