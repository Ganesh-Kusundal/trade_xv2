"""Centralized error message constants for TradeXV2."""

# Risk gate
RISK_CHECK_FAILED = "Risk check failed"
KILL_SWITCH_ACTIVE = "Kill switch is active"
KILL_SWITCH_ACTIVE_ORDER = "Kill switch is active — order rejected"
KILL_SWITCH_ACTIVE_SQUARE_OFF = "Kill switch is active — square-off rejected"
KILL_SWITCH_ACTIVE_EXTENDED = "Kill switch active"

# Loss circuit breaker
LOSS_CIRCUIT_BREAKER_OPEN = "Loss circuit breaker is OPEN"
DAILY_LOSS_LIMIT_REACHED = "Daily loss limit reached"

# Order lifecycle
ALREADY_FILLED_PREFIX = "already filled"
ORDERS_DISABLED = "ORDERS_DISABLED"
LIVE_ORDERS_DISABLED = "Live orders are disabled"
LIVE_ORDER_CANCELLATION_DISABLED = "Live order cancellation is disabled"

# Broker blocked
NOT_LIVE_ACTIONABLE = "not live-actionable"
NO_LIVE_ACTIONABLE_GATE = "no live-actionable gate registered"

# Parity
RUNTIME_PARITY_GATE_FAILED = "Runtime parity gate failed"
