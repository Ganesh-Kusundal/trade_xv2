"""Shadow portfolio projection parity — ledger vs live position book (ADR-015)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from application.oms.ledger_authority import ledger_authority_enabled
from application.oms.position_manager import PositionManager
from domain.ledger_recovery import rebuild_projector_from_ledger
from domain.ports.execution_ledger import ExecutionLedgerPort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ShadowDrift:
    symbol: str
    exchange: str
    field: str
    ledger_value: str
    live_value: str


@dataclass
class ShadowParityReport:
    enabled: bool
    compared_symbols: int = 0
    drifts: list[ShadowDrift] = field(default_factory=list)

    @property
    def has_drift(self) -> bool:
        return bool(self.drifts)


def compare_ledger_vs_positions(
    ledger: ExecutionLedgerPort | None,
    position_manager: PositionManager,
) -> ShadowParityReport:
    """Rebuild positions from ledger fills and diff against the live book."""
    if not ledger_authority_enabled() or ledger is None:
        return ShadowParityReport(enabled=False)

    projected = rebuild_projector_from_ledger(ledger)
    live_by_key = {(p.exchange, p.symbol): p for p in position_manager.get_positions()}
    drifts: list[ShadowDrift] = []
    keys = set(live_by_key) | {(p.exchange, p.symbol) for p in projected.get_positions()}

    for exchange, symbol in sorted(keys):
        live = live_by_key.get((exchange, symbol))
        shadow = projected.get_position(symbol, exchange)
        live_qty = live.quantity if live else 0
        shadow_qty = shadow.quantity if shadow else 0
        if live_qty != shadow_qty:
            drifts.append(
                ShadowDrift(
                    symbol=symbol,
                    exchange=exchange,
                    field="quantity",
                    ledger_value=str(shadow_qty),
                    live_value=str(live_qty),
                )
            )
            continue
        if live_qty == 0:
            continue
        live_avg = str(live.avg_price if live else 0)
        shadow_avg = str(shadow.avg_price if shadow else 0)
        if live_avg != shadow_avg:
            drifts.append(
                ShadowDrift(
                    symbol=symbol,
                    exchange=exchange,
                    field="avg_price",
                    ledger_value=shadow_avg,
                    live_value=live_avg,
                )
            )

    report = ShadowParityReport(
        enabled=True,
        compared_symbols=len(keys),
        drifts=drifts,
    )
    if drifts:
        logger.warning(
            "ledger_shadow_drift count=%d symbols=%d",
            len(drifts),
            len(keys),
        )
    return report
