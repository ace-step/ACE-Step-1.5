/**
 * LyricsTimeline — Renders lyric markers as wavesurfer regions on the waveform.
 *
 * Each LrcLine becomes a draggable region. Dragging a region updates the line's
 * start time in the lyrics store.
 */

import { useEffect, useRef } from 'react'
import type { Region } from 'wavesurfer.js/dist/plugins/regions.js'
import type { WaveformPlayerHandle } from '../audio/WaveformPlayer'
import { useLyricsStore } from '../../stores/lyrics'
import type { LrcLine } from '../../lib/lrc'

interface LyricsTimelineProps {
  /** Ref to the WaveformPlayer imperative handle */
  playerRef: React.RefObject<WaveformPlayerHandle | null>
  /** Audio duration in seconds */
  duration: number
}

/** Violet tint for regions */
const REGION_COLOR = 'rgba(124, 58, 237, 0.10)'
const REGION_COLOR_ACTIVE = 'rgba(124, 58, 237, 0.25)'

export function LyricsTimeline({ playerRef, duration }: LyricsTimelineProps) {
  const lines = useLyricsStore((s) => s.lines)
  const updateLineTime = useLyricsStore((s) => s.updateLineTime)
  const regionsMapRef = useRef<Map<string, Region>>(new Map())
  const updatingRef = useRef(false)

  // Sync regions whenever lines change
  useEffect(() => {
    const regions = playerRef.current?.getRegions()
    if (!regions || !duration || duration <= 0) return

    // Prevent re-entrance from region update events
    updatingRef.current = true

    // Clear existing lyric regions
    const existing = regionsMapRef.current
    existing.forEach((r) => {
      try { r.remove() } catch { /* region may already be gone */ }
    })
    existing.clear()

    // Add a region for each line
    lines.forEach((line, idx) => {
      const nextTime = idx < lines.length - 1 ? lines[idx + 1].time : duration
      const end = Math.min(nextTime, duration)
      const regionId = `lrc-${idx}`

      try {
        const region = regions.addRegion({
          id: regionId,
          start: line.time,
          end: Math.max(end, line.time + 0.1), // minimum 100ms width
          content: line.text.length > 30 ? line.text.slice(0, 30) + '…' : line.text,
          color: REGION_COLOR,
          drag: true,
          resize: false
        })

        existing.set(regionId, region)
      } catch {
        /* wavesurfer may not be ready */
      }
    })

    updatingRef.current = false

    // Listen for region drag updates
    const handleUpdate = (region: Region) => {
      if (updatingRef.current) return
      const match = region.id.match(/^lrc-(\d+)$/)
      if (!match) return
      const idx = parseInt(match[1], 10)
      if (idx >= 0 && idx < lines.length) {
        updateLineTime(idx, region.start)
      }
    }

    regions.on('region-updated', handleUpdate)

    return () => {
      // Unsubscribe — wavesurfer regions plugin doesn't have .off, but
      // the regions instance is recreated when wavesurfer reinitializes
    }
  }, [lines, duration, playerRef, updateLineTime])

  // This component doesn't render visible DOM — it only manages wavesurfer regions
  return null
}
