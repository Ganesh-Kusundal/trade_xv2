/**
 * Widget Registry — registers all built-in widgets and exports the singleton.
 * Adding a new widget? Just add an import + register call here.
 */

import { widgetRegistry } from '../registry'
import type { WidgetManifest } from '../Widget'
import {
  LineChart, BarChart3, Activity, Telescope, Brain, GitBranch,
  PieChart, Target, Shield, AlertTriangle, Layers, Briefcase, Play,
  History, FileText, BarChart2, Flame, Snowflake, ScanLine, ClipboardList,
  Gauge, Wallet, ListChecks, Crosshair, Sigma, Magnet, BookOpen, Filter, Zap,
} from 'lucide-react'

// Import widget components
import WatchlistWidget from './watchlist/WatchlistWidget'
import ChartWidget from './chart/ChartWidget'
import ScanResultsWidget from './scan-results/ScanResultsWidget'
import PnLSummaryWidget from './pnl-summary/PnLSummaryWidget'
import PositionsWidget from './positions/PositionsWidget'
import OrdersWidget from './orders/OrdersWidget'
import RiskGaugeWidget from './risk-gauge/RiskGaugeWidget'
import EquityCurveWidget from './equity-curve/EquityCurveWidget'
import PCRGaugeWidget from './pcr-gauge/PCRGaugeWidget'
import StrategyListWidget from './strategy-list/StrategyListWidget'
import AlertsFeedWidget from './alerts-feed/AlertsFeedWidget'
import BreadthWidget from './breadth/BreadthWidget'
import QuickOrderWidget from './quick-order/QuickOrderWidget'
import MarketDepthWidget from './market-depth/MarketDepthWidget'
import IndexStripWidget from './index-strip/IndexStripWidget'
import MoversWidget from './movers/MoversWidget'
import ReplayPlayerWidget from './replay-player/ReplayPlayerWidget'
import RSHeatmapWidget from './relative-strength/RSHeatmapWidget'
import SignalFeedWidget from './signals/SignalFeedWidget'
import OptionChainWidget from './option-chain/OptionChainWidget'
import HoldingsWidget from './holdings/HoldingsWidget'

// DeepCharts-style orderflow widgets
import FootprintWidget from './footprint/FootprintWidget'
import DeepDOMWidget from './deepdom/DeepDOMWidget'
import IcebergWidget from './iceberg/IcebergWidget'
import VolumeProfileWidget from './volume-profile/VolumeProfileWidget'
import DeepPrintWidget from './deepprint/DeepPrintWidget'
import TPOProfileWidget from './tpo-profile/TPOProfileWidget'
import InitialBalanceWidget from './initial-balance/InitialBalanceWidget'
import BuysideSqueezeWidget from './buyside-squeeze/BuysideSqueezeWidget'
import DOMHeatmapWidget from './dom-heatmap/DOMHeatmapWidget'

// AMT Scalper System canvas widgets
import AMTDeepChartWidget from './amt-deep-chart/AMTDeepChartWidget'
import AMTVolumeProfileWidget from './amt-volume-profile/AMTVolumeProfileWidget'
import AMTDeepDOMWidget from './amt-deep-dom/AMTDeepDOMWidget'

// Symbol universe used for default watchlists
const DEFAULT_WATCHLIST = ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 'SBIN', 'ITC', 'LT', 'AXISBANK', 'BHARTIARTL', 'TATAMOTORS', 'MARUTI']

// ─── Manifests ────────────────────────────────────────────────────────────

const manifests: WidgetManifest[] = [
  // Market
  {
    type: 'watchlist',
    name: 'Watchlist',
    description: 'Live watchlist with LTP and day change for tracked symbols.',
    category: 'market',
    icon: ListChecks,
    defaultSize: { w: 3, h: 6, minW: 2, minH: 4 },
    component: WatchlistWidget,
    defaultConfig: () => ({ symbols: DEFAULT_WATCHLIST, title: 'Watchlist' }),
    configSchema: [
      { key: 'title', label: 'Title', type: 'text' },
    ],
  },
  {
    type: 'index-strip',
    name: 'Index Strip',
    description: 'NIFTY 50, BANK NIFTY, NIFTY IT, INDIA VIX and more.',
    category: 'market',
    icon: BarChart3,
    defaultSize: { w: 6, h: 2, minW: 3, minH: 2 },
    component: IndexStripWidget,
    defaultConfig: () => ({ title: 'Market Indices' }),
  },
  {
    type: 'market-depth',
    name: 'Market Depth',
    description: '5-level bid/ask depth for the active symbol.',
    category: 'market',
    icon: Layers,
    defaultSize: { w: 3, h: 5, minW: 2, minH: 4 },
    component: MarketDepthWidget,
    defaultConfig: () => ({ symbol: 'RELIANCE', levels: 5 }),
  },
  {
    type: 'movers',
    name: 'Top Movers',
    description: 'Top gainers and losers from your positions.',
    category: 'market',
    icon: Flame,
    defaultSize: { w: 4, h: 5, minW: 3, minH: 4 },
    component: MoversWidget,
    defaultConfig: () => ({ direction: 'both', count: 5 }),
  },

  // Charts
  {
    type: 'chart',
    name: 'Candlestick Chart',
    description: 'High-performance candlestick chart with EMA/SMA/BB overlays.',
    category: 'chart',
    icon: LineChart,
    defaultSize: { w: 6, h: 8, minW: 3, minH: 5 },
    component: ChartWidget,
    defaultConfig: () => ({ symbol: 'RELIANCE', timeframe: '5m', showIndicators: true, title: 'Chart' }),
  },

  // Scanner
  {
    type: 'scan-results',
    name: 'Scan Results',
    description: 'Live scanner results with scores, RSI, ROC and reasons.',
    category: 'scanner',
    icon: ScanLine,
    defaultSize: { w: 5, h: 7, minW: 3, minH: 5 },
    component: ScanResultsWidget,
    defaultConfig: () => ({ scannerId: 'sc-1', topN: 30, title: 'RS Momentum' }),
  },

  // Analytics
  {
    type: 'breadth',
    name: 'Market Breadth',
    description: 'Advances vs declines, new highs/lows, % above 50/200 DMA.',
    category: 'analytics',
    icon: BarChart2,
    defaultSize: { w: 3, h: 5, minW: 2, minH: 4 },
    component: BreadthWidget,
    defaultConfig: () => ({ title: 'Market Breadth' }),
  },
  {
    type: 'rs-heatmap',
    name: 'RS Heatmap',
    description: 'Relative-strength heatmap of your positions.',
    category: 'analytics',
    icon: Activity,
    defaultSize: { w: 4, h: 4, minW: 3, minH: 3 },
    component: RSHeatmapWidget,
    defaultConfig: () => ({ title: 'RS Heatmap' }),
  },
  {
    type: 'pcr-gauge',
    name: 'PCR Gauge',
    description: 'Put-Call ratio, max pain, total OI, ATM IV.',
    category: 'analytics',
    icon: Gauge,
    defaultSize: { w: 3, h: 4, minW: 2, minH: 3 },
    component: PCRGaugeWidget,
    defaultConfig: () => ({ title: 'PCR' }),
  },

  // Options
  {
    type: 'option-chain',
    name: 'Option Chain',
    description: 'Live option chain with OI, IV, Greeks, LTP.',
    category: 'options',
    icon: Sigma,
    defaultSize: { w: 6, h: 8, minW: 4, minH: 5 },
    component: OptionChainWidget,
    defaultConfig: () => ({ underlying: 'NIFTY', title: 'NIFTY Option Chain' }),
  },

  // Strategy
  {
    type: 'strategy-list',
    name: 'Strategy List',
    description: 'Active strategies with P&L, win rate, and status.',
    category: 'strategy',
    icon: Brain,
    defaultSize: { w: 4, h: 5, minW: 3, minH: 4 },
    component: StrategyListWidget,
    defaultConfig: () => ({ title: 'Strategies' }),
  },
  {
    type: 'signal-feed',
    name: 'Signal Feed',
    description: 'Live buy/sell signals from all active strategies.',
    category: 'strategy',
    icon: Crosshair,
    defaultSize: { w: 4, h: 5, minW: 3, minH: 4 },
    component: SignalFeedWidget,
    defaultConfig: () => ({ count: 10, title: 'Live Signals' }),
  },
  {
    type: 'equity-curve',
    name: 'Equity Curve',
    description: 'Cumulative equity curve with benchmark comparison.',
    category: 'strategy',
    icon: LineChart,
    defaultSize: { w: 6, h: 5, minW: 4, minH: 3 },
    component: EquityCurveWidget,
    defaultConfig: () => ({ days: 252, title: 'Equity Curve' }),
  },

  // Replay
  {
    type: 'replay-player',
    name: 'Replay Player',
    description: 'Historical playback with speed control and timeline.',
    category: 'replay',
    icon: Play,
    defaultSize: { w: 4, h: 4, minW: 3, minH: 3 },
    component: ReplayPlayerWidget,
    defaultConfig: () => ({ symbol: 'RELIANCE', date: '2024-12-30' }),
  },

  // Portfolio
  {
    type: 'pnl-summary',
    name: 'P&L Summary',
    description: 'Total value, today P&L, week, month, total.',
    category: 'portfolio',
    icon: Wallet,
    defaultSize: { w: 3, h: 3, minW: 2, minH: 3 },
    component: PnLSummaryWidget,
    defaultConfig: () => ({ title: 'P&L' }),
  },
  {
    type: 'positions',
    name: 'Positions',
    description: 'Live open positions with LTP, P&L, and trend sparkline.',
    category: 'portfolio',
    icon: Briefcase,
    defaultSize: { w: 5, h: 6, minW: 4, minH: 4 },
    component: PositionsWidget,
    defaultConfig: () => ({ compact: false, title: 'Positions' }),
  },
  {
    type: 'holdings',
    name: 'Holdings',
    description: 'Long-term CNC holdings with P&L and search.',
    category: 'portfolio',
    icon: ClipboardList,
    defaultSize: { w: 5, h: 5, minW: 4, minH: 4 },
    component: HoldingsWidget,
    defaultConfig: () => ({ title: 'Holdings' }),
  },
  {
    type: 'orders',
    name: 'Orders',
    description: 'Open orders with cancel/modify actions.',
    category: 'portfolio',
    icon: FileText,
    defaultSize: { w: 4, h: 5, minW: 3, minH: 4 },
    component: OrdersWidget,
    defaultConfig: () => ({ status: 'OPEN', title: 'Open Orders' }),
  },
  {
    type: 'quick-order',
    name: 'Quick Order',
    description: 'Fast bracket order ticket with SL and target.',
    category: 'portfolio',
    icon: Target,
    defaultSize: { w: 3, h: 7, minW: 2, minH: 5 },
    component: QuickOrderWidget,
    defaultConfig: () => ({ defaultSymbol: 'RELIANCE' }),
  },

  // Risk
  {
    type: 'risk-gauge',
    name: 'Risk Gauge',
    description: 'VaR, Sharpe, exposure, margin utilization.',
    category: 'risk',
    icon: Shield,
    defaultSize: { w: 3, h: 4, minW: 2, minH: 3 },
    component: RiskGaugeWidget,
    defaultConfig: () => ({ title: 'Risk' }),
  },

  // Orderflow (DeepCharts-style)
  {
    type: 'footprint',
    name: 'Footprint Chart',
    description: 'Price-ladder footprint with bid/ask volume + delta per level, POC/HVN/LVN markers, and iceberg detection.',
    category: 'analytics',
    icon: BookOpen,
    defaultSize: { w: 8, h: 7, minW: 5, minH: 5 },
    component: FootprintWidget,
    defaultConfig: () => ({ symbol: 'NIFTY', bars: 24, levelsPerBar: 12, showIcebergs: true, showDeltaSummary: true, title: 'Footprint' }),
  },
  {
    type: 'deepdom',
    name: 'DeepDOM',
    description: 'Multi-level order book with iceberg detection, imbalance ratio, and aggressive hit visualisation.',
    category: 'analytics',
    icon: Layers,
    defaultSize: { w: 4, h: 8, minW: 3, minH: 5 },
    component: DeepDOMWidget,
    defaultConfig: () => ({ symbol: 'NIFTY', levels: 20, showHeatmap: true, showIcebergs: true, title: 'DeepDOM' }),
  },
  {
    type: 'iceberg',
    name: 'Iceberg Detector',
    description: 'Detects potential iceberg orders (visible + repeated refills) with confidence score.',
    category: 'analytics',
    icon: Snowflake,
    defaultSize: { w: 5, h: 6, minW: 4, minH: 5 },
    component: IcebergWidget,
    defaultConfig: () => ({ symbol: 'NIFTY', levels: 30, minSize: 5000, title: 'Icebergs' }),
  },
  {
    type: 'volume-profile',
    name: 'Volume Profile',
    description: 'Horizontal volume profile with POC, HVN, LVN and 70% Value Area.',
    category: 'analytics',
    icon: BarChart2,
    defaultSize: { w: 4, h: 8, minW: 3, minH: 5 },
    component: VolumeProfileWidget,
    defaultConfig: () => ({ symbol: 'NIFTY', levels: 30, side: 'right', title: 'Volume Profile' }),
  },
  {
    type: 'deepprint',
    name: 'Deep Print',
    description: 'Time & Sales tape with buy/sell side colouring, sweep/block flags, and cumulative delta.',
    category: 'analytics',
    icon: Filter,
    defaultSize: { w: 4, h: 7, minW: 3, minH: 5 },
    component: DeepPrintWidget,
    defaultConfig: () => ({ symbol: 'NIFTY', count: 80, minSize: 0, title: 'Deep Print' }),
  },
  {
    type: 'tpo-profile',
    name: 'TPO Profile',
    description: 'Market Profile (TPO) with letter-per-period stack, single prints, and poor high/low detection.',
    category: 'analytics',
    icon: BarChart3,
    defaultSize: { w: 5, h: 8, minW: 4, minH: 5 },
    component: TPOProfileWidget,
    defaultConfig: () => ({ symbol: 'NIFTY', levels: 24, periods: 13, title: 'TPO Profile' }),
  },
  {
    type: 'initial-balance',
    name: 'Initial Balance',
    description: 'IB High/Low/Mid with 1x/2x/3x extensions, VAH/VAL, and session progress.',
    category: 'analytics',
    icon: Target,
    defaultSize: { w: 4, h: 6, minW: 3, minH: 4 },
    component: InitialBalanceWidget,
    defaultConfig: () => ({ symbol: 'NIFTY', ibMinutes: 30, title: 'Initial Balance' }),
  },
  {
    type: 'buyside-squeeze',
    name: 'Buyside Squeeze',
    description: 'Aggressive buy-side bubbles sized by lift volume — visualises buy pressure clusters.',
    category: 'analytics',
    icon: Zap,
    defaultSize: { w: 5, h: 6, minW: 4, minH: 5 },
    component: BuysideSqueezeWidget,
    defaultConfig: () => ({ symbol: 'NIFTY', count: 50, title: 'Buyside Squeeze' }),
  },
  {
    type: 'dom-heatmap',
    name: 'DOM Heatmap',
    description: 'Orderbook heatmap with magnets, reliable-test, low-slippage, and stable-cluster markers.',
    category: 'analytics',
    icon: Magnet,
    defaultSize: { w: 4, h: 8, minW: 3, minH: 5 },
    component: DOMHeatmapWidget,
    defaultConfig: () => ({ symbol: 'NIFTY', levels: 20, title: 'DOM Heatmap' }),
  },

  // AMT Scalper System canvas widgets
  {
    type: 'amt-deep-chart',
    name: 'AMT Deep Chart',
    description: 'Canvas-rendered candlesticks with VWAP/POC/PVG/IB/LIQ indicators, delta histogram, and cyan-on-black AMT styling.',
    category: 'chart',
    icon: BookOpen,
    defaultSize: { w: 7, h: 8, minW: 4, minH: 5 },
    component: AMTDeepChartWidget,
    defaultConfig: () => ({ symbol: 'XAUUSDm', timeframe: 'M1', showIndicators: true, showVolume: true, title: 'AMT Deep Chart' }),
  },
  {
    type: 'amt-volume-profile',
    name: 'AMT Volume Profile',
    description: 'Canvas-rendered horizontal volume profile in AMT cyan-on-black style with POC/VAH/VAL lines.',
    category: 'analytics',
    icon: BarChart3,
    defaultSize: { w: 2, h: 8, minW: 2, minH: 5 },
    component: AMTVolumeProfileWidget,
    defaultConfig: () => ({ symbol: 'XAUUSDm', title: 'AMT Volume Profile' }),
  },
  {
    type: 'amt-deep-dom',
    name: 'AMT Deep DOM',
    description: 'Canvas-rendered multi-level bid/ask DOM with green/red gradient bars and spread annotation.',
    category: 'market',
    icon: Layers,
    defaultSize: { w: 3, h: 8, minW: 2, minH: 5 },
    component: AMTDeepDOMWidget,
    defaultConfig: () => ({ symbol: 'XAUUSDm', levels: 16, title: 'AMT Deep DOM' }),
  },

  // Alerts
  {
    type: 'alerts-feed',
    name: 'Alerts Feed',
    description: 'Real-time alert feed with priority filters.',
    category: 'alerts',
    icon: AlertTriangle,
    defaultSize: { w: 4, h: 6, minW: 3, minH: 4 },
    component: AlertsFeedWidget,
    defaultConfig: () => ({ maxItems: 20, title: 'Alerts' }),
  },
]

// Register all
for (const m of manifests) {
  widgetRegistry.register(m)
}

export { widgetRegistry }
