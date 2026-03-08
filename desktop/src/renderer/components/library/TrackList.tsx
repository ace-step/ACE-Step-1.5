import { useRef, useCallback } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Music } from 'lucide-react'
import { useLibraryStore } from '../../stores/library'
import { useAudioStore } from '../../stores/audio'
import { TrackRow } from './TrackRow'
import { TrackCard } from './TrackCard'

export function TrackList() {
  const {
    tracks, viewMode, isLoading, totalTrackCount,
    selectedTrackIds, page, pageSize, setPage
  } = useLibraryStore()
  const currentTrackId = useAudioStore((s) => s.currentTrackId)
  const isAudioPlaying = useAudioStore((s) => s.isPlaying)

  const parentRef = useRef<HTMLDivElement>(null)

  // List mode virtualizer
  const listVirtualizer = useVirtualizer({
    count: tracks.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 64,
    overscan: 10
  })

  // Grid mode virtualizer (rows of cards)
  const CARD_WIDTH = 200
  const GAP = 12
  const parentWidth = parentRef.current?.clientWidth || 800
  const columns = Math.max(1, Math.floor((parentWidth + GAP) / (CARD_WIDTH + GAP)))
  const gridRows = Math.ceil(tracks.length / columns)

  const gridVirtualizer = useVirtualizer({
    count: gridRows,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 240,
    overscan: 4
  })

  // Pagination
  const totalPages = Math.ceil(totalTrackCount / pageSize)
  const hasMore = page < totalPages - 1

  // Empty state
  if (!isLoading && tracks.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 text-[var(--color-text-muted)]">
        <Music size={40} className="text-white/10" />
        <p className="text-sm">No tracks yet</p>
        <p className="text-xs text-[var(--color-text-dim)]">
          Generate some music to see it here
        </p>
      </div>
    )
  }

  // Loading skeleton
  if (isLoading && tracks.length === 0) {
    return (
      <div className="flex flex-1 flex-col gap-1 px-1">
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="flex h-16 items-center gap-3 px-3 animate-pulse"
          >
            <div className="h-3.5 w-3.5 rounded bg-white/5" />
            <div className="h-8 w-8 rounded-full bg-white/5" />
            <div className="flex-1 space-y-1.5">
              <div className="h-3 w-40 rounded bg-white/5" />
              <div className="h-2.5 w-24 rounded bg-white/5" />
            </div>
            <div className="h-3 w-16 rounded bg-white/5" />
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div
        ref={parentRef}
        className="flex-1 overflow-auto"
      >
        {viewMode === 'list' ? (
          // ── List View ──
          <div
            style={{ height: listVirtualizer.getTotalSize(), position: 'relative' }}
          >
            {listVirtualizer.getVirtualItems().map((virtualItem) => {
              const track = tracks[virtualItem.index]
              if (!track) return null
              return (
                <div
                  key={track.id}
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    height: `${virtualItem.size}px`,
                    transform: `translateY(${virtualItem.start}px)`
                  }}
                >
                  <TrackRow
                    track={track}
                    isSelected={selectedTrackIds.has(track.id)}
                    isPlaying={isAudioPlaying && currentTrackId === track.id}
                  />
                </div>
              )
            })}
          </div>
        ) : (
          // ── Grid View ──
          <div
            style={{ height: gridVirtualizer.getTotalSize(), position: 'relative' }}
            className="px-3 pt-3"
          >
            {gridVirtualizer.getVirtualItems().map((virtualRow) => {
              const startIndex = virtualRow.index * columns
              const rowTracks = tracks.slice(startIndex, startIndex + columns)

              return (
                <div
                  key={virtualRow.index}
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    transform: `translateY(${virtualRow.start}px)`
                  }}
                  className="flex gap-3 pb-3"
                >
                  {rowTracks.map((track) => (
                    <div key={track.id} style={{ width: CARD_WIDTH }} className="shrink-0">
                      <TrackCard
                        track={track}
                        isSelected={selectedTrackIds.has(track.id)}
                        isPlaying={isAudioPlaying && currentTrackId === track.id}
                      />
                    </div>
                  ))}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Pagination footer */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 border-t border-white/5 px-4 py-2">
          <button
            onClick={() => setPage(page - 1)}
            disabled={page === 0}
            className="rounded px-2.5 py-1 text-xs text-[var(--color-text-muted)] hover:bg-white/5 disabled:opacity-30 disabled:pointer-events-none transition-colors"
          >
            Previous
          </button>
          <span className="text-[10px] tabular-nums text-[var(--color-text-dim)]">
            Page {page + 1} of {totalPages}
          </span>
          <button
            onClick={() => setPage(page + 1)}
            disabled={!hasMore}
            className="rounded px-2.5 py-1 text-xs text-[var(--color-text-muted)] hover:bg-white/5 disabled:opacity-30 disabled:pointer-events-none transition-colors"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
