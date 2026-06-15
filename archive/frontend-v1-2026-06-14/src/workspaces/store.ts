/**
 * Workspace Store — Zustand store for the widget-based workspace system.
 *
 * State:
 *   - workspaces: all saved workspaces (templates + user-created)
 *   - currentWorkspaceId: which one is active
 *   - editingMode: true when user is in "customize" mode (widgets show settings/remove)
 *
 * Actions:
 *   - create / duplicate / delete workspace
 *   - add / remove / move / resize / configure widget
 *   - set current workspace
 *   - save layout
 *
 * Persisted to localStorage automatically.
 */

import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Workspace, WidgetInstance } from '@/widgets/Widget'
import { widgetRegistry } from '@/widgets/registry'
import { WORKSPACE_TEMPLATES } from './templates'

interface WorkspaceState {
  workspaces: Workspace[]
  currentWorkspaceId: string | null
  editingMode: boolean

  // Workspace operations
  setCurrent: (id: string) => void
  createWorkspace: (name: string, fromTemplateId?: string) => string
  duplicateWorkspace: (id: string) => string
  deleteWorkspace: (id: string) => void
  renameWorkspace: (id: string, name: string) => void
  setEditingMode: (editing: boolean) => void

  // Widget operations
  addWidget: (workspaceId: string, type: string, layout?: { x: number; y: number }) => string | null
  removeWidget: (workspaceId: string, widgetId: string) => void
  updateWidgetLayout: (workspaceId: string, layouts: { i: string; x: number; y: number; w: number; h: number }[]) => void
  updateWidgetConfig: (workspaceId: string, widgetId: string, config: Record<string, any>) => void
  toggleWidgetHidden: (workspaceId: string, widgetId: string) => void
  showAllWidgets: (workspaceId: string) => void

  // Selectors
  getCurrent: () => Workspace | undefined
}

const generateId = (prefix: string) => `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`

export const useWorkspaceStore = create<WorkspaceState>()(
  persist(
    (set, get) => ({
      workspaces: WORKSPACE_TEMPLATES,
      currentWorkspaceId: WORKSPACE_TEMPLATES[0]?.id || null,
      editingMode: false,

      setCurrent: (id) => set({ currentWorkspaceId: id }),

      createWorkspace: (name, fromTemplateId) => {
        const id = generateId('ws')
        let widgets: WidgetInstance[] = []
        if (fromTemplateId) {
          const template = get().workspaces.find((w) => w.id === fromTemplateId)
          if (template) {
            widgets = template.widgets.map((w) => ({
              ...w,
              id: generateId('w'),
            }))
          }
        } else {
          // Create an empty workspace with one default widget
          const instance = widgetRegistry.createInstance('watchlist', { x: 0, y: 0 })
          if (instance) widgets = [instance]
        }
        const newWs: Workspace = {
          id,
          name,
          widgets,
          createdAt: Date.now(),
          updatedAt: Date.now(),
        }
        set((s) => ({
          workspaces: [...s.workspaces, newWs],
          currentWorkspaceId: id,
        }))
        return id
      },

      duplicateWorkspace: (id) => {
        const original = get().workspaces.find((w) => w.id === id)
        if (!original) return id
        const newId = generateId('ws')
        const copy: Workspace = {
          ...original,
          id: newId,
          name: `${original.name} (Copy)`,
          builtIn: false,
          widgets: original.widgets.map((w) => ({ ...w, id: generateId('w') })),
          createdAt: Date.now(),
          updatedAt: Date.now(),
        }
        set((s) => ({
          workspaces: [...s.workspaces, copy],
          currentWorkspaceId: newId,
        }))
        return newId
      },

      deleteWorkspace: (id) => {
        const ws = get().workspaces.find((w) => w.id === id)
        if (ws?.builtIn) return // Cannot delete built-in
        set((s) => {
          const filtered = s.workspaces.filter((w) => w.id !== id)
          return {
            workspaces: filtered,
            currentWorkspaceId: s.currentWorkspaceId === id ? (filtered[0]?.id || null) : s.currentWorkspaceId,
          }
        })
      },

      renameWorkspace: (id, name) =>
        set((s) => ({
          workspaces: s.workspaces.map((w) => (w.id === id ? { ...w, name, updatedAt: Date.now() } : w)),
        })),

      setEditingMode: (editing) => set({ editingMode: editing }),

      addWidget: (workspaceId, type, layout) => {
        const instance = widgetRegistry.createInstance(type, layout)
        if (!instance) return null
        set((s) => ({
          workspaces: s.workspaces.map((w) =>
            w.id === workspaceId
              ? { ...w, widgets: [...w.widgets, instance], updatedAt: Date.now() }
              : w,
          ),
        }))
        return instance.id
      },

      removeWidget: (workspaceId, widgetId) =>
        set((s) => ({
          workspaces: s.workspaces.map((w) =>
            w.id === workspaceId
              ? { ...w, widgets: w.widgets.filter((wi) => wi.id !== widgetId), updatedAt: Date.now() }
              : w,
          ),
        })),

      updateWidgetLayout: (workspaceId, layouts) =>
        set((s) => ({
          workspaces: s.workspaces.map((w) => {
            if (w.id !== workspaceId) return w
            const newWidgets = w.widgets.map((wi) => {
              const layout = layouts.find((l) => l.i === wi.id)
              if (!layout) return wi
              return { ...wi, layout: { ...wi.layout, x: layout.x, y: layout.y, w: layout.w, h: layout.h } }
            })
            return { ...w, widgets: newWidgets, updatedAt: Date.now() }
          }),
        })),

      updateWidgetConfig: (workspaceId, widgetId, config) =>
        set((s) => ({
          workspaces: s.workspaces.map((w) =>
            w.id === workspaceId
              ? {
                  ...w,
                  widgets: w.widgets.map((wi) => (wi.id === widgetId ? { ...wi, config: { ...wi.config, ...config } } : wi)),
                  updatedAt: Date.now(),
                }
              : w,
          ),
        })),

      toggleWidgetHidden: (workspaceId, widgetId) =>
        set((s) => ({
          workspaces: s.workspaces.map((w) =>
            w.id === workspaceId
              ? {
                  ...w,
                  widgets: w.widgets.map((wi) =>
                    wi.id === widgetId
                      ? { ...wi, hidden: !wi.hidden, hiddenAt: !wi.hidden ? Date.now() : undefined }
                      : wi,
                  ),
                  updatedAt: Date.now(),
                }
              : w,
          ),
        })),

      showAllWidgets: (workspaceId) =>
        set((s) => ({
          workspaces: s.workspaces.map((w) =>
            w.id === workspaceId
              ? { ...w, widgets: w.widgets.map((wi) => ({ ...wi, hidden: false, hiddenAt: undefined })), updatedAt: Date.now() }
              : w,
          ),
        })),

      getCurrent: () => {
        const id = get().currentWorkspaceId
        return get().workspaces.find((w) => w.id === id)
      },
    }),
    {
      name: 'tradex-workspaces',
      partialize: (s) => ({ workspaces: s.workspaces, currentWorkspaceId: s.currentWorkspaceId }),
    },
  ),
)
