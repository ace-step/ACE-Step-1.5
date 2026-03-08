import { useEffect } from 'react'

import { History, PlayCircle, RotateCcw } from 'lucide-react'

import { useGenerationHistoryStore } from '../../stores/generation-history'
import { Button } from '../ui/Button'

function formatTimestamp(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toLocaleString()
}

export function GenerationHistoryPanel() {
  const entries = useGenerationHistoryStore((state) => state.entries)
  const loading = useGenerationHistoryStore((state) => state.loading)
  const error = useGenerationHistoryStore((state) => state.error)
  const loadEntries = useGenerationHistoryStore((state) => state.loadEntries)
  const applyEntry = useGenerationHistoryStore((state) => state.applyEntry)
  const openEntryResults = useGenerationHistoryStore((state) => state.openEntryResults)
  const clearError = useGenerationHistoryStore((state) => state.clearError)

  useEffect(() => {
    void loadEntries()
  }, [loadEntries])

  if (loading && entries.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-[var(--color-text-muted)]">
        Loading generation history...
      </div>
    )
  }

  if (entries.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 text-[var(--color-text-muted)]">
        <History size={44} strokeWidth={1} className="opacity-20" />
        <p className="text-sm">Completed batches will appear here after generation finishes.</p>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto p-4">
      {error ? (
        <div className="mb-4 rounded-xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-100">
          {error}
        </div>
      ) : null}

      <div className="mb-4 flex justify-end">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            clearError()
            void loadEntries()
          }}
        >
          Refresh History
        </Button>
      </div>

      <div className="space-y-3">
        {entries.map((entry) => (
          <div
            key={entry.id}
            className="rounded-2xl border border-white/5 bg-white/[0.02] p-4 transition-colors hover:border-white/10"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="truncate text-sm font-medium text-[var(--color-text-primary)]">
                    {entry.prompt_preview || 'Untitled batch'}
                  </p>
                  <span className="rounded-full border border-white/10 px-2 py-0.5 text-[10px] uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
                    {entry.mode || 'custom'}
                  </span>
                </div>
                <p className="mt-2 text-xs text-[var(--color-text-muted)]">
                  {formatTimestamp(entry.created_at)} - {entry.track_count} saved track
                  {entry.track_count === 1 ? '' : 's'}
                </p>
                <p className="mt-1 text-xs leading-5 text-[var(--color-text-dim)]">
                  {entry.track_ids.length > 0
                    ? entry.tracks.map((track) => track.caption || track.id).join(', ')
                    : 'This batch has result snapshots but no saved library tracks yet.'}
                </p>
              </div>

              <div className="flex flex-wrap gap-2">
                <Button variant="ghost" size="sm" onClick={() => applyEntry(entry)}>
                  <RotateCcw size={14} />
                  Reuse Settings
                </Button>
                <Button variant="primary" size="sm" onClick={() => openEntryResults(entry)}>
                  <PlayCircle size={14} />
                  Open Results
                </Button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
