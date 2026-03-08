import { useMemo } from 'react'
import { Play, Pause, Download, Library, GitCompareArrows } from 'lucide-react'
import type { GenerationResult } from '../../stores/generation'
import { useAudioStore } from '../../stores/audio'
import { useGenerationStore } from '../../stores/generation'
import { useLibraryStore } from '../../stores/library'
import { useUIStore } from '../../stores/ui'
import { cn } from '../../lib/utils'
import { formatDuration } from '../../lib/utils'
import { buildGenerationQueue } from '../../lib/playback-queue'

interface ResultCardProps {
  result: GenerationResult
  index: number
}

export function ResultCard({ result, index }: ResultCardProps) {
  const currentTrackId = useAudioStore((s) => s.currentTrackId)
  const currentTime = useAudioStore((s) => s.currentTime)
  const duration = useAudioStore((s) => s.duration)
  const isPlaying = useAudioStore((s) => s.isPlaying)
  const pause = useAudioStore((s) => s.pause)
  const resume = useAudioStore((s) => s.resume)
  const seek = useAudioStore((s) => s.seek)
  const playQueue = useAudioStore((s) => s.playQueue)
  const results = useGenerationStore((s) => s.results)

  const queue = useMemo(() => buildGenerationQueue(results), [results])
  const queueId = `generation:${index}`
  const isCurrent = currentTrackId === queueId

  const togglePlay = () => {
    if (isCurrent) {
      if (isPlaying) {
        pause()
      } else {
        resume()
      }
      return
    }

    playQueue(queue, index, { type: 'generation', label: 'Generation Results' })
  }

  const handleDownload = async () => {
    try {
      const savePath = await window.aceStep.fs.saveDialog({
        defaultPath: `track-${index + 1}.mp3`,
        filters: [{ name: 'Audio', extensions: ['mp3', 'wav', 'flac'] }]
      })
      if (savePath) {
        const normalizedPath = savePath.replace(/\\/g, '/')
        const lastSlash = normalizedPath.lastIndexOf('/')
        const targetDir = lastSlash >= 0 ? normalizedPath.slice(0, lastSlash) : '.'
        const filename =
          lastSlash >= 0 ? normalizedPath.slice(lastSlash + 1) : normalizedPath

        await window.aceStep.fs.saveAudio(result.filePath, targetDir, filename)
      }
    } catch (err) {
      console.error('Save failed:', err)
    }
  }

  const handleSeek = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!isCurrent || !duration) return
    const rect = e.currentTarget.getBoundingClientRect()
    const pct = (e.clientX - rect.left) / rect.width
    seek(pct * duration)
  }

  const visibleCurrentTime = isCurrent ? currentTime : 0
  const visibleDuration = isCurrent ? duration : (result.metas?.duration || 0)
  const progress = visibleDuration > 0 ? visibleCurrentTime / visibleDuration : 0

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-white/5 bg-white/[0.02] p-3 hover:border-white/10 transition-colors">
      {/* Track info */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-medium text-[var(--color-text-primary)]">
            Track {index + 1}
          </p>
          {result.metas?.genres && (
            <p className="truncate text-[10px] text-[var(--color-text-muted)]">
              {result.metas.genres}
            </p>
          )}
        </div>
        {result.metas?.bpm && (
          <span className="shrink-0 rounded bg-white/5 px-1.5 py-0.5 text-[10px] text-[var(--color-text-muted)]">
            {Math.round(result.metas.bpm)} BPM
          </span>
        )}
      </div>

      {/* Waveform placeholder / progress bar */}
      <div
        className="relative h-8 cursor-pointer rounded bg-white/5 overflow-hidden"
        onClick={handleSeek}
      >
        <div
          className="absolute inset-y-0 left-0 bg-[var(--color-violet)]/20"
          style={{ width: `${progress * 100}%` }}
        />
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-[var(--color-violet)]"
          style={{ left: `${progress * 100}%` }}
        />
      </div>

      {/* Controls */}
      <div className="flex items-center gap-2">
        <button
          onClick={togglePlay}
          className={cn(
            'flex h-8 w-8 items-center justify-center rounded-full transition-colors',
            isCurrent && isPlaying
              ? 'bg-[var(--color-violet)] text-white'
              : 'bg-white/10 text-[var(--color-text-primary)] hover:bg-white/15'
          )}
        >
          {isCurrent && isPlaying ? <Pause size={14} /> : <Play size={14} className="ml-0.5" />}
        </button>

        <span className="flex-1 text-[10px] tabular-nums text-[var(--color-text-muted)]">
          {formatDuration(visibleCurrentTime)} / {formatDuration(visibleDuration)}
        </span>

        <button
          onClick={handleDownload}
          className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--color-text-muted)] hover:bg-white/5 hover:text-[var(--color-text-primary)] transition-colors"
          title="Save to file"
        >
          <Download size={14} />
        </button>

        <button
          onClick={() => {
            const { setCompareSlot, compareSlotA } = useLibraryStore.getState()
            // Build a minimal TrackRecord-like object for comparison
            const fakeTrack = {
              id: `gen-${index}`,
              file_path: result.filePath,
              caption: result.prompt || `Track ${index + 1}`,
              bpm: result.metas?.bpm || null,
              key_scale: result.metas?.keyscale || null,
              duration_seconds: result.metas?.duration || null,
              is_favorite: 0,
              rating: null
            } as any
            setCompareSlot(compareSlotA ? 'B' : 'A', fakeTrack)
          }}
          className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--color-text-muted)] hover:bg-white/5 hover:text-[var(--color-cyan)] transition-colors"
          title="Compare"
        >
          <GitCompareArrows size={14} />
        </button>

        <button
          onClick={() => {
            useUIStore.getState().setActiveSection('library')
          }}
          className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--color-text-muted)] hover:bg-white/5 hover:text-[var(--color-violet)] transition-colors"
          title="Go to Library"
        >
          <Library size={14} />
        </button>
      </div>
    </div>
  )
}
