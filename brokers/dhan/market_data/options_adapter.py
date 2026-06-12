"""Options adapter for Dhan."""

from __future__ import annotations

from brokers.common.api.ports import OptionsProvider
from brokers.common.core.enums import ExchangeSegment
from brokers.common.core.models import OptionContract
from brokers.dhan.market_data.options import DhanOptionsClient


class DhanOptionsAdapter(OptionsProvider):
    """Trade_J-style options adapter over ``DhanOptionsClient``."""

    def __init__(self, options_client: DhanOptionsClient) -> None:
        self._options_client = options_client

    @property
    def options_client(self) -> DhanOptionsClient:
        return self._options_client

    def get_expiries(self, underlying: str, exchange_segment: ExchangeSegment) -> list[str]:
        return self._options_client.get_expiries(underlying, exchange_segment)

    def get_option_chain(
        self,
        underlying: str,
        exchange_segment: ExchangeSegment,
        expiry: str,
    ) -> list[OptionContract]:
        return self._options_client.get_parsed_option_chain(
            underlying,
            exchange_segment,
            expiry,
        )
