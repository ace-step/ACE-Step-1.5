import type { AdapterLibraryEntry } from '../../../shared/training'
import { Button } from '../ui/Button'
import { cn } from '../../lib/utils'

interface AdapterLibraryCardProps {
  adapters: AdapterLibraryEntry[]
  librarySources: string[]
  selectedAdapterPath: string | null
  scanning: boolean
  actionPending: boolean
  onSelect: (path: string) => void
  onLoadSelected: () => void
  onReveal: (path: string) => void
  onAddFolder: () => void
  onAddFiles: () => void
  onRemoveSource: (path: string) => void
  onRescan: () => void
}

export function AdapterLibraryCard({
  adapters,
  librarySources,
  selectedAdapterPath,
  scanning,
  actionPending,
  onSelect,
  onLoadSelected,
  onReveal,
  onAddFolder,
  onAddFiles,
  onRemoveSource,
  onRescan
}: AdapterLibraryCardProps) {
  return (
    <section className="rounded-2xl border border-white/5 bg-white/[0.02] p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-medium text-[var(--color-text-primary)]">Adapter Library</h2>
          <p className="mt-1 text-xs leading-5 text-[var(--color-text-muted)]">
            Scan folders or add individual `.safetensors` files, then load the selected adapter into the running model.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button variant="default" size="sm" onClick={onAddFolder}>
            Add Folder
          </Button>
          <Button variant="default" size="sm" onClick={onAddFiles}>
            Add Files
          </Button>
          <Button variant="ghost" size="sm" onClick={onRescan} disabled={scanning}>
            {scanning ? 'Scanning...' : 'Rescan'}
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={onLoadSelected}
            disabled={!selectedAdapterPath || actionPending}
          >
            Load Selected
          </Button>
        </div>
      </div>

      <div className="mt-5 rounded-xl border border-white/5 bg-black/10 p-4">
        <div className="text-[11px] uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
          Library Sources
        </div>
        {librarySources.length === 0 ? (
          <p className="mt-2 text-sm text-[var(--color-text-muted)]">
            No folders or adapter files added yet.
          </p>
        ) : (
          <div className="mt-3 flex flex-wrap gap-2">
            {librarySources.map((source) => (
              <button
                key={source}
                onClick={() => onRemoveSource(source)}
                className="rounded-full border border-white/10 px-3 py-1 text-xs text-[var(--color-text-muted)] transition-colors hover:border-white/20 hover:text-[var(--color-text-primary)]"
              >
                {source}
              </button>
            ))}
          </div>
        )}
      </div>

      {adapters.length === 0 ? (
        <div className="mt-5 rounded-xl border border-dashed border-white/10 px-4 py-8 text-center text-sm text-[var(--color-text-muted)]">
          No adapters found in the current library. Add a folder or select one or more `.safetensors` files.
        </div>
      ) : (
        <div className="mt-5 space-y-3">
          {adapters.map((adapter) => {
            const selected = adapter.path === selectedAdapterPath

            return (
              <div
                key={adapter.path}
                className={cn(
                  'rounded-xl border p-4 transition-colors',
                  selected
                    ? 'border-[var(--color-violet)]/30 bg-[var(--color-violet)]/10'
                    : 'border-white/5 bg-black/10'
                )}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <button className="min-w-0 flex-1 text-left" onClick={() => onSelect(adapter.path)}>
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-medium text-[var(--color-text-primary)]">
                        {adapter.name}
                      </p>
                      <span className="rounded-full border border-white/10 px-2 py-0.5 text-[10px] uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
                        {adapter.kind}
                      </span>
                    </div>
                    <p className="mt-2 text-xs leading-5 text-[var(--color-text-muted)]">
                      {adapter.path}
                    </p>
                  </button>

                  <div className="flex gap-2">
                    <Button variant="ghost" size="sm" onClick={() => onReveal(adapter.path)}>
                      Reveal
                    </Button>
                    <Button variant="default" size="sm" onClick={() => onSelect(adapter.path)}>
                      {selected ? 'Selected' : 'Select'}
                    </Button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}
