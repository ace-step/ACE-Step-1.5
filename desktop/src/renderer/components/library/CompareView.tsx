import { useState, useCallback } from 'react'
import { X, Trophy, Link2, Link2Off } from 'lucide-react'
import { cn } from '../../lib/utils'
import { useLibraryStore } from '../../stores/library'
import { WaveformPlayer } from '../audio/WaveformPlayer'
import { getTrackAudioUrl } from '../../hooks/useTrackAudioUrl'

export function CompareView() {
  const {
    compareSlotA, compareSlotB, comparePanelOpen, compareSynced,
    toggleComparePanel, setCompareSynced, markWinner
  } = useLibraryStore()

  const [syncTime, setSyncTime] = useState<number | null>(null)
  const [activePlayer, setActivePlayer] = useState<'A' | 'B' | null>(null)

  const handleTimeUpdate = useCallback((player: 'A' | 'B', time: number) => {
    if (compareSynced && activePlayer === player) {
      setSyncTime(time)
    }
  }, [compareSynced, activePlayer])

  const handlePlayStateChange = useCallback((player: 'A' | 'B', playing: boolean) => {
    if (playing) {
      setActivePlayer(player)
    } else if (activePlayer === player) {
      setActivePlayer(null)
    }
  }, [activePlayer])

  if (!comparePanelOpen) return null

  return (
    <div className="border-t border-white/10 bg-[var(--color-bg-secondary)]">
      {/* Header */}
      <div className="flex items-center gap-3 border-b border-white/5 px-4 py-2">
        <span className="text-xs font-medium text-[var(--color-text-primary)]">
          A/B Compare
        </span>

        {/* Sync toggle */}
        <button
          onClick={() => setCompareSynced(!compareSynced)}
          className={cn(
            'flex items-center gap-1.5 rounded-md px-2 py-1 text-[10px] transition-colors',
            compareSynced
              ? 'bg-[var(--color-cyan)]/15 text-[var(--color-cyan)]'
              : 'text-[var(--color-text-dim)] hover:bg-white/5'
          )}
        >
          {compareSynced ? <Link2 size={11} /> : <Link2Off size={11} />}
          {compareSynced ? 'Synced' : 'Independent'}
        </button>

        <div className="flex-1" />

        <button
          onClick={toggleComparePanel}
          className="flex h-6 w-6 items-center justify-center rounded text-[var(--color-text-dim)] hover:bg-white/5 hover:text-[var(--color-text-muted)] transition-colors"
        >
          <X size={14} />
        </button>
      </div>

      {/* Comparison slots */}
      <div className="grid grid-cols-2 gap-4 p-4">
        {/* Slot A */}
        <CompareSlot
          label="A"
          track={compareSlotA}
          syncTime={compareSynced && activePlayer === 'B' ? syncTime : null}
          onTimeUpdate={(t) => handleTimeUpdate('A', t)}
          onPlayStateChange={(p) => handlePlayStateChange('A', p)}
          onMarkWinner={() => markWinner('A')}
          hasOpponent={!!compareSlotB}
        />

        {/* Slot B */}
        <CompareSlot
          label="B"
          track={compareSlotB}
          syncTime={compareSynced && activePlayer === 'A' ? syncTime : null}
          onTimeUpdate={(t) => handleTimeUpdate('B', t)}
          onPlayStateChange={(p) => handlePlayStateChange('B', p)}
          onMarkWinner={() => markWinner('B')}
          hasOpponent={!!compareSlotA}
        />
      </div>
    </div>
  )
}

interface CompareSlotProps {
  label: string
  track: ReturnType<typeof useLibraryStore.getState>['compareSlotA']
  syncTime: number | null
  onTimeUpdate: (time: number) => void
  onPlayStateChange: (playing: boolean) => void
  onMarkWinner: () => void
  hasOpponent: boolean
}

function CompareSlot({
  label, track, syncTime,
  onTimeUpdate, onPlayStateChange, onMarkWinner, hasOpponent
}: CompareSlotProps) {
  if (!track) {
    return (
      <div className="flex h-32 items-center justify-center rounded-lg border border-dashed border-white/10 bg-white/[0.01]">
        <p className="text-xs text-[var(--color-text-dim)]">
          Drag a track here for Slot {label}
        </p>
      </div>
    )
  }

  const audioUrl = getTrackAudioUrl(track.file_path)
  const title = track.caption || 'Untitled'

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-white/5 bg-white/[0.02] p-3">
      {/* Track info */}
      <div className="flex items-center gap-2">
        <span className="flex h-5 w-5 items-center justify-center rounded bg-[var(--color-violet)]/20 text-[10px] font-bold text-[var(--color-violet)]">
          {label}
        </span>
        <p className="flex-1 truncate text-xs font-medium text-[var(--color-text-primary)]">
          {title}
        </p>
        {/* Metadata */}
        <div className="flex items-center gap-1">
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
        </div>
      </div>

      {/* Waveform */}
      <WaveformPlayer
        audioUrl={audioUrl}
        trackId={track.id}
        height={64}
        enableRegions
        syncTime={syncTime}
        onTimeUpdate={onTimeUpdate}
        onPlayStateChange={onPlayStateChange}
      />

      {/* Winner button */}
      {hasOpponent && (
        <button
          onClick={onMarkWinner}
          className="flex h-7 items-center justify-center gap-1.5 rounded-md bg-amber-500/10 text-xs text-amber-400 hover:bg-amber-500/20 transition-colors"
        >
          <Trophy size={12} />
          Winner
        </button>
      )}
    </div>
  )
}
