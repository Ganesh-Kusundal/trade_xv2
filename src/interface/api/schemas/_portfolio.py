"""Portfolio, Order, Position, Trade schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from domain.value_objects.money import MoneyField


class PositionResponse(BaseModel):
    """Position data."""

    symbol: str
    exchange: str
    quantity: int
    average_price: MoneyField
    current_price: MoneyField
    unrealized_pnl: MoneyField
    realized_pnl: MoneyField
    pnl_pct: float


class PositionListResponse(BaseModel):
    """All positions."""

    positions: list[PositionResponse]
    total_pnl: MoneyField
    total_exposure: MoneyField


class OrderRequest(BaseModel):
    """Place order request with comprehensive validation."""

    symbol: str = Field(
        ..., min_length=1, max_length=50, description="Trading symbol (e.g., RELIANCE, RELIANCE-EQ)"
    )
    exchange: str = Field(..., description="Exchange: NSE, BSE, NFO, CDS, MCX")
    transaction_type: str = Field(..., description="BUY or SELL")
    order_type: str = Field(..., description="MARKET, LIMIT, SL, SL-M")
    quantity: int = Field(
        ..., ge=1, le=1000000, description="Order quantity (must be > 0 and <= 1M)"
    )
    price: float | None = Field(None, ge=0.01, le=1000000, description="Price for LIMIT/SL orders")
    trigger_price: float | None = Field(
        None, ge=0.01, le=1000000, description="Trigger price for SL/SL-M orders"
    )
    product_type: str = Field("INTRADAY", description="INTRADAY, DELIVERY, MARGIN, CO, BO")
    correlation_id: str | None = Field(None, description="Optional correlation ID for tracing")

    @field_validator("transaction_type")
    @classmethod
    def validate_transaction_type(cls, v: str) -> str:
        if v.upper() not in ("BUY", "SELL"):
            raise ValueError("transaction_type must be BUY or SELL")
        return v.upper()

    @field_validator("exchange")
    @classmethod
    def validate_exchange(cls, v: str) -> str:
        valid_exchanges = {"NSE", "BSE", "NFO", "CDS", "MCX", "BCD"}
        if v.upper() not in valid_exchanges:
            raise ValueError(f"exchange must be one of: {valid_exchanges}")
        return v.upper()

    @field_validator("order_type")
    @classmethod
    def validate_order_type(cls, v: str) -> str:
        valid_types = {"MARKET", "LIMIT", "SL", "SL-M"}
        if v.upper() not in valid_types:
            raise ValueError(f"order_type must be one of: {valid_types}")
        return v.upper()

    @field_validator("product_type")
    @classmethod
    def validate_product_type(cls, v: str) -> str:
        valid_products = {"INTRADAY", "DELIVERY", "MARGIN", "CO", "BO"}
        if v.upper() not in valid_products:
            raise ValueError(f"product_type must be one of: {valid_products}")
        return v.upper()

    @model_validator(mode="after")
    def validate_order_constraints(self) -> OrderRequest:
        order_type = self.order_type.upper()
        if order_type in ("LIMIT", "SL") and (self.price is None or self.price <= 0):
            raise ValueError("price is required and must be > 0 for LIMIT/SL orders")
        if order_type in ("SL", "SL-M") and (self.trigger_price is None or self.trigger_price <= 0):
            raise ValueError("trigger_price is required and must be > 0 for SL/SL-M orders")
        if order_type == "SL" and self.price and self.trigger_price:
            if self.transaction_type.upper() == "BUY":
                if self.price < self.trigger_price:
                    raise ValueError("for SL BUY orders, price must be >= trigger_price")
            else:
                if self.price > self.trigger_price:
                    raise ValueError("for SL SELL orders, price must be <= trigger_price")
        return self


class OrderResponse(BaseModel):
    """Order data."""

    order_id: str
    symbol: str
    exchange: str
    transaction_type: str
    order_type: str
    quantity: int
    price: MoneyField | None = None
    status: str
    filled_quantity: int = 0
    average_price: MoneyField | None = None
    timestamp: datetime = Field(default_factory=datetime.now)


class OrderListResponse(BaseModel):
    """All orders."""

    orders: list[OrderResponse]
    count: int


class Position(BaseModel):
    """Simplified position model."""

    symbol: str
    exchange: str
    quantity: int
    average_price: MoneyField
    current_price: MoneyField
    unrealized_pnl: MoneyField
    realized_pnl: MoneyField
    pnl_pct: float


class PositionsResponse(BaseModel):
    """All positions response."""

    positions: list[Position]
    count: int
    total_pnl: MoneyField
    total_pnl_percent: float


class Holding(BaseModel):
    """Holding model."""

    symbol: str
    exchange: str
    quantity: int
    average_price: MoneyField
    current_price: MoneyField
    invested_value: MoneyField
    current_value: MoneyField
    pnl: MoneyField
    pnl_percent: float


class HoldingsResponse(BaseModel):
    """All holdings response."""

    holdings: list[Holding]
    count: int
    total_value: MoneyField
    total_invested: MoneyField
    total_pnl: MoneyField


class PortfolioSummary(BaseModel):
    """Portfolio summary."""

    total_value: MoneyField
    total_invested: MoneyField
    total_pnl: MoneyField
    total_pnl_percent: float
    realized_pnl: MoneyField
    unrealized_pnl: MoneyField
    margin_used: MoneyField
    margin_available: MoneyField
    positions_count: int
    holdings_count: int


class TradeResponse(BaseModel):
    """Trade execution model."""

    trade_id: str
    order_id: str
    symbol: str
    exchange: str
    transaction_type: str
    quantity: int
    price: MoneyField
    timestamp: datetime


class TradesResponse(BaseModel):
    """All trades response."""

    trades: list[TradeResponse]
    count: int


class OrdersResponse(BaseModel):
    """All orders response (alias for OrderListResponse)."""

    orders: list[OrderResponse]
    count: int
