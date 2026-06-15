/**
 * Mock data service — references the Python backend contracts but generates
 * realistic synthetic data for the frontend.
 *
 * Backend modules referenced:
 *   - datalake.gateway.DataLakeGateway  (historical candles)
 *   - datalake.catalog.DataCatalog       (symbol universe, sector mapping)
 *   - brokers.dhan.market_data.*        (live quotes, depth, option chain)
 *   - analytics.scanner.scanners.*      (scan results)
 *   - analytics.options.options_analytics.* (option chain analytics)
 *   - analytics.backtest.engine.*       (backtest results)
 *   - analytics.strategy.pipeline.*     (signals)
 *   - analytics.market_breadth.breadth.* (market breadth)
 *
 * Replace these services with real API calls once the backend FastAPI/WS
 * layer is in place.
 */

import type {
  Quote,
  Candle,
  Position,
  Order,
  Holding,
  Strategy,
  ScanResult,
  Scanner,
  Signal,
  OptionChain,
  OptionStrike,
  MarketBreadth,
  Portfolio,
  RiskMetrics,
  Alert,
  SectorPerformance,
  BacktestResult,
  Indicator,
  Symbol,
  Universe,
  Exchange,
} from '@/types/trading'
import { randomBetween } from '@/lib/utils'

// ───────────────────────────────────────────────────────────────────────────
// Symbol Universe (mirrors ind_nifty100list.csv + data/sectors/nifty_sector_mapping.csv)
// ───────────────────────────────────────────────────────────────────────────

const SECTOR_MAP: Record<string, string> = {
  RELIANCE: 'OilGas',
  TCS: 'IT',
  HDFCBANK: 'Finance',
  INFY: 'IT',
  ICICIBANK: 'Finance',
  HINDUNILVR: 'FMCG',
  ITC: 'FMCG',
  SBIN: 'Finance',
  BHARTIARTL: 'Telecom',
  KOTAKBANK: 'Finance',
  LT: 'CapitalGoods',
  AXISBANK: 'Finance',
  ASIANPAINT: 'ConsumerDur',
  MARUTI: 'Auto',
  BAJFINANCE: 'Finance',
  WIPRO: 'IT',
  HCLTECH: 'IT',
  SUNPHARMA: 'Pharma',
  TITAN: 'ConsumerDur',
  ULTRACEMCO: 'Cement',
  NESTLEIND: 'FMCG',
  TECHM: 'IT',
  POWERGRID: 'Power',
  NTPC: 'Power',
  'M&M': 'Auto',
  TATAMOTORS: 'Auto',
  TATASTEEL: 'Metals',
  ADANIENT: 'Metals',
  ADANIPORTS: 'Services',
  COALINDIA: 'Metals',
  ONGC: 'OilGas',
  JSPL: 'Metals',
  VEDL: 'Metals',
  DRREDDY: 'Pharma',
  CIPLA: 'Pharma',
  APOLLOHOSP: 'Healthcare',
  BRITANNIA: 'FMCG',
  EICHERMOT: 'Auto',
  HEROMOTOCO: 'Auto',
  BAJAJFINSV: 'Finance',
  INDUSINDBK: 'Finance',
  BANDHANBNK: 'Finance',
  IDEA: 'Telecom',
  YESBANK: 'Finance',
  PNB: 'Finance',
  BANKBARODA: 'Finance',
  CANBK: 'Finance',
  SBILIFE: 'Finance',
  HDFCLIFE: 'Finance',
  ICICIPRULI: 'Finance',
  DIVISLAB: 'Pharma',
  BIOCON: 'Pharma',
  LUPIN: 'Pharma',
  AUROPHARMA: 'Pharma',
  TATAPOWER: 'Power',
  ADANIGREEN: 'Power',
  ADANIPOWER: 'Power',
  JSWSTEEL: 'Metals',
  HINDALCO: 'Metals',
  GRASIM: 'Cement',
  AMBUJACEM: 'Cement',
  ACC: 'Cement',
  SHREECEM: 'Cement',
  BPCL: 'OilGas',
  IOC: 'OilGas',
  GAIL: 'OilGas',
  PIDILITIND: 'Chemicals',
  ASHOKLEY: 'Auto',
  TATACHEM: 'Chemicals',
  UPL: 'Chemicals',
  HAVELLS: 'ConsumerDur',
  VOLTAS: 'ConsumerDur',
  GODREJCP: 'FMCG',
  DABUR: 'FMCG',
  MARICO: 'FMCG',
  COLPAL: 'FMCG',
  EMAMILTD: 'FMCG',
  SIEMENS: 'CapitalGoods',
  ABB: 'CapitalGoods',
  CUMMINSIND: 'CapitalGoods',
  BHEL: 'CapitalGoods',
  'L&TFH': 'Finance',
  CHOLAFIN: 'Finance',
  SRF: 'Chemicals',
  MGL: 'OilGas',
  PETRONET: 'OilGas',
  RECLTD: 'Finance',
  PFC: 'Finance',
  IEX: 'Power',
  CONCOR: 'Services',
  BEL: 'CapitalGoods',
  HAL: 'CapitalGoods',
  BEML: 'CapitalGoods',
  COFORGE: 'IT',
  MPHASIS: 'IT',
  LTIM: 'IT',
  PERSISTENT: 'IT',
  OFSS: 'IT',
  KPITTECH: 'IT',
  ZOMATO: 'ConsumerServices',
  PAYTM: 'Finance',
  NYKAA: 'ConsumerServices',
  POLICYBZR: 'Finance',
  DELHIVERY: 'Services',
  IRCTC: 'ConsumerServices',
  JINDALSTEL: 'Metals',
  SAIL: 'Metals',
  NMDC: 'Metals',
  NATIONALUM: 'Metals',
  APLAPOLLO: 'Metals',
  ASTRAL: 'CapitalGoods',
  POLYCAB: 'CapitalGoods',
  KEI: 'CapitalGoods',
  TRENT: 'ConsumerServices',
  PAGEIND: 'ConsumerServices',
  BAJAJHLDNG: 'Finance',
  MUTHOOTFIN: 'Finance',
  MANAPPURAM: 'Finance',
  LICHSGFIN: 'Finance',
  PNBHOUSING: 'Finance',
  GODREJPROP: 'Realty',
  OBEREALTY: 'Realty',
  PRESTIGE: 'Realty',
  PHOENIXLTD: 'Realty',
  BRIGADE: 'Realty',
  MAHLIFE: 'Realty',
  SOBHA: 'Realty',
  HDFCAMC: 'Finance',
  'NAM-INDIA': 'Finance',
  UTIAMC: 'Finance',
  ABCAPITAL: 'Finance',
  MOTILALOFS: 'Finance',
  IIFL: 'Finance',
  MCX: 'Finance',
  BSE: 'Finance',
  CDSL: 'Finance',
  KFIN: 'Finance',
  ANGELONE: 'Finance',
  ZERODHA: 'Finance',
}

const NIFTY50_SYMBOLS: string[] = [
  'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 'HINDUNILVR', 'ITC', 'SBIN',
  'BHARTIARTL', 'KOTAKBANK', 'LT', 'AXISBANK', 'ASIANPAINT', 'MARUTI', 'BAJFINANCE',
  'WIPRO', 'HCLTECH', 'SUNPHARMA', 'TITAN', 'ULTRACEMCO', 'NESTLEIND', 'TECHM',
  'POWERGRID', 'NTPC', 'M&M', 'TATAMOTORS', 'TATASTEEL', 'ADANIENT', 'ADANIPORTS',
  'COALINDIA', 'ONGC', 'JSWSTEEL', 'HINDALCO', 'GRASIM', 'BPCL', 'IOC', 'DRREDDY',
  'CIPLA', 'APOLLOHOSP', 'BRITANNIA', 'EICHERMOT', 'HEROMOTOCO', 'BAJAJFINSV',
  'INDUSINDBK', 'DIVISLAB', 'TATAPOWER', 'ADANIGREEN', 'WIPRO', 'SBILIFE', 'HDFCLIFE',
]

const NIFTY100_EXTRA: string[] = [
  'BANKBARODA', 'CANBK', 'PNB', 'IDEA', 'YESBANK', 'BANDHANBNK', 'FEDERALBNK',
  'IDFCFIRSTB', 'AUBANK', 'CHOLAFIN', 'L&TFH', 'MUTHOOTFIN', 'MANAPPURAM',
  'PNBHOUSING', 'LICHSGFIN', 'PEL', 'SRF', 'PIDILITIND', 'ASHOKLEY', 'TATACHEM',
  'UPL', 'SIEMENS', 'ABB', 'CUMMINSIND', 'BHEL', 'BEL', 'HAL', 'COFORGE', 'MPHASIS',
  'LTIM', 'PERSISTENT', 'OFSS', 'CONCOR', 'BEML', 'IRCTC', 'ZOMATO', 'PAYTM',
  'POLICYBZR', 'DELHIVERY', 'NYKAA', 'TRENT', 'PAGEIND', 'GODREJPROP', 'OBEREALTY',
  'PRESTIGE', 'PHOENIXLTD', 'BRIGADE', 'MAHLIFE', 'SOBHA', 'ABCAPITAL', 'MCX',
  'BSE', 'CDSL', 'KFIN', 'ANGELONE',
]

const SECTOR_DEFAULTS: Record<string, string> = {
  Auto: 'Auto',
  Bank: 'Finance',
  Finance: 'Finance',
  IT: 'IT',
  Pharma: 'Pharma',
  FMCG: 'FMCG',
  Metal: 'Metals',
  Energy: 'OilGas',
  Realty: 'Realty',
}

export const SYMBOLS: Symbol[] = [
  ...NIFTY50_SYMBOLS,
  ...NIFTY100_EXTRA,
].map((sym) => ({
  symbol: sym,
  name: sym.charAt(0) + sym.slice(1).toLowerCase().replace(/(?:bank|fin|life)$/i, (m) => ` ${m.toUpperCase()}`),
  exchange: 'NSE' as Exchange,
  sector: SECTOR_MAP[sym] || 'Misc',
  industry: SECTOR_MAP[sym] || 'Misc',
  isin: `INE${Math.random().toString(36).slice(2, 12).toUpperCase()}`,
  lotSize: 1,
  tickSize: 0.05,
}))

export const SECTORS = Array.from(new Set(SYMBOLS.map((s) => s.sector))).sort()

export function getUniverseSymbols(universe: Universe): string[] {
  switch (universe) {
    case 'NIFTY50':
      return NIFTY50_SYMBOLS
    case 'NIFTY100':
      return [...NIFTY50_SYMBOLS, ...NIFTY100_EXTRA].slice(0, 100)
    case 'NIFTY200':
      return [...NIFTY50_SYMBOLS, ...NIFTY100_EXTRA, ...Array(100).fill(0).map((_, i) => `STOCK${i}`)].slice(0, 200)
    case 'NIFTY500':
      return [...NIFTY50_SYMBOLS, ...NIFTY100_EXTRA, ...Array(300).fill(0).map((_, i) => `STOCK${i}`)].slice(0, 500)
    case 'BANKNIFTY':
      return ['HDFCBANK', 'ICICIBANK', 'SBIN', 'KOTAKBANK', 'AXISBANK', 'INDUSINDBK', 'BAJFINANCE', 'BANKBARODA', 'PNB', 'CANBK', 'IDFCFIRSTB', 'FEDERALBNK', 'AUBANK', 'BANDHANBNK', 'YESBANK']
    case 'FINNIFTY':
      return ['BAJFINANCE', 'HDFCAMC', 'CHOLAFIN', 'SBILIFE', 'HDFCLIFE', 'ICICIPRULI', 'SHRIRAMFIN', 'MUTHOOTFIN', 'MANAPPURAM', 'LICHSGFIN', 'PEL', 'PNBHOUSING', 'L&TFH', 'ABCAPITAL', 'POONAWALLA']
    case 'CUSTOM':
      return NIFTY50_SYMBOLS
    default:
      return NIFTY50_SYMBOLS
  }
}

// ───────────────────────────────────────────────────────────────────────────
// Quote generation
// ───────────────────────────────────────────────────────────────────────────

const basePrices: Record<string, number> = {
  RELIANCE: 2935.4, TCS: 4080.5, HDFCBANK: 1670.2, INFY: 1847.3, ICICIBANK: 1290.5,
  HINDUNILVR: 2370.0, ITC: 480.0, SBIN: 825.0, BHARTIARTL: 1610.2, KOTAKBANK: 1750.0,
  LT: 3680.0, AXISBANK: 1175.0, ASIANPAINT: 2380.0, MARUTI: 12450.0, BAJFINANCE: 7180.0,
  WIPRO: 530.0, HCLTECH: 1800.0, SUNPHARMA: 1820.0, TITAN: 3640.0, ULTRACEMCO: 11800.0,
  NESTLEIND: 2280.0, TECHM: 1690.0, POWERGRID: 312.0, NTPC: 380.0, 'M&M': 2890.0,
  TATAMOTORS: 950.0, TATASTEEL: 152.0, ADANIENT: 2640.0, ADANIPORTS: 1390.0, COALINDIA: 425.0,
  ONGC: 270.0, JSWSTEEL: 920.0, HINDALCO: 650.0, GRASIM: 2680.0, BPCL: 320.0, IOC: 142.0,
  DRREDDY: 1240.0, CIPLA: 1520.0, APOLLOHOSP: 7080.0, BRITANNIA: 4820.0, EICHERMOT: 4870.0,
  HEROMOTOCO: 4780.0, BAJAJFINSV: 1640.0, INDUSINDBK: 1480.0, DIVISLAB: 6080.0, TATAPOWER: 415.0,
  ADANIGREEN: 1010.0, SBILIFE: 1820.0, HDFCLIFE: 680.0,
}

export function getBasePrice(symbol: string): number {
  return basePrices[symbol] || randomBetween(200, 5000)
}

export function generateQuote(symbol: string, override?: Partial<Quote>): Quote {
  const base = getBasePrice(symbol)
  const changePct = randomBetween(-3, 3)
  const change = (base * changePct) / 100
  const ltp = base + change
  const open = base + randomBetween(-base * 0.015, base * 0.015)
  const high = Math.max(ltp, open) + randomBetween(0, base * 0.012)
  const low = Math.min(ltp, open) - randomBetween(0, base * 0.012)
  const volume = Math.floor(randomBetween(100_000, 8_000_000))
  const vwap = (high + low + ltp) / 3
  return {
    symbol,
    exchange: 'NSE',
    ltp: Number(ltp.toFixed(2)),
    change: Number(change.toFixed(2)),
    changePct: Number(changePct.toFixed(2)),
    open: Number(open.toFixed(2)),
    high: Number(high.toFixed(2)),
    low: Number(low.toFixed(2)),
    prevClose: Number(base.toFixed(2)),
    volume,
    value: Math.floor(volume * ltp),
    vwap: Number(vwap.toFixed(2)),
    bid: Number((ltp - 0.05).toFixed(2)),
    ask: Number((ltp + 0.05).toFixed(2)),
    bidQty: Math.floor(randomBetween(100, 5000)),
    askQty: Math.floor(randomBetween(100, 5000)),
    oi: Math.floor(randomBetween(50_000, 5_000_000)),
    oiChange: Math.floor(randomBetween(-100_000, 100_000)),
    timestamp: Date.now(),
    ...override,
  }
}

// ───────────────────────────────────────────────────────────────────────────
// Candle history (synthetic, walks around base price)
// ───────────────────────────────────────────────────────────────────────────

export function generateCandles(
  symbol: string,
  timeframe: '1m' | '5m' | '15m' | '1h' | '1d' = '5m',
  bars = 200,
): Candle[] {
  const base = getBasePrice(symbol)
  const now = Date.now()
  const tfMs: Record<string, number> = {
    '1m': 60_000,
    '5m': 300_000,
    '15m': 900_000,
    '1h': 3_600_000,
    '1d': 86_400_000,
  }
  const ms = tfMs[timeframe]
  const candles: Candle[] = []
  let price = base * (1 - randomBetween(0, 0.08))

  for (let i = bars - 1; i >= 0; i--) {
    const drift = (base - price) * 0.02
    const vol = base * 0.005
    const open = price
    const close = open + drift + randomBetween(-vol, vol)
    const high = Math.max(open, close) + randomBetween(0, vol)
    const low = Math.min(open, close) - randomBetween(0, vol)
    const volume = Math.floor(randomBetween(10_000, 500_000))
    candles.push({
      timestamp: now - i * ms,
      open: Number(open.toFixed(2)),
      high: Number(high.toFixed(2)),
      low: Number(low.toFixed(2)),
      close: Number(close.toFixed(2)),
      volume,
      vwap: Number(((open + high + low + close) / 4).toFixed(2)),
    })
    price = close
  }
  return candles
}

// ───────────────────────────────────────────────────────────────────────────
// Portfolio / Positions / Orders
// ───────────────────────────────────────────────────────────────────────────

const SEED_POSITIONS = ['RELIANCE', 'SBIN', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK', 'ITC', 'LT']

export const POSITIONS: Position[] = SEED_POSITIONS.map((sym) => {
  const q = generateQuote(sym)
  const qty = Math.floor(randomBetween(50, 500))
  const avg = q.ltp * (1 + randomBetween(-0.04, 0.04))
  const pnl = (q.ltp - avg) * qty
  return {
    symbol: sym,
    exchange: 'NSE',
    side: 'BUY',
    quantity: qty,
    avgPrice: Number(avg.toFixed(2)),
    ltp: q.ltp,
    pnl: Number(pnl.toFixed(2)),
    pnlPct: Number(((pnl / (avg * qty)) * 100).toFixed(2)),
    product: 'MIS',
    dayChange: q.change,
    dayChangePct: q.changePct,
  }
})

export const OPEN_ORDERS: Order[] = [
  { orderId: 'ORD-24060101', symbol: 'RELIANCE', exchange: 'NSE', side: 'BUY', quantity: 100, filledQty: 0, avgPrice: 0, price: 2935.4, triggerPrice: 0, orderType: 'LIMIT', product: 'MIS', status: 'OPEN', strategy: 'HalfTrend Intraday', placedAt: Date.now() - 1000 * 60 * 12, updatedAt: Date.now() - 1000 * 60 * 11 },
  { orderId: 'ORD-24060102', symbol: 'SBIN', exchange: 'NSE', side: 'BUY', quantity: 200, filledQty: 0, avgPrice: 0, price: 808.1, triggerPrice: 0, orderType: 'LIMIT', product: 'MIS', status: 'OPEN', strategy: 'HalfTrend Intraday', placedAt: Date.now() - 1000 * 60 * 12, updatedAt: Date.now() - 1000 * 60 * 11 },
  { orderId: 'ORD-24060103', symbol: 'TCS', exchange: 'NSE', side: 'BUY', quantity: 50, filledQty: 0, avgPrice: 0, price: 3650.0, triggerPrice: 0, orderType: 'LIMIT', product: 'MIS', status: 'OPEN', strategy: 'VWAP Momentum', placedAt: Date.now() - 1000 * 60 * 9, updatedAt: Date.now() - 1000 * 60 * 9 },
  { orderId: 'ORD-24060104', symbol: 'HDFCBANK', exchange: 'NSE', side: 'BUY', quantity: 50, filledQty: 0, avgPrice: 0, price: 1640.0, triggerPrice: 0, orderType: 'STOP_LOSS', product: 'MIS', status: 'OPEN', strategy: 'OI Build-up', placedAt: Date.now() - 1000 * 60 * 7, updatedAt: Date.now() - 1000 * 60 * 7 },
  { orderId: 'ORD-24060105', symbol: 'ICICIBANK', exchange: 'NSE', side: 'BUY', quantity: 100, filledQty: 0, avgPrice: 0, price: 1240.0, triggerPrice: 0, orderType: 'LIMIT', product: 'MIS', status: 'OPEN', strategy: 'Opening Range Breakout', placedAt: Date.now() - 1000 * 60 * 5, updatedAt: Date.now() - 1000 * 60 * 5 },
]

export const CLOSED_ORDERS: Order[] = Array.from({ length: 12 }, (_, i) => {
  const sym = SEED_POSITIONS[i % SEED_POSITIONS.length]
  const q = generateQuote(sym)
  const side: 'BUY' | 'SELL' = i % 2 === 0 ? 'BUY' : 'SELL'
  const qty = Math.floor(randomBetween(50, 300))
  const entry = q.ltp * (1 + randomBetween(-0.02, 0.02))
  const exit = entry * (1 + randomBetween(-0.015, 0.025))
  return {
    orderId: `ORD-${24060000 + i}`,
    symbol: sym,
    exchange: 'NSE',
    side,
    quantity: qty,
    filledQty: qty,
    avgPrice: Number(side === 'BUY' ? entry.toFixed(2) : exit.toFixed(2)),
    price: Number(entry.toFixed(2)),
    triggerPrice: 0,
    orderType: 'MARKET',
    product: 'MIS',
    status: 'FILLED',
    strategy: ['HalfTrend Intraday', 'VWAP Momentum', 'OI Build-up', 'Opening Range Breakout'][i % 4],
    placedAt: Date.now() - 1000 * 60 * (60 + i * 10),
    updatedAt: Date.now() - 1000 * 60 * (50 + i * 10),
  }
})

export const HOLDINGS: Holding[] = SEED_POSITIONS.slice(0, 4).map((sym) => {
  const q = generateQuote(sym)
  const qty = Math.floor(randomBetween(20, 200))
  const avg = q.ltp * (1 + randomBetween(-0.06, 0.06))
  const pnl = (q.ltp - avg) * qty
  return {
    symbol: sym,
    exchange: 'NSE',
    quantity: qty,
    avgPrice: Number(avg.toFixed(2)),
    ltp: q.ltp,
    pnl: Number(pnl.toFixed(2)),
    pnlPct: Number(((pnl / (avg * qty)) * 100).toFixed(2)),
    dayChange: q.change,
    dayChangePct: q.changePct,
  }
})

export const PORTFOLIO: Portfolio = {
  totalValue: 12_45_678.9,
  investedValue: 9_85_000,
  availableCash: 2_60_678.9,
  marginUsed: 1_45_000,
  totalPnl: 2_83_456.6,
  totalPnlPct: 22.89,
  todayPnl: 14_256.4,
  todayPnlPct: 1.16,
  weekPnl: 32_456.6,
  monthPnl: 78_342.0,
  unrealizedPnl: 14_256.4,
  realizedPnl: 2_69_200.2,
  positionsCount: 8,
  openOrdersCount: 5,
  buyingPower: 4_50_000,
}

export const RISK_METRICS: RiskMetrics = {
  portfolioVar: 1.85,
  expectedShortfall: 2.45,
  maxDrawdown: -8.35,
  currentDrawdown: -1.20,
  beta: 0.95,
  alpha: 4.8,
  sharpe: 1.85,
  sortino: 2.45,
  exposure: { long: 65.0, short: 0, net: 65.0, gross: 65.0 },
  concentration: { topPosition: 18.2, top5: 58.4, top10: 78.0, sectorMax: 28.5 },
  margin: { used: 145_000, available: 855_000, utilization: 14.5 },
}

// ───────────────────────────────────────────────────────────────────────────
// Scanners
// ───────────────────────────────────────────────────────────────────────────

export const SCANNERS: Scanner[] = [
  { id: 'sc-1', name: 'RS Momentum Scan', type: 'MOMENTUM', universe: 'NIFTY500', filters: [], schedule: 'Every 1m', enabled: true, lastRun: Date.now() - 60_000, resultCount: 502 },
  { id: 'sc-2', name: 'Volume Breakout Scan', type: 'BREAKOUT', universe: 'NIFTY500', filters: [], schedule: 'Every 1m', enabled: true, lastRun: Date.now() - 90_000, resultCount: 500 },
  { id: 'sc-3', name: 'OI Build-up Scan', type: 'OI_BUILDER', universe: 'NIFTY50', filters: [], schedule: 'Every 1m', enabled: true, lastRun: Date.now() - 70_000, resultCount: 50 },
  { id: 'sc-4', name: 'VWAP Reversal Scan', type: 'VWAP', universe: 'NIFTY100', filters: [], schedule: 'Every 5m', enabled: true, lastRun: Date.now() - 180_000, resultCount: 100 },
  { id: 'sc-5', name: 'RS Rank Top 50', type: 'RS', universe: 'NIFTY200', filters: [], schedule: 'Daily 9:00', enabled: true, lastRun: Date.now() - 3_600_000, resultCount: 200 },
  { id: 'sc-6', name: 'Opening Range Breakout', type: 'BREAKOUT', universe: 'NIFTY500', filters: [], schedule: '9:30', enabled: false, resultCount: 0 },
]

export function generateScanResults(scanner: Scanner): ScanResult {
  const universe = getUniverseSymbols(scanner.universe)
  const count = Math.min(50, Math.floor(universe.length * 0.4))
  const candidates = universe
    .slice(0, count)
    .map((sym, i) => {
      const rsi = randomBetween(20, 85)
      const roc = randomBetween(-5, 12)
      const volRatio = randomBetween(0.5, 4)
      const score = Math.max(0, Math.min(100, 100 - i * 1.5 + randomBetween(-5, 5)))
      const reasons: string[] = []
      if (rsi > 60) reasons.push('RSI > 60')
      if (rsi < 40) reasons.push('RSI < 40')
      if (roc > 3) reasons.push(`ROC ${roc.toFixed(1)}%`)
      if (volRatio > 2) reasons.push(`Vol ${volRatio.toFixed(1)}x`)
      return {
        symbol: sym,
        score: Number(score.toFixed(2)),
        reasons,
        metrics: { rsi: Number(rsi.toFixed(1)), roc: Number(roc.toFixed(2)), volRatio: Number(volRatio.toFixed(2)) },
        rank: i + 1,
        prevRank: i + 1 + Math.floor(randomBetween(-3, 3)),
      }
    })
    .sort((a, b) => b.score - a.score)
    .map((c, i) => ({ ...c, rank: i + 1 }))

  return {
    id: `scan-${Date.now()}`,
    name: scanner.name,
    type: scanner.type,
    universe: scanner.universe,
    candidates,
    count: candidates.length,
    universeSize: universe.length,
    executedAt: Date.now() - 60_000,
    duration: 1234,
    status: 'COMPLETED',
  }
}

// ───────────────────────────────────────────────────────────────────────────
// Strategies
// ───────────────────────────────────────────────────────────────────────────

export const STRATEGIES: Strategy[] = [
  {
    id: 'strat-1',
    name: 'HalfTrend Intraday',
    type: 'INTRADAY',
    description: 'Volatility-tuned halftrend intraday momentum with ATR stops.',
    entry: {
      conditions: ['HalfTrend direction = Bull', 'RSI > 55', 'Volume > 1.5x avg', 'Time ∈ [9:30, 14:30]'],
      indicators: ['HalfTrend', 'RSI(14)', 'ATR(14)', 'RelativeVolume(20)'],
      logic: 'AND',
      time: { from: '09:30', to: '14:30' },
      signal: 'BUY',
    },
    exit: {
      conditions: ['HalfTrend flips Bear', 'Trail SL hit', 'EOD 15:15'],
      indicators: ['HalfTrend', 'ATR(14)'],
      logic: 'OR',
      time: { from: '15:15', to: '15:15' },
      signal: 'AUTO',
    },
    risk: { stopLoss: 1.5, target: 3.5, trailingSL: true, maxPositions: 5, positionSize: 20, maxDailyLoss: 3, maxDrawdown: 8 },
    universe: 'NIFTY50',
    status: 'LIVE',
    capital: 500_000,
    pnl: { today: 14_545.30, week: 73_140.90, month: 2_45_678.90, total: 2_45_678.90 },
    winRate: 62.35,
    sharpe: 1.85,
    trades: { today: 12, total: 245, winning: 152, losing: 93 },
    createdAt: Date.now() - 1000 * 60 * 60 * 24 * 90,
    updatedAt: Date.now() - 1000 * 60 * 60 * 6,
  },
  {
    id: 'strat-2',
    name: 'VWAP Momentum',
    type: 'INTRADAY',
    description: 'VWAP reclaim with volume confirmation and OI alignment.',
    entry: {
      conditions: ['Close > VWAP', 'RSI > 50', 'Volume > 2x avg', 'Call OI ↑'],
      indicators: ['VWAP', 'RSI(14)', 'RelativeVolume(20)', 'OI Change'],
      logic: 'AND',
      time: { from: '09:45', to: '14:00' },
      signal: 'BUY',
    },
    exit: {
      conditions: ['Close < VWAP', 'Trail SL 1%'],
      indicators: ['VWAP', 'ATR(14)'],
      logic: 'OR',
      signal: 'AUTO',
    },
    risk: { stopLoss: 1.0, target: 2.5, trailingSL: true, maxPositions: 6, positionSize: 15, maxDailyLoss: 2, maxDrawdown: 6 },
    universe: 'NIFTY100',
    status: 'LIVE',
    capital: 400_000,
    pnl: { today: 9_732.50, week: 41_205.30, month: 1_45_678.20, total: 1_45_678.20 },
    winRate: 58.42,
    sharpe: 1.45,
    trades: { today: 8, total: 188, winning: 110, losing: 78 },
    createdAt: Date.now() - 1000 * 60 * 60 * 24 * 60,
    updatedAt: Date.now() - 1000 * 60 * 60 * 4,
  },
  {
    id: 'strat-3',
    name: 'OI Build-up',
    type: 'INTRADAY',
    description: 'Long build-up detection in options with price-volume confirmation.',
    entry: {
      conditions: ['Price ↑ + OI ↑', 'PCR > 1.2', 'IV < 25'],
      indicators: ['Price', 'OI Change', 'PCR', 'IV'],
      logic: 'AND',
      signal: 'BUY',
    },
    exit: {
      conditions: ['Price ↓ + OI ↓', 'EOD'],
      indicators: ['Price', 'OI'],
      logic: 'OR',
      signal: 'AUTO',
    },
    risk: { stopLoss: 1.2, target: 3.0, trailingSL: false, maxPositions: 4, positionSize: 25, maxDailyLoss: 2.5, maxDrawdown: 7 },
    universe: 'NIFTY50',
    status: 'CERTIFIED',
    capital: 350_000,
    pnl: { today: 4_445.20, week: 22_156.10, month: 71_205.50, total: 71_205.50 },
    winRate: 64.20,
    sharpe: 1.95,
    trades: { today: 5, total: 102, winning: 65, losing: 37 },
    createdAt: Date.now() - 1000 * 60 * 60 * 24 * 30,
    updatedAt: Date.now() - 1000 * 60 * 60 * 12,
  },
  {
    id: 'strat-4',
    name: 'Opening Range Breakout',
    type: 'INTRADAY',
    description: '15-minute ORB with volume and OI confirmation.',
    entry: {
      conditions: ['Close > ORH', 'Volume > 3x avg', '15m candle body > 70%'],
      indicators: ['OpeningRange', 'RelativeVolume(20)', 'CandleBody'],
      logic: 'AND',
      time: { from: '09:15', to: '10:00' },
      signal: 'BUY',
    },
    exit: {
      conditions: ['Close < ORL', 'Trail SL 0.8%'],
      indicators: ['OpeningRange', 'ATR(14)'],
      logic: 'OR',
      signal: 'AUTO',
    },
    risk: { stopLoss: 0.8, target: 2.0, trailingSL: true, maxPositions: 3, positionSize: 30, maxDailyLoss: 2, maxDrawdown: 5 },
    universe: 'NIFTY100',
    status: 'TESTING',
    capital: 250_000,
    pnl: { today: 0, week: -3_456.40, month: 8_256.70, total: 8_256.70 },
    winRate: 56.12,
    sharpe: 1.20,
    trades: { today: 0, total: 28, winning: 15, losing: 13 },
    createdAt: Date.now() - 1000 * 60 * 60 * 24 * 14,
    updatedAt: Date.now() - 1000 * 60 * 60 * 24,
  },
]

// ───────────────────────────────────────────────────────────────────────────
// Signals
// ───────────────────────────────────────────────────────────────────────────

export const SIGNALS: Signal[] = [
  { id: 'sig-1', symbol: 'RELIANCE', exchange: 'NSE', signalType: 'STRONG_BUY', confidence: 0.89, strategy: 'HalfTrend Intraday', entryPrice: 2935.4, stopLoss: 2890.0, target: 3020.0, reasons: ['HalfTrend bullish flip', 'RSI 58', 'Vol 2.1x'], metrics: { rsi: 58, volRatio: 2.1 }, timestamp: Date.now() - 1000 * 60 * 3 },
  { id: 'sig-2', symbol: 'SBIN', exchange: 'NSE', signalType: 'BUY', confidence: 0.76, strategy: 'VWAP Momentum', entryPrice: 808.1, stopLoss: 800.0, target: 825.0, reasons: ['VWAP reclaim', 'Vol 1.8x'], metrics: { rsi: 55, volRatio: 1.8 }, timestamp: Date.now() - 1000 * 60 * 5 },
  { id: 'sig-3', symbol: 'TCS', exchange: 'NSE', signalType: 'BUY', confidence: 0.72, strategy: 'HalfTrend Intraday', entryPrice: 3650.0, stopLoss: 3620.0, target: 3720.0, reasons: ['HalfTrend up', 'Trend continuation'], metrics: { rsi: 60 }, timestamp: Date.now() - 1000 * 60 * 7 },
  { id: 'sig-4', symbol: 'HDFCBANK', exchange: 'NSE', signalType: 'BUY', confidence: 0.81, strategy: 'OI Build-up', entryPrice: 1640.0, stopLoss: 1620.0, target: 1680.0, reasons: ['Long build-up', 'PCR 1.4'], metrics: { pcr: 1.4 }, timestamp: Date.now() - 1000 * 60 * 10 },
  { id: 'sig-5', symbol: 'ICICIBANK', exchange: 'NSE', signalType: 'STRONG_BUY', confidence: 0.92, strategy: 'Opening Range Breakout', entryPrice: 1240.0, stopLoss: 1230.0, target: 1265.0, reasons: ['ORH breakout', 'Vol 3.2x'], metrics: { volRatio: 3.2 }, timestamp: Date.now() - 1000 * 60 * 12 },
  { id: 'sig-6', symbol: 'LT', exchange: 'NSE', signalType: 'BUY', confidence: 0.68, strategy: 'VWAP Momentum', entryPrice: 3680.0, stopLoss: 3655.0, target: 3730.0, reasons: ['VWAP support'], metrics: { rsi: 56 }, timestamp: Date.now() - 1000 * 60 * 18 },
  { id: 'sig-7', symbol: 'ITC', exchange: 'NSE', signalType: 'HOLD', confidence: 0.45, strategy: 'HalfTrend Intraday', reasons: ['Sideways zone'], metrics: { rsi: 50 }, timestamp: Date.now() - 1000 * 60 * 22 },
]

// ───────────────────────────────────────────────────────────────────────────
// Option chain
// ───────────────────────────────────────────────────────────────────────────

export function generateOptionChain(underlying = 'NIFTY', spot = 24_900): OptionChain {
  const atm = Math.round(spot / 50) * 50
  const strikes: OptionStrike[] = []
  for (let s = atm - 1000; s <= atm + 1000; s += 50) {
    const moneyness = (s - spot) / spot
    const callIV = 14 + Math.abs(moneyness) * 80
    const putIV = 14 + Math.abs(moneyness) * 80
    const callLTP = Math.max(0.05, spot * 0.005 * Math.exp(-Math.abs(moneyness) * 10) + (s < spot ? spot - s : 0) * 0.4)
    const putLTP = Math.max(0.05, spot * 0.005 * Math.exp(-Math.abs(moneyness) * 10) + (s > spot ? s - spot : 0) * 0.4)
    strikes.push({
      strike: s,
      callOI: Math.floor(randomBetween(50_000, 800_000)),
      callOIChange: Math.floor(randomBetween(-100_000, 200_000)),
      callVolume: Math.floor(randomBetween(10_000, 500_000)),
      callIV: Number(callIV.toFixed(2)),
      callLTP: Number(callLTP.toFixed(2)),
      callChange: Number(randomBetween(-30, 30).toFixed(2)),
      callBid: Number((callLTP - 0.5).toFixed(2)),
      callAsk: Number((callLTP + 0.5).toFixed(2)),
      callDelta: s < spot ? 0.6 + moneyness * 0.4 : 0.3,
      callGamma: 0.003,
      callTheta: -2.1,
      callVega: 4.5,
      putOI: Math.floor(randomBetween(50_000, 900_000)),
      putOIChange: Math.floor(randomBetween(-100_000, 200_000)),
      putVolume: Math.floor(randomBetween(10_000, 500_000)),
      putIV: Number(putIV.toFixed(2)),
      putLTP: Number(putLTP.toFixed(2)),
      putChange: Number(randomBetween(-30, 30).toFixed(2)),
      putBid: Number((putLTP - 0.5).toFixed(2)),
      putAsk: Number((putLTP + 0.5).toFixed(2)),
      putDelta: s < spot ? -0.4 : -0.6 - moneyness * 0.4,
      putGamma: 0.003,
      putTheta: -1.9,
      putVega: 4.3,
    })
  }
  const totalCallOI = strikes.reduce((s, x) => s + x.callOI, 0)
  const totalPutOI = strikes.reduce((s, x) => s + x.putOI, 0)
  const pcr = totalCallOI ? totalPutOI / totalCallOI : 0
  const maxPain = strikes.reduce((max, x) => {
    const callPain = strikes.reduce((s, x2) => s + (x.strike < x2.strike ? x2.callOI * (x2.strike - x.strike) : 0), 0)
    const putPain = strikes.reduce((s, x2) => s + (x.strike > x2.strike ? x2.putOI * (x.strike - x2.strike) : 0), 0)
    const total = callPain + putPain
    return total < max.pain ? { strike: x.strike, pain: total } : max
  }, { strike: atm, pain: Infinity }).strike

  return {
    symbol: underlying,
    underlying,
    expiry: '26-Jun-2025',
    spot,
    atm,
    pcr: Number(pcr.toFixed(2)),
    maxPain,
    totalCallOI,
    totalPutOI,
    iv: 14.2,
    ivChange: 0.32,
    strikes,
    timestamp: Date.now(),
  }
}

// ───────────────────────────────────────────────────────────────────────────
// Market breadth
// ───────────────────────────────────────────────────────────────────────────

export const MARKET_BREADTH: MarketBreadth = {
  advances: 1842,
  declines: 1284,
  unchanged: 162,
  total: 3288,
  advanceDeclineRatio: 1.43,
  newHighs: 184,
  newLows: 67,
  above50DMA: 2102,
  below50DMA: 1186,
  above200DMA: 1854,
  below200DMA: 1434,
  rsRotation: [
    { sector: 'IT', rs: 92, change: 1.8 },
    { sector: 'Bank', rs: 88, change: 0.9 },
    { sector: 'Auto', rs: 76, change: 0.5 },
    { sector: 'Pharma', rs: 71, change: -0.3 },
    { sector: 'FMCG', rs: 65, change: 0.2 },
    { sector: 'Metal', rs: 58, change: -0.7 },
    { sector: 'Energy', rs: 54, change: 0.1 },
    { sector: 'Realty', rs: 48, change: -1.2 },
  ],
}

export const SECTOR_PERFORMANCE: SectorPerformance[] = [
  { sector: 'IT', change: 1245.6, changePct: 1.85, advances: 32, declines: 8, rs: 92, volume: 1_245_000_000, topGainer: 'TCS', topLoser: 'WIPRO' },
  { sector: 'Bank', change: 142.5, changePct: 0.65, advances: 24, declines: 6, rs: 88, volume: 4_125_000_000, topGainer: 'HDFCBANK', topLoser: 'BANKBARODA' },
  { sector: 'Auto', change: 88.4, changePct: 0.42, advances: 18, declines: 10, rs: 76, volume: 845_000_000, topGainer: 'MARUTI', topLoser: 'ASHOKLEY' },
  { sector: 'Pharma', change: -45.8, changePct: -0.28, advances: 12, declines: 18, rs: 71, volume: 425_000_000, topGainer: 'DRREDDY', topLoser: 'CIPLA' },
  { sector: 'FMCG', change: 22.6, changePct: 0.18, advances: 14, declines: 12, rs: 65, volume: 245_000_000, topGainer: 'HINDUNILVR', topLoser: 'BRITANNIA' },
  { sector: 'Metal', change: -88.4, changePct: -0.72, advances: 8, declines: 22, rs: 58, volume: 1_125_000_000, topGainer: 'JSWSTEEL', topLoser: 'TATASTEEL' },
  { sector: 'Energy', change: 12.4, changePct: 0.12, advances: 11, declines: 9, rs: 54, volume: 985_000_000, topGainer: 'RELIANCE', topLoser: 'ONGC' },
  { sector: 'Realty', change: -64.5, changePct: -1.18, advances: 6, declines: 22, rs: 48, volume: 245_000_000, topGainer: 'GODREJPROP', topLoser: 'OBEREALTY' },
]

// ───────────────────────────────────────────────────────────────────────────
// Alerts
// ───────────────────────────────────────────────────────────────────────────

export const ALERTS: Alert[] = [
  { id: 'al-1', symbol: 'RELIANCE', type: 'PRICE', message: 'RELIANCE crossed 2,935 (LTP 2,935.40)', condition: 'LTP > 2,930', priority: 'HIGH', triggeredAt: Date.now() - 1000 * 60 * 3, status: 'ACTIVE' },
  { id: 'al-2', symbol: 'SBIN', type: 'VOLUME', message: 'SBIN volume 4.2x of 20-period avg', condition: 'Vol > 3x AvgVol(20)', priority: 'MEDIUM', triggeredAt: Date.now() - 1000 * 60 * 12, status: 'ACTIVE' },
  { id: 'al-3', symbol: 'NIFTY', type: 'TECHNICAL', message: 'NIFTY 50 broke 24,900 resistance', condition: 'Close > 24,900', priority: 'HIGH', triggeredAt: Date.now() - 1000 * 60 * 8, status: 'ACKNOWLEDGED' },
  { id: 'al-4', symbol: 'TCS', type: 'OI', message: 'TCS 3700 CE OI build-up 124%', condition: 'OI Change > 100%', priority: 'MEDIUM', triggeredAt: Date.now() - 1000 * 60 * 18, status: 'ACTIVE' },
  { id: 'al-5', symbol: 'PORTFOLIO', type: 'RISK', message: 'Daily P&L drawdown approaching -2% limit', condition: 'DailyPnL < -1.8%', priority: 'CRITICAL', triggeredAt: Date.now() - 1000 * 60 * 22, status: 'ACTIVE' },
]

// ───────────────────────────────────────────────────────────────────────────
// Backtests
// ───────────────────────────────────────────────────────────────────────────

function genEquityCurve(days: number, start = 100_000, targetReturn = 0.45, volatility = 0.012): { timestamp: number; equity: number; drawdown: number; benchmark: number }[] {
  const result = []
  let equity = start
  let benchmark = start
  let peak = start
  const dailyReturn = Math.pow(1 + targetReturn, 1 / days) - 1
  const now = Date.now()
  for (let i = 0; i < days; i++) {
    const noise = (Math.random() - 0.5) * volatility * 2
    equity = equity * (1 + dailyReturn + noise)
    benchmark = benchmark * (1 + dailyReturn * 0.8 + noise * 0.7)
    peak = Math.max(peak, equity)
    const drawdown = ((equity - peak) / peak) * 100
    result.push({
      timestamp: now - (days - i) * 86_400_000,
      equity: Number(equity.toFixed(2)),
      benchmark: Number(benchmark.toFixed(2)),
      drawdown: Number(drawdown.toFixed(2)),
    })
  }
  return result
}

export const BACKTESTS: BacktestResult[] = [
  {
    id: 'bt-1',
    name: 'HalfTrend Intraday — NIFTY50',
    config: { symbol: 'NIFTY50', universe: 'NIFTY50', from: '2020-01-01', to: '2024-12-31', timeframe: '5m', capital: 1_000_000, slippage: 0.05, brokerage: 20, strategy: 'HalfTrend Intraday' },
    totalReturn: 245.6,
    cagr: 28.5,
    sharpe: 1.85,
    sortino: 2.45,
    calmar: 2.15,
    maxDrawdown: -8.35,
    winRate: 62.35,
    profitFactor: 1.85,
    trades: { total: 245, winning: 152, losing: 93, avgWin: 4520, avgLoss: -2450 },
    equityCurve: genEquityCurve(252, 1_000_000, 0.85, 0.012),
    tradesList: [],
    status: 'COMPLETED',
    startedAt: Date.now() - 1000 * 60 * 60 * 24 * 2,
    completedAt: Date.now() - 1000 * 60 * 60 * 24 * 2 + 1000 * 60 * 18,
  },
  {
    id: 'bt-2',
    name: 'VWAP Momentum — NIFTY100',
    config: { symbol: 'NIFTY100', universe: 'NIFTY100', from: '2021-01-01', to: '2024-12-31', timeframe: '5m', capital: 1_000_000, slippage: 0.05, brokerage: 20, strategy: 'VWAP Momentum' },
    totalReturn: 145.6,
    cagr: 22.1,
    sharpe: 1.45,
    sortino: 1.95,
    calmar: 1.65,
    maxDrawdown: -6.20,
    winRate: 58.42,
    profitFactor: 1.55,
    trades: { total: 188, winning: 110, losing: 78, avgWin: 3850, avgLoss: -2150 },
    equityCurve: genEquityCurve(252, 1_000_000, 0.55, 0.011),
    tradesList: [],
    status: 'COMPLETED',
    startedAt: Date.now() - 1000 * 60 * 60 * 24 * 5,
    completedAt: Date.now() - 1000 * 60 * 60 * 24 * 5 + 1000 * 60 * 24,
  },
  {
    id: 'bt-3',
    name: 'OI Build-up — NIFTY50',
    config: { symbol: 'NIFTY50', universe: 'NIFTY50', from: '2022-01-01', to: '2024-12-31', timeframe: '15m', capital: 1_000_000, slippage: 0.05, brokerage: 20, strategy: 'OI Build-up' },
    totalReturn: 71.2,
    cagr: 18.5,
    sharpe: 1.95,
    sortino: 2.65,
    calmar: 2.05,
    maxDrawdown: -4.85,
    winRate: 64.20,
    profitFactor: 1.95,
    trades: { total: 102, winning: 65, losing: 37, avgWin: 5250, avgLoss: -2540 },
    equityCurve: genEquityCurve(252, 1_000_000, 0.32, 0.010),
    tradesList: [],
    status: 'COMPLETED',
    startedAt: Date.now() - 1000 * 60 * 60 * 24 * 10,
    completedAt: Date.now() - 1000 * 60 * 60 * 24 * 10 + 1000 * 60 * 30,
  },
]

// ───────────────────────────────────────────────────────────────────────────
// Indicators (technical snapshot)
// ───────────────────────────────────────────────────────────────────────────

export const INDICATORS: Indicator[] = [
  { name: 'RSI(14)', value: 58.2, signal: 'BULLISH', description: 'Above midline' },
  { name: 'MACD', value: 12.5, signal: 'BULLISH', description: 'Bullish crossover' },
  { name: 'ADX(14)', value: 28.4, signal: 'BULLISH', description: 'Strong trend' },
  { name: 'Stoch RSI', value: 76.8, signal: 'BULLISH', description: 'Overbought zone' },
  { name: 'Bollinger %B', value: 0.78, signal: 'BULLISH', description: 'Upper band test' },
  { name: 'ATR(14)', value: 28.5, signal: 'NEUTRAL', description: 'Volatility normal' },
  { name: 'VWAP Dev.', value: 0.42, signal: 'BULLISH', description: 'Above VWAP' },
  { name: 'SuperTrend', value: 1, signal: 'BULLISH', description: 'Bullish flip' },
]

// ───────────────────────────────────────────────────────────────────────────
// Market Indices
// ───────────────────────────────────────────────────────────────────────────

export const INDICES = [
  { symbol: 'NIFTY 50', ltp: 24_906.45, change: 51.20, changePct: 0.21, prevClose: 24_855.25, open: 24_870.10, high: 24_950.40, low: 24_810.20 },
  { symbol: 'BANK NIFTY', ltp: 53_256.80, change: -185.40, changePct: -0.35, prevClose: 53_442.20, open: 53_400.50, high: 53_480.10, low: 53_120.40 },
  { symbol: 'NIFTY IT', ltp: 41_285.20, change: 752.45, changePct: 1.85, prevClose: 40_532.75, open: 40_650.40, high: 41_320.80, low: 40_580.20 },
  { symbol: 'FIN NIFTY', ltp: 25_485.60, change: 124.80, changePct: 0.49, prevClose: 25_360.80, open: 25_400.10, high: 25_510.20, low: 25_320.50 },
  { symbol: 'SENSEX', ltp: 81_754.20, change: 152.40, changePct: 0.19, prevClose: 81_601.80, open: 81_650.40, high: 81_820.10, low: 81_540.80 },
  { symbol: 'INDIA VIX', ltp: 14.85, change: -0.42, changePct: -2.75, prevClose: 15.27, open: 15.10, high: 15.32, low: 14.65 },
]
