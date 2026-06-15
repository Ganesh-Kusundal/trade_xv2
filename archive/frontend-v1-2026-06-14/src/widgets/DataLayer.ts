/**
 * DataLayer — central abstraction over REST, WebSocket, and DuckDB queries.
 *
 * Widgets MUST consume data through this layer. No widget should fetch
 * directly from a broker, REST endpoint, or WebSocket. This keeps widgets
 * decoupled from data sources and enables:
 *   - Easy mocking during frontend development
 *   - Caching & request deduplication
 *   - Swapping live sources without touching widget code
 *
 * In production, the implementations of these methods will call the
 * Python backend (FastAPI + WebSocket). During frontend dev, the
 * default mock implementations use the services/mockData.ts simulator.
 */

import {
  POSITIONS,
  OPEN_ORDERS,
  HOLDINGS,
  PORTFOLIO,
  RISK_METRICS,
  MARKET_BREADTH,
  SCANNERS,
  generateScanResults,
  generateOptionChain,
  generateQuote,
  generateCandles,
  SYMBOLS,
  STRATEGIES,
  SIGNALS,
  ALERTS,
  CLOSED_ORDERS,
  BACKTESTS,
} from '@/services/mockData'
import type { Quote, Candle, Order, Position, Holding, Portfolio, RiskMetrics, MarketBreadth, ScanResult, OptionChain, Strategy, Signal, Alert, BacktestResult } from '@/types/trading'

// In-flight request cache to prevent duplicate concurrent fetches
const inflight = new Map<string, Promise<any>>()

async function deduped<T>(key: string, fn: () => Promise<T>): Promise<T> {
  if (inflight.has(key)) return inflight.get(key)!
  const p = fn().finally(() => inflight.delete(key))
  inflight.set(key, p)
  return p
}

export const dataLayer = {
  // ── Quotes ──────────────────────────────────────────────────────────
  async getQuotes(symbols: string[]): Promise<Record<string, Quote>> {
    return deduped(`quotes:${symbols.join(',')}`, async () => {
      // Seed quotes — widgets will tick the live simulator on mount for real-time updates
      const result: Record<string, Quote> = {}
      for (const s of symbols) {
        result[s] = generateQuote(s)
      }
      return result
    })
  },

  async getQuote(symbol: string): Promise<Quote> {
    return deduped(`quote:${symbol}`, async () => generateQuote(symbol))
  },

  // ── Candles ─────────────────────────────────────────────────────────
  async getCandles(symbol: string, timeframe: '1m' | '5m' | '15m' | '1h' | '1d', bars = 200): Promise<Candle[]> {
    return deduped(`candles:${symbol}:${timeframe}:${bars}`, async () => {
      return generateCandles(symbol, timeframe, bars)
    })
  },

  // ── Portfolio ───────────────────────────────────────────────────────
  async getPortfolio(): Promise<Portfolio> {
    return Promise.resolve(PORTFOLIO)
  },

  async getPositions(): Promise<Position[]> {
    return Promise.resolve(POSITIONS)
  },

  async getHoldings(): Promise<Holding[]> {
    return Promise.resolve(HOLDINGS)
  },

  // ── Orders ──────────────────────────────────────────────────────────
  async getOpenOrders(): Promise<Order[]> {
    return Promise.resolve(OPEN_ORDERS)
  },

  async getOrderHistory(): Promise<Order[]> {
    return Promise.resolve(CLOSED_ORDERS)
  },

  // ── Risk ────────────────────────────────────────────────────────────
  async getRiskMetrics(): Promise<RiskMetrics> {
    return Promise.resolve(RISK_METRICS)
  },

  // ── Market ──────────────────────────────────────────────────────────
  async getMarketBreadth(): Promise<MarketBreadth> {
    return Promise.resolve(MARKET_BREADTH)
  },

  async getSymbols(): Promise<typeof SYMBOLS> {
    return Promise.resolve(SYMBOLS)
  },

  // ── Scanners ────────────────────────────────────────────────────────
  async listScanners() {
    return Promise.resolve(SCANNERS)
  },

  async runScan(scannerId: string): Promise<ScanResult> {
    return deduped(`scan:${scannerId}`, async () => {
      const scanner = SCANNERS.find((s) => s.id === scannerId) || SCANNERS[0]
      return generateScanResults(scanner)
    })
  },

  // ── Options ─────────────────────────────────────────────────────────
  async getOptionChain(underlying = 'NIFTY', spot?: number): Promise<OptionChain> {
    return deduped(`oc:${underlying}:${spot}`, async () => {
      return generateOptionChain(underlying, spot || (underlying === 'NIFTY' ? 24_900 : 2_900))
    })
  },

  // ── Strategies ──────────────────────────────────────────────────────
  async listStrategies(): Promise<Strategy[]> {
    return Promise.resolve(STRATEGIES)
  },

  async getSignals(): Promise<Signal[]> {
    return Promise.resolve(SIGNALS)
  },

  // ── Alerts ──────────────────────────────────────────────────────────
  async listAlerts(): Promise<Alert[]> {
    return Promise.resolve(ALERTS)
  },

  // ── Backtests ───────────────────────────────────────────────────────
  async listBacktests(): Promise<BacktestResult[]> {
    return Promise.resolve(BACKTESTS)
  },
}
