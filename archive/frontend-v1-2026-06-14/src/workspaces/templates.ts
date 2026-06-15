/**
 * Workspace Templates — predefined widget layouts.
 *
 * A workspace is a named collection of widget instances. Built-in templates
 * are read-only (builtIn: true) but can be duplicated to create a user
 * workspace the user can fully customize.
 */

import type { Workspace } from '@/widgets/Widget'
import { widgetRegistry } from '@/widgets/registry'
import '@/widgets/library' // ensure widgets are registered

const DEFAULT_WATCHLIST = ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 'SBIN', 'ITC', 'LT', 'AXISBANK', 'BHARTIARTL']

function inst(type: string, layout: { x: number; y: number; w?: number; h?: number }, configOverride?: any): any {
  const m = widgetRegistry.get(type)
  if (!m) throw new Error(`Unknown widget type: ${type}`)
  return {
    id: `w-${type}-${Math.random().toString(36).slice(2, 8)}`,
    type,
    config: { ...m.defaultConfig(), ...(configOverride || {}) },
    layout: {
      x: layout.x,
      y: layout.y,
      w: layout.w ?? m.defaultSize.w,
      h: layout.h ?? m.defaultSize.h,
    },
  }
}

// 12-column grid system
export const WORKSPACE_TEMPLATES: Workspace[] = [
  // 1. Default Workspace — overall market overview
  {
    id: 'tpl-default',
    name: 'Default Workspace',
    builtIn: true,
    createdAt: Date.now(),
    updatedAt: Date.now(),
    widgets: [
      inst('pnl-summary', { x: 0, y: 0, w: 3, h: 3 }),
      inst('index-strip', { x: 3, y: 0, w: 6, h: 2 }),
      inst('risk-gauge', { x: 9, y: 0, w: 3, h: 3 }),
      inst('watchlist', { x: 0, y: 2, w: 3, h: 7 }),
      inst('chart', { x: 3, y: 2, w: 6, h: 7 }),
      inst('movers', { x: 9, y: 3, w: 3, h: 6 }),
      inst('scan-results', { x: 0, y: 9, w: 6, h: 6 }),
      inst('breadth', { x: 6, y: 9, w: 3, h: 4 }),
      inst('signal-feed', { x: 9, y: 9, w: 3, h: 6 }),
      inst('equity-curve', { x: 6, y: 13, w: 6, h: 4 }),
    ],
  },

  // 2. Live Trading Workspace — order entry focus
  {
    id: 'tpl-live-trading',
    name: 'Live Trading',
    builtIn: true,
    createdAt: Date.now(),
    updatedAt: Date.now(),
    widgets: [
      inst('quick-order', { x: 0, y: 0, w: 3, h: 8 }),
      inst('chart', { x: 3, y: 0, w: 6, h: 8 }),
      inst('watchlist', { x: 9, y: 0, w: 3, h: 8 }),
      inst('positions', { x: 0, y: 8, w: 6, h: 5 }),
      inst('orders', { x: 6, y: 8, w: 3, h: 5 }),
      inst('pnl-summary', { x: 9, y: 8, w: 3, h: 3 }),
      inst('risk-gauge', { x: 9, y: 11, w: 3, h: 4 }),
    ],
  },

  // 3. Research Workspace — multi-chart analysis
  {
    id: 'tpl-research',
    name: 'Research',
    builtIn: true,
    createdAt: Date.now(),
    updatedAt: Date.now(),
    widgets: [
      inst('chart', { x: 0, y: 0, w: 8, h: 8 }),
      inst('quick-order', { x: 8, y: 0, w: 2, h: 7 }),
      inst('market-depth', { x: 10, y: 0, w: 2, h: 5 }),
      inst('watchlist', { x: 8, y: 7, w: 4, h: 5 }),
      inst('movers', { x: 0, y: 8, w: 4, h: 5 }),
      inst('breadth', { x: 4, y: 8, w: 4, h: 5 }),
      inst('signal-feed', { x: 8, y: 12, w: 4, h: 5 }),
      inst('equity-curve', { x: 0, y: 13, w: 8, h: 4 }),
    ],
  },

  // 4. Scanner Workspace — opportunity discovery
  {
    id: 'tpl-scanner',
    name: 'Scanner',
    builtIn: true,
    createdAt: Date.now(),
    updatedAt: Date.now(),
    widgets: [
      inst('scan-results', { x: 0, y: 0, w: 6, h: 9 }),
      inst('chart', { x: 6, y: 0, w: 6, h: 6 }),
      inst('rs-heatmap', { x: 0, y: 9, w: 4, h: 4 }),
      inst('breadth', { x: 4, y: 9, w: 4, h: 4 }),
      inst('watchlist', { x: 8, y: 9, w: 4, h: 4 }),
      inst('signal-feed', { x: 0, y: 13, w: 6, h: 4 }),
      inst('pnl-summary', { x: 6, y: 13, w: 3, h: 4 }),
      inst('risk-gauge', { x: 9, y: 13, w: 3, h: 4 }),
    ],
  },

  // 5. Options Workspace — option chain focus
  {
    id: 'tpl-options',
    name: 'Options',
    builtIn: true,
    createdAt: Date.now(),
    updatedAt: Date.now(),
    widgets: [
      inst('option-chain', { x: 0, y: 0, w: 7, h: 10 }),
      inst('pcr-gauge', { x: 7, y: 0, w: 3, h: 5 }),
      inst('chart', { x: 10, y: 0, w: 2, h: 8 }),
      inst('index-strip', { x: 7, y: 5, w: 3, h: 2 }),
      inst('movers', { x: 7, y: 7, w: 5, h: 3 }),
      inst('signal-feed', { x: 0, y: 10, w: 6, h: 4 }),
      inst('pnl-summary', { x: 6, y: 10, w: 3, h: 4 }),
      inst('positions', { x: 9, y: 10, w: 3, h: 4 }),
    ],
  },

  // 6. Replay Workspace — historical playback
  {
    id: 'tpl-replay',
    name: 'Replay',
    builtIn: true,
    createdAt: Date.now(),
    updatedAt: Date.now(),
    widgets: [
      inst('chart', { x: 0, y: 0, w: 8, h: 8 }),
      inst('replay-player', { x: 8, y: 0, w: 4, h: 4 }),
      inst('watchlist', { x: 8, y: 4, w: 4, h: 4 }),
      inst('positions', { x: 0, y: 8, w: 6, h: 5 }),
      inst('orders', { x: 6, y: 8, w: 3, h: 5 }),
      inst('equity-curve', { x: 9, y: 8, w: 3, h: 5 }),
      inst('signal-feed', { x: 0, y: 13, w: 6, h: 4 }),
      inst('risk-gauge', { x: 6, y: 13, w: 3, h: 4 }),
      inst('pnl-summary', { x: 9, y: 13, w: 3, h: 4 }),
    ],
  },

  // 7. Risk & P&L Workspace — risk monitoring
  {
    id: 'tpl-risk',
    name: 'Risk & P&L',
    builtIn: true,
    createdAt: Date.now(),
    updatedAt: Date.now(),
    widgets: [
      inst('pnl-summary', { x: 0, y: 0, w: 3, h: 3 }),
      inst('risk-gauge', { x: 3, y: 0, w: 3, h: 3 }),
      inst('breadth', { x: 6, y: 0, w: 3, h: 3 }),
      inst('equity-curve', { x: 9, y: 0, w: 3, h: 3 }),
      inst('positions', { x: 0, y: 3, w: 6, h: 5 }),
      inst('orders', { x: 6, y: 3, w: 6, h: 5 }),
      inst('alerts-feed', { x: 0, y: 8, w: 4, h: 5 }),
      inst('movers', { x: 4, y: 8, w: 4, h: 5 }),
      inst('rs-heatmap', { x: 8, y: 8, w: 4, h: 5 }),
      inst('strategy-list', { x: 0, y: 13, w: 6, h: 4 }),
      inst('signal-feed', { x: 6, y: 13, w: 6, h: 4 }),
    ],
  },

  // 8. Orderflow Pro — DeepCharts-style orderflow trading desk
  {
    id: 'tpl-orderflow',
    name: 'Orderflow Pro',
    builtIn: true,
    createdAt: Date.now(),
    updatedAt: Date.now(),
    widgets: [
      inst('footprint', { x: 0, y: 0, w: 7, h: 8 }, { symbol: 'NIFTY' }),
      inst('deepdom', { x: 7, y: 0, w: 3, h: 8 }),
      inst('volume-profile', { x: 10, y: 0, w: 2, h: 8 }),
      inst('deepprint', { x: 0, y: 8, w: 4, h: 6 }),
      inst('iceberg', { x: 4, y: 8, w: 4, h: 6 }),
      inst('buyside-squeeze', { x: 8, y: 8, w: 4, h: 6 }),
      inst('initial-balance', { x: 0, y: 14, w: 4, h: 4 }),
      inst('tpo-profile', { x: 4, y: 14, w: 4, h: 4 }),
      inst('dom-heatmap', { x: 8, y: 14, w: 4, h: 4 }),
    ],
  },

  // 9. AMT Scalper — fully-automated cyan/black canvas workspace
  {
    id: 'tpl-amt-scalper',
    name: 'AMT Scalper',
    builtIn: true,
    createdAt: Date.now(),
    updatedAt: Date.now(),
    widgets: [
      inst('amt-deep-chart', { x: 0, y: 0, w: 7, h: 8 }, { symbol: 'XAUUSDm' }),
      inst('amt-volume-profile', { x: 7, y: 0, w: 2, h: 8 }),
      inst('amt-deep-dom', { x: 9, y: 0, w: 3, h: 8 }),
      inst('positions', { x: 0, y: 8, w: 3, h: 4 }),
      inst('equity-curve', { x: 3, y: 8, w: 3, h: 4 }),
      inst('watchlist', { x: 6, y: 8, w: 3, h: 4 }),
      inst('signal-feed', { x: 9, y: 8, w: 3, h: 4 }),
    ],
  },
]
