"""P&L Based Exit adapter — auto-exit when profit/loss thresholds hit (Trader's Control)."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from brokers.common.transport_errors import map_transport_exception
from brokers.dhan.api.http_client import DhanHttpClient
from brokers.dhan.domain import PnlExitConfig, PnlExitStatus
from brokers.dhan.exceptions import PnlExitError

logger = logging.getLogger(__name__)


class PnlExitAdapter:
    """Adapter for Dhan P&L Based Exit API (``/pnlExit``).

    Configured rules stay active for the current trading day only.
    """

    def __init__(self, client: DhanHttpClient):
        self._client = client

    def configure(
        self,
        *,
        profit_value: Decimal | float | str | None = None,
        loss_value: Decimal | float | str | None = None,
        product_types: list[str] | None = None,
        enable_kill_switch: bool = False,
    ) -> PnlExitStatus:
        """Configure automatic exit on cumulative P&L thresholds.

        Args:
            profit_value: Target profit amount that triggers exit (optional).
            loss_value: Target loss amount that triggers exit (optional).
            product_types: Products covered, e.g. ``["INTRADAY", "CNC"]``.
            enable_kill_switch: Also activate kill switch when threshold hits.

        Returns:
            Parsed :class:`PnlExitStatus`.

        Raises:
            ValueError: If neither profit nor loss is provided.
            PnlExitError: If the API call fails.
        """
        if profit_value is None and loss_value is None:
            raise ValueError("At least one of profit_value or loss_value is required")

        payload: dict[str, Any] = {
            "enableKillSwitch": bool(enable_kill_switch),
        }
        if profit_value is not None:
            payload["profitValue"] = str(Decimal(str(profit_value)))
        if loss_value is not None:
            payload["lossValue"] = str(Decimal(str(loss_value)))
        if product_types:
            payload["productType"] = [str(p).upper() for p in product_types]

        try:
            data = self._client.post("/pnlExit", json=payload)
        except Exception as exc:
            mapped = map_transport_exception(exc)
            raise PnlExitError(str(mapped)) from mapped

        status = self._parse_status(data)
        logger.info(
            "pnl_exit_configured",
            extra={
                "status": status.status,
                "profit": str(status.profit_value) if status.profit_value is not None else None,
                "loss": str(status.loss_value) if status.loss_value is not None else None,
            },
        )
        return status

    def stop(self) -> PnlExitStatus:
        """Disable the active P&L based exit for the session."""
        try:
            data = self._client.delete("/pnlExit")
        except Exception as exc:
            mapped = map_transport_exception(exc)
            raise PnlExitError(str(mapped)) from mapped

        status = self._parse_status(data)
        logger.info("pnl_exit_stopped", extra={"status": status.status})
        return status

    def get(self) -> PnlExitConfig:
        """Fetch the currently active P&L based exit configuration."""
        try:
            data = self._client.get("/pnlExit")
        except Exception as exc:
            mapped = map_transport_exception(exc)
            raise PnlExitError(str(mapped)) from mapped

        raw = data.get("data", data) if isinstance(data, dict) else {}
        if not isinstance(raw, dict):
            raw = {}

        status = str(raw.get("pnlExitStatus", raw.get("status", "INACTIVE")) or "INACTIVE")
        product = raw.get("productType") or raw.get("product_types") or []
        if isinstance(product, str):
            product = [product]

        profit = raw.get("profit", raw.get("profitValue"))
        loss = raw.get("loss", raw.get("lossValue"))
        kill = raw.get("enable_kill_switch", raw.get("enableKillSwitch", False))

        config = PnlExitConfig(
            status=status.upper(),
            profit_value=Decimal(str(profit)) if profit is not None and str(profit) != "" else None,
            loss_value=Decimal(str(loss)) if loss is not None and str(loss) != "" else None,
            product_types=tuple(str(p).upper() for p in product),
            enable_kill_switch=bool(kill),
            message=str(raw.get("message", "") or ""),
        )
        logger.info("pnl_exit_fetched", extra={"status": config.status})
        return config

    def _parse_status(self, data: Any) -> PnlExitStatus:
        raw = data.get("data", data) if isinstance(data, dict) else {}
        if not isinstance(raw, dict):
            raw = {}
        status = str(raw.get("pnlExitStatus", raw.get("status", "")) or "")
        return PnlExitStatus(
            status=status.upper() if status else "UNKNOWN",
            message=str(raw.get("message", "") or ""),
            profit_value=(
                Decimal(str(raw["profitValue"]))
                if raw.get("profitValue") is not None
                else (Decimal(str(raw["profit"])) if raw.get("profit") is not None else None)
            ),
            loss_value=(
                Decimal(str(raw["lossValue"]))
                if raw.get("lossValue") is not None
                else (Decimal(str(raw["loss"])) if raw.get("loss") is not None else None)
            ),
        )
