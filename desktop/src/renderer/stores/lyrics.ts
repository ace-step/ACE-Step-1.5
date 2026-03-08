import { create } from 'zustand'
import { isElectron } from '../lib/utils'
import { parseLrc, serializeLrc, heuristicAlign, wordsToLrc } from '../lib/lrc'
import type { LrcLine } from '../lib/lrc'
import type { TrackRecord } from './library'

// ── Store Interface ──

export interface LyricsState {
  /** Track ID being edited */
  trackId: string | null
  /** Current LRC lines */
  lines: LrcLine[]
  /** Unsaved changes */
  isDirty: boolean
  /** Whisper alignment in progress */
  isAligning: boolean
  /** Last alignment error */
  alignError: string | null
  /** Line-level or word-level editing */
  editMode: 'line' | 'word'
  /** Tap-to-sync mode active */
  tapSyncActive: boolean
  /** Index of next line to stamp in tap-sync */
  tapSyncIndex: number

  // ── Actions ──
  openTrack: (track: TrackRecord) => void
  setLines: (lines: LrcLine[]) => void
  updateLineTime: (index: number, time: number) => void
  updateLineText: (index: number, text: string) => void
  insertLine: (index: number, line: LrcLine) => void
  deleteLine: (index: number) => void
  save: () => Promise<void>
  alignWithWhisper: (audioPath: string, language?: string) => Promise<void>
  runHeuristicAlign: (lyrics: string, duration: number, bpm?: number | null) => void
  setEditMode: (mode: 'line' | 'word') => void
  startTapSync: () => void
  stopTapSync: () => void
  tapLine: (currentTime: number) => void
  importLrc: (lrcText: string) => void
  exportLrc: () => string
  reset: () => void
}

// ── Store ──

export const useLyricsStore = create<LyricsState>((set, get) => ({
  trackId: null,
  lines: [],
  isDirty: false,
  isAligning: false,
  alignError: null,
  editMode: 'line',
  tapSyncActive: false,
  tapSyncIndex: 0,

  openTrack: (track) => {
    const lines = track.lrc_text ? parseLrc(track.lrc_text) : []
    set({
      trackId: track.id,
      lines,
      isDirty: false,
      isAligning: false,
      alignError: null,
      tapSyncActive: false,
      tapSyncIndex: 0
    })
  },

  setLines: (lines) => set({ lines, isDirty: true }),

  updateLineTime: (index, time) =>
    set((state) => {
      const lines = [...state.lines]
      if (index < 0 || index >= lines.length) return state
      lines[index] = { ...lines[index], time }
      // Re-sort by time
      lines.sort((a, b) => a.time - b.time)
      return { lines, isDirty: true }
    }),

  updateLineText: (index, text) =>
    set((state) => {
      const lines = [...state.lines]
      if (index < 0 || index >= lines.length) return state
      lines[index] = { ...lines[index], text }
      return { lines, isDirty: true }
    }),

  insertLine: (index, line) =>
    set((state) => {
      const lines = [...state.lines]
      lines.splice(index + 1, 0, line)
      return { lines, isDirty: true }
    }),

  deleteLine: (index) =>
    set((state) => {
      const lines = [...state.lines]
      if (index < 0 || index >= lines.length) return state
      lines.splice(index, 1)
      return { lines, isDirty: true }
    }),

  save: async () => {
    if (!isElectron) return
    const { trackId, lines } = get()
    if (!trackId) return

    const lrcText = serializeLrc(lines)
    try {
      // Import dynamically to avoid circular deps
      const { useLibraryStore } = await import('./library')
      await useLibraryStore.getState().updateTrack(trackId, { lrc_text: lrcText })
      set({ isDirty: false })
    } catch (err) {
      console.error('Failed to save LRC:', err)
    }
  },

  alignWithWhisper: async (audioPath, language) => {
    if (!isElectron) return
    set({ isAligning: true, alignError: null })

    try {
      const { transcribeAudio } = await import('../api/client')
      const result = await transcribeAudio(audioPath, language)

      if (result.words && result.words.length > 0) {
        const lines = wordsToLrc(result.words)
        set({ lines, isDirty: true, isAligning: false })
      } else if (result.lrc_text) {
        const lines = parseLrc(result.lrc_text)
        set({ lines, isDirty: true, isAligning: false })
      } else {
        set({ isAligning: false, alignError: 'No timestamps returned from Whisper' })
      }
    } catch (err: any) {
      set({ isAligning: false, alignError: err.message || 'Alignment failed' })
    }
  },

  runHeuristicAlign: (lyrics, duration, bpm) => {
    const lines = heuristicAlign(lyrics, duration, bpm)
    set({ lines, isDirty: true })
  },

  setEditMode: (mode) => set({ editMode: mode }),

  startTapSync: () => set({ tapSyncActive: true, tapSyncIndex: 0 }),

  stopTapSync: () => set({ tapSyncActive: false }),

  tapLine: (currentTime) =>
    set((state) => {
      if (!state.tapSyncActive) return state
      const { tapSyncIndex, lines } = state
      if (tapSyncIndex >= lines.length) {
        return { tapSyncActive: false }
      }
      const updated = [...lines]
      updated[tapSyncIndex] = { ...updated[tapSyncIndex], time: currentTime }
      return {
        lines: updated,
        tapSyncIndex: tapSyncIndex + 1,
        isDirty: true,
        // Auto-stop after last line
        tapSyncActive: tapSyncIndex + 1 < lines.length
      }
    }),

  importLrc: (lrcText) => {
    const lines = parseLrc(lrcText)
    set({ lines, isDirty: true })
  },

  exportLrc: () => {
    return serializeLrc(get().lines)
  },

  reset: () =>
    set({
      trackId: null,
      lines: [],
      isDirty: false,
      isAligning: false,
      alignError: null,
      tapSyncActive: false,
      tapSyncIndex: 0
    })
}))
