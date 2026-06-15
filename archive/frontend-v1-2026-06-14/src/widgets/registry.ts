/**
 * Widget Registry — central singleton that holds all widget manifests.
 *
 * Adding a new widget:
 *   1. Create a widget component
 *   2. Define a manifest
 *   3. Register it via registerWidget()
 *   4. Use it from the Widget Gallery — no routing/nav changes needed
 *
 * Usage:
 *   import { widgetRegistry } from '@/widgets/registry'
 *   const manifest = widgetRegistry.get('watchlist')
 *   const list = widgetRegistry.list({ category: 'market' })
 */

import type { WidgetManifest, WidgetCategory, WidgetInstance } from './Widget'

class WidgetRegistry {
  private manifests = new Map<string, WidgetManifest>()
  private categories: { id: WidgetCategory; label: string; order: number }[] = [
    { id: 'market', label: 'Market', order: 1 },
    { id: 'chart', label: 'Charts', order: 2 },
    { id: 'scanner', label: 'Scanner', order: 3 },
    { id: 'analytics', label: 'Analytics', order: 4 },
    { id: 'options', label: 'Options', order: 5 },
    { id: 'strategy', label: 'Strategy', order: 6 },
    { id: 'replay', label: 'Replay', order: 7 },
    { id: 'portfolio', label: 'Portfolio', order: 8 },
    { id: 'risk', label: 'Risk', order: 9 },
    { id: 'alerts', label: 'Alerts', order: 10 },
    { id: 'utility', label: 'Tools', order: 11 },
  ]

  register<TConfig = Record<string, any>>(manifest: WidgetManifest<TConfig>) {
    if (this.manifests.has(manifest.type)) {
      console.warn(`[WidgetRegistry] Overwriting existing widget "${manifest.type}"`)
    }
    this.manifests.set(manifest.type, manifest as unknown as WidgetManifest)
  }

  get(type: string): WidgetManifest | undefined {
    return this.manifests.get(type)
  }

  has(type: string): boolean {
    return this.manifests.has(type)
  }

  list(filter?: { category?: WidgetCategory }): WidgetManifest[] {
    const all = Array.from(this.manifests.values())
    if (filter?.category) {
      return all.filter((m) => m.category === filter.category)
    }
    return all.sort((a, b) => a.name.localeCompare(b.name))
  }

  listByCategory(): Record<WidgetCategory, WidgetManifest[]> {
    const out = {} as Record<WidgetCategory, WidgetManifest[]>
    for (const cat of this.categories) out[cat.id] = []
    for (const manifest of this.manifests.values()) {
      out[manifest.category].push(manifest)
    }
    return out
  }

  getCategories() {
    return this.categories
  }

  /** Build a default WidgetInstance from a manifest type. */
  createInstance(type: string, layout?: { x: number; y: number }): WidgetInstance | null {
    const manifest = this.get(type)
    if (!manifest) return null
    return {
      id: `w-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      type,
      config: manifest.defaultConfig(),
      layout: {
        x: layout?.x ?? 0,
        y: layout?.y ?? 0,
        w: manifest.defaultSize.w,
        h: manifest.defaultSize.h,
        minW: manifest.defaultSize.minW,
        minH: manifest.defaultSize.minH,
      },
    }
  }
}

export const widgetRegistry = new WidgetRegistry()
export type { WidgetCategory }
