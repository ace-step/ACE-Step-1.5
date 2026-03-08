/**
 * KaraokePreview — Compact bar showing real-time lyric highlighting.
 *
 * Displays the current, previous, and next lyric lines during playback.
 * In word-level mode, highlights individual words as they pass.
 */

import { useMemo } from 'react'
import { cn } from '../../lib/utils'
import { useLyricsStore } from '../../stores/lyrics'
import { findActiveLine, findActiveWord } from '../../lib/lrc'

interface KaraokePreviewProps {
  /** Current playback time in seconds */
  currentTime: number
  /** Whether audio is playing */
  isPlaying: boolean
}

export function KaraokePreview({ currentTime, isPlaying }: KaraokePreviewProps) {
  const lines = useLyricsStore((s) => s.lines)
  const editMode = useLyricsStore((s) => s.editMode)

  const activeIdx = useMemo(() => findActiveLine(lines, currentTime), [lines, currentTime])

  if (lines.length === 0) return null

  const prevLine = activeIdx > 0 ? lines[activeIdx - 1] : null
  const currentLine = activeIdx >= 0 ? lines[activeIdx] : null
  const nextLine = activeIdx >= 0 && activeIdx < lines.length - 1
    ? lines[activeIdx + 1]
    : null

  // Word-level highlighting
  const activeWordIdx = currentLine?.words && editMode === 'word'
    ? findActiveWord(currentLine.words, currentTime)
    : -1

  return (
    <div className={cn(
      'flex flex-col items-center justify-center gap-0.5 px-3 py-2 border-t border-white/5 min-h-[60px] transition-opacity',
      isPlaying ? 'opacity-100' : 'opacity-60'
    )}>
      {/* Previous line (faded) */}
      <p className="text-[10px] text-[var(--color-text-dim)] truncate max-w-full h-4">
        {prevLine?.text || '\u00A0'}
      </p>

      {/* Current line (prominent) */}
      <div className="text-sm font-medium text-[var(--color-text-primary)] truncate max-w-full min-h-[20px]">
        {currentLine ? (
          currentLine.words && editMode === 'word' ? (
            // Word-level highlighting
            <span>
              {currentLine.words.map((word, wIdx) => (
                <span
                  key={wIdx}
                  className={cn(
                    'transition-colors duration-150',
                    wIdx <= activeWordIdx
                      ? 'text-[var(--color-violet)]'
                      : 'text-[var(--color-text-muted)]'
                  )}
                >
                  {word.text}{wIdx < currentLine.words!.length - 1 ? ' ' : ''}
                </span>
              ))}
            </span>
          ) : (
            <span className="text-[var(--color-violet)]">{currentLine.text}</span>
          )
        ) : (
          <span className="text-[var(--color-text-dim)]">♪</span>
        )}
      </div>

      {/* Next line (faded) */}
      <p className="text-[10px] text-[var(--color-text-dim)] truncate max-w-full h-4">
        {nextLine?.text || '\u00A0'}
      </p>
    </div>
  )
}
