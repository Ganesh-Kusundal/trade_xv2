/**
 * Typed API client for the TradeXV2 FastAPI backend.
 *
 * Mirrors the real routes under `/api/v1` (see src/interface/api/main.py):
 *   health, market, symbols, portfolio, orders, scanner, backtest, live/*.
 *
 * The client only depends on `fetch`, so it is trivially mockable in tests
 * (components consume the `TradingApi` interface, not the concrete class).
 */
import type {
  BacktestResultResponse,
  BacktestRunRequest,
  BrokerCapabilities,
  BrokerHealth,
  CandlesResponse,
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
import { API_BASE, API_KEY } from "./config";

/** Raised for non-2xx responses. `detail` carries FastAPI's `detail` body. */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: unknown,
    message?: string,
  ) {
    super(message ?? `API error ${status}`);
    this.name = "ApiError";
  }
}

export interface OrderQuery {
  status?: string;
  from_date?: string;
  to_date?: string;
  limit?: number;
}

/**
 * Structural contract that UI components depend on. `ApiClient` implements it;
 * tests provide a hand-written fake implementing only the methods they use.
 */
export interface TradingApi {
  health(): Promise<HealthResponse>;
  readiness(): Promise<ReadinessResponse>;
  metrics(): Promise<Record<string, unknown>>;

  quote(symbol: string, exchange?: string): Promise<QuoteResponse>;
  candles(params: {
    symbol: string;
    timeframe: string;
    from_ts?: number;
    to_ts?: number;
    limit?: number;
  }): Promise<CandlesResponse>;
  depth(symbol: string, exchange?: string): Promise<DepthResponse>;

  optionChain(underlying: string, params?: { expiry?: string; strike_range?: number }): Promise<OptionChainResponse>;
  pcr(underlying: string, expiry?: string): Promise<PCRResponse>;
  maxPain(underlying: string, expiry?: string): Promise<MaxPainResponse>;
  ivSurface(underlying: string, params?: { expiry?: string; option_type?: string }): Promise<IVSurfaceResponse>;
  volumeProfile(underlying: string, expiry?: string): Promise<VolumeProfileResponse>;

  positions(status?: string): Promise<PositionsResponse>;
  holdings(): Promise<HoldingsResponse>;
  portfolioSummary(): Promise<PortfolioSummary>;

  orders(params?: OrderQuery): Promise<OrdersResponse>;
  trades(): Promise<TradesResponse>;
  placeOrder(req: OrderRequest): Promise<OrderResponse>;
  cancelOrder(orderId: string): Promise<OrderResponse>;

  scannerResults(params?: {
    scanner_name?: string;
    date?: string;
    limit?: number;
  }): Promise<{ scans: unknown[]; count: number }>;
  topCandidates(limit?: number): Promise<ScannerCandidatesResponse>;
  snapshots(limit?: number): Promise<ScannerCandidatesResponse>;
  runScanner(scannerName: string, universe?: string): Promise<Record<string, unknown>>;

  runBacktest(req: BacktestRunRequest): Promise<BacktestResultResponse>;
  backtestResult(runId: string): Promise<BacktestResultResponse>;

  brokerHealth(): Promise<BrokerHealth>;
  brokerCapabilities(): Promise<BrokerCapabilities>;
}

export class ApiClient implements TradingApi {
  constructor(
    private readonly baseUrl: string = API_BASE,
    private readonly apiKey: string | undefined = API_KEY,
  ) {}

  private get prefix(): string {
    return `${this.baseUrl}/api/v1`;
  }

  private async request<T>(
    path: string,
    init?: RequestInit,
    query?: Record<string, string | number | undefined>,
  ): Promise<T> {
    const url = new URL(`${this.prefix}${path}`, "http://localhost");
    // URL with a dummy base keeps the relative `/api/v1/...` path when baseUrl is "".
    if (query) {
      for (const [k, v] of Object.entries(query)) {
        if (v !== undefined) url.searchParams.set(k, String(v));
      }
    }
    const target = this.baseUrl
      ? `${this.baseUrl}/api/v1${path}${url.search}`
      : `/api/v1${path}${url.search}`;

    const headers = new Headers(init?.headers);
    headers.set("Content-Type", "application/json");
    if (this.apiKey) headers.set("X-API-Key", this.apiKey);

    let res: Response;
    try {
      res = await fetch(target, { ...init, headers });
    } catch (e) {
      throw new ApiError(0, null, `Network error: ${(e as Error).message}`);
    }

    const text = await res.text();
    const body = text ? JSON.parse(text) : null;

    if (!res.ok) {
      const detail = body?.detail ?? body;
      throw new ApiError(res.status, detail, `API error ${res.status}`);
    }
    return body as T;
  }

  // ── Health ────────────────────────────────────────────────────────────────
  health() {
    return this.request<HealthResponse>("/health");
  }
  readiness() {
    return this.request<ReadinessResponse>("/health/readyz");
  }
  metrics() {
    return this.request<Record<string, unknown>>("/health/metrics");
  }

  // ── Market ─────────────────────────────────────────────────────────────────
  quote(symbol: string, exchange = "NSE") {
    return this.request<QuoteResponse>(
      `/market/quote/${encodeURIComponent(symbol)}`,
      undefined,
      { exchange },
    );
  }
  candles(params: {
    symbol: string;
    timeframe: string;
    from_ts?: number;
    to_ts?: number;
    limit?: number;
  }) {
    return this.request<CandlesResponse>("/market/candles", undefined, {
      symbol: params.symbol,
      timeframe: params.timeframe,
      from_ts: params.from_ts,
      to_ts: params.to_ts,
      limit: params.limit,
    });
  }
  depth(symbol: string, exchange = "NSE") {
    return this.request<DepthResponse>(
      `/live/depth/${encodeURIComponent(symbol)}`,
      undefined,
      { exchange },
    );
  }

  // ── Options Analytics ───────────────────────────────────────────────────
  optionChain(underlying: string, params?: { expiry?: string; strike_range?: number }) {
    return this.request<OptionChainResponse>(
      `/options/chain/${encodeURIComponent(underlying.toUpperCase())}`,
      undefined,
      { expiry: params?.expiry, strike_range: params?.strike_range },
    );
  }
  pcr(underlying: string, expiry?: string) {
    return this.request<PCRResponse>(
      `/options/pcr/${encodeURIComponent(underlying.toUpperCase())}`,
      undefined,
      { expiry },
    );
  }
  maxPain(underlying: string, expiry?: string) {
    return this.request<MaxPainResponse>(
      `/options/max-pain/${encodeURIComponent(underlying.toUpperCase())}`,
      undefined,
      { expiry },
    );
  }
  ivSurface(underlying: string, params?: { expiry?: string; option_type?: string }) {
    return this.request<IVSurfaceResponse>(
      `/options/iv-surface/${encodeURIComponent(underlying.toUpperCase())}`,
      undefined,
      { expiry: params?.expiry, option_type: params?.option_type },
    );
  }
  volumeProfile(underlying: string, expiry?: string) {
    return this.request<VolumeProfileResponse>(
      `/options/volume-profile/${encodeURIComponent(underlying.toUpperCase())}`,
      undefined,
      { expiry },
    );
  }

  // ── Portfolio ──────────────────────────────────────────────────────────────
  positions(status?: string) {
    return this.request<PositionsResponse>("/portfolio/positions", undefined, {
      status,
    });
  }
  holdings() {
    return this.request<HoldingsResponse>("/portfolio/holdings");
  }
  portfolioSummary() {
    return this.request<PortfolioSummary>("/portfolio/summary");
  }

  // ── Orders ────────────────────────────────────────────────────────────────
  orders(params?: OrderQuery) {
    return this.request<OrdersResponse>("/orders", undefined, {
      status: params?.status,
      from_date: params?.from_date,
      to_date: params?.to_date,
      limit: params?.limit,
    });
  }
  trades() {
    return this.request<TradesResponse>("/orders/trades");
  }
  placeOrder(req: OrderRequest) {
    return this.request<OrderResponse>("/orders", {
      method: "POST",
      body: JSON.stringify(req),
    });
  }
  cancelOrder(orderId: string) {
    return this.request<OrderResponse>(`/orders/${encodeURIComponent(orderId)}`, {
      method: "DELETE",
    });
  }

  // ── Scanner ─────────────────────────────────────────────────────────────────
  scannerResults(params?: {
    scanner_name?: string;
    date?: string;
    limit?: number;
  }) {
    return this.request<{ scans: unknown[]; count: number }>("/scanner/results", undefined, {
      scanner_name: params?.scanner_name,
      date: params?.date,
      limit: params?.limit,
    });
  }
  topCandidates(limit = 10) {
    return this.request<ScannerCandidatesResponse>("/scanner/top-candidates", undefined, {
      limit,
    });
  }
  snapshots(limit = 50) {
    return this.request<ScannerCandidatesResponse>("/scanner/snapshots", undefined, {
      limit,
    });
  }
  runScanner(scannerName: string, universe = "NIFTY500") {
    return this.request<Record<string, unknown>>("/scanner/run", undefined, {
      scanner_name: scannerName,
      universe,
    });
  }

  // ── Backtest ─────────────────────────────────────────────────────────────────
  runBacktest(req: BacktestRunRequest) {
    return this.request<BacktestResultResponse>("/backtest/run", {
      method: "POST",
      body: JSON.stringify(req),
    });
  }
  backtestResult(runId: string) {
    return this.request<BacktestResultResponse>(
      `/backtest/results/${encodeURIComponent(runId)}`,
    );
  }

  // ── Live broker (connectivity / status) ────────────────────────────────────
  brokerHealth() {
    return this.request<BrokerHealth>("/live/health");
  }
  brokerCapabilities() {
    return this.request<BrokerCapabilities>("/live/capabilities");
  }
}
