"""Options client for Dhan.

Implements options functionality for futures and options contracts.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from brokers.common.core.enums import ExchangeSegment, InstrumentType
from brokers.common.core.models import OptionContract
from brokers.common.resilience.retry import RetryExecutor
from brokers.dhan.mapper.dhan_segment_mapper import to_wire_value as _seg_wire

logger = logging.getLogger(__name__)


def _coerce_security_id(security_id: str):
    if security_id.isdigit():
        return int(security_id)
    return security_id


class DhanOptionsClient:
    """Options client — expiry list, option chain, Greeks, etc.

    Design reference: Trade_J ``DhanOptionsClient``.
    """

    def __init__(
        self,
        http_client: Any,
        settings: Any,
        url_resolver: Any,
        retry_executor: RetryExecutor,
        rolling_option_client: DhanRollingOptionClient | None = None,
    ) -> None:
        self._http_client = http_client
        self._settings = settings
        self._url_resolver = url_resolver
        self._retry_executor = retry_executor
        self._rolling_option_client = rolling_option_client
        self._cooldown = 3.1
        self._last_request_times: dict[tuple[str, str], float] = {}

    def get_expiries(
        self,
        underlying: str,
        exchange_segment: ExchangeSegment,
    ) -> list[str]:
        """Get available expiry list from Dhan's API."""
        response = self._retry_executor.execute(
            lambda: self._http_client.post_json(
                self._url_resolver.option_chain_expiry_list_url(),
                {
                    "UnderlyingScrip": _coerce_security_id(underlying),
                    "UnderlyingSeg": _seg_wire(exchange_segment),
                },
            )
        )
        data = response.get("data", {})
        if isinstance(data, dict):
            values = data.get("expiryList") or data.get("expiries") or data.get("expiry") or []
        else:
            values = data
        return [str(v) for v in values]

    def get_option_chain(
        self,
        underlying: str,
        exchange_segment: ExchangeSegment,
        expiry: str,
    ) -> dict[str, Any]:
        """Get option chain for a security ID and expiry."""
        key = (underlying, expiry)
        last_time = self._last_request_times.get(key, 0.0)
        import time as _time

        elapsed = _time.time() - last_time
        if elapsed < self._cooldown:
            sleep_time = self._cooldown - elapsed
            _time.sleep(sleep_time)

        res = self._retry_executor.execute(
            lambda: self._http_client.post_json(
                self._url_resolver.option_chain_url(),
                {
                    "UnderlyingScrip": _coerce_security_id(underlying),
                    "UnderlyingSeg": _seg_wire(exchange_segment),
                    "Expiry": expiry,
                },
            )
        )
        self._last_request_times[key] = _time.time()
        return res

    def get_parsed_option_chain(
        self,
        underlying: str,
        exchange_segment: ExchangeSegment,
        expiry: str,
    ) -> list[OptionContract]:
        """Get parsed option chain for a security ID and expiry."""
        if self._rolling_option_client:
            return self._rolling_option_client.get_rolling_option_chain(
                underlying, exchange_segment, expiry
            )

        response = self.get_option_chain(underlying, exchange_segment, expiry)
        return self._parse_option_chain(response, underlying, exchange_segment, expiry)

    def _parse_option_chain(
        self,
        option_chain: dict[str, Any],
        underlying: str,
        exchange_segment: ExchangeSegment,
        expiry: str,
    ) -> list[OptionContract]:
        """Parse option chain response into OptionContract objects."""
        contracts: list[OptionContract] = []
        option_data = self._option_data(option_chain)

        if isinstance(option_data, dict):
            for strike, sides in option_data.items():
                if not isinstance(sides, dict):
                    continue
                contract = self._option_contract_from_sides(
                    strike,
                    sides,
                    exchange_segment,
                    expiry,
                )
                if contract:
                    contracts.append(contract)
            return contracts

        if isinstance(option_data, list):
            for item in option_data:
                if isinstance(item, dict):
                    contract = self._parse_option_contract(
                        item,
                        underlying,
                        exchange_segment,
                        expiry,
                    )
                    if contract:
                        contracts.append(contract)

        return contracts

    def _option_data(self, option_chain: dict[str, Any]) -> Any:
        data = option_chain.get("data", {})
        if isinstance(data, dict):
            return data.get("optionChain") or data.get("options") or data.get("oc") or data
        return data

    def _option_contract_from_sides(
        self,
        strike: Any,
        sides: dict[str, Any],
        exchange_segment: ExchangeSegment,
        expiry: str,
    ) -> OptionContract | None:
        ce = sides.get("ce") or sides.get("CE") or sides.get("call") or {}
        pe = sides.get("pe") or sides.get("PE") or sides.get("put") or {}
        ce = ce if isinstance(ce, dict) else {}
        pe = pe if isinstance(pe, dict) else {}

        return OptionContract(
            strike=Decimal(str(strike)),
            expiry=expiry,
            instrument_type=InstrumentType.OPTIONS,
            exchange_segment=exchange_segment,
            lot_size=int(ce.get("lot_size") or pe.get("lotSize") or 0),
            ce_ltp=self._decimal_or_none(ce.get("last_price") or ce.get("ltp")),
            ce_bid=self._decimal_or_none(
                ce.get("top_bid_price") or ce.get("bidPrice") or ce.get("bid")
            ),
            ce_ask=self._decimal_or_none(
                ce.get("top_ask_price") or ce.get("askPrice") or ce.get("ask")
            ),
            ce_iv=self._decimal_or_none(
                ce.get("implied_volatility") or ce.get("iv") or (ce.get("greeks") or {}).get("iv")
            ),
            ce_oi=self._int_or_none(ce.get("oi") or ce.get("openInterest")),
            ce_volume=self._int_or_none(ce.get("volume")),
            pe_ltp=self._decimal_or_none(pe.get("last_price") or pe.get("ltp")),
            pe_bid=self._decimal_or_none(
                pe.get("top_bid_price") or pe.get("bidPrice") or pe.get("bid")
            ),
            pe_ask=self._decimal_or_none(
                pe.get("top_ask_price") or pe.get("askPrice") or pe.get("ask")
            ),
            pe_iv=self._decimal_or_none(
                pe.get("implied_volatility") or pe.get("iv") or (pe.get("greeks") or {}).get("iv")
            ),
            pe_oi=self._int_or_none(pe.get("oi") or pe.get("openInterest")),
            pe_volume=self._int_or_none(pe.get("volume")),
        )

    def _parse_option_contract(
        self,
        item: dict[str, Any],
        underlying: str,
        exchange_segment: ExchangeSegment,
        expiry: str,
    ) -> OptionContract | None:
        try:
            strike = Decimal(str(item.get("strikePrice") or item.get("strike") or 0))
            instrument_type = item.get("instrumentType", "OPT")
            instrument_enum = InstrumentType.EQUITY
            if instrument_type == "OPT":
                instrument_enum = InstrumentType.OPTIONS
            elif instrument_type == "FUT":
                instrument_enum = InstrumentType.FUTURES

            return OptionContract(
                strike=strike,
                expiry=expiry,
                instrument_type=instrument_enum,
                exchange_segment=exchange_segment,
                lot_size=int(item.get("lotSize") or 0),
                ce_ltp=self._decimal_or_none(item.get("ceLtp") or item.get("ce_ltp")),
                ce_bid=self._decimal_or_none(item.get("ceBid") or item.get("ce_bid")),
                ce_ask=self._decimal_or_none(item.get("ceAsk") or item.get("ce_ask")),
                ce_iv=self._decimal_or_none(item.get("ceIv") or item.get("ce_iv")),
                ce_oi=self._int_or_none(item.get("ceOi") or item.get("ce_oi")),
                ce_volume=self._int_or_none(item.get("ceVolume") or item.get("ce_volume")),
                pe_ltp=self._decimal_or_none(item.get("peLtp") or item.get("pe_ltp")),
                pe_bid=self._decimal_or_none(item.get("peBid") or item.get("pe_bid")),
                pe_ask=self._decimal_or_none(item.get("peAsk") or item.get("pe_ask")),
                pe_iv=self._decimal_or_none(item.get("peIv") or item.get("pe_iv")),
                pe_oi=self._int_or_none(item.get("peOi") or item.get("pe_oi")),
                pe_volume=self._int_or_none(item.get("peVolume") or item.get("pe_volume")),
            )
        except Exception as e:
            logger.warning(f"Failed to parse option contract: {e}")
            return None

    @staticmethod
    def _decimal_or_none(value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        return Decimal(str(value))

    @staticmethod
    def _int_or_none(value: Any) -> int | None:
        if value in (None, ""):
            return None
        return int(value)


class DhanRollingOptionClient:
    """Client for rolling options operations.

    Handles rolling options for futures and options contracts, including
    expiry management and contract transitions.
    """

    def __init__(
        self,
        http_client: Any,
        settings: Any,
        url_resolver: Any,
        retry_executor: RetryExecutor,
    ) -> None:
        self._http_client = http_client
        self._settings = settings
        self._url_resolver = url_resolver
        self._retry_executor = retry_executor

        # Cache for rolling option data
        self._rolling_cache: dict[str, dict[str, Any]] = {}

    def get_rolling_option_chain(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
        expiry: str,
    ) -> list[OptionContract]:
        """Get rolling option chain for a security ID and expiry."""
        cache_key = f"{security_id}:{_seg_wire(exchange_segment)}:{expiry}"

        # Check cache first
        if cache_key in self._rolling_cache:
            return self._rolling_cache[cache_key]

        # Get option chain from Dhan
        option_chain = self._get_option_chain_from_dhan(security_id, exchange_segment, expiry)

        # Parse and cache the result
        contracts = self._parse_option_chain(option_chain, security_id, exchange_segment, expiry)
        self._rolling_cache[cache_key] = contracts

        return contracts

    def get_available_expiries(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
    ) -> list[str]:
        """Get available expiries for rolling options."""
        response = self._retry_executor.execute(
            lambda: self._http_client.post_json(
                self._url_resolver.option_chain_expiry_list_url(),
                {
                    "UnderlyingScrip": _coerce_security_id(security_id),
                    "UnderlyingSeg": _seg_wire(exchange_segment),
                },
            )
        )
        data = response.get("data", {})
        if isinstance(data, dict):
            values = data.get("expiryList") or data.get("expiries") or data.get("expiry") or []
        else:
            values = data
        return [str(v) for v in values]

    def roll_to_next_expiry(
        self,
        underlying: str,
        exchange_segment: ExchangeSegment,
        current_expiry: str,
    ) -> dict[str, Any]:
        """Roll position to next expiry."""
        # Get next expiry
        expiries = self.get_available_expiries(underlying, exchange_segment)
        expiries = [e for e in expiries if e > current_expiry]

        if not expiries:
            raise ValueError(f"No future expiry available for {underlying}")

        next_expiry = expiries[0]

        # In a real implementation, this would execute the roll operation
        # For now, return the roll details
        return {
            "underlying": underlying,
            "exchange_segment": exchange_segment.value,
            "current_expiry": current_expiry,
            "next_expiry": next_expiry,
            "roll_date": datetime.now().isoformat(),
            "status": "pending",
        }

    def _get_option_chain_from_dhan(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
        expiry: str,
    ) -> dict[str, Any]:
        """Get option chain from Dhan API."""
        return self._retry_executor.execute(
            lambda: self._http_client.post_json(
                self._url_resolver.option_chain_url(),
                {
                    "UnderlyingScrip": _coerce_security_id(security_id),
                    "UnderlyingSeg": _seg_wire(exchange_segment),
                    "Expiry": expiry,
                },
            )
        )

    def _parse_option_chain(
        self,
        option_chain: dict[str, Any],
        underlying: str,
        exchange_segment: ExchangeSegment,
        expiry: str,
    ) -> list[OptionContract]:
        """Parse option chain response into OptionContract objects."""
        contracts = []

        # Extract data from response
        data = option_chain.get("data", {})
        if isinstance(data, dict):
            option_data = data.get("optionChain") or data.get("options") or data
        else:
            option_data = data

        # Parse each option contract
        for item in option_data:
            contract = self._parse_option_contract(item, underlying, exchange_segment, expiry)
            if contract:
                contracts.append(contract)

        return contracts

    def _parse_option_contract(
        self,
        item: dict[str, Any],
        underlying: str,
        exchange_segment: ExchangeSegment,
        expiry: str,
    ) -> OptionContract | None:
        """Parse a single option contract from API response."""
        try:
            # Extract strike price
            strike = Decimal(str(item.get("strikePrice") or item.get("strike") or 0))

            # Extract instrument type
            instrument_type = item.get("instrumentType", "OPT")
            from brokers.common.core.enums import InstrumentType

            instrument_enum = InstrumentType.EQUITY
            if instrument_type == "OPT":
                instrument_enum = InstrumentType.OPTIONS
            elif instrument_type == "FUT":
                instrument_enum = InstrumentType.FUTURES

            # Create option contract
            contract = OptionContract(
                strike=strike,
                expiry=expiry,
                instrument_type=instrument_enum,
                exchange_segment=exchange_segment,
                lot_size=int(item.get("lotSize") or 1),
                # CE data
                ce_ltp=Decimal(str(item.get("ceLtp") or item.get("ce") or 0))
                if item.get("ceLtp") or item.get("ce")
                else None,
                ce_bid=Decimal(str(item.get("ceBid") or 0)) if item.get("ceBid") else None,
                ce_ask=Decimal(str(item.get("ceAsk") or 0)) if item.get("ceAsk") else None,
                ce_iv=Decimal(str(item.get("ceIv") or 0)) if item.get("ceIv") else None,
                ce_oi=int(item.get("ceOi") or 0),
                ce_volume=int(item.get("ceVolume") or 0),
                # PE data
                pe_ltp=Decimal(str(item.get("peLtp") or item.get("pe") or 0))
                if item.get("peLtp") or item.get("pe")
                else None,
                pe_bid=Decimal(str(item.get("peBid") or 0)) if item.get("peBid") else None,
                pe_ask=Decimal(str(item.get("peAsk") or 0)) if item.get("peAsk") else None,
                pe_iv=Decimal(str(item.get("peIv") or 0)) if item.get("peIv") else None,
                pe_oi=int(item.get("peOi") or 0),
                pe_volume=int(item.get("peVolume") or 0),
            )

            return contract

        except Exception as e:
            # Log error and skip invalid contract
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to parse option contract: {e}")
            return None

    def clear_cache(self) -> None:
        """Clear rolling option cache."""
        self._rolling_cache.clear()
