import type { GenerationMode } from '../../api/types'
import { useGenerationHistoryStore } from '../../stores/generation-history'
import { useGenerationStore } from '../../stores/generation'
import { Tabs } from '../ui/Tabs'
import { BatchNav } from './BatchNav'
import { CustomMode } from './CustomMode'
import { GenerateButton } from './GenerateButton'
import { GenerationHistoryPanel } from './GenerationHistoryPanel'
import { ResultsGrid } from './ResultsGrid'
import { SimpleMode } from './SimpleMode'
import { SourceMode } from './SourceMode'

const modeTabs: { value: GenerationMode; label: string }[] = [
  { value: 'simple', label: 'Simple' },
  { value: 'custom', label: 'Custom' },
  { value: 'remix', label: 'Remix' },
  { value: 'repaint', label: 'Repaint' },
  { value: 'extract', label: 'Extract' },
  { value: 'lego', label: 'Lego' },
  { value: 'complete', label: 'Complete' }
]

export function GenerationStudio() {
  const { mode, setMode } = useGenerationStore()
  const activeView = useGenerationHistoryStore((state) => state.activeView)
  const setView = useGenerationHistoryStore((state) => state.setView)

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="overflow-x-auto border-b border-white/5 px-4 py-3">
        <Tabs value={mode} onChange={setMode} tabs={modeTabs} className="w-fit flex-wrap" />
      </div>

      <div className="flex flex-1 overflow-hidden">
        <div className="flex w-[400px] shrink-0 flex-col overflow-y-auto border-r border-white/5">
          <div className="flex-1 p-4">
            {mode === 'simple' ? (
              <SimpleMode />
            ) : mode === 'custom' ? (
              <CustomMode />
            ) : (
              <SourceMode mode={mode} />
            )}
          </div>
          <div className="border-t border-white/5 p-4">
            <GenerateButton />
          </div>
        </div>

        <div className="flex flex-1 flex-col overflow-hidden">
          <div className="border-b border-white/5 px-4 py-3">
            <Tabs
              value={activeView}
              onChange={setView}
              tabs={[
                { value: 'results', label: 'Results' },
                { value: 'history', label: 'History' }
              ]}
              className="w-fit"
            />
          </div>
          {activeView === 'history' ? (
            <GenerationHistoryPanel />
          ) : (
            <>
              <ResultsGrid />
              <BatchNav />
            </>
          )}
        </div>
      </div>
    </div>
  )
}
