/**
 * LyricsEditor — Scrollable list of lyric lines with inline editing.
 *
 * Each row shows: timestamp badge [mm:ss.xx] + editable text input.
 * Active line (matching playback time) is highlighted.
 * Supports tap-to-sync mode (Space/Enter stamps time on next line).
 */

import { useRef, useEffect, useCallback } from 'react'
import { Plus, X } from 'lucide-react'
import { cn } from '../../lib/utils'
import { useLyricsStore } from '../../stores/lyrics'
import { findActiveLine } from '../../lib/lrc'
import type { WaveformPlayerHandle } from '../audio/WaveformPlayer'

interface LyricsEditorProps {
  /** Current playback time in seconds */
  currentTime: number
  /** Ref to waveform player for seeking */
  playerRef: React.RefObject<WaveformPlayerHandle | null>
}

/** Format seconds to mm:ss.xx display */
function fmtTime(seconds: number): string {
  const s = Math.max(0, seconds)
  const min = Math.floor(s / 60)
  const sec = s - min * 60
  return `${String(min).padStart(2, '0')}:${sec.toFixed(2).padStart(5, '0')}`
}

export function LyricsEditor({ currentTime, playerRef }: LyricsEditorProps) {
  const lines = useLyricsStore((s) => s.lines)
  const updateLineTime = useLyricsStore((s) => s.updateLineTime)
  const updateLineText = useLyricsStore((s) => s.updateLineText)
  const insertLine = useLyricsStore((s) => s.insertLine)
  const deleteLine = useLyricsStore((s) => s.deleteLine)
  const tapSyncActive = useLyricsStore((s) => s.tapSyncActive)
  const tapSyncIndex = useLyricsStore((s) => s.tapSyncIndex)
  const tapLine = useLyricsStore((s) => s.tapLine)

  const listRef = useRef<HTMLDivElement>(null)
  const activeIdx = findActiveLine(lines, currentTime)

  // Auto-scroll to active line during playback
  useEffect(() => {
    if (activeIdx < 0 || !listRef.current) return
    const rows = listRef.current.querySelectorAll('[data-line-idx]')
    const row = rows[activeIdx] as HTMLElement | undefined
    if (row) {
      row.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }
  }, [activeIdx])

  // Tap-to-sync keyboard handler
  const handleTapKey = useCallback(
    (e: React.KeyboardEvent) => {
      if (!tapSyncActive) return
      if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault()
        const time = playerRef.current?.getCurrentTime() || 0
        tapLine(time)
      }
    },
    [tapSyncActive, tapLine, playerRef]
  )

  // Seek to line's timestamp
  const handleSeek = useCallback(
    (time: number) => {
      playerRef.current?.seekTo(time)
    },
    [playerRef]
  )

  if (lines.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center px-4 py-8 text-center">
        <p className="text-xs text-[var(--color-text-dim)]">
          No lyrics synced yet. Click <strong>Sync Lyrics</strong> to generate timestamps,
          or <strong>Import</strong> an .lrc file.
        </p>
      </div>
    )
  }

  return (
    <div
      ref={listRef}
      className="flex-1 overflow-y-auto px-2 py-1"
      onKeyDown={handleTapKey}
      tabIndex={tapSyncActive ? 0 : undefined}
    >
      {lines.map((line, idx) => {
        const isActive = idx === activeIdx
        const isTapTarget = tapSyncActive && idx === tapSyncIndex

        return (
          <div
            key={idx}
            data-line-idx={idx}
            className={cn(
              'group flex items-start gap-1.5 rounded px-1.5 py-1 transition-colors',
              isActive && 'bg-[var(--color-violet)]/10 border-l-2 border-[var(--color-violet)]',
              isTapTarget && 'bg-[var(--color-cyan)]/10 border-l-2 border-[var(--color-cyan)]',
              !isActive && !isTapTarget && 'border-l-2 border-transparent hover:bg-white/[0.03]'
            )}
          >
            {/* Timestamp badge */}
            <button
              onClick={() => handleSeek(line.time)}
              className="shrink-0 rounded bg-white/5 px-1.5 py-0.5 font-mono text-[10px] text-[var(--color-text-dim)] hover:bg-white/10 hover:text-[var(--color-text-muted)] transition-colors mt-0.5"
              title="Click to seek"
            >
              {fmtTime(line.time)}
            </button>

            {/* Editable text */}
            <input
              type="text"
              value={line.text}
              onChange={(e) => updateLineText(idx, e.target.value)}
              className="flex-1 bg-transparent text-xs text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-dim)] min-w-0"
              placeholder="Lyric text..."
            />

            {/* Action buttons (visible on hover) */}
            <div className="flex shrink-0 items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
              <button
                onClick={() => insertLine(idx, { time: line.time + 1, text: '' })}
                className="flex h-5 w-5 items-center justify-center rounded text-[var(--color-text-dim)] hover:bg-white/5 hover:text-[var(--color-text-muted)]"
                title="Insert line after"
              >
                <Plus size={11} />
              </button>
              <button
                onClick={() => deleteLine(idx)}
                className="flex h-5 w-5 items-center justify-center rounded text-[var(--color-text-dim)] hover:bg-red-500/20 hover:text-red-400"
                title="Delete line"
              >
                <X size={11} />
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
