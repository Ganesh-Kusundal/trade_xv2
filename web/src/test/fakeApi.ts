import type { TradingApi } from "../api/client";
import type {
  BacktestResultResponse,
  BacktestRunRequest,
  BrokerCapabilities,
  BrokerHealth,
  DepthResponse,
  HealthResponse,
  HoldingsResponse,
  IVSurfaceResponse,
  MaxPainResponse,
  OrderRequest,
  OrderResponse,
  OptionChainResponse,
  OrdersResponse,
  PCRResponse,
  PositionsResponse,
  PortfolioSummary,
  QuoteResponse,
  ReadinessResponse,
  ScannerCandidatesResponse,
  TradeResponse,
  TradesResponse,
  VolumeProfileResponse,
} from "../types";

/**
 * Build a fully-typed fake `TradingApi` with safe defaults so tests only
 * override the methods a component actually calls.
 */
export function createFakeApi(overrides: Partial<TradingApi> = {}): TradingApi {
  const empty = async () => ({} as never);
  const base: TradingApi = {
    health: () => Promise.resolve<HealthResponse>({ status: "healthy", version: "1.0.0", timestamp: new Date().toISOString() }),
    readiness: () => Promise.resolve<ReadinessResponse>({ ready: true, checks: {}, timestamp: new Date().toISOString() }),
    metrics: () => Promise.resolve<Record<string, unknown>>({ http_requests: { total: 0 } }),
    quote: (symbol: string) => Promise.resolve<QuoteResponse>({
      symbol, exchange: "NSE", ltp: 0, timestamp: 0,
    }),
    candles: () => Promise.resolve({ symbol: "", timeframe: "", candles: [], count: 0 }),
    depth: (symbol: string) => Promise.resolve<DepthResponse>({ symbol, bids: [], asks: [] }),
    optionChain: (underlying: string) =>
      Promise.resolve<OptionChainResponse>({ underlying, expiry: "all", contracts: [], count: 0 }),
    pcr: (underlying: string) =>
      Promise.resolve<PCRResponse>({
        timestamp: 0, underlying, expiry_kind: "MONTH", expiry_date: "", spot: 0,
        pcr_volume: null, pcr_oi: null, total_ce_volume: 0, total_pe_volume: 0,
        total_ce_oi: 0, total_pe_oi: 0,
      }),
    maxPain: (underlying: string) =>
      Promise.resolve<MaxPainResponse>({
        timestamp: 0, underlying, expiry_kind: "MONTH", expiry_date: "", spot: 0,
        max_pain_strike: 0, total_pain_at_max_pain: 0, distance_from_spot: 0, position_vs_spot: "at_spot",
      }),
    ivSurface: (underlying: string) =>
      Promise.resolve<IVSurfaceResponse>({
        timestamp: 0, underlying, expiry_kind: "MONTH", expiry_date: "", spot: 0,
        atm_strike: 0, atm_iv: 0, otm_put_iv: 0, otm_call_iv: 0, iv_skew: 0,
        put_call_iv_ratio: null, days_to_expiry: 0,
      }),
    volumeProfile: (underlying: string) =>
      Promise.resolve<VolumeProfileResponse>({ underlying, expiry: "all", strikes: [], profile: [], count: 0 }),
    positions: () => Promise.resolve<PositionsResponse>({ positions: [], count: 0, total_pnl: 0, total_pnl_percent: 0 }),
    holdings: () => Promise.resolve<HoldingsResponse>({ holdings: [], count: 0, total_value: 0, total_invested: 0, total_pnl: 0 }),
    portfolioSummary: () => Promise.resolve<PortfolioSummary>({ total_value: 0, total_invested: 0, total_pnl: 0, total_pnl_percent: 0, realized_pnl: 0, unrealized_pnl: 0, margin_used: 0, margin_available: 0, positions_count: 0, holdings_count: 0 }),
    orders: () => Promise.resolve<OrdersResponse>({ orders: [], count: 0 }),
    trades: () => Promise.resolve<TradesResponse>({ trades: [], count: 0 }),
    placeOrder: (req: OrderRequest) => Promise.resolve<OrderResponse>({
      order_id: "ord-1", symbol: req.symbol, exchange: req.exchange, transaction_type: req.transaction_type,
      order_type: req.order_type, quantity: req.quantity, price: req.price ?? null, status: "OPEN",
      filled_quantity: 0, average_price: null, timestamp: new Date().toISOString(),
    }),
    cancelOrder: (id: string) => Promise.resolve<OrderResponse>({
      order_id: id, symbol: "X", exchange: "NSE", transaction_type: "BUY", order_type: "LIMIT",
      quantity: 1, price: null, status: "CANCELLED", filled_quantity: 0, average_price: null,
      timestamp: new Date().toISOString(),
    }),
    scannerResults: () => Promise.resolve({ scans: [], count: 0 }),
    topCandidates: () => Promise.resolve<ScannerCandidatesResponse>({ candidates: [], count: 0 }),
    snapshots: () => Promise.resolve<ScannerCandidatesResponse>({ candidates: [], count: 0 }),
    runScanner: () => Promise.resolve({ scan_id: "s1", status: "completed" }),
    runBacktest: (req: BacktestRunRequest) => Promise.resolve<BacktestResultResponse>({
      run_id: "r1", symbol: req.symbol, timeframe: req.timeframe,
      metrics: { total_return_pct: 10, annualized_return_pct: 10, sharpe_ratio: 1.2, sortino_ratio: 1.5, max_drawdown_pct: 5, profit_factor: 1.8, win_rate: 55, total_trades: 20, winning_trades: 11, losing_trades: 9 },
      research_mode: "pure_sim", research_only: true,
    }),
    backtestResult: () => Promise.resolve<BacktestResultResponse>({
      run_id: "r1", symbol: "X", timeframe: "1d",
      metrics: { total_return_pct: 0, annualized_return_pct: 0, sharpe_ratio: 0, sortino_ratio: 0, max_drawdown_pct: 0, profit_factor: 0, win_rate: 0, total_trades: 0, winning_trades: 0, losing_trades: 0 },
      research_mode: "pure_sim", research_only: true,
    }),
    brokerHealth: () => Promise.resolve<BrokerHealth>({ status: "healthy", broker: "paper", describe: {}, timestamp: new Date().toISOString() }),
    brokerCapabilities: () => Promise.resolve<BrokerCapabilities>({ broker: "paper", capabilities: {} }),
  };
  return { ...base, ...overrides };
}
