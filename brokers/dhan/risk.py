"""Session risk provider for Dhan.

Implements session risk calculation and monitoring for Dhan trades.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from brokers.common.core.enums import ExchangeSegment
from brokers.common.core.models import FundLimits, Position
from brokers.common.resilience.retry import RetryExecutor
from brokers.dhan.websocket.market_data import DhanMarketFeedWebSocketClient


class DhanSessionRiskProvider:
    """Session risk provider for Dhan.

    Calculates and monitors session risk for Dhan trades, including
    position risk, exposure limits, and margin requirements.
    """

    def __init__(
        self,
        http_client: Any,
        settings: Any,
        url_resolver: Any,
        retry_executor: RetryExecutor,
        websocket_client: DhanMarketFeedWebSocketClient | None = None,
    ) -> None:
        self._http_client = http_client
        self._settings = settings
        self._url_resolver = url_resolver
        self._retry_executor = retry_executor
        self._websocket_client = websocket_client

        # Risk tracking
        self._position_risk: dict[str, Decimal] = {}
        self._exposure_limits: dict[str, Decimal] = {}
        self._margin_requirements: dict[str, Decimal] = {}
        self._risk_alerts: list[dict[str, Any]] = []

        # Risk thresholds
        self._max_position_size = Decimal("100000")
        self._max_daily_loss = Decimal("50000")
        self._max_exposure_per_security = Decimal("20000")
        self._min_margin_buffer = Decimal("5000")

    def get_fund_limits(self) -> FundLimits:
        """Get current fund limits and margin details."""
        response = self._retry_executor.execute(
            lambda: self._http_client.get_json(self._url_resolver.fund_limits_url())
        )
        data = response.get("data", {})

        return FundLimits(
            available_balance=Decimal(str(data.get("availableBalance", 0))),
            used_margin=Decimal(str(data.get("usedMargin", 0))),
            total_margin=Decimal(str(data.get("totalMargin", 0))),
            collateral=Decimal(str(data.get("collateral", 0))),
            m2m_realized=Decimal(str(data.get("m2mRealized", 0))),
            m2m_unrealized=Decimal(str(data.get("m2mUnrealized", 0))),
        )

    def get_positions(self) -> list[Position]:
        """Get current positions."""
        response = self._retry_executor.execute(
            lambda: self._http_client.get_json(self._url_resolver.positions_url())
        )
        data = response.get("data", [])

        positions = []
        for item in data:
            position = Position(
                exchange_segment=ExchangeSegment(item.get("exchangeSegment", "NSE")),
                quantity=int(item.get("quantity", 0)),
                buy_quantity=int(item.get("buyQuantity", 0)),
                sell_quantity=int(item.get("sellQuantity", 0)),
                buy_average_price=Decimal(str(item.get("buyAveragePrice", 0))),
                sell_average_price=Decimal(str(item.get("sellAveragePrice", 0))),
                net_quantity=int(item.get("netQuantity", 0)),
                net_value=Decimal(str(item.get("netValue", 0))),
                unrealized_pnl=Decimal(str(item.get("unrealizedPnl", 0))),
                realized_pnl=Decimal(str(item.get("realizedPnl", 0))),
                product_type=ExchangeSegment(item.get("productType", "INTRADAY")),
                instrument_type=ExchangeSegment(item.get("instrumentType", "EQUITY")),
                last_price=Decimal(str(item.get("lastPrice", 0))),
                m2m_pnl=Decimal(str(item.get("m2mPnl", 0))),
            )
            positions.append(position)

        return positions

    def calculate_session_risk(self) -> dict[str, Any]:
        """Calculate comprehensive session risk."""
        positions = self.get_positions()
        fund_limits = self.get_fund_limits()

        risk_metrics = {
            "timestamp": datetime.now().isoformat(),
            "total_positions": len(positions),
            "total_exposure": Decimal("0"),
            "max_single_position": Decimal("0"),
            "total_unrealized_pnl": Decimal("0"),
            "total_realized_pnl": Decimal("0"),
            "risk_score": 0.0,
            "alerts": [],
        }

        # Calculate risk metrics
        for position in positions:
            exposure = abs(position.net_quantity) * position.last_price
            risk_metrics["total_exposure"] += exposure
            risk_metrics["total_unrealized_pnl"] += position.unrealized_pnl
            risk_metrics["total_realized_pnl"] += position.realized_pnl

            if exposure > risk_metrics["max_single_position"]:
                risk_metrics["max_single_position"] = exposure

            # Check individual position risk
            self._check_position_risk(position, risk_metrics)

        # Calculate overall risk score
        risk_metrics["risk_score"] = self._calculate_risk_score(risk_metrics, fund_limits)

        # Generate risk alerts
        risk_metrics["alerts"] = self._generate_risk_alerts(risk_metrics, fund_limits)

        return risk_metrics

    def _check_position_risk(self, position: Position, risk_metrics: dict[str, Any]) -> None:
        """Check risk for a single position."""
        exposure = abs(position.net_quantity) * position.last_price

        # Check position size limit
        if exposure > self._max_position_size:
            self._add_risk_alert(
                "position_size_exceeded",
                f"Position size {exposure} exceeds limit {self._max_position_size}",
                severity="high",
            )

        # Check exposure per security
        if exposure > self._max_exposure_per_security:
            self._add_risk_alert(
                "exposure_limit_exceeded",
                f"Exposure {exposure} exceeds limit {self._max_exposure_per_security}",
                severity="medium",
            )

        # Check margin requirements
        required_margin = exposure * Decimal("0.1")  # Assuming 10% margin requirement
        if required_margin > self._min_margin_buffer:
            self._add_risk_alert(
                "margin_requirement_low",
                f"Required margin {required_margin} below buffer {self._min_margin_buffer}",
                severity="low",
            )

    def _calculate_risk_score(self, risk_metrics: dict[str, Any], fund_limits: FundLimits) -> float:
        """Calculate overall risk score (0-100)."""
        score = 0.0

        # Position size risk (0-30 points)
        position_risk = min(risk_metrics["max_single_position"] / self._max_position_size, 1.0)
        score += position_risk * 30

        # Exposure risk (0-25 points)
        total_exposure_risk = min(
            risk_metrics["total_exposure"] / (fund_limits.available_balance * Decimal("0.5")), 1.0
        )
        score += total_exposure_risk * 25

        # P&L volatility risk (0-25 points)
        pnl_volatility = min(
            abs(risk_metrics["total_unrealized_pnl"]) / fund_limits.available_balance, 1.0
        )
        score += pnl_volatility * 25

        # Margin risk (0-20 points)
        margin_risk = min((fund_limits.used_margin / fund_limits.available_balance), 1.0)
        score += margin_risk * 20

        return min(score, 100.0)

    def _generate_risk_alerts(
        self,
        risk_metrics: dict[str, Any],
        fund_limits: FundLimits,
    ) -> list[dict[str, Any]]:
        """Generate risk alerts based on current risk metrics."""
        alerts = []

        # Check for high risk score
        if risk_metrics["risk_score"] > 75:
            alerts.append(
                {
                    "type": "high_risk_score",
                    "message": f"High risk score: {risk_metrics['risk_score']:.1f}",
                    "severity": "critical",
                    "timestamp": datetime.now().isoformat(),
                }
            )

        # Check for low margin buffer
        if fund_limits.available_balance < self._min_margin_buffer:
            alerts.append(
                {
                    "type": "low_margin_buffer",
                    "message": f"Low margin buffer: {fund_limits.available_balance}",
                    "severity": "high",
                    "timestamp": datetime.now().isoformat(),
                }
            )

        # Check for large unrealized losses
        if risk_metrics["total_unrealized_pnl"] < -self._max_daily_loss:
            alerts.append(
                {
                    "type": "large_unrealized_loss",
                    "message": f"Large unrealized loss: {risk_metrics['total_unrealized_pnl']}",
                    "severity": "medium",
                    "timestamp": datetime.now().isoformat(),
                }
            )

        return alerts

    def _add_risk_alert(self, alert_type: str, message: str, severity: str) -> None:
        """Add a risk alert."""
        alert = {
            "type": alert_type,
            "message": message,
            "severity": severity,
            "timestamp": datetime.now().isoformat(),
        }
        self._risk_alerts.append(alert)

    def get_risk_alerts(self) -> list[dict[str, Any]]:
        """Get current risk alerts."""
        return list(self._risk_alerts)

    def clear_risk_alerts(self) -> None:
        """Clear all risk alerts."""
        self._risk_alerts.clear()

    def subscribe_to_risk_updates(self, callback: callable) -> bool:
        """Subscribe to real-time risk updates."""
        if self._websocket_client:
            # In a real implementation, this would subscribe to risk WebSocket
            return True
        return False
