import { useState, useCallback, useRef, useEffect } from 'react'
import {
  Search, X, SlidersHorizontal, LayoutList, LayoutGrid,
  ArrowUpDown, Trash2, FolderInput, ChevronDown
} from 'lucide-react'
import { cn } from '../../lib/utils'
import { useLibraryStore, type TrackSortField } from '../../stores/library'
import { usePlaylistsStore } from '../../stores/playlists'

const SORT_OPTIONS: { value: TrackSortField; label: string }[] = [
  { value: 'created_at', label: 'Date' },
  { value: 'rating', label: 'Rating' },
  { value: 'bpm', label: 'BPM' },
  { value: 'duration_seconds', label: 'Duration' },
  { value: 'caption', label: 'Title' }
]

const KEY_OPTIONS = [
  '', 'C major', 'C minor', 'C# major', 'C# minor',
  'D major', 'D minor', 'Eb major', 'Eb minor',
  'E major', 'E minor', 'F major', 'F minor',
  'F# major', 'F# minor', 'G major', 'G minor',
  'Ab major', 'Ab minor', 'A major', 'A minor',
  'Bb major', 'Bb minor', 'B major', 'B minor'
]

export function LibraryToolbar() {
  const {
    filters, sortField, sortDirection, viewMode, activePlaylistId,
    selectedTrackIds, totalTrackCount,
    setFilters, resetFilters, setSort, setViewMode,
    deleteTracks, clearSelection
  } = useLibraryStore()
  const removeTracksFromActivePlaylist = usePlaylistsStore((s) => s.removeTracksFromActivePlaylist)

  const [searchValue, setSearchValue] = useState(filters.search)
  const [showFilters, setShowFilters] = useState(false)
  const [showSort, setShowSort] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const sortRef = useRef<HTMLDivElement>(null)

  // Close sort dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (sortRef.current && !sortRef.current.contains(e.target as Node)) {
        setShowSort(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleSearchChange = useCallback((value: string) => {
    setSearchValue(value)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setFilters({ search: value })
    }, 300)
  }, [setFilters])

  const clearSearch = useCallback(() => {
    setSearchValue('')
    setFilters({ search: '' })
  }, [setFilters])

  const hasActiveFilters = filters.bpmMin != null || filters.bpmMax != null ||
    filters.keyScale != null || filters.ratingMin != null ||
    filters.generationMode != null || filters.isFavorite === true

  const selectedCount = selectedTrackIds.size

  const handleRemoveFromPlaylist = useCallback(async () => {
    await removeTracksFromActivePlaylist(Array.from(selectedTrackIds))
    clearSelection()
  }, [clearSelection, removeTracksFromActivePlaylist, selectedTrackIds])

  return (
    <div className="flex flex-col gap-2 border-b border-white/5 px-4 py-2.5">
      {/* Main toolbar row */}
      <div className="flex items-center gap-2">
        {/* Search */}
        <div className="relative flex-1 max-w-sm">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--color-text-dim)]" />
          <input
            type="text"
            value={searchValue}
            onChange={(e) => handleSearchChange(e.target.value)}
            placeholder="Search tracks..."
            className="h-8 w-full rounded-md border border-white/5 bg-white/[0.03] pl-8 pr-8 text-xs text-[var(--color-text-primary)] placeholder-[var(--color-text-dim)] outline-none focus:border-[var(--color-violet)]/30 transition-colors"
          />
          {searchValue && (
            <button
              onClick={clearSearch}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--color-text-dim)] hover:text-[var(--color-text-muted)]"
            >
              <X size={12} />
            </button>
          )}
        </div>

        {/* Filter toggle */}
        <button
          onClick={() => setShowFilters(!showFilters)}
          className={cn(
            'flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs transition-colors',
            showFilters || hasActiveFilters
              ? 'bg-[var(--color-violet)]/15 text-[var(--color-violet)]'
              : 'text-[var(--color-text-muted)] hover:bg-white/5'
          )}
        >
          <SlidersHorizontal size={13} />
          <span>Filter</span>
          {hasActiveFilters && (
            <span className="flex h-4 w-4 items-center justify-center rounded-full bg-[var(--color-violet)] text-[9px] text-white">
              !
            </span>
          )}
        </button>

        {/* Sort dropdown */}
        <div ref={sortRef} className="relative">
          <button
            onClick={() => setShowSort(!showSort)}
            className="flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs text-[var(--color-text-muted)] hover:bg-white/5 transition-colors"
          >
            <ArrowUpDown size={13} />
            <span>{SORT_OPTIONS.find((s) => s.value === sortField)?.label}</span>
            <ChevronDown size={11} className={cn('transition-transform', showSort && 'rotate-180')} />
          </button>
          {showSort && (
            <div className="absolute right-0 top-full z-20 mt-1 w-36 rounded-lg border border-white/10 bg-[var(--color-bg-secondary)] py-1 shadow-xl">
              {SORT_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => {
                    setSort(opt.value)
                    setShowSort(false)
                  }}
                  className={cn(
                    'flex w-full items-center px-3 py-1.5 text-xs transition-colors',
                    sortField === opt.value
                      ? 'text-[var(--color-violet)]'
                      : 'text-[var(--color-text-muted)] hover:bg-white/5'
                  )}
                >
                  {opt.label}
                  {sortField === opt.value && (
                    <span className="ml-auto text-[10px]">
                      {sortDirection === 'asc' ? '↑' : '↓'}
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="w-px h-5 bg-white/5" />

        {/* View mode */}
        <div className="flex rounded-md border border-white/5">
          <button
            onClick={() => setViewMode('list')}
            className={cn(
              'flex h-7 w-7 items-center justify-center rounded-l-md transition-colors',
              viewMode === 'list'
                ? 'bg-white/10 text-[var(--color-text-primary)]'
                : 'text-[var(--color-text-dim)] hover:text-[var(--color-text-muted)]'
            )}
            title="List view"
          >
            <LayoutList size={13} />
          </button>
          <button
            onClick={() => setViewMode('grid')}
            className={cn(
              'flex h-7 w-7 items-center justify-center rounded-r-md transition-colors',
              viewMode === 'grid'
                ? 'bg-white/10 text-[var(--color-text-primary)]'
                : 'text-[var(--color-text-dim)] hover:text-[var(--color-text-muted)]'
            )}
            title="Grid view"
          >
            <LayoutGrid size={13} />
          </button>
        </div>

        {/* Track count */}
        <span className="text-[10px] text-[var(--color-text-dim)] tabular-nums ml-1">
          {totalTrackCount} track{totalTrackCount !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Bulk action bar (when tracks selected) */}
      {selectedCount > 0 && (
        <div className="flex items-center gap-2 rounded-md bg-[var(--color-violet)]/10 px-3 py-1.5">
          <span className="text-xs text-[var(--color-violet)]">
            {selectedCount} selected
          </span>
          <div className="flex-1" />
          <button
            onClick={clearSelection}
            className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
          >
            Clear
          </button>
          <button
            onClick={() => deleteTracks(Array.from(selectedTrackIds))}
            className="flex items-center gap-1 text-xs text-red-400 hover:text-red-300 transition-colors"
          >
            <Trash2 size={12} />
            Delete
          </button>
          {activePlaylistId && (
            <button
              onClick={() => {
                void handleRemoveFromPlaylist()
              }}
              className="flex items-center gap-1 text-xs text-[var(--color-cyan)] hover:text-cyan-300 transition-colors"
            >
              <FolderInput size={12} />
              Remove from Playlist
            </button>
          )}
        </div>
      )}

      {/* Expanded filter row */}
      {showFilters && (
        <div className="flex flex-wrap items-center gap-2 pt-1">
          {/* BPM range */}
          <div className="flex items-center gap-1">
            <span className="text-[10px] text-[var(--color-text-dim)]">BPM</span>
            <input
              type="number"
              value={filters.bpmMin ?? ''}
              onChange={(e) => setFilters({ bpmMin: e.target.value ? Number(e.target.value) : null })}
              placeholder="60"
              className="h-6 w-14 rounded border border-white/5 bg-white/[0.03] px-1.5 text-[10px] text-[var(--color-text-primary)] outline-none focus:border-[var(--color-violet)]/30"
            />
            <span className="text-[10px] text-[var(--color-text-dim)]">–</span>
            <input
              type="number"
              value={filters.bpmMax ?? ''}
              onChange={(e) => setFilters({ bpmMax: e.target.value ? Number(e.target.value) : null })}
              placeholder="200"
              className="h-6 w-14 rounded border border-white/5 bg-white/[0.03] px-1.5 text-[10px] text-[var(--color-text-primary)] outline-none focus:border-[var(--color-violet)]/30"
            />
          </div>

          <div className="w-px h-4 bg-white/5" />

          {/* Key select */}
          <div className="flex items-center gap-1">
            <span className="text-[10px] text-[var(--color-text-dim)]">Key</span>
            <select
              value={filters.keyScale || ''}
              onChange={(e) => setFilters({ keyScale: e.target.value || null })}
              className="h-6 rounded border border-white/5 bg-white/[0.03] px-1.5 text-[10px] text-[var(--color-text-primary)] outline-none"
            >
              <option value="">Any</option>
              {KEY_OPTIONS.filter(Boolean).map((k) => (
                <option key={k} value={k}>{k}</option>
              ))}
            </select>
          </div>

          <div className="w-px h-4 bg-white/5" />

          {/* Min rating */}
          <div className="flex items-center gap-1">
            <span className="text-[10px] text-[var(--color-text-dim)]">Rating ≥</span>
            <select
              value={filters.ratingMin ?? ''}
              onChange={(e) => setFilters({ ratingMin: e.target.value ? Number(e.target.value) : null })}
              className="h-6 rounded border border-white/5 bg-white/[0.03] px-1.5 text-[10px] text-[var(--color-text-primary)] outline-none"
            >
              <option value="">Any</option>
              {[1, 2, 3, 4, 5].map((r) => (
                <option key={r} value={r}>{'★'.repeat(r)}</option>
              ))}
            </select>
          </div>

          <div className="w-px h-4 bg-white/5" />

          {/* Favorites only */}
          <label className="flex items-center gap-1 cursor-pointer">
            <input
              type="checkbox"
              checked={filters.isFavorite === true}
              onChange={(e) => setFilters({ isFavorite: e.target.checked ? true : null })}
              className="h-3 w-3 rounded accent-[var(--color-violet)]"
            />
            <span className="text-[10px] text-[var(--color-text-dim)]">Favorites</span>
          </label>

          {/* Reset */}
          {hasActiveFilters && (
            <button
              onClick={resetFilters}
              className="ml-auto text-[10px] text-[var(--color-text-dim)] hover:text-[var(--color-violet)] transition-colors"
            >
              Reset filters
            </button>
          )}
        </div>
      )}
    </div>
  )
}
