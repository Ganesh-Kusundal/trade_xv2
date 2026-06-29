"""
IBrokerGateway - The Single Source of Truth for Broker Operations

This interface defines the EXCLUSIVE contract between the Application layer
and any Broker implementation (Dhan, Upstox, Paper, Future Brokers).

RULES:
1. Application layer depends ONLY on this interface, never concrete implementations
2. All broker-specific details (REST APIs, WebSockets, auth, error codes) MUST stay inside broker adapters
3. Return types are ALWAYS domain objects, never broker DTOs
4. Any change to this interface requires a MAJOR version bump and dual-version support

Version: 2.0.0 (Stability Engineering Lock)
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Callable, Dict, Any
from decimal import Decimal
from datetime import datetime

from domain.entities.order import Order
from domain.entities.position import Position
from domain.entities.instrument import Instrument
from domain.entities.market import MarketTick as Tick
from domain.historical import HistoricalBar as Bar
from domain.types import OrderStatus, OrderType, Side as OrderSide
from domain.result import GatewayResult as Result


class IBrokerGateway(ABC):
    """
    Abstract base class defining the broker gateway contract.
    
    All broker implementations (Dhan, Upstox, Paper) MUST implement this interface.
    All application code MUST depend only on this interface.
    """
    
    # =========================================================================
    # LIFECYCLE MANAGEMENT
    # =========================================================================
    
    @abstractmethod
    async def initialize(self) -> Result[None]:
        """
        Initialize broker connection (auth, websocket, session).
        
        Returns:
            Result[None]: Success if initialized, Failure with error details otherwise.
        """
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """
        Gracefully shutdown all connections (HTTP, WebSocket).
        
        Must ensure:
        - No pending orders are lost
        - All events are flushed
        - Resources are released
        """
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """
        Check if broker is currently connected and authenticated.
        
        Returns:
            bool: True if ready for trading, False otherwise.
        """
        pass
    
    # =========================================================================
    # ORDER MANAGEMENT
    # =========================================================================
    
    @abstractmethod
    async def place_order(
        self,
        instrument: Instrument,
        side: OrderSide,
        order_type: OrderType,
        quantity: int,
        price: Optional[Decimal] = None,
        trigger_price: Optional[Decimal] = None,
        client_order_id: Optional[str] = None,
    ) -> Result[Order]:
        """
        Place a new order.
        
        Args:
            instrument: Target instrument (symbol, exchange, segment)
            side: BUY or SELL
            order_type: LIMIT, MARKET, SL, SL-M
            quantity: Number of shares/lots
            price: Limit price (required for LIMIT/SL)
            trigger_price: Stop trigger (required for SL/SL-M)
            client_order_id: Idempotency key for retry safety
            
        Returns:
            Result[Order]: Order entity with broker-assigned ID if successful.
            
        Guarantees:
            - Idempotent: Same client_order_id won't create duplicate orders
            - Atomic: Either fully placed or fully rejected
            - Domain-clean: Returns domain Order, not broker DTO
        """
        pass
    
    @abstractmethod
    async def modify_order(
        self,
        order_id: str,
        quantity: Optional[int] = None,
        price: Optional[Decimal] = None,
        trigger_price: Optional[Decimal] = None,
    ) -> Result[Order]:
        """
        Modify an existing order.
        
        Args:
            order_id: Broker-assigned order ID
            quantity: New quantity (optional)
            price: New price (optional)
            trigger_price: New trigger price (optional)
            
        Returns:
            Result[Order]: Updated order entity.
        """
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> Result[Order]:
        """
        Cancel an existing order.
        
        Args:
            order_id: Broker-assigned order ID
            
        Returns:
            Result[Order]: Cancelled order entity with updated status.
        """
        pass
    
    @abstractmethod
    async def get_order_status(self, order_id: str) -> Result[Order]:
        """
        Fetch current status of an order.
        
        Args:
            order_id: Broker-assigned order ID
            
        Returns:
            Result[Order]: Current order state.
        """
        pass
    
    @abstractmethod
    async def get_all_orders(
        self,
        status_filter: Optional[List[OrderStatus]] = None,
        date: Optional[datetime] = None,
    ) -> Result[List[Order]]:
        """
        Fetch all orders (optionally filtered).
        
        Args:
            status_filter: Filter by statuses (e.g., [PENDING, TRIGGER_PENDING])
            date: Fetch orders for specific date (default: today)
            
        Returns:
            Result[List[Order]]: List of order entities.
        """
        pass
    
    # =========================================================================
    # POSITION & PORTFOLIO
    # =========================================================================
    
    @abstractmethod
    async def get_positions(self) -> Result[List[Position]]:
        """
        Fetch all open positions.
        
        Returns:
            Result[List[Position]]: List of position entities with:
                - quantity
                - average_price
                - unrealized_pnl (if LTP available)
                - realized_pnl (for closed positions)
        """
        pass
    
    @abstractmethod
    async def get_holdings(self) -> Result[List[Any]]:
        """
        Fetch T+1/T+2 holdings (delivery positions).
        
        Returns:
            Result[List[Any]]: List of holding entities.
        """
        pass
    
    @abstractmethod
    async def get_funds(self) -> Result[Dict[str, Decimal]]:
        """
        Fetch account funds/margins.
        
        Returns:
            Result[Dict[str, Decimal]]: Dictionary with:
                - available_cash
                - margin_used
                - total_equity
        """
        pass
    
    # =========================================================================
    # MARKET DATA - HISTORICAL
    # =========================================================================
    
    @abstractmethod
    async def get_historical_data(
        self,
        instrument: Instrument,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Result[List[Bar]]:
        """
        Fetch historical OHLCV bars.
        
        Args:
            instrument: Target instrument
            timeframe: '1m', '5m', '15m', '1h', '1d'
            start_date: Start of range (inclusive)
            end_date: End of range (inclusive)
            
        Returns:
            Result[List[Bar]]: List of bar entities sorted by timestamp.
            
        Performance Requirements:
            - 90 days of 1-min data: < 10 seconds
            - 1 year of daily data: < 2 seconds
        """
        pass
    
    # =========================================================================
    # MARKET DATA - LIVE
    # =========================================================================
    
    @abstractmethod
    async def subscribe_ticks(
        self,
        instruments: List[Instrument],
        callback: Callable[[Tick], None],
    ) -> Result[None]:
        """
        Subscribe to real-time tick data.
        
        Args:
            instruments: List of instruments to subscribe
            callback: Function called for each tick received
            
        Returns:
            Result[None]: Success if subscription active.
            
        Guarantees:
            - Callback receives normalized domain Tick objects
            - No broker-specific fields leak into callback
            - Auto-reconnect on connection loss
        """
        pass
    
    @abstractmethod
    async def unsubscribe_ticks(
        self,
        instruments: List[Instrument],
    ) -> Result[None]:
        """
        Unsubscribe from tick data.
        
        Args:
            instruments: List of instruments to unsubscribe
            
        Returns:
            Result[None]: Success if unsubscribed.
        """
        pass
    
    @abstractmethod
    async def subscribe_depth(
        self,
        instrument: Instrument,
        callback: Callable[[Dict[str, Any]], None],
        levels: int = 5,
    ) -> Result[None]:
        """
        Subscribe to market depth (order book).
        
        Args:
            instrument: Target instrument
            callback: Function called for each depth update
            levels: Number of bid/ask levels (default: 5)
            
        Returns:
            Result[None]: Success if subscription active.
        """
        pass
    
    # =========================================================================
    # INSTRUMENT MASTER
    # =========================================================================
    
    @abstractmethod
    async def get_instruments(self) -> Result[List[Instrument]]:
        """
        Fetch complete instrument master (all tradable symbols).
        
        Returns:
            Result[List[Instrument]]: List of all available instruments.
            
        Note:
            This is typically cached after first fetch.
        """
        pass
    
    @abstractmethod
    async def search_instrument(
        self,
        symbol: str,
        exchange: Optional[str] = None,
    ) -> Result[Optional[Instrument]]:
        """
        Search for a specific instrument.
        
        Args:
            symbol: Symbol name (e.g., 'RELIANCE', 'NIFTY')
            exchange: Optional exchange filter ('NSE', 'BSE', 'MCX')
            
        Returns:
            Result[Optional[Instrument]]: Matching instrument or None.
        """
        pass
    
    # =========================================================================
    # HEALTH & DIAGNOSTICS
    # =========================================================================
    
    @abstractmethod
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get detailed health status.
        
        Returns:
            Dict containing:
                - connection_state: CONNECTED/DISCONNECTED/RECONNECTING
                - last_tick_time: Timestamp of last received tick
                - latency_ms: Current API latency
                - rate_limit_remaining: Requests remaining in window
                - errors_last_hour: Count of recent errors
        """
        pass
    
    @abstractmethod
    async def ping(self) -> Result[float]:
        """
        Ping broker API to measure latency.
        
        Returns:
            Result[float]: Round-trip latency in milliseconds.
        """
        pass


# Backward compatibility alias for legacy code
OrderTransportPort = IBrokerGateway


__all__ = ["IBrokerGateway", "OrderTransportPort"]
