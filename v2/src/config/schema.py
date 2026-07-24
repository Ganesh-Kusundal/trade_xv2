"""AppConfig — declarative trading framework configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field

from domain.enums import BrokerId, Environment


class MessageBusConfig(BaseModel):
    max_queue_size: int = 10_000
    persistent_log: bool = False
    persistent_log_path: str = "./data/message_log.sqlite"


class RiskConfig(BaseModel):
    max_order_size: int = 1000
    max_position_size: int = 5000
    max_daily_loss: float = 50_000
    max_orders_per_day: int = 100


class DataConfig(BaseModel):
    datalake_path: str = "./data/lake"
    default_timeframe: str = "1m"


class ComponentsConfig(BaseModel):
    message_bus: MessageBusConfig = Field(default_factory=MessageBusConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    data: DataConfig = Field(default_factory=DataConfig)


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "json"


class ObservabilityConfig(BaseModel):
    metrics_enabled: bool = True
    tracing_enabled: bool = True
    otlp_endpoint: str = "http://localhost:4317"


class DhanBrokerConfig(BaseModel):
    client_id: str = ""
    access_token: str = ""
    pin: str = ""
    totp_secret: str = ""
    base_url: str = "https://api.dhan.co/v2"
    token_path: str = "./runtime/dhan-token.json"


class UpstoxBrokerConfig(BaseModel):
    client_id: str = ""
    client_secret: str = ""
    access_token: str = ""
    refresh_token: str = ""
    mobile: str = ""
    pin: str = ""
    totp_secret: str = ""
    base_url: str = "https://api.upstox.com/v2"
    token_path: str = "./runtime/upstox-token.json"


class AppConfig(BaseModel):
    environment: Environment = Environment.PAPER
    broker: BrokerId = BrokerId.PAPER
    components: ComponentsConfig = Field(default_factory=ComponentsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    dhan: DhanBrokerConfig = Field(default_factory=DhanBrokerConfig)
    upstox: UpstoxBrokerConfig = Field(default_factory=UpstoxBrokerConfig)
