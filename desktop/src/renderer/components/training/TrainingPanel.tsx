import { useEffect, useState } from 'react'

import { useTrainingStore } from '../../stores/training'
import { AdapterLibraryCard } from './AdapterLibraryCard'
import { AdapterRuntimeCard } from './AdapterRuntimeCard'
import { ModelManagementPanel } from './ModelManagementPanel'
import { TrainingWorkflowPanel } from './TrainingWorkflowPanel'
import { Tabs } from '../ui/Tabs'

type TrainingView = 'workflow' | 'adapters' | 'models'

export function TrainingPanel() {
  const [activeView, setActiveView] = useState<TrainingView>('workflow')
  const {
    librarySources,
    adapters,
    selectedAdapterPath,
    status,
    loading,
    scanning,
    actionPending,
    error,
    hydrate,
    refreshStatus,
    addLibrarySources,
    removeLibrarySource,
    rescanLibrary,
    selectAdapter,
    loadSelectedAdapter,
    unloadAdapter,
    setAdapterEnabled,
    setAdapterScale,
    clearError
  } = useTrainingStore()

  useEffect(() => {
    void hydrate()
  }, [hydrate])

  const addFolders = async () => {
    clearError()
    const paths = await window.aceStep.fs.openDialog({
      properties: ['openDirectory', 'multiSelections'],
      title: 'Add Adapter Folders'
    })
    await addLibrarySources(paths)
  }

  const addFiles = async () => {
    clearError()
    const paths = await window.aceStep.fs.openDialog({
      properties: ['openFile', 'multiSelections'],
      title: 'Add Adapter Files',
      filters: [{ name: 'SafeTensors', extensions: ['safetensors'] }]
    })
    await addLibrarySources(paths)
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-6xl p-6">
        <div className="mb-6">
          <h1 className="text-lg font-semibold text-[var(--color-text-primary)]">Training</h1>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">
            Runtime training tools now cover adapter management and model inventory without leaving the desktop app.
          </p>
        </div>

        <Tabs
          className="mb-6 max-w-sm"
          value={activeView}
          onChange={setActiveView}
          tabs={[
            { value: 'workflow', label: 'Workflow' },
            { value: 'adapters', label: 'Adapters' },
            { value: 'models', label: 'Models' }
          ]}
        />

        {error && activeView === 'adapters' ? (
          <div className="mb-6 rounded-xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-100">
            {error}
          </div>
        ) : null}

        {loading && activeView === 'adapters' ? (
          <div className="rounded-2xl border border-white/5 bg-white/[0.02] px-5 py-10 text-center text-sm text-[var(--color-text-muted)]">
            Loading adapter runtime...
          </div>
        ) : activeView === 'workflow' ? (
          <TrainingWorkflowPanel />
        ) : activeView === 'models' ? (
          <ModelManagementPanel />
        ) : (
          <div className="space-y-6">
            <AdapterRuntimeCard
              status={status}
              actionPending={actionPending}
              onRefresh={() => void refreshStatus()}
              onUnload={() => void unloadAdapter()}
              onToggleEnabled={(enabled) => void setAdapterEnabled(enabled)}
              onScaleChange={(scale) => void setAdapterScale(scale)}
            />
            <AdapterLibraryCard
              adapters={adapters}
              librarySources={librarySources}
              selectedAdapterPath={selectedAdapterPath}
              scanning={scanning}
              actionPending={actionPending}
              onSelect={selectAdapter}
              onLoadSelected={() => void loadSelectedAdapter()}
              onReveal={(path) => void window.aceStep.fs.revealInExplorer(path)}
              onAddFolder={() => void addFolders()}
              onAddFiles={() => void addFiles()}
              onRemoveSource={(path) => void removeLibrarySource(path)}
              onRescan={() => void rescanLibrary()}
            />
          </div>
        )}
      </div>
    </div>
  )
}
