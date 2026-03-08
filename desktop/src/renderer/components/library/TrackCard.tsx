import { memo, useCallback } from 'react'
import {
  Play, Pause, Heart, Star,
  GitCompareArrows, RefreshCw
} from 'lucide-react'
import { cn, formatDuration } from '../../lib/utils'
import { useLibraryStore, type TrackRecord } from '../../stores/library'
import { useGenerationStore } from '../../stores/generation'
import { useUIStore } from '../../stores/ui'
import { useAudioStore } from '../../stores/audio'
import { WaveformPlayer } from '../audio/WaveformPlayer'
import { setDraggedTrackIds } from '../../lib/track-drag'
import { buildTrackQueue, type PlaybackQueueContext } from '../../lib/playback-queue'
import { usePlaylistsStore } from '../../stores/playlists'

interface TrackCardProps {
  track: TrackRecord
  isSelected: boolean
  isPlaying: boolean
}

export const TrackCard = memo(function TrackCard({ track, isSelected, isPlaying }: TrackCardProps) {
  const { toggleTrackSelection, toggleFavorite, setRating, setCompareSlot, selectedTrackIds } = useLibraryStore()
  const currentTrackId = useAudioStore((s) => s.currentTrackId)
  const playQueue = useAudioStore((s) => s.playQueue)
  const pause = useAudioStore((s) => s.pause)
  const resume = useAudioStore((s) => s.resume)
  const loadFromTrack = useGenerationStore((s) => s.loadFromTrack)
  const setActiveSection = useUIStore((s) => s.setActiveSection)

  const isCurrent = currentTrackId === track.id
  const audioUrl = buildTrackQueue(
    [track],
    { type: 'library', label: 'Library' }
  )[0]?.audioUrl || ''

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

  const handleDragStart = useCallback((e: React.DragEvent) => {
    const trackIds = selectedTrackIds.has(track.id)
      ? Array.from(selectedTrackIds)
      : [track.id]
    setDraggedTrackIds(e, trackIds)
  }, [selectedTrackIds, track.id])

  const title = track.caption || 'Untitled'

  return (
    <div
      draggable
      onDragStart={handleDragStart}
      className={cn(
        'group flex flex-col rounded-xl border transition-colors overflow-hidden',
        isSelected
          ? 'border-[var(--color-violet)]/40 bg-[var(--color-violet)]/10'
          : 'border-white/5 bg-white/[0.02] hover:border-white/10'
      )}
    >
      {/* Waveform area */}
      <div className="relative px-2.5 pt-2.5">
        <WaveformPlayer
          audioUrl={audioUrl}
          trackId={track.id}
          height={56}
          compact
        />

        {/* Select checkbox overlay */}
        <input
          type="checkbox"
          checked={isSelected}
          onChange={() => toggleTrackSelection(track.id)}
          className="absolute left-2 top-2 h-3.5 w-3.5 rounded accent-[var(--color-violet)] cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity"
        />
      </div>

      {/* Track info */}
      <div className="flex flex-col gap-1.5 p-2.5 pt-2">
        <p className="truncate text-xs font-medium text-[var(--color-text-primary)]" title={title}>
          {title}
        </p>

        {/* Metadata pills */}
        <div className="flex flex-wrap gap-1">
          {track.bpm && (
            <span className="rounded bg-white/5 px-1.5 py-0.5 text-[9px] tabular-nums text-[var(--color-text-dim)]">
              {Math.round(track.bpm)} BPM
            </span>
          )}
          {track.key_scale && (
            <span className="rounded bg-white/5 px-1.5 py-0.5 text-[9px] text-[var(--color-text-dim)]">
              {track.key_scale}
            </span>
          )}
          {track.duration_seconds && (
            <span className="rounded bg-white/5 px-1.5 py-0.5 text-[9px] tabular-nums text-[var(--color-text-dim)]">
              {formatDuration(track.duration_seconds)}
            </span>
          )}
        </div>

        {/* Rating + Favorite */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-0.5">
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
                <Star size={10} fill={(track.rating || 0) >= r ? 'currentColor' : 'none'} />
              </button>
            ))}
          </div>

          <button
            onClick={() => toggleFavorite(track.id)}
            className={cn(
              'transition-colors',
              track.is_favorite
                ? 'text-rose-400'
                : 'text-white/10 hover:text-rose-400/50'
            )}
          >
            <Heart size={12} fill={track.is_favorite ? 'currentColor' : 'none'} />
          </button>
        </div>

        {/* Action buttons (visible on hover) */}
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={() => setCompareSlot('A', track)}
            className="flex h-6 flex-1 items-center justify-center gap-1 rounded bg-white/5 text-[10px] text-[var(--color-text-dim)] hover:bg-[var(--color-cyan)]/10 hover:text-[var(--color-cyan)] transition-colors"
            title="Compare"
          >
            <GitCompareArrows size={10} />
            <span>Compare</span>
          </button>

          {track.full_params_json && (
            <button
              onClick={handleRegenerate}
              className="flex h-6 flex-1 items-center justify-center gap-1 rounded bg-white/5 text-[10px] text-[var(--color-text-dim)] hover:bg-[var(--color-violet)]/10 hover:text-[var(--color-violet)] transition-colors"
              title="Regenerate"
            >
              <RefreshCw size={10} />
              <span>Regen</span>
            </button>
          )}
        </div>
      </div>
    </div>
  )
})
