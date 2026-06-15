/**
 * Trading domain types — mirrors the canonical Python models in:
 *   - brokers/common/core/domain.py (Order, Position, Holding, etc.)
 *   - analytics/strategy/models.py (Signal, SignalType)
 *   - analytics/scanner/models.py (Candidate, ScanResult)
 */

export type Side = 'BUY' | 'SELL'
export type Exchange = 'NSE' | 'BSE' | 'NFO' | 'MCX' | 'CDS'
export type ProductType = 'CNC' | 'MIS' | 'NRML'
export type OrderType = 'MARKET' | 'LIMIT' | 'STOP_LOSS' | 'STOP_LOSS_MARKET' | 'BRACKET' | 'COVER'
export type OrderStatus = 'OPEN' | 'PARTIALLY_FILLED' | 'FILLED' | 'CANCELLED' | 'REJECTED' | 'EXPIRED'
export type SignalType = 'STRONG_BUY' | 'BUY' | 'HOLD' | 'SELL' | 'STRONG_SELL'
export type OptionType = 'CE' | 'PE'
export type Timeframe = '1m' | '3m' | '5m' | '15m' | '30m' | '1h' | '4h' | '1d' | '1w'
export type ScanType = 'MOMENTUM' | 'BREAKOUT' | 'REVERSAL' | 'VOLUME' | 'OI_BUILDER' | 'VWAP' | 'RS' | 'CUSTOM'
export type Universe = 'NIFTY50' | 'NIFTY100' | 'NIFTY200' | 'NIFTY500' | 'BANKNIFTY' | 'FINNIFTY' | 'CUSTOM'

export interface Symbol {
  symbol: string
  name: string
  exchange: Exchange
  sector: string
  industry: string
  isin: string
  lotSize: number
  tickSize: number
}

export interface Quote {
  symbol: string
  exchange: Exchange
  ltp: number
  change: number
  changePct: number
  open: number
  high: number
  low: number
  prevClose: number
  volume: number
  value: number          /* turnover */
  vwap: number
  bid: number
  ask: number
  bidQty: number
  askQty: number
  oi: number
  oiChange: number
  timestamp: number
}

export interface Candle {
  timestamp: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  oi?: number
  vwap?: number
}

export interface Order {
  orderId: string
  symbol: string
  exchange: Exchange
  side: Side
  quantity: number
  filledQty: number
  avgPrice: number
  price: number
  triggerPrice: number
  orderType: OrderType
  product: ProductType
  status: OrderStatus
  strategy?: string
  placedAt: number
  updatedAt: number
  tag?: string
}

export interface Position {
  symbol: string
  exchange: Exchange
  side: Side
  quantity: number
  avgPrice: number
  ltp: number
  pnl: number
  pnlPct: number
  product: ProductType
  dayChange: number
  dayChangePct: number
}

export interface Holding {
  symbol: string
  exchange: Exchange
  quantity: number
  avgPrice: number
  ltp: number
  pnl: number
  pnlPct: number
  dayChange: number
  dayChangePct: number
}

export interface Signal {
  id: string
  symbol: string
  exchange: Exchange
  signalType: SignalType
  confidence: number
  strategy: string
  entryPrice?: number
  stopLoss?: number
  target?: number
  reasons: string[]
  metrics: Record<string, number>
  timestamp: number
}

export interface Candidate {
  symbol: string
  score: number
  reasons: string[]
  metrics: Record<string, number>
  rank?: number
  prevRank?: number
}

export interface ScanResult {
  id: string
  name: string
  type: ScanType
  universe: Universe
  candidates: Candidate[]
  count: number
  universeSize: number
  executedAt: number
  duration: number          /* ms */
  status: 'RUNNING' | 'COMPLETED' | 'FAILED' | 'QUEUED'
}

export interface Scanner {
  id: string
  name: string
  type: ScanType
  universe: Universe
  filters: ScanFilter[]
  schedule?: string
  enabled: boolean
  lastRun?: number
  resultCount: number
}

export interface ScanFilter {
  field: string
  op: '>' | '<' | '>=' | '<=' | '==' | '!=' | 'IN' | 'NOT_IN' | 'BETWEEN'
  value: number | string | number[] | string[]
}

export interface Strategy {
  id: string
  name: string
  type: 'INTRADAY' | 'SWING' | 'POSITIONAL' | 'OPTIONS'
  description: string
  entry: StrategyBlock
  exit: StrategyBlock
  risk: RiskConfig
  universe: Universe
  status: 'DRAFT' | 'TESTING' | 'CERTIFIED' | 'LIVE' | 'PAUSED'
  capital: number
  pnl: { today: number; week: number; month: number; total: number }
  winRate: number
  sharpe: number
  trades: { today: number; total: number; winning: number; losing: number }
  createdAt: number
  updatedAt: number
}

export interface StrategyBlock {
  conditions: string[]    /* human-readable conditions */
  indicators: string[]
  logic: 'AND' | 'OR'
  time?: { from: string; to: string }
  signal: 'BUY' | 'SELL' | 'AUTO'
}

export interface RiskConfig {
  stopLoss: number         /* % */
  target: number           /* % */
  trailingSL: boolean
  maxPositions: number
  positionSize: number     /* % of capital */
  maxDailyLoss: number     /* % */
  maxDrawdown: number      /* % */
}

export interface BacktestConfig {
  symbol: string
  universe?: Universe
  from: string
  to: string
  timeframe: Timeframe
  capital: number
  slippage: number
  brokerage: number
  strategy: string
}

export interface BacktestResult {
  id: string
  name: string
  config: BacktestConfig
  totalReturn: number
  cagr: number
  sharpe: number
  sortino: number
  calmar: number
  maxDrawdown: number
  winRate: number
  profitFactor: number
  trades: {
    total: number
    winning: number
    losing: number
    avgWin: number
    avgLoss: number
  }
  equityCurve: { timestamp: number; equity: number; drawdown: number; benchmark: number }[]
  tradesList: BacktestTrade[]
  status: 'RUNNING' | 'COMPLETED' | 'FAILED' | 'QUEUED'
  startedAt: number
  completedAt?: number
}

export interface BacktestTrade {
  id: string
  symbol: string
  side: Side
  qty: number
  entry: number
  exit: number
  pnl: number
  pnlPct: number
  entryTime: number
  exitTime: number
  duration: number    /* minutes */
  reason: string
}

export interface OptionChain {
  symbol: string
  underlying: string
  expiry: string
  spot: number
  atm: number
  pcr: number
  maxPain: number
  totalCallOI: number
  totalPutOI: number
  iv: number
  ivChange: number
  strikes: OptionStrike[]
  timestamp: number
}

export interface OptionStrike {
  strike: number
  callOI: number
  callOIChange: number
  callVolume: number
  callIV: number
  callLTP: number
  callChange: number
  callBid: number
  callAsk: number
  callDelta: number
  callGamma: number
  callTheta: number
  callVega: number
  putOI: number
  putOIChange: number
  putVolume: number
  putIV: number
  putLTP: number
  putChange: number
  putBid: number
  putAsk: number
  putDelta: number
  putGamma: number
  putTheta: number
  putVega: number
}

export interface Portfolio {
  totalValue: number
  investedValue: number
  availableCash: number
  marginUsed: number
  totalPnl: number
  totalPnlPct: number
  todayPnl: number
  todayPnlPct: number
  weekPnl: number
  monthPnl: number
  unrealizedPnl: number
  realizedPnl: number
  positionsCount: number
  openOrdersCount: number
  buyingPower: number
}

export interface RiskMetrics {
  portfolioVar: number
  expectedShortfall: number
  maxDrawdown: number
  currentDrawdown: number
  beta: number
  alpha: number
  sharpe: number
  sortino: number
  exposure: {
    long: number
    short: number
    net: number
    gross: number
  }
  concentration: {
    topPosition: number
    top5: number
    top10: number
    sectorMax: number
  }
  margin: {
    used: number
    available: number
    utilization: number
  }
}

export interface MarketBreadth {
  advances: number
  declines: number
  unchanged: number
  total: number
  advanceDeclineRatio: number
  newHighs: number
  newLows: number
  above50DMA: number
  below50DMA: number
  above200DMA: number
  below200DMA: number
  rsRotation: { sector: string; rs: number; change: number }[]
}

export interface Alert {
  id: string
  symbol: string
  type: 'PRICE' | 'VOLUME' | 'OI' | 'TECHNICAL' | 'NEWS' | 'RISK'
  message: string
  condition: string
  priority: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
  triggeredAt: number
  status: 'ACTIVE' | 'ACKNOWLEDGED' | 'DISMISSED'
}

export interface SectorPerformance {
  sector: string
  change: number
  changePct: number
  advances: number
  declines: number
  rs: number
  volume: number
  topGainer: string
  topLoser: string
}

export interface Indicator {
  name: string
  value: number
  signal: 'BULLISH' | 'BEARISH' | 'NEUTRAL'
  description?: string
}
