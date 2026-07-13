/**
 * TypeScript domain types mirroring the TradeXV2 FastAPI schemas
 * (see src/interface/api/schemas.py). Money fields serialize to `float`
 * on the wire (MoneyField is a Decimal internally, PlainSerializer(float)).
 * Keep these in sync with the backend schemas when they change.
 */

/** Backend MoneyField -> JSON float. */
export type Money = number;

// ── Enums (mirrors domain validation in schemas.OrderRequest) ───────────────

export type Exchange = "NSE" | "BSE" | "NFO" | "CDS" | "MCX" | "BCD";
export type TransactionType = "BUY" | "SELL";
export type OrderType = "MARKET" | "LIMIT" | "SL" | "SL-M";
export type ProductType = "INTRADAY" | "DELIVERY" | "MARGIN" | "CO" | "BO";

// ── Health ─────────────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: string;
  version: string;
  timestamp: string;
  services?: Record<string, string> | null;
}

export interface ReadinessResponse {
  ready: boolean;
  checks: Record<string, unknown>;
  timestamp: string;
}

// ── Market Data ───────────────────────────────────────────────────────────────

export interface Candle {
  t: number; // timestamp (ms)
  o: Money;
  h: Money;
  l: Money;
  c: Money;
  v: number;
  oi: number;
}

export interface CandlesResponse {
  symbol: string;
  timeframe: string;
  exchange?: string;
  candles: Candle[];
  count: number;
}

export interface QuoteResponse {
  symbol: string;
  exchange: string;
  ltp: Money;
  timestamp: number; // ms
  bid?: Money | null;
  ask?: Money | null;
  bid_qty?: number | null;
  ask_qty?: number | null;
  volume?: number | null;
  oi?: number | null;
  open?: Money | null;
  high?: Money | null;
  low?: Money | null;
  close?: Money | null;
}

export interface DepthLevel {
  price: Money | string;
  qty: number | string;
}
export interface DepthResponse {
  symbol: string;
  bids: DepthLevel[];
  asks: DepthLevel[];
}

// ── Symbols ───────────────────────────────────────────────────────────────────

export interface SymbolInfo {
  symbol: string;
  exchange: string;
  name?: string | null;
  segment?: string | null;
  isin?: string | null;
  lot_size: number;
  tick_size: number;
  sector?: string | null;
  instrument_type: string;
  first_date?: string | null;
  last_date?: string | null;
  total_rows: number;
}

export interface SymbolSearchResponse {
  results: SymbolInfo[];
  count: number;
}

// ── Portfolio & Orders ───────────────────────────────────────────────────────

export interface Position {
  symbol: string;
  exchange: string;
  quantity: number;
  average_price: Money;
  current_price: Money;
  unrealized_pnl: Money;
  realized_pnl: Money;
  pnl_pct: number;
}

export interface PositionsResponse {
  positions: Position[];
  count: number;
  total_pnl: Money;
  total_pnl_percent: number;
}

export interface Holding {
  symbol: string;
  exchange: string;
  quantity: number;
  average_price: Money;
  current_price: Money;
  invested_value: Money;
  current_value: Money;
  pnl: Money;
  pnl_percent: number;
}

export interface HoldingsResponse {
  holdings: Holding[];
  count: number;
  total_value: Money;
  total_invested: Money;
  total_pnl: Money;
}

export interface PortfolioSummary {
  total_value: Money;
  total_invested: Money;
  total_pnl: Money;
  total_pnl_percent: number;
  realized_pnl: Money;
  unrealized_pnl: Money;
  margin_used: Money;
  margin_available: Money;
  positions_count: number;
  holdings_count: number;
}

export interface OrderRequest {
  symbol: string;
  exchange: Exchange;
  transaction_type: TransactionType;
  order_type: OrderType;
  quantity: number;
  price?: number | null;
  trigger_price?: number | null;
  product_type?: ProductType;
  correlation_id?: string | null;
}

export interface OrderResponse {
  order_id: string;
  symbol: string;
  exchange: string;
  transaction_type: string;
  order_type: string;
  quantity: number;
  price: Money | null;
  status: string;
  filled_quantity: number;
  average_price: Money | null;
  timestamp: string;
}

export interface OrdersResponse {
  orders: OrderResponse[];
  count: number;
}

export interface TradeResponse {
  trade_id: string;
  order_id: string;
  symbol: string;
  exchange: string;
  transaction_type: string;
  quantity: number;
  price: Money;
  timestamp: string;
}

export interface TradesResponse {
  trades: TradeResponse[];
  count: number;
}

// ── Scanner ───────────────────────────────────────────────────────────────────

export interface ScannerSnapshot {
  symbol: string;
  ltp: number;
  intraday_score: number;
  signal: string; // BUY, SELL, BREAKOUT, NEUTRAL
  trend: string; // Bullish, Bearish, Neutral
  momentum_5d_pct?: number | null;
  rsi_14?: number | null;
  roc_5?: number | null;
  relative_volume?: number | null;
  day_high?: number | null;
  day_low?: number | null;
  day_volume?: number | null;
}

export interface ScannerCandidatesResponse {
  candidates: ScannerSnapshot[];
  count: number;
  timestamp?: string;
}

// ── Backtest ──────────────────────────────────────────────────────────────────

export interface BacktestMetrics {
  total_return_pct: number;
  annualized_return_pct: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown_pct: number;
  profit_factor: number;
  win_rate: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
}

export interface BacktestResultResponse {
  run_id: string;
  symbol: string;
  timeframe: string;
  metrics: BacktestMetrics;
  trades?: unknown[] | null;
  research_mode: string;
  research_only: boolean;
}

export interface BacktestRunRequest {
  symbol: string;
  years: number;
  timeframe: string;
  initial_capital: number;
  strategy: string;
}

// ── Live Broker (connectivity / status) ──────────────────────────────────────

export interface BrokerHealth {
  status: string;
  broker: string;
  describe: unknown;
  timestamp: string;
}

export interface BrokerCapabilities {
  broker: string;
  capabilities: unknown;
}

// ── WebSocket messages (see src/interface/api/ws/market.py) ─────────────────

export type WsMessage =
  | { type: "quote"; symbol: string; ltp: number; [k: string]: unknown }
  | { type: "candle"; symbol: string; timeframe: string; [k: string]: unknown }
  | { type: "subscribed"; symbols: string[] }
  | { type: "unsubscribed"; symbols: string[] }
  | { type: "pong"; timestamp?: unknown }
  | { type: "error"; reason?: string; message?: string };

// ── Options Analytics ──────────────────────────────────────────────────────

export interface OptionContractRow {
  symbol: string;
  expiry: string;
  strike: number;
  option_type: string; // CE or PE
  ltp: number;
  bid?: number | null;
  ask?: number | null;
  volume: number;
  oi: number;
  iv?: number | null;
}

export interface OptionChainResponse {
  underlying: string;
  expiry: string;
  contracts: OptionContractRow[];
  count: number;
}

export interface PCRResponse {
  timestamp: number;
  underlying: string;
  expiry_kind: string;
  expiry_date: string;
  spot: number;
  pcr_volume: number | null;
  pcr_oi: number | null;
  total_ce_volume: number;
  total_pe_volume: number;
  total_ce_oi: number;
  total_pe_oi: number;
}

export interface MaxPainResponse {
  timestamp: number;
  underlying: string;
  expiry_kind: string;
  expiry_date: string;
  spot: number;
  max_pain_strike: number;
  total_pain_at_max_pain: number;
  distance_from_spot: number;
  position_vs_spot: string;
}

export interface IVSurfaceResponse {
  timestamp: number;
  underlying: string;
  expiry_kind: string;
  expiry_date: string;
  spot: number;
  atm_strike: number;
  atm_iv: number;
  otm_put_iv: number;
  otm_call_iv: number;
  iv_skew: number;
  put_call_iv_ratio: number | null;
  days_to_expiry: number;
}

export interface VolumeProfileResponse {
  underlying: string;
  expiry: string;
  strikes: number[];
  profile: { strike: number; ce_volume: number; pe_volume: number; total_volume: number }[];
  count: number;
}
