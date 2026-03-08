import { Pause, Play, Repeat, Shuffle, SkipBack, SkipForward, Volume2 } from 'lucide-react'

import { cn, formatDuration } from '../../lib/utils'
import { useAudioStore } from '../../stores/audio'

export function GlobalPlayer() {
  const currentTrackUrl = useAudioStore((s) => s.currentTrackUrl)
  const currentTitle = useAudioStore((s) => s.currentTitle)
  const currentSubtitle = useAudioStore((s) => s.currentSubtitle)
  const isPlaying = useAudioStore((s) => s.isPlaying)
  const currentTime = useAudioStore((s) => s.currentTime)
  const duration = useAudioStore((s) => s.duration)
  const volume = useAudioStore((s) => s.volume)
  const queue = useAudioStore((s) => s.queue)
  const currentIndex = useAudioStore((s) => s.currentIndex)
  const shuffle = useAudioStore((s) => s.shuffle)
  const repeatMode = useAudioStore((s) => s.repeatMode)
  const togglePlayPause = useAudioStore((s) => s.togglePlayPause)
  const playNext = useAudioStore((s) => s.playNext)
  const playPrevious = useAudioStore((s) => s.playPrevious)
  const seek = useAudioStore((s) => s.seek)
  const setVolume = useAudioStore((s) => s.setVolume)
  const setShuffle = useAudioStore((s) => s.setShuffle)
  const cycleRepeatMode = useAudioStore((s) => s.cycleRepeatMode)

  if (!currentTrackUrl) return null

  return (
    <div className="border-t border-white/5 bg-[var(--color-bg-primary)]/95 px-4 py-2 backdrop-blur">
      <div className="flex items-center gap-4">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-[var(--color-text-primary)]">
            {currentTitle || 'Now Playing'}
          </p>
          <p className="truncate text-[11px] text-[var(--color-text-dim)]">
            {currentSubtitle || 'Playback Queue'}
          </p>
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={() => setShuffle(!shuffle)}
            className={cn(
              'flex h-8 w-8 items-center justify-center rounded-md transition-colors',
              shuffle
                ? 'bg-[var(--color-cyan)]/15 text-[var(--color-cyan)]'
                : 'text-[var(--color-text-dim)] hover:bg-white/5 hover:text-[var(--color-text-primary)]'
            )}
            title="Shuffle queue"
          >
            <Shuffle size={14} />
          </button>
          <button
            onClick={playPrevious}
            className="flex h-8 w-8 items-center justify-center rounded-md text-[var(--color-text-dim)] hover:bg-white/5 hover:text-[var(--color-text-primary)] transition-colors"
            title="Previous"
          >
            <SkipBack size={15} />
          </button>
          <button
            onClick={togglePlayPause}
            className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--color-violet)]/20 text-[var(--color-violet)] hover:bg-[var(--color-violet)]/30 transition-colors"
            title={isPlaying ? 'Pause' : 'Play'}
          >
            {isPlaying ? <Pause size={18} /> : <Play size={18} className="ml-0.5" />}
          </button>
          <button
            onClick={playNext}
            className="flex h-8 w-8 items-center justify-center rounded-md text-[var(--color-text-dim)] hover:bg-white/5 hover:text-[var(--color-text-primary)] transition-colors"
            title="Next"
          >
            <SkipForward size={15} />
          </button>
          <button
            onClick={cycleRepeatMode}
            className={cn(
              'flex h-8 min-w-[42px] items-center justify-center gap-1 rounded-md px-2 transition-colors',
              repeatMode !== 'off'
                ? 'bg-[var(--color-violet)]/15 text-[var(--color-violet)]'
                : 'text-[var(--color-text-dim)] hover:bg-white/5 hover:text-[var(--color-text-primary)]'
            )}
            title="Cycle repeat mode"
          >
            <Repeat size={14} />
            <span className="text-[10px] uppercase">{repeatMode}</span>
          </button>
        </div>

        <div className="flex min-w-[240px] flex-1 items-center gap-3">
          <span className="w-12 text-right text-[11px] tabular-nums text-[var(--color-text-dim)]">
            {formatDuration(currentTime)}
          </span>
          <input
            type="range"
            min={0}
            max={Math.max(duration, 1)}
            step={0.1}
            value={Math.min(currentTime, Math.max(duration, 1))}
            onChange={(event) => seek(Number(event.target.value))}
            className="h-1.5 flex-1 accent-[var(--color-violet)]"
          />
          <span className="w-12 text-[11px] tabular-nums text-[var(--color-text-dim)]">
            {formatDuration(duration)}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[11px] text-[var(--color-text-dim)]">
            {queue.length > 0 ? `${currentIndex + 1}/${queue.length}` : '0/0'}
          </span>
          <Volume2 size={14} className="text-[var(--color-text-dim)]" />
          <input
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={volume}
            onChange={(event) => setVolume(Number(event.target.value))}
            className="w-24 accent-[var(--color-cyan)]"
          />
        </div>
      </div>
    </div>
  )
}
