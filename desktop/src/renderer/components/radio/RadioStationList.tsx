import { Plus, Trash2 } from 'lucide-react'

import type { RadioStationRecord } from '../../../shared/radio'
import { Button } from '../ui/Button'
import { cn } from '../../lib/utils'

interface RadioStationListProps {
  stations: RadioStationRecord[]
  activeStationId: string | null
  onCreate: () => void
  onSelect: (stationId: string) => void
  onDelete: (stationId: string) => void
}

export function RadioStationList({
  stations,
  activeStationId,
  onCreate,
  onSelect,
  onDelete
}: RadioStationListProps) {
  return (
    <aside className="flex w-full max-w-[320px] flex-col border-r border-white/5 bg-black/10">
      <div className="flex items-center justify-between gap-3 border-b border-white/5 px-4 py-4">
        <div>
          <p className="text-sm font-semibold text-[var(--color-text-primary)]">Radio</p>
          <p className="text-xs text-[var(--color-text-muted)]">Station presets and output history</p>
        </div>
        <Button variant="primary" size="sm" onClick={onCreate}>
          <Plus size={14} />
          New
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {stations.length === 0 ? (
          <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.02] p-4 text-xs text-[var(--color-text-muted)]">
            Create a station to define a recurring vibe and capture every generated track in one place.
          </div>
        ) : (
          stations.map((station) => {
            const isActive = station.id === activeStationId
            return (
              <div
                key={station.id}
                className={cn(
                  'group mb-2 rounded-xl border transition-colors',
                  isActive
                    ? 'border-[var(--color-violet)]/30 bg-[var(--color-violet)]/10'
                    : 'border-white/5 bg-white/[0.02] hover:border-white/10 hover:bg-white/[0.04]'
                )}
              >
                <div className="flex items-start justify-between gap-3 px-3 pt-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-[var(--color-text-primary)]">
                      {station.name}
                    </p>
                    <p className="truncate text-[11px] uppercase tracking-[0.12em] text-[var(--color-text-muted)]">
                      {station.genre || 'custom station'}
                    </p>
                  </div>
                  <button
                    onClick={() => onDelete(station.id)}
                    className="rounded-md p-1 text-[var(--color-text-muted)] opacity-0 transition group-hover:opacity-100 hover:bg-white/5 hover:text-red-300"
                    title="Delete station"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>

                <button
                  onClick={() => onSelect(station.id)}
                  className="flex w-full flex-col gap-2 px-3 pb-3 text-left"
                >
                  <p className="line-clamp-2 text-xs text-[var(--color-text-muted)]">
                    {station.caption_template || station.description || 'No station prompt yet'}
                  </p>

                  <div className="flex items-center justify-between text-[11px] text-[var(--color-text-muted)]">
                    <span>{station.track_count} tracks</span>
                    <span>{station.output_playlist_id || 'Library only'}</span>
                  </div>
                </button>
              </div>
            )
          })
        )}
      </div>
    </aside>
  )
}
