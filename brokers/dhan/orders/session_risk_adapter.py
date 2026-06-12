"""Dhan session risk adapter."""

from __future__ import annotations

from typing import Any

from brokers.common.api.ports import SessionRiskProvider
from brokers.common.core.models import PnlExitPolicy, PnlExitResult
from brokers.common.resilience.retry import RetryExecutor
from brokers.dhan.auth.http import DhanAuthenticatedHttpClient
from brokers.dhan.auth.urls import DhanApiUrlResolver
from brokers.dhan.mapper.mapping import str_field


class DhanSessionRiskProvider(SessionRiskProvider):
    """Dhan session-risk adapter."""

    def __init__(
        self,
        http_client: DhanAuthenticatedHttpClient,
        url_resolver: DhanApiUrlResolver,
        retry_executor: RetryExecutor,
    ) -> None:
        self._http_client = http_client
        self._url_resolver = url_resolver
        self._retry_executor = retry_executor

    def enable_pnl_exit(self, policy: PnlExitPolicy) -> PnlExitResult:
        payload: dict[str, Any] = {
            "profit": float(policy.profit_threshold),
            "loss": float(policy.loss_threshold),
            "killSwitch": policy.enable_kill_switch,
        }
        response = self._retry_executor.execute(
            lambda: self._http_client.post_json(self._url_resolver.pnl_exit_url(), payload)
        )
        data = response.get("data") if isinstance(response, dict) else response
        if not isinstance(data, dict):
            data = response if isinstance(response, dict) else {}
        return PnlExitResult(
            enabled=True,
            status=str_field(data, "status", "pnlExitStatus"),
            message=str_field(data, "message", "remarks"),
        )
