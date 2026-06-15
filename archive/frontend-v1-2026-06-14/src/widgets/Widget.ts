/**
 * Widget Framework — the core contract for all widgets in TradeXV2.
 *
 * Inspired by Bloomberg Launchpad, Grafana, Datadog, and TradingView's
 * multi-layout architecture: every visualization is a self-contained,
 * independently stateful building block that can be composed into any
 * workspace.
 *
 * Every widget has:
 *   - Independent state (config, data)
 *   - Independent refresh (data-fetching)
 *   - Independent data source (via DataLayer)
 *   - Independent layout (x, y, w, h in the grid)
 *   - Independent persistence (saved with workspace)
 */

import type { ReactNode, ComponentType } from 'react'
import type { LucideIcon } from 'lucide-react'

export type WidgetCategory =
  | 'market'
  | 'scanner'
  | 'analytics'
  | 'chart'
  | 'strategy'
  | 'replay'
  | 'portfolio'
  | 'risk'
  | 'options'
  | 'alerts'
  | 'utility'

/** A field in a widget's configuration form. */
export interface ConfigField {
  key: string
  label: string
  type: 'text' | 'number' | 'select' | 'multiselect' | 'toggle' | 'slider'
  default?: any
  options?: { value: any; label: string }[]
  min?: number
  max?: number
  step?: number
  description?: string
}

/** Props passed to every widget component. */
export interface WidgetProps<TConfig = Record<string, any>> {
  /** Unique instance id (auto-generated). */
  id: string
  /** Widget config (user-tunable). */
  config: TConfig
  /** Update a config key. */
  updateConfig?: (key: keyof TConfig, value: any) => void
  /** Refresh data manually. */
  refresh: () => void
  /** True while refreshing. */
  loading: boolean
  /** Last refresh timestamp. */
  lastUpdated?: number
}

/** Static widget metadata (registry entry). */
export interface WidgetManifest<TConfig = any> {
  /** Unique widget type id, e.g. "watchlist", "chart.candlestick". */
  type: string
  /** Display name. */
  name: string
  /** Short description. */
  description: string
  /** Group for the Widget Gallery. */
  category: WidgetCategory
  /** Icon (lucide). */
  icon: LucideIcon
  /** Default grid size (in columns / rows). */
  defaultSize: { w: number; h: number; minW: number; minH: number }
  /** Optional configuration form schema. */
  configSchema?: ConfigField[]
  /** Default config factory. */
  defaultConfig: () => TConfig
  /** The widget component. */
  component: ComponentType<WidgetProps<any>>
  /** Optional renderer for the config panel (advanced). */
  ConfigPanel?: ComponentType<{ config: TConfig; onChange: (c: TConfig) => void }>
}

/** A widget placed inside a workspace (instance + layout). */
export interface WidgetInstance {
  /** Unique instance id (uuid). */
  id: string
  /** The widget type — refers to WidgetManifest.type */
  type: string
  /** Per-instance config (overrides default). */
  config: Record<string, any>
  /** Position in the grid. */
  layout: {
    x: number
    y: number
    w: number
    h: number
    minW?: number
    minH?: number
  }
  /** Whether the widget is currently hidden (collapsed to a chip). */
  hidden?: boolean
  /** When hidden was toggled. */
  hiddenAt?: number
}

export type WidgetComponent<TConfig = Record<string, any>> = ComponentType<WidgetProps<TConfig>>

/** A workspace — a named collection of widget instances. */
export interface Workspace {
  id: string
  name: string
  icon?: string
  widgets: WidgetInstance[]
  createdAt: number
  updatedAt: number
  builtIn?: boolean
  isTemplate?: boolean
}
