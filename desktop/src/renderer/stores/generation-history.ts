import { create } from 'zustand'

import type {
  CreateGenerationHistoryInput,
  GenerationHistoryEntry,
  GenerationHistoryResultSnapshot
} from '../../shared/generation-history'
import type { GenerateMusicRequest, GenerationMode } from '../api/types'
import { getDefaultGenerationParams } from '../api/types'
import { getTrackAudioUrl } from '../hooks/useTrackAudioUrl'
import type { GenerationResult } from './generation'
import { useGenerationStore } from './generation'
import { useUIStore } from './ui'

type GenerationWorkspaceView = 'results' | 'history'

interface GenerationHistoryState {
  entries: GenerationHistoryEntry[]
  activeView: GenerationWorkspaceView
  loading: boolean
  error: string | null

  loadEntries: (limit?: number) => Promise<void>
  recordCompletedBatch: (
    results: GenerationResult[],
    params: Partial<GenerateMusicRequest>,
    mode: string,
    trackIds?: string[]
  ) => Promise<void>
  applyEntry: (entry: GenerationHistoryEntry) => void
  openEntryResults: (entry: GenerationHistoryEntry) => void
  setView: (view: GenerationWorkspaceView) => void
  clearError: () => void
}

const VALID_GENERATION_MODES = new Set<GenerationMode>([
  'simple',
  'custom',
  'remix',
  'repaint',
  'extract',
  'lego',
  'complete'
])

function normalizeMode(mode: string | null): GenerationMode {
  return mode && VALID_GENERATION_MODES.has(mode as GenerationMode)
    ? (mode as GenerationMode)
    : 'custom'
}

function toResultSnapshots(results: GenerationResult[]): GenerationHistoryResultSnapshot[] {
  return results.map((result) => ({
    prompt: result.prompt || '',
    lyrics: result.lyrics || '',
    metas: result.metas || {}
  }))
}

function toCreateInput(
  results: GenerationResult[],
  params: Partial<GenerateMusicRequest>,
  mode: string,
  trackIds: string[]
): CreateGenerationHistoryInput {
  return {
    mode,
    params_json: params as Record<string, unknown>,
    result_json: toResultSnapshots(results),
    track_ids: trackIds
  }
}

function toGenerationResults(entry: GenerationHistoryEntry): GenerationResult[] {
  if (entry.tracks.length > 0) {
    return entry.tracks.map((track, index) => {
      const snapshot = entry.result_json[index]
      const metas = (snapshot?.metas || {}) as Record<string, unknown>
      return {
        filePath: track.file_path,
        audioUrl: getTrackAudioUrl(track.file_path),
        prompt: snapshot?.prompt || track.caption || '',
        lyrics: snapshot?.lyrics || track.lyrics || '',
        metas: {
          ...metas,
          duration: track.duration_seconds ?? (metas.duration as number | undefined),
          bpm: track.bpm ?? (metas.bpm as number | undefined),
          keyscale: track.key_scale ?? (metas.keyscale as string | undefined),
          timesignature: track.time_signature ?? (metas.timesignature as string | undefined)
        }
      }
    })
  }

  return entry.result_json.map((result, index) => ({
    filePath: `history:${entry.id}:${index}`,
    audioUrl: '',
    prompt: result.prompt,
    lyrics: result.lyrics,
    metas: result.metas || {}
  }))
}

export const useGenerationHistoryStore = create<GenerationHistoryState>((set) => ({
  entries: [],
  activeView: 'results',
  loading: false,
  error: null,

  loadEntries: async (limit = 50) => {
    set({ loading: true, error: null })
    try {
      const entries = await window.aceStep.generationHistory.list(limit)
      set({ entries, loading: false })
    } catch (error: any) {
      set({ loading: false, error: error?.message || 'Failed to load generation history.' })
    }
  },

  recordCompletedBatch: async (results, params, mode, trackIds = []) => {
    try {
      const created = await window.aceStep.generationHistory.create(
        toCreateInput(results, params, mode, trackIds)
      )
      set((state) => ({
        entries: [created, ...state.entries.filter((entry) => entry.id !== created.id)]
      }))
    } catch (error: any) {
      set({ error: error?.message || 'Failed to record generation history.' })
    }
  },

  applyEntry: (entry) => {
    const mode = normalizeMode(entry.mode)
    const params = {
      ...getDefaultGenerationParams(),
      ...(entry.params_json || {})
    } as Partial<GenerateMusicRequest>

    useGenerationStore.setState({ mode, params })
    useUIStore.getState().setActiveSection('generate')
  },

  openEntryResults: (entry) => {
    const mode = normalizeMode(entry.mode)
    const params = {
      ...getDefaultGenerationParams(),
      ...(entry.params_json || {})
    } as Partial<GenerateMusicRequest>
    const results = toGenerationResults(entry)

    useGenerationStore.setState({
      mode,
      params,
      results,
      batches: [{ results, params }],
      currentBatchIndex: 0
    })
    useUIStore.getState().setActiveSection('generate')
    set({ activeView: 'results' })
  },

  setView: (view) => set({ activeView: view }),
  clearError: () => set({ error: null })
}))
