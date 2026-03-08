/**
 * TrackDetailView — 420px right panel in the Library for editing
 * track metadata and lyrics synchronization.
 *
 * Tabs: Lyrics | Info
 *
 * Lyrics tab: WaveformPlayer + LyricsTimeline overlay + toolbar + LyricsEditor + KaraokePreview
 * Info tab: Read-only metadata display (future: editable fields)
 */

import { useRef, useState, useCallback, useEffect } from 'react'
import {
  X, Music2, Save, Upload, Download, Keyboard,
  Wand2, Loader2, AlertCircle, Type, AlignLeft
} from 'lucide-react'
import { cn, formatDuration } from '../../lib/utils'
import { useLibraryStore } from '../../stores/library'
import { useLyricsStore } from '../../stores/lyrics'
import { WaveformPlayer, type WaveformPlayerHandle } from '../audio/WaveformPlayer'
import { LyricsTimeline } from './LyricsTimeline'
import { LyricsEditor } from './LyricsEditor'
import { KaraokePreview } from './KaraokePreview'
import { getTrackAudioUrl } from '../../hooks/useTrackAudioUrl'
import { isElectron } from '../../lib/utils'

type DetailTab = 'lyrics' | 'info'

export function TrackDetailView() {
  const detailTrackId = useLibraryStore((s) => s.detailTrackId)
  const tracks = useLibraryStore((s) => s.tracks)
  const openTrackDetail = useLibraryStore((s) => s.openTrackDetail)

  const track = tracks.find((t) => t.id === detailTrackId)

  const {
    openTrack, save, isDirty, isAligning, alignError,
    editMode, setEditMode, lines,
    tapSyncActive, startTapSync, stopTapSync,
    alignWithWhisper, runHeuristicAlign, importLrc, exportLrc,
    reset
  } = useLyricsStore()

  const [activeTab, setActiveTab] = useState<DetailTab>('lyrics')
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)

  const playerRef = useRef<WaveformPlayerHandle | null>(null)
  const audioUrl = track ? getTrackAudioUrl(track.file_path) : ''

  // Open track in lyrics store when detail track changes
  useEffect(() => {
    if (track) {
      openTrack(track)
    }
    return () => { reset() }
  }, [track?.id])

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        openTrackDetail(null)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [openTrackDetail])

  // ── Handlers ──

  const handleSync = useCallback(async () => {
    if (!track) return
    try {
      await alignWithWhisper(track.file_path, track.vocal_language || undefined)
    } catch {
      // Fallback to heuristic
      if (track.lyrics && duration > 0) {
        runHeuristicAlign(track.lyrics, duration, track.bpm)
      }
    }
  }, [track, duration, alignWithWhisper, runHeuristicAlign])

  const handleHeuristicSync = useCallback(() => {
    if (!track?.lyrics || duration <= 0) return
    runHeuristicAlign(track.lyrics, duration, track.bpm)
  }, [track, duration, runHeuristicAlign])

  const handleImport = useCallback(async () => {
    if (!isElectron) return
    const paths = await window.aceStep.fs.openDialog({
      properties: ['openFile'],
      filters: [{ name: 'LRC Files', extensions: ['lrc', 'txt'] }],
      title: 'Import LRC File'
    })
    if (paths.length > 0) {
      const content = await window.aceStep.fs.readTextFile(paths[0])
      importLrc(content)
    }
  }, [importLrc])

  const handleExport = useCallback(async () => {
    if (!isElectron) return
    const filename = track?.caption
      ? `${track.caption.replace(/[^a-zA-Z0-9-_ ]/g, '').slice(0, 50)}.lrc`
      : 'lyrics.lrc'
    const savePath = await window.aceStep.fs.saveDialog({
      defaultPath: filename,
      filters: [{ name: 'LRC Files', extensions: ['lrc'] }],
      title: 'Export LRC File'
    })
    if (savePath) {
      const content = exportLrc()
      await window.aceStep.fs.writeTextFile(savePath, content)
    }
  }, [track, exportLrc])

  const handleSave = useCallback(async () => {
    await save()
  }, [save])

  if (!track) return null

  return (
    <div className="flex w-[420px] shrink-0 flex-col border-l border-white/5 bg-[var(--color-bg-primary)]">
      {/* ── Header ── */}
      <div className="flex items-center gap-2 border-b border-white/5 px-3 py-2">
        <Music2 size={14} className="shrink-0 text-[var(--color-violet)]" />
        <h3 className="flex-1 truncate text-xs font-medium text-[var(--color-text-primary)]">
          {track.caption || 'Untitled Track'}
        </h3>
        {isDirty && (
          <span className="shrink-0 rounded bg-amber-500/10 px-1.5 py-0.5 text-[9px] text-amber-400">
            unsaved
          </span>
        )}
        <button
          onClick={() => openTrackDetail(null)}
          className="flex h-6 w-6 items-center justify-center rounded text-[var(--color-text-dim)] hover:bg-white/5 hover:text-[var(--color-text-primary)] transition-colors"
          title="Close (Esc)"
        >
          <X size={14} />
        </button>
      </div>

      {/* ── Waveform Player ── */}
      <div className="px-3 pt-2">
        <WaveformPlayer
          ref={playerRef}
          audioUrl={audioUrl}
          trackId={track.id}
          height={80}
          enableRegions={true}
          onTimeUpdate={setCurrentTime}
          onPlayStateChange={setIsPlaying}
          onReady={setDuration}
        />
        {/* Lyrics regions overlay (no visible DOM) */}
        <LyricsTimeline playerRef={playerRef} duration={duration} />
      </div>

      {/* ── Tab bar ── */}
      <div className="flex border-b border-white/5 px-3 mt-1">
        {(['lyrics', 'info'] as DetailTab[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={cn(
              'px-3 py-1.5 text-[11px] font-medium capitalize transition-colors border-b-2',
              activeTab === tab
                ? 'border-[var(--color-violet)] text-[var(--color-text-primary)]'
                : 'border-transparent text-[var(--color-text-dim)] hover:text-[var(--color-text-muted)]'
            )}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* ── Tab content ── */}
      {activeTab === 'lyrics' ? (
        <div className="flex flex-1 flex-col overflow-hidden">
          {/* Lyrics toolbar */}
          <div className="flex flex-wrap items-center gap-1 border-b border-white/5 px-3 py-1.5">
            {/* Sync button */}
            <button
              onClick={handleSync}
              disabled={isAligning}
              className={cn(
                'flex items-center gap-1 rounded px-2 py-1 text-[10px] font-medium transition-colors',
                isAligning
                  ? 'bg-[var(--color-violet)]/10 text-[var(--color-violet)]'
                  : 'bg-[var(--color-violet)]/20 text-[var(--color-violet)] hover:bg-[var(--color-violet)]/30'
              )}
              title="AI-sync lyrics using Whisper (requires OpenAI API key)"
            >
              {isAligning ? <Loader2 size={11} className="animate-spin" /> : <Wand2 size={11} />}
              {isAligning ? 'Syncing…' : 'Sync Lyrics'}
            </button>

            {/* Heuristic fallback */}
            {track.lyrics && (
              <button
                onClick={handleHeuristicSync}
                className="flex items-center gap-1 rounded px-2 py-1 text-[10px] text-[var(--color-text-dim)] hover:bg-white/5 hover:text-[var(--color-text-muted)] transition-colors"
                title="Spread lyrics evenly (no AI, uses BPM)"
              >
                <AlignLeft size={11} />
                Even
              </button>
            )}

            {/* Spacer */}
            <div className="flex-1" />

            {/* Line/Word toggle */}
            <button
              onClick={() => setEditMode(editMode === 'line' ? 'word' : 'line')}
              className={cn(
                'flex items-center gap-1 rounded px-1.5 py-1 text-[10px] transition-colors',
                editMode === 'word'
                  ? 'bg-[var(--color-cyan)]/10 text-[var(--color-cyan)]'
                  : 'text-[var(--color-text-dim)] hover:bg-white/5'
              )}
              title={editMode === 'word' ? 'Word-level mode' : 'Line-level mode'}
            >
              <Type size={11} />
              {editMode === 'word' ? 'Word' : 'Line'}
            </button>

            {/* Tap-to-sync */}
            <button
              onClick={() => tapSyncActive ? stopTapSync() : startTapSync()}
              className={cn(
                'flex items-center gap-1 rounded px-1.5 py-1 text-[10px] transition-colors',
                tapSyncActive
                  ? 'bg-[var(--color-cyan)]/10 text-[var(--color-cyan)]'
                  : 'text-[var(--color-text-dim)] hover:bg-white/5'
              )}
              title="Tap Space/Enter to stamp each line's time during playback"
            >
              <Keyboard size={11} />
              Tap
            </button>

            {/* Import */}
            <button
              onClick={handleImport}
              className="flex h-6 w-6 items-center justify-center rounded text-[var(--color-text-dim)] hover:bg-white/5 hover:text-[var(--color-text-muted)] transition-colors"
              title="Import .lrc file"
            >
              <Upload size={12} />
            </button>

            {/* Export */}
            <button
              onClick={handleExport}
              disabled={lines.length === 0}
              className="flex h-6 w-6 items-center justify-center rounded text-[var(--color-text-dim)] hover:bg-white/5 hover:text-[var(--color-text-muted)] transition-colors disabled:opacity-30"
              title="Export .lrc file"
            >
              <Download size={12} />
            </button>

            {/* Save */}
            <button
              onClick={handleSave}
              disabled={!isDirty}
              className={cn(
                'flex h-6 w-6 items-center justify-center rounded transition-colors',
                isDirty
                  ? 'text-amber-400 hover:bg-amber-500/10'
                  : 'text-[var(--color-text-dim)] opacity-30'
              )}
              title="Save to track"
            >
              <Save size={12} />
            </button>
          </div>

          {/* Error banner */}
          {alignError && (
            <div className="flex items-center gap-2 bg-red-500/10 px-3 py-1.5 text-[10px] text-red-400">
              <AlertCircle size={12} />
              <span className="flex-1">{alignError}</span>
              <button
                onClick={() => useLyricsStore.setState({ alignError: null })}
                className="shrink-0 text-red-400/60 hover:text-red-400"
              >
                <X size={10} />
              </button>
            </div>
          )}

          {/* Lyrics editor (scrollable) */}
          <LyricsEditor currentTime={currentTime} playerRef={playerRef} />

          {/* Karaoke preview bar */}
          <KaraokePreview currentTime={currentTime} isPlaying={isPlaying} />
        </div>
      ) : (
        /* ── Info tab ── */
        <div className="flex-1 overflow-y-auto px-3 py-2">
          <div className="flex flex-col gap-2">
            <InfoRow label="Caption" value={track.caption} />
            <InfoRow label="BPM" value={track.bpm != null ? String(Math.round(track.bpm)) : null} />
            <InfoRow label="Key" value={track.key_scale} />
            <InfoRow label="Duration" value={track.duration_seconds != null ? formatDuration(track.duration_seconds) : null} />
            <InfoRow label="Time Sig" value={track.time_signature} />
            <InfoRow label="Language" value={track.vocal_language} />
            <InfoRow label="Mode" value={track.generation_mode} />
            <InfoRow label="Task" value={track.task_type} />
            <InfoRow label="Steps" value={track.inference_steps != null ? String(track.inference_steps) : null} />
            <InfoRow label="Guidance" value={track.guidance_scale != null ? String(track.guidance_scale) : null} />
            <InfoRow label="Seed" value={track.seed} />
            <InfoRow label="Format" value={track.audio_format} />
            {track.notes && <InfoRow label="Notes" value={track.notes} />}
            {track.lyrics && (
              <div className="mt-1">
                <span className="text-[10px] text-[var(--color-text-dim)]">Lyrics</span>
                <p className="mt-0.5 whitespace-pre-wrap text-[11px] text-[var(--color-text-muted)] bg-white/[0.02] rounded p-2 max-h-40 overflow-y-auto">
                  {track.lyrics}
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null
  return (
    <div className="flex items-baseline gap-2">
      <span className="shrink-0 w-16 text-[10px] text-[var(--color-text-dim)]">{label}</span>
      <span className="text-[11px] text-[var(--color-text-muted)] truncate">{value}</span>
    </div>
  )
}
