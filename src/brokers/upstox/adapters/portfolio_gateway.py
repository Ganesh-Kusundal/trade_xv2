"""PortfolioGateway — positions, holdings, and balance queries.

Responsibility: Fetch account portfolio data including positions, holdings,
and fund limits. Thin wrapper over the existing PortfolioAdapter.
Thread-safe: All methods are stateless and thread-safe.
"""

from __future__ import annotations

from typing import Any

from domain.entities import Balance, Holding, Position


class PortfolioGateway:
    """Portfolio operations — funds, positions, holdings.

    Encapsulates:
    - Fund limits and available balance
    - Position tracking (open/closed)
    - Holdings (long-term equity)

    Thread Safety:
        All methods are stateless and thread-safe. Delegates to PortfolioAdapter.

    Example::

        gw = PortfolioGateway(portfolio_adapter)
        balance = gw.funds()
        positions = gw.positions()
        holdings = gw.holdings()
    """

    def __init__(self, portfolio_adapter: Any) -> None:
        """Initialize with PortfolioAdapter.

        Args:
            portfolio_adapter: PortfolioAdapter instance providing account data
        """
        self._portfolio = portfolio_adapter

    def funds(self) -> Balance:
        """Fetch account fund limits.

        Returns:
            Balance dataclass with available margin
        """
        return self._portfolio.get_funds()

    def positions(self) -> list[Position]:
        """Fetch all positions.

        Returns:
            List of Position dataclasses
        """
        return self._portfolio.get_positions()

    def holdings(self) -> list[Holding]:
        """Fetch all holdings.

        Returns:
            List of Holding dataclasses
        """
        return self._portfolio.get_holdings()
