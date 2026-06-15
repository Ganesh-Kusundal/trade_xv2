/**
 * Workspace — root page for the widget-based workspace mode.
 * Wraps the WorkspaceCanvas with selection state.
 */

import { useState } from 'react'
import { WorkspaceCanvas } from '@/workspaces/WorkspaceCanvas'

export function Workspace() {
  const [selectedWidgetId, setSelectedWidgetId] = useState<string | null>(null)
  return <WorkspaceCanvas selectedWidgetId={selectedWidgetId} onSelectWidget={setSelectedWidgetId} />
}
