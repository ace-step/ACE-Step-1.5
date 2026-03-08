import { memo, useCallback, useState } from 'react'
import {
  Play, Pause, Heart, Star, MoreHorizontal,
  GitCompareArrows, RefreshCw, Trash2, FolderInput, Music2
} from 'lucide-react'
import { cn, formatDuration } from '../../lib/utils'
import { useLibraryStore, type TrackRecord } from '../../stores/library'
import { useGenerationStore } from '../../stores/generation'
import { useUIStore } from '../../stores/ui'
import { useAudioStore } from '../../stores/audio'
import { setDraggedTrackIds } from '../../lib/track-drag'
import { buildTrackQueue, type PlaybackQueueContext } from '../../lib/playback-queue'
import { usePlaylistsStore } from '../../stores/playlists'

interface TrackRowProps {
  track: TrackRecord
  isSelected: boolean
  isPlaying: boolean
}

export const TrackRow = memo(function TrackRow({ track, isSelected, isPlaying }: TrackRowProps) {
  const [showMenu, setShowMenu] = useState(false)
  const {
    toggleTrackSelection, toggleFavorite, setRating,
    setCompareSlot, deleteTrack, selectedTrackIds
  } = useLibraryStore()
  const currentTrackId = useAudioStore((s) => s.currentTrackId)
  const playQueue = useAudioStore((s) => s.playQueue)
  const pause = useAudioStore((s) => s.pause)
  const resume = useAudioStore((s) => s.resume)
  const loadFromTrack = useGenerationStore((s) => s.loadFromTrack)
  const setActiveSection = useUIStore((s) => s.setActiveSection)

  const isCurrent = currentTrackId === track.id

  const handlePlay = useCallback(() => {
    if (isCurrent) {
      if (isPlaying) {
        pause()
      } else {
        resume()
      }
      return
    }

    const libraryState = useLibraryStore.getState()
    const playlistState = usePlaylistsStore.getState()
    const queueContext: PlaybackQueueContext = libraryState.activePlaylistId
      ? {
          type: 'playlist',
          label:
            playlistState.playlists.find((playlist) => playlist.id === libraryState.activePlaylistId)?.name ||
            'Playlist',
          sourceId: libraryState.activePlaylistId
        }
      : {
          type: 'library',
          label:
            libraryState.projects.find((project) => project.id === libraryState.activeProjectId)?.name ||
            'All Tracks',
          sourceId: libraryState.activeProjectId
        }
    const queue = buildTrackQueue(libraryState.tracks, queueContext)
    const startIndex = queue.findIndex((item) => item.id === track.id)
    if (startIndex < 0) {
      return
    }

    playQueue(queue, startIndex, queueContext)
  }, [isCurrent, isPlaying, pause, playQueue, resume, track.id])

  const handleRegenerate = useCallback(() => {
    if (track.full_params_json) {
      loadFromTrack(track.full_params_json, track.generation_mode || undefined)
      setActiveSection('generate')
    }
  }, [track.full_params_json, track.generation_mode, loadFromTrack, setActiveSection])

  const handleCompare = useCallback((slot: 'A' | 'B') => {
    setCompareSlot(slot, track)
    setShowMenu(false)
  }, [track, setCompareSlot])

  const handleDragStart = useCallback((e: React.DragEvent) => {
    const trackIds = selectedTrackIds.has(track.id)
      ? Array.from(selectedTrackIds)
      : [track.id]
    setDraggedTrackIds(e, trackIds)
  }, [selectedTrackIds, track.id])

  const handleDoubleClick = useCallback(() => {
    useLibraryStore.getState().openTrackDetail(track.id)
  }, [track.id])

  const title = track.caption || 'Untitled'
  const bpmText = track.bpm ? `${Math.round(track.bpm)} BPM` : null
  const keyText = track.key_scale || null
  const durText = track.duration_seconds ? formatDuration(track.duration_seconds) : null

  return (
    <div
      draggable
      onDragStart={handleDragStart}
      onDoubleClick={handleDoubleClick}
      className={cn(
        'group flex h-16 items-center gap-3 border-b border-white/[0.03] px-3 transition-colors cursor-default',
        isSelected ? 'bg-[var(--color-violet)]/10' : 'hover:bg-white/[0.02]',
        isCurrent && isPlaying && 'bg-[var(--color-violet)]/5'
      )}
    >
      {/* Checkbox */}
      <input
        type="checkbox"
        checked={isSelected}
        onChange={() => toggleTrackSelection(track.id)}
        className="h-3.5 w-3.5 shrink-0 rounded accent-[var(--color-violet)] cursor-pointer"
      />

      {/* Play button */}
      <button
        onClick={handlePlay}
        className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-colors',
          isPlaying
            ? 'bg-[var(--color-violet)] text-white'
            : 'bg-white/5 text-[var(--color-text-muted)] group-hover:bg-white/10 group-hover:text-[var(--color-text-primary)]'
        )}
      >
        {isPlaying ? <Pause size={13} /> : <Play size={13} className="ml-0.5" />}
      </button>

      {/* Title + subtitle */}
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-medium text-[var(--color-text-primary)]">
          {title}
        </p>
        {track.lyrics && (
          <p className="truncate text-[10px] text-[var(--color-text-dim)]">
            {track.lyrics.slice(0, 60).replace(/\n/g, ' ')}
          </p>
        )}
      </div>

      {/* Metadata pills */}
      <div className="hidden lg:flex items-center gap-1.5 shrink-0">
        {bpmText && (
          <span className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] tabular-nums text-[var(--color-text-dim)]">
            {bpmText}
          </span>
        )}
        {keyText && (
          <span className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] text-[var(--color-text-dim)]">
            {keyText}
          </span>
        )}
        {durText && (
          <span className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] tabular-nums text-[var(--color-text-dim)]">
            {durText}
          </span>
        )}
      </div>

      {/* Rating */}
      <div className="hidden md:flex items-center gap-0.5 shrink-0">
        {[1, 2, 3, 4, 5].map((r) => (
          <button
            key={r}
            onClick={() => setRating(track.id, track.rating === r ? 0 : r)}
            className={cn(
              'transition-colors',
              (track.rating || 0) >= r
                ? 'text-amber-400'
                : 'text-white/10 hover:text-amber-400/50'
            )}
          >
            <Star size={11} fill={(track.rating || 0) >= r ? 'currentColor' : 'none'} />
          </button>
        ))}
      </div>

      {/* Favorite */}
      <button
        onClick={() => toggleFavorite(track.id)}
        className={cn(
          'shrink-0 transition-colors',
          track.is_favorite
            ? 'text-rose-400'
            : 'text-white/10 hover:text-rose-400/50'
        )}
      >
        <Heart size={13} fill={track.is_favorite ? 'currentColor' : 'none'} />
      </button>

      {/* Hover actions */}
      <div className="flex items-center gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={() => handleCompare('A')}
          className="flex h-6 w-6 items-center justify-center rounded text-[var(--color-text-dim)] hover:bg-white/5 hover:text-[var(--color-cyan)] transition-colors"
          title="Compare (Slot A)"
        >
          <GitCompareArrows size={12} />
        </button>

        {track.full_params_json && (
          <button
            onClick={handleRegenerate}
            className="flex h-6 w-6 items-center justify-center rounded text-[var(--color-text-dim)] hover:bg-white/5 hover:text-[var(--color-violet)] transition-colors"
            title="Regenerate with same params"
          >
            <RefreshCw size={12} />
          </button>
        )}

        {/* More menu */}
        <div className="relative">
          <button
            onClick={() => setShowMenu(!showMenu)}
            className="flex h-6 w-6 items-center justify-center rounded text-[var(--color-text-dim)] hover:bg-white/5 hover:text-[var(--color-text-muted)] transition-colors"
          >
            <MoreHorizontal size={12} />
          </button>
          {showMenu && (
            <div className="absolute right-0 top-full z-30 mt-1 w-40 rounded-lg border border-white/10 bg-[var(--color-bg-secondary)] py-1 shadow-xl">
              <button
                onClick={() => { handleCompare('A'); }}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-[var(--color-text-muted)] hover:bg-white/5"
              >
                <GitCompareArrows size={12} /> Compare as A
              </button>
              <button
                onClick={() => { handleCompare('B'); }}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-[var(--color-text-muted)] hover:bg-white/5"
              >
                <GitCompareArrows size={12} /> Compare as B
              </button>
              {track.full_params_json && (
                <button
                  onClick={handleRegenerate}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-[var(--color-text-muted)] hover:bg-white/5"
                >
                  <RefreshCw size={12} /> Regenerate
                </button>
              )}
              <button
                onClick={() => { handleDoubleClick(); setShowMenu(false) }}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-[var(--color-text-muted)] hover:bg-white/5"
              >
                <Music2 size={12} /> Edit Lyrics
              </button>
              <div className="my-1 border-t border-white/5" />
              <button
                onClick={() => { deleteTrack(track.id); setShowMenu(false) }}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-red-400 hover:bg-white/5"
              >
                <Trash2 size={12} /> Delete
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Date */}
      <span className="hidden xl:block text-[10px] text-[var(--color-text-dim)] tabular-nums w-16 text-right shrink-0">
        {new Date(track.created_at * 1000).toLocaleDateString('en-US', {
          month: 'short', day: 'numeric'
        })}
      </span>
    </div>
  )
})
