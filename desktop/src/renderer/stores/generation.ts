import { create } from 'zustand'
import type { GenerationMode, GenerateMusicRequest, JobResultItem } from '../api/types'
import { getDefaultGenerationParams } from '../api/types'

export interface GenerationResult {
  filePath: string
  audioUrl: string
  prompt: string
  lyrics: string
  metas: Record<string, any>
}

export interface BatchRecord {
  results: GenerationResult[]
  params: Partial<GenerateMusicRequest>
}

export interface GenerationSaveTarget {
  stationId?: string | null
  playlistId?: string | null
  runId?: string | null
}

export interface GenerationState {
  mode: GenerationMode
  params: Partial<GenerateMusicRequest>
  isGenerating: boolean
  progress: number
  progressText: string
  activeJobId: string | null
  results: GenerationResult[]
  currentBatchIndex: number
  batches: BatchRecord[]
  saveTarget: GenerationSaveTarget | null

  // Toggles
  thinkEnabled: boolean
  autoScore: boolean
  autoLRC: boolean
  autoGenerate: boolean

  // Actions
  setMode: (mode: GenerationMode) => void
  setParams: (partial: Partial<GenerateMusicRequest>) => void
  resetParams: () => void
  setGenerating: (isGenerating: boolean) => void
  setProgress: (progress: number, text?: string) => void
  setActiveJobId: (id: string | null) => void
  setResults: (results: GenerationResult[]) => void
  addBatch: (batch: BatchRecord) => void
  navigateBatch: (index: number) => void
  setSaveTarget: (target: GenerationSaveTarget | null) => void
  setThinkEnabled: (enabled: boolean) => void
  setAutoScore: (enabled: boolean) => void
  setAutoLRC: (enabled: boolean) => void
  setAutoGenerate: (enabled: boolean) => void
  loadFromTrack: (paramsJson: string, mode?: string) => void
}

export const useGenerationStore = create<GenerationState>((set, get) => ({
  mode: 'simple',
  params: getDefaultGenerationParams(),
  isGenerating: false,
  progress: 0,
  progressText: '',
  activeJobId: null,
  results: [],
  currentBatchIndex: 0,
  batches: [],
  saveTarget: null,
  thinkEnabled: false,
  autoScore: false,
  autoLRC: false,
  autoGenerate: false,

  setMode: (mode) => set({ mode }),
  setParams: (partial) =>
    set((state) => ({ params: { ...state.params, ...partial } })),
  resetParams: () => set({ params: getDefaultGenerationParams() }),
  setGenerating: (isGenerating) => set({ isGenerating }),
  setProgress: (progress, text) =>
    set({ progress, progressText: text || '' }),
  setActiveJobId: (id) => set({ activeJobId: id }),
  setResults: (results) => set({ results }),
  setSaveTarget: (target) => set({ saveTarget: target }),

  addBatch: (batch) =>
    set((state) => {
      const batches = [...state.batches, batch]
      return {
        batches,
        currentBatchIndex: batches.length - 1,
        results: batch.results
      }
    }),

  navigateBatch: (index) =>
    set((state) => {
      const batch = state.batches[index]
      if (!batch) return state
      return {
        currentBatchIndex: index,
        results: batch.results
      }
    }),

  setThinkEnabled: (enabled) => set({ thinkEnabled: enabled }),
  setAutoScore: (enabled) => set({ autoScore: enabled }),
  setAutoLRC: (enabled) => set({ autoLRC: enabled }),
  setAutoGenerate: (enabled) => set({ autoGenerate: enabled }),

  loadFromTrack: (paramsJson, mode) => {
    try {
      const params = JSON.parse(paramsJson)
      set({
        params: { ...getDefaultGenerationParams(), ...params },
        mode: (mode as GenerationMode) || 'custom'
      })
    } catch {
      console.error('Failed to load params from track')
    }
  }
}))
