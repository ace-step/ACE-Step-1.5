import { useRef, useEffect, useState, useCallback, memo, forwardRef, useImperativeHandle } from 'react'
import WaveSurfer from 'wavesurfer.js'
import RegionsPlugin, { type Region } from 'wavesurfer.js/dist/plugins/regions.js'
import { cn, formatDuration } from '../../lib/utils'
import { useAudioStore } from '../../stores/audio'
import {
  Play, Pause, ZoomIn, ZoomOut, Activity,
  Repeat, SkipBack, SkipForward
} from 'lucide-react'

export interface WaveformPlayerProps {
  /** Audio URL (ace-audio:// or http://) */
  audioUrl: string
  /** Unique key to force re-render on track change */
  trackId?: string
  /** Height in pixels */
  height?: number
  /** Show spectrogram overlay (TODO: enable when spectrogram plugin is wired) */
  showSpectrogram?: boolean
  /** Enable region markers for A/B looping */
  enableRegions?: boolean
  /** External sync: when set, player seeks to this time */
  syncTime?: number | null
  /** Callback when currentTime changes (for sync) */
  onTimeUpdate?: (time: number) => void
  /** Callback when play state changes */
  onPlayStateChange?: (playing: boolean) => void
  /** Callback when duration is known */
  onReady?: (duration: number) => void
  /** CSS class for container */
  className?: string
  /** Compact mode (reduced controls) for grid view */
  compact?: boolean
}

/** Imperative handle exposed via ref */
export interface WaveformPlayerHandle {
  getWaveSurfer: () => WaveSurfer | null
  getRegions: () => RegionsPlugin | null
  getCurrentTime: () => number
  getDuration: () => number
  seekTo: (time: number) => void
  playPause: () => void
}

export const WaveformPlayer = memo(forwardRef<WaveformPlayerHandle, WaveformPlayerProps>(function WaveformPlayer({
  audioUrl,
  trackId,
  height = 80,
  showSpectrogram = false,
  enableRegions = false,
  syncTime = null,
  onTimeUpdate,
  onPlayStateChange,
  onReady,
  className,
  compact = false
}, ref) {
  const containerRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WaveSurfer | null>(null)
  const regionsRef = useRef<RegionsPlugin | null>(null)
  const isPlayingRef = useRef(false)
  const syncingRef = useRef(false)

  const [isPlaying, setIsPlaying] = useState(false)
  const [duration, setDuration] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)
  const [zoom, setZoom] = useState(1)
  const [isReady, setIsReady] = useState(false)
  const [loopActive, setLoopActive] = useState(false)
  const [loopRegion, setLoopRegion] = useState<{ start: number; end: number } | null>(null)

  const volume = useAudioStore((s) => s.volume)

  // Initialize wavesurfer
  useEffect(() => {
    if (!containerRef.current || !audioUrl) return

    const plugins: any[] = []

    if (enableRegions) {
      const regions = RegionsPlugin.create()
      regionsRef.current = regions
      plugins.push(regions)
    }

    const ws = WaveSurfer.create({
      container: containerRef.current,
      height,
      waveColor: 'rgba(124, 58, 237, 0.25)',
      progressColor: '#7c3aed',
      cursorColor: '#06b6d4',
      cursorWidth: 2,
      barWidth: 2,
      barGap: 1,
      barRadius: 2,
      normalize: true,
      plugins
    })

    ws.load(audioUrl)

    ws.on('ready', () => {
      const dur = ws.getDuration()
      setDuration(dur)
      setIsReady(true)
      ws.setVolume(volume)
      onReady?.(dur)
    })

    ws.on('timeupdate', (time: number) => {
      setCurrentTime(time)
      if (isPlayingRef.current && !syncingRef.current) {
        onTimeUpdate?.(time)
      }

      // Loop region enforcement
      if (loopActive && loopRegion && time >= loopRegion.end) {
        ws.setTime(loopRegion.start)
      }
    })

    ws.on('play', () => {
      isPlayingRef.current = true
      setIsPlaying(true)
      onPlayStateChange?.(true)
    })

    ws.on('pause', () => {
      isPlayingRef.current = false
      setIsPlaying(false)
      onPlayStateChange?.(false)
    })

    ws.on('finish', () => {
      isPlayingRef.current = false
      setIsPlaying(false)
      onPlayStateChange?.(false)
    })

    // Handle region creation for A/B looping
    if (enableRegions && regionsRef.current) {
      regionsRef.current.on('region-created', (region: Region) => {
        setLoopRegion({ start: region.start, end: region.end })
      })
      regionsRef.current.on('region-updated', (region: Region) => {
        setLoopRegion({ start: region.start, end: region.end })
      })
    }

    wsRef.current = ws

    return () => {
      ws.destroy()
      wsRef.current = null
      regionsRef.current = null
      setIsReady(false)
      setIsPlaying(false)
      setCurrentTime(0)
      setDuration(0)
    }
  }, [audioUrl, trackId, enableRegions])

  // Sync volume from global store
  useEffect(() => {
    if (wsRef.current && isReady) {
      wsRef.current.setVolume(volume)
    }
  }, [volume, isReady])

  // Expose imperative handle for parent components (e.g. LyricsTimeline)
  useImperativeHandle(ref, () => ({
    getWaveSurfer: () => wsRef.current,
    getRegions: () => regionsRef.current,
    getCurrentTime: () => wsRef.current?.getCurrentTime() || 0,
    getDuration: () => wsRef.current?.getDuration() || 0,
    seekTo: (time: number) => wsRef.current?.setTime(time),
    playPause: () => wsRef.current?.playPause()
  }), [isReady])

  // External sync (for A/B comparison)
  useEffect(() => {
    if (syncTime != null && wsRef.current && isReady && !isPlayingRef.current) {
      syncingRef.current = true
      wsRef.current.setTime(syncTime)
      requestAnimationFrame(() => { syncingRef.current = false })
    }
  }, [syncTime, isReady])

  // Zoom
  useEffect(() => {
    if (wsRef.current && isReady) {
      wsRef.current.zoom(zoom * 50)
    }
  }, [zoom, isReady])

  const togglePlay = useCallback(() => {
    wsRef.current?.playPause()
  }, [])

  const skipBack = useCallback(() => {
    if (wsRef.current) {
      const newTime = Math.max(0, (wsRef.current.getCurrentTime() || 0) - 5)
      wsRef.current.setTime(newTime)
    }
  }, [])

  const skipForward = useCallback(() => {
    if (wsRef.current) {
      const dur = wsRef.current.getDuration() || 0
      const newTime = Math.min(dur, (wsRef.current.getCurrentTime() || 0) + 5)
      wsRef.current.setTime(newTime)
    }
  }, [])

  const handleZoomIn = useCallback(() => setZoom((z) => Math.min(z * 1.5, 20)), [])
  const handleZoomOut = useCallback(() => setZoom((z) => Math.max(z / 1.5, 1)), [])

  const toggleLoop = useCallback(() => {
    if (!enableRegions || !regionsRef.current || !wsRef.current) return
    if (loopActive) {
      setLoopActive(false)
      setLoopRegion(null)
      regionsRef.current.clearRegions()
    } else {
      // Create a default loop region (25%-75% of duration)
      const dur = wsRef.current.getDuration()
      const region = regionsRef.current.addRegion({
        start: dur * 0.25,
        end: dur * 0.75,
        color: 'rgba(6, 182, 212, 0.15)',
        drag: true,
        resize: true
      })
      setLoopRegion({ start: region.start, end: region.end })
      setLoopActive(true)
    }
  }, [enableRegions, loopActive])

  // Compact mode: minimal player
  if (compact) {
    return (
      <div className={cn('flex flex-col gap-1', className)}>
        <div
          ref={containerRef}
          className="w-full rounded bg-white/[0.02] cursor-pointer"
        />
        <div className="flex items-center gap-2">
          <button
            onClick={togglePlay}
            className="flex h-6 w-6 items-center justify-center rounded text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
          >
            {isPlaying ? <Pause size={12} /> : <Play size={12} />}
          </button>
          <span className="text-[10px] font-mono text-[var(--color-text-dim)]">
            {formatDuration(currentTime)} / {formatDuration(duration)}
          </span>
        </div>
      </div>
    )
  }

  // Full mode
  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      {/* Waveform container */}
      <div
        ref={containerRef}
        className="w-full rounded-lg bg-white/[0.02] overflow-hidden cursor-pointer"
      />

      {/* Controls bar */}
      <div className="flex items-center gap-1.5">
        {/* Transport */}
        <button
          onClick={skipBack}
          className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--color-text-muted)] hover:bg-white/5 hover:text-[var(--color-text-primary)] transition-colors"
          title="Back 5s"
        >
          <SkipBack size={14} />
        </button>
        <button
          onClick={togglePlay}
          className="flex h-8 w-8 items-center justify-center rounded-md bg-[var(--color-violet)]/20 text-[var(--color-violet)] hover:bg-[var(--color-violet)]/30 transition-colors"
          title={isPlaying ? 'Pause' : 'Play'}
        >
          {isPlaying ? <Pause size={16} /> : <Play size={16} />}
        </button>
        <button
          onClick={skipForward}
          className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--color-text-muted)] hover:bg-white/5 hover:text-[var(--color-text-primary)] transition-colors"
          title="Forward 5s"
        >
          <SkipForward size={14} />
        </button>

        {/* Time display */}
        <span className="mx-1 text-xs font-mono text-[var(--color-text-muted)] min-w-[90px]">
          {formatDuration(currentTime)} / {formatDuration(duration)}
        </span>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Zoom controls */}
        <button
          onClick={handleZoomOut}
          className="flex h-6 w-6 items-center justify-center rounded text-[var(--color-text-dim)] hover:text-[var(--color-text-muted)] transition-colors"
          title="Zoom out"
          disabled={zoom <= 1}
        >
          <ZoomOut size={13} />
        </button>
        <button
          onClick={handleZoomIn}
          className="flex h-6 w-6 items-center justify-center rounded text-[var(--color-text-dim)] hover:text-[var(--color-text-muted)] transition-colors"
          title="Zoom in"
          disabled={zoom >= 20}
        >
          <ZoomIn size={13} />
        </button>

        {/* Loop toggle (only when regions enabled) */}
        {enableRegions && (
          <button
            onClick={toggleLoop}
            className={cn(
              'flex h-6 w-6 items-center justify-center rounded transition-colors',
              loopActive
                ? 'text-[var(--color-cyan)] bg-[var(--color-cyan)]/10'
                : 'text-[var(--color-text-dim)] hover:text-[var(--color-text-muted)]'
            )}
            title={loopActive ? 'Disable loop' : 'Enable A/B loop'}
          >
            <Repeat size={13} />
          </button>
        )}

        {/* Spectrogram toggle (placeholder for future) */}
        {showSpectrogram !== undefined && (
          <button
            className="flex h-6 w-6 items-center justify-center rounded text-[var(--color-text-dim)] hover:text-[var(--color-text-muted)] transition-colors opacity-50"
            title="Spectrogram (coming soon)"
            disabled
          >
            <Activity size={13} />
          </button>
        )}
      </div>
    </div>
  )
}))
